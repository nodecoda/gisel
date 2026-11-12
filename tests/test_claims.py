"""Every claim in docs/CLAIMS.md must cite something that exists."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Claims(unittest.TestCase):
    def test_every_cited_path_exists(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check-claims.py")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_the_table_is_not_empty(self):
        text = (ROOT / "docs" / "CLAIMS.md").read_text()
        rows = [line for line in text.splitlines()
                if line.startswith("|") and "---" not in line]
        self.assertGreaterEqual(len(rows) - 1, 10)


if __name__ == "__main__":
    unittest.main()
