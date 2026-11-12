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
from . import contract
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
    targets: dict = field(default_factory=dict)    # slot -> set[(dim, n)] from on/to
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
    """Record what one rule reads.

    The traversal is `ast.walk_nodes`: it descends through every dict value,
    so an inline `select_type` arm is inspected too.  The old hand-written
    recursion only followed `args`/`arg`/`set` and silently skipped a select
    guard -- a feature or slot inside one never reached the axes.
    """
    for n in A.walk_nodes(node):
        k = n.get("kind")
        if k == "slot":
            info.slots.add(n["index"])
        if k == "memSlot":
            info.uses_mem = True
        if k == "imm":
            info.imms.add(n["index"])
        if k in ("memOrdering", "memFailureOrdering"):
            info.uses_ordering = True

        if k == "in":
            lhs, rhs = n["args"]
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
            args = n["args"]
            slots = [x["index"] for x in args[:-1] if x.get("kind") == "slot"]
            for i, e in enumerate(args[-1].get("elems", [])):
                if isinstance(e, list):
                    for j, text in enumerate(e):
                        if j < len(slots) and isinstance(text, str):
                            _add_literal(info, slots[j], text)
        elif k == "inMemDesc":
            info.uses_mem = True
            for e in n["args"][3].get("elems", []):
                if isinstance(e, list) and len(e) == 4:
                    info.mem_entries.append(tuple(e))
        elif k in ("eq", "ne", "lt", "le", "gt", "ge"):
            a, b = n["args"]
            for expr, other in ((a, b), (b, a)):
                if other.get("kind") != "int":
                    continue
                if isinstance(expr, dict) and expr.get("kind") == "imm":
                    index = expr["index"]
                    info.imms.add(index)
                    info.imm_thresholds.setdefault(index, set()).add(
                        other["value"])
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
                    info.thresholds.setdefault(slot, set()).add(
                        (dim, other["value"]))
        elif k == "leaf" and n.get("name") == "isPow2":
            slot = _slot_of(n)
            if slot is not None:
                info.slots.add(slot)
                for value in L.POW2:
                    info.thresholds.setdefault(slot, set()).add(
                        ("bits", value))


def inspect_rule(rule):
    info = RuleInfo()
    _walk_info(rule["predicate"], info)
    for key in ("on", "to"):
        node = rule.get(key)
        if not node:
            continue
        _walk_info(node, info)
        # A mutation's target type is a seed for the directed witness search
        # even though it is not a value the rule *matches*: `clamp_min(0, s32,
        # 2)` and `widen(elem_of(slot(0)), min_vector_size(64))` name their
        # type only inside `to`.  Keep these out of `literals`, which the main
        # candidate axes use, so the base query set does not move.
        slot = _slot_of(node)
        if slot is None:
            continue
        for n in A.walk_nodes(node):
            if n.get("kind") != "ty":
                continue
            args = n.get("args") or []
            for text in _literals(args[0] if args else None):
                try:
                    t = E.parse_case_llt(text)
                except E.EvalError:
                    continue
                info.targets.setdefault(slot, set()).add(t)
    return info


def walk_atoms(node, out):
    """Predicate atoms, descending only through boolean combinators.

    A `select` guard is one atom: its arms are not separate unary observations
    of a slot.  This is the class-partition definition in `spec/graph.md` and
    is deliberately narrower than `ast.walk_nodes`.
    """
    if not isinstance(node, dict):
        return
    if node.get("kind") in ("all", "any", "not", "nary"):
        for value in node.get("args", []):
            walk_atoms(value, out)
        if "arg" in node:
            walk_atoms(node["arg"], out)
        return
    out.append(node)


def atoms(ruleset):
    """Every distinct predicate atom in a ruleset, in first-seen order."""
    out, seen = [], set()
    for rule in ruleset["rules"]:
        found = []
        walk_atoms(rule.get("predicate"), found)
        for atom in found:
            key = json.dumps(atom, sort_keys=True, separators=(",", ":"),
                             default=str)
            if key not in seen:
                seen.add(key)
                out.append(atom)
    return out


