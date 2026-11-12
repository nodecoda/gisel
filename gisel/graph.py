"""Build a finite quotient graph for a schema-0.4 legalizer document.

The graph is deliberately built on the same normal form and evaluator as the
other gisel commands.  It is a static diagnostic: no MIR, TableGen or LLVM
runtime is involved.
"""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import analysis as AN
from . import axes as axesmod
from . import domain as D
from . import dsl
from . import eval as E
from . import jsonl as jsonl_codec
from . import llt as L


from .actions import TERMINAL_ACTIONS

TERMINAL = TERMINAL_ACTIONS
# Wider than `cases`' 16 on purpose: the graph must address boundary and
# outside points that the case generator deliberately trims.
GRAPH_CANDIDATE_CAP = 64
_CLOSURE_SAMPLE_LIMIT = 20
# Representative choice inside a class, not the candidate sentinel list:
# prefer the odd/lane-3 shapes so a class is addressed by its most specific
# member.  The candidate list itself lives in `analysis`.
_REPRESENTATIVE_TEXT = ("s3", "s7", "s24", "s33", "s63", "s65",
                        "v3s8", "v5s8", "v3s32", "v5s32")
_REPRESENTATIVE_RANK = {text: i
                        for i, text in enumerate(_REPRESENTATIVE_TEXT)}


class GraphError(ValueError):
    def __init__(self, message, *, kind=None, detail=None):
        super().__init__(message)
        self.kind = kind
        self.detail = detail or {}


def _json_key(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      default=str)


def _type_text(t):
    return L.spell(t)


def _representative_key(t):
    return (_REPRESENTATIVE_RANK.get(_type_text(t),
                                     len(_REPRESENTATIVE_RANK)),
            _type_text(t))


def _violation_text(violation):
    """One-line closure sample; never a raw Python dict."""
    parts = [str(violation.get("state", ""))]
    member = violation.get("member")
    if member:
        parts.append("member=" + ",".join(member))
    mutation = violation.get("mutation")
    if mutation:
        parts.append("mutation=" + mutation)
    targets = violation.get("targets")
    if targets:
        parts.append("targets=" + " | ".join(targets))
    reason = violation.get("reason")
    if reason:
        parts.append("reason=" + reason)
    return " ".join(part for part in parts if part)


def _node_text(node):
    opcode, classes, mem = node[0], node[1], node[2]
    suffix = ",m%s" % mem if mem is not None else ""
    if len(node) > 3 and node[3] is not None:
        suffix += ",i%s" % node[3]
    return "%s[%s%s]" % (opcode, ",".join(map(str, classes)), suffix)



def _collapse(t, extended):
    return t if extended else E.collapse_extended(t)


def _parse_type(text, extended):
    try:
        return _collapse(E.parse_case_llt(text), extended)
    except E.EvalError as exc:
        raise GraphError(str(exc)) from exc


def _mem_desc(mem, extended):
    if mem is None:
        return []
    ordering, failure = ((mem[2], mem[3]) if len(mem) >= 4
                         else ("NotAtomic", "NotAtomic"))
    return [E.MemDesc(_parse_type(mem[0], extended), int(mem[1]),
                      ordering, failure)]


def _opcode_shape(opcode, slots):
    """Arity and pointer slots from the one bundled table.

    An entry with no `ptype` is a broken snapshot, not "no pointer slots": the
    generator always writes both keys, so treating a missing key as empty would
    hide a data bug.
    """
    info = slots.get(opcode)
    if info is None:
        return None, set()
    if "arity" not in info or "ptype" not in info:
        raise GraphError(
            "opcode %s: opcode-slots.json entry lacks arity/ptype" % opcode)
    return info["arity"], set(info["ptype"])


def _declared_types(source, pointer_width, extended):
    types, _, _ = D.domain_axes(source, pointer_width)
    return {_parse_type(text, extended) for text in types}


def _mem_type_spellings(node, evaluator, config):
    """Resolve a memory-type value for one configuration.

    An unresolved select falls back to both branches: dropping the row would
    silently shrink the memory axis, which is worse than keeping a sound union.
    """
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        select = node.get("select")
        if isinstance(select, dict):
            try:
                branch = ("then" if evaluator.bool_value(
                    select["cond"], [], None, config) else "else")
            except Exception:
                return AN.type_value_spellings(node)
            return _mem_type_spellings(select.get(branch), evaluator, config)
    return AN.type_value_spellings(node)


def _memory_values(infos, domain_mems, pointer_width, extended, extra_mems=(),
                   expand=None, axis_profile=None,
                   ordering_pairs=(("NotAtomic", "NotAtomic"),)):
    rows = list(AN.mem_candidates(infos, expand=expand))
    if axis_profile is not None:
        rows = axis_profile.apply_mems(rows)
    if not rows:
        rows = [(mty, "", mty, align) for mty, _bits, align in domain_mems]
    out, seen = [], set()
    for _t0, _t1, mty, align in rows:
        mty = D._resolve(str(mty), pointer_width)
        value = (mty, int(align))
        parsed = (_parse_type(mty, extended), value[1])
        if parsed not in seen:
            seen.add(parsed)
            out.append(value)
    points, seen_points = [], set()
    for mty, align in out:
        for ordering, failure in ordering_pairs:
            key = (mty, align, ordering, failure)
            if key not in seen_points:
                seen_points.add(key)
                points.append(key)
    for entry in extra_mems:
        mty = D._resolve(str(entry[0]), pointer_width)
        align = int(entry[1])
        pairs = ([(entry[2], entry[3])] if len(entry) >= 4
                 else ordering_pairs)
        for ordering, failure in pairs:
            key = (mty, align, ordering, failure)
            if key not in seen_points:
                seen_points.add(key)
                points.append(key)
    return sorted(points, key=lambda x: (x[0], x[1], x[2], x[3]))


