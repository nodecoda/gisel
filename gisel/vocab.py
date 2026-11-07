"""Facts about the DSL vocabulary that no single corpus can determine.

Everything here is a property of the language or of the compatibility layer it
targets, not of a target's rule set.  Each entry names the authority that fixes
it, so a stale value is a bug you can look up rather than a number to trust.
"""

# The eleven operators the core IR has, in the frozen artifact order
# (widen, narrow, more, fewer, bitcast, ... scalarize).
CORE_OPERATORS = [
    "bitcast", "custom", "fewer", "legal", "libcall", "lower",
    "more", "narrow", "scalarize", "unsupported", "widen",
]

# Frozen compatibility counters, not a property of the DSL:
#   builders = 50, entries = 64, overloads = 64.
# Pinned by tests/artifacts/*.check.json (both targets report 50/64/64).
# They are the numbers the "the API is not the language" argument turns on:
# fifty C++ builder methods and sixty-four overloads, against eleven
# operators and three rule forms.
BUILDER_VOCABULARY = {"builders": 50, "overloads": 64, "entries": 64}
