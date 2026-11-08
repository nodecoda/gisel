"""`tools/check-axes.py`: does an axis profile still sample what rules name?"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "check-axes.py"
CORPUS = ROOT / "tests" / "corpus"
X86 = CORPUS / "X86LegalizerInfo.gisel"
A64 = CORPUS / "AArch64LegalizerInfo.gisel"
RISCV = CORPUS / "RISCVLegalizerInfo.gisel"
X86_FEATURES = ROOT / "tests" / "cases" / "x86-features.json"
A64_FEATURES = ROOT / "tests" / "cases" / "features.json"
RISCV_FEATURES = ROOT / "tests" / "cases" / "riscv-features.json"

THRESHOLD = """\
type s32 = LLT::scalar(32)

ruleset G_SEXT_INREG: G_SEXT_INREG
    legal (slot(0) == ty(s32) and imm(0) > 32)
    lower true
"""


def run(source, axes, features=None, *flags):
    cmd = [sys.executable, str(TOOL), str(source), "--axes", str(axes)]
    if features is not None:
        cmd += ["--features", str(features)]
    cmd += list(flags)
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def profile(directory, data):
    path = Path(directory) / "axes.json"
    path.write_text(json.dumps(data))
    return path


class Clean(unittest.TestCase):
    def test_derived_axis_has_no_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1})
            result = run(X86, axes, X86_FEATURES)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("0 gap(s)", result.stdout)

    def test_imm_profile_covering_every_literal(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1, "imms": {"0": [8, 16, 32]}})
            result = run(RISCV, axes, RISCV_FEATURES)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_json_shape(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1})
            result = run(X86, axes, X86_FEATURES, "--json")
            self.assertEqual(result.returncode, 0)
            body = json.loads(result.stdout)
            self.assertEqual(body, {"gaps": [], "info": []})


class Immediates(unittest.TestCase):
    def test_missing_literal_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1, "imms": {"0": [8, 16]}})
            result = run(RISCV, axes, RISCV_FEATURES)
            self.assertEqual(result.returncode, 1)
            self.assertIn("imm(0) == 32 is never sampled", result.stdout)

    def test_threshold_needs_both_sides(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "t.gisel"
            source.write_text(THRESHOLD)
            one_side = profile(d, {"version": 1, "imms": {"0": [32]}})
            result = run(source, one_side)
            self.assertEqual(result.returncode, 1)
            self.assertIn("imm(0) > 32 is never true", result.stdout)
            both = Path(d) / "both.json"
            both.write_text(json.dumps({"version": 1, "imms": {"0": [32, 33]}}))
            result = run(source, both)
            self.assertEqual(result.returncode, 0, result.stdout)


class Orderings(unittest.TestCase):
    def test_no_ordering_axis_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1})
            result = run(A64, axes, A64_FEATURES)
            self.assertEqual(result.returncode, 1)
            self.assertIn("mem_ordering >= Unordered is never true",
                          result.stdout)

    def test_axis_without_notatomic_drops_a_branch(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1, "mems": {"orderings": [
                "Unordered", "Acquire", "Release",
                "SequentiallyConsistent"]}})
            result = run(A64, axes, A64_FEATURES)
            self.assertEqual(result.returncode, 1)
            self.assertIn("mem_ordering >= Unordered is never false",
                          result.stdout)

    def test_axis_with_notatomic_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1, "mems": {"orderings": [
                "NotAtomic", "Unordered", "Acquire", "Release",
                "SequentiallyConsistent"]}})
            result = run(A64, axes, A64_FEATURES)
            self.assertEqual(result.returncode, 0, result.stdout)


class Types(unittest.TestCase):
    def test_removed_type_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1, "types": {"remove": ["s8"]}})
            result = run(X86, axes, X86_FEATURES)
            self.assertEqual(result.returncode, 1)
            self.assertIn("type s8 is removed by types.remove", result.stdout)

    def test_explicit_miss_is_advisory(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1, "types": {
                "mode": "explicit", "values": ["s32"]}})
            result = run(X86, axes, X86_FEATURES)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("info: type s8 is not in the explicit type axis",
                          result.stdout)
            strict = run(X86, axes, X86_FEATURES, "--strict")
            self.assertEqual(strict.returncode, 1)
            self.assertIn("type s8 is not in the explicit type axis",
                          strict.stdout)

    def test_removed_mem_row_is_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1, "mems": {
                "remove": [["s8", "p0", "s8", 8]]}})
            result = run(A64, axes, A64_FEATURES)
            self.assertEqual(result.returncode, 1)
            self.assertIn("mem row s8/8 is removed by mems.remove",
                          result.stdout)


class Errors(unittest.TestCase):
    def test_unknown_profile_key_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1, "bogus": {}})
            result = run(X86, axes, X86_FEATURES)
            self.assertEqual(result.returncode, 2)
            self.assertIn("check-axes:", result.stderr)

    def test_missing_source_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            axes = profile(d, {"version": 1})
            result = run(Path(d) / "nope.gisel", axes)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
