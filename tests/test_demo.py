"""`gisel demo` is the first command a reader runs; these tests keep it honest.

The demo is a script over the four verbs, so the interesting failures are:
it must not need a checkout or LLVM, it must write where it says, and a stage
that answers "no" must stop the run with that stage's exit code instead of
printing a cheerful summary.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None):
    return subprocess.run([sys.executable, "-m", "gisel", "demo", *args],
                          cwd=cwd or ROOT, capture_output=True, text=True)


class EndToEnd(unittest.TestCase):
    # M68k is the documented five-minute corpus: 13 rules, so all four stages
    # finish in well under a second and the assertions stay about behaviour.
    def test_one_command_runs_every_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "artifacts"
            done = run("--corpus", "m68k", "--out", str(out))
            self.assertEqual(done.returncode, 0, done.stderr)
            for name in ("m68k.inc", "m68k.cases.jsonl"):
                path = out / name
                self.assertTrue(path.is_file(), path)
                self.assertGreater(path.stat().st_size, 0, path)
            self.assertIn("[4/4] build the quotient graph", done.stdout)
            self.assertIn("demo: ok", done.stdout)
            self.assertIn("wrote:", done.stdout)
            self.assertIn(str(out.resolve() / "m68k.inc"), done.stdout)

    def test_the_questions_are_reproducible(self):
        with tempfile.TemporaryDirectory() as a, \
                tempfile.TemporaryDirectory() as b:
            self.assertEqual(run("--corpus", "m68k", "--out", a).returncode, 0)
            self.assertEqual(run("--corpus", "m68k", "--out", b).returncode, 0)
            self.assertEqual((Path(a) / "m68k.cases.jsonl").read_bytes(),
                             (Path(b) / "m68k.cases.jsonl").read_bytes())

    def test_it_creates_a_missing_out_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "a" / "b" / "c"
            done = run("--corpus", "m68k", "--out", str(out))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue((out / "m68k.inc").is_file())


class Failures(unittest.TestCase):
    def test_unknown_corpus_is_a_usage_error(self):
        done = run("--corpus", "nope")
        self.assertEqual(done.returncode, 2)
        self.assertIn("unknown corpus", done.stderr)
        self.assertIn("x86", done.stderr)

    def test_a_failing_stage_stops_the_run(self):
        # An unknown graph configuration fails the last stage; the demo must
        # return that stage's rc and never print the summary line.
        with tempfile.TemporaryDirectory() as tmp:
            done = run("--corpus", "m68k", "--out", tmp,
                       "--config", "no-such-config")
            self.assertEqual(done.returncode, 2, done.stdout)
            self.assertIn("stage 4 failed", done.stderr)
            self.assertNotIn("demo: ok", done.stdout)

    def test_help_names_the_defaults(self):
        done = run("--help")
        self.assertEqual(done.returncode, 0)
        self.assertIn("gisel demo", done.stdout)
        self.assertIn("x86", done.stdout)


if __name__ == "__main__":
    unittest.main()
