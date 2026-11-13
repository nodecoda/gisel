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
the generated queries that also occur in an answer file.  Queries with no
answer are reported as *uncovered*, never as passes.  ``agree ==
covered == 0 disagreements`` is the subset statement; it says nothing about
the uncovered ones.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import dataclass, field

from . import axes as axesmod
from . import corpus as corpora
from . import answers as answer_file
from . import analysis
from . import eval as E
from . import jsonl as jsonl_codec
from . import llt as L
from . import output

# The analysis surface other verbs import; `cases` owns neither the parser nor
# the rule projection, it only consumes them.
document = analysis.document
derive_features = analysis.derive_features
session = analysis.session
inspect_rule = analysis.inspect_rule
inspect_ruleset = analysis.inspect_ruleset
imm_candidates = analysis.imm_candidates
type_value_spellings = analysis.type_value_spellings
RuleInfo = analysis.RuleInfo

KINDS = ("equivalence", "boundary", "outside")
# The generator trims the cartesian product; `graph` deliberately uses a wider
# cap.  Two policies, two names -- do not make them equal without re-recording
# every frozen artifact.
DEFAULT_MAX_SLOT_VALUES = 16



# ---- LLT text and mutation ----------------------------------------------

llt_text = L.spell





# ---- predicate inspection ------------------------------------------------

def _mem_shape_ok(case, mem_opcodes):
    """A memory-carrying query has to look like one the IR can produce.

    Two contracts the backends state with `assert` before looking at a rule:

      * an opcode whose rules read `MMODescrs[0]` always carries one;
      * the memory size fits the value slot (`QueryMemSize <= Size`).
    """
    if case.opcode not in mem_opcodes:
        return True
    if case.mem is None:
        return False
    types = _parse(case.types)
    value_bits = L.scalar_bits(types[0])
    mem_bits = L.scalar_bits(E.parse_case_llt(case.mem[0]))
    if value_bits and mem_bits and mem_bits > value_bits:
        return False
    return True


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
    imms: tuple = ()

    def __post_init__(self):
        # mem is kept as (mty, align, ordering, failure_ordering); the two
        # ordering slots are appended for every legacy two-element input.
        if self.mem is not None and len(self.mem) == 2:
            object.__setattr__(
                self, "mem",
                (self.mem[0], int(self.mem[1]), "NotAtomic", "NotAtomic"))

    def key(self):
        return (self.config, self.opcode, self.types, self.mem, self.imms)

    def query(self):
        mem = None
        if self.mem:
            if tuple(self.mem[2:4]) == ("NotAtomic", "NotAtomic"):
                mem = list(self.mem[:2])
            else:
                mem = list(self.mem)
        q = {"config": self.config, "name": self.opcode,
             "types": list(self.types),
             "mem": mem,
             "imms": list(self.imms)}
        q.update({"kind": self.kind, "ruleset": self.ruleset,
                  "rule": self.rule, "reason": self.reason})
        return q


@dataclass
class Generation:
    cases: list
    stats: dict


def _parse(types):
    return [E.parse_case_llt(t) for t in types]


def mem_point(value):
    """Normalize a query ``mem`` value to the internal four-tuple."""
    if value is None:
        return None
    if len(value) >= 4:
        return (value[0], int(value[1]), value[2], value[3])
    return (value[0], int(value[1]), "NotAtomic", "NotAtomic")


def _mems(case):
    if case.mem is None:
        return []
    mty, align, ordering, failure = mem_point(case.mem)
    return [E.MemDesc(E.parse_case_llt(mty), align, ordering, failure)]


def _fire(evaluator, config, opcode, types, mems, imms=()):
    """``(ruleset_index, rule_index, action, type_idx, new_type)`` or None."""
    for rs_idx in evaluator.by_opcode.get(opcode, []):
        for ri, rule in enumerate(evaluator.rulesets[rs_idx]["rules"]):
            if not evaluator.bool_value(rule["predicate"], types, mems,
                                        config, imms):
                continue
            ok, new_type = E.shim_guard_and_newtype(
                rule.get("op"), rule.get("on"), rule.get("to"),
                types, mems, evaluator, config, imms)
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
                     _parse(case.types), _mems(case), case.imms)
    except (E.EvalError, IndexError, KeyError, TypeError, ValueError,
            AssertionError):
        return "error"


