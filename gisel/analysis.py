"""Read-only analysis of a `.gisel` source and its core document.

Three callers used to reach into `gisel.cases` for these: `graph`, `domain`
and the workbench's `tools/check-axes.py`.  None of them generates a case, so
the helpers live here instead: parsing to the schema-0.4 document, deriving a
feature table, and projecting a ruleset into the slots/literals/observations
the axes and the graph are built from.

`cases` re-exports every public name below so existing callers keep working.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import ast as A
from . import eval as E
from . import llt as L
from .backend import core_json


def _slot_of(node):
    """The literal slot index an expression reads, or None."""
    if not isinstance(node, dict):
        return None
    k = node.get("kind")
    if k == "slot":
        return node["index"]
    if k == "sameAs":
        arg = node.get("args", [None])[0]
        return arg["value"] if isinstance(arg, dict) and "value" in arg else None
    for key in ("args", "arg"):
        v = node.get(key)
        if isinstance(v, list):
            for x in v:
                s = _slot_of(x)
                if s is not None:
                    return s
        elif isinstance(v, dict):
            s = _slot_of(v)
            if s is not None:
                return s
    return None


def _dim_of(node):
    """``bits`` / ``bytes`` / ``lanes`` for a numeric expression, or None."""
    if not isinstance(node, dict):
        return None
    k = node.get("kind")
    if k in ("bitsOf", "scalarOf", "sizeOf"):
        return "bits"
    if k == "sizeInBytesOf":
        return "bytes"
    if k == "numElems":
        return "lanes"
    if k == "type":
        return "bits"
    return None


def _mem_observation(node):
    """``("size"|"align", None)`` for a direct memory-descriptor read.

    A rule may ask about the memory type itself rather than name a descriptor:
    `size_of(mem_ty(mem_slot(0)))` and `align_of(mem_slot(0))`.  Those are the
    only two observations in the language, so recording the literal they are
    compared against is enough to synthesise a memory axis.
    """
    if not isinstance(node, dict):
        return None
    if node.get("kind") == "sizeOf":
        inner = (node.get("args") or [None])[0]
        if isinstance(inner, dict) and inner.get("kind") == "memTy":
            return "size"
    if node.get("kind") == "alignOf":
        inner = (node.get("args") or [None])[0]
        if isinstance(inner, dict) and inner.get("kind") == "memSlot":
            return "align"
    return None


def _literals(node):
    """LLT literals in a set/type node, as parsed tuples."""
    out = []
    if not isinstance(node, dict):
        return out
    if node.get("kind") == "type":
        value = node.get("value")
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, dict):
            for key in ("then", "else"):
                if isinstance(value.get(key), str):
                    out.append(value[key])
    elif node.get("kind") == "set":
        for e in node.get("elems", []):
            if isinstance(e, str):
                out.append(e)
            elif isinstance(e, list):
                out.extend(x for x in e[:3] if isinstance(x, str))
    return out


@dataclass
class RuleInfo:
    literals: dict = field(default_factory=dict)   # slot -> set[(dim, n)]
    thresholds: dict = field(default_factory=dict)  # slot -> set[(dim, n)]
    mem_entries: list = field(default_factory=list)  # (t0, t1, mty, align)
    mem_obs: set = field(default_factory=set)  # ("size"|"align", literal)
    uses_mem: bool = False
    slots: set = field(default_factory=set)
    uses_ordering: bool = False
    imms: set = field(default_factory=set)           # imm indices this rule reads
    imm_values: dict = field(default_factory=dict)   # index -> {literal}
    imm_thresholds: dict = field(default_factory=dict)  # index -> {literal}


def _add_literal(info, slot, text):
    try:
        t = E.parse_case_llt(text)
    except E.EvalError:
        return
    info.literals.setdefault(slot, set()).add(t)
    bits = L.scalar_bits(t)
    if bits:
        info.thresholds.setdefault(slot, set()).add(("bits", bits))
    lanes = L.lanes(t)
    if lanes:
        info.thresholds.setdefault(slot, set()).add(("lanes", lanes))


def _walk_info(node, info):
    if not isinstance(node, dict):
        return
    k = node.get("kind")
    if k == "slot":
        info.slots.add(node["index"])
    if k == "memSlot":
        info.uses_mem = True
    if k == "imm":
        info.imms.add(node["index"])
    if k in ("memOrdering", "memFailureOrdering"):
        info.uses_ordering = True

    if k == "in":
        lhs, rhs = node["args"]
        if (isinstance(lhs, dict) and lhs.get("kind") == "imm"
                and isinstance(rhs, dict) and rhs.get("of") == "Int"):
            index = lhs["index"]
            info.imms.add(index)
            for value in rhs.get("elems", []):
                if isinstance(value, int):
                    info.imm_values.setdefault(index, set()).add(value)
        slot = _slot_of(lhs)
        if slot is not None:
            info.slots.add(slot)
            for text in _literals(rhs):
                _add_literal(info, slot, text)
    elif k in ("inPairs", "inTriples"):
        args = node["args"]
        slots = [x["index"] for x in args[:-1] if x.get("kind") == "slot"]
        for i, e in enumerate(args[-1].get("elems", [])):
            if isinstance(e, list):
                for j, text in enumerate(e):
                    if j < len(slots) and isinstance(text, str):
                        _add_literal(info, slots[j], text)
    elif k == "inMemDesc":
        info.uses_mem = True
        for e in node["args"][3].get("elems", []):
            if isinstance(e, list) and len(e) == 4:
                info.mem_entries.append(tuple(e))
    elif k in ("eq", "ne", "lt", "le", "gt", "ge"):
        a, b = node["args"]
        for expr, other in ((a, b), (b, a)):
            if other.get("kind") != "int":
                continue
            if isinstance(expr, dict) and expr.get("kind") == "imm":
                index = expr["index"]
                info.imms.add(index)
                info.imm_thresholds.setdefault(index, set()).add(other["value"])
                continue
            obs = _mem_observation(expr)
            if obs is not None:
                info.uses_mem = True
                info.mem_obs.add((obs, other["value"]))
                continue
            slot = _slot_of(expr)
            dim = _dim_of(expr)
            if slot is not None and dim is not None:
                info.slots.add(slot)
                info.thresholds.setdefault(slot, set()).add((dim, other["value"]))
    elif k == "leaf" and node.get("name") == "isPow2":
        slot = _slot_of(node)
        if slot is not None:
            info.slots.add(slot)
            for n in L.POW2:
                info.thresholds.setdefault(slot, set()).add(("bits", n))

    for key in ("args", "arg", "set"):
        v = node.get(key)
        if isinstance(v, list):
            for x in v:
                _walk_info(x, info)
        elif isinstance(v, dict):
            _walk_info(v, info)


def inspect_rule(rule):
    info = RuleInfo()
    _walk_info(rule["predicate"], info)
    for key in ("on", "to"):
        if rule.get(key):
            _walk_info(rule[key], info)
    return info


def inspect_ruleset(rs):
    nslots = 1
    for rule in rs["rules"]:
        for node in (rule["predicate"], rule.get("on"), rule.get("to")):
            s = _slot_of(node)
            if s is not None:
                nslots = max(nslots, s + 1)
    infos = [inspect_rule(r) for r in rs["rules"]]
    for info in infos:
        for s in info.slots:
            nslots = max(nslots, s + 1)
    return nslots, infos


def imm_candidates(infos, axes=None):
    """Per-index immediate candidates derived from the rules' own literals.

    ``imm(i) == 32`` and ``in(imm(i), [8, 16])`` are the only ways a rule can
    name an immediate, so the literals (plus their immediate neighbours) are
    the finite axis.  A profile may replace/extend the values per index.
    """
    read, values = set(), {}
    for info in infos:
        read |= info.imms
        for index, literals in info.imm_values.items():
            values.setdefault(index, set()).update(
                int(v) for v in literals)
        for index, literals in info.imm_thresholds.items():
            values.setdefault(index, set()).update(
                int(v) for v in literals)
    out = {}
    for index in sorted(read):
        base = set(values.get(index, set()))
        candidates = set(base)
        candidates.add(0)
        for value in base:
            candidates.add(value + 1)
            if value > 0:
                candidates.add(value - 1)
        ordered = sorted(candidates)
        if axes is not None:
            ordered = axes.apply_imms(index, ordered)
        out[index] = ordered
    return out


def imm_tuples(imm_axis, cap=32):
    """Cartesian product of the per-index values, as evaluator tuples."""
    if not imm_axis:
        return [()]
    indexes = sorted(imm_axis)
    width = indexes[-1] + 1
    out = []
    for combo in itertools.product(*(imm_axis[i] for i in indexes)):
        if len(out) >= cap:
            break
        value = [0] * width
        for index, item in zip(indexes, combo):
            value[index] = item
        out.append(tuple(value))
    return out or [()]


def type_value_spellings(value):
    """LLT spellings denoted by a core type value.

    A type value is a string, or a feature-selected pair
    ``{"select": {"cond": ..., "then": ..., "else": ...}}``.  A caller with
    an evaluator can pick one branch; without one, both branches are the
    sound union, because the query generator covers every configuration.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        select = value.get("select")
        if isinstance(select, dict):
            out = []
            for key in ("then", "else"):
                for text in type_value_spellings(select.get(key)):
                    if text not in out:
                        out.append(text)
            return out
    return []


