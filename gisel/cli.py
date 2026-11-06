"""Command line for the gisel legalizer DSL."""

import argparse
import difflib
import sys
from pathlib import Path

from . import td
from .backend import check_json, core_json, llvm_inc, table

BACKENDS = ("td", "inc", "check", "table", "core")


def _table_prefix(source, explicit):
    """-legalizer-table-prefix, defaulted from the source file name.

    tblgen's default is "X86", which is why the AArch64 lane has to pass
    -legalizer-table-prefix=AArch64.  Deriving it from `X86LegalizerInfo.gisel`
    removes that footgun; --prefix still overrides.
    """
    if explicit:
        return explicit
    stem = Path(source).stem
    return stem[:-len("LegalizerInfo")] if stem.endswith("LegalizerInfo") else stem


def _read_text(path):
    try:
        return Path(path).read_text()
    except OSError as e:
        print(f"{path}: {e.strerror}", file=sys.stderr)
        return None


def _source_error(source, exc):
    """`path:line: message`, the shape every editor understands."""
    msg = str(exc)
    if msg.startswith("line "):
        msg = msg[len("line "):]
    print(f"{source}:{msg}", file=sys.stderr)
    return 2


def _generate(gs, source, emit, prefix=None):
    if emit == "td":
        return td.emit_td(gs, source)
    if emit == "inc":
        return llvm_inc.emit_inc(gs, source)
    if emit == "check":
        return check_json.emit_check(gs)
    if emit == "table":
        return table.emit_table(gs, _table_prefix(source, prefix))
    if emit == "core":
        return core_json.emit_core(gs, source, Path(source).read_text())
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
    g.add_argument("--prefix", help="table prefix (default: from the file name)")

    c = sub.add_parser("check", help="verify a generated artifact is up to date")
    c.add_argument("source")
    c.add_argument("--emit", default="td", choices=BACKENDS)
    c.add_argument("--against", help="artifact to compare against")
    c.add_argument("--td", help="compatibility alias for --against")
    c.add_argument("--strict-origin", action="store_true",
                   help="core: also compare the per-rule origin line numbers")

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
        source_text = _read_text(args.source)
        if source_text is None:
            return 2
        try:
            gs = td.parse_gisel(source_text)
            text = _generate(gs, args.source, args.emit, getattr(args, "prefix", None))
        except ValueError as e:
            return _source_error(args.source, e)
        try:
            Path(args.out).write_text(text)
        except OSError as e:
            print(f"{args.out}: {e.strerror}", file=sys.stderr)
            return 2
        print(f"{args.out}: {len(gs['rulesets'])} rule sets, "
              f"{sum(len(r['rules']) for r in gs['rulesets'])} rules")
        return 0
    if args.cmd == "check":
        want_path = args.against or args.td
        if not want_path:
            c.error("check needs --against <artifact>")
        source_text = _read_text(args.source)
        if source_text is None:
            return 2
        try:
            gs = td.parse_gisel(source_text)
            got = _generate(gs, args.source, args.emit)
        except ValueError as e:
            return _source_error(args.source, e)
        want = _read_text(want_path)
        if want is None:
            return 2
        if args.emit == "core" and not args.strict_origin:
            got = core_json.strip_origin(got)
            want = core_json.strip_origin(want)
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
    # `eval` owns its own argument set; drop the subcommand word.
    return evaluator.main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
