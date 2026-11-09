"""Immediate axis: rules that read ``imm(i)`` must be exercised, not skipped."""

import json
import tempfile
import unittest
from pathlib import Path

from gisel import axes, cases, domain, graph

ROOT = Path(__file__).resolve().parents[1]
WASM = ROOT / "tests" / "corpus" / "WebAssemblyLegalizerInfo.gisel"

FIXTURE = """\
type s8 = LLT::scalar(8)
type s32 = LLT::scalar(32)

ruleset G_SEXT_INREG: G_SEXT_INREG
    legal (in(imm(0), [8, 16]) and in(slot(0), s32))
    lower true
"""


def write(directory, name, text):
    path = Path(directory) / name
    path.write_text(text)
    return path


class WasmCorpus(unittest.TestCase):
    def test_sext_inreg_is_witnessed(self):
        doc = cases.document(WASM)
        features = cases.derive_features(doc)
        generation = cases.generate(doc, features)
        self.assertNotIn("Wasm_G_SEXT_INREG#0", generation.stats["unwitnessed"])
        witnesses = [case for case in generation.cases
                     if case.ruleset == "Wasm_G_SEXT_INREG" and case.rule == 0]
        self.assertTrue(witnesses)
        self.assertTrue(any(case.imms for case in witnesses))

    def test_domain_enumerates_imm_values(self):
        doc = cases.document(WASM)
        features = cases.derive_features(doc)
        rows = list(domain.enumerate_domain(WASM, features, configs=["all"]))
        sext = [row for row in rows if row["name"] == "G_SEXT_INREG"]
        self.assertTrue(sext)
        values = {tuple(row["imms"]) for row in sext}
        self.assertIn((8,), values)
        self.assertIn((16,), values)
        self.assertIn((32,), values)
        self.assertIn((7,), values)   # neighbour of 8


class Profile(unittest.TestCase):
    def test_profile_values_replace_derived_imms(self):
        with tempfile.TemporaryDirectory() as d:
            source = write(d, "t.gisel", FIXTURE)
            doc = cases.document(source)
            profile = axes.load(write(d, "axes.json", json.dumps(
                {"version": 1, "imms": {"0": [4, 5]}})))
            profile.bind(source, doc, cases.derive_features(doc))
            _nslots, infos = cases.inspect_ruleset(doc["rulesets"][0])
            axis = cases.imm_candidates(infos, profile)
            self.assertEqual(axis, {0: [4, 5]})

    def test_invalid_imm_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source = write(d, "t.gisel", FIXTURE)
            doc = cases.document(source)
            profile = axes.load(write(d, "axes.json", json.dumps(
                {"version": 1, "imms": {"1": [4]}})))
            with self.assertRaises(axes.AxisError):
                profile.bind(source, doc, cases.derive_features(doc))


class Graph(unittest.TestCase):
    def build(self, directory, profile=None):
        source = write(directory, "t.gisel", FIXTURE)
        doc = cases.document(source)
        features = cases.derive_features(doc)
        return source, doc, features

    def test_no_axis_marks_the_opcode_uncovered(self):
        with tempfile.TemporaryDirectory() as d:
            source, doc, features = self.build(d)
            report = graph.build(source, "none", features)
        self.assertIn("G_SEXT_INREG", report.uncovered)
        self.assertEqual(report.states, {})

    def test_axis_builds_imm_states(self):
        with tempfile.TemporaryDirectory() as d:
            source, doc, features = self.build(d)
            profile = axes.load(write(d, "axes.json", json.dumps(
                {"version": 1, "imms": {"0": [8, 16]}})))
            profile.bind(source, doc, features)
            report = graph.build(source, "none", features,
                                 axis_profile=profile)
            self.assertNotIn("G_SEXT_INREG", report.uncovered)
            self.assertTrue(report.states)
            self.assertTrue(any(len(key) == 4 for key in report.states))
            tables = report.class_tables["G_SEXT_INREG"]
            self.assertIsNotNone(tables[2])

    def test_imm_points_stay_addressable_in_the_oracle(self):
        with tempfile.TemporaryDirectory() as d:
            source, doc, features = self.build(d)
            profile = axes.load(write(d, "axes.json", json.dumps(
                {"version": 1, "imms": {"0": [8, 16]}})))
            profile.bind(source, doc, features)
            report = graph.build(source, "none", features,
                                 axis_profile=profile)
            oracle = Path(d) / "oracle.jsonl"
            rows = [
                {"config": "none", "name": "G_SEXT_INREG",
                 "types": ["s32"], "mem": None, "imms": [8],
                 "action": "Legal", "type_idx": 0,
                 "new_type": "LLT_invalid"},
                {"config": "none", "name": "G_SEXT_INREG",
                 "types": ["s32"], "mem": None, "imms": [16],
                 "action": "Legal", "type_idx": 0,
                 "new_type": "LLT_invalid"},
            ]
            oracle.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            result = graph.oracle_check(report, oracle,
                                        cases.E.Evaluator(doc, features), True)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["uncovered"], 0)
        self.assertEqual(result["disagree"], 0)


if __name__ == "__main__":
    unittest.main()
