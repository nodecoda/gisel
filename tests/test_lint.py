"""`gisel lint`: J1/J2b/J3a/J3b over a source file, no LLVM required."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gisel import dsl  # noqa: E402

CORPUS = ROOT / "tests" / "corpus"
GENERIC_TD = Path("/home/ubuntu/llvm/trees/explore/llvm/include/llvm/Target/"
                  "GenericOpcodes.td")


def run(*args):
    return subprocess.run([sys.executable, "-m", "gisel.cli", *args],
                          cwd=ROOT, capture_output=True, text=True)


def lint_source(text):
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "T.gisel"
        src.write_text(text)
        return run("lint", str(src))


class LintCorpus(unittest.TestCase):
    def test_both_corpora_have_no_errors(self):
        for name, nrules in (("X86LegalizerInfo", 332),
                             ("AArch64LegalizerInfo", 743)):
            r = run("lint", str(CORPUS / f"{name}.gisel"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("0 error(s)", r.stdout)
            self.assertIn(f"{nrules} rule(s)", r.stdout)

    def test_json_is_machine_readable(self):
        r = run("lint", str(CORPUS / "AArch64LegalizerInfo.gisel"), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(r.stdout)
        self.assertEqual(doc["errors"], [])
        self.assertEqual(doc["rules"], 743)
        # Variadic opcodes are the only ones without a fixed arity.
        self.assertTrue(doc["warnings"])
        self.assertTrue(all("arity unknown" in w["message"]
                            for w in doc["warnings"]))

    def test_variadic_warning_is_per_ruleset_not_per_rule(self):
        r = run("lint", str(CORPUS / "X86LegalizerInfo.gisel"), "--json")
        doc = json.loads(r.stdout)
        self.assertLessEqual(len(doc["warnings"]), 8)


class NegativeControl(unittest.TestCase):
    """A checker that never rejects is vacuous."""

    def test_slot_out_of_range(self):
        r = lint_source("type X86_s32 = LLT::scalar(32)\n"
                        "ruleset X86_ADD: G_ADD\n"
                        "    widen(slot(3), X86_s32)\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn(":3:", r.stderr)
        self.assertIn("Slot 3", r.stderr)
        self.assertIn("out of range", r.stderr)

    def test_guard_must_be_bool(self):
        # The parser only builds predicates, so exercise J1 directly: a bare
        # type observation is not a legal guard.
        errs = []
        dsl.check_rule({"op": "legal", "type_idx": 0,
                        "predicate": {"kind": "slot", "index": 0}}, 1, errs)
        self.assertTrue(any("guard must be Bool" in e for e in errs), errs)

    def test_action_target_sort(self):
        r = lint_source("type X86_s32 = LLT::scalar(32)\n"
                        "ruleset X86_ADD: G_ADD\n"
                        "    narrow(slot(0), vector)\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("target sort Kind not in action table", r.stderr)

    def test_unknown_node_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            dsl._tc({"kind": "bogus"}, 1, [])


class ArityTable(unittest.TestCase):
    """The table the checker trusts; the old regex got G_VECREDUCE_FADD wrong."""

    def test_known_shapes(self):
        m = dsl.load_arity_manifest()
        self.assertEqual(m["G_VECREDUCE_FADD"], 2)   # VectorReduction: type0/1
        self.assertEqual(m["G_MEMCPY"], 3)           # ptype0/ptype1/type2
        self.assertEqual(m["G_ATOMICRMW_ADD"], 2)    # ptype1/type0
        self.assertEqual(m["G_FENCE"], 0)            # no type operands
        self.assertIsNone(m["G_INTRINSIC"])          # variable_ops

    def test_bundled_table_matches_the_source(self):
        if not GENERIC_TD.exists():
            self.skipTest("no LLVM source tree")
        self.assertEqual(dsl.build_arity_manifest(str(GENERIC_TD)),
                         dsl.load_arity_manifest())


if __name__ == "__main__":
    unittest.main()
