#!/usr/bin/env python3
"""Answer a query file, surviving the queries that make the runner abort.

    tools/ab/run-queries.py RUNNER QUERIES OUT [--report FILE]

A query that trips an LLVM assertion kills the process, and a buffered tail
would be lost.  The runner flushes per answer, so we restart after the query
that aborted and mark it `unanswerable` in the output.  The answer file stays
parallel to the query file, which is what `tools/ab/diff.py` needs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(runner, queries, out, report=None):
    lines = [line for line in queries.read_text().splitlines() if line.strip()]
    answers, aborted = [], []
    start = 0
    while start < len(lines):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl",
                                         delete=False) as handle:
            handle.write("\n".join(lines[start:]) + "\n")
            chunk = handle.name
        proc = subprocess.run([str(runner), "--queries", chunk],
                              capture_output=True, text=True)
        Path(chunk).unlink()
        got = [line for line in proc.stdout.splitlines() if line.strip()]
        answers.extend(got)
        if proc.returncode == 0:
            break
        if proc.returncode not in (-6, -11, 134, 139):   # SIGABRT/SIGSEGV
            print("%s: exit %d on query %d:\n%s"
                  % (runner, proc.returncode, start + len(got) + 1,
                     proc.stderr.strip()), file=sys.stderr)
            return aborted
        bad = start + len(got)
        if bad >= len(lines):
            bad = start        # the runner died before answering anything
        aborted.append(bad)
        start = bad + 1

    rows = []
    for index, line in enumerate(lines):
        if index in set(aborted):
            record = json.loads(line)
            record["status"] = "unanswerable"
            record["reason"] = "asserted"
            rows.append(json.dumps(record))
        else:
            rows.append(answers.pop(0) if answers else line)
    out.write_text("\n".join(rows) + "\n")
    if report is not None:
        report.write_text(json.dumps(
            {"queries": len(lines), "answered": len(lines) - len(aborted),
             "unanswerable": len(aborted),
             "lines": [index + 1 for index in aborted]}, indent=1) + "\n")
    print("%s: %d queries, %d unanswerable"
          % (runner, len(lines), len(aborted)), file=sys.stderr)
    return aborted


def main(argv=None):
    parser = argparse.ArgumentParser(prog="run-queries")
    parser.add_argument("runner")
    parser.add_argument("queries")
    parser.add_argument("out")
    parser.add_argument("--report")
    args = parser.parse_args(argv)
    run(Path(args.runner), Path(args.queries), Path(args.out),
        Path(args.report) if args.report else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