# The shape filter is a claim about LLVM (the MIR verifier), not about
# a target's rule set, so it lives in `analysis` next to the rest of the
# rule projection.  Re-exported here for the callers that already use it.
type_shape_ok = analysis.type_shape_ok
_candidate_key = analysis._candidate_key
_candidates = analysis.candidates
_mem_candidates = analysis.mem_candidates


def _declares_scalable(doc):
    """Whether the document's declared domain contains a scalable vector.

    X86 declares no scalable type, so a `nxv*` query is not a question its
    legalizer can be asked: `LLT::getNumElements()` aborts on it.  Generating
    one turns a shape filter into a crash in the official runner.
    """
    for text in doc.get("domain", {}).get("types", []):
        for spelling in type_value_spellings(text):
            try:
                t = E.parse_case_llt(spelling)
            except E.EvalError:
                continue
            if t[0] == "vector" and t[2]:
                return True
    return False




# Opcodes whose slots are related by a type shape (`type_shape_ok`).  Only for
# these is it worth crossing one slot's candidates into another: elsewhere the
# slots really are independent axes.
_SHAPED_OPCODES = frozenset({
    "G_MERGE_VALUES", "G_UNMERGE_VALUES", "G_CONCAT_VECTORS",
    "G_SHUFFLE_VECTOR", "G_FPTOSI_SAT", "G_FPTOUI_SAT",
})


def _shape_candidates(opcode, per):
    """Let a shaped opcode's slots reach each other's values.

    The candidate sets are built one slot at a time, and a slot the rules never
    name falls back to the domain order, which for a shaped opcode may hold
    nothing that pairs with the other slots -- then every product point is
    filtered out and the ruleset loses all its witnesses.  Mirroring the values
    (append-only, so nothing that already worked is dropped) keeps at least the
    pairable combinations inside the product.
    """
    if opcode not in _SHAPED_OPCODES or len(per) < 2:
        return per
    everything = []
    for values in per:
        for value in values:
            if value not in everything:
                everything.append(value)
    out = [list(values) for values in per]
    for slot in range(len(out)):
        for value in everything:
            if value not in out[slot]:
                out[slot].append(value)
    return out




def _defaults(per):
    return tuple(values[0] if values else E.parse_case_llt("s32")
                 for values in per)




def _pad(types, nslots, default):
    out = list(types[:nslots])
    while len(out) < nslots:
        out.append(default[len(out)] if len(out) < len(default)
                   else E.parse_case_llt("s32"))
    return tuple(out)


def _queries(per, default, mem_entries, uses_mem, imm_tuples=(()),
             mem_pairs=(("NotAtomic", "NotAtomic"),), opcode=""):
    """Base queries: sampled type tuples, plus memory-descriptor queries.

    The matched descriptor (the row's own t0/t1) is what ``inMemDesc`` asks
    for.  A descriptor is also crossed with a few unrelated type tuples: some
    rules compare the slot against ``memTy`` (X86_STORE's mismatch rule), and
    that edge only exists when the two are not taken from the same row.
    """
    out = []
    dropped = 0
    if uses_mem:
        for t0, t1, mty, align in mem_entries:
            types = _pad([E.parse_case_llt(x) for x in (t0, t1)], len(per),
                         default)
            if not type_shape_ok(opcode, types):
                dropped += 1
                continue
            for ordering, failure in mem_pairs:
                for imms in imm_tuples:
                    out.append((types, (mty, int(align), ordering, failure),
                                imms))
        cross = list(itertools.islice(itertools.product(*per), 4))
        for _, _, mty, align in mem_entries[:8]:
            for types in cross:
                for ordering, failure in mem_pairs:
                    for imms in imm_tuples:
                        out.append((types,
                                    (mty, int(align), ordering, failure),
                                    imms))
    for types in itertools.product(*per):
        if not type_shape_ok(opcode, types):
            dropped += 1
            continue
        for imms in imm_tuples:
            out.append((types, None, imms))
    return out, dropped


