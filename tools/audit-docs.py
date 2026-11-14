#!/usr/bin/env python3
"""Find documentation that can no longer be true.

The gate tests cover the claims we know how to replay (see
`tests/test_docs_snippets.py`, `tests/test_docs_transcripts.py`).  This tool is
the discovery pass for the rest: it walks every markdown file, separates prose
from code, and reports three kinds of finding.

  error   mechanically wrong now: a prose link that does not resolve, a shell
          line naming a verb that does not exist, the two landing pages
          disagreeing on their shape.
  warn    a value that will rot: a literal version in an instruction, a test
          count, a sha256 that matches no file in the tree.  Some of these are
          legitimate history; the point is that each one is a decision.
  info    transcripts and snapshots, with the command that regenerates them
          when the doc names one.

Exit codes: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ORIGIN = Path(__file__).resolve().parents[1]
ROOT = ORIGIN
SKIP = {".git", "build", ".omx", "__pycache__", "node_modules"}

FENCE = re.compile(r"```([A-Za-z0-9_+.-]*)\n(.*?)```", re.S)
SPAN = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^(#{1,6}) ", re.M)
COMMAND = re.compile(r"^(?:\$ )?(?:python3 -m |\./)?gisel\s+([a-z][a-z-]*)", re.M)
EMIT = re.compile(r"--emit=(?:\{([^}]*)\}|([\w-]+))")
HISTORICAL = re.compile(r"<!--\s*audit:\s*historical\s*-->\n+```")
VERSION = re.compile(r"\b\d+\.\d+\.\d+\b")
TESTS = re.compile(r"\b(?:Ran \d+ tests|\d+ passed)\b")
DIGEST = re.compile(r"\b[0-9a-f]{64}\b")


def markdown():
    for path in sorted(ROOT.rglob("*.md")):
        if SKIP & set(path.relative_to(ROOT).parts):
            continue
        yield path


def fences(text):
    return [(info, block) for info, block in FENCE.findall(text)]


def prose(text):
    return SPAN.sub("", FENCE.sub("", text))


def live_fences(text):
    """Fences minus the ones a `<!-- audit: historical -->` marker silences."""
    silenced = [match.end() - 4 for match in HISTORICAL.finditer(text)]
    out = []
    for match in FENCE.finditer(text):
        if any(abs(match.start() - start) <= 4 for start in silenced):
            continue
        out.append((match.group(1), match.group(2), match.start()))
    return out


def line_of(text, offset):
    return text[:offset].count("\n") + 1


def file_digests():
    digests = set()
    for path in ROOT.rglob("*"):
        if not path.is_file() or SKIP & set(path.relative_to(ROOT).parts):
            continue
        if path.stat().st_size > 4_000_000:
            continue
        try:
            digests.add(hashlib.sha256(path.read_bytes()).hexdigest())
        except OSError:
            pass
    return digests


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as findings too")
    ap.add_argument("--root", default=str(ORIGIN),
                    help="tree to audit (default: this checkout)")
    args = ap.parse_args(argv)
    global ROOT
    ROOT = Path(args.root).resolve()

    errors, warns, infos = [], [], []
    pages = {}

    from_digests = file_digests()
    try:
        sys.path.insert(0, str(ORIGIN))
        from gisel.cli import BACKENDS, COMMANDS
    except ImportError:
        print("audit-docs: cannot import gisel.cli; run from the checkout",
              file=sys.stderr)
        return 2

    for path in markdown():
        rel = str(path.relative_to(ROOT))
        text = path.read_text(errors="replace")
        pages[rel] = text
        for match in LINK.finditer(prose(text)):
            target = match.group(1).split("#")[0]
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if not (path.parent / target).resolve().exists():
                errors.append((rel, line_of(text, match.start()), "broken link", match.group(1)))
        for info, block, offset in live_fences(text):
            if info not in ("sh", "bash", "console", ""):
                continue
            for match in COMMAND.finditer(block):
                if match.group(1) not in COMMANDS:
                    errors.append((rel, line_of(text, offset + match.start()),
                                   "unknown verb", match.group(1)))
            for match in EMIT.finditer(block):
                values = (match.group(1) or match.group(2)).replace(" ", "").split(",")
                for value in values:
                    if value and value not in BACKENDS:
                        errors.append((rel, line_of(text, offset + match.start()),
                                       "unknown --emit value", value))
            for match in TESTS.finditer(block):
                warns.append((rel, line_of(text, offset + match.start()),
                              "volatile count", match.group(0)))
            for match in VERSION.finditer(block):
                warns.append((rel, line_of(text, offset + match.start()),
                              "literal version", match.group(0)))
            if "sha256" in block:
                infos.append((rel, line_of(text, offset),
                              "transcript carries a fingerprint", ""))
        for match in DIGEST.finditer(text):
            if match.group(0) not in from_digests:
                warns.append((rel, line_of(text, match.start()),
                              "sha256 of no file in the tree", match.group(0)[:12] + "…"))

    english, chinese = pages.get("README.md"), pages.get("README.zh.md")
    if english is not None and chinese is not None:
        if ([len(x) for x in HEADING.findall(english)]
                != [len(x) for x in HEADING.findall(chinese)]):
            errors.append(("README.zh.md", 1, "heading skeleton differs from README.md", ""))
        if ([i for i, _ in fences(english)] != [i for i, _ in fences(chinese)]):
            errors.append(("README.zh.md", 1, "code-block shape differs from README.md", ""))

    report = {
        "errors": [dict(zip(("path", "line", "kind", "detail"), row)) for row in errors],
        "warnings": [dict(zip(("path", "line", "kind", "detail"), row)) for row in warns],
        "info": [dict(zip(("path", "line", "kind", "detail"), row)) for row in infos],
    }
    if args.json:
        import json
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for label, rows in (("error", errors), ("warn", warns), ("info", infos)):
            for path, line, kind, detail in rows:
                print("%-5s %s:%d  %s %s" % (label, path, line, kind, detail))
        print("audit-docs: %d error(s), %d warning(s)" % (len(errors), len(warns)))
    return 1 if errors or (args.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
