"""Case generation: equivalence classes, boundaries, outside points."""

import json
import tempfile
import unittest
from pathlib import Path

from gisel import cases, eval as E

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "corpus"
DATA = ROOT / "tests" / "cases"

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

TWO = """\
type s32 = LLT::scalar(32)

ruleset B_ADD: G_ADD
    legal in(slot(0), s32)

ruleset B_SUB: G_SUB
    legal in(slot(0), s32)
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


class RulesetFilter(unittest.TestCase):
    """`only_rulesets` is a chunking device, not a different generator."""

    def test_a_chunk_matches_the_full_run(self):
        with tempfile.TemporaryDirectory() as d:
            doc = cases.document(write(d, TWO))
        features = cases.derive_features(doc)
        full = cases.generate(doc, features)
        chunk = cases.generate(doc, features, only_rulesets=["B_SUB"])
        self.assertEqual({c.opcode for c in chunk.cases}, {"G_SUB"})
        self.assertEqual({c.key() for c in chunk.cases},
                         {c.key() for c in full.cases if c.opcode == "G_SUB"})

    def test_an_opcode_names_the_ruleset_too(self):
        doc, features, _ = build(FIXTURE)
        gen = cases.generate(doc, features, only_rulesets=["G_ADD"])
        self.assertTrue(gen.cases)

    def test_a_typo_is_an_error_not_an_empty_file(self):
        doc, features, _ = build(FIXTURE)
        with self.assertRaises(ValueError):
            cases.generate(doc, features, only_rulesets=["NOPE"])

    def test_ruleset_with_queries_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            src = write(d, FIXTURE)
            rc = cases.main([
                str(src), "--out", str(Path(d) / "out.jsonl"),
                "--queries", str(Path(d) / "q.jsonl"),
                "--oracle", str(Path(d) / "o.jsonl"),
                "--ruleset", "B_ADD",
            ])
        self.assertEqual(rc, 2)


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

    def test_the_mutation_target_type_seeds_the_directed_search(self):
        # The rule names its trigger type only in `to`: clamp_max to v4s32
        # fires on a wider vector of the same element.  The declared domain
        # has v4s32 but not v16s32, so only a search seeded from the target
        # (and its neighbours) can witness it.
        text = """\
type s32 = LLT::scalar(32)
type v4s32 = LLT::fixed_vector(4, 32)

ruleset B_ADD: G_ADD
    legal in(slot(0), s32)
    clamp_max(0, s32, num_elems(ty(v4s32)))
"""
        doc, features, gen = build(text)
        self.assertEqual(gen.stats["witnessed"], 2)
        self.assertEqual(gen.stats["shadowed"], 0)
        directed = [c for c in gen.cases
                    if c.rule == 1 and "directed" in c.reason]
        self.assertTrue(directed)
        self.assertNotIn(directed[0].types[0], ("s32", "v4s32"))

    def test_rule_no_config_enables_is_unexercised(self):
        with tempfile.TemporaryDirectory() as d:
            doc = cases.document(write(d, GATED))
        features = E.Features({"off": {"Subtarget.hasF()": False,
                                       "LLT::getUseExtended()": True}})
        gen = cases.generate(doc, features)
        self.assertEqual(gen.stats["witnessed"], 0)
        self.assertEqual(gen.stats["unexercised"], 1)

    def test_the_slot_budget_is_soft_and_reported(self):
        # 20 literals in one slot: `_candidates` keeps every literal plus its
        # neighbours, so the axis is wider than `max_slot_values`.  That is
        # the design, and the stats have to say so instead of letting a
        # reader treat 16 as a hard cap.
        bits = [1, 3, 5, 6, 7, 9, 10, 11, 12, 13,
                17, 18, 19, 20, 21, 22, 23, 25, 26, 27]
        text = "".join("type S%d = LLT::scalar(%d)\n" % (b, b) for b in bits)
        text += "\nruleset B_ADD: G_ADD\n    legal in(slot(0), [%s])\n" % (
            ", ".join("S%d" % b for b in bits))
        doc, features, gen = build(text)
        self.assertEqual(gen.stats["slot_budget"], 16)
        self.assertGreater(gen.stats["candidate_max"], 16)
        self.assertGreaterEqual(gen.stats["candidate_over_budget"], 1)

    def test_every_generated_type_round_trips(self):
        doc, features, gen = build(FIXTURE)
        for case in gen.cases:
            for text in case.types:
                self.assertEqual(cases.llt_text(E.parse_case_llt(text)), text)


MERGE = """\
type s32 = LLT::scalar(32)
type s64 = LLT::scalar(64)
type v2s32 = LLT::fixed_vector(2, LLT::scalar(32))
type nxv16s8 = LLT::scalable_vector(16, LLT::scalar(8))