def generate(doc, features, *, configs=None,
             max_slot_values=DEFAULT_MAX_SLOT_VALUES,
             max_outside=2, max_boundary_per_rule=24,
             max_witnesses_per_rule=4, axes=None,
             only_rulesets=None) -> Generation:
    """Derive the three case kinds from one schema-0.4 document.

    ``only_rulesets`` limits the run to the named ruleset defs (or their
    opcodes).  A large target is generated in chunks; an unknown name is an
    error rather than an empty file, because a typo would otherwise look like
    "this ruleset has no queries".
    """
    wanted = set(only_rulesets or ())
    if wanted:
        known = {rs.get("def") for rs in doc["rulesets"]}
        known |= {op for rs in doc["rulesets"] for op in rs["opcodes"]}
        missing = sorted(wanted - known)
        if missing:
            raise ValueError("unknown ruleset(s): %s" % ", ".join(missing))
    evaluator = E.Evaluator(doc, features)
    configs = list(configs) if configs else sorted(features.table)
    cases, seen = [], set()
    stats = {"configs": configs, "rulesets": 0, "opcodes": 0, "rules": 0,
             "witnessed": 0, "shadowed": 0, "unexercised": 0,
             "equivalence": 0, "boundary": 0, "outside": 0,
             "ill_formed": 0, "ill_formed_opcodes": {},
             # `max_slot_values` is a soft budget: every literal and its
             # neighbours survive, so a slot can be wider than the budget.
             # Report both so a reader never mistakes 16 for a hard cap.
             "slot_budget": max_slot_values,
             "candidate_max": 0, "candidate_over_budget": 0,
             "unwitnessed": []}

    # Opcodes whose rules read a memory descriptor.  A query for one of them
    # without a descriptor is not a legalizer query at all: the backends read
    # `MMODescrs[0]` unconditionally, so an empty array asserts before any rule
    # runs.
    mem_opcodes = {rs["opcodes"][0] for rs in doc["rulesets"]
                   if rs["opcodes"]
                   and any(i.uses_mem for i in inspect_ruleset(rs)[1])}

    def emit(case):
        if case.key() in seen:
            return False
        # Every path ends here, so this is the one place that has to hold:
        # `_queries` filters early to save evaluator work, but boundary and
        # witness probes build types directly.
        if (not type_shape_ok(case.opcode, _parse(case.types))
                or not _mem_shape_ok(case, mem_opcodes)):
            stats["ill_formed"] += 1
            stats["ill_formed_opcodes"][case.opcode] = (
                stats["ill_formed_opcodes"].get(case.opcode, 0) + 1)
            return False
        seen.add(case.key())
        cases.append(case)
        stats[case.kind] += 1
        return True

    scalable_ok = _declares_scalable(doc)
    for rs_idx, rs in enumerate(doc["rulesets"]):
        if not rs["opcodes"]:
            continue
        if wanted and rs.get("def") not in wanted \
                and not (wanted & set(rs["opcodes"])):
            continue
        opcode = rs["opcodes"][0]
        nslots, infos = inspect_ruleset(rs)
        domain = [E.parse_case_llt(t) for t in doc["domain"]["types"]]
        per = _shape_candidates(opcode, _candidates(
            infos, nslots, max_slot_values, domain, scalable_ok))
        if axes is not None:
            per = [axes.apply_types(slot) for slot in per]
        widest = max((len(values) for values in per), default=0)
        stats["candidate_max"] = max(stats["candidate_max"], widest)
        if widest > max_slot_values:
            stats["candidate_over_budget"] += 1
        default = _defaults(per)
        mem_entries = _mem_candidates(infos)
        if axes is not None:
            mem_entries = axes.apply_mems(mem_entries)
        uses_mem = any(info.uses_mem for info in infos)
        uses_ordering = any(info.uses_ordering for info in infos)
        mem_pairs = (axes.ordering_pairs()
                     if (axes is not None and uses_ordering)
                     else [("NotAtomic", "NotAtomic")])
        imm_axis = imm_candidates(infos, axes)
        imm_tuples = analysis.imm_tuples(imm_axis)
        queries, dropped = _queries(per, default, mem_entries, uses_mem,
                                    imm_tuples, mem_pairs, opcode)
        stats["ill_formed"] += dropped
        if dropped:
            stats["ill_formed_opcodes"][opcode] = (
                stats["ill_formed_opcodes"].get(opcode, 0) + dropped)

        stats["rulesets"] += 1
        stats["opcodes"] += len(rs["opcodes"])
        stats["rules"] += len(rs["rules"])

        # -- pass 1: which query is the first match for which rule -----------
        fires = {}          # (config, ri) -> [(types, mem, imms, result)]
        for config in configs:
            for types, mem, imms in queries:
                case = Case(config, opcode, tuple(llt_text(t) for t in types),
                            mem, "equivalence", rs["def"], None, "",
                            imms=imms)
                res = _try_fire(evaluator, case)
                if not isinstance(res, tuple) or res[0] != rs_idx:
                    continue
                fires.setdefault((config, res[1]), []).append(
                    (types, mem, imms, res))

        witnessed = sorted({ri for _, ri in fires})
        stats["witnessed"] += len(witnessed)

        # -- equivalence ---------------------------------------------------
        for (config, ri), bases in sorted(fires.items()):
            limit = max_witnesses_per_rule if infos[ri].uses_mem else 1
            for types, mem, imms, _ in bases[:limit]:
                emit(Case(config, opcode,
                          tuple(llt_text(t) for t in types), mem,
                          "equivalence", rs["def"], ri,
                          "first match for rule %d%s"
                          % (ri, " (mem)" if mem else ""), imms=imms))

        # -- shadowed / unexercised ---------------------------------------
        unwitnessed = [ri for ri in range(len(rs["rules"]))
                       if ri not in witnessed]
        for ri in unwitnessed:
            found = _rule_witness(evaluator, rs_idx, ri, rs, configs, infos,
                                  default, mem_entries, imm_tuples, mem_pairs,
                                  scalable_ok, per)
            if found is not None:
                config, types, mem, imms, res = found
                if emit(Case(config, opcode,
                             tuple(llt_text(x) for x in types), mem,
                             "equivalence", rs["def"], ri,
                             "first match for rule %d (directed)" % ri,
                             imms=imms)):
                    stats["witnessed"] += 1
                    witnessed.append(ri)
                    fires[(config, ri)] = [(tuple(types), mem, imms, res)]
                    continue
            stat = _satisfiable(evaluator, rs_idx, ri, rs, configs, infos,
                                per, default, mem_entries, imm_tuples,
                                mem_pairs)
            stats["shadowed" if stat else "unexercised"] += 1
            if len(stats["unwitnessed"]) < 200:
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
                for types, mem, imms, base in bases:
                    for slot in range(nslots):
                        for dim, n in sorted(infos[ri].thresholds.get(slot, ())):
                            for probe in (n - 1, n, n + 1):
                                mut = L.mutate(types[slot], dim, probe)
                                if mut is None or mut == types[slot]:
                                    continue
                                vtypes = types[:slot] + (mut,) + types[slot + 1:]
                                case = Case(config, opcode,
                                            tuple(llt_text(t) for t in vtypes),
                                            mem, "boundary", rs["def"], ri,
                                            "%s %d -> %d" % (dim, n, probe),
                                            imms=imms)
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
                        mty, align, ordering, failure = mem
                        # An MMO's alignment is a power of two (`Align`), and
                        # upstream asserts on anything else before it even looks
                        # at the rule.  Probe the neighbouring power of two, not
                        # `align +/- 1`, so the question stays a legal query.
                        probes = {max(8, align // 2), align * 2}
                        for probe in sorted(probes):
                            if probe == align:
                                continue
                            reason = "align %d -> %d" % (align, probe)
                            case = Case(config, opcode,
                                        tuple(llt_text(t) for t in types),
                                        (mty, probe, ordering, failure),
                                        "boundary", rs["def"], ri,
                                        reason, imms=imms)
                            res = _try_fire(evaluator, case)
                            if (res != "error" and _outcome(res) != base[1:]
                                    and emit(case)):
                                emitted += 1
                        mt = E.parse_case_llt(mty)
                        bits = L.scalar_bits(mt)
                        if bits:
                            for probe in (bits - 1, bits + 1):
                                nmt = L.resize_bits(mt, probe)
                                if nmt is None:
                                    continue
                                case = Case(config, opcode,
                                            tuple(llt_text(t) for t in types),
                                            (llt_text(nmt), align, ordering,
                                             failure), "boundary",
                                            rs["def"], ri,
                                            "mem bits %d -> %d" % (bits, probe),
                                            imms=imms)
                                res = _try_fire(evaluator, case)
                                if (res != "error" and _outcome(res) != base[1:]
                                        and emit(case)):
                                    emitted += 1
                    if mem is not None and len(mem_pairs) > 1:
                        mty, align, ordering, failure = mem
                        for other_ordering, other_failure in mem_pairs[:4]:
                            if (other_ordering, other_failure) == (
                                    ordering, failure):
                                continue
                            case = Case(config, opcode,
                                        tuple(llt_text(t) for t in types),
                                        (mty, align, other_ordering,
                                         other_failure), "boundary",
                                        rs["def"], ri,
                                        "ordering %s/%s" % (other_ordering,
                                                            other_failure),
                                        imms=imms)
                            res = _try_fire(evaluator, case)
                            if res == "error":
                                continue
                            if _outcome(res) != base[1:] and emit(case):
                                emitted += 1
                    for index, literals in sorted(
                            infos[ri].imm_thresholds.items()):
                        for n in sorted(literals):
                            for probe in (n - 1, n + 1):
                                if probe < 0 or emitted >= max_boundary_per_rule:
                                    continue
                                vimms = list(imms)
                                if index >= len(vimms):
                                    continue
                                vimms[index] = probe
                                case = Case(config, opcode,
                                            tuple(llt_text(t) for t in types),
                                            mem, "boundary", rs["def"], ri,
                                            "imm[%d] %d -> %d"
                                            % (index, n, probe),
                                            imms=tuple(vimms))
                                res = _try_fire(evaluator, case)
                                if res == "error":
                                    continue
                                if _outcome(res) != base[1:] and emit(case):
                                    emitted += 1
                    if emitted >= max_boundary_per_rule:
                        break

        # -- outside -------------------------------------------------------
        probes = list(queries)
        if uses_mem:
            for mty, align in ((e[2], 0) for e in mem_entries[:4]):
                ordering, failure = mem_pairs[0]
                probes.insert(0, (_pad([E.parse_case_llt("s3"),
                                        E.parse_case_llt("p0:64")],
                                       nslots, default),
                                (mty, align, ordering, failure),
                                imm_tuples[0]))
        for config in configs:
            emitted = 0
            for types, mem, imms in probes:
                case = Case(config, opcode, tuple(llt_text(t) for t in types),
                            mem, "outside", rs["def"], None, "no rule fires",
                            imms=imms)
                if _try_fire(evaluator, case) is None and emit(case):
                    emitted += 1
                if emitted >= max_outside:
                    break

    stats["cases"] = len(cases)
    return Generation(cases, stats)


def generate_from_queries(doc, features, queries_path, oracle_path,
                          *, max_outside=2, max_boundary=24,
                          max_witnesses=4):
    """Compress a complete query/answer run into a regression case set.

    The query file fixes the test population.  The oracle is only used to
    prove that every population member has an answer and to find answer
    transitions; the evaluator supplies rule names for human-readable case
    metadata.  This keeps case compression downstream of the end-to-end A/B
    run instead of making it the equivalence proof.
    """
    evaluator = E.Evaluator(doc, features)
    oracle, oracle_errors = answer_file.load(oracle_path)
    records = []
    missing = 0
    unanswerable = 0
    evaluator_errors = 0
    with open(queries_path) as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                q = json.loads(line)
                key = answer_file.key(q)
            except (ValueError, KeyError, TypeError, E.EvalError) as exc:
                print("%s:%d: %s" % (queries_path, lineno, exc),
                      file=sys.stderr)
                evaluator_errors += 1
                continue
            answer = oracle.get(key)
            if answer is None:
                missing += 1
                continue
            if answer[0] == "unanswerable":
                unanswerable += 1
                continue
            mem = mem_point(q.get("mem"))
            case = Case(q["config"], q["name"], tuple(q.get("types", [])),
                        mem, "", "", None, "",
                        imms=tuple(q.get("imms") or ()))
            fired = _try_fire(evaluator, case)
            if fired == "error":
                evaluator_errors += 1
                continue
            records.append((q, answer, case, fired))

    cases, seen = [], set()
    stats = {"configs": sorted(features.table), "rulesets": len(doc["rulesets"]),
             "opcodes": len({q["name"] for q, _, _, _ in records}),
             "rules": sum(len(rs["rules"]) for rs in doc["rulesets"]),
             "witnessed": 0, "shadowed": 0, "unexercised": 0,
             "equivalence": 0, "boundary": 0, "outside": 0,
             "oracle_missing": missing, "oracle_errors": oracle_errors,
             "evaluator_errors": evaluator_errors,
             "oracle_unanswerable": unanswerable, "unwitnessed": [],
             # This path fixes the population from the query file; it does
             # not drop ill-formed shapes.  The keys exist so the shared CLI
             # stats printer does not KeyError after a successful run.
             "ill_formed": 0, "ill_formed_opcodes": {}}

    def emit(case):
        # The differ works on queries an oracle already answered; filtering
        # them here would change what it compares, so shapes are not checked.
        if case.key() in seen:
            return False
        seen.add(case.key())
        cases.append(case)
        stats[case.kind] += 1
        return True

    witnesses = {}
    outside = {}
    for q, answer, case, fired in records:
        if fired is None:
            outside.setdefault((case.config, case.opcode), 0)
            if outside[(case.config, case.opcode)] < max_outside:
                outside[(case.config, case.opcode)] += 1
                emit(Case(case.config, case.opcode, case.types, case.mem,
                          "outside", "", None, "no rule fires",
                          imms=case.imms))
            continue
        rs_idx, rule_idx = fired[:2]
        rs_name = evaluator.rulesets[rs_idx]["def"]
        key = (case.config, rs_name, rule_idx)
        if len(witnesses.get(key, [])) < max_witnesses:
            witnesses.setdefault(key, []).append(case)
            emit(Case(case.config, case.opcode, case.types, case.mem,
                      "equivalence", rs_name, rule_idx,
                      "first match for rule %d" % rule_idx,
                      imms=case.imms))

    stats["witnessed"] = len(witnesses)
    all_rules = {(c, rs["def"], ri)
                 for c in features.table for rs in doc["rulesets"]
                 for ri in range(len(rs["rules"]))}
    absent = sorted(all_rules - set(witnesses), key=repr)
    stats["unexercised"] = len(absent)
    stats["unwitnessed"] = ["%s#%d: unexercised" % (key[1], key[2])
                             for key in absent[:40]]

    groups = {}
    for q, answer, case, fired in records:
        if fired == "error":
            continue
        mem = tuple(case.mem) if case.mem else None
        groups.setdefault((case.config, case.opcode, repr(mem),
                           case.imms), []).append((case, answer))
    for group in groups.values():
        group.sort(key=lambda x: repr(x[0].types))
        emitted = 0
        for (left, left_answer), (right, right_answer) in zip(group, group[1:]):
            if left_answer == right_answer:
                continue
            if emit(Case(right.config, right.opcode, right.types, right.mem,
                         "boundary", "", None, "oracle answer transition",
                         imms=right.imms)):
                emitted += 1
            if emitted >= max_boundary:
                break

    stats["cases"] = len(cases)
    return Generation(cases, stats)


def _compatible_types(opcode, base, slots, combo, per):
    """Every well-formed fill of the slots a rule search does not enumerate.

    A rule that only constrains slot 0 still needs a legal value in slot 1.
    Taking the default blindly can produce a shape the MIR verifier rejects,
    which would make the search "find" a query that can never be asked -- and
    stopping at the first legal fill can make it "find" one whose *other* rule
    fires first.  Both callers want to keep looking, so this yields.
    """
    types = list(base)
    for s, t in zip(slots, combo):
        types[s] = t
    free = [s for s in range(len(types)) if s not in slots]
    if not free:
        if type_shape_ok(opcode, types):
            yield tuple(types)
        return
    for fill in itertools.product(*(per[s] for s in free)):
        trial = list(types)
        for s, value in zip(free, fill):
            trial[s] = value
        if type_shape_ok(opcode, trial):
            yield tuple(trial)


def _satisfiable(evaluator, rs_idx, ri, rs, configs, infos, per, default,
                 mem_entries, imm_tuples=((),),
                 mem_pairs=(("NotAtomic", "NotAtomic"),)):
    """Whether rule ``ri`` can fire *at all* under any supplied config."""
    rule = rs["rules"][ri]
    slots = sorted(infos[ri].slots) or [0]
    values = [per[s] if s < len(per) else [default[s]] for s in slots]
    mem_trials = [None]
    if infos[ri].uses_mem:
        mem_trials += [(mty, int(align), ordering, failure)
                       for _, _, mty, align in mem_entries
                       for ordering, failure in mem_pairs]
    opcode = rs["opcodes"][0]
    for config in configs:
        for combo in itertools.product(*values):
          for types in _compatible_types(opcode, default, slots, combo, per):
            for mem in mem_trials:
                mems = ([E.MemDesc(E.parse_case_llt(mem[0]), mem[1],
                                   mem[2], mem[3])] if mem else [])
                for imms in imm_tuples:
                    try:
                        if not evaluator.bool_value(
                                rule["predicate"], types, mems, config, imms):
                            continue
                        ok, _ = E.shim_guard_and_newtype(
                            rule.get("op"), rule.get("on"), rule.get("to"),
                            types, mems, evaluator, config, imms)
                    except (E.EvalError, IndexError, KeyError, TypeError,
                            ValueError, AssertionError):
                        continue
                    if ok:
                        return True
    return False


def _rule_witness(evaluator, rs_idx, ri, rs, configs, infos, default,
                  mem_entries, imm_tuples=((),),
                  mem_pairs=(("NotAtomic", "NotAtomic"),), scalable_ok=True,
                  per=None):
    """A query that makes rule ``ri`` the *first* match, or ``None``.

    The shared candidate product is capped, so a rule can lose its witness to a
    truncation somewhere else in the rule set even though the rule is
    reachable.  This search only enumerates the types this rule names (plus
    their neighbours), which is small enough to exhaust and specific enough to
    land on it.  ``None`` means "no witness in this bounded search", not
    "dead": ``_satisfiable`` answers the weaker predicate question.
    """
    opcode = rs["opcodes"][0]
    slots = sorted(infos[ri].slots) or [0]
    per_slot = []
    for s in slots:
        cand = set(infos[ri].literals.get(s, set()))
        cand |= infos[ri].targets.get(s, set())
        for leaf in list(cand):
            cand |= L.neighbours(leaf)
        if not cand:
            cand = {default[s] if s < len(default)
                    else E.parse_case_llt("s32")}
        values = sorted(cand, key=_candidate_key)
        if not scalable_ok:
            values = [x for x in values
                      if not (x[0] == "vector" and x[2])] or values[:1]
        per_slot.append(values[:96])
    total = 1
    for values in per_slot:
        total *= len(values)
    if total > 200000:
        return None
    mem_trials = [None]
    if infos[ri].uses_mem:
        mem_trials += [(mty, int(align), ordering, failure)
                       for _, _, mty, align in mem_entries
                       for ordering, failure in mem_pairs]
    # Free slots are filled from the ruleset axis; cap them so a three-slot
    # opcode does not multiply the directed search by the whole product.
    search = ([list(v[:16]) for v in per] if per is not None
              else [list(v) for v in per_slot])
    for config in configs:
        for combo in itertools.product(*per_slot):
            for types in _compatible_types(opcode, default, slots, combo,
                                           search):
                for mem in mem_trials:
                    mems = ([E.MemDesc(E.parse_case_llt(mem[0]), mem[1],
                                       mem[2], mem[3])] if mem else [])
                    for imms in imm_tuples:
                        try:
                            res = _fire(evaluator, config, opcode, types, mems,
                                        imms)
                        except (E.EvalError, IndexError, KeyError, TypeError,
                                ValueError, AssertionError):
                            continue
                        if (res is not None and res[0] == rs_idx
                                and res[1] == ri):
                            return (config, types, mem, imms, res)
    return None


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
    # Use the same reader as every other answer file: it normalizes the
    # two-element mem spelling to the four-tuple the case key uses.
    return answer_file.key(q)


def index_oracle(path):
    # One reader for every answer file: a bad line is a `file:line` error and
    # a conflicting duplicate is not silently resolved to the first row.
    rows, _errors = jsonl_codec.read_rows(path, strict=True)
    return {row.key: row.raw for row in rows}


def differ(generation, doc, features, oracle_path):
    evaluator = E.Evaluator(doc, features)
    index = index_oracle(oracle_path)
    diff = Diff()
    for case in generation.cases:
        key = (case.config, case.opcode, tuple(_parse(case.types)),
               (E.parse_case_llt(case.mem[0]), case.mem[1], case.mem[2],
                case.mem[3]) if case.mem else None,
               case.imms)
        want = index.get(key)
        if want is None:
            diff.uncovered += 1
            continue
        diff.covered += 1
        try:
            action, type_idx, new_type = E.evaluate(
                evaluator, case.config, case.opcode, _parse(case.types),
                _mems(case), case.imms)
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

def _inputs(args):
    """Resolve the positional source, --corpus, --features and --axes."""
    return corpora.resolve(args.source, args.corpus, args.features, args.axes)

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="gisel cases",
        description="generate equivalence-class, boundary and outside cases")
    ap.add_argument("source", nargs="?",
                    help="a .gisel source (or use --corpus NAME)")
    ap.add_argument("--corpus", metavar="NAME",
                    help="a bundled corpus: %s" % ", ".join(corpora.names()))
    ap.add_argument("--out", required=True)
    ap.add_argument("--features",
                    help="feature truth table (default: derive none/all/only-N)")
    ap.add_argument("--config", action="append", dest="configs",
                    help="limit to configs from --features (repeatable)")
    ap.add_argument("--against", help="oracle JSONL to differ against")
    ap.add_argument("--queries", help="complete answerless query JSONL")
    ap.add_argument("--oracle", help="answers for --queries JSONL")
    ap.add_argument("--max-outside", type=int, default=None,
                    help="default: profile value, else 2")
    ap.add_argument("--axes", help="axis profile JSON (analysis only)")
    ap.add_argument("--json", action="store_true", help="print stats as JSON")
    ap.add_argument("--strict-coverage", action="store_true",
                    help="fail when any rule has no witness in the query set")
    ap.add_argument("--ruleset", action="append", dest="rulesets",
                    help="only these ruleset defs or opcodes (repeatable); "
                         "split a large target into chunks")
    args = ap.parse_args(argv)

    try:
        source, features_path, axes_path = _inputs(args)
        axes = axesmod.load(axes_path) if axes_path else None
        doc, features, axes = session(
            source, features=features_path, configs=args.configs,
            axes=axes)
        cases_profile = axes.profile("cases") if axes is not None else {}
        max_slot_values = int(cases_profile.get("max_slot_values", 16))
        boundaries = bool(cases_profile.get("boundaries", True))
        max_outside = (args.max_outside if args.max_outside is not None
                       else int(cases_profile.get("max_outside", 2)))
    except (axesmod.AxisError, ValueError) as exc:
        print("gisel cases: %s" % exc, file=sys.stderr)
        return 2
    if not features.table:
        print("cases: no configurations selected", file=sys.stderr)
        return 2
    if bool(args.queries) != bool(args.oracle):
        print("cases: --queries and --oracle must be provided together",
              file=sys.stderr)
        return 2
    if args.queries and args.rulesets:
        # A fixed query file is already the set to compress; silently ignoring
        # the filter would make the caller believe it got one chunk.
        print("cases: --ruleset filters generated cases; with --queries the "
              "file is already fixed", file=sys.stderr)
        return 2
    if args.queries:
        generation = generate_from_queries(
            doc, features, args.queries, args.oracle,
            max_outside=max_outside)
    else:
        try:
            generation = generate(
                doc, features, configs=sorted(features.table),
                max_slot_values=max_slot_values,
                max_boundary_per_rule=24 if boundaries else 0,
                max_outside=max_outside, axes=axes,
                only_rulesets=args.rulesets)
        except ValueError as exc:
            print("gisel cases: %s" % exc, file=sys.stderr)
            return 2

    rc = output.write_lines(
        args.out,
        (json.dumps(case.query(), sort_keys=True) + "\n"
         for case in generation.cases))
    if rc:
        return rc

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
        if stats["ill_formed"]:
            print("ill-formed=%d (%s)"
                  % (stats["ill_formed"],
                     ", ".join("%s %d" % kv for kv in
                               sorted(stats["ill_formed_opcodes"].items()))))
    if args.strict_coverage and (stats["unexercised"] or stats["shadowed"]):
        print("cases: %d rule(s) have no witness (%d unexercised, %d shadowed);"
              " the query set does not cover every rule"
              % (stats["unexercised"] + stats["shadowed"],
                 stats["unexercised"], stats["shadowed"]), file=sys.stderr)
        for entry in stats["unwitnessed"][:20]:
            print("  " + entry, file=sys.stderr)
        return 1
    if args.against and stats["diff"]["covered"] == 0:
        print("cases: no overlapping queries; check --features/--config "
              "spellings", file=sys.stderr)
        return 2
    if args.against and (stats["diff"]["disagree"] or stats["diff"]["errors"]):
        return 1
    if args.queries and (stats["oracle_missing"] or stats["oracle_errors"]
                         or stats["evaluator_errors"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
