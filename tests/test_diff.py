"""Full-set differential: missing keys are failures, not uncovered points."""

import json
import tempfile
import unittest
from pathlib import Path

from gisel import diff


def row(name, types, action="Legal", new_type="LLT_invalid", config="C0"):
    return {"config": config, "name": name, "types": types, "mem": None,
            "imms": [], "action": action, "type_idx": 0, "new_type": new_type}


class Diff(unittest.TestCase):
    def write(self, rows):
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        for r in rows:
            f.write(json.dumps(r) + "\n")
        f.close()
        return f.name

    def run_diff(self, a, b):
        pa, pb = self.write(a), self.write(b)
        ra, e1 = diff._load(pa)
        rb, e2 = diff._load(pb)
        r = diff.compare(ra, rb)
        r["errors"] = e1 + e2
        return r

    def test_agree(self):
        a = [row("G_ADD", ["s32"])]
        r = self.run_diff(a, a)
        self.assertEqual((r["disagree"], r["missing_ref"], r["missing_ours"]),
                         (0, 0, 0))
        self.assertEqual(r["agree"], 1)

    def test_disagree(self):
        a = [row("G_ADD", ["s64"], "WidenScalar", "s64")]
        b = [row("G_ADD", ["s64"], "Legal", "LLT_invalid")]
        r = self.run_diff(a, b)
        self.assertEqual(r["disagree"], 1)
        self.assertEqual((r["missing_ref"], r["missing_ours"]), (0, 0))

    def test_missing_on_each_side(self):
        a = [row("G_ADD", ["s32"]), row("G_ADD", ["s64"])]
        b = [row("G_ADD", ["s32"]), row("G_SUB", ["s32"])]
        r = self.run_diff(a, b)
        self.assertEqual(r["missing_ref"], 1)   # G_SUB only in ours
        self.assertEqual(r["missing_ours"], 1)  # G_ADD s64 only in ref

    def test_duplicate_key_is_an_error(self):
        a = [row("G_ADD", ["s32"]), row("G_ADD", ["s32"])]
        pa = self.write(a)
        _, errors = diff._load(pa)
        self.assertEqual(errors, 1)

    def test_symmetric_unanswerable_is_agree(self):
        a = [row("G_CTLZ", ["p0:32", "s32"])]
        a[0].update(status="unanswerable", reason="asserted")
        b = [dict(a[0])]
        r = self.run_diff(a, b)
        self.assertEqual(r["agree"], 1)
        self.assertEqual(r["unanswerable"], 1)
        self.assertEqual(r["disagree"], 0)

    def test_answerable_and_unanswerable_disagree(self):
        a = [row("G_CTLZ", ["p0:32", "s32"])]
        b = [dict(a[0], status="unanswerable", reason="asserted")]
        r = self.run_diff(a, b)
        self.assertEqual(r["disagree"], 1)


if __name__ == "__main__":
    unittest.main()