def _candidate_axes(infos, arity, ptypes, domain_types, extra_types, extended,
                    include_non_pointer=False, include_derived=True):
    # Start with every declared value and add the deterministic cut points
    # that cases.py derives from the rules.  These are the finite observation
    # domain, and are also what lets the graph address the existing oracle's
    # boundary queries.  A mutation outside this set is reported as outside.
    base = (AN.candidates(infos, arity, GRAPH_CANDIDATE_CAP,
                                 list(domain_types))
            if include_derived else [[] for _ in range(arity)])
    axes = []
    for index in range(arity):
        values = list(domain_types) + list(base[index]) + list(extra_types)
        if index in ptypes and not include_non_pointer:
            values = [t for t in values if t[0] == "pointer"]
        unique = {}
        for value in values:
            unique[_type_text(value)] = value
        axes.append([unique[k] for k in sorted(unique)])
        if not axes[-1]:
            raise GraphError("opcode slot %d has no finite type candidates" % index)
    return axes


def _atom_value(evaluator, atom, types, mem, config, imms=()):
    try:
        value = evaluator.bool_value(atom, types, _mem_desc(mem, evaluator.extended(config)),
                                     config, imms)
        if value is None:
            return None
        return bool(value)
    except (E.EvalError, IndexError, KeyError, TypeError, ValueError,
            ZeroDivisionError, AssertionError):
        return None


@dataclass
class AxisClasses:
    values: list
    class_of: dict
    members: dict
    signatures: dict


def _make_classes(values, axis, atoms, rules, axes, mem_values,
                  evaluator, config):
    baseline = [items[0] for items in axes]
    base_mem = mem_values[0] if mem_values else None
    base_mems = _mem_desc(base_mem, evaluator.extended(config))
    signatures = {}
    for value in values:
        types = list(baseline)
        types[axis] = value
        signature = []
        for atom in atoms:
            slots, has_mem, has_imm, has_ordering = AN.dependencies(atom)
            if (slots - {axis}) or has_mem or has_ordering:
                # A relation involving another slot cannot be represented by
                # a unary class without losing information.  Preserve the
                # concrete value; closure checking still audits the result.
                signature.append(["raw", _type_text(value)])
            elif has_imm:
                # The imm axis is a separate dimension; keeping the value
                # here would make the type class depend on it.
                signature.append(["raw-imm", _type_text(value)])
            else:
                signature.append(_atom_value(evaluator, atom, tuple(types),
                                              base_mem, config))
        # The explicit predicate alone is not the whole observation: a rule
        # also carries an implicit shim guard (widen only fires on a
        # non-power-of-two size, scalarize only on a vector, ...).  Two types
        # that differ only in that guard have different successors, so the
        # class must record it or the quotient stops being a function.
        for rule in rules:
            if rule.get("on") is None:
                continue
            slots, has_mem, has_imm, has_ordering = AN.dependencies(
                rule.get("predicate"))
            to_slots = AN.mutation_slots(rule.get("to"))
            if ((slots - {axis}) or has_mem or has_imm or has_ordering
                    or (to_slots - {axis})):
                signature.append(["raw-guard", _type_text(value)])
            else:
                signature.append(E.rule_matches(
                    evaluator, config, rule, tuple(types), base_mems))
        signatures[value] = tuple(signature)

    groups = collections.defaultdict(list)
    for value, signature in signatures.items():
        groups[_json_key(signature)].append(value)
    class_of, members, ordered = {}, {}, []
    for cid, key in enumerate(sorted(groups)):
        group = sorted(groups[key], key=_representative_key)
        members[cid] = group
        ordered.append((cid, group, json.loads(key)))
        for value in group:
            class_of[value] = cid
    return AxisClasses(list(values), class_of, members,
                       {cid: sig for cid, _group, sig in ordered})


def _make_mem_classes(mem_values, atoms, axes, evaluator, config):
    baseline = [items[0] for items in axes]
    signatures = {}
    for value in mem_values:
        signature = []
        for atom in atoms:
            slots, has_mem, has_imm, _has_ordering = AN.dependencies(atom)
            if slots or not has_mem or has_imm:
                signature.append(["raw", value])
            else:
                signature.append(_atom_value(evaluator, atom, tuple(baseline),
                                              value, config))
        signatures[value] = tuple(signature)
    groups = collections.defaultdict(list)
    for value, signature in signatures.items():
        groups[_json_key(signature)].append(value)
    class_of, members, ordered = {}, {}, []
    for cid, key in enumerate(sorted(groups)):
        group = sorted(groups[key], key=lambda x: (x[0], x[1]))
        members[cid] = group
        ordered.append((cid, group, json.loads(key)))
        for value in group:
            class_of[value] = cid
    return AxisClasses(list(mem_values), class_of, members,
                       {cid: sig for cid, _group, sig in ordered})


