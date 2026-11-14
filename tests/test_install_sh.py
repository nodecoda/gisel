"""`scripts/install.sh` is the first command on a machine with no checkout.

The full install needs the network, so CI runs it for real (`install.yml`).
These tests cover what can be checked offline: the script is POSIX sh, every
exit path is reachable, and `--dry-run` prints the plan without touching the
filesystem or the index.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install.sh"


def run(*args, cwd=None):
    return subprocess.run(["sh", str(SCRIPT), *args], cwd=cwd or ROOT,
                          capture_output=True, text=True)


class Shape(unittest.TestCase):
    def test_it_is_posix_sh(self):
        text = SCRIPT.read_text()
        self.assertTrue(text.startswith("#!/bin/sh\n"), text[:20])
        # `[[` is a bashism; `curl ... | sh` on a minimal image is dash.
        self.assertNotIn("[[ ", text)
        for flag in ("set -eu",):
            self.assertIn(flag, text)

    def test_shell_parses_it(self):
        done = subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True,
                              text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


class DryRun(unittest.TestCase):
    def test_prefix_plans_a_venv_without_touching_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "prefix"
            done = run("--prefix", str(out), "--dry-run")
            self.assertEqual(done.returncode, 0, done.stderr)
            # The plan goes to stdout (`+ command`), the narration to stderr;
            # read both so the assertion does not depend on buffering order.
            both = done.stdout + done.stderr
            self.assertIn("install.sh: venv", both)
            self.assertIn("-m venv", both)
            self.assertIn("pip install", both)
            self.assertIn("install.sh: dry run, nothing was installed", both)
            self.assertFalse(out.exists(), "--dry-run created %s" % out)

    def test_from_git_prints_the_pinned_specs(self):
        done = run("--from-git", "--dry-run")
        self.assertEqual(done.returncode, 0, done.stderr)
        both = done.stdout + done.stderr
        self.assertIn("git+https://github.com/nodecoda/gisel@", both)
        self.assertIn("git+https://github.com/nodecoda/gisel-anchor@", both)
        self.assertIn("git+https://github.com/nodecoda/gisel-ab@", both)

    def test_rev_overrides_win_over_the_manifest(self):
        done = run("--dry-run", "--rev-gisel", "abc123", "--rev-anchor",
                   "def456", "--rev-ab", "012345")
        self.assertEqual(done.returncode, 0, done.stderr)
        both = done.stdout + done.stderr
        self.assertIn("gisel@abc123", both)
        self.assertIn("gisel-anchor@def456", both)
        self.assertIn("gisel-ab@012345", both)


class Usage(unittest.TestCase):
    def test_help(self):
        done = run("--help")
        self.assertEqual(done.returncode, 0)
        self.assertIn("--prefix", done.stdout)
        self.assertIn("--from-git", done.stdout)

    def test_unknown_argument_is_exit_two(self):
        done = run("--nope")
        self.assertEqual(done.returncode, 2)
        self.assertIn("unknown argument", done.stderr)


if __name__ == "__main__":
    unittest.main()
