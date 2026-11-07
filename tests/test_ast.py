"""The front end produces the language AST, not a record-shaped model.

The digests below were taken from the old record front end before it was
deleted.  They pin both the declaration payloads and the per-rule line
numbers, so a change in the AST (or in the downgrade) that would have moved
an artifact fails here first.
"""

import hashlib
import json
import unittest
from pathlib import Path

from gisel import ast as A

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "corpus"
CORPORA = ("AArch64LegalizerInfo", "M68kLegalizerInfo",
           "RISCVLegalizerInfo", "WebAssemblyLegalizerInfo",
           "X86LegalizerInfo")

# sha256 of json.dumps(record_model, sort_keys, compact)
MODEL = {
    "AArch64LegalizerInfo":
        "90ad84ac13a00f11bcd915c386ca63c6dbc23d95bf981d65e165f543373a17ed",
    "M68kLegalizerInfo":
        "af8f045cfd3dffc3ca37c2e5cea902f381f8354ad990b06554874a34fd036181",
    "RISCVLegalizerInfo":
        "1ddd711ea29342e3d3dff4c511ed93817a92831ea3069085102747f9bf795cb2",
    "WebAssemblyLegalizerInfo":
        "072f417a20b01989a5aac0c675fd3047c8887cd2ed9eca91d965e85c0c00c357",
    "X86LegalizerInfo":
        "b9458060c631e7b8f17243477ad3857f7cab89872d9578418996321d2363196a",
}

# the same, after one-table-per-opcode canonicalisation
CANON = {
    "AArch64LegalizerInfo":
        "720bc1f515688bf546efe833c1224d24189c4b0cde4a23b56a211906792527c9",
    "M68kLegalizerInfo":
        "16ee470ebb29859e1ebfc6989e73cb815917c62cd6ae90e15965e879321d86d0",
    "RISCVLegalizerInfo":
        "84ea07269919f5b53ea51e978c092ea1a5edc8be8c1b639469860a0f3dcaee93",
    "WebAssemblyLegalizerInfo":
        "b77da4d07db31e7693f230c9a5c6d127af755fb55ad9e408b8e51da1b89b3fa9",
    "X86LegalizerInfo":
        "292ecfd77e960e320437168c8ef2f6c6ae142f08c10f55f0bd7cbee3f32f87fd",
}


def text_of(name):
    return (CORPUS / (name + ".gisel")).read_text()


def digest(obj):
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


class DowngradeAdapter(unittest.TestCase):
    def test_program_downgrades_to_the_frozen_record_model(self):
        for name in CORPORA:
            model = A.to_record_model(A.parse_program(text_of(name)))
            self.assertEqual(digest(model), MODEL[name], name)

    def test_ast_canonicalisation_matches_the_frozen_transform(self):
        for name in CORPORA:
            prog = A.parse_program(text_of(name))
            canon = A.Program(prog.includes, prog.decls,
                              A.canonicalize_rulesets(prog.rulesets),
                              prog.features, prog.preds, prog.named_types,
                              prog.selects, prog.setlike)
            self.assertEqual(
                digest(A.to_record_model(canon)["rulesets"]), CANON[name],
                name)


class StructuredTypes(unittest.TestCase):
    """No record name may survive in a rule's type positions."""

    LLTS = (A.Scalar, A.Integer, A.Float, A.BFloat16, A.Pointer, A.Vector)

    def _walk(self, node, where):
        if isinstance(node, dict):
            if node.get("kind") == "type":
                value = node["value"]
                self.assertIsInstance(
                    value, self.LLTS + (A.SelectValue, A.SetValue),
                    "%s: record-shaped type value %r" % (where, value))
            for v in node.values():
                self._walk(v, where)
        elif isinstance(node, (list, tuple)):
            for v in node:
                self._walk(v, where)

    def test_rule_types_are_structured(self):
        for name in CORPORA:
            prog = A.parse_program(text_of(name))
            for rs in prog.rulesets:
                for rule in rs.rules:
                    for field in (rule.on, rule.to, rule.predicate):
                        self._walk(field, "%s:%d" % (name, rule.line))

    def test_named_types_are_llt_values(self):
        for name in CORPORA:
            prog = A.parse_program(text_of(name))
            for d in prog.decls:
                if isinstance(d, A.NamedType):
                    self.assertIsInstance(d.llt, self.LLTS, d.name)
                    self.assertTrue(A.llt_text(d.llt))


class RendererNames(unittest.TestCase):
    """Record names are computed at the .td/.inc exit, not stored."""

    def test_nametable_round_trips_every_unambiguous_named_type(self):
        for name in CORPORA:
            prog = A.parse_program(text_of(name))
            names = A.NameTable(prog)
            for d in prog.decls:
                if not isinstance(d, A.NamedType):
                    continue
                same = [x for x in prog.decls
                        if isinstance(x, A.NamedType) and x.llt == d.llt]
                if len(same) == 1:
                    self.assertEqual(names.value_name(d.llt), d.name)


if __name__ == "__main__":
    unittest.main()
