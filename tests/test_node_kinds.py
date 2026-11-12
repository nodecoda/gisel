"""An unknown node kind is a named failure, never a silent `False`/`0`.

The two interpreters work on different inputs (core JSON vs the language
AST), so they cannot share one dispatch table.  They can share the rule that
matters: a kind nobody implemented stops the consumer that met it, and says
which one it was.
"""

import unittest

from gisel import ast as A
from gisel import eval as E
from gisel.backend import llvm_inc as I


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