def _make_imm_classes(values, atoms, evaluator, config):
    """Classify immediate tuples by the predicate values that read only them."""
    signatures = {}
    for value in values:
        signature = []
        for atom in atoms:
            slots, has_mem, has_imm, _has_ordering = AN.dependencies(atom)
            if not has_imm:
                continue
            if slots or has_mem:
                # Cannot be a function of imm alone; keep the value distinct
                # so the quotient never merges two different imm points.
                signature.append(["raw", list(value)])
            else:
                signature.append(_atom_value(evaluator, atom, (), None,
                                              config, value))
        signatures[value] = tuple(signature)
    groups = collections.defaultdict(list)
    for value, signature in signatures.items():
        groups[_json_key(signature)].append(value)
    class_of, members, ordered = {}, {}, []
    for cid, key in enumerate(sorted(groups)):
        group = sorted(groups[key])
        members[cid] = group
        ordered.append((cid, group, json.loads(key)))
        for value in group:
            class_of[value] = cid
    return AxisClasses(list(values), class_of, members,
                       {cid: sig for cid, _group, sig in ordered})


def _rebuild_classes(table, groups):
    """Renumber a partition after a refinement split."""
    groups = [sorted(group, key=_representative_key) for group in groups]
    groups = [group for group in groups if group]
    groups.sort(key=lambda group: _representative_key(group[0]))
    class_of, members, signatures = {}, {}, {}
    for cid, group in enumerate(groups):
        members[cid] = group
        signatures[cid] = ["refined", cid]
        for value in group:
            class_of[value] = cid
    return AxisClasses(list(table.values), class_of, members, signatures)


def _refine_classes(type_classes, opcode, baseline, base_mem, evaluator,
                    config, extended, declared, max_rounds=8):
    """Split each axis class until one class has one successor class.

    This is opt-in.  The default partition is the atom `spec/graph.md`
    defines; refining it changes what "atom" means, so it never happens on
    its own and the class count before/after is reported.
    """

    def target_of(axis, value, table):
        types = list(baseline)
        types[axis] = value
        try:
            action, type_idx, new_type, rule = E.evaluate_with_rule(
                evaluator, config, opcode, types,
                _mem_desc(base_mem, extended), ())
        except Exception:
            return None
        if rule is None or action in TERMINAL:
            return None
        if type_idx != axis:
            # A cross-slot mutation (`widen(slot(1), same_as(0))`) is decided
            # by this axis but writes another one.  The old refinement only
            # looked at same-slot writes, so RISC-V's poison-count classes
            # stayed mixed: s3 and s8 both fired the rule, but widened slot 1
            # to nxv1s3 and nxv1s8 respectively.  Split on the actual target
            # of the other slot; using that slot's class would be coarser and
            # needs the full table set.
            if new_type == types[type_idx]:
                return None
            return ("slot", type_idx, _type_text(new_type))
        if new_type == value:
            return None
        if new_type not in declared:
            return None       # outside: no successor class to split by
        return ("class", table.class_of.get(new_type))

    for _round in range(max_rounds):
        changed = False
        refined = []
        for axis, table in enumerate(type_classes):
            seen = {}
            for cid, members in table.members.items():
                for value in members:
                    target = target_of(axis, value, table)
                    seen[value] = target
            by_class = collections.defaultdict(list)
            for value, target in seen.items():
                by_class[table.class_of[value]].append(value)
            groups = []
            for cid in sorted(by_class):
                values = by_class[cid]
                # `None` (no successor: terminal, no-rule, or outside the
                # declared domain) is its own bucket.  Folding it into an
                # arbitrary successor class left a class that mixed a moving
                # member with an outside one, which closure still rejects.
                keys = {seen[v] for v in values}
                if len(keys) <= 1:
                    groups.append(values)
                    continue
                changed = True
                buckets = collections.defaultdict(list)
                for value in values:
                    buckets[seen[value]].append(value)
                for key in sorted(buckets,
                                  key=lambda x: (x is not None, str(x))):
                    groups.append(buckets[key])
            refined.append(_rebuild_classes(table, groups))
        type_classes = refined
        if not changed:
            break
    return type_classes


def _opaque(evaluator, atoms, types, mem, config, imms=()):
    return any(_atom_value(evaluator, atom, types, mem, config, imms) is None
               for atom in atoms)


def _find_cycles(edges):
    """Three-colour DFS, iterative.

    A legalizer chain is a path, and the largest state sets are tens of
    thousands of nodes: recursion depth is the longest chain, not the node
    count, but a long chain can still exceed Python's default limit.  An
    explicit stack keeps the answer and the sample order identical without
    turning a deep graph into a `RecursionError`.
    """
    adjacency = {node: [target for target, _label in edges.get(node, [])
                        if target in edges]
                 for node in edges}
    color, count, samples = {}, 0, []
    for root in sorted(edges, key=_node_text):
        if color.get(root, 0) != 0:
            continue
        stack = [(root, 0)]
        path = []
        position = {}
        while stack:
            node, index = stack[-1]
            if index == 0:
                color[node] = 1
                position[node] = len(path)
                path.append(node)
            targets = adjacency.get(node, ())
            if index < len(targets):
                stack[-1] = (node, index + 1)
                target = targets[index]
                state = color.get(target, 0)
                if state == 1:
                    count += 1
                    if len(samples) < 5:
                        samples.append(path[position[target]:] + [target])
                elif state == 0:
                    stack.append((target, 0))
            else:
                stack.pop()
                path.pop()
                position.pop(node, None)
                color[node] = 2
    return count, samples


