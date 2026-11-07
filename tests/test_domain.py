"""Answerless domain enumeration: axes come from declarations, not the rules."""

import unittest
from pathlib import Path

from gisel import cases, domain

ROOT = Path(__file__).resolve().parents[1]
X86 = ROOT / "tests" / "corpus" / "X86LegalizerInfo.gisel"


class X86Domain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = cases.document(X86)
        cls.features = cases.derive_features(cls.doc)

    def rows(self, **kw):
        return list(domain.enumerate_domain(X86, self.features,
                                            configs=["none"], **kw))

    def test_points_and_axes(self):
        rows = self.rows()
        # 26,092 points the old D* enumerated, plus the five zero-type-slot
        # opcodes (G_BR, G_TRAP, G_DEBUGTRAP, G_UBSANTRAP, G_INVOKE_REGION_START)
        # that -gen-legalizer also emits.
        self.assertEqual(len(rows), 26097)
        types, mems, _ = domain.domain_axes(X86)
        self.assertEqual(len(types), 24)
        self.assertEqual(len(mems), 23)

    def test_no_answer_fields(self):
        row = self.rows()[0]
        self.assertEqual(set(row), {"config", "name", "types", "mem", "imms"})

    def test_pointer_slots_are_fixed(self):
        rows = self.rows()
        load = [r for r in rows if r["name"] == "G_LOAD"]
        self.assertEqual(len(load), 552)          # 24 value types x 23 mem descs
        self.assertTrue(all(r["types"][1] == "p0:64" for r in load))
        ptr_add = [r for r in rows if r["name"] == "G_PTR_ADD"]
        self.assertEqual(len(ptr_add), 24)
        self.assertTrue(all(r["types"][0] == "p0:64" for r in ptr_add))

    def test_pointer_width_is_a_configuration_axis(self):
        rows = self.rows(pointer_width=32)
        self.assertEqual(len(rows), 26097)
        values = {t for r in rows for t in r["types"]}
        self.assertIn("p0:32", values)
        self.assertIn("v2p0:32", values)
        self.assertNotIn("p0:64", values)

    def test_enumeration_is_deterministic(self):
        self.assertEqual(self.rows(), self.rows())


if __name__ == "__main__":
    unittest.main()
