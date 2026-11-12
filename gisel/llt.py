"""Tuple LLT operations used by the query generator and the graph.

This is the single LLT module.  It owns both the evaluator's view
(`isScalar`/`sizeInBits`/mutation) and the generation view (spelling,
dimensions, neighbours); `gisel/eval.py` re-exports the evaluator names so
existing callers keep working.  Before this, `eval.py`, `axes.py` and
`domain.py` each had a copy and could disagree about the same tuple.

A tuple LLT is the evaluator's normal form:

    ("scalar"|"integer"|"float"|"bf16", bits)
    ("pointer", address_space, bits | "*")
    ("vector", lanes, scalable, elem)
    ("invalid",)
"""

from __future__ import annotations

# Scalar widths a `is_pow2` predicate is allowed to compare against.
POW2 = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512)

# LLVM pointers have a target-chosen width; 63/65 are spellable LLTs but not
# widths a subtarget can have.  Mutating into them would emit a boundary the
# configuration space cannot contain.
POINTER_BITS = (16, 32, 64, 128)

# LLVM IR has a closed set of float widths.  `f31`/`f33` are spellable LLTs
# (LLT::floatIEEE takes any size) but no IR produces one, and a target
# legalizer asserts when asked to legalize it, so a probe there is noise.
# 80 is deliberately absent: `x86_fp80` is not an IEEE format, LLT spells it
# `scalar(80)`, and `LLT::floatIEEE(80)` is unreachable -- a query spelled
# `f80` cannot even be constructed, so asking it would only abort the runner.
FLOAT_BITS = (16, 32, 64, 128)

KIND_ORDER = {"scalar": 0, "integer": 0, "float": 0, "bf16": 0,
              "vector": 1, "pointer": 2, "invalid": 3}


def spell(t) -> str:
    """The Core IR spelling, accepted by `eval.parse_case_llt`."""
    if t[0] == "invalid":
        return "LLT_invalid"
    if t[0] == "bf16":
        return "bf16"
    if t[0] == "pointer":
        return "p%d:%s" % (t[1], t[2])
    if t[0] == "vector":
        head = "nxv" if t[2] else "v"
        return head + str(t[1]) + spell(t[3])
    return {"scalar": "s", "integer": "i", "float": "f"}[t[0]] + str(t[1])


def scalar_bits(t):
    """The scalar width of a scalar-like or pointer LLT, else None."""
    if t[0] in ("scalar", "integer", "float"):
        return t[1]
    if t[0] == "bf16":
        return 16
    if t[0] == "pointer" and t[2] != "*":
        return t[2]
    return None


def lanes(t):
    return t[1] if t[0] == "vector" else None


def total_bits(t):
    """Total known-minimum bits, or None for a wildcard pointer/unknown."""
    if t[0] == "vector":
        elem = total_bits(t[3])
        return None if elem is None else t[1] * elem
    if t[0] == "pointer":
        return t[2] if t[2] != "*" else None
    if t[0] == "bf16":
        return 16
    if t[0] in ("scalar", "integer", "float"):
        return t[1]
    return None


def resize_bits(t, bits):
    """Same shape, scalar/element/pointer width set to ``bits``."""
    if bits is None or bits <= 0:
        return None
    if t[0] in ("scalar", "integer"):
        return (t[0], bits)
    if t[0] == "float":
        if bits not in FLOAT_BITS:
            return None
        return ("float", bits)
    if t[0] == "pointer":
        if bits not in POINTER_BITS:
            return None
        return ("pointer", t[1], bits)
    if t[0] == "vector":
        elem = resize_bits(t[3], bits)
        return None if elem is None else ("vector", t[1], t[2], elem)
    return None


def relane(t, count):
    if t[0] != "vector" or count <= 0:
        return None
    return scalar_or_vector(count, t[2], t[3])


def mutate(t, dim, n):
    if dim == "bits":
        return resize_bits(t, n)
    if dim == "bytes":
        return resize_bits(t, 8 * n)
    if dim == "lanes":
        return relane(t, n)
    return None


def neighbours(t):
    """Off-by-one spellings around one LLT, never used as a class witness."""
    out = set()
    bits = scalar_bits(t)
    if bits is not None:
        if t[0] == "float":
            out.update(("float", n) for n in FLOAT_BITS if n != bits)
        else:
            if bits > 1:
                out.add(resize_bits(t, bits - 1))
            out.add(resize_bits(t, bits + 1))
    count = lanes(t)
    if count is not None:
        if count > 1:
            out.add(relane(t, count - 1))
        out.add(relane(t, count + 1))
        # Lane-count predicates compare against small powers of two; the +-1
        # neighbours alone miss v4s8 when the literal is v16s8.
        for n in (1, 2, 4, 8, 16, 32, 64):
            out.add(relane(t, n))
        # Flipping scalability on a one-lane vector would spell a fixed
        # one-lane vector, which *is* its element type; `relane` collapses
        # that spelling, so the flip must not reintroduce it.
        if not (t[1] == 1 and t[2]):
            out.add((t[0], t[1], not t[2], t[3]))
    if t[0] == "bf16":
        out.add(("float", 16))
    return {x for x in out if x is not None and x != t}


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
