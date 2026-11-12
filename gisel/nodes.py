"""The core node vocabulary: what a node kind is, not how it is computed.

There are three consumers with three different jobs:

* ``eval`` evaluates value/boolean nodes;
* ``backend.core_json`` serialises the normal form;
* ``backend.llvm_inc`` spells predicates and mutations as C++.

They must agree on the *vocabulary* (which kinds exist and whether a kind is a
value or a boolean), but not on the implementation.  This module is only that
vocabulary.  It deliberately has no evaluator and no C++ strings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeSpec:
    sort: str
    # Number of positional children for documentation; -1 means "not fixed".
    # Validation does not enforce it: several kinds carry named fields
    # (``value``, ``elems``, ``index``) and a few spell a negated child as
    # ``arg``.  A wrong arity still fails in the consumer that knows the
    # shape; this table's job is to catch an unknown *kind* once.
    args: int = -1


VALUE_KINDS = {
    "int", "type", "slot", "imm", "memSlot", "elemOf", "scalarOf",
    "numElems", "bitsOf", "sizeOf", "sizeInBytesOf", "alignOf", "addrSpace",
    "memTy", "memOrdering", "memFailureOrdering", "ty", "sameAs", "select",
    "mul", "add", "sub", "urem", "udiv", "pow2Ceil", "pow2AtLeast",
    "pow2Min", "multipleOf",
    "alignTo", "intOfSize", "vecOf", "scalarOrVecOf", "eltTypeTo",
    "eltSizeTo", "divLanes", "replace", "set", "sortOf",
}

BOOL_KINDS = {
    "leaf", "true", "all", "any", "not", "nary", "isPow2", "isByteSized",
    "isBFloat16", "isFixedVector", "isFloat16", "in", "inPairs",
    "inTriples", "inMemDesc", "eq", "ne", "lt", "le", "gt", "ge",
}

# Literal tags that appear as operands (inside sets or comparisons), not as
# standalone evaluator nodes.
TAG_KINDS = {
    "pow2", "pow2Min", "minVectorSize",
    "kindScalar", "kindVector", "kindScalableVector", "kindPointer",
    "kindPointerVector",
    "orderingUnordered", "orderingMonotonic", "orderingAcquire",
    "orderingRelease", "orderingAcquireRelease",
    "orderingSequentiallyConsistent",
}

KINDS = {}
KINDS.update({kind: NodeSpec("value") for kind in VALUE_KINDS})
KINDS.update({kind: NodeSpec("bool") for kind in BOOL_KINDS})
KINDS.update({kind: NodeSpec("tag") for kind in TAG_KINDS})


def spec(kind):
    return KINDS.get(kind)


def known(node, sort=None):
    """True when ``node`` names a known kind (and, if given, the right sort)."""
    if not isinstance(node, dict):
        return False
    item = KINDS.get(node.get("kind"))
    return item is not None and (sort is None or item.sort == sort)


def known_any(node):
    return known(node)
