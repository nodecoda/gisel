"""`tools/audit-docs.py` must be clean here and must bite when it is not.

The auditor is the discovery pass for claims the gate tests do not replay.
Running it as a test keeps the error classes (links, verbs, `--emit` values,
the two landing pages' shape) from regressing; the negative control keeps the
auditor itself honest.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "audit-docs.py"


def audit(root=None):
    command = [sys.executable, str(TOOL), "--json"]
    if root is not None:
        command += ["--root", str(root)]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    return run.returncode, json.loads(run.stdout) if run.stdout else None, run.stderr


class ThisTree(unittest.TestCase):
    def test_no_document_is_already_wrong(self):
        rc, report, err = audit()
        self.assertEqual(rc, 0, json.dumps(report, indent=2, ensure_ascii=False) + err)
        self.assertEqual(report["errors"], [])


class NegativeControl(unittest.TestCase):
    def test_a_broken_link_and_a_removed_backend_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "# demo\n\n"
                "[gone](missing.md)\n\n"
                "```sh\npython3 -m gisel gen --emit=td x.gisel\n```\n")
            rc, report, err = audit(root)
        self.assertEqual(rc, 1, err)
        kinds = {item["kind"] for item in report["errors"]}
        self.assertIn("broken link", kinds)
        self.assertIn("unknown --emit value", kinds)


if __name__ == "__main__":
    unittest.main()