@dataclass
class Report:
    config: str
    states: dict
    edges: dict
    classes: int
    uncovered: list
    closure: dict
    injected_edge: dict | None = None
    class_tables: dict | None = None
    skipped: list | None = None
    classes_before: int | None = None
    shape_skipped: int = 0

    def public(self):
        outcomes = collections.Counter(s["outcome"] for s in self.states.values())
        for name in ("moves", "no-rule", "terminal", "opaque", "outside",
                     "stuck"):
            outcomes.setdefault(name, 0)
        terminal = collections.Counter(
            s.get("action") for s in self.states.values()
            if s["outcome"] == "terminal")
        cycles, samples = _find_cycles(self.edges)
        out = {
            "config": self.config,
            "states": len(self.states),
            "edges": sum(len(v) for v in self.edges.values()),
            "outcomes": dict(sorted(outcomes.items())),
            "terminal": dict(sorted(terminal.items())),
            "opaque": outcomes.get("opaque", 0),
            "outside": outcomes.get("outside", 0),
            "cycles": cycles,
            "cycle_samples": [[_node_text(x) for x in sample]
                              for sample in samples],
            "classes": self.classes,
            "shape": self.shape_skipped,
            **({"classes_before": self.classes_before}
               if self.classes_before is not None else {}),
            "uncovered": self.uncovered,
            "closure": self.closure,
            "injected_edge": self.injected_edge,
        }
        if self.skipped:
            out["skipped"] = list(self.skipped)
        return out


def _skip_matcher(entries):
    """Return a predicate for ``profiles.graph.skip`` entries.

    An entry matches an opcode exactly or as a family prefix
    (``G_INTRINSIC`` skips ``G_INTRINSIC_WO_CHAIN`` as well).
    """
    if not entries:
        return lambda _opcode: False
    entries = tuple(entries)
    return lambda opcode: any(opcode == e or opcode.startswith(e + "_")
                              for e in entries)


_SHAPE_SEARCH_LIMIT = 4096


def _shape_representative(opcode, pools):
    """A member tuple whose shape the MIR verifier accepts, or ``None``.

    Class pools are Cartesian, so a class tuple can hold no legalizer-visible
    combination at all: AArch64 ``G_ASHR`` crosses a vector source with a
    scalar amount, and ``MachineVerifier`` rejects that before the legalizer
    runs ("Shifts and rotates require operands to be either all scalars or all
    vectors").  Such a class tuple is not a state the official side can be
    asked about, so the graph must not build it.
    """
    if len(pools) < 2:
        return tuple(pool[0] for pool in pools)
    options = []
    for pool in pools:
        seen = {}
        for t in pool:
            vector = t[0] == "vector"
            sig = (vector, t[1] if vector else None,
                   t[2] if vector else None, t[3] if vector else None)
            seen.setdefault(sig, t)
        options.append(list(seen.values()))
    for combo in itertools.islice(itertools.product(*options),
                                  _SHAPE_SEARCH_LIMIT):
        if AN.type_shape_ok(opcode, combo):
            return tuple(combo)
    return None


def _state_key(opcode, type_classes, mem_class, imm_class=None):
    # Keep the historical three-tuple when the ruleset does not read imm, so
    # no-imm graphs keep their exact text and keys.
    if imm_class is None:
        return (opcode, tuple(type_classes), mem_class)
    return (opcode, tuple(type_classes), mem_class, imm_class)


