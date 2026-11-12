"""`clamp_min`/`clamp_max` keep their source constructor through lowering."""

import json
import tempfile
import unittest
from pathlib import Path

from gisel import ast as A
from gisel.backend import core_json
from gisel.backend import llvm_inc as I

SOURCE = """\
type S8 = LLT::scalar(8)
type S32 = LLT::scalar(32)

ruleset G_ADD: G_ADD
    clamp_max(0, S8, 16)
"""


class ClampSource(unittest.TestCase):
    def setUp(self):
        self.program = A.parse_program(SOURCE)

    def test_source_operator_survives_normalisation(self):
        rule = self.program.rulesets[0].rules[0]
        self.assertEqual(rule.source_op, "clamp_max")
        self.assertEqual(rule.op, "fewer")

    def test_inc_spells_clamp_max(self):
        text = I.emit_inc(self.program, "T.gisel")
        self.assertIn("clampMaxNumElements", text)

    def test_core_does_not_leak_source_op(self):
        text = core_json.emit_core(self.program, "T.gisel")
        self.assertNotIn("source_op", text)
        json.loads(text)


if __name__ == "__main__":
    unittest.main()
