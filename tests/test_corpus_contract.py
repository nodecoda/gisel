"""The corpus is gisel's input; the importer is somebody else's tool.

The C++ transcriber moved to the `gisel-anchor` project.  This test is the
gisel-side contract that keeps the checked-in corpus usable without any C++
tooling: every file must still compile to `--emit=core`, and must still carry
the rule count the last reviewed `--emit=core` produced (alias rulesets are
expanded, so this is higher than lint's source-rule count).  A count change is a corpus
change, not a refactor: update this table in the same commit as the corpus.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "corpus"

RULES = {
    "AArch64LegalizerInfo.gisel": 743,
    "ARMLegalizerInfo.gisel": 102,
    "M68kLegalizerInfo.gisel": 13,
    "MipsLegalizerInfo.gisel": 95,
    "PowerPCLegalizerInfo.gisel": 25,
    "RISCVLegalizerInfo.gisel": 413,
    "SPIRVLegalizerInfo.gisel": 353,
    "WebAssemblyLegalizerInfo.gisel": 109,
    "X86LegalizerInfo.gisel": 328,
}


class CorpusContract(unittest.TestCase):
    def test_every_corpus_compiles_to_core(self):
        for name, expected in sorted(RULES.items()):
            with self.subTest(corpus=name):
                with tempfile.TemporaryDirectory() as d:
                    out = Path(d) / "core.json"
                    r = subprocess.run(
                        [sys.executable, "-m", "gisel", "gen",
                         str(CORPUS / name), "--emit=core", "--out", str(out)],
                        capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    doc = json.loads(out.read_text())
                got = sum(len(rs["rules"]) for rs in doc["rulesets"])
                self.assertEqual(got, expected, name)

    def test_no_stray_corpus_files(self):
        self.assertEqual(sorted(p.name for p in CORPUS.glob("*.gisel")),
                         sorted(RULES))


if __name__ == "__main__":
    unittest.main()
