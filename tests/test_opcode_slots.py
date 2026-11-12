"""The bundled opcode snapshot is the only arity source."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "gisel" / "data"


def load(name):
    return json.loads((DATA / name).read_text())


class OneTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slots = load("opcode-slots.json")["opcodes"]

    def test_there_is_no_derived_arity_file(self):
        self.assertFalse((DATA / "generic_opcodes.json").exists())

    def test_every_entry_names_arity_and_pointer_slots(self):
        for name, info in self.slots.items():
            with self.subTest(opcode=name):
                self.assertIn("arity", info)
                self.assertIn("ptype", info)

    def test_lint_projects_the_same_arity(self):
        from gisel import dsl
        manifest = dsl.load_arity_manifest()
        self.assertEqual(set(manifest), set(self.slots))
        self.assertEqual(manifest,
                         {name: info["arity"]
                          for name, info in self.slots.items()})

    def test_the_five_lint_gaps_are_closed(self):
        for name in ("G_PHI", "G_BUILD_VECTOR", "G_MERGE_VALUES",
                     "G_UNMERGE_VALUES", "G_CONCAT_VECTORS"):
            self.assertIsNotNone(self.slots[name]["arity"], name)

    def test_variadic_is_unknown_not_zero(self):
        self.assertIsNone(self.slots["G_INTRINSIC"]["arity"])

    def test_no_typed_operand_is_zero(self):
        for name in ("G_BR", "G_FENCE", "G_TRAP"):
            self.assertEqual(self.slots[name]["arity"], 0, name)

    def test_class_body_slots_are_followed(self):
        for name in ("G_ATOMICRMW_OR", "G_ATOMICRMW_FADD"):
            self.assertEqual(self.slots[name]["arity"], 2, name)
            self.assertEqual(self.slots[name]["ptype"], [1], name)


if __name__ == "__main__":
    unittest.main()
