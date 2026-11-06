"""Type classes for the ``-gen-legalizer-table`` backend.

M3 step 1: ``resolve`` and ``collectClasses``/``collectMemClasses``
(LegalizerInfoEmitter.cpp:5157-5400).  The rule translation, the descriptors
and the per-rule-set evaluators come next; this module is what they index
into, so it is verified against the artifact's class tables before any of that
is written.

Classes are keyed by ``(kind, element bits, lanes)`` and ordered by
``lessTypeClass``: kind rank, then element bits, then lanes.  The ``root`` of a
class is the first named type (in declaration order) that produced it, which
is what the generated ``// X86_s16`` comments record.
"""

from collections import namedtuple

TableType = namedtuple("TableType", "kind bits lanes root")

# typeRank, LegalizerInfoEmitter.cpp:5323
RANK = {
    "Pointer": 0,
    "Scalar": 1,
    "Integer": 2,
    "Float": 3,
    "BFloat": 4,
    "Vector": 5,
    "PtrVector": 6,
    "ScalableVector": 7,
    "ScalablePtrVector": 8,
}

# tableTypeKindName, :5372
KIND_NAME = {
    "Pointer": "Kind_Pointer",
    "Scalar": "Kind_Scalar",
    "Integer": "Kind_Integer",
    "Float": "Kind_Float",
    "BFloat": "Kind_BFloat",
    "Vector": "Kind_Vector",
    "PtrVector": "Kind_PtrVector",
    "ScalableVector": "Kind_ScalableVector",
    "ScalablePtrVector": "Kind_ScalablePtrVector",
}

SCALARS = ("Scalar", "Integer", "Float", "BFloat")


def strip_parens(s):
    s = s.strip()
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(s) - 1:
                    return s  # the leading '(' closes before the end
        s = s[1:-1].strip()
    return s