def dependencies(node):
    """(slots, has_mem, imms, has_ordering) read by one predicate or mutation."""
    info = RuleInfo()
    _walk_info(node, info)
    return info.slots, info.uses_mem, info.imms, info.uses_ordering


def mutation_slots(node):
    """Slots a mutation expression reads, including ``same_as(k)`` indices."""
    slots = set()
    for n in A.walk_nodes(node):
        slot = _slot_of(n)
        if slot is not None:
            slots.add(slot)
    return slots


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
    """Feature table from a file, or one derived from the document's guards.

    A feature can appear in a rule predicate or in a `select_type` inside an
    `on`/`to` mutation; every field is walked, so a configuration axis is
    never dropped just because it lives in the mutation.
    """
    if path:
        table = E.load_features(path)
        if configs:
            table = E.Features({c: table.table[c] for c in configs
                                if c in table.table})
        return table
    exprs = []
    seen = set()
    for rs in doc["rulesets"]:
        for rule in rs["rules"]:
            for field in (rule["predicate"], rule.get("on"), rule.get("to")):
                for node in A.walk_nodes(field):
                    if (node.get("kind") == "leaf"
                            and node.get("name") == "hasFeature"):
                        expr = node["args"][0]
                        if expr not in seen:
                            seen.add(expr)
                            exprs.append(expr)

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


# Shapes the generic MIR verifier rejects before the legalizer can run.  A
# query of such a shape is not reachable, so it is not part of the domain: the
# runner would either abort on the official side or answer a question that no
# `llc` input can ask.
#
# Every entry names where the rule comes from.  A shape rule is a claim about
# LLVM, so it is either quoted from a verifier check or marked `semantics` when
# the verifier does not check the opcode and only the opcode's meaning
# constrains it.  Opcodes with no entry are *not* guessed at: the cartesian
# product still produces whatever the rules admit.
#
# This is a filter on the *question*, not on the answer: it never decides what
# a legal query means, only whether the question can be asked at all.

def type_shape_ok(opcode, types):
    """True when the tuple is a question the MIR verifier would pass on.

    A query of a shape the verifier rejects is not reachable from IR: the
    runner would either abort before answering or answer a question no `llc`
    input can ask.  Those tuples are not part of the domain.

    The rules live in `gisel/data/contract-shapes.jsonc`, one entry per
    opcode, each carrying the verifier check it transcribes as `source`.
    Opcodes with no entry are not guessed at: the cartesian product still
    produces whatever the rules admit.  This is a filter on the *question*,
    not on the answer: it never decides what a legal query means.
    """
    return contract.check(opcode, types)


# ---------------------------------------------------------------------------
# Value candidates (moved from cases.py; graph is the other caller)
# ---------------------------------------------------------------------------

# Values that exercise each LLT kind even when a rule set names none of them.
# Ordered so a rule with no literals still gets an ordinary scalar witness
# before the exotic shapes; the list is a fallback, not a preference.
_SENTINELS = (
    "s32", "s64", "s8", "s16", "s128", "s1", "s3", "s7", "s24", "s31",
    "s33", "s63", "s65", "v4s32", "v2s64", "v16s8", "nxv1s8", "v3s32",
    "nxv4s32", "p0:64", "p0:32", "p0:128", "p0:*", "f16", "f32", "f64",
    "bf16",
)
_SENTINEL_LLTS = tuple(E.parse_case_llt(s) for s in _SENTINELS)


_KIND_ORDER = L.KIND_ORDER


def _candidate_key(t):
    """Prefer the ordinary spelling of a rule's own predicate.

    A `bits_of(slot) == 64` rule is satisfied by both `s64` and `p0:64`; the
    scalar is the natural witness, and using the pointer here would make the
    boundary pass mutate the pointer width.  Pointers stay available after
    scalars, so `typeIs(slot, p0)` rules still get a pointer witness.
    """
    return (_KIND_ORDER.get(t[0], 9), L.spell(t))


