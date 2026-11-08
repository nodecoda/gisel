"""Command line for the gisel legalizer DSL."""

import argparse
import difflib
import json
import sys
from pathlib import Path

from . import ast as A, dsl
from . import cases as casegen
from . import diff as diffgen
from . import domain as domaingen
from .backend import check_json, core_json, llvm_inc, table

BACKENDS = ("inc", "check", "table", "core")


def _table_prefix(source, explicit, gs=None):
    """The table backend's prefix, defaulted from the source file name.

    Deriving it from `X86LegalizerInfo.gisel` keeps the generated C++ table
    self-contained; ``--prefix`` still overrides.
    """
    if explicit:
        return explicit
    if gs is not None:
        for rs in gs.rulesets:
            if "_" in rs.name:
                return rs.name.split("_", 1)[0]
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
    # One gate for all four backends: a feature expression the file did not
    # declare cannot be spelled by any of them (`core` and `inc` used to be
    # the only two that noticed, and only at their own stage).
    bad = A.undeclared_features(gs)
    if bad:
        line, _ruleset, expr = bad[0]
        raise ValueError("line %d: undeclared feature expression %r; declare "
                         "it with `feature NAME = <expr>`" % (line, expr))
    # One table per opcode: a legalizer may build the same opcode twice (the
    # second chain only answers what the first did not).  The emitted C++
    # chain and frozen core JSON carry one table per opcode, so the artifact
    # is canonicalized first.
    gs = A.Program(gs.decls,
                   A.canonicalize_rulesets(gs.rulesets),
                   gs.features, gs.preds, gs.named_types, gs.selects,
                   gs.setlike)
    if emit == "inc":
        return llvm_inc.emit_inc(gs, source)
    if emit == "check":
        return check_json.emit_check(gs)
    if emit == "table":
        return table.emit_table(gs, _table_prefix(source, prefix, gs))
    if emit == "core":
        return core_json.emit_core(gs, source, Path(source).read_text())
    raise ValueError(f"unknown backend {emit!r}")


def _load_manifest(path):
    """Bundled table by default; an explicit file may be bare or wrapped."""
    if not path:
        return dsl.load_arity_manifest()
    raw = json.loads(Path(path).read_text())
    return raw["opcodes"] if "opcodes" in raw else raw