def split_conditional(s):
    """`Cond ? Then : Else` at depth 0 -> (Then, Else), else None."""
    depth = 0
    q = -1
    for i, ch in enumerate(s):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "?" and depth == 0:
            q = i
            break
    if q < 0:
        return None
    depth = 0
    for i in range(q + 1, len(s)):
        ch = s[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == ":" and depth == 0:
            return s[q + 1:i].strip(), s[i + 1:].strip()
    return None


def _arg_of(expr, prefix):
    if expr.startswith(prefix) and expr.endswith(")"):
        return expr[len(prefix):-1].strip()
    return None


def _split_lanes(arg):
    depth = 0
    for i, ch in enumerate(arg):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            return arg[:i].strip(), arg[i + 1:].strip()
    return None, None


class Resolver:
    def __init__(self, gs):
        # A select type names a condition, not a class; its branches are
        # named types in their own right and are collected when reached.
        self.named = {n: p for k, n, p in gs["decls"] if k == "type"}

    def resolve(self, expr, root, depth=0):
        expr = strip_parens(expr)
        if depth > 16:
            raise ValueError("type expression nests too deep: %r" % expr)

        split = split_conditional(expr)
        if split:
            return (self.resolve(split[0], root, depth) +
                    self.resolve(split[1], root, depth))

        arg = _arg_of(expr, "LLT::scalar(")
        if arg is not None:
            return [TableType("Scalar", int(arg), 1, root)]
        if _arg_of(expr, "LLT::pointer(") is not None:
            return [TableType("Pointer", 0, 1, root)]
        arg = _arg_of(expr, "LLT::integer(")
        if arg is not None:
            return [TableType("Integer", int(arg), 1, root)]

        for name, bits in (("float16", 16), ("float32", 32), ("float64", 64),
                           ("float128", 128)):
            if expr == "LLT::%s()" % name:
                return [TableType("Float", bits, 1, root)]
        if expr == "LLT::bfloat16()":
            return [TableType("BFloat", 16, 1, root)]

        for prefix, kind, ptr_kind in (
                ("LLT::scalable_vector(", "ScalableVector",
                 "ScalablePtrVector"),
                ("LLT::fixed_vector(", "Vector", "PtrVector")):
            arg = _arg_of(expr, prefix)
            if arg is None:
                continue
            lanes, elem = _split_lanes(arg)
            if lanes is None:
                raise ValueError("malformed vector type %r" % expr)
            lanes = int(lanes)
            if elem.isdigit():
                return [TableType(kind, int(elem), lanes, root)]
            out = []
            for e in self.resolve(elem, root, depth + 1):
                if e.kind in SCALARS:
                    out.append(TableType(kind, e.bits, lanes, root))
                elif e.kind == "Pointer":
                    out.append(TableType(ptr_kind, 0, lanes, root))
                else:
                    raise ValueError("unsupported vector element in %r" % expr)
            return out

        if expr and (expr[0].isalpha() or expr[0] == "_") and \
                all(c.isalnum() or c == "_" for c in expr):
            if expr not in self.named:
                raise ValueError("unknown named type %r" % expr)
            return self.resolve(self.named[expr], root, depth + 1)

        raise ValueError("cannot derive a table type class from %r" % expr)


def less_type_class(t):
    return (RANK[t.kind], t.bits, t.lanes)


def collect_classes(gs):
    r = Resolver(gs)
    types = [(n, p) for k, n, p in gs["decls"] if k == "type"]
    seen, out = set(), []
    for name, expr in types:
        for t in r.resolve(expr, name):
            key = (t.kind, t.bits, t.lanes)
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
    out.sort(key=less_type_class)
    if not out or out[0].kind != "Pointer":
        raise ValueError("a legalizer table needs a pointer type class")
    return out


def collect_mem_classes(gs, classes=None):
    r = Resolver(gs)
    classes = classes if classes is not None else collect_classes(gs)
    types = [(n, p) for k, n, p in gs["decls"] if k == "type"]
    seen, out = set(), []
    for name, expr in types:
        for t in r.resolve(expr, name):
            key = (t.kind, t.bits, t.lanes)
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
    # The pointer class is the one width the .td leaves to the subtarget, and
    # it is also the self-check probe for a memdesc rule set.
    if ("Pointer", 0, 1) not in seen:
        out.append(TableType("Pointer", 0, 1, "p0"))
    out.sort(key=less_type_class)
    return out or [classes[0]]


def dump(gs):
    """A text rendering close to the artifact, for diffing by eye."""
    lines = []
    for label, items in (("TypeClasses", collect_classes(gs)),
                         ("MemClasses", collect_mem_classes(gs))):
        lines.append("%s (%d):" % (label, len(items)))
        for i, t in enumerate(items):
            lines.append("  /*%d*/ {%s, %d, %d}, // %s"
                         % (i, KIND_NAME[t.kind], t.bits, t.lanes, t.root))
    return "\n".join(lines) + "\n"


# ---- sections 1-3 of the artifact ----------------------------------------

HEADER = """\
//===-- {P}LegalizerTable.inc - generated table data -----*- C++ -*-===//
//
// Generated by llvm-tblgen -gen-legalizer-table.  Do not edit.
// Type classes, per-opcode descriptors and the per-rule-set evaluators.
//
//===----------------------------------------------------------------------===//
"""


def _walk(node, pred):
    if isinstance(node, dict):
        if pred(node):
            return True
        return any(_walk(v, pred) for v in node.values())
    if isinstance(node, list):
        return any(_walk(v, pred) for v in node)
    return False


def reads_mem_desc(rule):
    """True when the rule reads a memory descriptor (needsMemDesc, :5540)."""
    return any(_walk(part, lambda n: n.get("kind") in ("memSlot", "inMemDesc"))
               for part in (rule.get("on"), rule.get("to"), rule.get("predicate")))


def mem_desc_aligns(rule):
    """The alignment thresholds a rule's memdesc sets name (:5580)."""
    out = set()

    def visit(node):
        if isinstance(node, dict):
            if node.get("kind") in ("inMemDesc", "set") and node.get("arity") == 2:
                for e in node.get("elems", []):
                    if len(e) == 4:
                        out.add(e[3])
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)

    for part in (rule.get("on"), rule.get("to"), rule.get("predicate")):
        visit(part)
    return out


