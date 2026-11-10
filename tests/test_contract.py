"""The shape contract is data: parse it, validate it, pin its decisions."""

import json
import tempfile
import unittest
from pathlib import Path

from gisel import contract
from gisel import eval as E

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "gisel" / "data" / "contract-shapes.jsonc"


def t(spell):
    return E.parse_case_llt(spell)


class Table(unittest.TestCase):
    def test_every_rule_has_a_source(self):
        document = contract.validate(
            json.loads(contract._strip_jsonc(DATA.read_text())))
        for rule in document["rules"]:
            self.assertTrue(rule["source"], rule["opcode"])

    def test_duplicate_opcode_is_rejected(self):
        doc = {"schema": "gisel-contract/1", "rules": [
            {"opcode": "G_A", "checks": [], "source": "x"},
            {"opcode": "G_A", "checks": [], "source": "y"},
        ]}
        with self.assertRaises(ValueError):
            contract.validate(doc)

    def test_rule_without_source_is_rejected(self):
        doc = {"schema": "gisel-contract/1", "rules": [
            {"opcode": "G_A", "checks": []}]}
        with self.assertRaises(ValueError):
            contract.validate(doc)

    def test_unknown_kind_is_rejected(self):
        doc = {"schema": "gisel-contract/1", "rules": [
            {"opcode": "G_A", "source": "x",
             "checks": [{"slot": 0, "kind": "banana"}]}]}
        with self.assertRaises(ValueError):
            contract.validate(doc)

    def test_comments_are_stripped_but_not_inside_strings(self):
        text = '{"a": "x//y", // tail\n "b": 1 /* mid */ }'
        self.assertEqual(json.loads(contract._strip_jsonc(text)),
                         {"a": "x//y", "b": 1})


class Shapes(unittest.TestCase):
    def ok(self, opcode, *types):
        return contract.check(opcode, [t(x) for x in types])

    def test_unknown_opcode_is_in_contract(self):
        self.assertTrue(self.ok("G_ADD", "s32", "s32"))

    def test_merge_values(self):
        self.assertTrue(self.ok("G_MERGE_VALUES", "s64", "s32", "s32"))
        self.assertFalse(self.ok("G_MERGE_VALUES", "s64", "v2s32"))

    def test_unmerge_values(self):
        self.assertTrue(self.ok("G_UNMERGE_VALUES", "s32", "s64"))
        self.assertTrue(self.ok("G_UNMERGE_VALUES", "v2s32", "v2s32"))
        self.assertFalse(self.ok("G_UNMERGE_VALUES", "s32", "v2s32", "v4s32"))
        # Pinned known narrowness: the scalar-destination vector form is
        # dropped today (spec/contract.md, REPORT-coverage §9.5).
        self.assertFalse(self.ok("G_UNMERGE_VALUES", "v2s32", "s32", "s32"))

    def test_concat_vectors(self):
        self.assertTrue(self.ok("G_CONCAT_VECTORS", "v4s16", "v2s16"))
        self.assertFalse(self.ok("G_CONCAT_VECTORS", "v4s16", "v2s32"))
        self.assertFalse(self.ok("G_CONCAT_VECTORS", "v6s16", "v2s16"))
        self.assertFalse(self.ok("G_CONCAT_VECTORS", "s32", "v2s16"))

    def test_comparisons(self):
        self.assertTrue(self.ok("G_ICMP", "v4s1", "v4s32"))
        self.assertFalse(self.ok("G_ICMP", "s8", "v4s32"))
        self.assertFalse(self.ok("G_FCMP", "v4s1", "v2f32"))

    def test_shuffle_vector(self):
        self.assertTrue(self.ok("G_SHUFFLE_VECTOR", "v4s32", "v4s32"))
        self.assertFalse(self.ok("G_SHUFFLE_VECTOR", "v4s32", "v4p0:64"))
        self.assertFalse(self.ok("G_SHUFFLE_VECTOR", "s32", "v4s32"))

    def test_shifts_and_rotates(self):
        for opcode in ("G_SHL", "G_LSHR", "G_ASHR", "G_ROTR", "G_ROTL"):
            self.assertTrue(self.ok(opcode, "v4s32", "v4s32"))
            self.assertTrue(self.ok(opcode, "s32", "s32"))
            self.assertFalse(self.ok(opcode, "v4s32", "s32"))

    def test_saturating_conversion(self):
        self.assertTrue(self.ok("G_FPTOSI_SAT", "v4s32", "v4f32"))
        self.assertFalse(self.ok("G_FPTOSI_SAT", "v4s32", "s32"))

    def test_short_tuple_rule_keeps_the_old_answer(self):
        # A one-slot shift never reaches the verifier check.
        self.assertTrue(contract.check("G_SHL", [t("s32")]))


