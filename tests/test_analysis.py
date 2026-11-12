"""Rule analysis must read every field of a rule, not just the predicate.

A feature or a slot can sit inside an `on`/`to` mutation, or inside an inline
`select_type` guard.  When the walker only followed predicate arguments, the
axis or the slot vanished from the analysis and the rule became unexercised
with no diagnostic.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gisel import analysis  # noqa: E402


def document(text):
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "T.gisel"
        src.write_text(text)
        return analysis.document(src)


class FeaturesInEveryField(unittest.TestCase):
    def test_a_feature_in_a_mutation_is_a_configuration_axis(self):
        doc = document(
            "feature F = Subtarget.hasAVX()\n"
            "type S32 = LLT::scalar(32)\n"
            "type S16 = LLT::scalar(16)\n"
            "ruleset T_G_ADD: G_ADD\n"
            "    widen(slot(0), select_type(F, S32, S16))\n")
        table = analysis.derive_features(doc)
        self.assertIn("only-0", table.table)
        self.assertTrue(table.table["all"]["Subtarget.hasAVX()"])
        self.assertFalse(table.table["none"]["Subtarget.hasAVX()"])

    def test_a_feature_in_an_on_position_is_a_configuration_axis(self):
        doc = document(
            "feature F = Subtarget.hasAVX()\n"
            "type S32 = LLT::scalar(32)\n"
            "type S16 = LLT::scalar(16)\n"
            "ruleset T_G_ADD: G_ADD\n"
            "    widen(slot(0), ty(select_type(F, S32, S16)))\n")
        table = analysis.derive_features(doc)
        self.assertIn("only-0", table.table)


class SessionBootstrap(unittest.TestCase):
    SOURCE = (
        "feature F = Subtarget.hasAVX()\n"
        "type S32 = LLT::scalar(32)\n"
        "type S16 = LLT::scalar(16)\n"
        "ruleset T_G_ADD: G_ADD\n"
        "    legal in(slot(0), select_type(F, S32, S16))\n")

    def test_one_call_returns_the_document_and_the_derived_table(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(self.SOURCE)
            doc, features, axes = analysis.session(src)
        self.assertEqual(doc["version"], "0.4")
        self.assertEqual(sorted(features.table), ["all", "none", "only-0"])
        self.assertIsNone(axes)
        self.assertTrue(features.table["all"]["LLT::getUseExtended()"])

    def test_config_filter_is_applied_to_the_derived_table(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(self.SOURCE)
            _doc, features, _axes = analysis.session(src, configs=["none"])
        self.assertEqual(sorted(features.table), ["none"])


class SlotsInEveryField(unittest.TestCase):
    def test_a_slot_in_a_select_guard_counts_toward_the_arity(self):
        doc = document(
            "type S32 = LLT::scalar(32)\n"
            "type S16 = LLT::scalar(16)\n"
            "ruleset T_G_ADD: G_ADD\n"
            "    legal in(slot(0), "
            "select_type(slot(1) == 64, S32, S16))\n")
        nslots, infos = analysis.inspect_ruleset(doc["rulesets"][0])
        self.assertEqual(nslots, 2)
        self.assertEqual(sorted(infos[0].slots), [0, 1])


if __name__ == "__main__":
    unittest.main()