def needs_mem_desc(ruleset):
    return any(reads_mem_desc(r) for r in ruleset["rules"])


def align_thresholds(gs):
    out = set()
    for rs in gs["rulesets"]:
        if not needs_mem_desc(rs):
            continue
        for r in rs["rules"]:
            out |= mem_desc_aligns(r)
    return sorted(out)


def emit_feature_signature(gs, P):
    feats = [(n, p) for k, n, p in gs["decls"] if k == "feature"]
    if len(feats) > 32:
        raise ValueError("feature signature needs more than 32 bits")
    out = ["// Environment signature: one bit per LegalizeFeature, in .td order.",
           "// A shared table cache keys on this, so equal signatures must mean equal",
           "// answers.",
           "enum : uint32_t {"]
    for i, (name, cond) in enumerate(feats):
        out.append("  %sFeatureBit_%s = 1u << %d," % (P, name, i))
    out += ["};", "",
            "static uint32_t %sFeatureSignature(const %sSubtarget &Subtarget) {"
            % (P, P),
            "  uint32_t S = 0;"]
    for name, cond in feats:
        out.append("  S |= (%s) ? %sFeatureBit_%s : 0u;" % (cond, P, name))
    out += ["  return S;", "}", ""]
    return out


def _class_lines(name, items):
    out = ["static constexpr LegalizerTypeClass %s[] = {" % name]
    for i, t in enumerate(items):
        out.append("  /*%d*/ {%s, %d, %d}, // %s"
                   % (i, KIND_NAME[t.kind], t.bits, t.lanes, t.root))
    out.append("};")
    return out


def emit_head(gs, P):
    """Everything before the per-rule-set evaluators."""
    classes = collect_classes(gs)
    mem = collect_mem_classes(gs, classes)
    aligns = align_thresholds(gs)

    out = HEADER.format(P=P).splitlines()
    out.append("")
    out += emit_feature_signature(gs, P)
    out += _class_lines(P + "TypeClasses", classes)
    out.append("static constexpr unsigned %sNumTypeClasses = sizeof(%sTypeClasses)"
               " / sizeof(%sTypeClasses[0]);" % (P, P, P))
    out.append("")
    out.append("// Classes of the memory-descriptor axis (the descriptor's LLT).")
    out += _class_lines(P + "MemClasses", mem)
    out.append("static constexpr unsigned %sNumMemClasses = sizeof(%sMemClasses)"
               " / sizeof(%sMemClasses[0]);" % (P, P, P))
    out.append("")
    out.append("// Alignment classes for the memory-descriptor axis: a query meets a")
    out.append("// prefix of the thresholds, because TypePairAndMemDesc only asks")
    out.append("// Align >= Entry.Align.")
    out.append("static constexpr unsigned %sAlignThresholds[] = {%s};"
               % (P, ", ".join(str(a) for a in aligns)))
    out.append("static constexpr unsigned %sNumAlignClasses = sizeof(%sAlignThresholds)"
               " / sizeof(%sAlignThresholds[0]) + 1;" % (P, P, P))
    out.append("")
    out.append("// Slots 0 and 1, partitioned by the full class list; a rule set that")
    out.append("// reads a memory descriptor adds the descriptor axis.  A rule set")
    out.append("// that needs anything else is not in this table (see the emitter).")
    out.append("static constexpr LegalizerTableDesc %sTables[] = {" % P)
    for i, rs in enumerate(gs["rulesets"]):
        has_mem = needs_mem_desc(rs)
        out.append("  /*%d*/ {{0, 1}, {%d, %d}, %s, %s}, // %s"
                   % (i, len(classes), len(classes),
                      "0" if has_mem else "kNoMemDesc",
                      ("%sNumMemClasses * %sNumAlignClasses" % (P, P))
                      if has_mem else "0",
                      rs["def"]))
    out.append("};")
    out.append("static constexpr unsigned %sNumTables = sizeof(%sTables)"
               " / sizeof(%sTables[0]);" % (P, P, P))
    out.append("")
    lower = P[:1].lower() + P[1:]
    out.append("static inline int %sTableForOpcode(unsigned Opcode) {" % lower)
    out.append("  switch (Opcode) {")
    for i, rs in enumerate(gs["rulesets"]):
        for op in rs["opcodes"]:
            out.append("  case TargetOpcode::%s: return %d;" % (op, i))
    out += ["  default: return -1;", "  }", "}", ""]
    return out


