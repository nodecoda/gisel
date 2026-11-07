"""Case generation: equivalence classes, boundaries, outside points."""

import tempfile
import unittest
from pathlib import Path

from gisel import cases, eval as E

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "corpus"
ORACLE = ROOT / "tests" / "cases"

FIXTURE = """\
type s8 = LLT::scalar(8)
type s16 = LLT::scalar(16)
type s32 = LLT::scalar(32)
type s64 = LLT::scalar(64)

ruleset B_ADD: G_ADD
    legal (bits_of(slot(0)) == 32)
    legal (bits_of(slot(0)) == 64)
"""

SHADOWED = """\
type s32 = LLT::scalar(32)

ruleset B_ADD: G_ADD
    legal in(slot(0), s32)
    legal in(slot(0), s32)
"""

GATED = """\
feature F = Subtarget.hasF()
type s32 = LLT::scalar(32)

ruleset B_ADD: G_ADD
    legal (feature("Subtarget.hasF()") and in(slot(0), s32))
"""


def write(d, text):
    path = Path(d) / "t.gisel"
    path.write_text(text)
    return path


def build(text):
    with tempfile.TemporaryDirectory() as d:
        doc = cases.document(write(d, text))
    features = cases.derive_features(doc)
    return doc, features, cases.generate(doc, features)


class Shapes(unittest.TestCase):
    def test_three_kinds(self):
        doc, features, gen = build(FIXTURE)
        kinds = {c.kind for c in gen.cases}
        self.assertEqual(kinds, set(cases.KINDS))

    def test_equivalence_is_one_witness_per_rule(self):
        doc, features, gen = build(FIXTURE)
        eq = [c for c in gen.cases if c.kind == "equivalence"]
        self.assertEqual({(c.config, c.rule) for c in eq},
                         {("all", 0), ("all", 1), ("none", 0), ("none", 1)})
        self.assertEqual({c.types[0] for c in eq}, {"s32", "s64"})

    def test_boundary_is_an_actual_transition(self):
        doc, features, gen = build(FIXTURE)
        types = {c.types[0] for c in gen.cases if c.kind == "boundary"}
        self.assertEqual(types, {"s31", "s33", "s63", "s65"})

    def test_outside_falls_back_to_unsupported(self):
        doc, features, gen = build(FIXTURE)
        evaluator = E.Evaluator(doc, features)
        outside = [c for c in gen.cases if c.kind == "outside"]
        self.assertTrue(outside)
        for case in outside:
            self.assertIsNone(cases.outcome(evaluator, case))
            action, _, _ = E.evaluate(evaluator, case.config, case.opcode,
                                      cases._parse(case.types), [])
            self.assertEqual(action, "Unsupported")

    def test_equivalence_tag_names_the_rule_that_fires(self):
        doc, features, gen = build(FIXTURE)
        evaluator = E.Evaluator(doc, features)
        for case in gen.cases:
            if case.kind != "equivalence":
                continue
            res = cases.outcome(evaluator, case)
            self.assertIsInstance(res, tuple, case)
            self.assertEqual(res[1], case.rule, case)

    def test_shadowed_rule_is_reported_not_sampled(self):
        doc, features, gen = build(SHADOWED)
        self.assertEqual(gen.stats["witnessed"], 1)
        self.assertEqual(gen.stats["shadowed"], 1)
        self.assertEqual(gen.stats["unexercised"], 0)

    def test_rule_no_config_enables_is_unexercised(self):
        with tempfile.TemporaryDirectory() as d:
            doc = cases.document(write(d, GATED))
        features = E.Features({"off": {"Subtarget.hasF()": False,
                                       "LLT::getUseExtended()": True}})
        gen = cases.generate(doc, features)
        self.assertEqual(gen.stats["witnessed"], 0)
        self.assertEqual(gen.stats["unexercised"], 1)

    def test_every_generated_type_round_trips(self):
        doc, features, gen = build(FIXTURE)
        for case in gen.cases:
            for text in case.types:
                self.assertEqual(cases.llt_text(E.parse_case_llt(text)), text)


class Configs(unittest.TestCase):
    def test_config_filter_keeps_only_requested_rows(self):
        doc = cases.document(CORPUS / "X86LegalizerInfo.gisel")
        features = cases.derive_features(doc, ORACLE / "x86-features.json",
                                         ["C1"])
        self.assertEqual(sorted(features.table), ["C1"])


class FrozenDifferential(unittest.TestCase):
    """The generated X86 set overlaps the frozen oracle without disagreement."""

    def test_x86_cases_agree_on_the_overlap(self):
        doc = cases.document(CORPUS / "X86LegalizerInfo.gisel")
        features = E.load_features(ORACLE / "x86-features.json")
        gen = cases.generate(doc, features)
        diff = cases.differ(gen, doc, features,
                            ORACLE / "x86_ref_dump.jsonl")
        self.assertGreater(diff.covered, 0)
        self.assertEqual(diff.disagree, 0, diff.first)
        self.assertEqual(diff.errors, 0, diff.first)


if __name__ == "__main__":
    unittest.main()
