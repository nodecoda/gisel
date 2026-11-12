#!/usr/bin/env python3
"""Count rows, bad lines, duplicate keys and conflicting answers in JSONL.

This is a diagnostic tool, not part of the `gisel` command surface.  It exists
so the JSONL boundary can be audited before it becomes a codec: the policy in
`spec/cases-format.md` (same answer merges, a different answer is an error, a
bad line carries `file:line`) needs a measured population, not an assumption.

    python3 tools/jsonl-census.py FILE...

An answer row is a row with `action` or `status`; anything else is treated as
an answerless query and duplicates are compared by key only.  Exit 1 when any
bad line or conflicting duplicate is found, 0 otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gisel import answers as A  # noqa: E402


def classify(query):
    if "status" in query or "action" in query:
        return A.answer(query)
    return None


def census(path):
    result = {
        "file": str(path),
        "lines": 0,
        "blank": 0,
        "bad": 0,
        "duplicates": 0,
        "conflicts": 0,
        "unique_keys": 0,
        "bad_examples": [],
        "conflict_examples": [],
    }
    seen = {}
    with open(path) as stream:
        for lineno, line in enumerate(stream, 1):
            if not line.strip():
                result["blank"] += 1
                continue
            result["lines"] += 1
            try:
                query = json.loads(line)
                key = A.key(query)
                answer = classify(query)
            except Exception as exc:  # noqa: BLE001 - a census reports them all
                result["bad"] += 1
                if len(result["bad_examples"]) < 3:
                    result["bad_examples"].append("%d: %s" % (lineno, exc))
                continue
            if key in seen:
                result["duplicates"] += 1
                if seen[key] != answer:
                    result["conflicts"] += 1
                    if len(result["conflict_examples"]) < 3:
                        result["conflict_examples"].append(
                            "%d: %r vs %r" % (lineno, seen[key], answer))
            else:
                seen[key] = answer
    result["unique_keys"] = len(seen)
    return result


def main(argv):
    if not argv:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        print("usage: jsonl-census.py FILE...", file=sys.stderr)
        return 2
    totals = {"lines": 0, "bad": 0, "duplicates": 0, "conflicts": 0,
              "unique_keys": 0}
    failed = False
    for name in argv:
        result = census(name)
        print(json.dumps(result, sort_keys=True))
        for field in totals:
            totals[field] += result[field]
        failed = failed or bool(result["bad"] or result["conflicts"])
    print(json.dumps(dict(totals, files=len(argv)), sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