# ---- rule translation -----------------------------------------------------

# CoreTableTranslation per shim row, LegalizerInfoEmitter.cpp:2747-2815.
# Kept beside the shim table rather than inside it so the .inc backend stays
# the single owner of the C++ spelling; a test asserts the key sets agree.
TRANSLATION = {
    ("widen", "slot", "pow2"): "ScalarPow2",
    ("widen", "slot", "pow2Min"): "ScalarPow2",
    ("widen", "slot", "multipleOf"): "ScalarMultipleOf",
    ("widen", "slot", "ty"): "MinScalar",
    ("widen", "slot", "sameAs"): "MinScalarSameAs",
    ("widen", "elem", "pow2"): "ScalarOrEltPow2",
    ("widen", "elem", "pow2Min"): "ScalarOrEltPow2",
    ("widen", "elem", "multipleOf"): "ScalarMultipleOf",
    ("widen", "elem", "ty"): "MinScalarOrElt",
    ("widen", "elem", "sameAs"): "MinScalarSameAs",
    ("widen", "elem", "minVectorSize"): "WidenVectorMinSize",
    ("widen", "slot", "select"): "WidenPow2OrMinSize",
    ("widen", "slot", "int"): "WidenPow2OrMinSize",
    ("narrow", "slot", "ty"): "MaxScalar",
    ("narrow", "slot", "sameAs"): "MaxScalarSameAs",
    ("narrow", "elem", "ty"): "MaxScalarOrElt",
    ("more", "slot", "pow2"): "MorePow2",
    ("fewer", "slot", "ty"): "FewerToType",
    ("bitcast", "slot", "ty"): "BitcastToType",
    ("widen", "slot", "replace"): "WholeTypeMutation",
    ("narrow", "slot", "replace"): "WholeTypeMutation",
    ("more", "slot", "replace"): "WholeTypeMutation",
    ("fewer", "slot", "replace"): "WholeTypeMutation",
    ("bitcast", "slot", "replace"): "WholeTypeMutation",
    ("legal", "", ""): "GuardedAction",
    ("custom", "", ""): "GuardedAction",
    ("lower", "", ""): "GuardedAction",
    ("unsupported", "", ""): "GuardedAction",
    ("libcall", "", ""): "GuardedAction",
    ("scalarize", "slot", ""): "Scalarize",
}


def conjunction(a, b):
    """conjunction(), :6133."""
    if not a:
        return b
    if not b:
        return a
    return "(%s) && (%s)" % (a, b)


def emit_step(action, indent, mutation="", typed=None):
    """emitStep()/emitTypedStep(), :6149."""
    if typed is not None:
        return [indent + "return {LegalizeActions::%s, %s, %s};" % (action, typed[0], typed[1])]
    if not mutation:
        return [indent + "return {LegalizeActions::%s, 0, LLT{}};" % action]
    return [indent + "auto M = (%s)(Q);" % mutation,
            indent + "return {LegalizeActions::%s, M.first, M.second};" % action]