def build(source, config, features, *, pointer_width=64, slots=None,
          inject_edge=False, check_closure=False, extra_types=(),
          extra_mems=(), arity_overrides=None, progress=False,
          axis_profile=None, refine=False, max_states=None):
    """Build one configuration's graph and return a :class:`Report`."""
    doc = AN.document(source)
    evaluator = E.Evaluator(doc, features)
    slots = slots or D.load_opcode_slots()
    extended = evaluator.extended(config)
    declared = _declared_types(source, pointer_width, extended)
    domain_mems = D.domain_axes(source, pointer_width)[1]
    skip = ()
    if axis_profile is not None:
        # The profile is the single value set shared with `cases` and
        # `domain`; deriving it again here would let the three commands drift.
        type_texts, domain_mems, _ = D.effective_axes(
            source, pointer_width, axis_profile)
        declared = {_parse_type(text, extended) for text in type_texts}
        skip = tuple(axis_profile.profile("graph").get("skip", ()))
    skip = _skip_matcher(skip)
    states = {}
    class_tables = {}
    universe = set()
    edges = collections.defaultdict(list)
    uncovered = []
    skipped = set()
    total_classes = 0
    classes_before = 0
    shape_skipped = 0
    started = time.monotonic()

    for rs_idx, rs in enumerate(doc["rulesets"]):
        nslots, infos = AN.inspect_ruleset(rs)
        atoms = AN.atoms(rs)
        imm_axis = AN.imm_candidates(infos, axis_profile)
        imm_tuples = AN.imm_tuples(imm_axis) if imm_axis else [()]
        imm_spec = axis_profile.imms() if axis_profile is not None else {}
        uses_ordering = any(info.uses_ordering for info in infos)
        ordering_covered = (axis_profile is not None
                            and axis_profile.has_orderings())
        ordering_pairs = (axis_profile.ordering_pairs()
                          if ordering_covered and uses_ordering
                          else [("NotAtomic", "NotAtomic")])
        # The graph does not invent imm values: without an explicit axis the
        # opcode is reported as uncovered instead of every state turning
        # opaque on an IndexError.
        imm_covered = all(index in imm_spec for index in imm_axis)
        for opcode in rs["opcodes"]:
            if skip(opcode):
                skipped.add(opcode)
                continue
            arity, ptypes = _opcode_shape(opcode, slots)
            if arity_overrides and opcode in arity_overrides:
                arity = arity_overrides[opcode]
            if arity is None:
                uncovered.append(opcode)
                continue
            if imm_axis and not imm_covered:
                uncovered.append(opcode)
                continue
            if uses_ordering and not ordering_covered:
                uncovered.append(opcode)
                continue
            if arity != nslots:
                n = max(arity, nslots)
            else:
                n = arity
            domain_types = sorted(declared, key=_type_text)
            axes = _candidate_axes(
                infos, n, ptypes, domain_types, extra_types, extended,
                include_non_pointer=bool(extra_types),
                include_derived=not (axis_profile is not None
                                     and axis_profile.types_explicit()))
            mem_values = _memory_values(
                infos, domain_mems, pointer_width, extended, extra_mems,
                expand=lambda value: _mem_type_spellings(value, evaluator,
                                                         config),
                axis_profile=axis_profile,
                ordering_pairs=ordering_pairs)
            mem_values = mem_values if any(info.uses_mem for info in infos) else [None]
            for axis in axes:
                universe.update(axis)
            type_classes = [_make_classes(axes[i], i, atoms, rs["rules"], axes,
                                          mem_values if mem_values != [None] else [],
                                          evaluator, config)
                            for i in range(n)]
            if refine:
                classes_before += sum(len(tc.members) for tc in type_classes)
                # Refinement must judge "outside" against the same finite
                # set the graph enumerates, not against the source's type
                # declarations alone: sentinel values the axes carry are
                # states too, so mutating into one is not a domain exit.
                type_classes = _refine_classes(
                    type_classes, opcode, [items[0] for items in axes],
                    mem_values[0] if mem_values != [None] else None,
                    evaluator, config, extended,
                    set(declared).union(*axes))
            mem_classes = (_make_mem_classes(mem_values, atoms, axes,
                                             evaluator, config)
                           if mem_values != [None] else None)
            imm_classes = (_make_imm_classes(imm_tuples, atoms, evaluator,
                                             config)
                           if imm_axis else None)
            total_classes += sum(len(x.members) for x in type_classes)
            class_tables[opcode] = (type_classes, mem_classes, imm_classes)
            # Enumerate one state per class tuple, not one per concrete type
            # tuple.  Every class is non-empty and the classes partition each
            # axis, so this is the same state set with a far smaller product
            # (AArch64's 50x50x50 slot products collapse to a few classes).
            ranges = [range(len(tc.members)) for tc in type_classes]
            for cls in itertools.product(*ranges):
                mem_range = (range(len(mem_classes.members))
                             if mem_classes else [None])
                imm_range = (range(len(imm_classes.members))
                             if imm_classes else [None])
                pools = [type_classes[i].members[cls[i]] for i in range(n)]
                representative = _shape_representative(opcode, pools)
                if representative is None:
                    shape_skipped += 1
                    continue
                for mc in mem_range:
                    for ic in imm_range:
                        key = _state_key(opcode, cls, mc, ic)
                        if key in states:
                            continue
                        states[key] = {
                            "key": key,
                            "pools": pools,
                            "mem_pool": (mem_classes.members[mc]
                                         if mem_classes else None),
                            "imm_pool": (imm_classes.members[ic]
                                         if imm_classes else None),
                            "types": representative,
                            "mem": (mem_classes.members[mc][0]
                                    if mem_classes else None),
                            "imm": (imm_classes.members[ic][0]
                                    if imm_classes else None),
                            "tables": (type_classes, mem_classes,
                                       imm_classes),
                            "outcome": None, "action": None, "type_idx": 0,
                            "rule": None,
                        }
                        if max_states is not None and len(states) > max_states:
                            raise GraphError(
                                "state_limit: %s reaches %d states (limit %d)"
                                % (opcode, len(states), max_states),
                                kind="state_limit",
                                detail={"states": len(states),
                                        "limit": max_states,
                                        "opcode": opcode})

        if progress:
            print("[%d/%d] %s: %d state(s), %.1fs"
                  % (rs_idx + 1, len(doc["rulesets"]),
                     ",".join(rs["opcodes"][:3]), len(states),
                     time.monotonic() - started),
                  file=sys.stderr, flush=True)

    # The finite domain is what the axes enumerate: declared types, the
    # literals and cut points taken from the rules, and the stable sentinels.
    # A sentinel that the axes carry is a state like any other; calling its
    # successors "outside" was a bookkeeping bug, not a coverage gap.
    domain = Domain(frozenset(set(declared) | universe), class_tables)
    for key, state in states.items():
        opcode = key[0]
        types, mem, imm = state["types"], state["mem"], state["imm"]
        # Re-find the ruleset atoms for this opcode.  Canonical gisel files
        # have one ruleset per opcode; the fallback keeps duplicate-opcode
        # fixtures safe by taking the union of their atoms.
        rses = [rs for rs in doc["rulesets"] if opcode in rs["opcodes"]]
        atoms = []
        seen = set()
        for rs in rses:
            for atom in AN.atoms(rs):
                k = _json_key(atom)
                if k not in seen:
                    seen.add(k); atoms.append(atom)
        if _opaque(evaluator, atoms, types, mem, config, imm):
            state["outcome"] = "opaque"
            continue
        try:
            action, type_idx, new_type, rule = E.evaluate_with_rule(
                evaluator, config, opcode, list(types), _mem_desc(mem, extended),
                imm or ())
        except (E.EvalError, IndexError, KeyError, TypeError, ValueError,
                ZeroDivisionError, AssertionError):
            state["outcome"] = "opaque"
            continue
        state.update({"action": action, "type_idx": type_idx, "rule": rule})
        if rule is None:
            state["outcome"] = "no-rule"
            continue
        if action in TERMINAL:
            state["outcome"] = "terminal"
            continue
        if type_idx >= len(types) or new_type == types[type_idx]:
            state["outcome"] = "stuck"
            continue
        target_key = domain.successor(opcode, types, mem, imm, type_idx,
                                      new_type)
        if target_key is None:
            state["outcome"] = "outside"
            continue
        state["outcome"] = "moves"
        edges[key].append((target_key, {
            "action": action, "type_idx": type_idx, "rule": rule,
        }))

    closure = {"checked": bool(check_closure), "ok": True,
               "violations": [], "count": 0,
               "kinds": {"partition": 0, "outside": 0}}
    if check_closure:
        limit = _CLOSURE_SAMPLE_LIMIT

        def record(entry):
            closure["count"] += 1
            closure["ok"] = False
            kind = entry.get("kind", "partition")
            closure["kinds"][kind] += 1
            if len(closure["violations"]) < limit:
                closure["violations"].append(entry)

        def classify(member_types, member_mem, member_imm):
            """(outcome, target_key, action, rule, detail) for one member."""
            try:
                action, type_idx, new_type, rule = E.evaluate_with_rule(
                    evaluator, config, key[0], list(member_types),
                    _mem_desc(member_mem, extended), member_imm or ())
            except Exception as exc:
                return ("opaque", None, None, None,
                        {"reason": "opaque", "detail": str(exc)})
            if rule is None:
                return "no-rule", None, action, rule, None
            if action in TERMINAL:
                return "terminal", None, action, rule, None
            if type_idx >= len(member_types) or new_type == member_types[type_idx]:
                return "stuck", None, action, rule, None
            target_key = domain.successor(
                key[0], member_types, member_mem, member_imm, type_idx,
                new_type)
            if target_key is None:
                return "outside", None, action, rule, {
                    "reason": "outside",
                    "mutation": _type_text(new_type),
                }
            return "moves", target_key, action, rule, None

        # Audit concrete members of *every* class, not just the representative
        # of a moving one.  A representative that is terminal (or outside, or
        # unruly) used to hide a member that moves: the class-level "successor
        # is a function" claim was never checked for those classes.
        for key in sorted(states, key=_node_text):
            state = states[key]
            if state["outcome"] == "opaque":
                continue
            targets = set()
            for types, mem, imm in _state_members(state):
                outcome, target_key, action, rule, detail = classify(
                    types, mem, imm)
                member = [_type_text(x) for x in types]
                if outcome != state["outcome"]:
                    entry = {
                        "state": _node_text(key), "member": member,
                        "reason": "different outcome",
                        "outcome": outcome,
                        "representative": state["outcome"],
                        # Either direction of an outside/moving mix is a
                        # coverage gap; anything else is a partition error.
                        "kind": ("outside" if "outside" in (outcome,
                                                            state["outcome"])
                                 else "partition"),
                    }
                    entry.update(detail or {})
                    record(entry)
                elif action != state["action"] or rule != state["rule"]:
                    record({
                        "state": _node_text(key), "member": member,
                        "reason": "different rule",
                        "action": action, "rule": rule,
                        "representative_action": state["action"],
                        "representative_rule": state["rule"],
                    })
                if outcome == "moves":
                    targets.add(target_key)
            if len(targets) > 1:
                record({
                    "state": _node_text(key),
                    "reason": "multiple target classes",
                    "targets": [_node_text(x) for x in sorted(targets,
                                                              key=_node_text)],
                })

    injected = None
    if inject_edge:
        choices = [(source, target) for source in sorted(edges, key=_node_text)
                   for target, _label in edges[source]
                   if source != target]
        if not choices:
            choices = [(source, target) for source in sorted(edges, key=_node_text)
                       for target, _label in edges[source]]
        if not choices:
            raise GraphError("cannot inject edge: graph has no edges")
        source_node, target_node = choices[0]
        label = {"injected": True}
        edges[target_node].append((source_node, label))
        injected = {"from": _node_text(target_node),
                    "to": _node_text(source_node)}

    return Report(config, states, dict(edges), total_classes, uncovered,
                  closure, injected, class_tables, sorted(skipped),
                  classes_before if refine else None, shape_skipped)


