"""`opaque("...")`: the documented host-predicate escape point.

The corpus copies an expression it cannot evaluate into the generated C++,
where it is evaluated exactly once per query.  Everything else in gisel must
treat it as a hole: `eval` refuses to answer, `--emit=core` lists it under
`escapes`, and `cases` derives no axis from it.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCE = """\
type S32 = LLT::scalar(32)

ruleset T_G_LOAD: G_LOAD
    legal opaque("isLoadStoreLegal(ST, Query)")
    lower true
"""


def run(*args):
    return subprocess.run([sys.executable, "-m", "gisel", *args],
                          cwd=ROOT, capture_output=True, text=True)


class OpaquePredicate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.src = self.dir / "T.gisel"
        self.src.write_text(SOURCE)

    def test_lint_accepts_it(self):
        r = run("lint", str(self.src))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 error(s)", r.stdout)

    def test_inc_emits_the_expression_inside_the_rule_lambda(self):
        out = self.dir / "T.inc"
        r = run("gen", str(self.src), "--emit=inc", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = out.read_text()
        self.assertIn(
            '.legalIf([=](const LegalityQuery &Query) '
            '{ return (isLoadStoreLegal(ST, Query)); })', text)

    def test_core_lists_the_escape(self):
        out = self.dir / "T.json"
        r = run("gen", str(self.src), "--emit=core", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        doc = json.loads(out.read_text())
        self.assertEqual(doc["escapes"], ["isLoadStoreLegal(ST, Query)"])

    def test_eval_does_not_pretend_to_know(self):
        from gisel import ast, eval as E
        from gisel.backend.core_json import emit_core
        program = ast.parse_program(SOURCE)
        doc = json.loads(emit_core(program, "T.gisel"))
        evaluator = E.Evaluator(doc, E.Features({"none": {}}))
        rule = doc["rulesets"][0]["rules"][0]
        with self.assertRaises(E.EvalError) as ctx:
            evaluator.bool_value(rule["predicate"], ((("scalar", 32),),), (),
                                 config="none")
        self.assertEqual(ctx.exception.code, "opaque")

    def test_a_quoted_expression_round_trips(self):
        src = self.dir / "Q.gisel"
        src.write_text(
            'type S32 = LLT::scalar(32)\n\n'
            'ruleset T_G_ADD: G_ADD\n'
            '    legal opaque("isLegal(\\"G_ADD\\")")\n')
        out = self.dir / "Q.json"
        r = run("gen", str(src), "--emit=core", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        doc = json.loads(out.read_text())
        self.assertEqual(doc["escapes"], ['isLegal("G_ADD")'])


if __name__ == "__main__":
    unittest.main()
