"""Command line for the gisel legalizer DSL."""

import argparse
import difflib
import json
import sys
from pathlib import Path

from . import ast as A, dsl, td
from .backend import check_json, core_json, llvm_inc, table

BACKENDS = ("td", "inc", "check", "table", "core")


def _table_prefix(source, explicit, gs=None):
    """-legalizer-table-prefix, defaulted from the source file name.

    tblgen's default is "X86", which is why the AArch64 lane has to pass
    -legalizer-table-prefix=AArch64.  Deriving it from `X86LegalizerInfo.gisel`
    removes that footgun; --prefix still overrides.
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
    # One gate for all five backends: a feature expression the file did not
    # declare cannot be spelled by any of them (`core` and `inc` used to be
    # the only two that noticed, and only at their own stage).
    bad = A.undeclared_features(gs)
    if bad:
        line, _ruleset, expr = bad[0]
        raise ValueError("line %d: undeclared feature expression %r; declare "
                         "it with `feature NAME = <expr>`" % (line, expr))
    # One table per opcode: a legalizer may build the same opcode twice (the
    # second chain only answers what the first did not), but a LegalizeRuleSet
    # record cannot express that, so the artifact is canonicalized first.
    gs = A.Program(gs.includes, gs.decls,
                   A.canonicalize_rulesets(gs.rulesets),
                   gs.features, gs.preds, gs.named_types, gs.selects,
                   gs.setlike)
    if emit == "td":
        return td.emit_td(gs, source)
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
    ap = argparse.ArgumentParser(prog="gisel", description=__doc__)
    ap.add_argument("--version", action="version", version="gisel 0.3.0")
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
    b.add_argument("--title")

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
    e.add_argument("--verbose", action="store_true")

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
        want_path = args.against or args.td
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
    if args.cmd == "bootstrap":
        argv = ["bootstrap", "--td", args.td, "--core", args.core,
                "--out", args.out]
        if args.title:
            argv += ["--title", args.title]
        return td.main(argv)
    from . import eval as evaluator
    # `eval` owns its own argument set; drop the subcommand word.
    return evaluator.main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