@dataclass(frozen=True)
class Domain:
    """The finite state space one configuration's graph is built over.

    A mutation result is a state only when the value is both *declared* (the
    coverage contract `spec/graph.md` states: widening into an undeclared
    width is `outside`, not `no-rule`) and *classable* (the opcode's axes have
    a class for it).  Both conditions live here so `build` and the closure
    audit cannot disagree about what "outside" means.
    """

    declared: frozenset
    tables: dict

    def successor(self, opcode, types, mem, imm, changed_idx, new_type):
        """State key for one mutation result, or None when it is outside."""
        if new_type not in self.declared:
            return None
        target = list(types)
        target[changed_idx] = new_type
        table = self.tables.get(opcode)
        if table is None:
            return None
        return _class_key(table, opcode, tuple(target), mem, imm)


def _class_key(tables, opcode, types, mem, imms=None):
    """State key for concrete types/mem/imm, or None when outside the axes."""
    type_classes, mem_classes, imm_classes = tables
    if len(types) != len(type_classes):
        return None
    try:
        classes = tuple(type_classes[i].class_of[types[i]]
                        for i in range(len(types)))
        mc = mem_classes.class_of[mem] if mem_classes else None
        if imm_classes:
            ic = imm_classes.class_of[tuple(imms or ())]
        else:
            ic = None
    except (KeyError, TypeError):
        return None
    if imm_classes and ic is None:
        return None
    return _state_key(opcode, classes, mc, ic)


