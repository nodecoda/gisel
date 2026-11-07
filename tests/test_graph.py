"""Static quotient-graph tests, including the negative controls."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gisel import cases, eval as E, graph

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


GUARDED = """\
type S3 = LLT::scalar(3)
type S32 = LLT::scalar(32)

ruleset G_UMIN: G_UMIN
    widen(slot(0), pow2_min(32))
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

    def test_outside_is_counted_and_closure_reports_it(self):
        report = self.build(OUTSIDE)
        self.assertGreater(report.public()["outside"], 0)
        checked = self.build(OUTSIDE, check_closure=True)
        self.assertFalse(checked.closure["ok"])
        self.assertTrue(checked.closure["violations"])

    def test_implicit_guard_takes_part_in_the_class(self):
        # X86_UMIN spells the widen rule with a bare `true` predicate; only
        # the shim's `is_scalar && !is_pow2` guard separates s3 from s32.
        # Ignoring that guard merges them and turns s3 -> s32 into a
        # self-loop (a false cycle).
        report = self.build(GUARDED, check_closure=True)
        public = report.public()
        self.assertEqual(public["cycles"], 0)
        self.assertTrue(report.closure["ok"], report.closure)
        classes = [{cases.llt_text(member[0][0]) for member in state["members"]}
                   for state in report.states.values()]
        self.assertTrue(any("s3" in group for group in classes), classes)
        self.assertTrue(any("s32" in group for group in classes), classes)
        self.assertFalse(any({"s3", "s32"} <= group for group in classes),
                         classes)

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


if __name__ == "__main__":
    unittest.main()
