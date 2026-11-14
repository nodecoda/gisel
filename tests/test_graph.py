"""Static quotient-graph tests, including the negative controls."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gisel import cases, domain, eval as E, graph

ROOT = Path(__file__).resolve().parents[1]


def write_source(directory, text):
    path = Path(directory) / "graph.gisel"
    path.write_text(text)
    return path


FIXTURE = """\
type S8 = LLT::scalar(8)
type S32 = LLT::scalar(32)
type S64 = LLT::scalar(64)

ruleset G_ADD: G_ADD
    legal in(slot(0), S32)
    widen(slot(0), ty(S32))
"""

CLOSED = """\
type S32 = LLT::scalar(32)

ruleset G_ADD: G_ADD
    legal true
"""

OUTSIDE = """\
type S3 = LLT::scalar(3)

ruleset G_ADD: G_ADD
    widen(slot(0), pow2)
"""


MEMBER_MIX = """\
type S3 = LLT::scalar(3)
type S33 = LLT::scalar(33)
type S64 = LLT::scalar(64)

ruleset G_ADD: G_ADD
    widen(slot(0), pow2_min(32))
"""


GUARDED = """\
type S3 = LLT::scalar(3)
type S32 = LLT::scalar(32)

ruleset G_UMIN: G_UMIN
    widen(slot(0), pow2_min(32))
    lower true
"""


SHIFT_MIX = """\
type S8 = LLT::scalar(8)
type S32 = LLT::scalar(32)
type V16S8 = LLT::fixed_vector(16, 8)

ruleset G_ASHR: G_ASHR
    legal in_pairs(slot(0), slot(1), [[V16S8, V16S8], [S32, S32]])
    widen(slot(1), ty(S32))
    narrow(slot(1), same_as(0)) when sort_of(slot(0)) == vector
"""


SHIFT_SCALAR_LOOP = """\
type S8 = LLT::scalar(8)
type S32 = LLT::scalar(32)
type S64 = LLT::scalar(64)

ruleset G_SHL: G_SHL
    legal in_pairs(slot(0), slot(1), [[S64, S64]])
    widen(slot(0), ty(S32)) when bits_of(slot(0)) == 8
    narrow(slot(0), ty(S8)) when bits_of(slot(0)) == 32
"""


REFINABLE = """\
type S3 = LLT::scalar(3)
type S8 = LLT::scalar(8)
type S24 = LLT::scalar(24)
type S32 = LLT::scalar(32)
type S64 = LLT::scalar(64)

ruleset G_ADD: G_ADD
    legal in(slot(0), S64)
    widen(slot(0), pow2_min(8))
"""


CROSS_SLOT_REFINABLE = """\
type S3 = LLT::scalar(3)
type S8 = LLT::scalar(8)
type S64 = LLT::scalar(64)
type V2S1 = LLT::fixed_vector(2, 1)
type V2S8 = LLT::fixed_vector(2, 8)

ruleset G_CTLZ: G_CTLZ
    narrow(slot(0), ty(S64))
    widen(slot(1), same_as(0))
    narrow(slot(1), same_as(0))
    lower true