def _state_members(state):
    """Concrete (types, mem, imm) members of one state, expanded on demand."""
    pools = state["pools"]
    mem_pool = state["mem_pool"] or [None]
    imm_pool = state.get("imm_pool") or [None]
    opcode = state["key"][0]
    for types in itertools.product(*pools):
        # A concrete member the MIR verifier rejects is not a query the
        # legalizer can be asked; auditing it would invent a closure violation.
        if not AN.type_shape_ok(opcode, types):
            continue
        for mem in mem_pool:
            for imm in imm_pool:
                yield types, mem, imm


def oracle_check(report, oracle_path, evaluator, extended):
    result = {"total": 0, "matched": 0, "agree": 0, "disagree": 0,
              "uncovered": 0, "unaskable": 0, "errors": 0, "first": None}
    collapse = (lambda t: t) if extended else E.collapse_extended
    rows, _errors = jsonl_codec.read_rows(oracle_path, strict=True)
    for row in rows:
        query = row.raw
        config, name, row_types, row_mem, row_imms = row.key
        if config != report.config:
            continue
        result["total"] += 1
        types = tuple(collapse(value) for value in row_types)
        mem = (None if row_mem is None
               else (collapse(row_mem[0]),) + tuple(row_mem[1:]))
        imms = tuple(row_imms)
        tables = (report.class_tables or {}).get(name)
        key = (_class_key(tables, name, types, mem, imms)
               if tables else None)
        if key is None or key not in report.states:
            # A dump point whose shape no MIR can hold is not a graph
            # gap: `shape` already dropped it on purpose.  Keep the two
            # buckets apart so `uncovered` still means "reachable point
            # the graph failed to build".
            if not AN.type_shape_ok(name, types):
                result["unaskable"] += 1
            else:
                result["uncovered"] += 1
            continue
        result["matched"] += 1
        mems = ([] if mem is None
                else [E.MemDesc(mem[0], mem[1], mem[2], mem[3])])
        try:
            action, type_idx, new_type = E.evaluate(
                evaluator, report.config, name, list(types), mems, imms)
            want = query.get("new_type", "LLT_invalid")
            got = "LLT_invalid" if new_type == ("invalid",) else _type_text(new_type)
            if (action, type_idx, got) == (query.get("action"),
                                           query.get("type_idx", 0), want):
                result["agree"] += 1
            else:
                result["disagree"] += 1
                if result["first"] is None:
                    result["first"] = {"query": query, "got": [action, type_idx, got]}
        except Exception as exc:
            result["errors"] += 1
            if result["first"] is None:
                result["first"] = {"query": query, "error": str(exc)}
    return result


