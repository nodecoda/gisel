#!/usr/bin/env python3
"""Turn an AB diff into an attribution bundle.

    tools/ab/attribute.py --diff diff.json --doc core.json \
        --features features.json --queries queries.jsonl \
        --official official.answers.jsonl --ours ours.answers.jsonl \
        --eval eval.answers.jsonl --out bundle

The bundle is deterministic evidence for a human or an external agent:
groups by matrix class / diff class / opcode / config / rule, with the
smallest query key and the three answers.  This tool never calls a model.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gisel import answers as A  # noqa: E402
from gisel import cases as C  # noqa: E402
from gisel import eval as E  # noqa: E402


def answer_json(answer):
    if answer is None:
        return None
    if answer[0] == "unanswerable":
        return {"status": "unanswerable", "reason": answer[1]}
    return {"action": answer[1], "type_idx": answer[2],
            "new_type": C.llt_text(answer[3])}


def same(a, b, mode="full"):
    if a is None or b is None:
        return False
    if a[0] != b[0]:
        return False
    if a[0] == "unanswerable":
        return a[1] == b[1]
    if mode == "action":
        return a[1] == b[1]
    return a[1] == b[1] and a[2] == b[2] and E.values_equal(a[3], b[3])


def matrix_class(official, ours, evaluator):
    if evaluator is None:
        return "no_eval"
    if official is None or ours is None:
        return "missing"
    if same(official, ours) and same(official, evaluator):
        return "all_agree"
    if (official[0] == ours[0] == "unanswerable"
            and evaluator[0] == "answered"):
        return "both_assert"
    if (official[0] == "unanswerable" and ours[0] == "answered"
            and evaluator[0] == "answered"):
        return "official_assert"
    if (ours[0] == "unanswerable" and official[0] == "answered"
            and evaluator[0] == "answered"):
        return "ours_assert"
    if same(official, evaluator) and not same(ours, evaluator):
        return "translation"
    if same(ours, evaluator) and not same(official, evaluator):
        return "rule"
    if same(official, ours) and not same(official, evaluator):
        return "evaluator"
    return "multiple"


def load_queries(path):
    out = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        query = json.loads(line)
        out[A.key(query)] = query
    return out


OWNER = {
    "translation": "ours",
    "ours_assert": "ours",
    "rule": "ours-or-upstream",
    "evaluator": "ours",
    "official_assert": "llvm-or-query",
    "multiple": "unknown",
    "missing": "query-or-harness",
    "no_eval": "unknown",
    "all_agree": "none",
    "both_assert": "query",
}


def owner_for(matrix, ruleset):
    owner = OWNER.get(matrix, "unknown")
    if matrix == "official_assert" and ruleset is None:
        # No rule fired: the shape is likely outside the opcode's legal
        # operand space, so triage the query before blaming LLVM.
        return "query"
    return owner


def rule_for(doc, evaluator, query):
    case = C.Case(query["config"], query["name"],
                  tuple(query.get("types", [])),
                  C.mem_point(query.get("mem")), "", "", None, "",
                  imms=tuple(query.get("imms") or ()))
    fired = C._try_fire(evaluator, case)
    if fired in (None, "error"):
        return None, None
    return doc["rulesets"][fired[0]]["def"], fired[1]


def build_bundle(diff, doc, features, queries, official, ours, evaluator):
    ev = E.Evaluator(doc, features)
    groups = defaultdict(lambda: {"count": 0, "examples": []})
    matrix_counts = Counter()
    class_counts = Counter()
    owner_counts = Counter()
    for key in queries:
        matrix_counts[matrix_class(official.get(key), ours.get(key),
                                   evaluator.get(key))] += 1
    for item in diff.get("first_details", []):
        fields = item["key_fields"]
        key = A.key(fields)
        query = queries.get(key)
        ruleset = rule = None
        if query is not None:
            ruleset, rule = rule_for(doc, ev, query)
        o, u, e = official.get(key), ours.get(key), evaluator.get(key)
        kind = matrix_class(o, u, e)
        owner = owner_for(kind, ruleset)
        owner_counts[owner] += 1
        class_counts[item["class"]] += 1
        group = groups[(kind, item["class"], owner, fields["name"],
                        fields["config"], ruleset, rule)]
        group["count"] += 1
        if len(group["examples"]) < 3:
            group["examples"].append({
                "key": fields,
                "official": answer_json(o),
                "ours": answer_json(u),
                "eval": answer_json(e),
            })
    rows = []
    for (kind, cls, owner, opcode, config, ruleset, rule), group in groups.items():
        rows.append({
            "matrix": kind,
            "diff": cls,
            "owner": owner,
            "opcode": opcode,
            "config": config,
            "ruleset": ruleset,
            "rule": rule,
            "count": group["count"],
            "examples": group["examples"],
        })
    rows.sort(key=lambda r: (-r["count"], r["matrix"], r["opcode"],
                             r["config"], r["ruleset"] or "", r["rule"] or -1))
    return {
        "summary": {
            "diff": {k: diff.get(k) for k in
                     ("mode", "ref", "ours", "matched", "agree", "disagree",
                      "unanswerable", "missing_ref", "missing_ours", "errors")},
            "matrix": dict(matrix_counts),
            "diff_class": dict(class_counts),
            "owner": dict(owner_counts),
            "groups": len(rows),
        },
        "groups": rows,
    }


def markdown(bundle):
    summary = bundle["summary"]
    lines = [
        "# AB attribution bundle",
        "",
        "## Summary",
        "",
        "```text",
    ]
    for key, value in summary["diff"].items():
        if value is not None:
            lines.append("%s=%s" % (key, value))
    lines.append("matrix=%s" % json.dumps(summary["matrix"], sort_keys=True))
    lines.append("diff_class=%s" % json.dumps(summary["diff_class"],
                                               sort_keys=True))
    lines.append("owner=%s" % json.dumps(summary["owner"], sort_keys=True))
    lines.append("groups=%d" % summary["groups"])
    lines += [
        "```",
        "",
        "## Groups",
        "",
        "| count | owner | matrix | diff | opcode | config | ruleset#rule |",
        "|---:|---|---|---|---|---|---|",
    ]
    for row in bundle["groups"][:40]:
        rule = "%s#%s" % (row["ruleset"] or "-",
                          "-" if row["rule"] is None else row["rule"])
        lines.append("| %d | %s | %s | %s | %s | %s | %s |"
                     % (row["count"], row["owner"], row["matrix"],
                        row["diff"], row["opcode"], row["config"], rule))
    lines += ["", "## Examples", ""]
    for row in bundle["groups"][:20]:
        lines.append("### %s / %s / %s / %s#%s (%d)"
                     % (row["matrix"], row["diff"], row["opcode"],
                        row["config"], row["ruleset"] or "-", row["count"]))
        lines += ["```json", json.dumps(row["examples"][0], indent=1,
                                         sort_keys=True), "```", ""]
    return "\n".join(lines) + "\n"


def write_bundle(bundle, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    (out / "bundle.json").write_text(json.dumps(bundle, indent=1,
                                                sort_keys=True) + "\n")
    (out / "bundle.md").write_text(markdown(bundle))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="tools/ab/attribute.py",
        description="group an AB diff and add the three-way matrix")
    ap.add_argument("--diff", required=True)
    ap.add_argument("--doc", required=True, help="schema-0.4 core JSON")
    ap.add_argument("--features", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--official", required=True)
    ap.add_argument("--ours", required=True)
    ap.add_argument("--eval", help="eval answers; omit for diff-only bundles")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    diff = json.loads(Path(args.diff).read_text())
    doc = json.loads(Path(args.doc).read_text())
    features = E.load_features(args.features)
    queries = load_queries(Path(args.queries))
    official, e1 = A.load(args.official)
    ours, e2 = A.load(args.ours)
    evaluator, e3 = A.load(args.eval) if args.eval else ({}, 0)
    bundle = build_bundle(diff, doc, features, queries, official, ours,
                          evaluator)
    bundle["summary"]["reader_errors"] = e1 + e2 + e3
    write_bundle(bundle, Path(args.out))
    print("groups=%d matrix=%s diff_class=%s"
          % (bundle["summary"]["groups"],
             json.dumps(bundle["summary"]["matrix"], sort_keys=True),
             json.dumps(bundle["summary"]["diff_class"], sort_keys=True)))
    print("out=%s" % Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
