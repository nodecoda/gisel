"""Answer files: the reader in gisel, and the workbench A/B command.

`gisel.answers` only reads answer JSONL — `cases --queries`/`--oracle` needs
that.  The full-set comparison, its report and its exit codes belong to
`tools/ab/diff.py`: comparing two implementations is done *with* gisel, not by
gisel (`docs/SCOPE.md`).
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gisel import answers

ROOT = Path(__file__).resolve().parents[1]
DIFF = ROOT / "tools" / "ab" / "diff.py"


def row(name, types, action="Legal", new_type="LLT_invalid", config="C0"):
    return {"config": config, "name": name, "types": types, "mem": None,
            "imms": [], "action": action, "type_idx": 0, "new_type": new_type}


def write(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in rows:
        f.write(json.dumps(r) + "\n")
    f.close()
    return f.name


class Reader(unittest.TestCase):
    """`gisel.answers` is a reader; it does not compare."""

    def test_identical_duplicate_is_merged(self):
        path = write([row("G_ADD", ["s32"]), row("G_ADD", ["s32"])])
        got, errors = answers.load(path)
        self.assertEqual((len(got), errors), (1, 0))

    def test_conflicting_duplicate_is_an_error(self):
        path = write([row("G_ADD", ["s32"]),
                      row("G_ADD", ["s32"], "WidenScalar", "s64")])
        got, errors = answers.load(path)
        self.assertEqual((len(got), errors), (1, 1))


class Diff(unittest.TestCase):
    def run_diff(self, a, b, *flags):
        pa, pb = write(a), write(b)
        r = subprocess.run(
            [sys.executable, str(DIFF), pa, pb, "--json", *flags],
            capture_output=True, text=True)
        self.assertIn(r.returncode, (0, 1, 2), r.stderr)
        return r.returncode, json.loads(r.stdout)

    def test_agree(self):
        a = [row("G_ADD", ["s32"])]
        rc, r = self.run_diff(a, a)
        self.assertEqual(rc, 0)
        self.assertEqual((r["disagree"], r["missing_ref"], r["missing_ours"]),
                         (0, 0, 0))
        self.assertEqual(r["agree"], 1)

    def test_disagree(self):
        a = [row("G_ADD", ["s64"], "WidenScalar", "s64")]
        b = [row("G_ADD", ["s64"], "Legal", "LLT_invalid")]
        rc, r = self.run_diff(a, b)
        self.assertEqual(rc, 1)
        self.assertEqual(r["disagree"], 1)
        self.assertEqual((r["missing_ref"], r["missing_ours"]), (0, 0))

    def test_missing_on_each_side(self):
        a = [row("G_ADD", ["s32"]), row("G_ADD", ["s64"])]
        b = [row("G_ADD", ["s32"]), row("G_SUB", ["s32"])]
        rc, r = self.run_diff(a, b)
        self.assertEqual(rc, 1)
        self.assertEqual(r["missing_ref"], 1)   # G_SUB only in ours
        self.assertEqual(r["missing_ours"], 1)  # G_ADD s64 only in ref

    def test_symmetric_unanswerable_is_agree(self):
        a = [row("G_CTLZ", ["p0:32", "s32"])]
        a[0].update(status="unanswerable", reason="asserted")
        b = [dict(a[0])]
        rc, r = self.run_diff(a, b)
        self.assertEqual(rc, 0)
        self.assertEqual(r["agree"], 1)
        self.assertEqual(r["unanswerable"], 1)
        self.assertEqual(r["disagree"], 0)

    def test_answerable_and_unanswerable_disagree(self):
        a = [row("G_CTLZ", ["p0:32", "s32"])]
        b = [dict(a[0], status="unanswerable", reason="asserted")]
        rc, r = self.run_diff(a, b)
        self.assertEqual(rc, 1)
        self.assertEqual(r["disagree"], 1)


class Command(unittest.TestCase):
    """The workbench verb's human-readable output and its exit codes."""

    def run_diff(self, a, b):
        pa, pb = write(a), write(b)
        return subprocess.run([sys.executable, str(DIFF), pa, pb],
                              capture_output=True, text=True)

    def test_agree_returns_zero(self):
        rows = [row("G_ADD", ["s32"])]
        r = self.run_diff(rows, rows)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("disagree=0", r.stdout)

    def test_disagree_returns_one(self):
        a = [row("G_ADD", ["s64"], "WidenScalar", "s64")]
        b = [row("G_ADD", ["s64"], "Legal", "LLT_invalid")]
        r = self.run_diff(a, b)
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISMATCH", r.stdout)

    def test_unreadable_line_is_exit_two(self):
        pa, pb = write([row("G_ADD", ["s32"])]), write([row("G_ADD", ["s32"])])
        with open(pa, "a") as f:
            f.write("not json\n")
        r = subprocess.run([sys.executable, str(DIFF), pa, pb],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