def _oracle_inputs(path, configs, extended):
    """Read optional oracle points only to make their states addressable."""
    types, mems, arities = set(), set(), {}
    wanted = set(configs)
    rows, _errors = jsonl_codec.read_rows(path, strict=True)
    for row in rows:
        config, name, row_types, _mem, _imms = row.key
        if config not in wanted:
            continue
        arities[name] = max(arities.get(name, 0), len(row_types))
        for value in row_types:
            types.add(value if extended else E.collapse_extended(value))
        query = row.raw
        if query.get("mem") is not None:
            m = query["mem"]
            mems.add((m[0], int(m[1]))
                     + ((m[2], m[3]) if len(m) >= 4
                        else ("NotAtomic", "NotAtomic")))
    return (sorted(types, key=_type_text), sorted(mems), arities)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gisel graph",
                                     description="find cycles in the legalizer quotient graph")
    parser.add_argument("source")
    parser.add_argument("--emit", default="core", choices=("core",),
                        help="graph input normal form (only core is supported)")
    parser.add_argument("--features")
    parser.add_argument("--config", action="append", dest="configs")
    parser.add_argument("--pointer-width", type=int, default=64)
    parser.add_argument("--axes", help="axis profile JSON (analysis only)")
    parser.add_argument("--oracle", help="check matching points in an oracle JSONL")
    parser.add_argument("--inject-edge", action="store_true")
    parser.add_argument("--check-closure", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="audit that every class member lands in one "
                             "successor class; use --no-check-closure to "
                             "skip")
    parser.add_argument("--refine", action="store_true",
                        help="split classes until a class has one "
                             "successor class (opt-in; changes the atom)")
    parser.add_argument("--max-states", type=int, default=None,
                        help="stop with rc=2 after N states (deterministic "
                             "scale guard; default: no limit)")
    parser.add_argument("--progress", action="store_true",
                        help="print per-ruleset progress on stderr")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        axis_profile = axesmod.load(args.axes) if args.axes else None
        doc, features, axis_profile = AN.session(
            args.source, features=args.features, configs=args.configs,
            axes=axis_profile)
        if not features.table:
            raise GraphError("no configurations selected")
        if axis_profile is not None:
            state = axis_profile.profile("graph").get("state")
            if state is not None and set(state) != {"types", "mem"}:
                raise axesmod.AxisError(
                    "%s: profiles.graph.state: only ['types', 'mem'] is "
                    "implemented in this version" % axis_profile.path)
        oracle_types = oracle_mems = ()
        oracle_arities = {}
        if args.oracle:
            # The oracle is not semantic input.  Its points only extend the
            # finite observation domain so the alignment check can address
            # every dumped boundary query.
            oracle_types, oracle_mems, oracle_arities = _oracle_inputs(
                args.oracle, features.table, True)
        reports = []
        for config in sorted(features.table):
            extended = E.Evaluator(doc, features).extended(config)
            config_oracle_types = []
            for value in oracle_types:
                config_oracle_types.append(value if extended
                                           else E.collapse_extended(value))
            width = (axis_profile.pointer_width(config, args.pointer_width)
                     if axis_profile is not None else args.pointer_width)
            report = build(args.source, config, features,
                           pointer_width=width,
                           inject_edge=args.inject_edge,
                           check_closure=args.check_closure,
                           refine=args.refine,
                           extra_types=config_oracle_types,
                           extra_mems=oracle_mems,
                           arity_overrides=oracle_arities,
                           progress=args.progress or sys.stderr.isatty(),
                           axis_profile=axis_profile,
                           max_states=args.max_states)
            if args.oracle:
                evaluator = E.Evaluator(doc, features)
                report.oracle = oracle_check(report, args.oracle, evaluator,
                                             evaluator.extended(config))
            reports.append(report)
    except GraphError as exc:
        if args.json:
            payload = {"error": exc.kind or "graph_error",
                       "message": str(exc)}
            if exc.kind == "state_limit":
                payload["outcome"] = "unsupported_scale"
            payload.update(exc.detail)
            print(json.dumps(payload, sort_keys=True))
        else:
            print("gisel graph: %s" % exc, file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError,
            GraphError, axesmod.AxisError) as exc:
        print("gisel graph: %s" % exc, file=sys.stderr)
        return 2

    public = [r.public() for r in reports]
    for report, output in zip(reports, public):
        if args.oracle:
            output["oracle"] = getattr(report, "oracle")
        if args.json:
            continue
        print("config      : %s" % output["config"])
        print("states      : %d" % output["states"])
        print("edges       : %d" % output["edges"])
        print("classes     : %d" % output["classes"])
        if "classes_before" in output:
            print("refined     : %d -> %d class(es)"
                  % (output["classes_before"], output["classes"]))
        print("outcomes    : %s" % output["outcomes"])
        print("terminal    : %s" % output["terminal"])
        print("opaque      : %d" % output["opaque"])
        print("outside     : %d" % output["outside"])
        print("shape       : %d" % output["shape"])
        print("cycles      : %d" % output["cycles"])
        if output["uncovered"]:
            print("uncovered   : %s" % sorted(set(output["uncovered"])))
        if output.get("skipped"):
            print("skipped     : %s" % output["skipped"])
        if output["closure"]["checked"]:
            closure = output["closure"]
            status = "ok" if closure["ok"] else "FAILED"
            print("closure     : %s (%d violation(s), %d shown)"
                  % (status, closure.get("count", len(closure["violations"])),
                     min(3, len(closure["violations"]))))
            kinds = closure.get("kinds") or {}
            if kinds:
                print("  closure kinds: partition=%d outside=%d"
                      % (kinds.get("partition", 0), kinds.get("outside", 0)))
            for violation in closure["violations"][:3]:
                print("  closure: %s" % _violation_text(violation))
            if not closure["ok"] and not args.refine:
                print("  closure: successor is not a function of the state "
                      "above; cycles=0 is conditional.  Use --refine to split "
                      "the partition, or --no-check-closure to skip the audit.")
        else:
            print("closure     : not checked (--no-check-closure; cycles=0 is "
                  "conditional on the class partition being closed)")
        if args.oracle:
            print("oracle      : %s" % output["oracle"])
        for cycle in output["cycle_samples"]:
            print("   %s" % " -> ".join(cycle[:6]))
        print()
    if args.json:
        print(json.dumps({"reports": public}, indent=1, sort_keys=True))
    bad = any(output["cycles"] for output in public)
    bad = bad or any(not output["closure"]["ok"] for output in public)
    if args.oracle:
        bad = bad or any(getattr(r, "oracle")["disagree"] or
                         getattr(r, "oracle")["errors"] or
                         getattr(r, "oracle")["uncovered"] for r in reports)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
