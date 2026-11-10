#!/usr/bin/env python3
"""Explain every rule that `cases --strict-coverage` could not witness.

    coverage-report.py SOURCE STATS OUT [--features F] [--axes A]

`STATS` is the JSON `gisel cases --json` wrote.  For each unwitnessed rule this
classifies *why* there is no witness:

  dead-predicate                 the rule's predicate is false for every type
                                 in the declared domain;
  dead-guard                     the predicate holds, but the action's implicit
                                 shim guard (is_pow2, is_scalar, element count)
                                 is false for every sampled point;
  dominated                     a witness exists, but an earlier rule always
                                 answers it first (the `_fire` winner is listed);
  satisfiable-outside-query-product
                                 `_satisfiable` proves a point exists on the
                                 wider axis, but the query product never asks it
                                 (currently mem opcodes: only four type tuples
                                 are crossed with a descriptor).

This is a diagnostic, not a gate: `--strict-coverage` still exits 1 while any
rule lacks a witness.  The output is the per-rule evidence behind that exit.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gisel import analysis, ast as A, cases as C, eval as E  # noqa: E402
import gisel.axes as axesmod  # noqa: E402


def _parse_unwitnessed(stats):
    out = collections.defaultdict(dict)
    for entry in stats.get("unwitnessed", []):
        name, rest = entry.split("#", 1)
        index, reason = rest.split(":", 1)
        out[name][int(index)] = reason.strip()
    return out


def _rule_lines(source):
    program = A.parse_program(Path(source).read_text())
    return {rs.name: [rule.line for rule in rs.rules]
            for rs in program.rulesets}


def classify(doc, features, stats, axes=None, source=None):
    evaluator = E.Evaluator(doc, features)
    lines = _rule_lines(source) if source else {}
    configs = sorted(features.table)
    profile = axes.profile("cases") if axes is not None else {}
    max_slot = int(profile.get("max_slot_values", 16))
    wanted = _parse_unwitnessed(stats)
    out = []

    source_lines = None
    for rs_index, rs in enumerate(doc["rulesets"]):
        name = rs.get("def")
        if name not in wanted:
            continue
        opcode = rs["opcodes"][0]
        nslots, infos = C.inspect_ruleset(rs)
        domain = [E.parse_case_llt(t) for t in doc["domain"]["types"]]
        per = C._shape_candidates(opcode, C._candidates(
            infos, nslots, max_slot, domain, C._declares_scalable(doc)))
        if axes is not None:
            per = [axes.apply_types(slot) for slot in per]
        default = C._defaults(per)
        mem_entries = C._mem_candidates(infos)
        if axes is not None:
            mem_entries = axes.apply_mems(mem_entries)
        uses_mem = any(info.uses_mem for info in infos)
        uses_ordering = any(info.uses_ordering for info in infos)
        mem_pairs = (axes.ordering_pairs()
                     if (axes is not None and uses_ordering)
                     else [("NotAtomic", "NotAtomic")])
        imms = analysis.imm_tuples(C.imm_candidates(infos, axes))
        queries, _ = C._queries(per, default, mem_entries, uses_mem, imms,
                                mem_pairs, opcode)

        for rule_index, reported in sorted(wanted[name].items()):
            rule = rs["rules"][rule_index]
            pred = guard = 0
            winners = collections.Counter()
            example = {}
            for config in configs:
                for types, mem, imt in queries:
                    if uses_mem and mem is None:
                        continue
                    mems = ([E.MemDesc(E.parse_case_llt(mem[0]), mem[1],
                                       mem[2], mem[3])] if mem else [])
                    try:
                        if evaluator.bool_value(rule["predicate"], types, mems,
                                                config, imt) is not True:
                            continue
                    except Exception:
                        continue
                    pred += 1
                    try:
                        ok, _ = E.shim_guard_and_newtype(
                            rule.get("op"), rule.get("on"), rule.get("to"),
                            types, mems, evaluator, config, imt)
                    except Exception:
                        ok = False
                    if not ok:
                        continue
                    guard += 1
                    try:
                        result = C._fire(evaluator, config, opcode, types,
                                         mems, imt)
                    except Exception as exc:
                        key = ("error", type(exc).__name__)
                    else:
                        key = ("no-rule",) if result is None \
                            else (result[0], result[1])
                    winners[key] += 1
                    if key not in example:
                        example[key] = {
                            "config": config,
                            "types": [E.fmt_oracle_llt(t) for t in types],
                            "mem": list(mem) if mem else None,
                            "imms": list(imt),
                        }

            if reported == "shadowed":
                if guard and all(key != (rs_index, rule_index)
                                 for key in winners):
                    klass = "dominated"
                    detail = "an earlier rule answers every sampled point"
                else:
                    klass = "satisfiable-outside-query-product"
                    detail = ("_satisfiable finds a point on the wider axis; "
                              "the query product does not sample it")
            elif pred == 0:
                klass = "dead-predicate"
                detail = "predicate is false for every type in the domain"
            else:
                klass = "dead-guard"
                detail = ("predicate holds, but the implicit action guard is "
                          "false for every sampled point")

            out.append({
                "ruleset": name,
                "rule": rule_index,
                "line": (lines.get(name) or [None] * (rule_index + 1))[rule_index],
                "source": None,
                "reported": reported,
                "class": klass,
                "detail": detail,
                "pred_true": pred,
                "guard_true": guard,
                "winners": [
                    {"ruleset": key[0] if len(key) > 1 else None,
                     "rule": key[1] if len(key) > 1 else None,
                     "count": count,
                     "example": example.get(key)}
                    for key, count in winners.most_common(3)
                ] if klass == "dominated" else [],
            })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="coverage-report.py")
    ap.add_argument("source")
    ap.add_argument("stats")
    ap.add_argument("out")
    ap.add_argument("--features")
    ap.add_argument("--axes")
    args = ap.parse_args(argv)

    doc = C.document(args.source)
    axes = axesmod.load(args.axes) if args.axes else None
    features = C.derive_features(doc, args.features
                                 or (axes.configs_path if axes else None))
    if axes is not None:
        full = C.derive_features(doc, args.features or axes.configs_path)
        axes.bind(args.source, doc, full)
        axes.apply_features(features)
    stats = json.loads(Path(args.stats).read_text())
    report = classify(doc, features, stats, axes, args.source)

    text = Path(args.source).read_text().splitlines()
    for row in report:
        row["source"] = (text[row["line"] - 1].strip()
                         if row["line"] else None)
    Path(args.out).write_text(json.dumps(report, indent=1) + "\n")
    counts = collections.Counter(row["class"] for row in report)
    print("coverage-report: %d unwitnessed: %s"
          % (len(report), ", ".join("%s=%d" % kv
                                    for kv in sorted(counts.items()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
