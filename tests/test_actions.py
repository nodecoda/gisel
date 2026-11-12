"""The action vocabulary is one table, and every consumer reads it."""

import json
import unittest
from pathlib import Path

from gisel import actions
from gisel import eval as E
from gisel import graph as G
from gisel.backend import llvm_inc as I

ROOT = Path(__file__).resolve().parents[1]


def observed_actions():
    seen = set()
    for path in (ROOT / "tests" / "artifacts").glob("*.core.json"):
        doc = json.loads(path.read_text())

        def walk(value):
            if isinstance(value, dict):
                action = value.get("action")
                if isinstance(action, str):
                    seen.add(action)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(doc)
    return seen


class Vocabulary(unittest.TestCase):
    def test_names_and_ops_are_unique(self):
        self.assertEqual(len(actions.BY_NAME), len(actions.ACTIONS))
        self.assertEqual(len(actions.BY_OP), len(actions.ACTIONS))

    def test_terminals_have_both_spellings(self):
        for action in actions.ACTIONS:
            if not action.terminal:
                continue
            self.assertIsNotNone(action.for_spelling, action.name)
            self.assertIsNotNone(action.covering_shim, action.name)
            self.assertEqual(action.target_sorts, frozenset(), action.name)

    def test_mutations_declare_their_target_sorts(self):
        for action in actions.ACTIONS:
            if action.terminal:
                continue
            self.assertIsNone(action.for_spelling, action.name)
            self.assertTrue(action.target_sorts, action.name)

    def test_consumers_agree_with_the_table(self):
        self.assertEqual(E.NO_MUTATION_ACTIONS, actions.TERMINAL_ACTIONS)
        self.assertEqual(G.TERMINAL, actions.TERMINAL_ACTIONS)
        self.assertEqual(
            I.FOR_ACTION,
            {a.op: a.for_spelling for a in actions.ACTIONS
             if a.for_spelling})
        self.assertEqual(
            I.ALL_COVERING_SHIMS,
            {a.covering_shim for a in actions.ACTIONS if a.covering_shim})

    def test_every_corpus_action_has_a_spec(self):
        seen = observed_actions()
        self.assertEqual(seen, set(actions.BY_NAME),
                         "corpus actions and the table disagree")

    def test_no_spec_is_dead(self):
        for action in actions.ACTIONS:
            self.assertIn(action.name, observed_actions(), action.name)


if __name__ == "__main__":
    unittest.main()