def document(source):
    """The schema-0.4 document for one `.gisel` file, exactly as core emits it."""
    source = str(source)
    text = Path(source).read_text()
    gs = A.parse_program(text)
    gs = A.Program(gs.decls, A.canonicalize_rulesets(gs.rulesets),
                   gs.features, gs.preds, gs.named_types, gs.selects,
                   gs.setlike)
    return json.loads(core_json.emit_core(gs, source, text))


def derive_features(doc, path=None, configs=None):
    """Feature table from a file, or one derived from the document's guards."""
    if path:
        table = E.load_features(path)
        if configs:
            table = E.Features({c: table.table[c] for c in configs
                                if c in table.table})
        return table
    exprs = []
    seen = set()

    def walk(n):
        if isinstance(n, dict):
            if n.get("kind") == "leaf" and n.get("name") == "hasFeature":
                expr = n["args"][0]
                if expr not in seen:
                    seen.add(expr)
                    exprs.append(expr)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    for rs in doc["rulesets"]:
        for rule in rs["rules"]:
            walk(rule["predicate"])

    rows = {}
    rows["none"] = {e: False for e in exprs}
    rows["all"] = {e: True for e in exprs}
    for i, expr in enumerate(exprs):
        row = {x: False for x in exprs}
        row[expr] = True
        rows["only-%d" % i] = row
    for row in rows.values():
        row.setdefault("LLT::getUseExtended()", True)
    table = E.Features(rows)
    if configs:
        table = E.Features({c: rows[c] for c in configs if c in rows})
    return table