"""


class GraphFixture(unittest.TestCase):
    def build(self, text=FIXTURE, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            source = write_source(directory, text)
            doc = cases.document(source)
            features = cases.derive_features(doc)
            return graph.build(source, "none", features, **kwargs)

    def test_graph_has_no_cycle_and_injection_is_a_negative_control(self):
        report = self.build()
        self.assertEqual(report.public()["cycles"], 0)
        injected = self.build(inject_edge=True)
        self.assertGreaterEqual(injected.public()["cycles"], 1)

    def test_closure_passes_for_closed_fixture(self):
        report = self.build(CLOSED, check_closure=True)
        self.assertTrue(report.closure["ok"], report.closure)

    def test_outside_is_counted(self):
        # `widen(pow2)` sends `s3` to `s4`, a width no axis enumerates.
        report = self.build(OUTSIDE)
        self.assertGreater(report.public()["outside"], 0)

    def test_a_class_that_straddles_the_enumerated_domain_is_not_closed(self):
        # `s3` widens to `s4` (outside), while `s7`/`s24` in the same class
        # widen to the enumerated `s8`/`s32`.  The class is not a function on
        # the enumerated domain, and closure must say so.
        checked = self.build(OUTSIDE, check_closure=True)
        self.assertFalse(checked.closure["ok"], checked.closure)
        self.assertEqual(checked.closure["kinds"]["outside"], 6)
        members = {v["member"][0] for v in checked.closure["violations"]}
        self.assertIn("s7", members)

    def test_a_sentinel_the_axes_carry_is_not_outside(self):
        # The axes include the stable sentinels, so a mutation into one is an
        # ordinary edge.  Judging `outside` against the `.gisel` declarations
        # alone used to drop those edges: Mips declares no float types, so
        # every f16 -> f32 was reported as a domain exit even though f32 was
        # a state the graph itself enumerated.
        report = self.build(MEMBER_MIX, check_closure=True)
        self.assertEqual(report.public()["outside"], 0)
        self.assertTrue(report.closure["ok"], report.closure)

    def test_closure_audits_members_of_an_outside_class(self):
        # The representative `s3` widens to the unenumerated `s4`; `s7` is in
        # the same class and widens to the enumerated `s8`.  The old audit
        # looked at moving representatives only, so `s7` was never asked.
        report = self.build(OUTSIDE, check_closure=True)
        self.assertEqual(report.public()["cycles"], 0)
        members = {v["member"][0] for v in report.closure["violations"]}
        self.assertIn("s7", members)
        self.assertEqual(report.closure["kinds"],
                         {"partition": 0, "outside": 6})

    def test_implicit_guard_takes_part_in_the_class(self):
        # X86_UMIN spells the widen rule with a bare `true` predicate; only
        # the shim's `is_scalar && !is_pow2` guard separates s3 from s32.
        # Ignoring that guard merges them and turns s3 -> s32 into a
        # self-loop (a false cycle).
        report = self.build(GUARDED, check_closure=True)
        public = report.public()
        self.assertEqual(public["cycles"], 0)
        # `s33`/`s63`/`s65` widen into the enumerated `s64`/`s128`, so the
        # class is a function on the axes; only the guard separation matters.
        self.assertTrue(report.closure["ok"], report.closure)
        classes = [{cases.llt_text(member[0][0])
                    for member in graph._state_members(state)}
                   for state in report.states.values()]
        self.assertTrue(any("s3" in group for group in classes), classes)
        self.assertTrue(any("s32" in group for group in classes), classes)
        self.assertFalse(any({"s3", "s32"} <= group for group in classes),
                         classes)

    def test_refine_splits_a_class_with_two_targets(self):
        # s3 and s24 are one class (same predicates, same shim guard) but
        # widen(pow2_min(8)) sends them to s8 and s32.  The quotient is not a
        # function until the class is split; --refine is the opt-in that does
        # it, and the class count before/after is reported.
        plain = self.build(REFINABLE, check_closure=True)
        self.assertFalse(plain.closure["ok"])
        self.assertEqual(plain.closure["kinds"]["partition"], 1)
        self.assertEqual(plain.closure["kinds"]["outside"], 0)
        self.assertIsNone(plain.public().get("classes_before"))

        refined = self.build(REFINABLE, check_closure=True, refine=True)
        public = refined.public()
        self.assertTrue(refined.closure["ok"], refined.closure)
        self.assertEqual(refined.closure["kinds"]["partition"], 0)
        self.assertEqual(refined.closure["kinds"]["outside"], 0)
        self.assertEqual(public["classes_before"], plain.classes)
        self.assertGreater(public["classes"], public["classes_before"])
        self.assertGreater(public["states"], plain.public()["states"])

    def test_refine_splits_on_a_cross_slot_target(self):
        # The rule writes slot 1 from slot 0 (`same_as(0)`), so slot 0's
        # `s3` and `s8` share a class but send slot 1 to v2s3 (outside) and
        # v2s8 (declared).  Refinement must follow the written slot; looking
        # only at same-slot writes left RISC-V's poison-count classes mixed.
        plain = self.build(CROSS_SLOT_REFINABLE, check_closure=True)
        self.assertFalse(plain.closure["ok"], plain.closure)
        self.assertGreater(plain.closure["kinds"]["outside"], 0)

        refined = self.build(CROSS_SLOT_REFINABLE, check_closure=True,
                             refine=True)
        self.assertTrue(refined.closure["ok"], refined.closure)
        self.assertEqual(refined.closure["kinds"],
                         {"partition": 0, "outside": 0})
        self.assertGreater(refined.public()["classes"], plain.classes)

    def test_mir_shape_filter_drops_a_mixed_shift_ring(self):
        # (v16s8, s32) round-trips through widen/narrow in the rule table, but
        # no MIR holds that shape: the verifier demands both shift operands be
        # scalars or both be vectors.  The state must not be built, and the
        # drop has to be visible as `shape`, not silently disappear.
        report = self.build(SHIFT_MIX)
        public = report.public()
        self.assertEqual(public["cycles"], 0)
        self.assertGreater(public["shape"], 0)

        original = graph._shape_representative
        graph._shape_representative = (
            lambda opcode, pools: tuple(pool[0] for pool in pools))
        try:
            unfiltered = self.build(SHIFT_MIX)
        finally:
            graph._shape_representative = original
        self.assertGreater(unfiltered.public()["cycles"], 0)

    def test_the_shape_filter_does_not_hide_a_scalar_ring(self):
        # The negative control for the filter above: a ring the verifier does
        # accept (scalar -> scalar) must still be reported.
        public = self.build(SHIFT_SCALAR_LOOP).public()
        self.assertGreater(public["cycles"], 0)
        # `shape` still counts the mixed (scalar, vector) class tuples this
        # fixture's free slot produces; the point is that the scalar ring
        # survives the filter.
        for sample in public["cycle_samples"]:
            self.assertTrue(sample)

    def test_refine_is_not_the_default(self):
        plain = self.build(FIXTURE)
        self.assertNotIn("classes_before", plain.public())

    def test_opaque_is_a_separate_outcome(self):
        text = ('feature F = Subtarget.hasF()\n'
                'type S32 = LLT::scalar(32)\n'
                'ruleset G_ADD: G_ADD\n'
                '    legal (F and in(slot(0), S32))\n')
        with tempfile.TemporaryDirectory() as directory:
            source = write_source(directory, text)
            doc = cases.document(source)
            features = E.Features({"none": {"LLT::getUseExtended()": True}})
            report = graph.build(source, "none", features)
        self.assertGreater(report.public()["opaque"], 0)


    def test_state_limit_is_deterministic(self):
        with self.assertRaises(graph.GraphError) as caught:
            self.build(FIXTURE, max_states=1)
        self.assertEqual(caught.exception.kind, "state_limit")
        self.assertEqual(caught.exception.detail["limit"], 1)
        self.assertGreater(caught.exception.detail["states"], 1)

    def test_state_limit_cli_says_unsupported_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_source(directory, FIXTURE)
            r = subprocess.run(
                [sys.executable, "-m", "gisel", "graph", str(source),
                 "--max-states", "1", "--json"],
                capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["error"], "state_limit")
        self.assertEqual(payload["outcome"], "unsupported_scale")
        self.assertEqual(payload["limit"], 1)


class OracleAlignment(unittest.TestCase):
    def test_all_points_in_a_small_oracle_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_source(directory, FIXTURE)
            oracle = Path(directory) / "oracle.jsonl"
            rows = []
            for text, action in (("S32", "Legal"), ("S8", "WidenScalar")):
                rows.append({"config": "none", "name": "G_ADD",
                             "types": [text.lower()], "mem": None, "imms": [],
                             "action": action, "type_idx": 0,
                             "new_type": "LLT_invalid" if action == "Legal" else "s32"})
            oracle.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            doc = cases.document(source)
            features = cases.derive_features(doc)
            report = graph.build(source, "none", features,
                                 extra_types=[E.parse_case_llt("s8")])
            result = graph.oracle_check(report, oracle,
                                        E.Evaluator(doc, features), True)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["uncovered"], 0)
        self.assertEqual(result["disagree"], 0)


    def test_a_shape_invalid_dump_point_is_unaskable_not_uncovered(self):
        # `--oracle` used to return 1 for a dump point the graph never built,
        # even when the reason was the MIR shape rule (`(v16s8, s32)` shift).
        # That is not a graph gap: count it separately.
        with tempfile.TemporaryDirectory() as directory:
            source = write_source(directory, SHIFT_MIX)
            oracle = Path(directory) / "oracle.jsonl"
            oracle.write_text(json.dumps({
                "config": "none", "name": "G_ASHR",
                "types": ["v16s8", "s32"], "mem": None, "imms": [],
                "action": "NarrowScalar", "type_idx": 1,
                "new_type": "s8"}) + "\n")
            doc = cases.document(source)
            features = cases.derive_features(doc)
            report = graph.build(source, "none", features)
            result = graph.oracle_check(report, oracle,
                                        E.Evaluator(doc, features), True)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["unaskable"], 1)
        self.assertEqual(result["uncovered"], 0)
        self.assertEqual(result["disagree"], 0)


MEM_FIXTURE = """\
type S8 = LLT::scalar(8)
type S32 = LLT::scalar(32)
type S64 = LLT::scalar(64)
type P0 = LLT::pointer(0, 64)
feature XLen64 = XLen == 64
select Sel = if XLen64 then S64 else S32

