"""Tuple LLT operations used by the query generator and the graph.

The evaluator (`gisel/eval.py`) owns LLT *semantics*: parsing a Core IR
spelling, `isScalar`/`sizeInBits`, and the LLT operator== bag-of-bits rule.
This module owns the *generation* view of the same tuples: how to spell one,
which dimension it has, and what its neighbours are.  One copy, shared by
`cases`, `domain` and `graph`; before this a probe in `cases` and the graph's
node text could disagree about the same type.

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
    if count == 1 and not t[2]:
        return t[3]          # a fixed one-lane vector is the element type
    return ("vector", count, t[2], t[3])


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
