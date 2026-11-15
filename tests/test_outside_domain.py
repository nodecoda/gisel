"""A query outside the declared domain gets an answer, never a traceback.

Every rule may assume facts about the types it was written for: slot 1 of
`G_ICMP` is a vector when the rule reads `elemOf`, a width-wide divide lands on
a whole number of lanes, and a pointer has *some* width.  A probe asks the
neighbouring domain on purpose, so those assumptions fail.  The compiled
legalizer either answers (its asserts are compiled out) or dies; the model must
answer `unanswerable` and keep the run alive, so the two sides stay comparable.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gisel import eval as E  # noqa: E402
from gisel import llt  # noqa: E402


def slot(i):
    return {"kind": "slot", "index": i}


def ruleset(*rules):
    return {"def": "R", "opcodes": ["G_OP"], "rules": list(rules)}


def widen_to_int(i, value):
    return {"action": "WidenScalar", "type_idx": 0, "op": "widen",
            "on": slot(i), "to": {"kind": "int", "value": value},
            "predicate": {"kind": "leaf", "name": "true", "args": []}}


def legal():
    return {"action": "Legal", "type_idx": 0, "op": "legal",
            "predicate": {"kind": "leaf", "name": "true", "args": []}}


FEATURES = {"rv64": {"_xlen": 64},
            "x86-32": {"Subtarget.is64Bit()": False},
            "x86-64": {"Subtarget.is64Bit()": True},
            "plain": {}}


class AShapeTheRuleAssumed(unittest.TestCase):
    def test_elem_of_a_scalar_is_unanswerable(self):
        doc = {"rulesets": [{
            "def": "R", "opcodes": ["G_OP"],
            "rules": [{
                "action": "Legal", "type_idx": 0, "op": "legal",
                "predicate": {"kind": "in", "args": [
                    {"kind": "elemOf", "args": [slot(0)]},
                    {"kind": "set", "of": "Type", "elems": ["s8"]}]},
            }],
        }]}
        ev = E.Evaluator(doc, E.Features(FEATURES))
        with self.assertRaises(E.EvalError) as caught:
            E.evaluate(ev, "rv64", "G_OP", [("scalar", 7)], ())
        self.assertEqual(caught.exception.code, "shape")

    def test_an_inexact_lane_divide_is_refused(self):
        t = ("vector", 1, True, ("scalar", 65))
        with self.assertRaises(llt.ShapeError):
            llt.change_element_count_div(t, 2)
        exact = llt.change_element_count_div(
            ("vector", 4, False, ("scalar", 32)), 2)
        self.assertEqual(exact[1], 2)


class APointerHasAWidth(unittest.TestCase):
    def answer(self, config, value=8):
        doc = {"rulesets": [ruleset(widen_to_int(1, value), legal())]}
        ev = E.Evaluator(doc, E.Features(FEATURES))
        return E.evaluate(ev, config, "G_OP",
                          [("scalar", 7), ("pointer", 0, "*")], ())

    def test_a_wide_pointer_skips_an_integer_widen(self):
        # 64 is neither narrower than 8 nor a non-power-of-two: the C++
        # predicate is false, so the next rule answers.
        action, _, _ = self.answer("rv64")
        self.assertEqual(action, "Legal")

    def test_is64_bit_fills_in_a_missing_width(self):
        self.assertEqual(self.answer("x86-64")[0], "Legal")
        self.assertEqual(self.answer("x86-32")[0], "Legal")

    def test_a_narrow_pointer_is_widened_but_the_type_cannot_change(self):
        # A 64-bit pointer against a minimum of 65: the predicate is true, and
        # `changeElementSize` on a pointer is not a mutation C++ performs, so
        # the model refuses instead of inventing one.
        with self.assertRaises(E.EvalError) as caught:
            self.answer("rv64", value=65)
        self.assertEqual(caught.exception.code, "shape")


class ThroughTheCommandLine(unittest.TestCase):
    def test_the_run_finishes_and_writes_an_unanswerable_row(self):
        doc = {"schema": "0.4", "version": "0.4", "config": {},
               "domain": {"types": []},
               "rulesets": [{
                   "def": "R", "opcodes": ["G_OP"],
                   "rules": [{
                       "action": "Legal", "type_idx": 0, "op": "legal",
                       "predicate": {"kind": "in", "args": [
                           {"kind": "elemOf", "args": [slot(0)]},
                           {"kind": "set", "of": "Type", "elems": ["s8"]}]},
                   }],
               }], "escapes": []}
        query = {"config": "rv64", "name": "G_OP", "types": ["s7"],
                 "mem": None, "imms": []}
        with tempfile.TemporaryDirectory() as tmp:
            doc_path = Path(tmp) / "doc.json"
            feat_path = Path(tmp) / "features.json"
            cases = Path(tmp) / "cases.jsonl"
            answers = Path(tmp) / "answers.jsonl"
            doc_path.write_text(json.dumps(doc))
            feat_path.write_text(json.dumps(FEATURES))
            cases.write_text(json.dumps(query) + "\n")
            proc = subprocess.run(
                [sys.executable, "-m", "gisel", "eval", "--doc", str(doc_path),
                 "--features", str(feat_path), "--cases", str(cases),
                 "--answers", str(answers)],
                cwd=ROOT, capture_output=True, text=True)
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            row = json.loads(answers.read_text().strip())
            self.assertEqual(row["status"], "unanswerable")
            self.assertTrue(row["reason"].startswith("shape:"))


if __name__ == "__main__":
    unittest.main()
