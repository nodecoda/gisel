"""Read answer JSONL files.

An answer file pairs a query key with what a legalizer answered.  gisel reads
these files for `cases --queries`/`--oracle`; it does **not** compare two
implementations.  The full-set A/B comparison is a workbench concern and lives
with its command in ``tools/ab/diff.py`` — see ``docs/SCOPE.md``.
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
                # An answer file may repeat a query when a target builds the
                # same opcode twice.  An identical repeat is not an error; a
                # repeat with a different answer is, because then one of the
                # two rows would be silently dropped.
                if out[k] == a:
                    continue
                print("%s:%d: conflicting duplicate key %r" % (path, lineno, k),
                      file=sys.stderr)
                errors += 1
                continue
            out[k] = a
    return out, errors