def candidates(infos, nslots, cap, domain, scalable_ok=True):
    """Per-slot candidates: literals, domain types, neighbours, sentinels."""
    per = []
    for i in range(nslots):
        lit = set()
        for info in infos:
            lit |= info.literals.get(i, set())
        if not lit and not any(i in info.slots for info in infos):
            per.append([E.parse_case_llt("s32")])
            continue
        # A mutation rule only fires on a type its legal rules do *not* name,
        # so the neighbours of the literals are the candidates that reach it.
        # They must survive the cap: truncating to `max(cap, len(lit))` used to
        # drop every neighbour whenever a slot had `cap` or more literals,
        # which left the rules behind them permanently unwitnessed.  Domain
        # types go last so the product guard below trims them first.
        neigh = {x for t in lit for x in L.neighbours(t)}
        ordered = sorted(lit, key=_candidate_key)
        ordered += [t for t in sorted(neigh, key=_candidate_key)
                    if t not in ordered]
        ordered += [t for t in _SENTINEL_LLTS if t not in ordered]
        if cap > 0:
            keep = max(cap, len(ordered))
            ordered += [t for t in sorted(domain, key=_candidate_key)
                        if t not in ordered][:max(0, keep - len(ordered))]
        else:
            ordered += [t for t in sorted(domain, key=_candidate_key)
                        if t not in ordered]
        if not scalable_ok:
            ordered = [x for x in ordered
                       if not (x[0] == "vector" and x[2])] or ordered[:1]
        per.append(ordered)
    # Keep the cartesian product bounded without dropping any literal.
    while product_size(per) > 20000:
        widest = max(range(len(per)), key=lambda i: len(per[i]))
        if len(per[widest]) <= 1:
            break
        per[widest] = per[widest][:-1]
    return per


def product_size(per):
    n = 1
    for values in per:
        n *= len(values)
    return n


def mem_candidates(infos, expand=None):
    """Memory descriptor rows, with selected memory types made hashable."""
    expand = expand or type_value_spellings
    entries = []
    for info in infos:
        entries.extend(info.mem_entries)
    out = []
    seen = set()
    for t0, t1, mty, align in entries:
        for a in expand(t0):
            for b in expand(t1):
                for c in expand(mty):
                    key = (a, b, c, align)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(key)
    if out:
        return out
    return _observed_mem_entries(infos)


def _observed_mem_entries(infos, max_slot_types=4):
    """Descriptors for rules that read the memory type without naming one.

    `size_of(mem_ty(mem_slot(0))) == 32` says what the memory type must be
    wide; `align_of(mem_slot(0))` says how aligned.  Without a descriptor row
    there is no memory axis at all, and every rule that reads one is silently
    unwitnessed (Mips' G_LOAD was).  Synthesise one row per observed size at
    two alignments -- the minimum and the size itself, which are the two sides
    of `size <= align` -- crossed with the rules' own slot-type literals.
    """
    sizes, aligns = set(), set()
    for info in infos:
        for kind, value in info.mem_obs:
            (sizes if kind == "size" else aligns).add(value)
    if not sizes:
        return []
    slot0, slot1 = [], []
    for info in infos:
        for text in sorted(L.spell(t) for t in info.literals.get(0, ())):
            if text not in slot0:
                slot0.append(text)
        for text in sorted(L.spell(t) for t in info.literals.get(1, ())):
            if text not in slot1:
                slot1.append(text)
    if not slot0 or not slot1:
        return []
    rows = []
    seen = set()
    for bits in sorted(sizes):
        if bits < 8 or bits % 8:
            continue
        mty = "s%d" % bits
        for align in sorted({8, bits}):
            for t0 in slot0[:max_slot_types]:
                for t1 in slot1[:max_slot_types]:
                    key = (t0, t1, mty, align)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(key)
    return rows


# Back-compat for cases.py and its tests; graph imports the public names.
_candidates = candidates
_mem_candidates = mem_candidates
_product_size = product_size

