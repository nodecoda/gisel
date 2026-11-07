"""Emit the ``-gen-legalizer-check`` JSON from the schema-0.4 normal form.

Mirrors ``LegalizerCheckEmitter::run`` (LegalizerInfoEmitter.cpp:8004) and the
counters it prints from ``verifyLoweringRegistry`` (:4568).

Two kinds of number appear in that JSON, and they must not be confused:

* per-target counts (``rule_sets``, ``rules``, ``core_rules``, ``coverage``)
  are derived from the corpus.  ``Rules`` counts every entry in a rule set's
  ``Rules`` list, including ``ImmIdx``; ``Coverage`` counts the ``immIdx``
  markers, so ``rules == core_rules + legacy_rules + coverage``.
* vocabulary counts (``builders``, ``overloads``, ``entries``) describe the
  TableGen compatibility layer itself -- 50 ``LegalizeBuilder`` records and 64
  ``LegalizeLowering`` entries, the same for every target.  They are carried
  as provenance-stamped constants in ``gisel/vocab.py`` because they are not a
  property of the DSL; a target cannot change them.
"""

from .. import ast as A
from ..vocab import BUILDER_VOCABULARY, CORE_OPERATORS


def counts(gs):
    """Per-target counters, in the shape ``LoweringStats`` uses."""
    if not isinstance(gs, A.Program):
        raise TypeError("counts needs the language AST")
    rule_sets = len(gs.rulesets)
    core = sum(len(rs.rules) for rs in gs.rulesets)
    imm = sum(len(rs.coverage) for rs in gs.rulesets)
    return {
        "rule_sets": rule_sets,
        "rules": core + imm,
        "core_rules": core,
        "legacy_rules": 0,
        "coverage": imm,
    }


def emit_check(gs):
    c = counts(gs)
    v = BUILDER_VOCABULARY
    out = [
        "{",
        '  "builders": %d,' % v["builders"],
        '  "overloads": %d,' % v["overloads"],
        '  "entries": %d,' % v["entries"],
        '  "rule_sets": %d,' % c["rule_sets"],
        '  "rules": %d,' % c["rules"],
        '  "escapes": 0,',
        '  "entries_without_table_translation": 0,',
        '  "rule_sets_without_table_translation": 0,',
        '  "core_rules": %d,' % c["core_rules"],
        '  "legacy_rules": %d,' % c["legacy_rules"],
        '  "coverage": %d,' % c["coverage"],
        '  "core_operators": [' +
        ", ".join('"%s"' % op for op in CORE_OPERATORS) + "]",
        "}",
    ]
    return "\n".join(out) + "\n"