ruleset G_STORE: G_STORE
    legal in_mem_desc(slot(0), slot(1), mem_slot(0), [mem_desc(S32, P0, Sel, 8)])
    lower true
"""


class ConfigDependentMemory(unittest.TestCase):
    """A memory type selected per configuration must not break the axes."""

    def test_select_memory_type_expands_per_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_source(directory, MEM_FIXTURE)
            doc = cases.document(source)
            features = cases.derive_features(doc)
            # Without an evaluator both branches are kept: a sound union.
            rows = []
            for ruleset in doc["rulesets"]:
                _, infos = cases.inspect_ruleset(ruleset)
                rows.extend(cases._mem_candidates(infos))
            self.assertEqual({"s32", "s64"}, {row[2] for row in rows})

            def mems_for(config):
                report = graph.build(source, config, features)
                return {str(state["mem"]) for state in report.states.values()}

            atomic = ("NotAtomic", "NotAtomic")
            self.assertEqual({str(("s32", 8) + atomic)}, mems_for("none"))
            self.assertEqual({str(("s64", 8) + atomic)}, mems_for("all"))

            _, mem_axis, _ = domain.domain_axes(source)
            self.assertEqual({"s32", "s64"}, {text for text, _bits, _align in mem_axis})

    def test_riscv_memory_rows_are_hashable(self):
        # RISCVLegalizerInfo.gisel carries a configuration-selected memory type;
        # feeding it to a set used to raise `TypeError: unhashable type: 'dict'`.
        source = ROOT / "tests" / "corpus" / "RISCVLegalizerInfo.gisel"
        doc = cases.document(source)
        rows = []
        for ruleset in doc["rulesets"]:
            _, infos = cases.inspect_ruleset(ruleset)
            rows.extend(cases._mem_candidates(infos))
        self.assertTrue(rows)
        memory_types = {row[2] for row in rows}
        self.assertIn("s32", memory_types)
        self.assertIn("s64", memory_types)
        _types, mem_axis, _doc = domain.domain_axes(source)
        self.assertTrue(mem_axis)

    def test_outcomes_always_reports_every_bucket(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_source(directory, FIXTURE)
            doc = cases.document(source)
            features = cases.derive_features(doc)
            outcomes = graph.build(source, "none", features).public()["outcomes"]
        self.assertEqual(
            {"moves", "no-rule", "terminal", "opaque", "outside", "stuck"},
            set(outcomes),
        )


class Verdict(unittest.TestCase):
    """The verdict line is the one-line reading of cycles + closure."""

    def build(self, text=FIXTURE, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            source = write_source(directory, text)
            doc = cases.document(source)
            features = cases.derive_features(doc)
            return graph.build(source, "none", features, **kwargs)

    def test_closed_graph_is_safe(self):
        report = self.build(CLOSED, check_closure=True)
        self.assertEqual(report.public()["verdict"], "safe")

    def test_open_closure_is_conditional_even_without_cycles(self):
        report = self.build(OUTSIDE, check_closure=True)
        public = report.public()
        self.assertEqual(public["cycles"], 0)
        self.assertEqual(public["verdict"], "conditional")

    def test_cycle_is_unsafe(self):
        report = self.build(inject_edge=True)
        public = report.public()
        self.assertGreaterEqual(public["cycles"], 1)
        self.assertEqual(public["verdict"], "unsafe")

    def test_skipped_closure_is_conditional(self):
        report = self.build(CLOSED, check_closure=False)
        self.assertEqual(report.public()["verdict"], "conditional")


if __name__ == "__main__":
    unittest.main()