def translate_core_rule(rule, cxx):
    """translateCoreRule(), :6859.  Returns (statements, reason)."""
    on = rule.get("on")
    to = rule.get("to")
    on_form = {"elemOf": "elem"}.get(on["kind"], on["kind"]) if on else ""
    to_form = to["kind"] if to else ""
    key = (rule["op"], on_form, to_form)
    tr = TRANSLATION.get(key)
    if tr is None:
        return None, "no table translation for %s/%s/%s" % key

    idx = str(rule["type_idx"])
    v = "Q.Types[%s]" % idx
    guard = rule["predicate"]
    if guard.get("kind") == "leaf" and guard.get("name") == "true":
        p = ""
    else:
        p = cxx.boolean(guard)

    cond = ""
    mut = ""

    if tr == "WidenVectorMinSize":
        size = str(to["args"][0]["value"])
        cond = "(%s.isFixedVector() && %s.getSizeInBits() < %s)" % (v, v, size)
        mut = ("[](const LegalityQuery &Q) { const LLT VecTy = Q.Types[%s]; "
               "const unsigned NumElts = VecTy.getNumElements(); "
               "const unsigned MinSize = %s / NumElts; "
               "return std::make_pair(unsigned(%s), LLT::fixed_vector(NumElts, "
               "VecTy.getElementType().changeElementSize(MinSize))); }"
               % (idx, size, idx))
    elif tr == "GuardedAction":
        pass
    elif tr == "Scalarize":
        cond = "isVector(%s)(Q)" % idx
        mut = "LegalizeMutations::scalarize(%s)" % idx
    elif tr == "MinScalarOrElt":
        ty = cxx.value(to)
        cond = "scalarOrEltNarrowerThan(%s, (%s).getScalarSizeInBits())(Q)" % (idx, ty)
        mut = "LegalizeMutations::changeElementSizeTo(%s, %s)" % (idx, ty)
    elif tr in ("ScalarPow2", "ScalarOrEltPow2"):
        kids = to.get("args") or []
        minimum = str(kids[0]["value"]) if kids else "0"
        cond = ("sizeNotPow2(%s)(Q)" if tr == "ScalarPow2"
                else "scalarOrEltSizeNotPow2(%s)(Q)") % idx
        mut = "LegalizeMutations::widenScalarOrEltToNextPow2(%s, %s)" % (idx, minimum)
    elif tr == "ScalarMultipleOf":
        size = str(to["args"][0]["value"])
        cond = "(Q.Types[%s].getScalarSizeInBits() %% %s != 0)" % (idx, size)
        mut = "LegalizeMutations::widenScalarOrEltToNextMultipleOf(%s, %s)" % (idx, size)
    elif tr in ("MinScalar", "MaxScalar"):
        ty = cxx.value(to)
        pred = "scalarNarrowerThan" if tr == "MinScalar" else "scalarWiderThan"
        cond = "%s(%s, (%s).getSizeInBits())(Q)" % (pred, idx, ty)
        mut = "LegalizeMutations::changeElementSizeTo(%s, %s)" % (idx, ty)
    elif tr in ("MinScalarOrElt", "MaxScalarOrElt"):
        ty = cxx.value(to)
        pred = ("scalarOrEltNarrowerThan" if tr == "MinScalarOrElt"
                else "scalarOrEltWiderThan")
        cond = "%s(%s, (%s).getScalarSizeInBits())(Q)" % (pred, idx, ty)
        mut = "LegalizeMutations::changeElementSizeTo(%s, %s)" % (idx, ty)
    elif tr in ("MinScalarSameAs", "MaxScalarSameAs"):
        other = str(to["args"][0]["value"])
        op = ">" if tr == "MinScalarSameAs" else "<"
        cond = ("(Q.Types[%s].getScalarSizeInBits() %s Q.Types[%s]"
                ".getScalarSizeInBits())" % (other, op, idx))
        mut = "LegalizeMutations::changeElementSizeTo(%s, %s)" % (idx, other)
    elif tr == "MorePow2":
        cond = "numElementsNotPow2(%s)(Q)" % idx
        mut = "LegalizeMutations::moreElementsToNextPow2(%s)" % idx
    elif tr == "FewerToType":
        ty = cxx.value(to)
        cond = "(%s.isVector() && %s.getSizeInBits() > (%s).getSizeInBits())" % (v, v, ty)
        mut = "LegalizeMutations::changeElementTo(%s, %s)" % (idx, ty)
    elif tr == "BitcastToType":
        ty = cxx.value(to)
        mut = "LegalizeMutations::changeElementTo(%s, %s)" % (idx, ty)
    elif tr == "WholeTypeMutation":
        mut = ("[=](const LegalityQuery &Q) { return std::make_pair(unsigned(%s), %s); }"
               % (idx, cxx.value(to["args"][0])))
    elif tr == "WidenPow2OrMinSize":
        minimum = cxx.value(to)
        cond = ("(scalarOrEltNarrowerThan(%s, %s)(Q) || scalarOrEltSizeNotPow2(%s)(Q))"
                % (idx, minimum, idx))
        mut = "LegalizeMutations::widenScalarOrEltToNextPow2(%s, %s)" % (idx, minimum)
    else:
        return None, "no table translation for %s" % tr

    cond = conjunction(p, cond)
    action = rule["action"]
    out = []
    if not cond:
        # An unconditional action ends the rule set; a mutation declares
        # `auto M`, so it is scoped to keep later `M`s distinct.
        if not mut:
            out += emit_step(action, "  ")
        else:
            out.append("  {")
            out += emit_step(action, "    ", mut)
            out.append("  }")
    else:
        out.append("  if (%s) {" % cond)
        out += emit_step(action, "    ", mut)
        out.append("  }")
    return out, None


