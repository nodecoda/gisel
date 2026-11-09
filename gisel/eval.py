#!/usr/bin/env python3
"""Independent evaluator for the Core IR normal form (schema 0.4).

This is the Phase 2 reference implementation.  It reads a
`legalizer-spec-core` JSON document (the `-gen-legalizer-core` normal form),
a per-configuration feature truth table, and a list of queries (one JSON
object per line, the same shape as the frozen AArch64 oracle dump), and
answers each query with the triple

    (action, type_idx, new_type)

exactly as the hand-written C++ builder chain does.  It is independent of
the C++ emitter and does not parse any generated `.inc`.

Evaluation is first-match: rule sets in document order, rules inside a rule
set in `rule_index` order, the first rule whose effective guard is true wins.

The effective guard of a rule is `guard && shim_guard`, where `guard` is the
serialised `predicate` and `shim_guard` is the implicit size/count/vector test
the C++ shim adds for lattice operators (for example `widen slot pow2` only
fires when the slot is a scalar whose size is not a power of two).  Terminal
actions and whole-type `replace` mutations carry no implicit guard.

An unknown feature string, predicate node, value node, target form, or action
raises `EvalError` instead of guessing, matching the deliberate-no-defaults
contract of the earlier 0.3 evaluator.

Usage:
  python tools/core_eval_04.py \
      --doc ~/legalizer-baseline/aarch64.core.json \
      --features tests/aarch64-oracle/features.json \
      --cases tests/aarch64-oracle/a64_ref_dump.jsonl
"""
import argparse
import json
import re
import sys

NO_MUTATION_ACTIONS = {"Legal", "Lower", "Libcall", "Custom", "Unsupported"}
SCALARIZE_ACTION = "FewerElements"  # scalarize projects to FewerElements


