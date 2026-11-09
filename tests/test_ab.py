"""The workbench AB harness: adapters, query validation, action-only diff."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AB = ROOT / "tools" / "ab"
DIFF = AB / "diff.py"

spec = importlib.util.spec_from_file_location("ab_harness", AB / "ab.py")
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)

spec = importlib.util.spec_from_file_location("ab_attribute", AB / "attribute.py")
attribute = importlib.util.module_from_spec(spec)
spec.loader.exec_module(attribute)


def write_jsonl(rows):
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for row in rows:
        handle.write(json.dumps(row) + "\n")
    handle.close()
    return Path(handle.name)


def answer(name, action="Legal", new_type="LLT_invalid", types=("s32",)):
    return {"config": "C0", "name": name, "types": list(types), "mem": None,
            "imms": [], "action": action, "type_idx": 0,
            "new_type": new_type}


def query(name="G_ADD", types=("s32",)):
    return {"config": "C0", "name": name, "types": list(types), "mem": None,
            "imms": []}


class Adapters(unittest.TestCase):
    def test_x86_and_aarch64_adapters_load(self):
        x86 = ab.load_target("x86")
        self.assertEqual(x86["strategy"], "swap-source")
        self.assertEqual(x86["inc_name"], "X86LegalizerInfo.inc")
        a64 = ab.load_target("aarch64")
        self.assertEqual(a64["strategy"], "generated-ctor")
        ctor = ab.load_target("x86-ctor")
        self.assertEqual(ctor["strategy"], "generated-ctor")
        self.assertEqual(a64["query_count"], 13199)

    def test_unknown_target_is_an_error(self):
        with self.assertRaises(ab.HarnessError):
            ab.load_target("no-such-target")


class CompareMode(unittest.TestCase):
    def run_diff(self, ref, ours, mode):
        a = write_jsonl(ref)
        b = write_jsonl(ours)
        proc = subprocess.run(
            [sys.executable, str(DIFF), str(a), str(b), "--json",
             "--compare", mode],
            capture_output=True, text=True)
        return proc.returncode, json.loads(proc.stdout)

    def test_action_mode_ignores_new_type(self):
        ref = [answer("G_ADD")]
        ours = [answer("G_ADD", new_type="s64")]
        rc, result = self.run_diff(ref, ours, "action")
        self.assertEqual(rc, 0)
        self.assertEqual(result["mode"], "action")
        self.assertEqual(result["disagree"], 0)
        rc, result = self.run_diff(ref, ours, "full")
        self.assertEqual(rc, 1)
        self.assertEqual(result["disagree"], 1)
        self.assertEqual(result["first_details"][0]["class"], "new_type")

    def test_action_mode_still_catches_action_change(self):
        ref = [answer("G_ADD", "Legal")]
        ours = [answer("G_ADD", "WidenScalar", "s64")]
        rc, result = self.run_diff(ref, ours, "action")
        self.assertEqual(rc, 1)
        self.assertEqual(result["first_details"][0]["class"], "action")


class Matrix(unittest.TestCase):
    def ans(self, action="Legal", new_type=("invalid",), type_idx=0):
        return ("answered", action, type_idx, new_type)

    def unanswerable(self):
        return ("unanswerable", "asserted")

    def test_all_agree(self):
        a = self.ans()
        self.assertEqual(attribute.matrix_class(a, a, a), "all_agree")

    def test_both_assert(self):
        a = self.unanswerable()
        self.assertEqual(attribute.matrix_class(a, a, self.ans()),
                         "both_assert")

    def test_official_assert(self):
        self.assertEqual(attribute.matrix_class(
            self.unanswerable(), self.ans(), self.ans()), "official_assert")

    def test_ours_assert(self):
        self.assertEqual(attribute.matrix_class(
            self.ans(), self.unanswerable(), self.ans()), "ours_assert")

    def test_translation_rule_and_evaluator(self):
        a = self.ans()
        b = self.ans(new_type=("scalar", 64))
        c = self.ans(action="Unsupported")
        self.assertEqual(attribute.matrix_class(a, b, a), "translation")
        self.assertEqual(attribute.matrix_class(a, b, b), "rule")
        self.assertEqual(attribute.matrix_class(a, a, b), "evaluator")


class Queries(unittest.TestCase):
    def features(self, d):
        path = Path(d) / "features.json"
        path.write_text(json.dumps({"C0": {}}) + "\n")
        return path

    def test_count_and_config_check(self):
        with tempfile.TemporaryDirectory() as d:
            features = self.features(d)
            queries = Path(d) / "q.jsonl"
            queries.write_text(json.dumps(query()) + "\n"
                               + json.dumps(query("G_SUB")) + "\n")
            self.assertEqual(ab.validate_queries(queries, features, 2), 2)

    def test_duplicate_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            features = self.features(d)
            queries = Path(d) / "q.jsonl"
            queries.write_text(json.dumps(query()) + "\n"
                               + json.dumps(query()) + "\n")
            with self.assertRaises(ab.HarnessError):
                ab.validate_queries(queries, features)

    def test_unknown_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            features = self.features(d)
            bad = query()
            bad["config"] = "C9"
            queries = Path(d) / "q.jsonl"
            queries.write_text(json.dumps(bad) + "\n")
            with self.assertRaises(ab.HarnessError):
                ab.validate_queries(queries, features)

    def test_three_element_mem_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            features = self.features(d)
            bad = query()
            bad["mem"] = ["s8", 8, "Unordered"]
            queries = Path(d) / "q.jsonl"
            queries.write_text(json.dumps(bad) + "\n")
            with self.assertRaises(ab.HarnessError):
                ab.validate_queries(queries, features)


if __name__ == "__main__":
    unittest.main()
