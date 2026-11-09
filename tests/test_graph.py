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

    def test_outside_is_counted_and_a_homogeneous_outside_class_closes(self):
        # `widen(pow2)` sends every member of the non-pow2 class into an
        # undeclared width.  The mutation is counted as `outside`, and the
        # class itself is homogeneous: closure has nothing to reject.
        report = self.build(OUTSIDE)
        self.assertGreater(report.public()["outside"], 0)
        checked = self.build(OUTSIDE, check_closure=True)
        self.assertTrue(checked.closure["ok"], checked.closure)
        self.assertEqual(checked.closure["kinds"]["outside"], 0)

    def test_closure_audits_members_of_an_outside_class(self):
        # The representative `s3` widens to the undeclared `s32`; `s33` is in
        # the same class and widens to the declared `s64`.  The old audit
        # looked at moves representatives only, so `s33` was never asked.
        report = self.build(MEMBER_MIX, check_closure=True)
        self.assertEqual(report.public()["cycles"], 0)
        members = {v["member"][0] for v in report.closure["violations"]}
        self.assertIn("s33", members)
        self.assertEqual(report.closure["kinds"],
                         {"partition": 0, "outside": 2})

    def test_implicit_guard_takes_part_in_the_class(self):
        # X86_UMIN spells the widen rule with a bare `true` predicate; only
        # the shim's `is_scalar && !is_pow2` guard separates s3 from s32.
        # Ignoring that guard merges them and turns s3 -> s32 into a
        # self-loop (a false cycle).
        report = self.build(GUARDED, check_closure=True)
        public = report.public()
        self.assertEqual(public["cycles"], 0)
        # The class that holds `s3` also holds `s33`/`s63`/`s65`, whose
        # widen targets are undeclared widths.  That is a coverage gap
        # (`outside`), not a rule partition error, and closure now says so
        # instead of trusting the representative.
        self.assertFalse(report.closure["ok"])
        self.assertEqual(report.closure["kinds"]["partition"], 0)
        self.assertEqual(report.closure["kinds"]["outside"], 3)
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
        self.assertEqual(plain.closure["kinds"]["outside"], 1)
        self.assertIsNone(plain.public().get("classes_before"))

        refined = self.build(REFINABLE, check_closure=True, refine=True)
        public = refined.public()
        self.assertTrue(refined.closure["ok"], refined.closure)
        self.assertEqual(refined.closure["kinds"]["partition"], 0)
        self.assertEqual(refined.closure["kinds"]["outside"], 0)
        self.assertEqual(public["classes_before"], plain.classes)
        self.assertGreater(public["classes"], public["classes_before"])
        self.assertGreater(public["states"], plain.public()["states"])

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


if __name__ == "__main__":
    unittest.main()
