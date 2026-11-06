"""Command line for the gisel legalizer DSL."""

import argparse
import difflib
import sys
from pathlib import Path

from . import td
from .backend import check_json, llvm_inc

BACKENDS = ("td", "inc", "check")


def _generate(gs, source, emit):
    if emit == "td":
        return td.emit_td(gs, source)
    if emit == "inc":
        return llvm_inc.emit_inc(gs, source)
    if emit == "check":
        return check_json.emit_check(gs)
    raise ValueError(f"unknown backend {emit!r}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="gisel", description=__doc__)
    ap.add_argument("--version", action="version", version="gisel 0.1.0")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="generate a backend artifact")
    g.add_argument("source")
    g.add_argument("--emit", default="td", choices=BACKENDS,
                   help="backend: td, inc (-gen-legalizer), check (-gen-legalizer-check)")
    g.add_argument("--out", required=True)

    c = sub.add_parser("check", help="verify a generated artifact is up to date")
    c.add_argument("source")
    c.add_argument("--emit", default="td", choices=BACKENDS)
    c.add_argument("--against", help="artifact to compare against")
    c.add_argument("--td", help="compatibility alias for --against")

    b = sub.add_parser("bootstrap", help="build a .gisel from a hand-written .td")
    b.add_argument("--td", required=True)
    b.add_argument("--core", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--title", default="Target")

    e = sub.add_parser("eval", help="evaluate the normal form without LLVM")
    e.add_argument("--doc", required=True)
    e.add_argument("--features", required=True)
    e.add_argument("--cases", required=True)
    e.add_argument("--verbose", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd == "gen":
        gs = td.parse_gisel(Path(args.source).read_text())
        text = _generate(gs, args.source, args.emit)
        Path(args.out).write_text(text)
        print(f"{args.out}: {len(gs['rulesets'])} rule sets, "
              f"{sum(len(r['rules']) for r in gs['rulesets'])} rules")
        return 0
    if args.cmd == "check":
        want_path = args.against or args.td
        if not want_path:
            c.error("check needs --against <artifact>")
        gs = td.parse_gisel(Path(args.source).read_text())
        got = _generate(gs, args.source, args.emit)
        want = Path(want_path).read_text()
        if got == want:
            print(f"{want_path}: up to date")
            return 0
        sys.stderr.writelines(difflib.unified_diff(
            want.splitlines(True), got.splitlines(True), want_path, "<generated>"))
        print(f"{want_path}: STALE (re-run `gisel gen --emit={args.emit}`)",
              file=sys.stderr)
        return 1
    if args.cmd == "bootstrap":
        return td.main(["bootstrap", "--td", args.td, "--core", args.core,
                        "--out", args.out, "--title", args.title])
    from . import eval as evaluator
    return evaluator.main()


if __name__ == "__main__":
    sys.exit(main())
