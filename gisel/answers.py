"""Read and compare answer JSONL files.

An answer file pairs a query key with what a legalizer answered.  This module
is the reader and the comparison; the command that prints the report is a
workbench tool (``tools/ab/diff.py``), see ``docs/SCOPE.md``.

Unlike ``gisel cases --against``, :func:`compare` is not an intersection
report: a key present on one side and absent on the other is a failure.  The
contract is "same queries, same answers".
"""

from __future__ import annotations

import json
import sys

from . import eval as E


def key(q):
    mem = None
    if q.get("mem"):
        m = q["mem"]
        mem = (E.parse_case_llt(m[0]), int(m[1]))
        mem += (m[2], m[3]) if len(m) >= 4 else ("NotAtomic", "NotAtomic")
    return (q["config"], q["name"],
            tuple(E.parse_case_llt(t) for t in q.get("types", [])),
            mem, tuple(q.get("imms") or []))


def answer(q):
    if q.get("status") == "unanswerable":
        return ("unanswerable", q.get("reason", ""))
    new = q.get("new_type")
    return ("answered", q["action"], int(q.get("type_idx", 0)),
            E.parse_case_llt(new) if isinstance(new, str) else ("invalid",))


def load(path):
    out = {}
    errors = 0
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                q = json.loads(line)
                k = key(q)
                a = answer(q)
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
