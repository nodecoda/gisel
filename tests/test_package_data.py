"""`--corpus NAME` must work from an installed wheel, not just a checkout.

The corpus and its feature tables are canonical under `tests/`, because the
frozen artifacts record `tests/corpus/...` as the origin of every ruleset.
The wheel therefore ships byte-identical copies under `gisel/data/`, produced
by `tools/sync-package-data.py`.  These tests keep the two copies from
drifting and pin the shortcut to the long form: `--corpus m68k` and the two
explicit paths must write the same bytes.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "tools" / "sync-package-data.py"
DATA = ROOT / "gisel" / "data"

TARGETS = {"aarch64", "arm", "m68k", "mips", "ppc", "riscv", "spirv",
           "wasm", "x86"}


def run(*args):
    return subprocess.run([sys.executable, "-m", "gisel", *args],
                          cwd=ROOT, capture_output=True, text=True)


class CopiesAreTheCheckout(unittest.TestCase):
    def test_package_data_is_in_sync(self):
        done = subprocess.run([sys.executable, str(SYNC), "--check"],
                              cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("in sync", done.stdout)

    def test_the_wheel_declares_the_corpus_files(self):
        text = (ROOT / "pyproject.toml").read_text()
        self.assertIn('"data/corpus/*.gisel"', text)
        self.assertIn('"data/cases/*.json"', text)


class EveryTargetResolves(unittest.TestCase):
    def test_the_manifest_covers_nine_targets(self):
        from gisel import corpus
        self.assertEqual(set(corpus.names()), TARGETS)

    def test_each_target_names_files_that_exist(self):
        from gisel import corpus
        for name in corpus.names():
            with self.subTest(target=name):
                entry = corpus.get(name)
                self.assertEqual(entry.name, name)
                self.assertTrue(entry.source.is_file(), entry.source)
                self.assertEqual(entry.source.suffix, ".gisel")
                for extra in (entry.features, entry.axes):
                    if extra is not None:
                        self.assertTrue(extra.is_file(), extra)

    def test_the_manifest_declares_its_origin(self):
        doc = json.loads((DATA / "corpora.json").read_text())
        self.assertEqual(doc["schema"], 1)
        self.assertIn("tests/", doc["source"])


class ShortcutEqualsTwoPaths(unittest.TestCase):
    """`--corpus` is sugar, so it must not change a single byte."""

    def test_cases_and_domain_match_the_explicit_paths(self):
        from gisel import corpus
        entry = corpus.get("m68k")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pairs = {}
            for verb, extra in (("cases", []), ("domain", [])):
                short = tmp / ("%s.short.jsonl" % verb)
                long = tmp / ("%s.long.jsonl" % verb)
                a = run(verb, "--corpus", "m68k", "--out", str(short), *extra)
                b = run(verb, str(entry.source),
                        "--features", str(entry.features),
                        "--out", str(long), *extra)
                self.assertEqual(a.returncode, 0, a.stderr)
                self.assertEqual(b.returncode, 0, b.stderr)
                pairs[verb] = (short.read_bytes(), long.read_bytes())
            for verb, (short, long) in pairs.items():
                with self.subTest(verb=verb):
                    self.assertEqual(short, long)
                    self.assertTrue(short)

    def test_cases_count_is_pinned(self):
        # 35 is the M68k contract: 14 equivalence + 11 boundary + 10 outside.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "m68k.jsonl"
            done = run("cases", "--corpus", "m68k", "--out", str(out))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("cases=35", done.stdout)
            self.assertEqual(len(out.read_text().splitlines()), 35)

    def test_domain_point_count_is_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "m68k.jsonl"
            done = run("domain", "--corpus", "m68k", "--out", str(out))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("points=112", done.stdout)
            self.assertEqual(len(out.read_text().splitlines()), 112)


class EveryVerbAcceptsTheName(unittest.TestCase):
    """The sugar is not specific to cases/domain: one spelling everywhere."""

    def test_gen_lint_and_graph_accept_a_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            inc = tmp / "m68k.inc"
            core = tmp / "m68k.core.json"
            a = run("gen", "--corpus", "m68k", "--emit=inc", "--out", str(inc))
            self.assertEqual(a.returncode, 0, a.stderr)
            self.assertIn("13 rules", a.stdout)
            b = run("gen", "--corpus", "m68k", "--emit=core", "--out", str(core))
            self.assertEqual(b.returncode, 0, b.stderr)
            c = run("lint", "--corpus", "m68k")
            self.assertEqual(c.returncode, 0, c.stderr)
            self.assertIn("0 error(s)", c.stdout)
            d = run("graph", "--corpus", "m68k")
            self.assertEqual(d.returncode, 0, d.stderr)
            self.assertIn("cycles      : 0", d.stdout)

    def test_gen_by_name_matches_gen_by_path_byte_for_byte(self):
        from gisel import corpus
        entry = corpus.get("m68k")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            by_name = tmp / "a.inc"
            by_path = tmp / "b.inc"
            run("gen", "--corpus", "m68k", "--emit=inc", "--out", str(by_name))
            run("gen", str(entry.source), "--emit=inc", "--out", str(by_path))
            self.assertEqual(by_name.read_bytes(), by_path.read_bytes())

    def test_check_accepts_a_name_and_ignores_origin_by_default(self):
        # A core artifact generated from `--corpus` records the package path
        # in every origin; `check` strips origins unless --strict-origin, so
        # comparing it with a tests/corpus artifact still passes.
        with tempfile.TemporaryDirectory() as tmp:
            core = Path(tmp) / "m68k.core.json"
            run("gen", "--corpus", "m68k", "--emit=core", "--out", str(core))
            same = run("check", "--corpus", "m68k", "--emit=core",
                       "--against", str(core))
            self.assertEqual(same.returncode, 0, same.stderr)
            strict = run("check", "--corpus", "m68k", "--emit=core",
                         "--strict-origin", "--against", str(core))
            self.assertEqual(strict.returncode, 0, strict.stderr)


class BadInvocations(unittest.TestCase):
    def test_gen_rejects_both_spellings(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = run("gen", "tests/corpus/M68kLegalizerInfo.gisel",
                       "--corpus", "m68k", "--emit=inc",
                       "--out", str(Path(tmp) / "x.inc"))
        self.assertEqual(done.returncode, 2)
        self.assertIn("not both", done.stderr)

    def test_source_and_corpus_together_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = run("cases", "tests/corpus/M68kLegalizerInfo.gisel",
                       "--corpus", "m68k",
                       "--out", str(Path(tmp) / "x.jsonl"))
        self.assertEqual(done.returncode, 2)
        self.assertIn("not both", done.stderr)

    def test_neither_is_a_usage_error_that_lists_the_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = run("domain", "--out", str(Path(tmp) / "x.jsonl"))
        self.assertEqual(done.returncode, 2)
        self.assertIn("--corpus NAME", done.stderr)
        self.assertIn("m68k", done.stderr)

    def test_unknown_name_lists_the_choices(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = run("cases", "--corpus", "no-such-target",
                       "--out", str(Path(tmp) / "x.jsonl"))
        self.assertEqual(done.returncode, 2)
        self.assertIn("unknown corpus", done.stderr)
        for name in TARGETS:
            self.assertIn(name, done.stderr)

    def test_no_output_is_written_on_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.jsonl"
            run("cases", "--corpus", "no-such-target", "--out", str(out))
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
