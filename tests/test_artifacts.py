"""Artifact gates: the checked-in .gisel reproduces the frozen artifacts.

The artifacts are gisel's own output (a drift baseline), not a second
implementation's: the ``-gen-legalizer`` backend and the ``.td`` it read are
retired.  Rule fidelity is the answer gate in ``EvaluatorCorpus`` below and in
``docs/CORPORA.md``.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
# All three corpora are cpp -> .gisel; the artifacts below are frozen from
# gisel itself (docs/CORPORA.md).
CORPORA = (("x86", "X86LegalizerInfo"), ("aarch64", "AArch64LegalizerInfo"))
SELF_BASELINE = (("riscv", "RISCVLegalizerInfo"),)


def run(*args, env=None):
    return subprocess.run([sys.executable, "-m", "gisel.cli", *args],
                          cwd=ROOT, env=env, capture_output=True, text=True)


class GoldenInc(unittest.TestCase):
    """M1: `gisel gen --emit=inc` is byte-identical to the frozen .inc."""

    def test_generated_inc_matches_golden(self):
        for name, src in CORPORA:
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / f"{name}.inc"
                r = run("gen", str(TESTS / "corpus" / f"{src}.gisel"),
                        "--emit=inc", "--out", str(out))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(
                    out.read_bytes(), (TESTS / "artifacts" / f"{name}.inc").read_bytes(),
                    f"{name}: generated .inc differs from golden")

    def test_check_inc_is_up_to_date(self):
        for name, src in CORPORA:
            r = run("check", str(TESTS / "corpus" / f"{src}.gisel"),
                    "--emit=inc", "--against", str(TESTS / "artifacts" / f"{name}.inc"))
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_llvm_tblgen_needed(self):
        """PATH without llvm-tblgen still reproduces both artifacts."""
        env = dict(os.environ, PATH="/usr/bin:/bin")
        for name, src in CORPORA:
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / f"{name}.inc"
                r = run("gen", str(TESTS / "corpus" / f"{src}.gisel"),
                        "--emit=inc", "--out", str(out), env=env)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(out.read_bytes(),
                                 (TESTS / "artifacts" / f"{name}.inc").read_bytes())

    def test_terminal_call_count_is_conserved(self):
        """One terminal per rule, plus one `.immIdx` per ImmIdx record."""
        expected = {"x86": (328, 0), "aarch64": (741, 3)}
        total = 0
        for name, _ in CORPORA:
            text = (TESTS / "artifacts" / f"{name}.inc").read_text()
            # Nested `if` blocks indent the chain one level deeper.
            calls = re.findall(r"^\s+\.([A-Za-z0-9_]+)", text, re.M)
            imm = [c for c in calls if c == "immIdx"]
            rules, imm_expected = expected[name]
            self.assertEqual(len(calls) - len(imm), rules, name)
            self.assertEqual(len(imm), imm_expected, name)
            total += len(calls)
        self.assertEqual(total, 1072)


class GoldenCheckJson(unittest.TestCase):
    """M2: `gisel gen --emit=check` is byte-identical to the frozen JSON."""

    def test_generated_check_matches_golden(self):
        for name, src in CORPORA:
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / f"{name}.check.json"
                r = run("gen", str(TESTS / "corpus" / f"{src}.gisel"),
                        "--emit=check", "--out", str(out))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(
                    out.read_bytes(),
                    (TESTS / "artifacts" / f"{name}.check.json").read_bytes(),
                    f"{name}: check JSON differs from golden")

    def test_coverage_sums_to_rules(self):
        """rules == core_rules + legacy_rules + coverage (LoweringStats:55)."""
        sys.path.insert(0, str(ROOT))
        from gisel import ast as A
        from gisel.backend import check_json

        for _, src in CORPORA:
            gs = A.parse_program((TESTS / "corpus" / f"{src}.gisel").read_text())
            c = check_json.counts(gs)
            self.assertEqual(c["rules"],
                             c["core_rules"] + c["legacy_rules"] + c["coverage"])


sys.path.insert(0, str(ROOT))
from gisel.backend.core_json import strip_origin as _strip_origin  # noqa: E402


class SelfBaseline(unittest.TestCase):
    """RISC-V's four artifacts are frozen from gisel (same as X86/AArch64 now).

    The gate catches corpus or generator drift; it does not claim byte
    equality with `llvm-tblgen` (`docs/CORPORA.md`).
    """

    def test_all_four_outputs_match_the_frozen_files(self):
        for name, src in SELF_BASELINE:
            with tempfile.TemporaryDirectory() as d:
                for emit, suffix in (("inc", "inc"),
                                     ("check", "check.json")):
                    out = Path(d) / f"{name}.{suffix}"
                    r = run("gen", str(TESTS / "corpus" / f"{src}.gisel"),
                            f"--emit={emit}", "--out", str(out))
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertEqual(
                        out.read_bytes(),
                        (TESTS / "artifacts" / f"{name}.{suffix}").read_bytes(),
                        f"{name}.{suffix}: frozen baseline is stale")
                out = Path(d) / f"{name}.core.json"
                r = run("gen", str(TESTS / "corpus" / f"{src}.gisel"),
                        "--emit=core", "--out", str(out))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(
                    _strip_origin(out.read_text()),
                    _strip_origin(
                        (TESTS / "artifacts" / f"{name}.core.json").read_text()),
                    "riscv.core.json: frozen baseline is stale outside origin")


class GoldenCoreJson(unittest.TestCase):
    """M4: `--emit=core` reproduces the normal form, modulo origin."""

    def test_generated_core_matches_golden(self):
        for name, src in CORPORA:
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / f"{name}.core.json"
                r = run("gen", str(TESTS / "corpus" / f"{src}.gisel"),
                        "--emit=core", "--out", str(out))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(
                    _strip_origin(out.read_text()),
                    _strip_origin((TESTS / "artifacts" / f"{name}.core.json").read_text()),
                    f"{name}: core JSON differs outside origin")

    def test_check_against_the_baseline_ignores_origin(self):
        for name, src in CORPORA:
            r = run("check", str(TESTS / "corpus" / f"{src}.gisel"),
                    "--emit=core",
                    "--against", str(TESTS / "artifacts" / f"{name}.core.json"))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = run("check", str(TESTS / "corpus" / f"{src}.gisel"),
                    "--emit=core", "--strict-origin",
                    "--against", str(TESTS / "artifacts" / f"{name}.core.json"))
            self.assertEqual(r.returncode, 1, "strict-origin must see the .gisel lines")

    def test_origin_points_at_the_gisel_source(self):
        sys.path.insert(0, str(ROOT))
        from gisel import ast as A
        from gisel.backend import core_json

        for _, src in CORPORA:
            text = (TESTS / "corpus" / f"{src}.gisel").read_text()
            gs = A.parse_program(text)
            lines = core_json.stage_lines(text)
            self.assertEqual(len(lines), len(gs.rulesets))
            self.assertTrue(all(n > 0 for n in lines.values()))

    def test_evaluator_answers_identically(self):
        """Feed both documents to gisel.eval; every answer must agree."""
        sys.path.insert(0, str(ROOT))
        from gisel import eval as E

        compared = 0
        answered = 0
        for name, src in CORPORA:
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / f"{name}.core.json"
                r = run("gen", str(TESTS / "corpus" / f"{src}.gisel"),
                        "--emit=core", "--out", str(out))
                self.assertEqual(r.returncode, 0, r.stderr)
                mine = json.loads(out.read_text())
                base = json.loads(
                    (TESTS / "artifacts" / f"{name}.core.json").read_text())
                self.assertEqual(mine["domain"], base["domain"])

                feats = set()
                def walk(o):
                    if isinstance(o, dict):
                        if o.get("name") == "hasFeature":
                            feats.add(o["args"][0])
                        for v in o.values():
                            walk(v)
                    elif isinstance(o, list):
                        for v in o:
                            walk(v)
                walk(base)
                table = {"default": {f: True for f in feats}}
                features = E.Features(table)

                docs = [E.Evaluator(mine, features), E.Evaluator(base, features)]
                points = 0
                for rs in mine["rulesets"]:
                    arity = _arity(rs)
                    for opcode in rs["opcodes"]:
                        for t in mine["domain"]["types"]:
                            # the domain is Core IR spelling (p0:64), not
                            # LLT::print (p0) -- spec/m4-scope.md §1.
                            types = [E.parse_core_llt(t)] * arity
                            mems = [E.MemDesc(types[0], E.size_in_bits(types[0])[0])]
                            answers = []
                            for ev in docs:
                                try:
                                    answers.append(
                                        E.evaluate(ev, "default", opcode, types, mems))
                                except Exception as e:  # noqa: BLE001 - compare both sides
                                    # Ill-typed synthetic points (e.g. elemOf on a
                                    # scalar) must fail the same way on both docs.
                                    answers.append(("error", type(e).__name__, str(e)))
                            self.assertEqual(answers[0], answers[1],
                                             f"{name} {opcode} {t}")
                            compared += 1
                            points += 1
                            if answers[0][0] != "error":
                                answered += 1
                self.assertGreater(points, 0, name)
                # A vacuous harness (everything errors) would prove nothing.
                self.assertGreater(answered, points // 2, name)
        self.assertGreater(compared, 1000)

    def test_domain_types_are_core_llt(self):
        """Every domain entry must parse as Core IR, including p0:<width>."""
        sys.path.insert(0, str(ROOT))
        from gisel import eval as E

        for name, _ in CORPORA:
            doc = json.loads((TESTS / "artifacts" / f"{name}.core.json").read_text())
            for t in doc["domain"]["types"]:
                try:
                    E.parse_core_llt(t)
                except E.EvalError as e:
                    self.fail(f"{name}: domain type {t!r} is not Core IR: {e}")
            self.assertIn("p0:64", doc["domain"]["types"], name)
        self.assertEqual(E.parse_core_llt("p0:64"), ("pointer", 0, 64))


def _max_index(node, kind):
    """Largest slot/sameAs index appearing in a rule body."""
    best = 0
    if isinstance(node, dict):
        if node.get("kind") == kind and isinstance(node.get("index"), int):
            best = max(best, node["index"] + 1)
        if node.get("kind") == kind and isinstance(node.get("value"), int):
            best = max(best, node["value"] + 1)
        for v in node.values():
            best = max(best, _max_index(v, kind))
    elif isinstance(node, list):
        for v in node:
            best = max(best, _max_index(v, kind))
    return best


def _arity(ruleset):
    """Type slots a rule set can address: type_idx, sameAs and slot indices."""
    n = 1
    for r in ruleset["rules"]:
        n = max(n, r.get("type_idx", 0) + 1)
        for key in ("predicate", "op", "on", "to"):
            n = max(n, _max_index(r.get(key), "slot"), _max_index(r.get(key), "sameAs"))
    return n


class EvaluatorSchemaShapes(unittest.TestCase):
    """Spellings the AArch64 corpus never exercised but the schema allows."""

    def test_nary_and_singular_not(self):
        sys.path.insert(0, str(ROOT))
        from gisel import eval as E

        ev = E.Evaluator({"rulesets": []},
                         E.Features({"c": {"f": True, "g": False}}))
        node = {"kind": "nary", "op": "all_of", "args": [
            {"kind": "leaf", "name": "hasFeature", "args": ["f"]},
            {"kind": "not", "arg": {"kind": "leaf", "name": "hasFeature",
                                    "args": ["g"]}}]}
        self.assertTrue(ev.bool_value(node, [], [], "c"))
        node["args"][1] = {"kind": "not", "args": [
            {"kind": "leaf", "name": "hasFeature", "args": ["f"]}]}
        self.assertFalse(ev.bool_value(node, [], [], "c"))

    def test_wildcard_pointer_matches_any_width(self):
        sys.path.insert(0, str(ROOT))
        from gisel import eval as E

        self.assertTrue(E.llt_eq(E.parse_core_llt("p0:32"),
                                 E.parse_core_llt("p0:*")))
        self.assertTrue(E.llt_eq(E.parse_core_llt("v2p0:32"),
                                 E.parse_core_llt("v2p0:*")))
        self.assertFalse(E.llt_eq(E.parse_core_llt("p1:32"),
                                  E.parse_core_llt("p0:*")))
        self.assertFalse(E.llt_eq(E.parse_core_llt("s32"),
                                  E.parse_core_llt("p0:*")))


class EvaluatorCorpus(unittest.TestCase):
    """Differential runs: our core JSON vs the frozen target answers."""

    def _check(self, corpus, features, dump, total):
        sys.path.insert(0, str(ROOT))
        from gisel import eval as E

        cases = TESTS / "cases"
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "core.json"
            r = run("gen", str(TESTS / "corpus" / corpus),
                    "--emit=core", "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            ev = E.Evaluator(json.loads(out.read_text()),
                             E.load_features(str(cases / features)))
        got, disagree, errors, first, _ = E.run_cases(ev, str(cases / dump))
        self.assertEqual(got, total)
        self.assertEqual((disagree, errors), (0, 0), first)

    def test_aarch64_cases_agree(self):
        self._check("AArch64LegalizerInfo.gisel", "features.json",
                    "a64_ref_dump.jsonl", 9632)

    def test_x86_cases_agree(self):
        self._check("X86LegalizerInfo.gisel", "x86-features.json",
                    "x86_ref_dump.jsonl", 5632)

    def test_riscv_cases_agree(self):
        """19512 = 2439 points x 8 configurations of the C++ constructor."""
        self._check("RISCVLegalizerInfo.gisel", "riscv-features.json",
                    "riscv_ref_dump.jsonl", 19512)

    def test_riscv_core_is_one_table_per_opcode(self):
        """The frozen artifact has one rule set per opcode.

        RISCV builds G_CTLZ twice (Zbb and non-Zbb chains).  The artifact
        contract concatenates the chains per opcode; that duplicates the
        shared Zbb rules once (402 -> 413) and drops the empty second block
        (96 -> 91).
        """
        sys.path.insert(0, str(ROOT))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "r.core.json"
            r = run("gen", str(TESTS / "corpus" / "RISCVLegalizerInfo.gisel"),
                    "--emit=core", "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            doc = json.loads(out.read_text())
        count = {}
        for rs in doc["rulesets"]:
            for op in rs["opcodes"]:
                count[op] = count.get(op, 0) + 1
        self.assertEqual([op for op, n in count.items() if n > 1], [])
        self.assertEqual(len(doc["rulesets"]), 91)
        self.assertEqual(sum(len(rs["rules"]) for rs in doc["rulesets"]), 413)


class ProbeCorpus(unittest.TestCase):
    """Probe corpora: every backend must still accept the source.

    M68k and WebAssembly are imported from pinned C++ (see
    `tests/test_import_cxx.py`), but they have no frozen artifact baseline the
    way X86/AArch64/RISC-V do; what is checked here is that each source
    survives every backend and lands in the canonical form intact.  WebAssembly
    is also the corpus that pins the immediate axis.
    """

    PROBES = (("M68kLegalizerInfo", 6, 13),
              ("PowerPCLegalizerInfo", 15, 25),
              ("ARMLegalizerInfo", 52, 96),
              ("WebAssemblyLegalizerInfo", 29, 109))

    def test_all_backends_accept_the_probe(self):
        for name, _, nrules in self.PROBES:
            for emit in ("inc", "check", "core"):
                with tempfile.TemporaryDirectory() as d:
                    out = Path(d) / "probe"
                    r = run("gen", "--emit=" + emit, "--out", str(out),
                            str(TESTS / "corpus" / f"{name}.gisel"))
                    self.assertEqual(r.returncode, 0, (name, emit, r.stderr))
                    self.assertIn(f"{nrules} rules", r.stdout)

    def test_imm_predicate_is_evaluated(self):
        """`imm(0)` reaches the evaluator, not just the C++ emitter.

        hasSignExt = true; 8 and 16 are legal for both widths, 32 only for
        i64, and everything else falls through to `lower`.
        """
        the_case = ('{"config":"signext","name":"G_SEXT_INREG","types":%s,'
                    '"imms":%s,"mem":null,"action":"%s","type_idx":0,'
                    '"new_type":"LLT_invalid"}')
        rows = [the_case % ('["i32"]', "[8]", "Legal"),
                the_case % ('["i32"]', "[16]", "Legal"),
                the_case % ('["i32"]', "[32]", "Lower"),
                the_case % ('["i64"]', "[32]", "Legal"),
                the_case % ('["i64"]', "[8]", "Legal")]
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            core = d / "w.core.json"
            r = run("gen", "--emit=core", "--out", str(core),
                    str(TESTS / "corpus" / "WebAssemblyLegalizerInfo.gisel"))
            self.assertEqual(r.returncode, 0, r.stderr)
            feats = d / "f.json"
            feats.write_text(json.dumps({"signext": {
                "ST.hasSignExt()": True,
                "ST.hasAddr64()": True}}))
            cases = d / "c.jsonl"
            cases.write_text("\n".join(rows) + "\n")
            r = run("eval", "--doc", str(core), "--features", str(feats),
                    "--cases", str(cases))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("cases=5 disagreements=0 errors=0", r.stdout)

    def test_wasm_core_json_is_closed(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "w.core.json"
            r = run("gen", "--emit=core", "--out", str(out),
                    str(TESTS / "corpus" / "WebAssemblyLegalizerInfo.gisel"))
            self.assertEqual(r.returncode, 0, r.stderr)
            doc = json.loads(out.read_text())
        self.assertEqual(len(doc["rulesets"]), 29)
        self.assertEqual(sum(len(rs["rules"]) for rs in doc["rulesets"]), 109)
        self.assertEqual(doc["escapes"], [])
        # i8/i16 are named but only used through mem_desc; p0 is a wildcard in
        # sets and p0:64 in the domain.
        self.assertEqual(doc["domain"]["types"],
                         ["f32", "f64", "i16", "i32", "i64", "i8", "p0:64",
                          "s32", "s64"])
        # The immediate axis: one rule reads imm 0, and the domain says so.
        self.assertEqual(doc["domain"]["imms"], [0])
        sext = [rs for rs in doc["rulesets"] if rs["opcodes"] == ["G_SEXT_INREG"]]
        self.assertEqual(len(sext), 1)
        self.assertEqual([r["op"] for r in sext[0]["rules"]],
                         ["legal", "widen", "narrow", "lower"])
        legal = sext[0]["rules"][0]["predicate"]
        blob = json.dumps(legal)
        self.assertIn('"kind": "imm"', blob)
        self.assertIn('"of": "Int"', blob)


class SourceNameIndependence(unittest.TestCase):
    """Renaming a source must not change what the backends emit."""

class CliSurface(unittest.TestCase):
    def test_module_entrypoint_and_version(self):
        from gisel import __version__

        r = subprocess.run([sys.executable, "-m", "gisel", "--version"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), f"gisel {__version__}")


class SourceErrors(unittest.TestCase):
    """A human-facing language must point at the file and the line it means."""

    def _run_bad(self, text, source="bad.gisel"):
        d = tempfile.mkdtemp()
        src = Path(d) / source
        src.write_text(text)
        return run("gen", str(src), "--emit=inc", "--out", str(Path(d) / "x.inc")), src

    def test_error_points_at_the_source_line(self):
        body = ('type X_s32 = LLT::scalar(32)\n'
                '\n'
                'ruleset X_A: G_ADD\n'
                '    legal in(slot(0), [X_s32])\n'
                '    widen(slot(0) pow2)\n')
        r, src = self._run_bad(body)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn(f"{src}:5: expected ,, got ID ('pow2')", r.stderr)

    def test_check_errors_are_not_tracebacks(self):
        r = run("check", str(TESTS / "corpus" / "X86LegalizerInfo.gisel"),
                "--emit=inc", "--against", "/nonexistent/x.inc")
        self.assertEqual(r.returncode, 2)
        self.assertIn("No such file", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        r = run("check", "/nonexistent/nope.gisel", "--emit=inc",
                "--against", str(TESTS / "artifacts" / "x86.inc"))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_missing_source_is_not_a_traceback(self):
        r = run("gen", "/nonexistent/nope.gisel", "--emit=inc", "--out", "/tmp/x.inc")
        self.assertEqual(r.returncode, 2)
        self.assertIn("No such file", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_wrapped_rule_reports_the_first_physical_line(self):
        body = ('type X_s32 = LLT::scalar(32)\n'
                'ruleset X_A: G_ADD\n'
                '    widen(slot(0),\n'
                '          pow2\n'
                '    legal in(slot(0), X_s32)\n')
        r, src = self._run_bad(body)
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"{src}:3:", r.stderr)


class ArtifactIntegrity(unittest.TestCase):
    """The frozen artifacts are the oracle; bytes must not drift silently."""

    def test_sha256_manifest_matches_the_checked_in_bytes(self):
        lines = (TESTS / "artifacts" / "SHA256").read_text().splitlines()
        seen = 0
        for line in lines:
            digest, path = line.split()
            p = TESTS / "artifacts" / Path(path).name
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),
                             digest, p.name)
            seen += 1
        self.assertEqual(seen, 9)


class ShimCoverage(unittest.TestCase):
    """G1: every (operator, observation, target) triple has a C++ shim."""

    def test_every_corpus_triple_has_a_shim(self):
        sys.path.insert(0, str(ROOT))
        from gisel import ast as A
        from gisel.backend import llvm_inc as inc

        seen = set()
        for _, src in CORPORA:
            gs = A.parse_program((TESTS / "corpus" / f"{src}.gisel").read_text())
            for rs in gs.rulesets:
                for rule in rs.rules:
                    on = rule.on
                    on_form = (inc.ONSERVATION_FORM.get(on["kind"], on["kind"])
                               if on else "")
                    seen.add((rule["op"], on_form,
                              rule.to["kind"] if rule.to else ""))
        missing = sorted(t for t in seen if t not in inc.SHIM_TABLE)
        self.assertEqual(missing, [])
        self.assertEqual(len(seen), 25)


class NegativeControl(unittest.TestCase):
    """A changed source must move the artifact; otherwise the gate is vacuous."""

    def _gen(self, text, d):
        src = Path(d) / "X86LegalizerInfo.gisel"
        src.write_text(text)
        out = Path(d) / "x86.inc"
        r = run("gen", str(src), "--emit=inc", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        return src, out

    def test_feature_change_is_visible(self):
        base = (TESTS / "corpus" / "X86LegalizerInfo.gisel").read_text()
        # The normal form keys a feature by its expression text, so a
        # mutation has to rewrite every occurrence.
        mutated = base.replace("Subtarget.canUseCMOV()", "Subtarget.hasCMOV()")
        self.assertNotEqual(base, mutated)
        golden = (TESTS / "artifacts" / "x86.inc").read_text()
        with tempfile.TemporaryDirectory() as d:
            src, out = self._gen(mutated, d)
            self.assertNotEqual(out.read_text(), golden)
            self.assertIn("Subtarget.hasCMOV()", out.read_text())
            r = run("check", str(src), "--emit=inc",
                    "--against", str(TESTS / "artifacts" / "x86.inc"))
            self.assertEqual(r.returncode, 1)
            self.assertIn("STALE", r.stderr)

    def test_target_change_is_visible(self):
        base = (TESTS / "corpus" / "X86LegalizerInfo.gisel").read_text()
        mutated = base.replace("pow2_min(8)", "pow2_min(16)", 1)
        self.assertNotEqual(base, mutated)
        golden = (TESTS / "artifacts" / "x86.inc").read_text()
        with tempfile.TemporaryDirectory() as d:
            _, out = self._gen(mutated, d)
            self.assertNotEqual(out.read_text(), golden)



class RemovedSurface(unittest.TestCase):
    """The .td renderer and its reader are gone from the CLI contract."""

    def test_td_backend_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            r = run("gen", str(TESTS / "corpus" / "X86LegalizerInfo.gisel"),
                    "--emit=td", "--out", str(Path(d) / "x.td"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("invalid choice", r.stderr)

    def test_check_td_alias_is_rejected(self):
        r = run("check", str(TESTS / "corpus" / "X86LegalizerInfo.gisel"),
                "--td", str(TESTS / "artifacts" / "x86.inc"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_bootstrap_is_rejected(self):
        r = run("bootstrap", "--td", "x.td", "--core", "x.json",
                "--out", "x.gisel")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("invalid choice", r.stderr)

    def test_default_emit_is_the_cpp_chain(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "x.inc"
            r = run("gen", str(TESTS / "corpus" / "X86LegalizerInfo.gisel"),
                    "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(out.read_bytes(),
                             (TESTS / "artifacts" / "x86.inc").read_bytes())


class SizeObservers(unittest.TestCase):
    """SizeOf/SizeInBytesOf have sort Int, but LLT returns a TypeSize.

    TypeSize's implicit conversion to an integer is a fatal error for a
    scalable vector.  The chain is instantiated for AArch64, so every size
    observer in the frozen chain must spell out getKnownMinValue() instead of
    leaving the conversion to whatever integer consumer follows it.
    """

    def test_chain_size_observers_take_known_min(self):
        for name, _ in CORPORA:
            text = (TESTS / "artifacts" / f"{name}.inc").read_text()
            for call in ("getSizeInBits()", "getSizeInBytes()"):
                start = 0
                while True:
                    i = text.find(call, start)
                    if i < 0:
                        break
                    tail = text[i + len(call):]
                    self.assertTrue(
                        tail.startswith(".getKnownMinValue()"),
                        f"{name}: {call} must take getKnownMinValue(): "
                        f"{text[max(0, i - 80):i + len(call) + 20]}")
                    start = i + len(call)
        aarch64 = (TESTS / "artifacts" / "aarch64.inc").read_text()
        self.assertIn("getSizeInBits().getKnownMinValue()", aarch64)
        self.assertIn("getSizeInBytes().getKnownMinValue()", aarch64)


if __name__ == "__main__":
    unittest.main()
