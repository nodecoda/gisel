"""The nine-corpus byte gate (G0).

`test_artifacts.py` freezes three big files; this gate covers every shipped
corpus with a SHA256 manifest and must fail when either side moves.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "check-nine-corpora.sh"


class NineCorpora(unittest.TestCase):
    def run_gate(self, *args):
        return subprocess.run(["bash", str(SCRIPT), *args], cwd=ROOT,
                              capture_output=True, text=True)

    def test_all_nine_are_byte_identical(self):
        proc = self.run_gate()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("nine corpora: 9 targets", proc.stdout)

    def test_a_changed_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out = tmp / "out"
            manifest = tmp / "SHA256"
            proc = self.run_gate("--record", "--out", str(out),
                                 "--manifest", str(manifest))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = manifest.read_text()
            first, rest = text.splitlines(True)[0], text.splitlines(True)[1:]
            digest, name = first.split()
            manifest.write_text("0" * 64 + "  " + name + "\n" + "".join(rest))
            proc = self.run_gate("--out", str(out),
                                 "--manifest", str(manifest))
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertIn(name, proc.stdout + proc.stderr)
            self.assertNotEqual(digest, "0" * 64)


if __name__ == "__main__":
    unittest.main()
