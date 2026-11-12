#!/usr/bin/env python3
"""Check that every claim in docs/CLAIMS.md names something that exists.

The failure this prevents: a report cites `expected_counts.json`, the file
never existed, and no gate noticed.  This is a link check, not a proof that
the command passes; the `gate` column says where that is proven.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "docs" / "CLAIMS.md"
COLUMNS = ("claim", "command", "expected", "gate")
PATH = re.compile(r"(?<![\w/])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+)")


def rows(text):
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != len(COLUMNS):
            continue
        if cells == list(COLUMNS) or set(cells[0]) <= {"-", ":"}:
            continue
        yield dict(zip(COLUMNS, cells))


def main():
    if not CLAIMS.is_file():
        print("check-claims: %s is missing" % CLAIMS, file=sys.stderr)
        return 1
    claims = list(rows(CLAIMS.read_text()))
    if len(claims) < 10:
        print("check-claims: only %d claims; expected at least 10" % len(claims),
              file=sys.stderr)
        return 1
    problems = []
    for claim in claims:
        for column in ("claim", "command", "expected", "gate"):
            if not claim[column]:
                problems.append("%s: empty %s" % (claim["claim"], column))
        for token in PATH.findall(claim["command"]):
            if token.startswith(("http://", "https://")):
                continue
            if not (ROOT / token).exists():
                problems.append("%s: command cites missing %s"
                                % (claim["claim"], token))
    if problems:
        for problem in problems:
            print("check-claims: %s" % problem, file=sys.stderr)
        return 1
    print("check-claims: %d claims, every cited path exists" % len(claims))
    return 0


if __name__ == "__main__":
    sys.exit(main())
