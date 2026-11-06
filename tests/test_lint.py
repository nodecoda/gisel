"""`gisel lint`: J1/J2b/J3a/J3b over a source file, no LLVM required."""

import json
import os
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

    def test_probe_corpora_have_no_errors(self):
        # Targets that have no .td yet: the .gisel is the only artifact, so a
        # silent change in what the front end accepts shows up here first.
        for name, nrules in (("M68kLegalizerInfo", 13),
                             ("WebAssemblyLegalizerInfo", 109)):
            r = run("lint", str(CORPUS / f"{name}.gisel"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("0 error(s)", r.stdout)
            self.assertIn(f"{nrules} rule(s)", r.stdout)

    def test_imm_axis(self):
        """`imm(i)` is an Int observation; `in` matches the set's sort."""
        ok = ("ruleset X: G_SEXT_INREG\n"
              "    legal (in(slot(0), i32) and (in(imm(0), [8, 16]) or imm(0) == 32))\n")
        r = lint_source(ok)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 error(s)", r.stdout)

        # An immediate set cannot test a type slot, and a type set cannot test
        # an immediate: `in` is homogeneous in the set's element sort.
        for bad, msg in ((("ruleset X: G_ADD\n"
                           "    legal in(slot(0), [8, 16])\n"), "Int set"),
                         (("ruleset X: G_ADD\n"
                           "    legal in(imm(0), [s32])\n"), "Type set")):
            r = lint_source(bad)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn(msg, r.stderr)

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


    def test_golden_diagnostics(self):
        """Line numbers are part of the contract; drift must be explicit."""
        r = run("lint", "tests/corpus/AArch64LegalizerInfo.gisel", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout,
                         (ROOT / "tests" / "golden" /
                          "lint-aarch64.json").read_text())

    def test_lint_needs_no_llvm_tblgen(self):
        with tempfile.TemporaryDirectory() as d:
            shim = Path(d) / "llvm-tblgen"
            shim.write_text("#!/bin/sh\necho nope >&2\nexit 127\n")
            shim.chmod(0o755)
            env = dict(os.environ, PATH=f"{d}{os.pathsep}{os.environ['PATH']}")
            r = subprocess.run([sys.executable, "-m", "gisel.cli", "lint",
                                "tests/corpus/X86LegalizerInfo.gisel"],
                               cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("nope", r.stderr)


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

    def test_bad_llt_expression_is_rejected(self):
        r = lint_source("\ntype X_s32 = LLT::scalar32(32)\n"
                        "ruleset X_ADD: G_ADD\n"
                        "    legal in(slot(0), [X_s32])\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn(":2:", r.stderr)
        self.assertIn("cannot normalize LLT expression", r.stderr)

    def test_nested_llt_is_accepted(self):
        r = lint_source("type X_v = LLT::scalable_vector(4, LLT::integer(32))\n"
                        "ruleset X_ADD: G_ADD\n"
                        "    legal in(slot(0), [X_v])\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_undeclared_feature_is_a_diagnostic(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text("feature F = Subtarget.hasAVX()\n"
                           "ruleset X_ADD: G_ADD\n    legal feature(F)\n")
            r = run("gen", str(src), "--emit=inc", "--out", str(Path(d) / "x.inc"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("undeclared feature expression", r.stderr)

    def test_unknown_node_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            dsl._tc({"kind": "bogus"}, 1, [])


class KindCoverage(unittest.TestCase):
    """Every node kind the corpus uses must have a sort rule."""

    def test_all_57_kinds_are_understood(self):
        samples = {}

        def walk(x):
            if isinstance(x, dict):
                k = x.get("kind")
                if k and k not in samples:
                    samples[k] = x
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)

        for name in ("x86", "aarch64"):
            walk(json.loads((ROOT / "tests" / "artifacts" /
                             f"{name}.core.json").read_text()))
        self.assertEqual(len(samples), 57)
        for kind, node in samples.items():
            with self.subTest(kind=kind):
                dsl._tc(node, 10 ** 9, [])


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
