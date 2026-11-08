#!/usr/bin/env python3
"""Compare two full-answer JSONL files: the A/B workbench verb.

    tools/ab/diff.py REF ANSWERS [--json]

Exit codes: 0 = same queries, same answers; 1 = a disagreeing or missing key;
2 = an unreadable line.  This is the workbench side of the boundary in
``docs/SCOPE.md``: the comparison logic is in ``gisel.answers``, the command is
here because it exists to compare a reference implementation with ours.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gisel import answers as A  # noqa: E402


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
    result = A.compare(ref, ours)
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
