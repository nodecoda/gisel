#!/usr/bin/env python3
"""Enumerate the answerless query domain (D*) for one `.gisel` source.

This is deliberately not a test-case generator: it never evaluates a rule.
The axes come from upstream facts -- the opcode's declared type slots
(`data/opcode-slots.json`) and the source's type/memory declarations -- so the
query set cannot be biased towards the rules under test.

Output is the same JSONL query shape the oracle dumps use, without the
`action` / `type_idx` / `new_type` columns:

    {"config": "C0", "name": "G_LOAD", "types": ["s8", "p0:64"],
     "mem": ["s8", 1], "imms": []}

The domain is finite and configuration-specific: the pointer width is a
property of the subtarget, so a mixed 32/64-bit configuration set needs one
run per width (`--pointer-width 32` / `64`).
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

from . import ast as A
from . import axes as axesmod
from . import analysis as AN
from . import corpus as corpora
from . import cases as C
from . import llt as L
from . import eval as E
from . import llt as L
from . import output
from . import dsl


def _data_path(name):
    return Path(__file__).resolve().parent / "data" / name


def load_opcode_slots(path=None):
    """The frozen GenericOpcodes.td table: arity plus pointer slot indices."""
    raw = json.loads(Path(path).read_text() if path else
                     _data_path("opcode-slots.json").read_text())
    return raw.get("opcodes", raw)


def _resolve(text, pointer_width):
    """Turn a configuration-dependent pointer spelling into a concrete one."""
    return text.replace("p0:*", "p0:%d" % pointer_width).replace(
        "p0:64", "p0:%d" % pointer_width)


def _named_types(source, pointer_width):
    """Every declared named type, with `p0:*` resolved for this subtarget.

    The core document drops wildcard spellings from `domain.types`, which
    loses `v2p0` / `v4p0`.  They are real domain values, so recover them from
    the source declarations rather than from the normal form.
    """
    gs = A.parse_program(Path(source).read_text())
    out = set()
    for decl in gs.decls:
        if isinstance(decl, A.NamedType):
            out.add(_resolve(A.llt_text(decl.llt), pointer_width))
    return out


def _walk_mem_rows(node, out, pointer_width):
    if isinstance(node, dict):
        if node.get("kind") == "inMemDesc":
            args = node.get("args", [])
            if len(args) >= 4 and isinstance(args[3], dict):
                for row in args[3].get("elems", []):
                    if isinstance(row, (list, tuple)) and len(row) >= 4:
                        for text in AN.type_value_spellings(row[2]):
                            mty = _resolve(text, pointer_width)
                            try:
                                t = E.parse_case_llt(mty)
                            except E.EvalError:
                                continue
                            bits = L.total_bits(t)
                            if bits:
                                out.add((mty, bits, int(row[3])))
        for value in node.values():
            _walk_mem_rows(value, out, pointer_width)
    elif isinstance(node, list):
        for value in node:
            _walk_mem_rows(value, out, pointer_width)


def _reads_mem(node):
    if isinstance(node, dict):
        if node.get("kind") in ("inMemDesc", "memSlot", "memSize",
                                "typeDiffersFromMemDesc"):
            return True
        return any(_reads_mem(v) for v in node.values())
    if isinstance(node, list):
        return any(_reads_mem(v) for v in node)
    return False


def domain_axes(source, pointer_width=64):
    """`(types, mems, doc)` for one source and pointer width."""
    doc = AN.document(source)
    types = {_resolve(t, pointer_width) for t in doc["domain"]["types"]}
    types |= _named_types(source, pointer_width)
    mems = set()
    for rs in doc["rulesets"]:
        for rule in rs["rules"]:
            _walk_mem_rows(rule["predicate"], mems, pointer_width)
    return sorted(types), sorted(mems), doc


def _apply_mem_axis(mems, axes, pointer_width):
    """Profile rows -> the `(mty, bits, align)` tuples this command emits."""
    rows = axes.apply_mems([(mty, "", mty, align)
                            for mty, _bits, align in mems])
    out = []
    for _t0, _t1, mty, align in rows:
        mty = _resolve(str(mty), pointer_width)
        try:
            parsed = E.parse_case_llt(mty)
        except E.EvalError:
            continue
        bits = L.total_bits(parsed)
        if bits:
            out.append((mty, bits, int(align)))
    return sorted(set(out))


def effective_axes(source, pointer_width=64, axes=None):
    """`domain_axes` with an optional profile applied."""
    types, mems, doc = domain_axes(source, pointer_width)
    if axes is not None:
        types = [L.spell(t) for t in axes.apply_types(
            [E.parse_case_llt(t) for t in types])]
        mems = _apply_mem_axis(mems, axes, pointer_width)
    return types, mems, doc


def enumerate_domain(source, features, configs=None, pointer_width=64,
                     slots=None, axes=None, stats=None):
    """Yield answerless queries for every (config, opcode, types, mem).

    ``stats`` (optional dict) is filled when the generator is exhausted with
    the two ways the domain is narrowed before a query exists:

    - ``skipped_opcodes``: opcodes whose arity is unknown to both the slot
      table and the arity manifest, so no slot axis can be built;
    - ``shape_dropped`` / ``shape_dropped_total``: type tuples rejected by
      ``type_shape_ok`` (not real MIR), counted per opcode.

    Both are counted in **type tuples**, not queries: the drop happens before
    the mem/imm product, so a dropped tuple would otherwise have become
    ``len(mem_axis) * len(imm_tuples)`` queries.  Saying which unit is being
    counted is the point -- a denominator nobody can recompute is not a
    denominator.
    """
    types, mems, doc = effective_axes(source, pointer_width, axes)
    slots = slots if slots is not None else load_opcode_slots()
    manifest = dsl.load_arity_manifest()
    configs = list(configs or sorted(features.table))
    parsed = {}

    def _llt(text):
        if text not in parsed:
            parsed[text] = E.parse_case_llt(text)
        return parsed[text]

    skipped = []
    shape_dropped = {}
    per_config = {}

    for config in configs:
        width = axes.pointer_width(config, pointer_width) if axes else pointer_width
        per_config[config] = ((width,) + effective_axes(source, width, axes)[:2]
                              if width != pointer_width else
                              (width, types, mems))

    for rs in doc["rulesets"]:
        uses_mem = any(_reads_mem(rule["predicate"]) for rule in rs["rules"])
        _nslots, infos = AN.inspect_ruleset(rs)
        uses_ordering = any(info.uses_ordering for info in infos)
        mem_pairs = (axes.ordering_pairs()
                     if (axes is not None and uses_ordering)
                     else [("NotAtomic", "NotAtomic")])
        imm_axis = AN.imm_candidates(infos, axes)
        imm_tuples = AN.imm_tuples(imm_axis)
        for opcode in rs["opcodes"]:
            info = slots.get(opcode, {})
            arity = info.get("arity")
            if arity is None:
                arity = manifest.get(opcode)
            if arity is None:
                skipped.append(opcode)
                continue
            ptype = set(info.get("ptype", ()))
            for config in configs:
                width, cfg_types, cfg_mems = per_config[config]
                slot_axes = [[_resolve("p0:*", width)] if i in ptype
                             else cfg_types for i in range(arity)]
                mem_axis = list(cfg_mems) if uses_mem else [None]
                for combo in itertools.product(*slot_axes):
                    if not C.type_shape_ok(opcode, [_llt(t) for t in combo]):
                        shape_dropped[opcode] = shape_dropped.get(opcode, 0) + 1
                        continue
                    for mem in mem_axis:
                        for ordering, failure in mem_pairs:
                            for imms in imm_tuples:
                                mem_json = None
                                if mem:
                                    mem_json = [mem[0], mem[2]]
                                    if (ordering, failure) != (
                                            "NotAtomic", "NotAtomic"):
                                        mem_json += [ordering, failure]
                                yield {
                                    "config": config,
                                    "name": opcode,
                                    "types": list(combo),
                                    "mem": mem_json,
                                    "imms": list(imms),
                                }
    if skipped:
        # Surface rather than silently narrowing the domain.
        sys.stderr.write("domain: skipped %d opcode(s) with unknown arity: %s\n"
                         % (len(skipped), ", ".join(sorted(set(skipped))[:8])))
    if shape_dropped:
        # A point whose type tuple cannot be a real MIR instruction is not part
        # of the domain.  Say how many, and for which opcodes: this is the part
        # of the product the answers cannot cover.
        sys.stderr.write(
            "domain: dropped %d ill-formed point(s): %s\n"
            % (sum(shape_dropped.values()),
               ", ".join("%s %d" % kv
                         for kv in sorted(shape_dropped.items()))))
    if stats is not None:
        stats["skipped_opcodes"] = sorted(set(skipped))
        stats["shape_dropped"] = dict(sorted(shape_dropped.items()))
        stats["shape_dropped_total"] = sum(shape_dropped.values())


def _inputs(args):
    """Resolve the positional source, --corpus, --features and --axes."""
    if args.source and args.corpus:
        raise corpora.CorpusError("give a .gisel source or --corpus NAME, "
                                  "not both")
    source, features, axes = args.source, args.features, args.axes
    if args.corpus:
        entry = corpora.get(args.corpus)
        source = str(entry.source)
        features = features or (str(entry.features) if entry.features else None)
        axes = axes or (str(entry.axes) if entry.axes else None)
    if not source:
        raise corpora.CorpusError(
            "give a .gisel source or --corpus NAME (bundled: %s)"
            % ", ".join(corpora.names()))
    return source, features, axes


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="gisel domain",
        description="enumerate the answerless query domain (D*)")
    ap.add_argument("source", nargs="?",
                    help="a .gisel source (or use --corpus NAME)")
    ap.add_argument("--corpus", metavar="NAME",
                    help="a bundled corpus: %s" % ", ".join(corpora.names()))
    ap.add_argument("--out", required=True)
    ap.add_argument("--features",
                    help="feature truth table (default: derive none/all/only-N)")
    ap.add_argument("--config", action="append", dest="configs",
                    help="limit to configs from --features (repeatable)")
    ap.add_argument("--pointer-width", type=int, default=64,
                    help="subtarget pointer width (default 64)")
    ap.add_argument("--slots", help="opcode slot table (default: bundled)")
    ap.add_argument("--axes", help="axis profile JSON (analysis only)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        source, features_path, axes_path = _inputs(args)
        axes = axesmod.load(axes_path) if axes_path else None
        _doc, features, axes = AN.session(
            source, features=features_path, configs=args.configs, axes=axes)
        if axes is not None:
            domain_profile = axes.profile("domain")
            if domain_profile.get("full", True) is False:
                raise axesmod.AxisError(
                    "%s: profiles.domain.full=false is not implemented"
                    % axes.path)
            max_points = int(domain_profile.get("max_points", 0))
        else:
            max_points = 0
    except (axesmod.AxisError, ValueError) as exc:
        print("gisel domain: %s" % exc, file=sys.stderr)
        return 2
    configs = sorted(features.table)
    if not configs:
        print("domain: no configurations selected", file=sys.stderr)
        return 2

    slots = load_opcode_slots(args.slots)
    diagnostics = {}
    rows = list(enumerate_domain(source, features, configs,
                                 args.pointer_width, slots, axes,
                                 diagnostics))
    raw_points = len(rows)
    truncated = bool(max_points and raw_points > max_points)
    if truncated:
        sys.stderr.write("domain: profile max_points truncates %d -> %d\n"
                         % (raw_points, max_points))
        rows = rows[:max_points]
    rows.sort(key=lambda q: (q["config"], q["name"], tuple(q["types"]),
                             json.dumps(q["mem"])))
    rc = output.write_lines(
        args.out, (json.dumps(row, sort_keys=True) + "\n" for row in rows))
    if rc:
        return rc

    types, mems, _ = effective_axes(source, args.pointer_width, axes)
    stats = {
        "configs": configs,
        "types": len(types),
        "mems": len(mems),
        "points": len(rows),
        "per_config": {c: sum(1 for r in rows if r["config"] == c)
                       for c in configs},
        "per_opcode": len({r["name"] for r in rows}),
        "raw_points": raw_points,
        "truncated": truncated,
    }
    stats.update(diagnostics)
    if args.json:
        print(json.dumps(stats, indent=1, sort_keys=True))
    else:
        print("%s: points=%d configs=%s types=%d mems=%d opcodes=%d "
              "shape_dropped=%d skipped=%d"
              % (args.out, stats["points"], ",".join(configs),
                 stats["types"], stats["mems"], stats["per_opcode"],
                 stats["shape_dropped_total"], len(stats["skipped_opcodes"])))
    return 0 if rows else 2


if __name__ == "__main__":
    sys.exit(main())