class EvalError(Exception):
    def __init__(self, code, detail):
        Exception.__init__(self, "%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# LLT model
#
# LLTs are plain tuples; everything below is closed over this representation.
#   ("scalar", bits)                          ANY_SCALAR
#   ("integer", bits)                         INTEGER (extended LLT)
#   ("float", bits)                           IEEE float, bits in {16,32,64,128}
#   ("bf16",)                                 bfloat16
#   ("pointer", addrspace, bits)              POINTER
#   ("vector", lanes, scalable, elem)         fixed or scalable vector
#   ("invalid",)                              LLT_invalid
# ---------------------------------------------------------------------------

_FLOAT_BITS = {16, 32, 64, 128}


def is_scalar(t):
    """LLT::isScalar(): ANY_SCALAR, INTEGER and FLOAT are all scalar."""
    return t[0] in ("scalar", "integer", "float", "bf16")


def is_integer(t):
    return t[0] == "integer"


def is_float(t):
    return t[0] == "float" or t[0] == "bf16"


def is_float_ieee(t):
    return t[0] == "float"


def is_bf16(t):
    return t[0] == "bf16"


def is_pointer(t):
    return t[0] == "pointer"


def is_vector(t):
    return t[0] == "vector"


def is_scalable(t):
    return is_vector(t) and t[2]


def is_fixed_vector(t):
    return is_vector(t) and not t[2]


def is_pointer_vector(t):
    return is_vector(t) and t[3][0] == "pointer"


def is_valid(t):
    return t[0] != "invalid"


def scalar_size(t):
    """getScalarSizeInBits: element size for vectors, scalar/pointer width else."""
    if t[0] == "vector":
        return scalar_size(t[3])
    if t[0] == "pointer":
        return t[2]
    if t[0] == "bf16":
        return 16
    return t[1]


def size_in_bits(t):
    """(known_min_bits, scalable) for getSizeInBits."""
    if t[0] == "vector":
        elt, scalable = size_in_bits(t[3])
        return (elt * t[1], scalable or t[2])
    if t[0] == "pointer":
        return (t[2], False)
    if t[0] == "bf16":
        return (16, False)
    return (t[1], False)


def size_in_bytes(t):
    """getSizeInBytes: (min + 7) // 8."""
    bits, scalable = size_in_bits(t)
    return ((bits + 7) // 8, scalable)


def num_elems(t):
    # In the NDEBUG build the oracle runs in, getElementCount()'s
    # isVector() assert is compiled out and a scalar/pointer stores
    # ElementCount::getFixed(0), so getNumElements() returns 0 there.
    if is_vector(t):
        return t[1]
    return 0


def get_scalar_type(t):
    return t[3] if is_vector(t) else t


def get_element_type(t):
    assert is_vector(t)
    return t[3]


def get_address_space(t):
    assert t[0] == "pointer" or (is_vector(t) and t[3][0] == "pointer")
    if is_vector(t):
        return t[3][2]
    return t[1]


def change_element_type(t, new_elt):
    """changeElementType: vector keeps its lanes; scalar becomes new_elt."""
    if is_vector(t):
        return ("vector", t[1], t[2], new_elt)
    return new_elt


def change_element_size(t, new_size):
    """changeElementSize: invalid for pointers, keeps vector lanes."""
    assert t[0] != "pointer" and not is_pointer_vector(t)
    if is_vector(t):
        return ("vector", t[1], t[2], change_element_size(t[3], new_size))
    if is_integer(t):
        return ("integer", new_size)
    if is_float_ieee(t):
        return ("float", new_size)
    # bf16 and ANY_SCALAR both degrade to a plain scalar here, matching
    # LLT::changeElementSize (isFloatIEEE() is false for bf16).
    return ("scalar", new_size)


def scalar_or_vector(lanes, scalable, elem):
    """scalar-or-vector: one fixed lane is the element type itself."""
    if lanes == 1 and not scalable:
        return elem
    return ("vector", lanes, scalable, elem)


def change_element_count_div(t, n):
    """divLanes: element count / n, keeping the scalable flag."""
    assert is_vector(t)
    return scalar_or_vector(t[1] // n, t[2], t[3])


def fixed_vector(lanes, elem):
    # `vec_of(1, T)` is T, for the same reason `scalarOrVecOf` collapses it.
    return scalar_or_vector(lanes, False, elem)


def scalable_vector(lanes, elem):
    return ("vector", lanes, True, elem)


def integer_type(bits, extended=True):
    return ("integer", bits) if extended else ("scalar", bits)


def collapse_extended(t):
    """The runtime view of an LLT spelling.

    LLT stores INTEGER/FLOAT/bfloat16 as distinct kinds only when
    LLT::getUseExtended() is on; that flag is set by the target machine
    (AArch64, AMDGPU, WebAssembly), not by the IR.  With the flag off,
    float16 is just scalar(16) and integer(32) is scalar(32), so legality
    predicates and mutations see no difference.
    """
    if t[0] in ("integer", "float"):
        return ("scalar", t[1])
    if t[0] == "bf16":
        return ("scalar", 16)
    if t[0] == "vector":
        return ("vector", t[1], t[2], collapse_extended(t[3]))
    return t


def pow2ceil(x):
    # LLVM PowerOf2Ceil: 1 << ceil(log2(x)); for 0 returns 1.
    if x <= 1:
        return 1
    p = 1
    while p < x:
        p <<= 1
    return p


def is_pow2_32(x):
    return x != 0 and (x & (x - 1)) == 0


def align_to(x, n):
    return ((x + n - 1) // n) * n


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

_CORE_VEC_RE = re.compile(r"^(nxv|v)(\d+)(.*)$")
_CORE_SCALAR_RE = re.compile(r"^(s|i|f)(\d+)$")
_CORE_PTR_RE = re.compile(r"^p(\d+):(\d+|\*)$")
_ORACLE_VEC_RE = re.compile(r"^<(\d+|vscale x \d+) x (.*)>$")


def _parse_elem_spelling(s, oracle):
    if s == "bf16":
        return ("bf16",)
    m = _CORE_SCALAR_RE.match(s)
    if m:
        kind, bits = m.group(1), int(m.group(2))
        if kind == "s":
            return ("scalar", bits)
        if kind == "i":
            return ("integer", bits)
        return ("float", bits)
    if not oracle:
        m = _CORE_PTR_RE.match(s)
        if m:
            w = m.group(2)
            return ("pointer", int(m.group(1)), int(w) if w != "*" else "*")
    else:
        m = re.match(r"^p(\d+)$", s)
        if m:
            # The frozen oracle was produced with PointerBits=64.
            return ("pointer", int(m.group(1)), 64)
    raise EvalError("bad_llt", "cannot parse LLT element %r" % (s,))


def parse_core_llt(s, extended=True):
    """Canonical Core IR spelling: s32, i32, f32, bf16, p0:64, v4s32, nxv4s32."""
    return _parse_core_llt(s, extended)


def _parse_core_llt(s, extended):
    if s == "bf16":
        t = ("bf16",)
        return t if extended else ("scalar", 16)
    m = _CORE_VEC_RE.match(s)
    if m:
        lanes = int(m.group(2))
        scalable = m.group(1) == "nxv"
        elem = _parse_elem_spelling(m.group(3), oracle=False)
        # A fixed one-lane vector *is* the element type: LLT::vector() asserts
        # on ElementCount::getFixed(1) (isScalar() is true), so `v1s8` never
        # reaches a target.  Normalise instead of keeping an unanswerable type.
        t = elem if (lanes == 1 and not scalable) else (
            "vector", lanes, scalable, elem)
        return t if extended else collapse_extended(t)
    m = _CORE_PTR_RE.match(s)
    if m:
        w = m.group(2)
        return ("pointer", int(m.group(1)), int(w) if w != "*" else "*")
    t = _parse_elem_spelling(s, oracle=False)
    return t if extended else collapse_extended(t)


def parse_oracle_llt(s):
    """LLT::print spelling: s32, i32, f32, bf16, p0, <4 x s32>, <vscale x 4 x s32>."""
    if s == "LLT_invalid":
        return ("invalid",)
    if s == "bf16":
        return ("bf16",)
    m = _ORACLE_VEC_RE.match(s)
    if m:
        head, elem = m.group(1), m.group(2)
        if head.startswith("vscale"):
            lanes = int(head.split()[2])
            scalable = True
        else:
            lanes = int(head)
            scalable = False
        elem_t = _parse_elem_spelling(elem, oracle=True)
        if lanes == 1 and not scalable:
            return elem_t
        return ("vector", lanes, scalable, elem_t)
    return _parse_elem_spelling(s, oracle=True)


def parse_case_llt(s):
    """A frozen-case type: Core IR spelling or LLT::print spelling.

    Our own oracle dumps write `p0:32`/`v4s32` (kind and pointer width are
    explicit); the older AArch64 dump writes LLT::print (`<4 x s32>`, `p0`).
    """
    if s == "LLT_invalid":
        return ("invalid",)
    if s.startswith("<"):
        return parse_oracle_llt(s)
    try:
        return parse_core_llt(s)
    except EvalError:
        return parse_oracle_llt(s)   # `p0`: LLT::print drops the pointer width


def _is_scalar_like(t):
    """LLT::isScalar(): ANY_SCALAR, INTEGER and FLOAT are all 'scalar'."""
    return t[0] in ("scalar", "integer", "float", "bf16")


def has_wildcard(t):
    """A pointer whose width the configuration decides (`p0:*`)."""
    if t[0] == "pointer":
        return t[2] == "*"
    if t[0] == "vector":
        return has_wildcard(t[3])
    return False


def llt_eq(a, b):
    """LLT equality; a `p<as>:*` element matches any width (see core JSON)."""
    """LLT operator==, including the ANY_SCALAR bag-of-bits rule.

    If either side is ANY_SCALAR the comparison is `isScalar() && same
    scalar size`, so s32 == i32 == f32 while i32 != f32.  Vector equality
    recurses through element types, so <8 x s8> == v8i8.
    """
    if a == b:
        return True
    if a[0] == "pointer" and b[0] == "pointer":
        return a[1] == b[1] and (a[2] == "*" or b[2] == "*" or a[2] == b[2])
    if a[0] == "scalar" or b[0] == "scalar":
        return (_is_scalar_like(a) and _is_scalar_like(b)
                and scalar_size(a) == scalar_size(b))
    if is_vector(a) and is_vector(b):
        return (a[1] == b[1] and a[2] == b[2]
                and llt_eq(a[3], b[3]))
    return False


def values_equal(a, b):
    """Compare two Core IR values: LLTs use LLT operator==, rest use ==."""
    if isinstance(a, tuple) and isinstance(b, tuple):
        return llt_eq(a, b)
    return a == b


def fmt_oracle_llt(t):
    if not is_valid(t):
        return "LLT_invalid"
    if is_vector(t):
        if t[2]:
            return "<vscale x %d x %s>" % (t[1], fmt_oracle_llt(t[3]))
        return "<%d x %s>" % (t[1], fmt_oracle_llt(t[3]))
    if t[0] == "pointer":
        return "p%d" % t[1]
    if t[0] == "bf16":
        return "bf16"
    if t[0] == "float":
        return "f%d" % t[1]
    if t[0] == "integer":
        return "i%d" % t[1]
    if t[0] == "scalar":
        return "s%d" % t[1]
    return "LLT_invalid"


# ---------------------------------------------------------------------------
# Atomic ordering lattice (matching llvm/Support/AtomicOrdering.h)
# ---------------------------------------------------------------------------

_ORDERING_INDEX = {
    "NotAtomic": 0, "Unordered": 1, "Monotonic": 2, "Acquire": 4,
    "Release": 5, "AcquireRelease": 6, "SequentiallyConsistent": 7,
}
_ORDERING_FROM_TAG = {
    "orderingUnordered": "Unordered",
    "orderingMonotonic": "Monotonic",
    "orderingAcquire": "Acquire",
    "orderingRelease": "Release",
    "orderingAcquireRelease": "AcquireRelease",
    "orderingSequentiallyConsistent": "SequentiallyConsistent",
}

_STRONGER = {
    0: [False] * 8,
    1: [True, False, False, False, False, False, False, False],
    2: [True, True, False, False, False, False, False, False],
    4: [True, True, True, True, False, False, False, False],
    5: [True, True, True, False, False, False, False, False],
    6: [True, True, True, True, True, True, False, False],
    7: [True, True, True, True, True, True, True, False],
}
_AT_LEAST = {
    0: [True, False, False, False, False, False, False, False],
    1: [True, True, False, False, False, False, False, False],
    2: [True, True, True, False, False, False, False, False],
    4: [True, True, True, True, True, False, False, False],
    5: [True, True, True, False, False, True, False, False],
    6: [True, True, True, True, True, True, True, False],
    7: [True] * 8,
}


def is_stronger_than(a, b):
    return _STRONGER[a][b]


def is_at_least_or_stronger_than(a, b):
    return _AT_LEAST[a][b]


# ---------------------------------------------------------------------------
# Feature truth table
# ---------------------------------------------------------------------------

class Features:
    def __init__(self, table):
        self.table = table  # config -> {feature_string: bool}

    def get(self, config, feat):
        row = self.table.get(config)
        if row is None:
            raise EvalError("unknown_config", "no feature row for %r" % (config,))
        if feat not in row:
            raise EvalError("unknown_feature", "no truth value for %r in %r" % (feat, config))
        return row[feat]


# ---------------------------------------------------------------------------
# Document / query model
# ---------------------------------------------------------------------------

class MemDesc:
    __slots__ = ("memory_ty", "align", "ordering", "failure_ordering")

    def __init__(self, memory_ty, align, ordering="NotAtomic",
                 failure_ordering="NotAtomic"):
        self.memory_ty = memory_ty
        self.align = align
        self.ordering = ordering
        self.failure_ordering = failure_ordering


class Evaluator:
    def __init__(self, doc, features):
        self.features = features
        self.rulesets = doc["rulesets"]
        self.by_opcode = {}
        for rs_idx, rs in enumerate(self.rulesets):
            for op in rs["opcodes"]:
                self.by_opcode.setdefault(op, []).append(rs_idx)

    def extended(self, config):
        """LLT::getUseExtended() for this configuration.

        The per-config feature table names it explicitly; tables written
        before the key existed are extended, which is what the only
        extended-LLT targets (AArch64, AMDGPU, WebAssembly) use.
        """
        row = self.features.table.get(config)
        if row is None:
            raise EvalError("unknown_config", "no feature row for %r" % (config,))
        return row.get("LLT::getUseExtended()", True)

    # -- value nodes -------------------------------------------------------
    def value(self, node, types, mems, config, imms=()):
        k = node["kind"]
        a = node.get("args", [])
        if k == "int":
            return node["value"]
        if k == "type":
            return self.type_value(node["value"], types, mems, config, imms)
        if k == "slot":
            return types[node["index"]]
        if k == "imm":
            return imms[node["index"]]
        if k == "memSlot":
            return mems[a[0]["value"]]
        if k == "elemOf":
            return get_element_type(self.value(a[0], types, mems, config, imms))
        if k == "scalarOf":
            return get_scalar_type(self.value(a[0], types, mems, config, imms))
        if k == "numElems":
            return num_elems(self.value(a[0], types, mems, config, imms))
        if k == "bitsOf":
            return scalar_size(self.value(a[0], types, mems, config, imms))
        if k == "sizeOf":
            arg = a[0]
            if arg.get("kind") == "memSlot":
                m = self.value(arg, types, mems, config, imms)
                return size_in_bits(m.memory_ty)[0]
            return size_in_bits(self.value(arg, types, mems, config, imms))[0]
        if k == "sizeInBytesOf":
            return size_in_bytes(self.value(a[0], types, mems, config, imms))[0]
        if k == "alignOf":
            return self.value(a[0], types, mems, config, imms).align
        if k == "addrSpace":
            return get_address_space(self.value(a[0], types, mems, config, imms))
        if k == "memTy":
            return self.value(a[0], types, mems, config, imms).memory_ty
        if k == "memOrdering":
            return self.value(a[0], types, mems, config, imms).ordering
        if k == "memFailureOrdering":
            return self.value(a[0], types, mems, config, imms).failure_ordering
        if k == "ty":
            return self.value(a[0], types, mems, config, imms)
        if k == "sameAs":
            return types[a[0]["value"]]
        if k == "select":
            if self.bool_value(a[0], types, mems, config, imms):
                return self.value(a[1], types, mems, config, imms)
            return self.value(a[2], types, mems, config, imms)
        if k == "mul":
            return self.int_value(a[0], types, mems, config, imms) * self.int_value(a[1], types, mems, config, imms)
        if k == "add":
            return self.int_value(a[0], types, mems, config, imms) + self.int_value(a[1], types, mems, config, imms)
        if k == "sub":
            return self.int_value(a[0], types, mems, config, imms) - self.int_value(a[1], types, mems, config, imms)
        if k == "urem":
            return self.int_value(a[0], types, mems, config, imms) % self.int_value(a[1], types, mems, config, imms)
        if k == "udiv":
            return self.int_value(a[0], types, mems, config, imms) // self.int_value(a[1], types, mems, config, imms)
        if k == "pow2Ceil":
            return pow2ceil(self.int_value(a[0], types, mems, config, imms))
        if k == "pow2AtLeast":
            return max(pow2ceil(self.int_value(a[0], types, mems, config, imms)),
                       self.int_value(a[1], types, mems, config, imms))
        if k == "alignTo":
            return align_to(self.int_value(a[0], types, mems, config, imms),
                            self.int_value(a[1], types, mems, config, imms))
        if k == "intOfSize":
            return integer_type(self.int_value(a[0], types, mems, config, imms),
                                self.extended(config))
        if k == "vecOf":
            return fixed_vector(self.int_value(a[0], types, mems, config, imms),
                                self.llt_value(a[1], types, mems, config, imms))
        if k == "scalarOrVecOf":
            return scalar_or_vector(self.int_value(a[0], types, mems, config, imms),
                                    False,
                                    self.llt_value(a[1], types, mems, config, imms))
        if k == "eltTypeTo":
            return change_element_type(self.llt_value(a[0], types, mems, config, imms),
                                       self.llt_value(a[1], types, mems, config, imms))
        if k == "eltSizeTo":
            return change_element_size(self.llt_value(a[0], types, mems, config, imms),
                                       self.int_value(a[1], types, mems, config, imms))
        if k == "divLanes":
            return change_element_count_div(self.llt_value(a[0], types, mems, config, imms),
                                            self.int_value(a[1], types, mems, config, imms))
        if k == "replace":
            return self.value(a[0], types, mems, config, imms)
        raise EvalError("unknown_value", "value node %r" % (k,))

    def type_value(self, v, types, mems, config, imms=()):
        """A type-valued node: an LLT spelling, or a feature-selected pair.

        The core JSON writes a subtarget-dependent type as
        ``{"kind":"type","value":{"select":{...}}}`` (emitter ``coreTypeValue``);
        the branch is resolved here, not in the document.
        """
        if isinstance(v, str):
            return parse_core_llt(v, self.extended(config))
        sel = v["select"]
        if self.bool_value(sel["cond"], types, mems, config, imms):
            return self.type_value(sel["then"], types, mems, config, imms)
        return self.type_value(sel["else"], types, mems, config, imms)

    def int_value(self, node, types, mems, config, imms=()):
        v = self.value(node, types, mems, config, imms)
        if isinstance(v, bool) or not isinstance(v, int):
            raise EvalError("bad_int", "node %r is not an Int" % (node.get("kind"),))
        return v

    def llt_value(self, node, types, mems, config, imms=()):
        v = self.value(node, types, mems, config, imms)
        if not isinstance(v, tuple):
            raise EvalError("bad_llt", "node %r is not an LLT" % (node.get("kind"),))
        return v

    # -- boolean nodes -----------------------------------------------------
    def bool_value(self, node, types, mems, config, imms=()):
        k = node["kind"]
        a = node.get("args", [])
        if k == "leaf":
            name = node.get("name")
            if name == "true":
                return True
            if name == "hasFeature":
                return self.features.get(config, a[0])
            if name == "opaque":
                # A host predicate the evaluator cannot answer.  It is a hole,
                # not False: `rule_matches` maps it to None and the graph
                # counts the state as opaque.
                raise EvalError("opaque", "host predicate %r" % (a[0],))
            raise EvalError("unknown_leaf", "leaf %r" % (name,))
        if k == "true":
            return True
        if k == "all":
            return all(self.bool_value(c, types, mems, config, imms) for c in a)
        if k == "any":
            return any(self.bool_value(c, types, mems, config, imms) for c in a)
        if k == "not":
            # schema-0.4 writes `{"kind":"not","arg":...}` for a negated DAG
            # predicate and `args` for a CoreNot node; accept both.
            child = a[0] if a else node["arg"]
            return not self.bool_value(child, types, mems, config, imms)
        if k == "nary":
            # `{"kind":"nary","op":"all_of"|"any_of","args":[...]}`: the
            # DAG-shaped spelling the emitter uses inside select guards.
            op = node.get("op")
            if op == "all_of":
                return all(self.bool_value(c, types, mems, config, imms) for c in a)
            if op == "any_of":
                return any(self.bool_value(c, types, mems, config, imms) for c in a)
            raise EvalError("unknown_nary", "nary op %r" % (op,))
        if k == "isPow2":
            return is_pow2_32(self.int_value(a[0], types, mems, config, imms))
        if k == "isByteSized":
            bits, _ = size_in_bits(self.llt_value(a[0], types, mems, config, imms))
            return bits % 8 == 0
        if k == "isBFloat16":
            return is_bf16(self.llt_value(a[0], types, mems, config, imms))
        if k == "isFixedVector":
            return is_fixed_vector(
                self.llt_value(a[0], types, mems, config, imms))
        if k == "isFloat16":
            t = self.llt_value(a[0], types, mems, config, imms)
            return t[0] == "float" and t[1] == 16
        if k in ("in", "inPairs", "inTriples", "inMemDesc"):
            return self.membership(node, types, mems, config, imms)
        if k in ("eq", "ne", "lt", "le", "gt", "ge"):
            return self.compare(node, types, mems, config, imms)
        raise EvalError("unknown_bool", "bool node %r" % (k,))

    # -- membership --------------------------------------------------------
    def _slot_index(self, node):
        if node.get("kind") == "slot":
            return node["index"]
        raise EvalError("bad_slot", "tuple membership needs a literal slot")

    def membership(self, node, types, mems, config, imms=()):
        k = node["kind"]
        a = node["args"]
        if k == "inMemDesc":
            i0 = self._slot_index(a[0])
            i1 = self._slot_index(a[1])
            mnode = a[2]
            if mnode.get("kind") != "memSlot":
                raise EvalError("bad_memslot", "inMemDesc third operand")
            m = mems[mnode["args"][0]["value"]]
            elems = a[3]["elems"]
            for e in elems:
                t0 = self.type_value(e[0], types, mems, config, imms)
                t1 = self.type_value(e[1], types, mems, config, imms)
                mt = self.type_value(e[2], types, mems, config, imms)
                align = e[3]
                # TypePairAndMemDesc::isCompatible compares TypeSize, not
                # the known-minimum bit count: `<vscale x 4 x s8>` is
                # scalable-32 and does not equal the fixed-32 `s32`.
                size_ok = (llt_eq(m.memory_ty, mt) if has_wildcard(mt)
                           else size_in_bits(m.memory_ty) == size_in_bits(mt))
                if (llt_eq(types[i0], t0) and llt_eq(types[i1], t1)
                        and m.align >= align and size_ok):
                    return True
            return False

        lhs = a[0]
        rhs = a[-1]
        nslots = len(a) - 1

        if k == "inPairs":
            i0 = self._slot_index(a[0]); i1 = self._slot_index(a[1])
            arity = rhs.get("arity", 2)
            for e in rhs["elems"]:
                if (llt_eq(types[i0], self.type_value(e[0], types, mems, config, imms))
                        and llt_eq(types[i1], self.type_value(e[1], types, mems, config, imms))):
                    return True
            return False
        if k == "inTriples":
            i0 = self._slot_index(a[0]); i1 = self._slot_index(a[1]); i2 = self._slot_index(a[2])
            for e in rhs["elems"]:
                if (llt_eq(types[i0], self.type_value(e[0], types, mems, config, imms))
                        and llt_eq(types[i1], self.type_value(e[1], types, mems, config, imms))
                        and llt_eq(types[i2], self.type_value(e[2], types, mems, config, imms))):
                    return True
            return False

        # one-slot `in`
        if rhs.get("kind") == "set" and rhs.get("of") == "Int":
            if lhs.get("kind") != "imm":
                raise EvalError("bad_int_set", "an Int set can only test an imm")
            return imms[lhs["index"]] in rhs["elems"]
        if rhs.get("kind") == "clamp":
            v = self.int_value(lhs, types, mems, config, imms)
            lo = rhs["args"][0]["value"]
            hi = rhs["args"][1]["value"]
            return lo <= v <= hi
        if rhs.get("kind") == "type":
            return llt_eq(self.llt_value(lhs, types, mems, config, imms),
                          self.type_value(rhs["value"], types, mems, config, imms))
        if rhs.get("kind") == "set" and rhs.get("of") == "Type":
            v = self.llt_value(lhs, types, mems, config, imms)
            for e in rhs["elems"]:
                if llt_eq(v, self.type_value(e, types, mems, config, imms)):
                    return True
            return False
        if rhs.get("kind") == "set" and rhs.get("of") == "Kind":
            # Lhs must be SortOf; the emitter lowers it to a disjunction of
            # kind predicates over the SortOf operand.
            if lhs.get("kind") != "sortOf":
                raise EvalError("bad_kind_set", "Kind set can only test SortOf")
            t = self.llt_value(lhs["args"][0], types, mems, config, imms)
            for e in rhs["elems"]:
                if _kind_predicate(e, t):
                    return True
            return False
        raise EvalError("unknown_set", "set %r" % (rhs.get("kind"),))

    # -- comparisons -------------------------------------------------------
    def compare(self, node, types, mems, config, imms=()):
        k = node["kind"]
        lhs = node["args"][0]
        rhs = node["args"][1]
        if lhs.get("kind") == "sortOf":
            t = self.llt_value(lhs["args"][0], types, mems, config, imms)
            pred = _kind_predicate(rhs.get("kind"), t)
            return (not pred) if k == "ne" else pred
        if lhs.get("kind") in ("memOrdering", "memFailureOrdering"):
            v = self.value(lhs, types, mems, config, imms)
            o = _ORDERING_FROM_TAG.get(rhs.get("kind"))
            if o is None:
                raise EvalError("bad_ordering", "not an ordering tag: %r" % (rhs.get("kind"),))
            vi = _ORDERING_INDEX[v]
            oi = _ORDERING_INDEX[o]
            if k == "eq":
                return vi == oi
            if k == "ne":
                return vi != oi
            if k == "ge":
                return is_at_least_or_stronger_than(vi, oi)
            if k == "gt":
                return is_stronger_than(vi, oi)
            if k == "le":
                return not is_stronger_than(vi, oi)
            if k == "lt":
                return not is_at_least_or_stronger_than(vi, oi)
            raise EvalError("bad_ordering_cmp", k)
        lv = self.value(lhs, types, mems, config, imms)
        rv = self.value(rhs, types, mems, config, imms)
        if k == "eq":
            return values_equal(lv, rv)
        if k == "ne":
            return not values_equal(lv, rv)
        if k == "lt":
            return lv < rv
        if k == "le":
            return lv <= rv
        if k == "gt":
            return lv > rv
        return lv >= rv


def _kind_predicate(tag, t):
    """SortOf tag -> LLT kind predicate."""
    if tag == "kindScalar":
        return is_scalar(t)
    if tag == "kindVector":
        return is_vector(t)
    if tag == "kindScalableVector":
        return is_scalable(t)
    if tag == "kindPointer":
        return is_pointer(t)
    if tag == "kindPointerVector":
        return is_pointer_vector(t)
    raise EvalError("bad_kind", "kind tag %r" % (tag,))


# ---------------------------------------------------------------------------
# Shim: implicit guard + new_type for (op, on-form, to-form)
# ---------------------------------------------------------------------------

def _slot_of(on_node):
    if on_node.get("kind") == "slot":
        return on_node["index"]
    if on_node.get("kind") in ("elemOf", "scalarOf"):
        inner = on_node["args"][0]
        if inner.get("kind") != "slot":
            raise EvalError("bad_on", "nested ElemOf has no type-index projection")
        return inner["index"]
    raise EvalError("bad_on", "observation is not a slot/elemOf")


def shim_guard_and_newtype(op, on_node, to_node, types, mems, ev, config,
                           imms=()):
    """Return (implicit_guard, new_type) for a matched rule.

    `new_type` is an LLT tuple; ("invalid",) means "not mutated".  When the
    implicit guard is false the mutation is deliberately not computed, exactly
    as the C++ shim's `actionIf` skips the mutation lambda for a query that
    fails its size/count test.
    """
    if on_node is None:
        # Terminal action: guard is the whole rule.
        return True, ("invalid",)
    idx = _slot_of(on_node)
    on_form = {"elemOf": "elem", "scalarOf": "scalar"}.get(
        on_node.get("kind"), "slot")

    if to_node is None:
        # scalarize
        t = types[idx]
        if not is_vector(t):
            return False, ("invalid",)
        return True, get_element_type(t)

    if to_node.get("kind") == "int":
        to_form = "int"
        to_int = to_node["value"]
    else:
        to_form = to_node["kind"]

    t = types[idx]
    ssz = scalar_size(t)
    size, _ = size_in_bits(t)

    # Whole-type mutation: the target is the rule's own type expression.
    if to_form == "replace":
        return True, ev.llt_value(to_node["args"][0], types, mems, config, imms)

    if op == "widen":
        if on_form == "slot" and to_form in ("select", "int"):
            minsz = ev.int_value(to_node, types, mems, config, imms)
            guard = (ssz < minsz) or (not is_pow2_32(ssz))
            if not guard:
                return False, ("invalid",)
            return True, change_element_size(t, max(pow2ceil(ssz), minsz))
        if to_form == "pow2":
            if on_form == "slot":
                guard = is_scalar(t) and not is_pow2_32(size)
            else:
                guard = not is_pow2_32(ssz)
            if not guard:
                return False, ("invalid",)
            return True, change_element_size(t, pow2ceil(ssz))
        if to_form == "pow2Min":
            n = ev.int_value(to_node["args"][0], types, mems, config, imms)
            if on_form == "slot":
                guard = is_scalar(t) and not is_pow2_32(size)
            else:
                guard = not is_pow2_32(ssz)
            if not guard:
                return False, ("invalid",)
            return True, change_element_size(t, max(pow2ceil(ssz), n))
        if to_form == "multipleOf":
            n = ev.int_value(to_node["args"][0], types, mems, config, imms)
            if on_form == "slot":
                guard = is_scalar(t) and (size % n != 0)
            else:
                guard = ssz % n != 0
            if not guard:
                return False, ("invalid",)
            return True, change_element_size(t, align_to(ssz, n))
        if to_form == "ty":
            target = ev.llt_value(to_node["args"][0], types, mems, config, imms)
            tsz = scalar_size(target)
            if on_form == "slot":
                guard = is_scalar(t) and size < tsz
            else:
                guard = ssz < tsz
            if not guard:
                return False, ("invalid",)
            return True, change_element_size(t, tsz)
        if to_form == "sameAs":
            k = to_node["args"][0]["value"]
            other = scalar_size(types[k])
            if not isinstance(other, int):
                raise EvalError("unknown_width",
                                "same_as(%d) has no known scalar width" % k)
            guard = other > ssz
            if not guard:
                return False, ("invalid",)
            return True, change_element_size(t, other)
        if to_form == "minVectorSize":
            n = to_node["args"][0]["value"]
            if not (is_fixed_vector(t) and size < n):
                return False, ("invalid",)
            num = num_elems(t)
            new_elt = change_element_size(get_element_type(t), n // num)
            return True, fixed_vector(num, new_elt)
        raise EvalError("unknown_shim", "%s %s %s" % (op, on_form, to_form))

    if op == "narrow":
        if to_form == "ty":
            target = ev.llt_value(to_node["args"][0], types, mems, config, imms)
            tsz = scalar_size(target)
            if on_form == "slot":
                guard = is_scalar(t) and size > tsz
            else:
                guard = ssz > tsz
            if not guard:
                return False, ("invalid",)
            return True, change_element_size(t, tsz)
        if to_form == "sameAs":
            k = to_node["args"][0]["value"]
            other = scalar_size(types[k])
            if not isinstance(other, int):
                raise EvalError("unknown_width",
                                "same_as(%d) has no known scalar width" % k)
            guard = other < ssz
            if not guard:
                return False, ("invalid",)
            return True, change_element_size(t, other)
        raise EvalError("unknown_shim", "%s %s %s" % (op, on_form, to_form))

    if op == "more":
        if to_form == "pow2":
            if not (is_fixed_vector(t) and not is_pow2_32(num_elems(t))):
                return False, ("invalid",)
            return True, fixed_vector(pow2ceil(num_elems(t)), get_element_type(t))
        raise EvalError("unknown_shim", "%s %s %s" % (op, on_form, to_form))

    if op == "fewer":
        if to_form == "ty":
            target = ev.llt_value(to_node["args"][0], types, mems, config, imms)
            tsize, _ = size_in_bits(target)
            if not (is_vector(t) and size > tsize):
                return False, ("invalid",)
            return True, change_element_type(t, target)
        raise EvalError("unknown_shim", "%s %s %s" % (op, on_form, to_form))

    if op == "bitcast":
        if to_form == "ty":
            target = ev.llt_value(to_node["args"][0], types, mems, config, imms)
            return True, change_element_type(t, target)
        raise EvalError("unknown_shim", "%s %s %s" % (op, on_form, to_form))

    raise EvalError("unknown_shim", "%s %s %s" % (op, on_form, to_form))

# ---------------------------------------------------------------------------
# Query evaluation
# ---------------------------------------------------------------------------

def evaluate(evaluator, config, opcode, types, mems, imms=()):
    idxs = evaluator.by_opcode.get(opcode)
    if idxs is None:
        raise EvalError("no_rules", "opcode %r has no rule sets" % (opcode,))
    for rs_idx in idxs:
        rs = evaluator.rulesets[rs_idx]
        for rule in rs["rules"]:
            if not evaluator.bool_value(rule["predicate"], types, mems, config, imms):
                continue
            guard, new_type = shim_guard_and_newtype(
                rule.get("op"), rule.get("on"), rule.get("to"),
                types, mems, evaluator, config, imms)
            if not guard:
                continue
            action = rule["action"]
            type_idx = rule.get("type_idx", 0)
            return action, type_idx, new_type
    # LegalizerInfo::getAction falls back to Unsupported when no rule fires.
    return "Unsupported", 0, ("invalid",)


def evaluate_with_rule(evaluator, config, opcode, types, mems, imms=()):
    """Evaluate once and also return the winning ``(ruleset, rule)``.

    ``evaluate`` is the public answer API and deliberately keeps its original
    three-value return shape.  Graph construction needs provenance to label
    edges and to distinguish a real ``unsupported`` rule from the fallback
    returned when no rule matched, so this is the additive variant.
    """
    idxs = evaluator.by_opcode.get(opcode)
    if idxs is None:
        raise EvalError("no_rules", "opcode %r has no rule sets" % (opcode,))
    for rs_idx in idxs:
        rs = evaluator.rulesets[rs_idx]
        for rule_idx, rule in enumerate(rs["rules"]):
            if not evaluator.bool_value(rule["predicate"], types, mems,
                                        config, imms):
                continue
            guard, new_type = shim_guard_and_newtype(
                rule.get("op"), rule.get("on"), rule.get("to"),
                types, mems, evaluator, config, imms)
            if not guard:
                continue
            return (rule["action"], rule.get("type_idx", 0), new_type,
                    (rs_idx, rule_idx))
    return "Unsupported", 0, ("invalid",), None


def rule_matches(evaluator, config, rule, types, mems, imms=()):
    """Three-valued match test for one rule, including the shim guard.

    ``evaluate_with_rule`` only reports the winner.  Building the quotient
    graph needs to know whether *each* rule matches, because the implicit
    guard (``is_pow2``/``is_scalar``/element count) narrows a rule beyond its
    explicit predicate and therefore takes part in the observation.  ``None``
    means an opaque leaf; it is not ``False``.
    """
    try:
        if evaluator.bool_value(rule["predicate"], types, mems,
                                config, imms) is not True:
            return False
        guard, _new_type = shim_guard_and_newtype(
            rule.get("op"), rule.get("on"), rule.get("to"),
            types, mems, evaluator, config, imms)
        return bool(guard)
    except (EvalError, IndexError, KeyError, TypeError, ValueError,
            ZeroDivisionError, AssertionError):
        return None


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def load_doc(path):
    with open(path) as f:
        doc = json.load(f)
    if doc.get("version") != "0.4":
        raise EvalError("bad_version", "expected schema 0.4, got %r" % (doc.get("version"),))
    return doc


def load_features(path):
    with open(path) as f:
        return Features(json.load(f))


def prepare_query(evaluator, q):
    """Parse one query line the way the target's ``LLT::print`` spells it.

    Returns ``(types, mems, imms, collapse)``.  ``collapse`` is the inverse of
    the extended-kind view, so a caller that compares against a frozen dump
    normalises its expected type the same way.
    """
    ext = evaluator.extended(q["config"])
    collapse = (lambda t: t) if ext else collapse_extended
    types = [collapse(parse_case_llt(s)) for s in q["types"]]
    mems = []
    if q["mem"] is not None:
        m = q["mem"]
        ordering, failure = ((m[2], m[3]) if len(m) >= 4
                             else ("NotAtomic", "NotAtomic"))
        mems.append(MemDesc(collapse(parse_case_llt(m[0])), m[1],
                            ordering, failure))
    return types, mems, q.get("imms") or [], collapse


def answer_queries(evaluator, cases_path, out_path):
    """Answer expectation-free queries in the A/B runner's JSONL shape.

    ``gisel cases`` emits questions; a compiled legalizer answers them.  This
    writes the evaluator's answers to the same questions in the same shape, so
    ``tools/ab/diff.py`` can tell whether the generated C++ still agrees with the
    model it was generated from.  A line the evaluator cannot answer is written
    as ``unanswerable`` so the output stays parallel to the input.
    """
    total = 0
    errors = 0
    first_failure = None
    action_counts = {}
    rows = []
    with open(cases_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            total += 1
            types, mems, imms, _collapse = prepare_query(evaluator, q)
            try:
                action, type_idx, new_type = evaluate(
                    evaluator, q["config"], q["name"], types, mems, imms)
            except EvalError as e:
                errors += 1
                if first_failure is None:
                    first_failure = "%s %s: %s" % (q["config"], q["name"], e)
                rows.append(json.dumps({
                    "config": q["config"], "name": q["name"],
                    "types": q["types"], "mem": q["mem"],
                    "imms": q.get("imms") or [], "status": "unanswerable",
                    "reason": str(e)}))
                continue
            action_counts[action] = action_counts.get(action, 0) + 1
            new_type_str = (fmt_oracle_llt(new_type) if new_type is not None
                            else "LLT_invalid")
            rows.append(json.dumps({
                "config": q["config"], "name": q["name"],
                "types": q["types"], "mem": q["mem"],
                "imms": q.get("imms") or [], "action": action,
                "type_idx": type_idx, "new_type": new_type_str}))
    with open(out_path, "w") as f:
        f.write("\n".join(rows) + "\n")
    return total, errors, first_failure, action_counts


def run_cases(evaluator, cases_path):
    total = 0
    disagree = 0
    errors = 0
    first_failure = None
    action_counts = {}
    with open(cases_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            q = json.loads(line)
            total += 1
            types, mems, imms, collapse = prepare_query(evaluator, q)
            try:
                action, type_idx, new_type = evaluate(
                    evaluator, q["config"], q["name"], types, mems, imms)
            except EvalError as e:
                errors += 1
                if first_failure is None:
                    first_failure = "ERROR %s: %s" % (q, e)
                continue
            new_type_str = fmt_oracle_llt(new_type) if new_type is not None else "LLT_invalid"
            want_new = collapse(parse_case_llt(q["new_type"]))
            action_counts[action] = action_counts.get(action, 0) + 1
            if (action != q["action"] or type_idx != q["type_idx"]
                    or new_type != want_new):
                disagree += 1
                if first_failure is None:
                    first_failure = (
                        "%s %s %s mem=%s: got (%s,%d,%s) want (%s,%d,%s)"
                        % (q["config"], q["name"], q["types"], q["mem"],
                           action, type_idx, new_type_str,
                           q["action"], q["type_idx"], q["new_type"]))
    return total, disagree, errors, first_failure, action_counts


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True)
    ap.add_argument("--features", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--answers", metavar="OUT", default=None,
                    help="answer expectation-free cases to OUT instead of "
                         "checking them against frozen expectations")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    doc = load_doc(args.doc)
    features = load_features(args.features)
    evaluator = Evaluator(doc, features)

    if args.answers:
        total, errors, first_failure, counts = answer_queries(
            evaluator, args.cases, args.answers)
        print("cases=%d errors=%d" % (total, errors))
        print("actions:", json.dumps(counts, sort_keys=True))
        if first_failure is not None:
            print("first failure:", first_failure)
        return 1 if errors else 0

    total, disagree, errors, first_failure, counts = run_cases(
        evaluator, args.cases)

    print("cases=%d disagreements=%d errors=%d" % (total, disagree, errors))
    print("actions:", json.dumps(counts, sort_keys=True))
    if first_failure is not None:
        print("first failure:", first_failure)
    if disagree or errors:
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
