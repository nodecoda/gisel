"""Memory-ordering axis: atomic rules must be witnessed, not left on NotAtomic."""

import json
import tempfile
import unittest
from pathlib import Path

from gisel import answers, axes, cases, domain, graph

FIXTURE = """\
type S8 = LLT::scalar(8)
type S32 = LLT::scalar(32)
type P0 = LLT::pointer(0, 64)

ruleset G_STORE: G_STORE
    legal (in_mem_desc(slot(0), slot(1), mem_slot(0), [mem_desc(S32, P0, S32, 8)]) and mem_ordering(mem_slot(0)) >= ordering_unordered)
    lower true
"""

ORDERED = {
    "version": 1,
    "mems": {
        "rows": [["S32", "P0", "S32", 8]],
        "orderings": ["Unordered", "Acquire", "SequentiallyConsistent"],
    },
}


def write(directory, name, text):
    path = Path(directory) / name
    path.write_text(text)
    return path


class Ordering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = write(self.tmp.name, "t.gisel", FIXTURE)
        self.doc = cases.document(self.source)
        self.features = cases.derive_features(self.doc)

    def profile(self, data=ORDERED):
        path = write(self.tmp.name, "axes.json", json.dumps(data))
        return axes.load(path).bind(self.source, self.doc, self.features)

    def test_pairs_and_defaults(self):
        profile = self.profile()
        self.assertEqual(profile.ordering_pairs(),
                         [("Unordered", "NotAtomic"),
                          ("Acquire", "NotAtomic"),
                          ("SequentiallyConsistent", "NotAtomic")])
        with tempfile.TemporaryDirectory() as d:
            empty = axes.load(write(d, "a.json", '{"version": 1}'))
        self.assertEqual(empty.ordering_pairs(), [("NotAtomic", "NotAtomic")])

    def test_case_is_unexercised_without_axis(self):
        generation = cases.generate(self.doc, self.features)
        self.assertIn("G_STORE#0: unexercised", generation.stats["unwitnessed"])

    def test_case_witnesses_the_atomic_rule_and_exports_orderings(self):
        generation = cases.generate(self.doc, self.features, axes=self.profile())
        self.assertNotIn("G_STORE#0: unexercised",
                         generation.stats["unwitnessed"])
        mems = [case.mem for case in generation.cases
                if case.ruleset == "G_STORE" and case.rule == 0]
        self.assertTrue(mems)
        self.assertTrue(all(len(mem) == 4 for mem in mems))
        self.assertTrue(any(mem[2] == "Unordered" for mem in mems))
        queries = [case.query() for case in generation.cases
                   if case.ruleset == "G_STORE" and case.rule == 0]
        self.assertTrue(all(len(q["mem"]) == 4 for q in queries))

    def test_default_queries_still_export_two_element_mem(self):
        generation = cases.generate(self.doc, self.features)
        for case in generation.cases:
            if case.mem:
                self.assertEqual(len(case.query()["mem"]), 2)

    def test_domain_crosses_ordering_values(self):
        rows = list(domain.enumerate_domain(
            self.source, self.features, configs=["none"],
            axes=self.profile()))
        store = [row for row in rows if row["name"] == "G_STORE"]
        ordered = {tuple(row["mem"][2:]) for row in store
                   if row["mem"] and len(row["mem"]) == 4}
        self.assertEqual(ordered,
                         {("Unordered", "NotAtomic"),
                          ("Acquire", "NotAtomic"),
                          ("SequentiallyConsistent", "NotAtomic")})

    def test_graph_marks_the_opcode_uncovered_without_axis(self):
        report = graph.build(self.source, "none", self.features)
        self.assertIn("G_STORE", report.uncovered)
        self.assertEqual(report.states, {})

    def test_graph_builds_ordering_classes_with_axis(self):
        profile = self.profile()
        report = graph.build(self.source, "none", self.features,
                             axis_profile=profile)
        self.assertNotIn("G_STORE", report.uncovered)
        self.assertTrue(report.states)
        mems = {state["mem"] for state in report.states.values()}
        self.assertIn(("s32", 8, "Unordered", "NotAtomic"), mems)

    def test_eval_reads_four_element_mem(self):
        from gisel import eval as E
        evaluator = E.Evaluator(self.doc, self.features)
        path = write(self.tmp.name, "cases.jsonl", json.dumps({
            "config": "none", "name": "G_STORE",
            "types": ["s32", "p0:64"],
            "mem": ["s32", 8, "Unordered", "NotAtomic"],
            "imms": [], "action": "Legal", "type_idx": 0,
            "new_type": "LLT_invalid"}) + "\n")
        total, disagree, errors, first, _counts = E.run_cases(
            evaluator, str(path))
        self.assertEqual((total, disagree, errors), (1, 0, 0), first)

    def test_diff_key_keeps_orderings_distinct(self):
        base = {"config": "none", "name": "G_STORE", "types": ["s32", "p0:64"],
                "imms": []}
        left = dict(base, mem=["s32", 8, "Unordered", "NotAtomic"], action="Legal")
        right = dict(base, mem=["s32", 8, "Acquire", "NotAtomic"], action="Lower")
        self.assertNotEqual(answers.key(left), answers.key(right))
        legacy = dict(base, mem=["s32", 8], action="Legal")
        same = dict(base, mem=["s32", 8, "NotAtomic", "NotAtomic"],
                    action="Legal")
        self.assertEqual(answers.key(legacy), answers.key(same))


if __name__ == "__main__":
    unittest.main()
