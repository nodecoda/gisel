"""Emit the ``-gen-legalizer`` C++ fragment from the schema-0.4 normal form.

This is a from-scratch reimplementation of the parts of
``llvm/utils/TableGen/LegalizerInfoEmitter.cpp`` (LLVM commit d48f5512a162)
that turn a rule set into the ``.inc`` the target's LegalizerInfo consumes:

  emitFeatures              :266
  selectText                :385
  emitTypes                 :412
  emitArg / emitArgList     :753 / :840
  emitRuleSet               :853
  CoreShimTable             :2747
  CoreCxxEmitter            :2974   (value :2983, boolean :2984)
  emitCoreRule              :3689

It consumes the same normal form the ``td`` backend consumes, so the two
backends cannot disagree about what a rule means: they only disagree about
how it is spelled.

Ported logic keeps the LLVM license header and names its source commit.
"""

from pathlib import Path

from .. import td as T

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


class IncEmitter:
    def __init__(self, gs, qvar="Query"):
        self.gs = gs
        self.qvar = qvar
        self.names = T.build_names(gs["decls"])
        self.feat_of = {n: p for k, n, p in gs["decls"] if k == "feature"}
        self.preds = {n: p for k, n, p in gs["decls"] if k == "pred"}
        self.used_features = set()
        self.sets = T.collect_named_sets(gs["decls"])

    # ---- names ----------------------------------------------------------

    def _type(self, name):
        if name in self.names.type:
            return self.names.type[name]
        if name in self.names.records:
            return name
        raise KeyError(f"unknown type name {name!r}")

    def _type_value(self, v):
        if isinstance(v, str):
            return self._type(v)
        name = self.names.select_value(v)
        if name is None:
            raise KeyError(f"no named select for {v!r}")
        return name

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
        if k in ("elemOf", "scalarOf", "numElems", "bitsOf", "sizeInBytesOf"):
            method = {"elemOf": "getElementType", "scalarOf": "getScalarType",
                      "numElems": "getNumElements", "bitsOf": "getScalarSizeInBits",
                      "sizeInBytesOf": "getSizeInBytes"}[k]
            return "(%s).%s()" % (self.value(n["args"][0]), method)
        if k == "isByteSized":
            return "(%s).isByteSized()" % self.value(n["args"][0])
        if k == "isBFloat16":
            return "(%s).isBFloat16()" % self.value(n["args"][0])
        if k == "isFloat16":
            return "(%s).isFloat16()" % self.value(n["args"][0])
        if k == "isPow2":
            return "llvm::isPowerOf2_32(%s)" % self.value(n["args"][0])
        if k == "sizeOf":
            inner = n["args"][0]
            if inner.get("kind") == "memSlot":
                # MemDesc::AlignInBits is an alignment, not a size.
                return "(%s).MemoryTy.getSizeInBits()" % self.value(inner)
            return "(%s).getSizeInBits()" % self.value(inner)
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
                # A guard that names a LegalizeFeature record emits the record
                # name bare; emitCoreRule's junction adds the parentheses.
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
        if k in ("isPow2", "isByteSized", "isBFloat16", "isFloat16"):
            return self.value(n)
        raise ValueError(f"no C++ boolean for node {n!r}")

    def _set_entries(self, n):
        """Normal-form set literal -> list of [Type0, Type1, MemTy, Align]."""
        if n.get("kind") == "type":
            # A named set, or a one-member set spelled as the type itself
            # (coreSetJson, :2820).
            if n["value"] in self.sets:
                return [[m] for m in self.sets[n["value"]]]
            return [[self._type_value(n["value"])]]
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

    def _select_text(self, payload):
        conds, types, otherwise = payload
        expr = otherwise
        for i in range(len(conds) - 1, -1, -1):
            expr = "(%s ? %s : %s)" % (self._pred_cxx(conds[i]), types[i], expr)
        return expr

    def _pred_cxx(self, name):
        """A select guard: a feature record name or a predicate-dag expression."""
        if name in self.feat_of:
            return self._feature(self.feat_of[name])
        if name in self.preds:
            return self._bool_dag_cxx(T._bool_node(T.parse_bool(self.preds[name]),
                                                   self.feat_of))
        raise KeyError(f"unknown select guard {name!r}")

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

    def _ruleset(self, rs):
        out = []
        for c in rs["comments"]:
            out.append("  // " + c)
        ops = rs["opcodes"]
        if len(ops) == 1:
            out.append("  getActionDefinitionsBuilder(%s)" % ops[0])
        else:
            out.append("  getActionDefinitionsBuilder({%s})" % ", ".join(ops))
        rules = [self.rule(r) for r in rs["rules"]]
        rules += ["      .immIdx(%d)" % i for i in rs.get("legacy", [])]
        if not rules:
            raise ValueError("rule set %r has no rules" % rs["def"])
        for i, r in enumerate(rules):
            out.append(r + (";" if i + 1 == len(rules) else ""))
        return out

    # ---- one rule (emitCoreRule, :3689) ----------------------------------

    def rule(self, r):
        on = r.get("on")
        to = r.get("to")
        on_form = ONSERVATION_FORM.get(on["kind"], on["kind"]) if on else ""
        to_form = to["kind"] if to else ""
        shim = SHIM_TABLE.get((r["op"], on_form, to_form))
        if shim is None:
            raise ValueError(
                "no C++ shim for operator '%s' over '%s' to '%s'"
                % (r["op"], on_form, to_form))

        guard = r["predicate"]
        unguarded = guard.get("kind") == "leaf" and guard.get("name") == "true"
        if unguarded and shim.unguarded:
            return "      .%s(%s)" % (
                shim.unguarded, r["type_idx"] if shim.takes_type_idx else "")

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
        return "      .%s(%s)" % (shim.method, ", ".join(args))

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
        return str(to["args"][0]["value"])

    # ---- whole file ------------------------------------------------------

    def emit(self):
        body = []
        for rs in self.gs["rulesets"]:
            body += self._ruleset(rs)

        types = []
        for kind, name, payload in self.gs["decls"]:
            if kind == "type":
                types.append("  const LLT %s = %s;" % (name, payload))
            elif kind == "select":
                types.append("  const LLT %s = %s;" % (name, self._select_text(payload)))
        lists = []
        for kind, name, payload in self.gs["decls"]:
            if kind == "type_list":
                lists.append("  const std::initializer_list<LLT> %s = {%s};"
                             % (name, ", ".join(payload)))

        features = ["  bool %s = %s;" % (n, p) for k, n, p in self.gs["decls"]
                    if k == "feature" and n in self.used_features]

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
    gs = T.parse_gisel(Path(args.gisel).read_text())
    text = emit_inc(gs, args.gisel)
    Path(args.out).write_text(text)
    print(f"{args.out}: {len(text.splitlines())} lines")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