ruleset B_MERGE: G_MERGE_VALUES
    legal in(slot(0), [s32, s64])
    legal in(slot(1), [s32, s64])

ruleset B_UNMERGE: G_UNMERGE_VALUES
    legal in(slot(0), [s32, s64])
    legal in(slot(1), [s32, s64])
"""

SHAPED = """\
type s8 = LLT::scalar(8)
type s16 = LLT::scalar(16)
type s32 = LLT::scalar(32)
type v2s32 = LLT::fixed_vector(2, LLT::scalar(32))
type v4s32 = LLT::fixed_vector(4, LLT::scalar(32))
type v8s8 = LLT::fixed_vector(8, LLT::scalar(8))
type v16s8 = LLT::fixed_vector(16, LLT::scalar(8))
type v8s16 = LLT::fixed_vector(8, LLT::scalar(16))
type v16s16 = LLT::fixed_vector(16, LLT::scalar(16))

ruleset B_CONCAT: G_CONCAT_VECTORS
    legal in_pairs(slot(0), slot(1), [[v16s8, v8s8], [v16s16, v8s16]])
    bitcast(slot(0), replace(ty(v4s32)))
"""


class VerifierShapes(unittest.TestCase):
    """Queries the generic MIR verifier rejects are not part of the domain."""

    def test_merge_is_scalar_only(self):
        self.assertTrue(cases.type_shape_ok(
            "G_MERGE_VALUES", [E.parse_case_llt("s64"),
                               E.parse_case_llt("s32")]))
        self.assertFalse(cases.type_shape_ok(
            "G_MERGE_VALUES", [E.parse_case_llt("f128"),
                               E.parse_case_llt("nxv16i8")]))

    def test_unmerge_vector_form_needs_matching_elements(self):
        ok = [E.parse_case_llt(t) for t in ("v4s8", "v16s8")]
        bad = [E.parse_case_llt(t) for t in ("nxv16i8", "f128")]
        mixed = [E.parse_case_llt(t) for t in ("v4s8", "s32")]
        self.assertTrue(cases.type_shape_ok("G_UNMERGE_VALUES", ok))
        self.assertFalse(cases.type_shape_ok("G_UNMERGE_VALUES", bad))
        self.assertFalse(cases.type_shape_ok("G_UNMERGE_VALUES", mixed))

    def test_concat_needs_double_lanes_and_one_element_type(self):
        ok = [E.parse_case_llt(t) for t in ("v16s8", "v8s8")]
        wrong_lanes = [E.parse_case_llt(t) for t in ("v16s8", "v2s32")]
        wrong_element = [E.parse_case_llt(t) for t in ("v4s32", "v2s16")]
        self.assertTrue(cases.type_shape_ok("G_CONCAT_VECTORS", ok))
        self.assertFalse(cases.type_shape_ok("G_CONCAT_VECTORS", wrong_lanes))
        self.assertFalse(cases.type_shape_ok("G_CONCAT_VECTORS", wrong_element))

    def test_shuffle_cannot_change_the_element_type(self):
        ok = [E.parse_case_llt(t) for t in ("v16s8", "v16s8")]
        changed = [E.parse_case_llt(t) for t in ("v16s8", "v16s32")]
        scalar = [E.parse_case_llt(t) for t in ("v16s8", "s32")]
        self.assertTrue(cases.type_shape_ok("G_SHUFFLE_VECTOR", ok))
        self.assertFalse(cases.type_shape_ok("G_SHUFFLE_VECTOR", changed))
        self.assertFalse(cases.type_shape_ok("G_SHUFFLE_VECTOR", scalar))

    def test_saturating_convert_keeps_the_lane_count(self):
        ok = [E.parse_case_llt(t) for t in ("v2i64", "v2f16")]
        short = [E.parse_case_llt(t) for t in ("v2i64", "f16")]
        self.assertTrue(cases.type_shape_ok("G_FPTOSI_SAT", ok))
        self.assertFalse(cases.type_shape_ok("G_FPTOSI_SAT", short))

    def test_comparison_result_is_integer(self):
        # type0 of G_ICMP/G_FCMP is the comparison result.  A float there is
        # not valid MIR; X86 G_FCMP previously accepted f16 in slot 0, then
        # `clampScalar(0, s8, s8)` turned it into f8 and the graph counted a
        # bogus `outside`.  The operand slot stays unconstrained by kind:
        # X86's table compares it by size only.
        ints = [E.parse_case_llt("s8"), E.parse_case_llt("s32")]
        floats = [E.parse_case_llt("f16"), E.parse_case_llt("f16")]
        mixed = [E.parse_case_llt("v4s32"), E.parse_case_llt("v4f32")]
        bad_lanes = [E.parse_case_llt("v4s32"), E.parse_case_llt("v2f32")]
        self.assertTrue(cases.type_shape_ok("G_ICMP", ints))
        self.assertFalse(cases.type_shape_ok("G_ICMP", floats))
        self.assertTrue(cases.type_shape_ok("G_FCMP", mixed))
        self.assertFalse(cases.type_shape_ok("G_FCMP", bad_lanes))
        self.assertFalse(cases.type_shape_ok("G_FCMP", floats))

    def test_shifts_and_rotates_keep_one_shape_category(self):
        # MachineVerifier.cpp: "Shifts and rotates require operands to be
        # either all scalars or all vectors".  A mixed pair never reaches the
        # legalizer, so it is not a query the runner can ask.
        scalar = [E.parse_case_llt("s32"), E.parse_case_llt("s32")]
        vector = [E.parse_case_llt("v16s8"), E.parse_case_llt("v16s8")]
        mixed = [E.parse_case_llt("v16s8"), E.parse_case_llt("s32")]
        for opcode in ("G_SHL", "G_LSHR", "G_ASHR", "G_ROTR", "G_ROTL"):
            self.assertTrue(cases.type_shape_ok(opcode, scalar), opcode)
            self.assertTrue(cases.type_shape_ok(opcode, vector), opcode)
            self.assertFalse(cases.type_shape_ok(opcode, mixed), opcode)

    def test_shape_check_survives_a_short_tuple(self):
        # `nslots` comes from the slots the ruleset names, not from the opcode's
        # arity: a hand-written ruleset may expose one slot of a two-slot
        # opcode.  The filter must answer False, not raise IndexError.
        one = [E.parse_case_llt("v16s8")]
        for opcode in ("G_CONCAT_VECTORS", "G_SHUFFLE_VECTOR",
                       "G_FPTOSI_SAT"):
            self.assertFalse(cases.type_shape_ok(opcode, one), opcode)

    def test_shape_filter_counts_what_it_drops(self):
        doc, features, gen = build(SHAPED)
        self.assertTrue(gen.cases)
        self.assertGreater(gen.stats["ill_formed"], 0)
        self.assertGreater(
            gen.stats["ill_formed_opcodes"].get("G_CONCAT_VECTORS", 0), 0)
        # Every surviving query is a shape MIR can hold, and the filter did not
        # cost either rule its witness.
        for case in gen.cases:
            types = [E.parse_case_llt(t) for t in case.types]
            self.assertTrue(cases.type_shape_ok(case.opcode, types), case)
        self.assertEqual(sorted({c.rule for c in gen.cases
                                 if c.kind == "equivalence"}), [0, 1])

    def test_other_opcodes_are_unaffected(self):
        self.assertTrue(cases.type_shape_ok(
            "G_ADD", [E.parse_case_llt("f128"),
                      E.parse_case_llt("nxv16i8")]))

    def test_generated_cases_respect_the_shape(self):
        doc, features, gen = build(MERGE)
        self.assertTrue(gen.cases)
        for case in gen.cases:
            types = [E.parse_case_llt(t) for t in case.types]
            self.assertTrue(cases.type_shape_ok(case.opcode, types), case)


class Configs(unittest.TestCase):
    def test_config_filter_keeps_only_requested_rows(self):
        doc = cases.document(CORPUS / "X86LegalizerInfo.gisel")
        features = cases.derive_features(doc, DATA / "x86-features.json",
                                         ["C1"])
        self.assertEqual(sorted(features.table), ["C1"])


class Differential(unittest.TestCase):
    def test_against_an_answered_query_file_compares_the_overlap(self):
        doc, features, gen = build(FIXTURE)
        with tempfile.TemporaryDirectory() as d:
            queries = Path(d) / "q.jsonl"
            answers = Path(d) / "a.jsonl"
            queries.write_text("".join(json.dumps({
                "config": c.config, "name": c.opcode,
                "types": list(c.types),
                "mem": list(c.mem) if c.mem else None,
                "imms": list(c.imms)}) + "\n" for c in gen.cases))
            total, errors, first, _ = E.answer_queries(
                E.Evaluator(doc, features), str(queries), str(answers))
            self.assertEqual((total, errors), (len(gen.cases), 0), first)
            diff = cases.differ(gen, doc, features, answers)
        self.assertEqual(diff.covered, len(gen.cases))
        self.assertEqual((diff.disagree, diff.errors), (0, 0), diff.first)


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

    def test_cli_prints_stats_after_a_query_oracle_run(self):
        with tempfile.TemporaryDirectory() as d:
            source = write(d, FIXTURE)
            queries = Path(d) / "queries.jsonl"
            oracle = Path(d) / "answers.jsonl"
            out = Path(d) / "cases.jsonl"
            q = {"config": "none", "name": "G_ADD", "types": ["s32"],
                 "mem": None, "imms": []}
            queries.write_text(json.dumps(q) + "\n")
            oracle.write_text(json.dumps(dict(
                q, action="Legal", type_idx=0, new_type="LLT_invalid")) + "\n")
            rc = cases.main([str(source), "--queries", str(queries),
                             "--oracle", str(oracle), "--out", str(out)])
            self.assertEqual(rc, 0)
            self.assertTrue(out.read_text().strip())


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

class CoverageGate(unittest.TestCase):
    """`--strict-coverage` turns the unwitnessed count into an exit code."""

    def _run(self, source, *extra):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "q.jsonl"
            return subprocess.run(
                [sys.executable, "-m", "gisel.cli", "cases", str(source),
                 "--out", str(out), *extra],
                capture_output=True, text=True)

    def test_a_fully_witnessed_source_passes(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(FIXTURE)
            r = self._run(src, "--strict-coverage")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_rule_with_no_witness_fails(self):
        # `legal s32` twice: the second rule can never be the first match, so
        # the set has no witness for it and the gate must say so instead of
        # reporting a green run.
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(SHADOWED)
            r = self._run(src, "--strict-coverage")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("no witness", r.stderr)

