"""Emit the ``-gen-legalizer`` C++ fragment from the language AST.

This is a from-scratch reimplementation of the legacy C++ legalizer emitter
(LLVM commit d48f5512a162) that turns a rule set into the ``.inc`` the
target's LegalizerInfo consumes:

  emitFeatures              :266
  selectText                :385
  emitTypes                 :412
  emitArg / emitArgList     :753 / :840
  emitRuleSet               :853
  CoreShimTable             :2747
  CoreCxxEmitter            :2974   (value :2983, boolean :2984)
  emitCoreRule              :3689

The AST is the only input: rule type positions are structured LLT values and
the C++ spelling (declaration names, guards, shims) is computed here.

Ported logic keeps the LLVM license header and names its source commit.
"""

import json
from pathlib import Path

from .. import ast as A

LICENSE_HEADER = """\
/*===- TableGen'erated file -------------------------------------*- C++ -*-===*\\
|*                                                                            *|
|* GlobalISel legalizer rule fragments                                        *|
|*                                                                            *|
|* Automatically generated file, do not edit!                                 *|
|*                                                                            *|
\\*===----------------------------------------------------------------------===*/
"""


class Shim:
    """One row of ``CoreShimTable`` (LegalizerInfoEmitter.cpp:2747)."""

    __slots__ = ("method", "takes_type_idx", "unguarded", "type_payload",
                 "has_payload")

    def __init__(self, method, payload, takes_type_idx=True, unguarded="",
                 type_payload=False):
        self.method = method
        self.takes_type_idx = takes_type_idx
        self.unguarded = unguarded
        self.type_payload = type_payload
        # `payload` is the C++ column of the table: 0 means "the call stops at
        # the type index", 1 means "one more argument follows".
        self.has_payload = bool(payload)


# (operator, observation form, target form) -> how the C++ chain spells it.
# The observation form is coreObservationForm(): ElemOf is spelled "elem".
SHIM_TABLE = {
    ("widen", "slot", "pow2"): Shim("coreWidenScalarToNextPow2", 0),
    ("widen", "slot", "pow2Min"): Shim("coreWidenScalarToNextPow2", 1),
    ("widen", "slot", "multipleOf"): Shim("coreWidenScalarToNextMultipleOf", 1),
    ("widen", "slot", "ty"): Shim("coreMinScalar", 1),
    ("widen", "slot", "sameAs"): Shim("coreMinScalarSameAs", 1),
    ("widen", "elem", "pow2"): Shim("coreWidenScalarOrEltToNextPow2", 0),
    ("widen", "elem", "pow2Min"): Shim("coreWidenScalarOrEltToNextPow2", 1),
    ("widen", "elem", "multipleOf"): Shim("coreWidenScalarOrEltToNextMultipleOf", 1),
    ("widen", "elem", "ty"): Shim("coreMinScalarOrElt", 1),
    ("widen", "elem", "sameAs"): Shim("coreMinScalarSameAs", 1),
    ("widen", "elem", "minVectorSize"): Shim("coreWidenVectorEltsToVectorMinSize", 1),
    ("widen", "slot", "select"): Shim("coreWidenScalarOrEltToNextPow2OrMinSize", 1),
    ("widen", "slot", "int"): Shim("coreWidenScalarOrEltToNextPow2OrMinSize", 1),
    ("narrow", "slot", "ty"): Shim("coreMaxScalar", 1),
    ("narrow", "slot", "sameAs"): Shim("coreMaxScalarSameAs", 1),
    ("narrow", "elem", "ty"): Shim("coreMaxScalarOrElt", 1),
    ("more", "slot", "pow2"): Shim("coreMoreElementsToNextPow2", 0),
    ("fewer", "slot", "ty"): Shim("coreFewerElementsToType", 1),
    ("fewer", "slot", "int"): Shim("fewerElementsIf", 1),
    ("bitcast", "slot", "ty"): Shim("coreBitcastTo", 1),
    ("widen", "slot", "replace"): Shim("coreWidenTo", 1, type_payload=True),
    ("narrow", "slot", "replace"): Shim("coreNarrowTo", 1, type_payload=True),
    ("more", "slot", "replace"): Shim("coreMoreTo", 1, type_payload=True),
    ("fewer", "slot", "replace"): Shim("coreFewerTo", 1, type_payload=True),
    ("bitcast", "slot", "replace"): Shim("coreBitcastToType", 1, type_payload=True),
    ("legal", "", ""): Shim("coreLegalIf", 0, takes_type_idx=False,
                            unguarded="alwaysLegal"),
    ("custom", "", ""): Shim("coreCustomIf", 0, takes_type_idx=False,
                             unguarded="custom"),
    ("lower", "", ""): Shim("coreLowerIf", 0, takes_type_idx=False,
                            unguarded="lower"),
    ("unsupported", "", ""): Shim("coreUnsupportedIf", 0, takes_type_idx=False,
                                  unguarded="unsupported"),
    ("libcall", "", ""): Shim("coreLibcallIf", 0, takes_type_idx=False,
                              unguarded="libcall"),
    ("scalarize", "slot", ""): Shim("coreScalarizeIf", 0, unguarded="scalarize"),
}

# Terminal actions that also have a declarative `xxxFor(Types)` form.  The
# `.gisel` text cannot tell `legalFor({...})` from `legalIf(typeInSet(0,...))`
# -- they are the same rule -- but the two spellings record *coverage*
# differently: `legalIf` marks every index covered, `legalFor` marks only the
# indices the type set mentions.  The target's `legalizer-info-validation.mir`
# pins that difference, so emit the declarative form whenever an overload
# exists for the shape.  (arity, gated) pairs accepted; `gated` means a
# `bool Pred` overload exists.
FOR_OVERLOADS = {
    "legalFor":       {(1, False), (1, True), (2, False), (2, True),
                       (3, True)},
    "lowerFor":       {(1, False), (2, False), (2, True)},
    "libcallFor":     {(1, False), (1, True), (2, False), (2, True)},
    "customFor":      {(1, False), (1, True), (2, False), (2, True)},
    "unsupportedFor": {(1, False)},
}

