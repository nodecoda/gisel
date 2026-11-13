"""`gisel doctor` is the first command a new install runs.

Its job is to fail loudly and *locally*: every failing check names the file
or the version and tells the reader what to reinstall.  These tests pin the
two contracts that make it useful -- exit codes (0 / 2, never 1) and the
`{checks:[{name,status,detail,fix}]}` JSON shape -- plus one real failure.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable, "-m", "gisel", "doctor", *args],
                          cwd=ROOT, capture_output=True, text=True)


class HealthyInstall(unittest.TestCase):
    def test_text_mode_passes(self):
        done = run()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("gisel doctor", done.stdout)
        self.assertRegex(done.stdout, r"corpora\s+ok\s+9 targets")

    def test_json_mode_is_the_contract_shape(self):
        done = run("--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        doc = json.loads(done.stdout)
        self.assertTrue(doc["ok"])
        names = [c["name"] for c in doc["checks"]]
        for required in ("python", "version", "opcode-slots", "corpora",
                         "commands"):
            self.assertIn(required, names)
        for check in doc["checks"]:
            self.assertEqual(set(check) - {"fix"}, {"name", "status", "detail"})
            self.assertEqual(check["status"], "ok")

    def test_every_bundled_target_is_hash_pinned(self):
        doc = json.loads(run("--json").stdout)
        corpora = [c for c in doc["checks"] if c["name"].startswith("corpus:")]
        self.assertEqual(len(corpora), 9)
        for check in corpora:
            self.assertRegex(check["detail"], r"^[0-9a-f]{12} \S+\.gisel$")

    def test_it_never_uses_exit_code_one(self):
        # 1 means "the answer is no" in this CLI; a broken install is not an
        # answer about rules.
        self.assertEqual(run().returncode, 0)


class BrokenInstall(unittest.TestCase):
    def test_a_missing_slot_table_fails_with_a_fix(self):
        from gisel import doctor
        real = doctor._data_dir()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(doctor, "_data_dir", lambda: Path(tmp)):
                found = doctor.checks()
        bad = [c for c in found if c.name == "opcode-slots"]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].status, "fail")
        self.assertIn("reinstall", bad[0].fix)
        self.assertTrue(real.is_dir())

    def test_a_missing_corpus_names_the_target(self):
        from gisel import corpus as corpora, doctor
        error = corpora.CorpusError("bundled file is missing: /nowhere.gisel")
        with mock.patch.object(corpora, "get", side_effect=error):
            found = doctor._corpora()
        bad = [c for c in found if c.status == "fail"]
        self.assertTrue(bad)
        self.assertIn("--corpus", bad[0].fix)


if __name__ == "__main__":
    unittest.main()
