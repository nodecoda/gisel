"""One value set, three samplers: cases/domain/graph agree under --axes."""

import json
import tempfile
import unittest
from pathlib import Path

from gisel import axes, cases, domain, graph

FIXTURE = """\
type s8 = LLT::scalar(8)
type s32 = LLT::scalar(32)
type s64 = LLT::scalar(64)
type P0 = LLT::pointer(0, 64)

ruleset G_LOAD: G_LOAD
    legal in_mem_desc(slot(0), slot(1), mem_slot(0), [mem_desc(s8, P0, s8, 8)])
    lower true

ruleset G_ADD: G_ADD
    legal in(slot(0), s32)
    widen(slot(0), pow2_min(32))
"""

EXPLICIT = {
    "version": 1,
    "types": {"mode": "explicit", "values": ["s8", "s32", "s64", "p0:64"]},
    "mems": {"mode": "explicit", "rows": [["s8", "p0:64", "s8", 8]]},
}

DERIVED_ADD = {
    "version": 1,
    "types": {"add": ["s16"]},
}


def type_text(value):
    return cases.llt_text(value) if isinstance(value, tuple) else value


class Wiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "t.gisel"
        self.source.write_text(FIXTURE)
        self.doc = cases.document(self.source)
        self.features = cases.derive_features(self.doc)

    def profile(self, data):
        path = Path(self.tmp.name) / "axes.json"
        path.write_text(json.dumps(data))
        return axes.load(path).bind(self.source, self.doc, self.features)

    def test_explicit_types_and_mems_reach_all_three_commands(self):
        profile = self.profile(EXPLICIT)
        # The profile lists one global set; pointer values are the only
        # candidates for pointer slots, and every non-pointer slot sees the
        # whole set (the pre-existing graph behaviour).
        want = {"s8", "s32", "s64", "p0:64"}

        generation = cases.generate(self.doc, self.features, axes=profile)
        seen = {case.types[0] for case in generation.cases
                if case.kind == "equivalence"}
        # cases is a sampler: every emitted value must come from the profile,
        # but it need not visit every value.
        self.assertLessEqual(seen, want)
        mems = {case.mem for case in generation.cases
                if case.kind == "equivalence" and case.mem}
        self.assertEqual(mems, {("s8", 8)})

        rows = list(domain.enumerate_domain(
            self.source, self.features, configs=["none"], axes=profile))
        self.assertEqual({t for row in rows for t in row["types"]}, want)
        self.assertEqual({tuple(row["mem"]) for row in rows if row["mem"]},
                         {("s8", 8)})

        report = graph.build(self.source, "none", self.features,
                             axis_profile=profile)
        type_classes, mem_classes = report.class_tables["G_LOAD"]
        self.assertEqual({type_text(v) for v in type_classes[0].values}, want)
        self.assertNotIn("s3", {type_text(v) for v in type_classes[0].values})
        self.assertEqual({v[0] for v in mem_classes.values}, {"s8"})

    def test_derive_add_is_visible_to_domain_and_graph(self):
        profile = self.profile(DERIVED_ADD)

        base = set(domain.domain_axes(self.source)[0])
        rows = list(domain.enumerate_domain(
            self.source, self.features, configs=["none"], axes=profile))
        self.assertEqual({t for row in rows for t in row["types"]},
                         base | {"s16"})

        report = graph.build(self.source, "none", self.features,
                             axis_profile=profile)
        type_classes = report.class_tables["G_ADD"][0]
        graph_types = {type_text(v) for v in type_classes[0].values}
        self.assertIn("s16", graph_types)
        # cases derives its candidates from the same set; a sample may be
        # smaller, but it must not invent values the graph cannot address.
        generation = cases.generate(self.doc, self.features, axes=profile)
        sampled = {case.types[0] for case in generation.cases
                   if case.kind == "equivalence"}
        self.assertLessEqual(sampled, graph_types)

    def test_per_config_pointer_width_reaches_domain_and_graph(self):
        data = dict(EXPLICIT)
        data["types"] = {"mode": "explicit",
                         "values": ["s8", "s32", "s64", "p0:32"]}
        data["mems"] = {"mode": "explicit",
                        "rows": [["s8", "p0:32", "s8", 8]]}
        data["bind"] = {"pointer_width": {"none": 32}}
        profile = self.profile(data)

        rows = [row for row in domain.enumerate_domain(
            self.source, self.features, configs=["none"], axes=profile)
            if row["name"] == "G_LOAD"]
        self.assertTrue(rows)
        self.assertTrue(all(row["types"][1] == "p0:32" for row in rows))

        report = graph.build(self.source, "none", self.features,
                             axis_profile=profile,
                             pointer_width=32)
        type_classes = report.class_tables["G_LOAD"][0]
        self.assertEqual({type_text(v) for v in type_classes[1].values},
                         {"p0:32"})


if __name__ == "__main__":
    unittest.main()
