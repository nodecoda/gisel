#!/usr/bin/env python3
"""Generate test cases from the Core IR document the DSL emits.

The generator has no second model: `gisel cases` parses the `.gisel`, runs the
same canonicalisation as `gen --emit=core`, and derives every case from that
schema-0.4 document.  Three kinds of case, each with a contract:

``equivalence``
    One representative per ``(config, rule)``: a query the rule answers and
    every earlier rule in the rule set declines.  Rules that are satisfiable
    but never first are reported as *shadowed*; rules no configuration can
    satisfy are *unexercised*.  A rule with no witness is a hole in the rule
    set, not a gap in the sample.

``boundary``
    A value adjacent to a threshold the rules compare against.  Boundaries are
    found by mutating an equivalence witness to ``N-1`` / ``N+1`` (bits, lane
    count, or a memory descriptor's size/alignment) and keeping the mutation
    only when the answer actually changes.  Every emitted boundary is therefore
    a real transition; values that merely sit next to a literal are not emitted.

``outside``
    A well-formed query no rule answers (the evaluator falls back to
    ``Unsupported``): a point in the domain but outside every rule's class.

The differential contract is deliberately narrow: ``--against`` compares only
the generated queries that also occur in the oracle dump.  Queries with no
oracle point are reported as *uncovered*, never as passes.  ``agree ==
covered == 0 disagreements`` is the subset statement; it says nothing about
the uncovered ones.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import ast as A
from . import eval as E
from .backend import core_json

KINDS = ("equivalence", "boundary", "outside")

# Values that exercise each LLT kind even when a rule set names none of them.
# Ordered so a rule with no literals still gets an ordinary scalar witness
# before the exotic shapes; the list is a fallback, not a preference.
_SENTINELS = (
    "s32", "s64", "s8", "s16", "s128", "s1", "s3", "s7", "s24", "s31",
    "s33", "s63", "s65", "v4s32", "v2s64", "v16s8", "v1s8", "v3s32",
    "nxv4s32", "p0:64", "p0:32", "p0:128", "p0:*", "f16", "f32", "f64",
    "bf16",
)
_POW2 = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512)
_SENTINEL_LLTS = tuple(E.parse_case_llt(s) for s in _SENTINELS)


# ---- LLT text and mutation ----------------------------------------------

def llt_text(t) -> str:
    """The Core IR spelling, accepted by :func:`eval.parse_case_llt`."""
    if t[0] == "invalid":
        return "LLT_invalid"
    if t[0] == "bf16":
        return "bf16"
    if t[0] == "pointer":
        return "p%d:%s" % (t[1], t[2])
    if t[0] == "vector":
        head = "nxv" if t[2] else "v"
        return head + str(t[1]) + llt_text(t[3])
    return {"scalar": "s", "integer": "i", "float": "f"}[t[0]] + str(t[1])


def _scalar_bits(t):
    if t[0] in ("scalar", "integer", "float"):
        return t[1]
    if t[0] == "bf16":
        return 16
    if t[0] == "pointer" and t[2] != "*":
        return t[2]
    return None


def _lanes(t):
    return t[1] if t[0] == "vector" else None


def _resize_bits(t, bits):
    """Same shape, scalar/element/pointer width set to ``bits``."""
    if bits is None or bits <= 0:
        return None
    if t[0] in ("scalar", "integer"):
        return (t[0], bits)
    if t[0] == "float":
        return ("float", bits)
    if t[0] == "pointer":
        return ("pointer", t[1], bits)
    if t[0] == "vector":
        elem = _resize_bits(t[3], bits)
        return None if elem is None else ("vector", t[1], t[2], elem)
    return None


def _relane(t, lanes):
    if t[0] != "vector" or lanes <= 0:
        return None
    return ("vector", lanes, t[2], t[3])


def _mutate(t, dim, n):
    if dim == "bits":
        return _resize_bits(t, n)
    if dim == "bytes":
        return _resize_bits(t, 8 * n)
    if dim == "lanes":
        return _relane(t, n)
    return None


def _neighbours(t):
    """Off-by-one spellings around one LLT, never used as a class witness."""
    out = set()
    bits = _scalar_bits(t)
    if bits is not None:
        if bits > 1:
            out.add(_resize_bits(t, bits - 1))
        out.add(_resize_bits(t, bits + 1))
    lanes = _lanes(t)
    if lanes is not None:
        if lanes > 1:
            out.add(_relane(t, lanes - 1))
        out.add(_relane(t, lanes + 1))
        out.add((t[0], t[1], not t[2], t[3]))
    if t[0] == "bf16":
        out.add(("float", 16))
    return {x for x in out if x is not None and x != t}


# ---- predicate inspection ------------------------------------------------

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
    uses_mem: bool = False
    slots: set = field(default_factory=set)


def _add_literal(info, slot, text):
    try:
        t = E.parse_case_llt(text)
    except E.EvalError:
        return
    info.literals.setdefault(slot, set()).add(t)
    bits = _scalar_bits(t)
    if bits:
        info.thresholds.setdefault(slot, set()).add(("bits", bits))
    lanes = _lanes(t)
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

    if k == "in":
        lhs, rhs = node["args"]
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
            slot = _slot_of(expr)
            dim = _dim_of(expr)
            if slot is not None and dim is not None:
                info.slots.add(slot)
                info.thresholds.setdefault(slot, set()).add((dim, other["value"]))
    elif k == "leaf" and node.get("name") == "isPow2":
        slot = _slot_of(node)
        if slot is not None:
            info.slots.add(slot)
            for n in _POW2:
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


# ---- case generation -----------------------------------------------------

@dataclass(frozen=True)
class Case:
    config: str
    opcode: str
    types: tuple
    mem: tuple | None
    kind: str
    ruleset: str
    rule: int | None
    reason: str

    def key(self):
        return (self.config, self.opcode, self.types, self.mem)

    def query(self):
        q = {"config": self.config, "name": self.opcode,
             "types": list(self.types),
             "mem": list(self.mem) if self.mem else None,
             "imms": []}
        q.update({"kind": self.kind, "ruleset": self.ruleset,
                  "rule": self.rule, "reason": self.reason})
        return q


@dataclass
class Generation:
    cases: list
    stats: dict


def _parse(types):
    return [E.parse_case_llt(t) for t in types]


def _mems(case):
    if case.mem is None:
        return []
    return [E.MemDesc(E.parse_case_llt(case.mem[0]), case.mem[1])]


def _fire(evaluator, config, opcode, types, mems):
    """``(ruleset_index, rule_index, action, type_idx, new_type)`` or None."""
    for rs_idx in evaluator.by_opcode.get(opcode, []):
        for ri, rule in enumerate(evaluator.rulesets[rs_idx]["rules"]):
            if not evaluator.bool_value(rule["predicate"], types, mems,
                                        config, ()):
                continue
            ok, new_type = E.shim_guard_and_newtype(
                rule.get("op"), rule.get("on"), rule.get("to"),
                types, mems, evaluator, config, ())
            if ok:
                return (rs_idx, ri, rule["action"],
                        rule.get("type_idx", 0), new_type)
    return None


def outcome(evaluator, case):
    """The firing rule and answer for one generated case.

    ``(ruleset_index, rule_index, action, type_idx, new_type)``, ``None`` when
    no rule matches, ``"error"`` when the LLT shape cannot be evaluated.
    """
    return _try_fire(evaluator, case)


def _outcome(res):
    """The answer triple, or ``None`` for the Unsupported fall-back."""
    return None if res is None else res[1:]


def _try_fire(evaluator, case):
    """The firing rule, ``None`` when no rule matches, ``"error"`` on bad LLTs."""
    try:
        return _fire(evaluator, case.config, case.opcode,
                     _parse(case.types), _mems(case))
    except (E.EvalError, IndexError, KeyError, TypeError, ValueError,
            AssertionError):
        return "error"


def _candidates(infos, nslots, cap):
    """Per-slot candidate values: literals, their neighbours, sentinels."""
    per = []
    for i in range(nslots):
        lit = set()
        for info in infos:
            lit |= info.literals.get(i, set())
        if not lit and not any(i in info.slots for info in infos):
            per.append([E.parse_case_llt("s32")])
            continue
        cand = set(lit)
        for t in lit:
            cand |= _neighbours(t)
        cand |= set(_SENTINEL_LLTS)
        ordered = sorted(lit, key=llt_text)
        ordered += [t for t in sorted({x for t in lit for x in _neighbours(t)},
                                      key=llt_text) if t not in ordered]
        ordered += [t for t in _SENTINEL_LLTS if t not in ordered]
        per.append(ordered[:max(cap, len(lit))])
    # Keep the cartesian product bounded without dropping any literal.
    while _product_size(per) > 20000:
        widest = max(range(len(per)), key=lambda i: len(per[i]))
        if len(per[widest]) <= 1:
            break
        per[widest] = per[widest][:-1]
    return per


def _product_size(per):
    n = 1
    for values in per:
        n *= len(values)
    return n


def _defaults(per):
    return tuple(values[0] if values else E.parse_case_llt("s32")
                 for values in per)


def _mem_candidates(infos):
    entries = []
    for info in infos:
        entries.extend(info.mem_entries)
    out = []
    seen = set()
    for t0, t1, mty, align in entries:
        key = (t0, t1, mty, align)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _pad(types, nslots, default):
    out = list(types[:nslots])
    while len(out) < nslots:
        out.append(default[len(out)] if len(out) < len(default)
                   else E.parse_case_llt("s32"))
    return tuple(out)


def _queries(per, default, mem_entries, uses_mem):
    """Base queries: every sampled type tuple, plus one per memory descriptor."""
    out = []
    if uses_mem:
        for t0, t1, mty, align in mem_entries:
            types = _pad([E.parse_case_llt(x) for x in (t0, t1)], len(per),
                         default)
            out.append((types, (mty, int(align))))
    out.extend((types, None) for types in itertools.product(*per))
    return out


def generate(doc, features, *, configs=None, max_slot_values=16,
             max_outside=2, max_boundary_per_rule=24,
             max_witnesses_per_rule=4) -> Generation:
    """Derive the three case kinds from one schema-0.4 document."""
    evaluator = E.Evaluator(doc, features)
    configs = list(configs) if configs else sorted(features.table)
    cases, seen = [], set()
    stats = {"configs": configs, "rulesets": 0, "opcodes": 0, "rules": 0,
             "witnessed": 0, "shadowed": 0, "unexercised": 0,
             "equivalence": 0, "boundary": 0, "outside": 0,
             "unwitnessed": []}

    def emit(case):
        if case.key() in seen:
            return False
        seen.add(case.key())
        cases.append(case)
        stats[case.kind] += 1
        return True

    for rs_idx, rs in enumerate(doc["rulesets"]):
        if not rs["opcodes"]:
            continue
        opcode = rs["opcodes"][0]
        nslots, infos = inspect_ruleset(rs)
        per = _candidates(infos, nslots, max_slot_values)
        default = _defaults(per)
        mem_entries = _mem_candidates(infos)
        uses_mem = any(info.uses_mem for info in infos)
        queries = _queries(per, default, mem_entries, uses_mem)

        stats["rulesets"] += 1
        stats["opcodes"] += len(rs["opcodes"])
        stats["rules"] += len(rs["rules"])

        # -- pass 1: which query is the first match for which rule -----------
        fires = {}          # (config, ri) -> [(types, mem, result)]
        for config in configs:
            for types, mem in queries:
                case = Case(config, opcode, tuple(llt_text(t) for t in types),
                            mem, "equivalence", rs["def"], None, "")
                res = _try_fire(evaluator, case)
                if not isinstance(res, tuple) or res[0] != rs_idx:
                    continue
                fires.setdefault((config, res[1]), []).append((types, mem, res))

        witnessed = sorted({ri for _, ri in fires})
        stats["witnessed"] += len(witnessed)

        # -- equivalence ---------------------------------------------------
        for (config, ri), bases in sorted(fires.items()):
            limit = max_witnesses_per_rule if infos[ri].uses_mem else 1
            for types, mem, _ in bases[:limit]:
                emit(Case(config, opcode,
                          tuple(llt_text(t) for t in types), mem,
                          "equivalence", rs["def"], ri,
                          "first match for rule %d%s"
                          % (ri, " (mem)" if mem else "")))

        # -- shadowed / unexercised ---------------------------------------
        unwitnessed = [ri for ri in range(len(rs["rules"]))
                       if ri not in witnessed]
        for ri in unwitnessed:
            stat = _satisfiable(evaluator, rs_idx, ri, rs, configs, infos,
                                per, default, mem_entries)
            stats["shadowed" if stat else "unexercised"] += 1
            if len(stats["unwitnessed"]) < 40:
                stats["unwitnessed"].append(
                    "%s#%d: %s" % (rs["def"], ri,
                                   "shadowed" if stat else "unexercised"))

        # -- boundary ------------------------------------------------------
        for config in configs:
            for ri in witnessed:
                limit = max_witnesses_per_rule if infos[ri].uses_mem else 1
                bases = fires.get((config, ri), [])[:limit]
                if not bases:
                    continue
                emitted = 0
                for types, mem, base in bases:
                    for slot in range(nslots):
                        for dim, n in sorted(infos[ri].thresholds.get(slot, ())):
                            for probe in (n - 1, n, n + 1):
                                mut = _mutate(types[slot], dim, probe)
                                if mut is None or mut == types[slot]:
                                    continue
                                vtypes = types[:slot] + (mut,) + types[slot + 1:]
                                case = Case(config, opcode,
                                            tuple(llt_text(t) for t in vtypes),
                                            mem, "boundary", rs["def"], ri,
                                            "%s %d -> %d" % (dim, n, probe))
                                res = _try_fire(evaluator, case)
                                if res == "error":
                                    continue
                                if _outcome(res) != base[1:] and emit(case):
                                    emitted += 1
                                if emitted >= max_boundary_per_rule:
                                    break
                            if emitted >= max_boundary_per_rule:
                                break
                        if emitted >= max_boundary_per_rule:
                            break
                    if mem is not None:
                        mty, align = mem
                        for probe, reason in (
                                (align - 1, "align %d -> %d" % (align, align - 1)),
                                (align + 1, "align %d -> %d" % (align, align + 1))):
                            case = Case(config, opcode,
                                        tuple(llt_text(t) for t in types),
                                        (mty, probe), "boundary", rs["def"], ri,
                                        reason)
                            res = _try_fire(evaluator, case)
                            if res != "error" and _outcome(res) != base[1:] and emit(case):
                                emitted += 1
                        mt = E.parse_case_llt(mty)
                        bits = _scalar_bits(mt)
                        if bits:
                            for probe in (bits - 1, bits + 1):
                                nmt = _resize_bits(mt, probe)
                                if nmt is None:
                                    continue
                                case = Case(config, opcode,
                                            tuple(llt_text(t) for t in types),
                                            (llt_text(nmt), align), "boundary",
                                            rs["def"], ri,
                                            "mem bits %d -> %d" % (bits, probe))
                                res = _try_fire(evaluator, case)
                                if (res != "error" and _outcome(res) != base[1:]
                                        and emit(case)):
                                    emitted += 1
                    if emitted >= max_boundary_per_rule:
                        break

        # -- outside -------------------------------------------------------
        probes = list(queries)
        if uses_mem:
            for mty, align in ((e[2], 0) for e in mem_entries[:4]):
                probes.insert(0, (_pad([E.parse_case_llt("s3"),
                                        E.parse_case_llt("p0:64")],
                                       nslots, default), (mty, align)))
        for config in configs:
            emitted = 0
            for types, mem in probes:
                case = Case(config, opcode, tuple(llt_text(t) for t in types),
                            mem, "outside", rs["def"], None, "no rule fires")
                if _try_fire(evaluator, case) is None and emit(case):
                    emitted += 1
                if emitted >= max_outside:
                    break

    stats["cases"] = len(cases)
    return Generation(cases, stats)


def _satisfiable(evaluator, rs_idx, ri, rs, configs, infos, per, default,
                 mem_entries):
    """Whether rule ``ri`` can fire *at all* under any supplied config."""
    rule = rs["rules"][ri]
    slots = sorted(infos[ri].slots) or [0]
    values = [per[s] if s < len(per) else [default[s]] for s in slots]
    mem_trials = [None]
    if infos[ri].uses_mem:
        mem_trials += [(mty, int(align)) for _, _, mty, align in mem_entries]
    for config in configs:
        for combo in itertools.product(*values):
            types = list(default)
            for s, t in zip(slots, combo):
                types[s] = t
            for mem in mem_trials:
                mems = ([E.MemDesc(E.parse_case_llt(mem[0]), mem[1])]
                        if mem else [])
                try:
                    if not evaluator.bool_value(rule["predicate"], types, mems,
                                                config, ()):
                        continue
                    ok, _ = E.shim_guard_and_newtype(
                        rule.get("op"), rule.get("on"), rule.get("to"),
                        types, mems, evaluator, config, ())
                except (E.EvalError, IndexError, KeyError, TypeError,
                        ValueError, AssertionError):
                    continue
                if ok:
                    return True
    return False


# ---- differential --------------------------------------------------------

@dataclass
class Diff:
    covered: int = 0
    agree: int = 0
    disagree: int = 0
    uncovered: int = 0
    errors: int = 0
    first: str | None = None


def _oracle_key(q):
    types = tuple(E.parse_case_llt(t) for t in q["types"])
    mem = None
    if q.get("mem"):
        mem = (E.parse_case_llt(q["mem"][0]), q["mem"][1])
    return (q["config"], q["name"], types, mem, tuple(q.get("imms") or []))


def index_oracle(path):
    index = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            index.setdefault(_oracle_key(q), q)
    return index


def differ(generation, doc, features, oracle_path):
    evaluator = E.Evaluator(doc, features)
    index = index_oracle(oracle_path)
    diff = Diff()
    for case in generation.cases:
        key = (case.config, case.opcode, tuple(_parse(case.types)),
               (E.parse_case_llt(case.mem[0]), case.mem[1]) if case.mem else None,
               ())
        want = index.get(key)
        if want is None:
            diff.uncovered += 1
            continue
        diff.covered += 1
        try:
            action, type_idx, new_type = E.evaluate(
                evaluator, case.config, case.opcode, _parse(case.types),
                _mems(case))
        except (E.EvalError, IndexError, KeyError, TypeError, ValueError) as e:
            diff.errors += 1
            if diff.first is None:
                diff.first = "ERROR %s: %s" % (key, e)
            continue
        want_type = E.parse_case_llt(want["new_type"]) if isinstance(
            want.get("new_type"), str) else ("invalid",)
        if (action == want["action"] and type_idx == want.get("type_idx", 0)
                and E.values_equal(new_type, want_type)):
            diff.agree += 1
        else:
            diff.disagree += 1
            if diff.first is None:
                diff.first = ("MISMATCH %s: ours=(%s,%s,%s) oracle=(%s,%s,%s)"
                              % (key, action, type_idx, E.fmt_oracle_llt(new_type),
                                 want["action"], want.get("type_idx", 0),
                                 want.get("new_type")))
    return diff


# ---- CLI -----------------------------------------------------------------

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


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="gisel cases",
        description="generate equivalence-class, boundary and outside cases")
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--features",
                    help="feature truth table (default: derive none/all/only-N)")
    ap.add_argument("--config", action="append", dest="configs",
                    help="limit to configs from --features (repeatable)")
    ap.add_argument("--against", help="oracle JSONL to differ against")
    ap.add_argument("--max-outside", type=int, default=2)
    ap.add_argument("--json", action="store_true", help="print stats as JSON")
    args = ap.parse_args(argv)

    doc = document(args.source)

    features = derive_features(doc, args.features, args.configs)
    if not features.table:
        print("cases: no configurations selected", file=sys.stderr)
        return 2
    generation = generate(doc, features, configs=sorted(features.table),
                          max_outside=args.max_outside)

    with open(args.out, "w") as f:
        for case in generation.cases:
            f.write(json.dumps(case.query(), sort_keys=True) + "\n")

    stats = dict(generation.stats)
    if args.against:
        diff = differ(generation, doc, features, args.against)
        stats["diff"] = diff.__dict__
        print("oracle: covered=%d agree=%d disagree=%d uncovered=%d errors=%d"
              % (diff.covered, diff.agree, diff.disagree, diff.uncovered,
                 diff.errors))
        if diff.first:
            print("first:", diff.first)
    if args.json:
        print(json.dumps(stats, indent=1, sort_keys=True))
    else:
        print("%s: cases=%d equivalence=%d boundary=%d outside=%d"
              % (args.out, stats["cases"], stats["equivalence"],
                 stats["boundary"], stats["outside"]))
        print("rules=%d witnessed=%d shadowed=%d unexercised=%d"
              % (stats["rules"], stats["witnessed"], stats["shadowed"],
                 stats["unexercised"]))
    if args.against and stats["diff"]["covered"] == 0:
        print("cases: no overlapping queries; check --features/--config "
              "spellings", file=sys.stderr)
        return 2
    if args.against and (stats["diff"]["disagree"] or stats["diff"]["errors"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
