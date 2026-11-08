#!/usr/bin/env python3
"""Compare two full-answer JSONL files: the A/B workbench verb.

    tools/ab/diff.py REF ANSWERS [--json]

Exit codes: 0 = same queries, same answers; 1 = a disagreeing or missing key;
2 = an unreadable line or a key with two different answers.  This is the workbench side of the boundary in
``docs/SCOPE.md``: the comparison lives here, not in ``gisel``, because it
exists to compare a reference implementation with ours.  Only the answer-file
reader is shared from ``gisel.answers``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gisel import answers as A  # noqa: E402
from gisel import eval as E  # noqa: E402


def compare(ref, ours):
    """Full-set comparison: a key on one side only is a failure.

    Unlike ``gisel cases --against``, which reports the overlap, this is the
    workbench contract "same queries, same answers".
    """
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
        prog="tools/ab/diff.py",
        description="compare two full-answer JSONL files")
    ap.add_argument("ref")
    ap.add_argument("ours")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    ref, e1 = A.load(args.ref)
    ours, e2 = A.load(args.ours)
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
