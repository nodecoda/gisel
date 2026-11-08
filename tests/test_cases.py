"""Case generation: equivalence classes, boundaries, outside points."""

import json
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


class OracleKeyShape(unittest.TestCase):
    def test_two_and_four_element_mem_share_a_key(self):
        base = {"config": "C0", "name": "G_LOAD", "types": ["s8", "p0:64"],
                "imms": []}
        two = dict(base, mem=["s8", 8])
        four = dict(base, mem=["s8", 8, "NotAtomic", "NotAtomic"])
        self.assertEqual(cases._oracle_key(two), cases._oracle_key(four))


class FullRunCompression(unittest.TestCase):
    def test_query_oracle_mode_requires_complete_answers(self):
        with tempfile.TemporaryDirectory() as d:
            source = write(d, FIXTURE)
            doc = cases.document(source)
            features = cases.derive_features(doc)
            queries = Path(d) / "queries.jsonl"
            oracle = Path(d) / "answers.jsonl"
            q1 = {"config": "none", "name": "G_ADD", "types": ["s32"],
                  "mem": None, "imms": []}
            q2 = dict(q1, types=["s64"])
            queries.write_text(json.dumps(q1) + "\n" + json.dumps(q2) + "\n")
            a1 = dict(q1, action="Legal", type_idx=0,
                      new_type="LLT_invalid")
            a2 = dict(q2, status="unanswerable", reason="asserted")
            oracle.write_text(json.dumps(a1) + "\n" + json.dumps(a2) + "\n")
            gen = cases.generate_from_queries(doc, features, queries, oracle)
        self.assertEqual(gen.stats["oracle_missing"], 0)
        self.assertEqual(gen.stats["oracle_unanswerable"], 1)
        self.assertEqual(gen.stats["evaluator_errors"], 0)
        self.assertTrue(any(c.kind == "equivalence" for c in gen.cases))


if __name__ == "__main__":
    unittest.main()


class OneLaneVectors(unittest.TestCase):
    """`LLT::vector` asserts on one fixed lane: `v1s8` is really `s8`."""

    def test_parse_collapses_a_fixed_one_lane_vector(self):
        self.assertEqual(E.parse_case_llt("v1s8"), E.parse_case_llt("s8"))
        self.assertEqual(E.parse_case_llt("v1p0:64"), E.parse_case_llt("p0:64"))
        self.assertEqual(cases.llt_text(E.parse_case_llt("nxv1s8")),
                         "nxv1s8")

    def test_vec_of_one_is_the_element_type(self):
        self.assertEqual(E.fixed_vector(1, E.parse_case_llt("s8")),
                         E.parse_case_llt("s8"))

    def test_no_generated_case_names_a_fixed_one_lane_vector(self):
        import re
        one_lane = re.compile(r"^v1(?!\d)")
        for source in sorted(CORPUS.glob("*.gisel")):
            doc = cases.document(source)
            features = cases.derive_features(doc)
            configs = sorted(features.table)[:1]
            gen = cases.generate(doc, features, configs=configs)
            bad = [c.types for c in gen.cases
                   if any(one_lane.search(t) for t in c.types)]
            self.assertEqual(bad, [], source.name)


class AnswerMode(unittest.TestCase):
    """`eval --answers` writes the runner-shaped answer to a bare query."""

    def test_answers_are_parallel_and_agree_with_evaluate(self):
        with tempfile.TemporaryDirectory() as d:
            doc = cases.document(write(d, FIXTURE))
            features = E.Features({"none": {}})
            evaluator = E.Evaluator(doc, features)
            queries = Path(d) / "q.jsonl"
            rows = [
                {"config": "none", "name": "G_ADD", "types": ["s32"],
                 "mem": None, "imms": []},
                {"config": "none", "name": "G_ADD", "types": ["s16"],
                 "mem": None, "imms": []},
            ]
            queries.write_text("".join(json.dumps(r) + "\n" for r in rows))
            out = Path(d) / "a.jsonl"
            total, errors, first, counts = E.answer_queries(
                evaluator, queries, out)
            self.assertEqual((total, errors, first), (2, 0, None))
            self.assertEqual(counts, {"Legal": 1, "Unsupported": 1})
            answers = [json.loads(line) for line in out.read_text().splitlines()]
            self.assertEqual(len(answers), len(rows))
            for query, answer in zip(rows, answers):
                action, type_idx, new_type = E.evaluate(
                    evaluator, query["config"], query["name"],
                    [E.parse_case_llt(query["types"][0])], [], [])
                self.assertEqual(answer["action"], action)
                self.assertEqual(answer["type_idx"], type_idx)
                self.assertEqual(answer["new_type"], E.fmt_oracle_llt(new_type))
                self.assertEqual(answer["types"], query["types"])
