"""The graph goldens cannot be edited to make a migration pass.

`tools/check-graph-golden.sh` regenerates the two recordings; this test only
pins their bytes.  It is deliberately cheap: the real gate is the script, which
runs `gisel graph` and compares output.
"""

from __future__ import annotations

import hashlib
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


if __name__ == "__main__":
    unittest.main()
