"""Golden manifests must name exactly the cases their scripts run."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def manifest(path):
    rows = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        sha, name = line.split()
        rows[name] = sha
    return rows


class NightlyGraphs(unittest.TestCase):
    def test_manifest_names_match_the_script(self):
        script = (ROOT / "tools" / "check-nightly-graphs.sh").read_text()
        names = {name + ".json" for name in
                 re.findall(r'^\s*"([A-Za-z0-9-]+)\|', script, re.M)}
        rows = manifest(ROOT / "tests/artifacts/graph/nightly/SHA256")
        self.assertEqual(set(rows), names)
        self.assertTrue(all(len(sha) == 64 for sha in rows.values()))


class CaseFiles(unittest.TestCase):
    def test_manifest_names_match_the_script(self):
        script = (ROOT / "tools" / "check-cases-golden.sh").read_text()
        names = {name + ".cases.jsonl" for name in
                 re.findall(r'^\s*(x86|aarch64|riscv)\)$', script, re.M)}
        rows = manifest(ROOT / "tests/artifacts/cases/SHA256")
        self.assertEqual(set(rows), names)
        self.assertTrue(all(len(sha) == 64 for sha in rows.values()))


if __name__ == "__main__":
    unittest.main()
