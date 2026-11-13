"""`p0:*` means "the configuration's pointer", not "any width".

The `.inc` emits `LLT::pointer(0, XLen)`, resolved by the target triple at
compile time; a core document can only say `p0:*`.  If the interpreter treats
that as "matches any width", it accepts a `p0:64` query under a 32-bit
configuration, which the compiled legalizer answers `Unsupported`.  The
feature table carries the width (`_pointer_width`, or `_xlen` as the RISC-V
tables spell it); these tests pin that it is used and that its absence keeps
the old wildcard behaviour.
"""

import unittest

from gisel import eval as E


def doc(rule_type):
    return {"rulesets": [{
        "def": "R",
        "opcodes": ["G_PREFETCH"],
        "rules": [{
            "action": "Legal", "type_idx": 0, "op": "legal",
            "predicate": {"kind": "eq", "args": [
                {"kind": "slot", "index": 0},
                {"kind": "type", "value": rule_type}]},
        }],
    }]}


FEATURES = {"rv32": {"_xlen": 32, "generic": True},
            "rv64": {"_pointer_width": 64},
            "plain": {"generic": True}}


class TheWidthComesFromTheConfig(unittest.TestCase):
    def setUp(self):
        self.ev = E.Evaluator(doc("p0:*"), E.Features(FEATURES))

    def answer(self, config, width):
        return E.evaluate(self.ev, config, "G_PREFETCH",
                          [("pointer", 0, width)], ())

    def test_a_64_bit_pointer_is_not_legal_on_a_32_bit_config(self):
        action, _, _ = self.answer("rv32", 64)
        self.assertEqual(action, "Unsupported")

    def test_the_configured_width_is_legal(self):
        action, _, _ = self.answer("rv32", 32)
        self.assertEqual(action, "Legal")

    def test_the_generic_key_works_too(self):
        self.assertEqual(self.answer("rv64", 64)[0], "Legal")
        self.assertEqual(self.answer("rv64", 32)[0], "Unsupported")

    def test_no_declared_width_keeps_the_old_wildcard(self):
        self.assertEqual(self.answer("plain", 64)[0], "Legal")
        self.assertEqual(self.answer("plain", 32)[0], "Legal")


class ReadingTheTable(unittest.TestCase):
    def test_bools_are_not_widths(self):
        self.assertIsNone(
            E.config_pointer_width({"c": {"_xlen": True}}, "c"))

    def test_pointer_width_wins_over_xlen(self):
        table = {"c": {"_pointer_width": 64, "_xlen": 32}}
        self.assertEqual(E.config_pointer_width(table, "c"), 64)

    def test_an_unknown_config_has_no_width(self):
        self.assertIsNone(E.config_pointer_width({}, "nope"))

    def test_the_substitution_reaches_vector_elements(self):
        t = ("vector", 4, False, ("pointer", 0, "*"))
        self.assertEqual(E.resolve_pointer_width(t, 32),
                         ("vector", 4, False, ("pointer", 0, 32)))


if __name__ == "__main__":
    unittest.main()
