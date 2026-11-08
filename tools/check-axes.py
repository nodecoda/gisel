#!/usr/bin/env python3
"""Fail when an axis profile stops sampling values the rules actually use.

    tools/check-axes.py SOURCE --axes FILE [--features FILE] [--json] [--strict]

The check is about *coverage*, not about the analysis result:

* every type spelling the rules name must be resolvable by the profile
  (unknown names and configuration-selected ``select`` names are gaps);
* ``types: derive`` -- a spelling that ``types.remove`` drops is a gap;
* ``types: explicit`` -- a spelling the profile does not list is *reported as
  information*, not as a gap: an explicit axis is a deliberate replacement, and
  the missing region shows up as ``outside``/``opaque`` in ``graph``.  Pass
  ``--strict`` to turn those into gaps;
* ``mems`` follows the same derive/explicit split for ``(mty, align)`` rows;
* an immediate literal (``imm(i) == N``, ``in(imm(i), [...])``) must stay in the
  sampled values for ``i``; a threshold ``N`` needs a sampled value below and
  above it, otherwise one branch of the comparison is never exercised;
* an ordering comparison needs a sampled ordering that satisfies it and, when
  the lattice has one, a sampled ordering that does not.

Wildcard pointer widths (``p0:*``) denote a family of concrete widths, so they
are checked for resolvability but never for presence in the axis.

Exit codes: 0 clean, 1 gaps, 2 usage or parse error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gisel import axes as axesmod
from gisel import cases as C
from gisel import eval as E

_ORDER_TAGS = dict(E._ORDERING_FROM_TAG)
_LATTICE = sorted(E._ORDERING_INDEX, key=E._ORDERING_INDEX.__getitem__)
_COMPARISONS = ("eq", "ne", "ge", "gt", "le", "lt")
_OP_TEXT = {"eq": "==", "ne": "!=", "lt": "<", "le": "<=",
            "gt": ">", "ge": ">="}
_AXIS_TEXT = {"memOrdering": "mem_ordering",
              "memFailureOrdering": "mem_failure_ordering"}


def _ordering_holds(value, op, tag):
    vi = E._ORDERING_INDEX[value]
    ti = E._ORDERING_INDEX[tag]
    if op == "eq":
        return vi == ti
    if op == "ne":
        return vi != ti
    if op == "ge":
        return E.is_at_least_or_stronger_than(vi, ti)
    if op == "gt":
        return E.is_stronger_than(vi, ti)
    if op == "le":
        return not E.is_stronger_than(vi, ti)
    if op == "lt":
        return not E.is_at_least_or_stronger_than(vi, ti)
    raise ValueError("unsupported ordering comparison %r" % (op,))


def _flip(kind):
    return {"lt": "gt", "gt": "lt", "le": "ge", "ge": "le"}.get(kind, kind)


def _walk(node, types, comparisons, imm_constraints, imm_literals):
    """Collect type spellings, ordering comparisons, immediate constraints."""
    if isinstance(node, list):
        for value in node:
            _walk(value, types, comparisons, imm_constraints, imm_literals)
        return
    if not isinstance(node, dict):
        return
    kind = node.get("kind")
    args = node.get("args") or []
    if kind == "type":
        for text in C.type_value_spellings(node.get("value")):
            types.add(text)
    elif kind in _COMPARISONS and len(args) == 2 \
            and isinstance(args[0], dict) and isinstance(args[1], dict):
        lhs, rhs = args
        if lhs.get("kind") in ("memOrdering", "memFailureOrdering"):
            tag = _ORDER_TAGS.get(rhs.get("kind"))
            if tag is not None:
                comparisons.add((lhs["kind"], kind, tag))
        for expr, other, op in ((lhs, rhs, kind), (rhs, lhs, _flip(kind))):
            if expr.get("kind") == "imm" and other.get("kind") == "int":
                imm_constraints.add((expr["index"], op, int(other["value"])))
    elif kind == "in" and len(args) == 2:
        lhs, rhs = args
        if lhs.get("kind") == "imm" and rhs.get("of") == "Int":
            for value in rhs.get("elems", []):
                if isinstance(value, int):
                    imm_literals.setdefault(lhs["index"], set()).add(value)
    for key, value in node.items():
        if key in ("args", "arg", "set", "elems"):
            _walk(value, types, comparisons, imm_constraints, imm_literals)


def collect(doc):
    """Type spellings, mem rows, immediate constraints, ordering comparisons."""
    types, comparisons = set(), set()
    imm_constraints, imm_literals = set(), {}
    mem_rows = []
    derived_imms = {}

    for rs in doc["rulesets"]:
        _nslots, infos = C.inspect_ruleset(rs)
        uses_mem = any(info.uses_mem for info in infos)
        for info in infos:
            for literals in info.literals.values():
                for value in literals:
                    types.add(C.llt_text(value))
            if not uses_mem:
                continue
            for row in C._mem_candidates([info]):
                mem_rows.append(tuple(row))
                for text in row[:3]:
                    if text:
                        types.add(str(text))
        for rule in rs["rules"]:
            for node in (rule.get("predicate"), rule.get("on"), rule.get("to")):
                _walk(node, types, comparisons, imm_constraints, imm_literals)
        for index, values in C.imm_candidates(infos).items():
            derived_imms.setdefault(index, set()).update(values)

    return {
        "types": types,
        "mem_rows": mem_rows,
        "imm_constraints": imm_constraints,
        "imm_literals": imm_literals,
        "derived_imms": derived_imms,
        "comparisons": comparisons,
    }


def _is_family(text):
    """Pointer widths spelled ``p0:*`` name a family, not one value."""
    return "*" in text or text == "LLT_invalid"


def check(source, profile, features=None):
    """Return ``(gaps, info)``; gaps are coverage failures, info is advisory."""
    doc = C.document(source)
    if features is None or isinstance(features, (str, Path)):
        features = C.derive_features(
            doc, str(features) if features else profile.configs_path)
    profile.bind(source, doc, features)
    profile.apply_features(features)

    found = collect(doc)
    gaps, info = [], []

    # -- types ------------------------------------------------------------
    explicit_types = profile.types_explicit()
    explicit_type_values = ({C.llt_text(t) for t in profile.apply_types([])}
                            if explicit_types else set())
    for text in sorted(found["types"]):
        try:
            resolved = profile.resolve_type(text)
        except axesmod.AxisError as exc:
            gaps.append("type %s: %s" % (text, exc))
            continue
        canonical = C.llt_text(resolved)
        if _is_family(canonical):
            continue
        if explicit_types:
            if canonical not in explicit_type_values:
                info.append("type %s is not in the explicit type axis"
                            % canonical)
            continue
        kept = {C.llt_text(t) for t in
                profile.apply_types([resolved], pointer_only=False)}
        if canonical not in kept:
            gaps.append("type %s is removed by types.remove" % canonical)

    # -- mem rows ---------------------------------------------------------
    explicit_mems = profile.mems_explicit()
    applied_mems = {(row[2], row[3]) for row in profile.apply_mems([])} \
        if explicit_mems else None
    for row in found["mem_rows"]:
        key = (C.llt_text(profile.resolve_type(row[2])), int(row[3]))
        if explicit_mems:
            if key not in applied_mems:
                info.append("mem row %s/%d is not in the explicit mem axis"
                            % key)
            continue
        kept = {(r[2], int(r[3])) for r in profile.apply_mems([row])}
        if key not in kept:
            gaps.append("mem row %s/%d is removed by mems.remove" % key)

    # -- immediates -------------------------------------------------------
    def sampled_imms(index):
        return set(profile.apply_imms(
            index, sorted(found["derived_imms"].get(index, ()))))

    for index in sorted(found["imm_literals"]):
        values = sampled_imms(index)
        for value in sorted(found["imm_literals"][index]):
            if value not in values:
                gaps.append("imm(%d) in [...] misses %d (sampled: %s)"
                            % (index, value, sorted(values)))
    for index, op, value in sorted(found["imm_constraints"]):
        values = sampled_imms(index)
        if op == "eq":
            if value not in values:
                gaps.append("imm(%d) == %d is never sampled (values: %s)"
                            % (index, value, sorted(values)))
        elif op == "ne":
            if not [v for v in values if v != value]:
                gaps.append("imm(%d) != %d is never true (values: %s)"
                            % (index, value, sorted(values)))
        else:
            holds = {"lt": lambda v: v < value, "le": lambda v: v <= value,
                     "gt": lambda v: v > value, "ge": lambda v: v >= value}[op]
            if not [v for v in values if holds(v)]:
                gaps.append("imm(%d) %s %d is never true (values: %s)"
                            % (index, _OP_TEXT[op], value, sorted(values)))
            if not [v for v in values if not holds(v)]:
                gaps.append("imm(%d) %s %d is never false (values: %s)"
                            % (index, _OP_TEXT[op], value, sorted(values)))

    # -- orderings --------------------------------------------------------
    sampled_orderings = sorted({o for o, _f in profile.ordering_pairs()})
    for axis, op, tag in sorted(found["comparisons"]):
        holds = [o for o in _LATTICE if _ordering_holds(o, op, tag)]
        fails = [o for o in _LATTICE if o not in holds]
        taken = set(sampled_orderings)
        label = "%s %s %s" % (_AXIS_TEXT.get(axis, axis), _OP_TEXT[op], tag)
        if holds and not taken.intersection(holds):
            gaps.append("%s is never true (sampled: %s)"
                        % (label, sampled_orderings))
        if fails and not taken.intersection(fails):
            gaps.append("%s is never false (sampled: %s)"
                        % (label, sampled_orderings))

    return sorted(set(gaps)), sorted(set(info))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="check-axes",
        description="verify an axis profile covers the values the rules use")
    parser.add_argument("source")
    parser.add_argument("--axes", required=True)
    parser.add_argument("--features")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="treat explicit-axis omissions as gaps")
    args = parser.parse_args(argv)
    try:
        profile = axesmod.load(args.axes)
        gaps, info = check(args.source, profile, args.features)
    except (axesmod.AxisError, ValueError, OSError) as exc:
        print("check-axes: %s" % exc, file=sys.stderr)
        return 2
    if args.strict:
        gaps = sorted(set(gaps) | set(info))
        info = []
    if args.json:
        print(json.dumps({"gaps": gaps, "info": info}, indent=1,
                         sort_keys=True))
    else:
        for gap in gaps:
            print(gap)
        for note in info:
            print("info: " + note)
        print("%s: %d gap(s), %d note(s)" % (args.axes, len(gaps), len(info)))
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
