"""Artifact gates: the checked-in .gisel reproduces the checked-in artifacts.

M0 gate: the .td (TableGen compatibility backend).
M1 gate: the .inc (-gen-legalizer), byte for byte, with no llvm-tblgen run.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
CORPORA = (("x86", "X86LegalizerInfo"), ("aarch64", "AArch64LegalizerInfo"))


def run(*args, env=None):
    return subprocess.run([sys.executable, "-m", "gisel.cli", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


class GoldenTd(unittest.TestCase):
    def test_generated_td_matches_golden(self):
        for name, src in CORPORA:
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / f"{name}.td"
                r = run("gen", str(TESTS / "corpus" / f"{src}.gisel"),
                        "--emit=td", "--out", str(out))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(
                    out.read_text(),
                    (TESTS / "golden" / f"{name}.td").read_text(),
                    f"{name}: generated .td differs from golden")

    def test_check_is_up_to_date(self):
        for name, src in CORPORA:
            r = run("check", str(TESTS / "corpus" / f"{src}.gisel"),
                    "--emit=td", "--td", str(TESTS / "golden" / f"{name}.td"))
            self.assertEqual(r.returncode, 0, r.stderr)


class GoldenInc(unittest.TestCase):
    """M1: `gisel gen --emit=inc` is byte-identical to -gen-legalizer."""

    def test_generated_inc_matches_golden(self):
        for name, src in CORPORA:
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / f"{name}.inc"
                r = run("gen", str(TESTS / "corpus" / f"{src}.gisel"),
                        "--emit=inc", "--out", str(out))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(
                    out.read_bytes(), (TESTS / "artifacts" / f"{name}.inc").read_bytes(),
                    f"{name}: generated .inc differs from golden")

    def test_check_inc_is_up_to_date(self):
        for name, src in CORPORA:
            r = run("check", str(TESTS / "corpus" / f"{src}.gisel"),
                    "--emit=inc", "--against", str(TESTS / "artifacts" / f"{name}.inc"))
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_llvm_tblgen_needed(self):
        """PATH without llvm-tblgen still reproduces both artifacts."""
        env = dict(os.environ, PATH="/usr/bin:/bin")
        for name, src in CORPORA:
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / f"{name}.inc"
                r = run("gen", str(TESTS / "corpus" / f"{src}.gisel"),
                        "--emit=inc", "--out", str(out), env=env)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(out.read_bytes(),
                                 (TESTS / "artifacts" / f"{name}.inc").read_bytes())

    def test_terminal_call_count_is_conserved(self):
        """One terminal per rule, plus one `.immIdx` per ImmIdx record."""
        expected = {"x86": (332, 0), "aarch64": (743, 3)}
        total = 0
        for name, _ in CORPORA:
            text = (TESTS / "artifacts" / f"{name}.inc").read_text()
            calls = re.findall(r"^      \.([A-Za-z0-9_]+)", text, re.M)
            imm = [c for c in calls if c == "immIdx"]
            rules, imm_expected = expected[name]
            self.assertEqual(len(calls) - len(imm), rules, name)
            self.assertEqual(len(imm), imm_expected, name)
            total += len(calls)
        self.assertEqual(total, 1078)


class ShimCoverage(unittest.TestCase):
    """G1: every (operator, observation, target) triple has a C++ shim."""

    def test_every_corpus_triple_has_a_shim(self):
        sys.path.insert(0, str(ROOT))
        from gisel import td
        from gisel.backend import llvm_inc as inc

        seen = set()
        for _, src in CORPORA:
            gs = td.parse_gisel((TESTS / "corpus" / f"{src}.gisel").read_text())
            for rs in gs["rulesets"]:
                for rule in rs["rules"]:
                    on = rule.get("on")
                    on_form = (inc.ONSERVATION_FORM.get(on["kind"], on["kind"])
                               if on else "")
                    seen.add((rule["op"], on_form,
                              rule["to"]["kind"] if rule.get("to") else ""))
        missing = sorted(t for t in seen if t not in inc.SHIM_TABLE)
        self.assertEqual(missing, [])
        self.assertEqual(len(seen), 25)


class NegativeControl(unittest.TestCase):
    """A changed source must move the artifact; otherwise the gate is vacuous."""

    def _gen(self, text, d):
        src = Path(d) / "X86LegalizerInfo.gisel"
        src.write_text(text)
        out = Path(d) / "x86.inc"
        r = run("gen", str(src), "--emit=inc", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        return src, out

    def test_feature_change_is_visible(self):
        base = (TESTS / "corpus" / "X86LegalizerInfo.gisel").read_text()
        # The normal form keys a feature by its expression text, so a
        # mutation has to rewrite every occurrence.
        mutated = base.replace("Subtarget.canUseCMOV()", "Subtarget.hasCMOV()")
        self.assertNotEqual(base, mutated)
        golden = (TESTS / "artifacts" / "x86.inc").read_text()
        with tempfile.TemporaryDirectory() as d:
            src, out = self._gen(mutated, d)
            self.assertNotEqual(out.read_text(), golden)
            self.assertIn("Subtarget.hasCMOV()", out.read_text())
            r = run("check", str(src), "--emit=inc",
                    "--against", str(TESTS / "artifacts" / "x86.inc"))
            self.assertEqual(r.returncode, 1)
            self.assertIn("STALE", r.stderr)

    def test_target_change_is_visible(self):
        base = (TESTS / "corpus" / "X86LegalizerInfo.gisel").read_text()
        mutated = base.replace("pow2_min(8)", "pow2_min(16)", 1)
        self.assertNotEqual(base, mutated)
        golden = (TESTS / "artifacts" / "x86.inc").read_text()
        with tempfile.TemporaryDirectory() as d:
            _, out = self._gen(mutated, d)
            self.assertNotEqual(out.read_text(), golden)


if __name__ == "__main__":
    unittest.main()
