"""Answerless domain enumeration: axes come from declarations, not the rules."""

import tempfile
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
        # that -gen-legalizer also emits; minus the points whose type tuple
        # cannot be a real MIR instruction (see `cases.type_shape_ok`).  The
        # shift family alone drops 768: 256 each for G_SHL/G_LSHR/G_ASHR.
        self.assertEqual(len(rows), 22835)
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
        self.assertEqual(len(rows), 22835)
        values = {t for r in rows for t in r["types"]}
        self.assertIn("p0:32", values)
        self.assertIn("v2p0:32", values)
        self.assertNotIn("p0:64", values)

    def test_enumeration_is_deterministic(self):
        self.assertEqual(self.rows(), self.rows())

    def test_diagnostics_count_every_dropped_tuple(self):
        """The denominator must be recomputable from the run's own output.

        `shape_dropped` counts type tuples, not queries: the drop happens
        before the mem/imm product, so one dropped tuple would have become
        several queries.
        """
        stats = {}
        rows = list(domain.enumerate_domain(
            X86, self.features, configs=["none"], stats=stats))
        self.assertEqual(stats["shape_dropped_total"],
                         sum(stats["shape_dropped"].values()))
        self.assertGreater(stats["shape_dropped_total"], 0)
        self.assertEqual(stats["shape_dropped"].get("G_SHL"), 256)
        self.assertEqual(stats["skipped_opcodes"],
                         ["G_INTRINSIC", "G_INTRINSIC_W_SIDE_EFFECTS"])
        self.assertEqual(len(rows), 22835)

    def test_diagnostics_are_present_even_when_empty(self):
        stats = {}
        list(domain.enumerate_domain(X86, self.features, configs=["none"],
                                     stats=stats))
        self.assertIn("skipped_opcodes", stats)
        self.assertIn("shape_dropped", stats)
        self.assertIn("shape_dropped_total", stats)


MERGE = """\
type s32 = LLT::scalar(32)
type s64 = LLT::scalar(64)
type nxv16s8 = LLT::scalable_vector(16, LLT::scalar(8))

ruleset B_MERGE: G_MERGE_VALUES
    legal in(slot(0), [s32, s64])
    legal in(slot(1), [s32, s64])

ruleset B_UNMERGE: G_UNMERGE_VALUES
    legal in(slot(0), [s32, s64])
    legal in(slot(1), [s32, s64])
"""


class VerifierShapes(unittest.TestCase):
    """The declared type domain is cut by the opcode's MIR shape, not by rules."""

    def rows(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "t.gisel"
            src.write_text(MERGE)
            features = cases.derive_features(cases.document(src))
            return list(domain.enumerate_domain(src, features,
                                                configs=["none"]))

    def test_merge_never_gets_a_vector_slot(self):
        merge = [r for r in self.rows() if r["name"] == "G_MERGE_VALUES"]
        self.assertTrue(merge)
        for row in merge:
            self.assertFalse(any(t.startswith(("v", "nxv"))
                                 for t in row["types"]), row)

    def test_unmerge_drops_mixed_shapes(self):
        unmerge = [r for r in self.rows() if r["name"] == "G_UNMERGE_VALUES"]
        self.assertTrue(unmerge)
        for row in unmerge:
            kinds = {t.startswith(("v", "nxv")) for t in row["types"]}
            self.assertEqual(len(kinds), 1, row)


if __name__ == "__main__":
    unittest.main()