def _has_slot(node):
    if isinstance(node, A.Rule):
        return any(_has_slot(v) for v in (node.on, node.to, node.predicate))
    if isinstance(node, dict):
        if node.get("kind") == "slot":
            return True
        return any(_has_slot(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(_has_slot(v) for v in node)
    return False


def _lint(gs, source, manifest):
    """J1/J2b/J3a/J3b over every rule, with `.gisel` line numbers."""
    errors, warnings = [], []
    nrules = 0
    # Every type a rule can name is declared above it: `type`, `select` and
    # `type_set`.  Passing the set through is what turns "unknown type name"
    # from a KeyError in the core backend into a diagnostic on the right line.
    names = {d.name for d in gs.decls
             if isinstance(d, (A.NamedType, A.SelectType, A.TypeSet))}
    for rs in gs.rulesets:
        opcodes = rs.opcodes
        rs_name = rs.name
        rules = rs.rules
        arities = [manifest.get(o) for o in opcodes]
        known = [a for a in arities if a is not None]
        arity = min(known) if known else None
        unknown = [o for o, a in zip(opcodes, arities) if a is None]
        first_slot_line = None
        for rule in rules:
            nrules += 1
            line = rule.line
            errs = []
            try:
                dsl.check_rule(rule, arity if arity is not None else 10 ** 9,
                               errs, names)
            except (KeyError, IndexError, TypeError, ValueError) as e:
                errs.append(f"malformed rule: {e}")
            for msg in errs:
                errors.append({"file": source, "line": line,
                               "ruleset": rs_name, "rule": rule["op"],
                               "message": msg})
            if unknown and first_slot_line is None and _has_slot(rule):
                first_slot_line = line
        if first_slot_line is not None:
            warnings.append({"file": source, "line": first_slot_line,
                             "ruleset": rs_name,
                             "message": "arity unknown for %s; slot bounds not checked"
                                        % ", ".join(unknown)})
    for line, ruleset, expr in A.undeclared_features(gs):
        errors.append({"file": source, "line": line, "ruleset": ruleset,
                       "rule": "-",
                       "message": "undeclared feature expression %r; declare "
                                  "it with `feature NAME = <expr>`" % expr})
    return errors, warnings, nrules


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(
        prog="gisel", description=__doc__,
        epilog="gisel does two things: turn a .gisel file into rule artifacts "
               "(gen/check/lint) and generate test cases (cases/domain).  "
               "eval answers queries for the case generator; graph analyses "
               "the normal form.  diff is the one workbench verb here: it "
               "compares answer files produced elsewhere.  Everything that "
               "reads LLVM sources, runs llvm-tblgen or compiles LLVM lives "
               "under tools/ and is not part of gisel.  See docs/SCOPE.md.")
    ap.add_argument("--version", action="version", version="gisel 0.3.0")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="generate a backend artifact")
    g.add_argument("source")
    g.add_argument("--emit", default="inc", choices=BACKENDS,
                   help="backend: inc (-gen-legalizer), check (-gen-legalizer-check), "
                        "table (-gen-legalizer-table), core (-gen-legalizer-core)")
    g.add_argument("--out", required=True)
    g.add_argument("--prefix", help="table prefix (default: from the file name)")

    c = sub.add_parser("check", help="verify a generated artifact is up to date")
    c.add_argument("source")
    c.add_argument("--emit", default="inc", choices=BACKENDS)
    c.add_argument("--against", help="artifact to compare against")
    c.add_argument("--strict-origin", action="store_true",
                   help="core: also compare the per-rule origin line numbers")

    cs = sub.add_parser("cases",
                        help="generate equivalence/boundary/outside test cases")
    cs.add_argument("source")
    cs.add_argument("--out", required=True, help="JSONL case file to write")
    cs.add_argument("--features",
                    help="feature truth table (default: derive none/all/only-N)")
    cs.add_argument("--config", action="append", dest="configs",
                    help="limit to configs from --features (repeatable)")
    cs.add_argument("--against",
                    help="oracle JSONL; compares only the overlapping queries")
    cs.add_argument("--queries",
                    help="complete answerless query JSONL to compress")
    cs.add_argument("--oracle",
                    help="complete answers JSONL for --queries")
    cs.add_argument("--max-outside", type=int, default=None)
    cs.add_argument("--axes", help="axis profile JSON (analysis only)")
    cs.add_argument("--json", action="store_true", help="print stats as JSON")

    d = sub.add_parser("domain",
                       help="enumerate the answerless query domain (D*)")
    d.add_argument("source")
    d.add_argument("--out", required=True, help="JSONL query file to write")
    d.add_argument("--features",
                   help="feature truth table (default: derive none/all/only-N)")
    d.add_argument("--config", action="append", dest="configs",
                   help="limit to configs from --features (repeatable)")
    d.add_argument("--pointer-width", type=int, default=64,
                   help="subtarget pointer width (default 64)")
    d.add_argument("--slots", help="opcode slot table (default: bundled)")
    d.add_argument("--axes", help="axis profile JSON (analysis only)")
    d.add_argument("--json", action="store_true", help="print stats as JSON")

    df = sub.add_parser("diff",
                        help="workbench: compare two full-answer JSONL files")
    df.add_argument("ref")
    df.add_argument("ours")
    df.add_argument("--json", action="store_true", help="print the report as JSON")

    l = sub.add_parser("lint", help="static checks over a source file (no LLVM)")
    l.add_argument("source")
    l.add_argument("--manifest",
                   help="opcode arity JSON (default: the bundled table)")
    l.add_argument("--json", action="store_true", help="machine-readable diagnostics")
    l.add_argument("--max-errors", type=int, default=50,
                   help="print at most N errors (exit code is unaffected)")

    e = sub.add_parser("eval", help="evaluate the normal form without LLVM")
    e.add_argument("--doc", required=True)
    e.add_argument("--features", required=True)
    e.add_argument("--cases", required=True)
    e.add_argument("--answers", metavar="OUT")
    e.add_argument("--verbose", action="store_true")

    gr = sub.add_parser("graph", help="find cycles in the legalizer quotient graph")
    gr.add_argument("source")
    gr.add_argument("--emit", default="core", choices=("core",),
                    help="graph input normal form (only core is supported)")
    gr.add_argument("--features")
    gr.add_argument("--config", action="append", dest="configs")
    gr.add_argument("--pointer-width", type=int, default=64)
    gr.add_argument("--axes", help="axis profile JSON (analysis only)")
    gr.add_argument("--oracle", help="check matching points in an oracle JSONL")
    gr.add_argument("--inject-edge", action="store_true")
    gr.add_argument("--check-closure", action="store_true")
    gr.add_argument("--progress", action="store_true")
    gr.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd == "gen":
        source_text = _read_text(args.source)
        if source_text is None:
            return 2
        try:
            gs = A.parse_program(source_text)
            text = _generate(gs, args.source, args.emit, getattr(args, "prefix", None))
        except ValueError as e:
            return _source_error(args.source, e)
        try:
            Path(args.out).write_text(text)
        except OSError as e:
            print(f"{args.out}: {e.strerror}", file=sys.stderr)
            return 2
        print(f"{args.out}: {len(gs.rulesets)} rule sets, "
              f"{sum(len(r.rules) for r in gs.rulesets)} rules")
        return 0
    if args.cmd == "check":
        want_path = args.against
        if not want_path:
            c.error("check needs --against <artifact>")
        source_text = _read_text(args.source)
        if source_text is None:
            return 2
        try:
            gs = A.parse_program(source_text)
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
    if args.cmd == "lint":
        text = _read_text(args.source)
        if text is None:
            return 2
        try:
            gs = A.parse_program(text)
        except ValueError as e:
            return _source_error(args.source, e)
        try:
            manifest = _load_manifest(args.manifest)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
            print(f"{args.manifest}: {e}", file=sys.stderr)
            return 2
        errors, warnings, nrules = _lint(gs, args.source, manifest)
        if args.json:
            print(json.dumps({"source": args.source,
                              "errors": errors, "warnings": warnings,
                              "rules": nrules}, indent=1))
        else:
            for e in errors[:args.max_errors]:
                print(f"{e['file']}:{e['line']}: {e['ruleset']}: "
                      f"{e['message']}", file=sys.stderr)
            if len(errors) > args.max_errors:
                print(f"... {len(errors) - args.max_errors} more error(s)",
                      file=sys.stderr)
            for w in warnings:
                print(f"{w['file']}:{w['line']}: warning: {w['message']}",
                      file=sys.stderr)
            print(f"{args.source}: {len(errors)} error(s), {len(warnings)} "
                  f"warning(s), {nrules} rule(s)")
        return 1 if errors else 0
    if args.cmd == "domain":
        return domaingen.main(argv[1:])
    if args.cmd == "diff":
        return diffgen.main(argv[1:])
    if args.cmd == "cases":
        return casegen.main(argv[1:])
    if args.cmd == "graph":
        from . import graph
        return graph.main(argv[1:])
    from . import eval as evaluator
    # `eval` owns its own argument set; drop the subcommand word.
    return evaluator.main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
