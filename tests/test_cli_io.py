"""`--out` is a file boundary: a path that cannot be written is exit code 2.

`spec/cli.md` §2 lists "写盘失败" under "无法开始".  Before this test the two
JSONL verbs let the `OSError` escape as a traceback and a shell saw rc=1,
which reads as "the input was fine and the answer is no".
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M68K = ROOT / "tests" / "corpus" / "M68kLegalizerInfo.gisel"
UNWRITABLE = "/proc/gisel-does-not-exist/out.jsonl"


def run(*args):
    return subprocess.run([sys.executable, "-m", "gisel", *args],
                          cwd=ROOT, capture_output=True, text=True)


class UnwritableOutIsNotAConclusion(unittest.TestCase):
    def test_cases(self):
        r = run("cases", str(M68K), "--out", UNWRITABLE)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(UNWRITABLE, r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_domain(self):
        r = run("domain", str(M68K), "--out", UNWRITABLE)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(UNWRITABLE, r.stderr)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