# Shims whose implementation calls `markAllIdxsAsCovered()`; a rule spelled
# with one of these covers every type and imm index, whatever its predicate
# says.  The rest record coverage through `typeIdx(i)`.
ALL_COVERING_SHIMS = {
    "coreLegalIf", "coreCustomIf", "coreLowerIf", "coreUnsupportedIf",
    "coreLibcallIf",
}

# terminal action -> its declarative `xxxFor` spelling.
FOR_ACTION = {
    "legal": "legalFor",
    "custom": "customFor",
    "lower": "lowerFor",
    "libcall": "libcallFor",
    "unsupported": "unsupportedFor",
}

# coreObservationForm(): only the forms the corpora use, plus the identity.
ONSERVATION_FORM = {"elemOf": "elem"}

# The three predicates whose C++ is a `LegalityPredicates::` call on the query.
QUERY_PREDICATES = {"in", "inPairs", "inTriples", "inMemDesc"}

KIND_PREDICATE = {
    "kindVector": "isVector",
    "kindScalableVector": "isScalableVector",
    "kindScalar": "isScalar",
    "kindPointer": "isPointer",
    "kindPointerVector": "isPointerVector",
}

ORDERING = {
    "orderingUnordered": "AtomicOrdering::Unordered",
    "orderingMonotonic": "AtomicOrdering::Monotonic",
    "orderingAcquire": "AtomicOrdering::Acquire",
    "orderingRelease": "AtomicOrdering::Release",
    "orderingAcquireRelease": "AtomicOrdering::AcquireRelease",
    "orderingSequentiallyConsistent": "AtomicOrdering::SequentiallyConsistent",
}

CMP_OP = {"eq": "==", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}


class _Stripped:
    """A rule with its top-level feature gate removed, for `if (gate) {}`."""

    def __init__(self, rule, predicate):
        self._rule = rule
        self._predicate = predicate

    def __getitem__(self, key):
        if key == "predicate":
            return self._predicate
        return self._rule[key]

    def get(self, key, default=None):
        if key == "predicate":
            return self._predicate
        return self._rule.get(key, default)


