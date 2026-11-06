"""Facts about the DSL vocabulary that no single corpus can determine.

Everything here is a property of the language or of the compatibility layer it
targets, not of a target's rule set.  Each entry names the authority that fixes
it, so a stale value is a bug you can look up rather than a number to trust.
"""

# The eleven operators the core IR has, sorted the way
# `RecordKeeper::getAllDerivedDefinitions` returns them (by name).
# Authority: llvm/include/llvm/Target/LegalizerCore.td:173-204
# (widen, narrow, more, fewer, bitcast, ... scalarize), whose record names sort
# into this order.
CORE_OPERATORS = [
    "bitcast", "custom", "fewer", "legal", "libcall", "lower",
    "more", "narrow", "scalarize", "unsupported", "widen",
]

# The size of the TableGen compatibility layer, not of the DSL:
#   builders = number of `LegalizeBuilder` records,
#   entries  = number of `LegalizeLowering` records,
#   overloads = sum of each builder's `Formals` length.
# Authority: llvm/include/llvm/Target/LegalizerInfo.td at d48f5512a162,
# pinned by tests/artifacts/*.check.json (both targets report 50/64/64).
#
# These are exactly the numbers the "the API is not the language" argument
# turns on: fifty C++ builder methods and sixty-four overloads, against eleven
# operators and three rule forms.
BUILDER_VOCABULARY = {"builders": 50, "overloads": 64, "entries": 64}
