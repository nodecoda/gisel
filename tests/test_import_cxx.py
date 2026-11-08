"""`tools/import-cxx.py`: the C++ constructor -> `.gisel` importer."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "import-cxx.py"
CORPUS = ROOT / "tests" / "corpus"
FIXTURE = ROOT / "tests" / "fixtures" / "legalizer-ctor.cpp"
RISCV_SRC = Path(os.environ.get(
    "GS_RISCV_SRC",
    "/home/ubuntu/llvm/trees/explore/llvm/lib/Target/RISCV/GISel/"
    "RISCVLegalizerInfo.cpp"))


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *args],
                          cwd=ROOT, capture_output=True, text=True)


def body(text):
    """Drop the generated header, which names the source path."""
    return text.split("//===------", 1)[1]


class Fixture(unittest.TestCase):
    def test_if_else_becomes_two_gated_tables(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "T.gisel"
            r = run("RISCV", str(FIXTURE), "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("0 refused", r.stdout)
            text = out.read_text()
            # `if (ST.hasStdExtZbb()) { legalFor } else { maxScalar }`
            self.assertIn(
                'legal (R_ST_hasStdExtZbb and '
                "in_pairs(slot(0), slot(1), [[R_s32, R_s32]]))", text)
            self.assertIn(
                'narrow(slot(0), ty(R_s32)) when not '
                'R_ST_hasStdExtZbb', text)
            # `minScalar(pred, 0, s32)` is a gated widen, not an unconditional one.
            self.assertIn(
                'widen(slot(0), ty(R_s32)) when '
                'R_ST_hasStdExtZbb', text)
            self.assertIn("lower true", text)

    def test_predicate_first_mutations_are_gated(self):
        # `minScalar(ST.hasStdExtZbb(), 0, sXLen)` in G_ABS: the leading
        # predicate is a gate, not a no-op.  Dropping it would widen in the
        # non-Zbb case too.
        text = (CORPUS / "RISCVLegalizerInfo.gisel").read_text()
        self.assertIn('widen(slot(0), ty(R_sXLen)) when '
                      'R_ST_hasStdExtZbb', text)

    def test_every_statement_is_either_emitted_or_refused(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "T.gisel"
            r = run("RISCV", str(FIXTURE), "--out", str(out), "--stats")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn("refused line", r.stdout)
            # 4 builder calls: legalFor, clampScalar (2 rules), maxScalar, minScalar, lower
            self.assertIn("TOTAL", r.stdout)
            total = [l for l in r.stdout.splitlines() if l.startswith("TOTAL")][0]
            self.assertEqual(total.split()[-2:], ["5", "6"])


class RisCvCorpus(unittest.TestCase):
    def test_corpus_lints(self):
        r = subprocess.run(
            [sys.executable, "-m", "gisel.cli", "lint",
             str(CORPUS / "RISCVLegalizerInfo.gisel")],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 error(s)", r.stdout)
        self.assertIn("402 rule(s)", r.stdout)

    @unittest.skipUnless(RISCV_SRC.exists(), "RISCVLegalizerInfo.cpp not present")
    def test_reimport_reproduces_the_checked_in_corpus(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "R.gisel"
            r = run("RISCV", str(RISCV_SRC), "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("0 refused", r.stdout)
            self.assertIn("402 rules", r.stdout)
            self.assertEqual(body(out.read_text()),
                             body((CORPUS / "RISCVLegalizerInfo.gisel").read_text()))


if __name__ == "__main__":
    unittest.main()
