"""The two host escape points, and the boundary between them.

`feature` is a constructor-time boolean (configuration axis): it may not read
the query.  `opaque` is a predicate hole: it is copied into the rule lambda,
never evaluated, and every exit must report it as a hole rather than `false`.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gisel import ast  # noqa: E402

CORPUS = ROOT / "tests" / "corpus"

BASE = """\
type S32 = LLT::scalar(32)

ruleset T_G_LOAD: G_LOAD
    legal opaque("same(ST)")
    lower opaque("same(ST)")
    unsupported opaque("other(Query)")
"""


def run(*args):
    return subprocess.run([sys.executable, "-m", "gisel", *args],
                          cwd=ROOT, capture_output=True, text=True)


class FeatureIsAConfigurationAxis(unittest.TestCase):
    def test_a_feature_must_not_read_the_query(self):
        text = ("feature F = Query.Types[0].isVector()\n"
                "type S32 = LLT::scalar(32)\n"
                "ruleset T_G_ADD: G_ADD\n"
                "    legal true\n")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(text)
            r = run("lint", str(src))
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("must not read the query", r.stderr)
            # Every exit goes through the same parse gate, not just lint.
            for emit in ("inc", "check", "core"):
                r = run("gen", str(src), f"--emit={emit}",
                        "--out", str(Path(d) / f"x.{emit}"))
                self.assertEqual(r.returncode, 2, f"{emit}: {r.stderr}")
                self.assertIn("must not read the query", r.stderr)

    def test_constructor_scope_and_declared_names_are_allowed(self):
        text = ("feature HasAVX = Subtarget.hasAVX()\n"
                "feature Wide = HasAVX && XLen == 64\n"
                "type S32 = LLT::scalar(32)\n"
                "ruleset T_G_ADD: G_ADD\n"
                "    legal (Wide and in(slot(0), S32))\n")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(text)
            r = run("lint", str(src))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            out = Path(d) / "T.inc"
            r = run("gen", str(src), "--emit=inc", "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            inc = out.read_text()
            self.assertIn("bool HasAVX = Subtarget.hasAVX();", inc)
            self.assertIn("bool Wide = HasAVX && XLen == 64;", inc)


class OpaqueIsAPredicateHole(unittest.TestCase):
    def test_check_counts_the_same_escapes_as_core(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(BASE)
            core = Path(d) / "T.core.json"
            check = Path(d) / "T.check.json"
            r = run("gen", str(src), "--emit=core", "--out", str(core))
            self.assertEqual(r.returncode, 0, r.stderr)
            r = run("gen", str(src), "--emit=check", "--out", str(check))
            self.assertEqual(r.returncode, 0, r.stderr)
            doc = json.loads(core.read_text())
            self.assertEqual(doc["escapes"], ["same(ST)", "other(Query)"])
            self.assertEqual(json.loads(check.read_text())["escapes"], 2)

    def test_opaque_cannot_be_a_mutation(self):
        text = ("type S32 = LLT::scalar(32)\n"
                "ruleset T_G_ADD: G_ADD\n"
                "    widen(slot(0), opaque(\"host()\"))\n")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(text)
            r = run("lint", str(src))
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("expected expr", r.stderr)


class InlineSelectType(unittest.TestCase):
    """`select_type(...)` in a type position is the fourth shape a value has.

    It is inline by definition (no record name), so both the escape-point
    audit and the `.inc` renderer have to handle it without a declaration.
    """

    SOURCE = """\
feature F = Subtarget.hasAVX()
type S32 = LLT::scalar(32)
type S16 = LLT::scalar(16)

ruleset T_G_ADD: G_ADD
    legal in(slot(0), select_type(F, S32, S16))
"""

    def test_every_backend_accepts_it(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(self.SOURCE)
            for emit in ("inc", "check", "core"):
                out = Path(d) / ("T." + emit)
                r = run("gen", str(src), f"--emit={emit}", "--out", str(out))
                self.assertEqual(r.returncode, 0, f"{emit}: {r.stderr}")
            inc = (Path(d) / "T.inc").read_text()
            self.assertIn("(F ? S32 : S16)", inc)

    def test_an_opaque_guard_is_inside_the_hole_audit(self):
        text = ("type S32 = LLT::scalar(32)\n"
                "type S16 = LLT::scalar(16)\n"
                "ruleset T_G_ADD: G_ADD\n"
                "    legal in(slot(0), select_type(opaque(\"host()\"), "
                "S32, S16))\n")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(text)
            program = ast.parse_program(text)
            self.assertEqual(ast.host_escapes(program), ["host()"])
            core = Path(d) / "T.core.json"
            check = Path(d) / "T.check.json"
            self.assertEqual(run("gen", str(src), "--emit=core",
                                 "--out", str(core)).returncode, 0)
            self.assertEqual(run("gen", str(src), "--emit=check",
                                 "--out", str(check)).returncode, 0)
            self.assertEqual(json.loads(core.read_text())["escapes"],
                             ["host()"])
            self.assertEqual(json.loads(check.read_text())["escapes"], 1)


class FrozenCorporaUseOnlyFeature(unittest.TestCase):
    def test_every_corpus_has_zero_escapes_and_clean_feature_scope(self):
        paths = sorted(CORPUS.glob("*.gisel"))
        self.assertEqual(len(paths), 9)
        for path in paths:
            with self.subTest(corpus=path.name):
                program = ast.parse_program(path.read_text())
                self.assertEqual(ast.host_escapes(program), [])
                self.assertIsNone(ast.feature_scope_error(program.features))


if __name__ == "__main__":
    unittest.main()
