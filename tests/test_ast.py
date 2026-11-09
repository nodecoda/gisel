"""The front end produces the language AST, not a record-shaped model.

There is no TableGen/record adapter any more: the tests pin the structured
type positions and the renderer-local names the C++ backend consumes.
"""

import unittest
from pathlib import Path

from gisel import ast as A

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "corpus"
CORPORA = ("AArch64LegalizerInfo", "M68kLegalizerInfo",
           "PowerPCLegalizerInfo", "RISCVLegalizerInfo",
           "WebAssemblyLegalizerInfo", "X86LegalizerInfo")


def text_of(name):
    return (CORPUS / (name + ".gisel")).read_text()


class StructuredTypes(unittest.TestCase):
    """No record name may survive in a rule's type positions."""

    LLTS = (A.Scalar, A.Integer, A.Float, A.BFloat16, A.Pointer, A.Vector)

    def _walk(self, node, where):
        if isinstance(node, dict):
            if node.get("kind") == "type":
                value = node["value"]
                self.assertIsInstance(
                    value, self.LLTS + (A.SelectValue, A.SetValue),
                    "%s: record-shaped type value %r" % (where, value))
            for v in node.values():
                self._walk(v, where)
        elif isinstance(node, (list, tuple)):
            for v in node:
                self._walk(v, where)

    def test_rule_types_are_structured(self):
        for name in CORPORA:
            prog = A.parse_program(text_of(name))
            for rs in prog.rulesets:
                for rule in rs.rules:
                    for field in (rule.on, rule.to, rule.predicate):
                        self._walk(field, "%s:%d" % (name, rule.line))

    def test_named_types_are_llt_values(self):
        for name in CORPORA:
            prog = A.parse_program(text_of(name))
            for d in prog.decls:
                if isinstance(d, A.NamedType):
                    self.assertIsInstance(d.llt, self.LLTS, d.name)
                    self.assertTrue(A.llt_text(d.llt))


class RendererNames(unittest.TestCase):
    """C++ declaration names are computed at the .inc exit, not stored."""

    def test_nametable_round_trips_every_unambiguous_named_type(self):
        for name in CORPORA:
            prog = A.parse_program(text_of(name))
            names = A.NameTable(prog)
            for d in prog.decls:
                if not isinstance(d, A.NamedType):
                    continue
                same = [x for x in prog.decls
                        if isinstance(x, A.NamedType) and x.llt == d.llt]
                if len(same) == 1:
                    self.assertEqual(names.value_name(d.llt), d.name)


class FeatureNamePredicates(unittest.TestCase):
    """A declared `feature NAME` is a boolean primary in rule predicates."""

    def test_feature_name_equals_inline_feature_call(self):
        src = (
            "feature HasAVX = Subtarget.hasAVX()\n"
            "type X86_Vec256 = LLT::fixed_vector(8, 32)\n"
            "ruleset X_ADD: G_ADD\n"
            "    legal (HasAVX and in(slot(0), X86_Vec256))\n"
        )
        prog = A.parse_program(src)
        pred = prog.rulesets[0].rules[0].predicate
        self.assertEqual(pred["kind"], "all")
        leaf = pred["args"][0]
        self.assertEqual(leaf, {"kind": "leaf", "name": "hasFeature",
                                "args": ["Subtarget.hasAVX()"]})

    def test_feature_name_matches_inline_spelling_semantics(self):
        by_name = A.parse_program(
            "feature HasAVX = Subtarget.hasAVX()\n"
            "ruleset X: G_ADD\n"
            "    legal HasAVX\n")
        by_inline = A.parse_program(
            "feature HasAVX = Subtarget.hasAVX()\n"
            "ruleset X: G_ADD\n"
            '    legal feature("Subtarget.hasAVX()")\n')
        self.assertEqual(by_name.rulesets[0].rules[0].predicate,
                         by_inline.rulesets[0].rules[0].predicate)


class Canonicalisation(unittest.TestCase):
    def test_one_rule_set_per_opcode(self):
        for name in CORPORA:
            prog = A.parse_program(text_of(name))
            canon = A.canonicalize_rulesets(prog.rulesets)
            ops = [op for rs in canon for op in rs.opcodes]
            self.assertEqual(len(ops), len(set(ops)), name)


class TableGenFreeModel(unittest.TestCase):
    """`include` survives only as frozen-corpus input, not as a model node."""

    def test_include_lines_are_accepted_and_dropped(self):
        prog = A.parse_program('include "llvm/Target/Target.td"\n'
                               "type s32 = LLT::scalar(32)\n")
        self.assertFalse(hasattr(prog, "includes"))
        self.assertEqual([d.name for d in prog.decls], ["s32"])

    def test_malformed_include_is_still_a_parse_error(self):
        with self.assertRaises(ValueError):
            A.parse_program("include llvm/Target/Target.td\n")


if __name__ == "__main__":
    unittest.main()
