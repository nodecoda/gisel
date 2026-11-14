"""`gisel demo`: the whole product in one command, on a bundled corpus.

The first thing a reader does after `pip install gisel` should not be five
copy-pasted commands with three file paths to fill in by hand.  `demo` runs
the same code paths the verbs run -- lint, `gen --emit=inc`, `cases`, and a
graph on one feature configuration -- writes the artifacts into one directory,
and prints what it wrote and what to try next.  It reads only the bundled
corpus, so it works from a wheel with no checkout and no LLVM.

Exit codes follow `spec/cli.md`: 0 every stage answered, 1 a stage answered
"no" (lint errors, a stale/missing artifact, a graph cycle), 2 usage or a
broken corpus.  A stage that fails stops the demo: continuing would print
artifacts downstream of a broken input.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import cli
from . import corpus as corpora

DEFAULT_CORPUS = "x86"
DEFAULT_OUT = "gisel-demo"


def _first_config(features_path: Path | None) -> str | None:
    """The graph needs one configuration; take the first the table lists.

    Running all of them is the honest survey but costs minutes on x86.  The
    demo prints the configuration it used, so the reader can ask for the rest
    with `gisel graph --corpus NAME --config ...`.
    """
    if features_path is None:
        return None
    try:
        table = json.loads(features_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(table, dict):
        return None
    configs = [name for name, row in table.items() if isinstance(row, dict)]
    return configs[0] if configs else None


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="gisel demo",
        description="run lint, gen, cases and graph once, without LLVM")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS, metavar="NAME",
                    help="bundled corpus (default: %s)" % DEFAULT_CORPUS)
    ap.add_argument("--out", default=DEFAULT_OUT, metavar="DIR",
                    help="directory for the demo artifacts (default: %s)"
                         % DEFAULT_OUT)
    ap.add_argument("--config", metavar="NAME",
                    help="graph configuration (default: the first in the "
                         "corpus feature table)")
    args = ap.parse_args(argv)

    try:
        bundle = corpora.get(args.corpus)
    except corpora.CorpusError as exc:
        print("gisel demo: %s" % exc, file=sys.stderr)
        return 2

    out = Path(args.out).expanduser()
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print("gisel demo: %s: %s" % (out, exc), file=sys.stderr)
        return 2
    out = out.resolve()
    config = args.config or _first_config(bundle.features)

    inc = out / ("%s.inc" % args.corpus)
    cases = out / ("%s.cases.jsonl" % args.corpus)
    stages = [
        ("lint", ["lint", "--corpus", args.corpus]),
        ("generate the C++ chain",
         ["gen", "--corpus", args.corpus, "--emit", "inc", "--out", str(inc)]),
        ("generate the questions",
         ["cases", "--corpus", args.corpus, "--out", str(cases)]),
        ("build the quotient graph",
         ["graph", "--corpus", args.corpus, "--refine"]
         + (["--config", config] if config else [])),
    ]

    started = time.monotonic()
    print("gisel demo: %s, %d stages, no LLVM" % (args.corpus, len(stages)))
    print("artifacts: %s" % out)
    for number, (title, argv_stage) in enumerate(stages, 1):
        print()
        print("[%d/%d] %s" % (number, len(stages), title))
        print("$ gisel %s" % " ".join(argv_stage))
        if argv_stage[0] == "graph":
            # The default partition answers "is the quotient a function?"
            # with "not yet" on X86 (272 violations); the refined partition
            # splits exactly those classes, so the demo asks for it and says
            # so.  `spec/graph.md` keeps `--refine` off by default because it
            # changes the atom definition; a demo that names the flag is not
            # making it the default.
            print("# --refine: split classes until the successor is a "
                  "function (default partition is coarser)")
        rc = cli.main(argv_stage)
        if rc:
            if argv_stage[0] == "graph" and rc == 1:
                print("demo: the graph said no (rc=1) -- a cycle or an "
                      "unclosed partition, which is an analysis finding, "
                      "not a broken install; read the report above",
                      file=sys.stderr)
            else:
                print("demo: stage %d failed with rc=%d; stopping"
                      % (number, rc), file=sys.stderr)
            return rc

    elapsed = time.monotonic() - started
    print()
    print("demo: ok (%.1f s)" % elapsed)
    print("wrote:")
    print("  %s" % inc)
    print("  %s" % cases)
    print("next:")
    print("  gisel graph --corpus %s --json > graph.json%s"
          % (args.corpus,
             "" if not config else "   # one config; drop --config for all"))
    print("  gisel domain --corpus %s --out domain.jsonl" % args.corpus)
    print("  gisel check --corpus %s --emit=inc --against %s"
          % (args.corpus, inc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
