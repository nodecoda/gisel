"""One parse, two views: the slot table and the arity manifest cannot drift."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "gisel" / "data"


def load(name):
    return json.loads((DATA / name).read_text())


class JoinedAtTheParse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slots = load("opcode-slots.json")["opcodes"]
        cls.arity = load("generic_opcodes.json")["opcodes"]

    def test_same_opcode_set(self):
        self.assertEqual(set(self.slots), set(self.arity))

    def test_same_arity_everywhere(self):
        mismatched = {name: (info["arity"], self.arity.get(name))
                      for name, info in self.slots.items()
                      if self.arity.get(name) != info["arity"]}
        self.assertEqual(mismatched, {})

    def test_the_five_lint_gaps_are_closed(self):
        # lint used to report "arity unknown" for these; the arity view had no
        # entry even though the slot table did.
        for name in ("G_PHI", "G_BUILD_VECTOR", "G_MERGE_VALUES",
                     "G_UNMERGE_VALUES", "G_CONCAT_VECTORS"):
            self.assertIsNotNone(self.arity[name], name)
            self.assertIsNotNone(self.slots[name]["arity"], name)

    def test_variadic_is_unknown_not_zero(self):
        self.assertIsNone(self.slots["G_INTRINSIC"]["arity"])
        self.assertIsNone(self.arity["G_INTRINSIC"])

    def test_no_typed_operand_is_zero(self):
        for name in ("G_BR", "G_FENCE", "G_TRAP"):
            self.assertEqual(self.slots[name]["arity"], 0, name)

    def test_class_body_slots_are_followed(self):
        # `def G_ATOMICRMW_OR : G_ATOMICRMW_OP;` and
        # `def G_ATOMICRMW_FADD : G_ATOMICRMW_FP_OP;` (a one-level subclass)
        # both live in the class body.
        for name in ("G_ATOMICRMW_OR", "G_ATOMICRMW_FADD"):
            self.assertEqual(self.slots[name]["arity"], 2, name)
            self.assertEqual(self.slots[name]["ptype"], [1], name)

    def test_derived_file_says_so(self):
        self.assertEqual(load("generic_opcodes.json")["generated_from"],
                         "opcode-slots.json")


if __name__ == "__main__":
    unittest.main()