class IncEmitter:
    def __init__(self, gs, qvar="Query"):
        if not isinstance(gs, A.Program):
            raise TypeError("IncEmitter needs the language AST, not a record model")
        self.gs = gs
        self.qvar = qvar
        self.used_features = set()
        self.names = A.NameTable(gs)
        self.feat_of = {d.name: d.cxx for d in gs.decls
                        if isinstance(d, A.Feature)}
        self.preds = {d.name: d.pred for d in gs.decls
                      if isinstance(d, A.PredicateDecl)}
        # canonical LLT spelling -> record name (last declaration wins).
        self._canonical = {}
        for d in gs.decls:
            if isinstance(d, A.NamedType):
                self._canonical[A.llt_text(d.llt)] = d.name
        self.sets = {}
        for d in gs.decls:
            if isinstance(d, (A.TypeSet, A.TypeList)):
                value = d.value
                if isinstance(value, A.SetValue) and value.arity == 1:
                    self.sets[d.name] = tuple(
                        self.names.value_name(e) for e in value.elems)
                else:
                    self.sets[d.name] = ()

    # ---- names ----------------------------------------------------------

    def _type(self, name):
        # `parse_program` leaves a bare string only for a token no
        # declaration named; a canonical spelling still maps to the target
        # record the old `Names.type` map would have chosen.
        if name in self._canonical:
            return self._canonical[name]
        if name in self.names.records:
            return name
        raise ValueError(f"unknown type name {name!r}: rules name declared "
                         f"`type`/`select`/`type_set` records, not LLT literals")

    def _type_value(self, v):
        if isinstance(v, str):
            return self._type(v)
        return self.names.value_name(v)

    def _feature(self, expr):
        name = self.names.feature.get(expr)
        if name is None:
            raise ValueError(
                f"undeclared feature expression {expr!r}; declare it with "
                f"`feature NAME = <expr>`, and pass the same expression text "
                f"to feature(\"...\")")
        self.used_features.add(name)
        return name

    # ---- C++ values (CoreCxxEmitter::value, :2834) -----------------------

    def value(self, n):
        k = n.get("kind")
        if k == "int":
            return str(n["value"])
        if k == "type":
            return self._type_value(n["value"])
        if k == "slot":
            return "%s.Types[%d]" % (self.qvar, n["index"])
        if k == "imm":
            return "%s.Immediates[%d]" % (self.qvar, n["index"])
        if k == "memSlot":
            return "%s.MMODescrs[%d]" % (self.qvar, n["args"][0]["value"])
        if k == "sameAs":
            return "%s.Types[%d]" % (self.qvar, n["args"][0]["value"])
        if k == "ty":
            return self.value(n["args"][0])
        if k == "replace":
            return self.value(n["args"][0])
        if k == "select":
            a = n["args"]
            return "(%s ? %s : %s)" % (self.boolean(a[0]), self.value(a[1]),
                                       self.value(a[2]))
        if k == "sizeInBytesOf":
            # LegalizerCore.td gives SizeInBytesOf sort Int.  LLT's observer
            # returns TypeSize, and TypeSize's implicit conversion to an
            # integer is a fatal error for a scalable vector; take the known
            # minimum, exactly like LegalityPredicates::memSizeNotByteSizePow2.
            return ("(%s).getSizeInBytes().getKnownMinValue()"
                    % self.value(n["args"][0]))
        if k == "numElems" and n["args"][0].get("kind") == "slot":
            # A query slot may hold a scalar or a scalable vector.
            # `getNumElements()` fatals on scalable and `getElementCount()`
            # asserts on scalars, so spell both cases out.  The value must be
            # the one a release-build LLT reports (and the one the evaluator's
            # `num_elems` uses): the known minimum for a vector, and 0 for
            # anything else -- scalars and pointers carry ElementCount 0.
            ty = self.value(n["args"][0])
            return ("((%s).isVector() ? (%s).getElementCount()"
                    ".getKnownMinValue() : 0)" % (ty, ty))
        if k in ("elemOf", "scalarOf", "numElems", "bitsOf"):
            method = {"elemOf": "getElementType", "scalarOf": "getScalarType",
                      "numElems": "getNumElements",
                      "bitsOf": "getScalarSizeInBits"}[k]
            return "(%s).%s()" % (self.value(n["args"][0]), method)
        if k == "isByteSized":
            return "(%s).isByteSized()" % self.value(n["args"][0])
        if k == "isBFloat16":
            return "(%s).isBFloat16()" % self.value(n["args"][0])
        if k == "isFixedVector":
            return "(%s).isFixedVector()" % self.value(n["args"][0])
        if k == "isFloat16":
            return "(%s).isFloat16()" % self.value(n["args"][0])
        if k == "isPow2":
            return "llvm::isPowerOf2_32(%s)" % self.value(n["args"][0])
        if k == "sizeOf":
            # SizeOf also has sort Int in LegalizerCore.td.  LLT returns a
            # TypeSize, so read the known minimum before using it as a number.
            inner = n["args"][0]
            if inner.get("kind") == "memSlot":
                # MemDesc::AlignInBits is an alignment, not a size.
                return ("(%s).MemoryTy.getSizeInBits().getKnownMinValue()"
                        % self.value(inner))
            return ("(%s).getSizeInBits().getKnownMinValue()"
                    % self.value(inner))
        if k == "alignOf":
            return "(%s).AlignInBits" % self.value(n["args"][0])
        if k == "addrSpace":
            return "(%s).getAddressSpace()" % self.value(n["args"][0])
        if k == "memTy":
            return "(%s).MemoryTy" % self.value(n["args"][0])
        if k == "memOrdering":
            return "(%s).Ordering" % self.value(n["args"][0])
        if k == "memFailureOrdering":
            return "(%s).FailureOrdering" % self.value(n["args"][0])
        if k == "pow2Ceil":
            return "llvm::PowerOf2Ceil(%s)" % self.value(n["args"][0])
        if k == "mul":
            return "(%s * %s)" % tuple(self.value(a) for a in n["args"])
        if k == "urem":
            return "(%s %% %s)" % tuple(self.value(a) for a in n["args"])
        if k == "udiv":
            return "(%s / %s)" % tuple(self.value(a) for a in n["args"])
        if k == "intOfSize":
            return "LLT::integer(%s)" % self.value(n["args"][0])
        if k == "vecOf":
            return "LLT::fixed_vector(%s, %s)" % tuple(
                self.value(a) for a in n["args"])
        if k == "scalarOrVecOf":
            return "LLT::scalarOrVector(ElementCount::getFixed(%s), %s)" % tuple(
                self.value(a) for a in n["args"])
        if k == "eltTypeTo":
            return "(%s).changeElementType(%s)" % tuple(
                self.value(a) for a in n["args"])
        if k == "eltSizeTo":
            return "(%s).changeElementSize(%s)" % tuple(
                self.value(a) for a in n["args"])
        if k == "divLanes":
            ty = self.value(n["args"][0])
            return ("(%s).changeElementCount((%s).getElementCount()"
                    ".divideCoefficientBy(%s))"
                    % (ty, ty, self.value(n["args"][1])))
        raise ValueError(f"no C++ value for node {n!r}")

    # ---- C++ booleans (CoreCxxEmitter::boolean, :2921) -------------------

    def boolean(self, n):
        k = n.get("kind")
        if k == "leaf":
            if n["name"] == "true":
                return "true"
            if n["name"] == "hasFeature":
                # A feature guard emits the declared bool name bare; the
                # junction adds the parentheses.
                return self._feature(n["args"][0])
            raise ValueError(f"unknown leaf predicate {n['name']!r}")
        if k in ("all", "any"):
            sep = " && " if k == "all" else " || "
            return sep.join("(%s)" % self.boolean(a) for a in n["args"])
        if k == "not":
            return "!(%s)" % self.boolean(n["args"][0])
        if k in QUERY_PREDICATES:
            return self._membership(n)
        if k in CMP_OP:
            return self._compare(n)
        if k in ("isPow2", "isByteSized", "isBFloat16", "isFloat16",
                 "isFixedVector"):
            return self.value(n)
        raise ValueError(f"no C++ boolean for node {n!r}")

    def _set_entries(self, n):
        """Normal-form set literal -> list of [Type0, Type1, MemTy, Align]."""
        if n.get("kind") == "type":
            value = n["value"]
            if isinstance(value, A.SetValue):
                # A named set (or a type-list expansion).  The AST has
                # already resolved its members.
                if value.arity == 1:
                    return [[self._type_value(e)] for e in value.elems]
                return [[self._type_value(x) for x in row]
                        for row in value.elems]
            return [[self._type_value(value)]]
        elems = n["elems"]
        arity = n.get("arity", 1)
        if arity == 1:
            return [[self._type_value(e)] for e in elems]
        return elems

    def _membership(self, n):
        kind = n["kind"]
        args = n["args"]
        if kind == "inMemDesc":
            slots = [a["args"][0]["value"] if a.get("kind") == "memSlot"
                     else a["index"] for a in args[:3]]
            entries = self._set_entries(args[3])
            rows = ", ".join("{%s, %s, %s, %d}" % (
                self._type_value(e[0]), self._type_value(e[1]),
                self._type_value(e[2]), e[3]) for e in entries)
            return ("LegalityPredicates::typePairAndMemDescInSet(%d, %d, %d, {%s})"
                    "(%s)" % (slots[0], slots[1], slots[2], rows, self.qvar))

        nslots = len(args) - 1
        rhs, lhs = args[-1], args[0]
        if nslots > 1:
            idx = ", ".join(str(a["index"]) for a in args[:nslots])
            entries = args[-1]["elems"]
            rows = ", ".join("{%s}" % ", ".join(self._type_value(x) for x in e)
                             for e in entries)
            fn = "typeTupleInSet" if nslots == 3 else "typePairInSet"
            return "LegalityPredicates::%s(%s, {%s})(%s)" % (fn, idx, rows, self.qvar)
        if rhs.get("kind") == "set" and rhs.get("of") == "Int":
            if lhs.get("kind") != "imm":
                raise ValueError("an Int set can only test an imm slot")
            return ("LegalityPredicates::immInSet(%d, {%s})(%s)"
                    % (lhs["index"],
                       ", ".join(str(e) for e in rhs["elems"]), self.qvar))
        if rhs.get("kind") == "clamp":
            v = self.value(lhs)
            return "(%s >= %d && %s <= %d)" % (
                v, rhs["args"][0]["value"], v, rhs["args"][1]["value"])
        if rhs.get("kind") == "set" and rhs.get("of") == "Kind":
            v = self.value(lhs["args"][0])
            return "(" + " || ".join(
                "%s.%s()" % (v, KIND_PREDICATE[e]) for e in rhs["elems"]) + ")"
        v = self.value(lhs)
        return "(" + " || ".join(
            "%s == %s" % (v, self._type_value(e[0]))
            for e in self._set_entries(rhs)) + ")"

    def _compare(self, n):
        lhs, rhs = n["args"]
        op = CMP_OP[n["kind"]]
        if lhs.get("kind") == "sortOf":
            v = self.value(lhs["args"][0])
            pred = KIND_PREDICATE[self._tag(rhs)]
            if op == "!=":
                return "!(%s.%s())" % (v, pred)
            return "%s.%s()" % (v, pred)
        if lhs.get("kind") in ("memOrdering", "memFailureOrdering"):
            v = self.value(lhs)
            o = ORDERING[self._tag(rhs)]
            if op == "==":
                return "(%s == %s)" % (v, o)
            if op == "!=":
                return "(%s != %s)" % (v, o)
            if op == ">=":
                return "isAtLeastOrStrongerThan(%s, %s)" % (v, o)
            if op == ">":
                return "isStrongerThan(%s, %s)" % (v, o)
            if op == "<=":
                return "(!isStrongerThan(%s, %s))" % (v, o)
            return "(!isAtLeastOrStrongerThan(%s, %s))" % (v, o)
        return "(%s %s %s)" % (self.value(lhs), op, self.value(rhs))

    @staticmethod
    def _tag(n):
        """A bare tag (`KindVector`) and `(KindVector)` carry the same name."""
        k = n.get("kind", "")
        if k in KIND_PREDICATE or k in ORDERING:
            return k
        return n.get("name", "")

    # ---- prologue --------------------------------------------------------

    def _select_text(self, decl):
        value = decl.value
        expr = self._type_value(value.otherwise)
        for cond, then in reversed(value.arms):
            expr = "(%s ? %s : %s)" % (
                self._pred_node(cond), self._type_value(then), expr)
        return expr

    def _pred_node(self, cond):
        """A resolved select guard (a feature leaf or a predicate tree)."""
        if cond.get("kind") == "leaf" and cond.get("name") == "hasFeature":
            return self._feature(cond["args"][0])
        return self._bool_dag_cxx(cond)

    def _bool_dag_cxx(self, node, paren=False):
        """Mirror emitPredicateDag(ParenIfBinOp=false)."""
        k = node["kind"]
        if k == "leaf":
            return self._feature(node["args"][0])
        if k == "not":
            inner = node["arg"] if "arg" in node else node["args"][0]
            return "!(%s)" % self._bool_dag_cxx(inner)
        if k in ("all", "any", "nary"):
            op = node.get("op", "all_of" if k == "all" else "any_of")
            sep = " && " if op == "all_of" else " || "
            kids = node["args"]
            out = sep.join(self._bool_dag_cxx(a, len(kids) > 1) for a in kids)
            return "(" + out + ")" if paren and len(kids) > 1 else out
        raise ValueError(f"unsupported predicate node {node!r}")

    _SLOTS = None

    @classmethod
    def _arity(cls, opcodes, rules=()):
        """Type-index count of a rule set, or None if it cannot be bounded.

        A type set that names an index covers that index in the C++ chain.  A
        set that stops short leaves the remaining indices to some other rule or
        to a free-form predicate, and only the free-form spelling records them.

        The frozen opcode table is a snapshot and does not know every opcode
        (the ATOMICRMW family, for one), so take the widest bound the rules
        themselves witness.
        """
        if cls._SLOTS is None:
            path = Path(__file__).resolve().parents[1] / "data" / "opcode-slots.json"
            cls._SLOTS = json.loads(path.read_text()).get("opcodes", {})
        seen = set()
        for op in opcodes:
            info = cls._SLOTS.get(op)
            if info is not None and info.get("arity") is not None:
                seen.add(info["arity"])
        used = cls._slots_used(rules)
        if used:
            seen.add(used)
        return max(seen) if seen else None

    @classmethod
    def _slots_used(cls, rules):
        """Highest type-slot index the rules mention, plus one."""
        best = 0

        def walk(n):
            nonlocal best
            if isinstance(n, dict):
                if n.get("kind") == "slot" and isinstance(n.get("index"), int):
                    best = max(best, n["index"] + 1)
                for v in n.values():
                    walk(v)
            elif isinstance(n, (list, tuple)):
                for v in n:
                    walk(v)
            return best

        for r in rules:
            walk(r.get("predicate"))
            walk(r.get("on"))
            walk(r.get("to"))
        return best

    def _gate_plan(self, rs, rules=None, drop=()):
        """(gate, guarded rules, other rules) when the set splits on one gate.

        The importer flattens an `if (ST.hasX()) { build } else { build2 }`
        pair into per-rule guards, but the two builders are not
        interchangeable: upstream only *builds* one of them for a given
        subtarget, so the other opcode keeps no rules and the pair's first
        opcode becomes the aliasing representative.  Recovering the block --
        including the outermost gate of a nested `if`/`else` chain -- keeps
        that structure.  `other` is empty for a plain `if`.
        """
        rules = rs["rules"] if rules is None else rules
        gates = [set(self._gates_of(r["predicate"])) for r in rules]
        # `legalFor(Gate, {...})` and `if (Gate) { legalFor({...}) }` are the
        # same rule, but only the second one suppresses the whole builder -- and
        # a suppressed builder is what makes the group's first opcode the
        # aliasing representative.  Hoisting is only justified when every rule
        # of the set carries exactly the same gate: one rule that keeps a gate
        # of its own means upstream built the chain unconditionally and spelled
        # the gate per rule.
        uniform = len({frozenset(s) for s in gates}) == 1
        # Spelling order, not sorted order: a nested `if (A && B)` must hoist
        # `A` first, otherwise the rule survives with a dead `A` conjunct and
        # the verifier still sees a free-form predicate.
        order = []
        for r in rules:
            for g in self._gates_of(r["predicate"]):
                if g not in drop and g not in order:
                    order.append(g)
        best = None
        for g in order:
            neg = self._negate(g)
            yes = [r for r, s in zip(rules, gates) if g in s]
            no = [r for r, s in zip(rules, gates) if neg in s]
            rest = [r for r, s in zip(rules, gates) if g not in s and neg not in s]
            if not (yes or no):
                continue
            # A later builder call can only append, so any rule that is not
            # part of the branch has to come after every rule that is.
            if rest:
                last_branch = max(rules.index(r) for r in yes + no)
                if min(rules.index(r) for r in rest) < last_branch:
                    continue
            # A group's builder is also its aliasing representative, so
            # dropping it changes what the verifier prints for every opcode in
            # the group -- and a group cannot be reopened afterwards.
            if rest and len(rs["opcodes"]) > 1:
                continue
            if not no and not (uniform or len(rs["opcodes"]) == 1):
                continue
            score = len(yes) + len(no)
            if best is None or score > best[4]:
                best = (g, yes, no, rest, score)
        if best is None:
            return None
        return best[:4]

    def _gates_of(self, pred):
        """Every feature gate of a predicate, in spelling order."""
        out = []

        def walk(n):
            if not isinstance(n, dict):
                return
            if n.get("kind") == "all":
                for a in n["args"]:
                    walk(a)
                return
            g = self._one_gate(n)
            if g is not None and g not in out:
                out.append(g)

        walk(pred)
        return out

    def _one_gate(self, n):
        """A build-time boolean the predicate spells, or None.

        Features are constructor-time booleans, so `(A || B)` and `!(A || B)`
        are gates too: upstream evaluates them once, when it decides whether
        to install the builder at all.
        """
        k = n.get("kind")
        if k == "leaf" and n.get("name") == "hasFeature":
            return self._feature(n["args"][0])
        if k in ("any", "all"):
            parts = [self._one_gate(a) for a in n["args"]]
            if all(p is not None for p in parts):
                op = " || " if k == "any" else " && "
                return "(" + op.join(parts) + ")"
            return None
        if k == "not":
            inner = (n.get("args") or [n.get("arg") or {}])[0]
            g = self._one_gate(inner)
            if g is None:
                return None
            if g.startswith("!(") and g.endswith(")"):
                return g[2:-1]
            return "!" + g
        return None

    @staticmethod
    def _negate(g):
        if g.startswith("!(") and g.endswith(")"):
            return g[2:-1]
        return "!" + g

    def _gate_of(self, pred):
        def as_gate(p):
            if p.get("kind") == "leaf" and p.get("name") == "hasFeature":
                return self._feature(p["args"][0])
            if p.get("kind") == "not":
                inner = (p.get("args") or [p.get("arg") or {}])[0]
                if inner.get("kind") == "leaf" and inner.get("name") == "hasFeature":
                    return "!" + self._feature(inner["args"][0])
            return None

        g = as_gate(pred)
        if g is not None:
            return g
        if pred.get("kind") == "all":
            found = [as_gate(p) for p in pred["args"]]
            found = [x for x in found if x is not None]
            if len(found) == 1:
                return found[0]
        return None

    def _drop_gate(self, pred, gate):
        """A predicate with the hoisted gate removed (nested `all`s too)."""
        true = {"kind": "leaf", "name": "true", "args": []}
        both = {gate, self._negate(gate)}
        if self._one_gate(pred) in both:
            return true
        if pred.get("kind") != "all":
            return pred
        rest = [self._drop_gate(p, gate) for p in pred["args"]
                if self._one_gate(p) not in both]
        rest = [p for p in rest
                if not (p.get("kind") == "leaf" and p.get("name") == "true")]
        if not rest:
            return true
        if len(rest) == 1:
            return rest[0]
        return {"kind": "all", "args": rest}

    def _ruleset(self, rs):
        out = []
        for c in rs["comments"]:
            out.append("  // " + c)
        self._rs_opcodes = rs["opcodes"]
        out += self._group(rs, list(rs["rules"]), (), "")
        return out

    def _group(self, rs, rules, drop, pad, path=()):
        """Emit the builder chain(s) for `rules`, hoisting build-time gates.

        `drop` carries the gates already hoisted above this point; their
        conjuncts are removed from the predicates the chain finally prints.
        """
        if not rules:
            return []
        plan = None
        if id(rs) not in self._no_hoist:
            plan = self._gate_plan(rs, rules, drop)
        if plan is None:
            return self._chain(rs, rules, drop, pad, path)
        gate, yes, no, rest = plan
        inner = drop + (gate,)
        out = [pad + "  if (%s) {" % gate]
        out += self._group(rs, yes, inner, pad + "  ",
                           path + ((gate, True),))
        if no:
            out.append(pad + "  } else {")
            out += self._group(rs, no, inner, pad + "  ",
                               path + ((gate, False),))
        out.append(pad + "  }")
        out += self._group(rs, rest, drop, pad, path)
        return out

    def _chain(self, rs, rules, drop, pad, path):
        ops = rs["opcodes"]
        out = []
        if len(ops) == 1:
            out.append(pad + "  getActionDefinitionsBuilder(%s)" % ops[0])
        else:
            out.append(pad + "  getActionDefinitionsBuilder({%s})"
                       % ", ".join(ops))
        self._rs_arity = self._arity(ops, rules)
        lines = []
        for r in rules:
            line, cov = self.rule(r, drop)
            if cov[0] == "gated":
                self._cov.append((tuple(ops), path + ((cov[1], True),),
                                  ("types", cov[2])))
            else:
                self._cov.append((tuple(ops), path, cov))
            lines.append(line)
        lines += ["      .immIdx(%d)" % i for i in rs.get("legacy", [])]
        if not lines:
            raise ValueError("rule set %r has no rules" % rs["def"])
        for i, line in enumerate(lines):
            out.append(pad + line + (";" if i + 1 == len(lines) else ""))
        return out

    # ---- one rule (emitCoreRule, :3689) ----------------------------------

    def rule(self, r, drop=()):
        if drop:
            pred = r["predicate"]
            for gate in drop:
                pred = self._drop_gate(pred, gate)
            r = _Stripped(r, pred)
        on = r.get("on")
        to = r.get("to")
        on_form = ONSERVATION_FORM.get(on["kind"], on["kind"]) if on else ""
        to_form = to["kind"] if to else ""
        shim = SHIM_TABLE.get((r["op"], on_form, to_form))
        if shim is None:
            raise ValueError(
                "no C++ shim for operator '%s' over '%s' to '%s'"
                % (r["op"], on_form, to_form))

        if r["op"] in FOR_ACTION:
            call = self._for_call(r, FOR_ACTION[r["op"]])
            if call is not None:
                return "      .%s" % call, self._for_cov(r)
        call = self._clamp_call(r)
        if call is not None:
            return "      .%s" % call, ("types", {r["type_idx"]})
        call = self._widen_for_call(r)
        if call is not None:
            shape = self._set_shape(r)
            return "      .%s" % call, ("types", set(range(shape[1])))

        guard = r["predicate"]
        unguarded = guard.get("kind") == "leaf" and guard.get("name") == "true"
        if shim.method == "fewerElementsIf":
            # FewerElements to an exact element count has no `core` helper, but
            # `fewerElementsIf` is public and takes the mutation directly, so
            # the generated `.inc` needs no addition to LLVM's headers.
            pred = ("[](const LegalityQuery &) { return true; }" if unguarded
                    else "[=](const LegalityQuery &Query) { return %s; }"
                         % self.boolean(guard))
            return ("      .fewerElementsIf(%s, "
                    "LegalizeMutations::changeElementCountTo(%d, "
                    "ElementCount::getFixed(%s)))"
                    % (pred, r["type_idx"], self._payload(r, shim)),
                    ("types", {r["type_idx"]}))
        if unguarded and shim.unguarded:
            cov = ("all",) if shim.method in ALL_COVERING_SHIMS else (
                "types", {r["type_idx"]})
            return ("      .%s(%s)" % (
                shim.unguarded, r["type_idx"] if shim.takes_type_idx else ""),
                cov)

        args = []
        if unguarded:
            args.append("[](const LegalityQuery &) { return true; }")
        else:
            args.append("[=](const LegalityQuery &Query) { return %s; }"
                        % self.boolean(guard))
        if shim.takes_type_idx:
            args.append(str(r["type_idx"]))
        if shim.has_payload:
            args.append(self._payload(r, shim))
        cov = ("all",) if shim.method in ALL_COVERING_SHIMS else (
            "types", {r["type_idx"]})
        return "      .%s(%s)" % (shim.method, ", ".join(args)), cov

    def _for_cov(self, r):
        """Coverage a `xxxFor(...)` call records: the indices it names.

        The `bool Pred` overloads add nothing when `Pred` is false, so the call
        is conditional on that gate.
        """
        gate, nslots, _ = self._set_shape(r)
        if gate is not None:
            return ("gated", gate, set(range(nslots)))
        return ("types", set(range(nslots)))

    def _rows(self, n, arity):
        """A normal-form set -> rows of C++ type values, or None."""
        if n.get("kind") == "type":
            value = n["value"]
            if isinstance(value, A.SetValue):
                if value.arity != arity:
                    return None
                if arity == 1:
                    return [[self._type_value(e)] for e in value.elems]
                return [[self._type_value(x) for x in row] for row in value.elems]
            if arity != 1:
                return None
            return [[self._type_value(value)]]
        if n.get("kind") != "set" or n.get("arity", 1) != arity:
            return None
        elems = n["elems"]
        if arity == 1:
            return [[self._type_value(e)] for e in elems]
        return [[self._type_value(x) for x in row] for row in elems]

    def _clamp_call(self, r):
        """Recover `clampMin/MaxNumElements` from its core desugaring.

        `.gisel` has a `clamp_max` / `clamp_min` operator, but the core normal
        form has no clamp node: it desugars to

            fewer(slot(i), replace(scalarOrVecOf(N, elemOf(slot(i)))))
              when sortOf(slot(i)) == Vector
               and sortOf(slot(i)) != ScalableVector
               and elemOf(slot(i)) == T
               and numElems(slot(i)) > N

        (and the `more` / `<` mirror for `clamp_min`).  Upstream spells that
        `clampMaxNumElements(i, T, N)`, which records coverage for *one* type
        index; the generic `coreFewerTo` shim marks every index covered and
        makes `legalizer-info-validation.mir` report a user-defined predicate.
        """
        op = r.get("op")
        if op not in ("fewer", "more"):
            return None
        on, to = r.get("on") or {}, r.get("to") or {}
        if on.get("kind") != "slot" or to.get("kind") != "replace":
            return None
        i = on["index"]
        pred = r["predicate"]
        if pred.get("kind") != "all" or len(pred["args"]) != 4:
            return None

        def arg(n, k=0):
            return (n.get("args") or [{}])[k]

        def inner_slot(n):
            """`sortOf(slot(i))` / `elemOf(slot(i))` / `numElems(slot(i))`."""
            for k in ("sortOf", "elemOf", "numElems"):
                if n.get("kind") == k:
                    a = arg(n)
                    return a.get("index") if a.get("kind") == "slot" else None
            return None

        def is_vector(n):
            return (n.get("kind") == "eq" and inner_slot(arg(n)) == i and
                    arg(n, 1).get("kind") == "kindVector")

        def not_scalable(n):
            if n.get("kind") != "not":
                return False
            inner = arg(n) if n.get("args") else (n.get("arg") or {})
            return (inner.get("kind") == "eq" and
                    inner_slot(arg(inner)) == i and
                    arg(inner, 1).get("kind") == "kindScalableVector")

        elt = bound = None
        for n in pred["args"]:
            if is_vector(n) or not_scalable(n):
                continue
            if (n.get("kind") == "eq" and arg(n).get("kind") == "elemOf" and
                    inner_slot(arg(n)) == i):
                rhs = arg(n, 1)
                if rhs.get("kind") != "ty":
                    return None
                elt = self._type_value(rhs["args"][0]["value"])
                continue
            if (n.get("kind") in ("gt", "lt") and
                    arg(n).get("kind") == "numElems" and
                    inner_slot(arg(n)) == i):
                bound = arg(n, 1)
                if (n["kind"] == "gt") != (op == "fewer"):
                    return None
                continue
            return None
        if elt is None or bound is None:
            return None
        body = to["args"][0]
        want = "scalarOrVecOf" if op == "fewer" else "vecOf"
        if body.get("kind") != want:
            return None
        args = body.get("args") or []
        if len(args) != 2 or args[1].get("kind") != "elemOf":
            return None
        if args[1]["args"][0].get("kind") != "slot":
            return None
        if args[1]["args"][0].get("index") != i:
            return None
        if args[0] != bound:
            return None
        method = ("clampMaxNumElements" if op == "fewer"
                  else "clampMinNumElements")
        return "%s(%d, %s, %s)" % (method, i, elt, self.value(bound))

    def _flatten_all(self, node, out):
        """Collect the conjuncts of a (possibly nested) `all` node."""
        if node.get("kind") == "all":
            for a in node["args"]:
                self._flatten_all(a, out)
        else:
            out.append(node)

    def _split_guard(self, guard):
        """(gate, conjuncts) for a rule guard.

        `gate` is the conjunction of the conjuncts that name a constructor-time
        boolean (`feature(...)`, including `!(...)` and `(A && B)` spellings);
        everything else is returned in `conjuncts`.  `(gate, [])` therefore
        means "the guard is only build-time conditions".
        """
        parts = []
        self._flatten_all(guard, parts)
        gates, rest = [], []
        for p in parts:
            g = self._one_gate(p)
            if g is None:
                rest.append(p)
            else:
                gates.append(g)
        if not gates:
            return None, rest
        if len(gates) == 1:
            return gates[0], rest
        return "(" + " && ".join(gates) + ")", rest

    def _eq_rows(self, node):
        """`slot(0) == T0 and slot(1) == T1` -> (nslots, [[T0, T1]])."""
        parts = []
        self._flatten_all(node, parts)
        by_index = {}
        for p in parts:
            if p.get("kind") != "eq":
                return None
            args = p.get("args") or []
            if len(args) != 2:
                return None
            lhs, rhs = args
            if lhs.get("kind") != "slot" or rhs.get("kind") != "type":
                return None
            i = lhs.get("index")
            if not isinstance(i, int) or i in by_index:
                return None
            by_index[i] = self._type_value(rhs["value"])
        idxs = sorted(by_index)
        if not idxs or idxs != list(range(len(idxs))):
            return None
        return len(idxs), [[by_index[i] for i in idxs]]

    def _set_shape(self, r):
        """(gate, nslots, rows) when the guard is one type-tuple membership."""
        gate, rest = self._split_guard(r["predicate"])
        if len(rest) != 1:
            return None
        node = rest[0]
        if node.get("kind") in ("in", "inPairs", "inTriples"):
            args = node["args"]
            nslots = len(args) - 1
            if [a.get("index") for a in args[:nslots]] != list(range(nslots)):
                return None
            rows = self._rows(args[-1], nslots)
        else:
            shape = self._eq_rows(node)
            if shape is None:
                return None
            nslots, rows = shape
        if rows is None or not rows:
            return None
        return gate, nslots, rows

    @staticmethod
    def _set_text(nslots, rows):
        if nslots == 1:
            return "{%s}" % ", ".join(row[0] for row in rows)
        return "{%s}" % ", ".join("{%s}" % ", ".join(row) for row in rows)

    def _imm_arity(self, ops):
        """Generic immediate slots of a rule set's opcodes (0 when unknown).

        The `xxxFor` entry points record coverage for type indices only.  A
        free-form `legalIf`/`lowerIf` marks *every* index covered, immediate
        slots included, so replacing one with the other loses the immediate
        half of the verifier's report.  Keep the free-form spelling whenever
        the opcode actually has an immediate to cover.
        """
        if self._SLOTS is None:
            path = Path(__file__).resolve().parents[1] / "data" / "opcode-slots.json"
            self._SLOTS = json.loads(path.read_text()).get("opcodes", {})
        return sum(self._SLOTS.get(op, {}).get("imm", 0) or 0 for op in ops)

    def _for_call(self, r, name):
        """`legal in(slot(0), [T,...])` as `legalFor({T,...})`, or None."""
        shape = self._set_shape(r)
        if shape is None:
            return None
        gate, nslots, rows = shape
        if (nslots, gate is not None) not in FOR_OVERLOADS[name]:
            return None
        if self._imm_arity(getattr(self, "_rs_opcodes", ())):
            return None
        # A *short* type set can be spelled two ways upstream:
        # `xxxFor({T,...})`, which covers only the indices it names, or
        # `xxxIf(typeInSet(0, {...}))`, which covers all of them.  The corpus
        # text is the same for both, so keep the free-form spelling unless the
        # rule is gated -- a gated short set is what `xxxFor(bool, {...})` is
        # for (`libcallFor(ST.is64Bit(), {s128, s32})`), while an ungated one
        # is upstream's `legalIf(typeInSet(...))`.
        if gate is None and nslots != getattr(self, "_rs_arity", None):
            return None
        body = self._set_text(nslots, rows)
        if gate is None:
            return "%s(%s)" % (name, body)
        return "%s(%s, %s)" % (name, gate, body)

    def _widen_for_call(self, r):
        """`widen(slot(0), replace(T)) when in(slot(0), [...])` as
        `widenScalarFor({...}, mutation)`.

        The `widenScalarIf` free-form builder marks every index covered; the
        `widenScalarFor` type-set form marks type index 0.  The `.gisel` text is
        the same for both, so recover the declarative spelling whenever the
        guard is exactly a type set.
        """
        if r.get("op") != "widen" or (r.get("to") or {}).get("kind") != "replace":
            return None
        shape = self._set_shape(r)
        if shape is None:
            return None
        gate, nslots, rows = shape
        if gate is not None or nslots != 1:
            return None
        mutation = self._payload(r, Shim("coreWidenTo", 1, type_payload=True))
        return "widenScalarFor(%s, %s)" % (
            self._set_text(nslots, rows), mutation)

    def _payload(self, r, shim):
        to = r["to"]
        if shim.type_payload:
            return ("[=](const LegalityQuery &Query) { return std::make_pair(%d, %s); }"
                    % (r["type_idx"], self.value(to["args"][0])))
        if to.get("kind") == "int":
            return str(to["value"])
        if to.get("kind") == "ty":
            inner = to["args"][0]
            if inner.get("kind") != "type":
                raise ValueError("a Ty target must name a type record")
            return self._type_value(inner["value"])
        if to.get("kind") == "select":
            return self.value(to)
        inner = to.get("args", [None])[0]
        if isinstance(inner, dict) and inner.get("kind") == "int":
            return str(inner["value"])
        return self.value(inner if inner is not None else to)

    # ---- whole file ------------------------------------------------------

    def _coverage_violations(self):
        """Opcodes a hoisted `if` leaves with a partial (non-empty) ruleset.

        A builder that is dropped entirely is fine: `verifyTypeIdxsCoverage`
        short-circuits on an empty rule set.  A builder that survives with only
        some of its rules is not: it has to cover every type index on its own.
        The rules that are emitted outside any `if` are the ones no subtarget
        can take away, so they must either be absent or cover the whole arity.
        """
        per_op = {}
        for ops, path, cov in self._cov:
            for op in ops:
                per_op.setdefault(op, []).append((path, cov))
        bad = set()
        for op, entries in per_op.items():
            arity = self._arity((op,), ())
            # `opcode-slots.json` is a snapshot and misses the ATOMICRMW
            # family; without an arity there is nothing to compare against.
            if arity is None:
                continue
            always = {"all": False, "types": set()}
            for p in self._unconditional_paths({p for p, _ in entries}):
                for path, cov in entries:
                    if path != p:
                        continue
                    if cov[0] == "all":
                        always["all"] = True
                    else:
                        always["types"] |= cov[1]
            if always["all"] or not always["types"]:
                continue
            if len(always["types"]) < arity:
                bad.add(op)
        return bad

    @staticmethod
    def _unconditional_paths(paths):
        """Paths that hold for every subtarget.

        `()` always holds, and so does a branch whose sibling exists: an
        `if (G) { ... } else { ... }` pair always runs one of the two.
        """
        def canon(path):
            """`!X` and `X` are the two sides of the same branch."""
            return tuple(
                (g[1:], not pol) if g.startswith("!") else (g, pol)
                for g, pol in path)

        canon_paths = {canon(p) for p in paths}
        out = {()}
        for p in sorted(paths, key=len):
            if not p:
                continue
            gate, polarity = canon(p)[-1]
            sibling = canon(p)[:-1] + ((gate, not polarity),)
            if p[:-1] in out and sibling in canon_paths:
                out.add(p)
        return out

    def emit(self):
        self._no_hoist = set()
        for _ in range(4):
            body = []
            self._cov = []
            for rs in self.gs.rulesets:
                body += self._ruleset(rs)
            bad = self._coverage_violations()
            if not bad:
                break
            self._no_hoist |= {id(rs) for rs in self.gs.rulesets
                               if set(rs["opcodes"]) & bad}
        else:
            raise ValueError(
                "no emission verifies the type coverage of its rule sets")

        types = []
        for d in self.gs.decls:
            if isinstance(d, A.NamedType):
                types.append("  const LLT %s = %s;" % (d.name, d.source))
            elif isinstance(d, A.SelectType):
                types.append("  const LLT %s = %s;"
                             % (d.name, self._select_text(d)))
        lists = []
        for d in self.gs.decls:
            if isinstance(d, A.TypeList):
                lists.append("  const std::initializer_list<LLT> %s = {%s};"
                             % (d.name, ", ".join(
                                 self._type_value(e) for e in d.value.elems)))
        features = ["  bool %s = %s;" % (d.name, d.cxx)
                    for d in self.gs.decls
                    if isinstance(d, A.Feature)
                    and d.name in self.used_features]

        out = [LICENSE_HEADER.rstrip("\n"), ""]
        if features:
            out += features + [""]
        if types:
            out += types + [""]
        if lists:
            out += lists + [""]
        out += body
        return "\n".join(out) + "\n"


def emit_inc(gs, source_name):
    return IncEmitter(gs).emit()


def main(argv):
    import argparse
    import sys

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gisel")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    gs = A.parse_program(Path(args.gisel).read_text())
    text = emit_inc(gs, args.gisel)
    Path(args.out).write_text(text)
    print(f"{args.out}: {len(text.splitlines())} lines")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