def emit_prologue(gs):
    """EmitPrologue(), :7560: every feature, type and type list, maybe_unused."""
    out = []
    for k, name, cond in gs["decls"]:
        if k == "feature":
            out.append("  [[maybe_unused]] const bool %s = %s;" % (name, cond))
    cxx = None
    from .llvm_inc import IncEmitter
    cxx = IncEmitter(gs, qvar="Q")
    for k, name, payload in gs["decls"]:
        if k == "type":
            out.append("  [[maybe_unused]] const LLT %s = %s;" % (name, payload))
        elif k == "select":
            out.append("  [[maybe_unused]] const LLT %s = %s;"
                       % (name, cxx._select_text(payload)))
    for k, name, payload in gs["decls"]:
        if k == "type_list":
            out.append("  [[maybe_unused]] const std::initializer_list<LLT> %s = {%s};"
                       % (name, ", ".join(payload)))
    out.append("")
    return out


EVAL_NOTE = [
    "// One evaluator per tabulated rule set.  Each begins with the same prologue",
    "// -gen-legalizer emits: the feature bools and LLT constants the .td rules",
    "// are written in terms of, so the table cannot disagree with the chain",
    "// about what a type or a feature means.",
]


def emit_evaluators(gs, P):
    from .llvm_inc import IncEmitter
    cxx = IncEmitter(gs, qvar="Q")
    prologue = emit_prologue(gs)
    out = list(EVAL_NOTE)
    opaque = []
    for i, rs in enumerate(gs["rulesets"]):
        out.append("")
        body, why = [], None
        for rule in rs["rules"]:
            text, reason = translate_core_rule(rule, cxx)
            if text is None:
                why = reason
                break
            body += text
        opaque.append(why)
        if why is not None:
            out.append("// %s is opaque: %s." % (rs["def"], why))
            out.append("// The reader falls back to the rule chain for this rule set.")
            continue
        out.append("static LegalizeActionStep %sEval%d(" % (P, i))
        out.append("    const %sSubtarget &Subtarget, const LegalityQuery &Q) {" % P)
        out += prologue
        out += body
        # endsUnconditional() is false for every core rule, so the tail is
        # always emitted.
        out.append("  return {LegalizeActions::Unsupported, 0, LLT{}};")
        out.append("}")

    lower = P[:1].lower() + P[1:]
    out.append("")
    out.append("/// Answer one query from a tabulated rule set.  False means the rule set")
    out.append("/// is opaque, and the caller uses the rule chain instead.")
    out.append("static std::optional<LegalizeActionStep> %sEvalTable(unsigned Table, "
               "const %sSubtarget &Subtarget," % (P, P))
    out.append("                         const LegalityQuery &Q) {")
    out.append("  switch (Table) {")
    for i, rs in enumerate(gs["rulesets"]):
        out.append("  case %d: // %s" % (i, rs["def"]))
        if opaque[i] is not None:
            out.append("    return std::nullopt;")
        else:
            out.append("    return %sEval%d(Subtarget, Q);" % (P, i))
    out.append("  default:")
    out.append("    return std::nullopt;")
    out.append("  }")
    out.append("}")
    return out


def emit_table(gs, P):
    out = emit_head(gs, P)
    out += emit_evaluators(gs, P)
    return "\n".join(out) + "\n"
