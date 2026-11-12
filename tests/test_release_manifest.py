"""The release manifest must fail loudly, not write a half-truth."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "release-manifest.py"


def module():
    spec = importlib.util.spec_from_file_location("release_manifest", TOOL)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class ReleaseManifest(unittest.TestCase):
    def test_missing_sibling_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, AB_SRC=str(Path(tmp) / "no-ab"))
            proc = subprocess.run(
                [sys.executable, str(TOOL), "--out", str(Path(tmp) / "r.json")],
                capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("not a git checkout", proc.stderr)

    def test_checkout_refs_only_reads_the_gisel_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wf = root / ".github" / "workflows" / "ci.yml"
            wf.parent.mkdir(parents=True)
            wf.write_text(
                "    steps:\n"
                "      - uses: actions/checkout@v7\n"
                "        with:\n"
                "          repository: someone/else\n"
                "          ref: ignored\n"
                "      - uses: actions/checkout@v7\n"
                "        with:\n"
                "          repository: nodecoda/gisel\n"
                "          path: gisel\n"
                "          ref: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n")
            refs = module().checkout_refs(root)
        self.assertEqual([ref for _, ref in refs], ["a" * 40])

    def test_stale_refs_fail_the_cohort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wf = root / ".github" / "workflows" / "ci.yml"
            wf.parent.mkdir(parents=True)
            wf.write_text(
                "      - uses: actions/checkout@v7\n"
                "        with:\n"
                "          repository: nodecoda/gisel\n"
                "          ref: %s\n" % ("b" * 40))
            stale = module().stale_refs((("ab", root),), "c" * 40)
        self.assertEqual(len(stale), 1)
        self.assertIn("checks out " + "b" * 12, stale[0])

    def test_manifest_file_reads_every_case_target(self):
        rows = module().manifest_file(
            ROOT / "tests" / "artifacts" / "cases" / "SHA256")
        self.assertEqual(set(rows), {
            "x86.cases.jsonl", "aarch64.cases.jsonl", "riscv.cases.jsonl"})
        self.assertTrue(all(len(sha) == 64 for sha in rows.values()))


if __name__ == "__main__":
    unittest.main()
