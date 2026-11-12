"""An unknown node kind is a named failure, never a silent `False`/`0`.

The two interpreters work on different inputs (core JSON vs the language
AST), so they cannot share one dispatch table.  They can share the rule that
matters: a kind nobody implemented stops the consumer that met it, and says
which one it was.
"""

import json
import unittest
from pathlib import Path

from gisel import ast as A
from gisel import eval as E
from gisel import nodes
from gisel.backend import llvm_inc as I

ROOT = Path(__file__).resolve().parents[1]


class RegistryCoversEveryCoreKind(unittest.TestCase):
    def test_every_kind_in_the_frozen_core_is_registered(self):
        kinds = set()

        def walk(value):
            if isinstance(value, dict):
                if isinstance(value.get("kind"), str):
                    kinds.add(value["kind"])
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        for path in sorted((ROOT / "tests" / "artifacts").glob("*.core.json")):
            walk(json.loads(path.read_text()))
        missing = sorted(kind for kind in kinds if nodes.spec(kind) is None)
        self.assertEqual(missing, [], "unregistered core kinds: %s" % missing)

    def test_mutation_targets_are_registered_even_when_no_corpus_uses_them(self):
        # `multipleOf` is a mutation target the importer can emit, but no
        # checked-in corpus uses it yet.  The frozen-core walk above cannot
        # see it; this list is the guard against a vocabulary that only
        # covers today's corpora.
        for kind in ("ty", "sameAs", "replace", "set", "sortOf",
                     "pow2Min", "multipleOf"):
            with self.subTest(kind=kind):
                self.assertIsNotNone(nodes.spec(kind), kind)

    def test_the_registry_separates_values_from_booleans(self):
        self.assertTrue(nodes.known({"kind": "eq"}, "bool"))
        self.assertFalse(nodes.known({"kind": "eq"}, "value"))
        self.assertTrue(nodes.known({"kind": "slot"}, "value"))
        self.assertFalse(nodes.known({"kind": "slot"}, "bool"))
        self.assertTrue(nodes.known({"kind": "kindVector"}, "tag"))


class UnknownKindIsLoud(unittest.TestCase):
    def test_evaluator_names_the_value_node(self):
        evaluator = E.Evaluator({"rulesets": []}, None)
        with self.assertRaises(E.EvalError) as ctx:
            evaluator.value({"kind": "bogus"}, (), [], "C0")
        self.assertEqual(ctx.exception.code, "unknown_value")
        self.assertIn("bogus", ctx.exception.detail)

    def test_emitter_names_the_value_node(self):
        emitter = I.IncEmitter(A.Program([], []))
        with self.assertRaises(ValueError) as ctx:
            emitter.value({"kind": "bogus"})
        self.assertIn("no C++ value for node", str(ctx.exception))
        self.assertIn("bogus", str(ctx.exception))

    def test_emitter_names_the_boolean_node(self):
        emitter = I.IncEmitter(A.Program([], []))
        with self.assertRaises(ValueError) as ctx:
            emitter.boolean({"kind": "bogus"})
        self.assertIn("no C++ boolean for node", str(ctx.exception))
        self.assertIn("bogus", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
