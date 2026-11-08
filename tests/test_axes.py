"""Axis profiles: schema validation and the no-axes compatibility shell."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gisel import axes, cases, domain, graph

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = """\
type s8 = LLT::scalar(8)
type s16 = LLT::scalar(16)
type s32 = LLT::scalar(32)
type s64 = LLT::scalar(64)

ruleset G_ADD: G_ADD
    legal in(slot(0), s32)
    widen(slot(0), ty(s32))
"""


def write(directory, name, text):
    path = Path(directory) / name
    path.write_text(text)
    return path


def load(directory, data, name="axes.json"):
    path = write(directory, name, json.dumps(data))
    return axes.Axes.load(path)


def base(**sections):
    data = {"version": 1}
    data.update(sections)
    return data


class Validation(unittest.TestCase):
    def test_minimal_profile_loads(self):
        with tempfile.TemporaryDirectory() as d:
            profile = load(d, base())
        self.assertEqual(profile.profile("cases"), {})
        self.assertEqual(profile.pointer_width("none"), 64)

    def test_missing_file_is_an_axis_error(self):
        with self.assertRaises(axes.AxisError):
            axes.Axes.load("/nonexistent/axes.json")

    def test_bad_json_is_an_axis_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = write(d, "axes.json", "{")
            with self.assertRaises(axes.AxisError):
                axes.Axes.load(path)

    def test_version_and_unknown_keys(self):
        bad = [
            {"version": 2},
            {"version": 1, "extra": 1},
            {"version": 1, "types": {"mode": "append"}},
            {"version": 1, "types": {"mode": "explicit"}},
            {"version": 1, "mems": {"rows": [["s8", "s8"]]}},
            {"version": 1, "mems": {"orderings": ["Relaxed"]}},
            {"version": 1, "imms": {"zero": [1]}},
            {"version": 1, "bind": {"pointer_width": {"none": "64"}}},
            {"version": 1, "bind": {"extended": {"none": 1}}},
            {"version": 1, "profiles": {"nope": {}}},
            {"version": 1, "profiles": {"graph": {"unknown": 1}}},
            {"version": 1, "profiles": {"graph": {"state": ["registers"]}}},
        ]
        for data in bad:
            with tempfile.TemporaryDirectory() as d:
                with self.subTest(data=data), self.assertRaises(axes.AxisError):
                    load(d, data)

    def test_source_binding_rejects_unknown_type_imm_and_config(self):
        with tempfile.TemporaryDirectory() as d:
            source = write(d, "t.gisel", FIXTURE)
            doc = cases.document(source)
            features = cases.derive_features(doc)
            bad = [
                base(types={"add": ["banana"]}),
                base(imms={"0": [8]}),
                base(bind={"pointer_width": {"zzz": 32}}),
            ]
            for data in bad:
                with self.subTest(data=data), self.assertRaises(axes.AxisError):
                    load(d, data).bind(source, doc, features)

    def test_source_binding_accepts_a_declared_type(self):
        with tempfile.TemporaryDirectory() as d:
            source = write(d, "t.gisel", FIXTURE)
            doc = cases.document(source)
            features = cases.derive_features(doc)
            profile = load(d, base(types={"add": ["s64"]}))
            profile.bind(source, doc, features)
            self.assertIn(cases.llt_text(profile.resolve_type("s64")), "s64")


class Application(unittest.TestCase):
    def test_derive_add_and_remove_edit_the_derived_set(self):
        with tempfile.TemporaryDirectory() as d:
            profile = load(d, base(
                types={"add": ["s16"], "remove": ["s8"]}))
            values = [cases.llt_text(t) for t in profile.apply_types(
                [cases.E.parse_case_llt(x) for x in ("s8", "s32")])]
            self.assertEqual(values, ["s32", "s16"])

    def test_explicit_replaces_but_keeps_pointer_filter(self):
        with tempfile.TemporaryDirectory() as d:
            profile = load(d, base(types={"mode": "explicit",
                                          "values": ["s8", "s16", "p0:64"]}))
            values = [cases.llt_text(t) for t in profile.apply_types([])]
            self.assertEqual(values, ["s8", "s16", "p0:64"])
            pointers = [cases.llt_text(t) for t in
                        profile.apply_types([], pointer_only=True)]
            self.assertEqual(pointers, ["p0:64"])

    def test_mems_derive_add_remove_and_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            profile = load(d, base(mems={
                "rows": [["s8", "s8", "s8", 8]],
                "remove": [["s8", "s8", "s8", 8]],
            }))
            self.assertEqual(profile.apply_mems([("s8", "s8", "s8", 8)]), [])
            explicit = load(d, base(mems={
                "mode": "explicit",
                "rows": [["s32", "s32", "s32", 4]],
            }))
            self.assertEqual(explicit.apply_mems([("s8", "s8", "s8", 8)]),
                             [("s32", "s32", "s32", 4)])


class NoAxesCompatibility(unittest.TestCase):
    def cli(self, *argv):
        return subprocess.run([sys.executable, "-m", "gisel", *argv],
                              cwd=ROOT, text=True, capture_output=True)

    def test_empty_profile_is_byte_identical_to_no_profile(self):
        with tempfile.TemporaryDirectory() as d:
            source = write(d, "t.gisel", FIXTURE)
            profile = write(d, "axes.json", json.dumps(base()))
            plain = Path(d) / "plain.jsonl"
            wired = Path(d) / "wired.jsonl"
            first = self.cli("cases", str(source), "--out", str(plain),
                             "--json")
            second = self.cli("cases", str(source), "--out", str(wired),
                              "--axes", str(profile), "--json")
            self.assertEqual(first.returncode, second.returncode,
                             first.stderr + second.stderr)
            self.assertEqual(plain.read_bytes(), wired.read_bytes())

    def test_generation_commands_do_not_accept_axes(self):
        with tempfile.TemporaryDirectory() as d:
            source = write(d, "t.gisel", FIXTURE)
            result = self.cli("gen", str(source), "--out",
                              str(Path(d) / "x.inc"), "--axes", "axes.json")
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
