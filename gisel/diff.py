#!/usr/bin/env python3
"""Compare two answer JSONL files over the full query set.

Unlike ``gisel cases --against``, this is not an intersection report: a key
present on one side and absent on the other is a failure.  The contract is
"same queries, same answers", which is what an A/B legalizer comparison needs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import eval as E


def _key(q):
    mem = None
    if q.get("mem"):
        mem = (E.parse_case_llt(q["mem"][0]), int(q["mem"][1]))
    return (q["config"], q["name"],
            tuple(E.parse_case_llt(t) for t in q.get("types", [])),
            mem, tuple(q.get("imms") or []))


def _answer(q):
    if q.get("status") == "unanswerable":
        return ("unanswerable", q.get("reason", ""))
    new = q.get("new_type")
    return ("answered", q["action"], int(q.get("type_idx", 0)),
            E.parse_case_llt(new) if isinstance(new, str) else ("invalid",))


def _load(path):
    out = {}
    errors = 0
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                q = json.loads(line)
                k = _key(q)
                a = _answer(q)
            except (ValueError, KeyError, TypeError, E.EvalError) as exc:
                print("%s:%d: %s" % (path, lineno, exc), file=sys.stderr)
                errors += 1
                continue
            if k in out:
                print("%s:%d: duplicate key %r" % (path, lineno, k),
                      file=sys.stderr)
                errors += 1
                continue
            out[k] = a
    return out, errors


def compare(ref, ours):
    keys = sorted(set(ref) | set(ours), key=repr)
    matched = [k for k in keys if k in ref and k in ours]
    agree = 0
    unanswerable = 0
    disagree = []
    for k in matched:
        a, b = ref[k], ours[k]
        same_unanswerable = (a[0] == b[0] == "unanswerable"
                             and a[1] == b[1])
        same_answer = (a[0] == b[0] == "answered"
                       and a[1] == b[1] and a[2] == b[2]
                       and E.values_equal(a[3], b[3]))
        if same_unanswerable or same_answer:
            agree += 1
            unanswerable += int(same_unanswerable)
        else:
            disagree.append((k, a, b))
    return {
        "ref": len(ref),
        "ours": len(ours),
        "matched": len(matched),
        "agree": agree,
        "unanswerable": unanswerable,
        "disagree": len(disagree),
        "missing_ref": len(set(ours) - set(ref)),
        "missing_ours": len(set(ref) - set(ours)),
        "first": disagree[:20],
        "missing_ref_keys": sorted(set(ours) - set(ref), key=repr)[:20],
        "missing_ours_keys": sorted(set(ref) - set(ours), key=repr)[:20],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="gisel diff",
        description="compare two full-answer JSONL files")
    ap.add_argument("ref")
    ap.add_argument("ours")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ref, e1 = _load(args.ref)
    ours, e2 = _load(args.ours)
    result = compare(ref, ours)
    result["errors"] = e1 + e2
    if args.json:
        print(json.dumps(result, indent=1, sort_keys=True))
    else:
        print("ref=%d ours=%d matched=%d agree=%d unanswerable=%d disagree=%d "
              "missing_ref=%d missing_ours=%d errors=%d"
              % (result["ref"], result["ours"], result["matched"],
                 result["agree"], result["unanswerable"], result["disagree"],
                 result["missing_ref"], result["missing_ours"],
                 result["errors"]))
        for key, a, b in result["first"]:
            print("MISMATCH %r: ref=%r ours=%r" % (key, a, b))
        for key in result["missing_ref_keys"][:5]:
            print("MISSING in ref: %r" % (key,))
        for key in result["missing_ours_keys"][:5]:
            print("MISSING in ours: %r" % (key,))
    if result["errors"]:
        return 2
    if (result["missing_ref"] or result["missing_ours"]
            or result["disagree"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
