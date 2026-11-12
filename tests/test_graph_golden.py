"""The graph goldens cannot be edited to make a migration pass.

`tools/check-graph-golden.sh` regenerates the four recordings; this test pins
their bytes and the two closure contracts.  It is deliberately cheap: the real
gate is the script, which runs `gisel graph` and compares output.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ARTIFACTS = Path(__file__).resolve().parent / "artifacts" / "graph"


class GraphGoldenManifest(unittest.TestCase):
    def test_manifest_matches_recorded_bytes(self):
        manifest = {}
        for line in (ARTIFACTS / "SHA256").read_text().splitlines():
            if not line.strip():
                continue
            digest, name = line.split()
            manifest[name.lstrip("./")] = digest
        files = {p.name for p in ARTIFACTS.glob("*.json")}
        self.assertEqual(files, set(manifest), "manifest and json files disagree")
        for name, expected in manifest.items():
            actual = hashlib.sha256((ARTIFACTS / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)


class GraphGoldenInvariants(unittest.TestCase):
    def reports(self, name):
        path = ARTIFACTS / name
        return json.loads(path.read_text())["reports"]

    def test_closure_counts_are_self_consistent(self):
        for path in sorted(ARTIFACTS.glob("*.json")):
            for report in json.loads(path.read_text())["reports"]:
                closure = report["closure"]
                self.assertTrue(closure["checked"], path.name)
                self.assertEqual(
                    closure["count"], sum(closure["kinds"].values()),
                    "%s: closure.count and kinds disagree" % path.name)

    def test_default_goldens_record_the_coverage_gap(self):
        for name in ("x86-none.json", "riscv-rv64gc.json"):
            for report in self.reports(name):
                self.assertEqual(report["cycles"], 0, name)
                self.assertGreater(report["closure"]["count"], 0, name)
                self.assertFalse(report["closure"]["ok"], name)

    def test_refine_goldens_are_closed(self):
        for name in ("x86-none-refine.json", "riscv-rv64gc-refine.json"):
            for report in self.reports(name):
                self.assertEqual(report["cycles"], 0, name)
                self.assertEqual(report["closure"]["count"], 0, name)
                self.assertTrue(report["closure"]["ok"], name)
                # Refinement may add classes, never remove them.
                self.assertGreaterEqual(report["classes"],
                                        report["classes_before"], name)
                # Outside states are sinks, not edges: they stay counted.
                self.assertGreater(report["outside"], 0, name)


if __name__ == "__main__":
    unittest.main()
