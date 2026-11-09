#!/usr/bin/env python3
"""Compare two full-answer JSONL files: the A/B workbench verb.

    tools/ab/diff.py REF ANSWERS [--json] [--compare action|full]

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
from gisel import cases as C  # noqa: E402
from gisel import eval as E  # noqa: E402


def _key_fields(key):
    config, name, types, mem, imms = key
    fields = {
        "config": config,
        "name": name,
        "types": [C.llt_text(t) for t in types],
        "mem": None,
        "imms": list(imms),
    }
    if mem is not None:
        fields["mem"] = [C.llt_text(mem[0]), mem[1], mem[2], mem[3]]
    return fields


def _classify(a, b):
    """Why two answers differ, coarsest first."""
    if a[0] != b[0]:
        return "status"
    if a[1] != b[1]:
        return "action"
    if a[2] != b[2]:
        return "type_idx"
    return "new_type"


def compare(ref, ours, mode="full", details_limit=100,
            allow_ref_asserts=None):
    """Full-set comparison: a key on one side only is a failure.

    ``mode="action"`` is the coarse smoke gate: it compares only the action
    name and deliberately ignores ``type_idx``/``new_type``.  ``mode="full"``
    is the acceptance comparison.  Unlike ``gisel cases --against``, which
    reports the overlap, this is the workbench contract "same queries, same
    answers".
    """
    if mode not in ("action", "full"):
        raise ValueError("unknown compare mode %r" % (mode,))
    keys = sorted(set(ref) | set(ours), key=repr)
    matched = [k for k in keys if k in ref and k in ours]
    agree = 0
    unanswerable = 0
    disagree = []
    ref_asserted = []
    for k in matched:
        a, b = ref[k], ours[k]
        if (allow_ref_asserts is not None and a[0] == "unanswerable"
                and a[1] == "asserted" and b[0] == "answered"):
            # The reference asserted before answering and ours answered.  Only
            # counted as a known class when the caller pins how many to expect:
            # an unpinned assert is a difference, not a footnote.
            ref_asserted.append((k, a, b))
            continue
        same_unanswerable = (a[0] == b[0] == "unanswerable"
                             and a[1] == b[1])
        if mode == "action":
            same_answer = a[0] == b[0] == "answered" and a[1] == b[1]
        else:
            same_answer = (a[0] == b[0] == "answered"
                           and a[1] == b[1] and a[2] == b[2]
                           and E.values_equal(a[3], b[3]))
        if same_unanswerable or same_answer:
            agree += 1
            unanswerable += int(same_unanswerable)
        else:
            disagree.append((k, a, b))
    details = [
        {"key": repr(k), "key_fields": _key_fields(k),
         "class": _classify(a, b),
         "ref": list(a), "ours": list(b)}
        for k, a, b in disagree[:details_limit]
    ]
    return {
        "mode": mode,
        "ref": len(ref),
        "ours": len(ours),
        "matched": len(matched),
        "agree": agree,
        "unanswerable": unanswerable,
        "disagree": len(disagree),
        "ref_asserted": len(ref_asserted),
        "ref_asserted_keys": [repr(k) for k, _, _ in ref_asserted[:20]],
        "missing_ref": len(set(ours) - set(ref)),
        "missing_ours": len(set(ref) - set(ours)),
        "first": disagree[:20],
        "first_details": details,
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
    ap.add_argument("--compare", choices=("action", "full"), default="full",
                    help="action: coarse smoke gate; full: acceptance")
    ap.add_argument("--details", type=int, default=100,
                    help="maximum first_details entries (default 100)")
    ap.add_argument("--allow-ref-asserts", type=int, default=None,
                    metavar="N",
                    help="count the queries whose reference answer is "
                         "'asserted' as a known class, not a difference; the "
                         "run fails unless exactly N of them are found")
    ap.add_argument("--expect-unanswerable", type=int, default=None,
                    metavar="N",
                    help="fail unless exactly N queries are unanswerable on "
                         "both sides; pins a shared assert so a new class of "
                         "assert cannot hide in the unanswerable count")
    args = ap.parse_args(argv)

    ref, e1 = A.load(args.ref)
    ours, e2 = A.load(args.ours)
    result = compare(ref, ours, args.compare, args.details,
                     args.allow_ref_asserts)
    result["errors"] = e1 + e2
    if args.json:
        print(json.dumps(result, indent=1, sort_keys=True))
    else:
        print("mode=%s ref=%d ours=%d matched=%d agree=%d unanswerable=%d "
              "disagree=%d missing_ref=%d missing_ours=%d errors=%d"
              % (result["mode"], result["ref"], result["ours"],
                 result["matched"], result["agree"], result["unanswerable"],
                 result["disagree"], result["missing_ref"],
                 result["missing_ours"], result["errors"]))
        for key, a, b in result["first"]:
            print("MISMATCH %r: ref=%r ours=%r" % (key, a, b))
        for key in result["missing_ref_keys"][:5]:
            print("MISSING in ref: %r" % (key,))
        for key in result["missing_ours_keys"][:5]:
            print("MISSING in ours: %r" % (key,))
    if result["errors"]:
        return 2
    if (args.expect_unanswerable is not None
            and result["unanswerable"] != args.expect_unanswerable):
        print("both sides unanswerable on %d queries, expected %d"
              % (result["unanswerable"], args.expect_unanswerable))
        return 1
    if (args.allow_ref_asserts is not None
            and result["ref_asserted"] != args.allow_ref_asserts):
        print("ref asserted on %d queries, expected %d"
              % (result["ref_asserted"], args.allow_ref_asserts))
        return 1
    if (result["missing_ref"] or result["missing_ours"]
            or result["disagree"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