SPELLINGS = ["s8", "s16", "s32", "s64", "i8", "i32", "f16", "f32", "f64",
             "bf16", "p0:64", "v2s8", "v4s32", "v2f32", "v2p0:64",
             "nxv4s32", "nxv2f32"]


def legacy(opcode, types):
    """The hand-written filter that `contract-shapes.jsonc` replaced.

    Kept as the oracle for the table: the refactor must not change a single
    decision, including the known-narrow `G_UNMERGE_VALUES` one.
    """
    isv = E.is_vector
    same_elt = lambda a, b: E.llt_eq(a[3], b[3])
    same_lanes = lambda a, b: isv(a) == isv(b) and (not isv(a) or a[1] == b[1])
    intres = lambda t: ((not isv(t) and t[0] == "scalar")
                        or (isv(t) and t[3][0] == "scalar"))
    if opcode in ("G_ICMP", "G_FCMP"):
        return (len(types) >= 2 and intres(types[0])
                and same_lanes(types[0], types[1]))
    if opcode == "G_MERGE_VALUES":
        return all(not isv(t) for t in types)
    if opcode == "G_UNMERGE_VALUES":
        if all(not isv(t) for t in types):
            return True
        if all(isv(t) for t in types):
            first = types[0]
            return all(t[2] == first[2] and same_elt(t, first)
                       for t in types[1:])
        return False
    if opcode == "G_CONCAT_VECTORS":
        return (len(types) >= 2 and isv(types[0]) and isv(types[1])
                and types[0][1] == types[1][1] * 2 and same_elt(types[0], types[1]))
    if opcode == "G_SHUFFLE_VECTOR":
        return (len(types) >= 2 and isv(types[0]) and isv(types[1])
                and same_elt(types[0], types[1]))
    if opcode in ("G_SHL", "G_LSHR", "G_ASHR", "G_ROTR", "G_ROTL"):
        if len(types) < 2:
            return True
        return (all(isv(t) for t in types[:2])
                or all(not isv(t) for t in types[:2]))
    if opcode in ("G_FPTOSI_SAT", "G_FPTOUI_SAT"):
        return len(types) >= 2 and same_lanes(types[0], types[1])
    return True


class Equivalence(unittest.TestCase):
    """The table must reproduce the hand-written filter decision for decision."""

    def test_cartesian_product_matches_legacy(self):
        import itertools
        types = [t(x) for x in SPELLINGS]
        opcodes = ["G_ICMP", "G_FCMP", "G_MERGE_VALUES", "G_UNMERGE_VALUES",
                   "G_CONCAT_VECTORS", "G_SHUFFLE_VECTOR", "G_SHL", "G_LSHR",
                   "G_ASHR", "G_ROTR", "G_ROTL", "G_FPTOSI_SAT",
                   "G_FPTOUI_SAT", "G_ADD"]
        for opcode in opcodes:
            for n in (1, 2, 3):
                for combo in itertools.product(types, repeat=n):
                    self.assertEqual(
                        contract.check(opcode, list(combo)),
                        legacy(opcode, list(combo)),
                        (opcode, combo))


if __name__ == "__main__":
    unittest.main()
