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
        for name, nrules in (("X86LegalizerInfo", 328),
                             ("AArch64LegalizerInfo", 741)):
            r = run("lint", str(CORPUS / f"{name}.gisel"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("0 error(s)", r.stdout)
            self.assertIn(f"{nrules} rule(s)", r.stdout)

    def test_probe_corpora_have_no_errors(self):
        # Probe corpora: the .gisel is the only artifact, so a
        # silent change in what the front end accepts shows up here first.
        for name, nrules in (("M68kLegalizerInfo", 13),
                             ("PowerPCLegalizerInfo", 25),
                             ("ARMLegalizerInfo", 96),
                             ("MipsLegalizerInfo", 95),
                             ("SPIRVLegalizerInfo", 353),
                             ("WebAssemblyLegalizerInfo", 109)):
            r = run("lint", str(CORPUS / f"{name}.gisel"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("0 error(s)", r.stdout)
            self.assertIn(f"{nrules} rule(s)", r.stdout)

    def test_imm_axis(self):
        """`imm(i)` is an Int observation; `in` matches the set's sort."""
        # A rule names types that are declared; `i32` alone is not a name.
        ok = ("type X_i32 = LLT::scalar(32)\n"
              "ruleset X: G_SEXT_INREG\n"
              "    legal (in(slot(0), X_i32) and (in(imm(0), [8, 16]) or imm(0) == 32))\n")
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
        self.assertEqual(doc["rules"], 741)
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


class ShimParity(unittest.TestCase):
    """`lint` and the `.inc` emitter must agree on what is spellable.

    They used to disagree: `narrow(slot(0), 32)` passed lint and then failed
    in `gen` with "no C++ shim".  lint now asks the emitter's own table.
    """

    SOURCE = ("type X86_s32 = LLT::scalar(32)\n"
              "ruleset X86_ADD: G_ADD\n"
              "    narrow(slot(0), 32)\n")

    def test_lint_reports_the_same_missing_shim_as_gen(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(self.SOURCE)
            lint = run("lint", str(src))
            gen = run("gen", str(src), "--emit=inc",
                      "--out", str(Path(d) / "T.inc"))
        self.assertEqual(lint.returncode, 1, lint.stderr)
        self.assertEqual(gen.returncode, 2, gen.stderr)
        message = ("no C++ shim for operator 'narrow' over 'slot' to 'int'")
        self.assertIn(message, lint.stderr)
        self.assertIn(message, gen.stderr)


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

    def test_declared_feature_name_is_a_boolean_primary(self):
        """`feature NAME = ...` is usable as `NAME`, not just `feature("...")`."""
        r = lint_source("feature HasAVX = Subtarget.hasAVX()\n"
                        "type X86_Vec256 = LLT::fixed_vector(8, 32)\n"
                        "ruleset X_ADD: G_ADD\n"
                        "    legal (HasAVX and in(slot(0), X86_Vec256))\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 error(s)", r.stdout)

    def test_undeclared_feature_name_is_rejected(self):
        r = lint_source("type X86_Vec256 = LLT::fixed_vector(8, 32)\n"
                        "ruleset X_ADD: G_ADD\n"
                        "    legal (HasAVX and in(slot(0), X86_Vec256))\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("expected comparison", r.stderr)

    def test_undeclared_feature_is_a_diagnostic(self):
        """Every layer says it, not just the one that happened to build first.

        `feature("...")` carries the C++ expression, not the declaration's
        name.  ``lint`` and every ``gen`` backend must report it as a
        diagnostic, not silently emit a reference to an undeclared feature.
        """
        text = ("feature F = Subtarget.hasAVX()\n"
                "ruleset X_ADD: G_ADD\n"
                "    legal feature(\"Subtarget.hasAVX2()\")\n")
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "T.gisel"
            src.write_text(text)
            r = run("lint", str(src))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn(":3:", r.stderr)
            for emit in ("inc", "check", "core"):
                r = run("gen", str(src), f"--emit={emit}",
                        "--out", str(Path(d) / f"x.{emit}"))
                self.assertEqual(r.returncode, 2, f"{emit}: {r.stdout}{r.stderr}")
                self.assertIn("undeclared feature expression", r.stderr)

    def test_unknown_type_name_is_a_diagnostic(self):
        """A type leaf must name a declared record, in both spellings.

        `in(slot(0), [s8])` (a set) and `in(slot(0), s8)` (one type) both
        reach the core backend, which used to raise KeyError from
        `type_name` -- a traceback, not a diagnostic, and only after lint had
        already said 0 error(s).
        """
        for rule in ("    legal in(slot(0), [s8])\n",
                     "    legal in(slot(0), s8)\n"):
            r = lint_source("ruleset R: G_ADD\n" + rule)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn(":2:", r.stderr)
            self.assertIn("unknown type name 's8'", r.stderr)

    def test_declared_type_names_still_lint_clean(self):
        r = lint_source("type X_s8 = LLT::scalar(8)\n"
                        "ruleset R: G_ADD\n"
                        "    legal in(slot(0), [X_s8])\n"
                        "    legal in(slot(0), X_s8)\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_exit_refuses_an_unknown_type_without_a_traceback(self):
        # `.inc` used to map the canonical spelling `s8` back to a declared
        # record, so the same source produced C++ while `core` said no.
        for emit in ("inc", "check", "core"):
            with tempfile.TemporaryDirectory() as d:
                src = Path(d) / "T.gisel"
                src.write_text("ruleset R: G_ADD\n"
                               "    legal in(slot(0), [s8])\n")
                r = run("gen", str(src), f"--emit={emit}",
                        "--out", str(Path(d) / "x.json"))
            self.assertEqual(r.returncode, 2, f"{emit}: {r.stdout + r.stderr}")
            self.assertIn("unknown type name 's8'", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

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


class ImportInventory(unittest.TestCase):
    """The census in docs/REPORT-riscv.md is the tool's output, not by hand."""

    SRC = Path("/home/ubuntu/llvm/trees/explore/llvm/lib/Target/RISCV/GISel/"
               "RISCVLegalizerInfo.cpp")

    @unittest.skipUnless(SRC.exists(), "needs the explore tree")
    def test_riscv_census_is_stable(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" /
                                                "import-inventory.py"),
                            str(self.SRC)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for line in ("| `getActionDefinitionsBuilder(...)` | 82 |",
                     "| top-level statements | 143 |",
                     "| chains extended later by name | 6 |",
                     "| estimated core rules | 355 |"):
            self.assertIn(line, r.stdout)


class ArityTable(unittest.TestCase):
    """The table the checker trusts; the old regex got G_VECREDUCE_FADD wrong."""

    def test_known_shapes(self):
        m = dsl.load_arity_manifest()
        self.assertEqual(m["G_VECREDUCE_FADD"], 2)   # VectorReduction: type0/1
        self.assertEqual(m["G_MEMCPY"], 3)           # ptype0/ptype1/type2
        self.assertEqual(m["G_ATOMICRMW_ADD"], 2)    # ptype1/type0
        self.assertEqual(m["G_FENCE"], 0)            # no type operands
        self.assertIsNone(m["G_INTRINSIC"])          # variable_ops



if __name__ == "__main__":
    unittest.main()
