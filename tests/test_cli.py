"""The product surface: which commands exist, and what their exit codes mean.

`spec/cli.md` is the contract; these tests keep the implementation from drifting
away from it.  Workbench commands (``tools/``) are deliberately absent.
"""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gisel
from gisel.cli import COMMANDS

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

FIXTURE = """\
type S8 = LLT::scalar(8)
type S32 = LLT::scalar(32)

ruleset G_ADD: G_ADD
    legal in(slot(0), S32)
"""

BAD = "ruleset G_ADD: G_ADD\n    legal in(slot(0),\n"

GRAPH_FIXTURE = """\
type S8 = LLT::scalar(8)
type S32 = LLT::scalar(32)

ruleset G_ADD: G_ADD
    legal in(slot(0), S32)
    widen(slot(0), ty(S32))
"""

SLOT_OUT_OF_RANGE = """\
type S32 = LLT::scalar(32)

ruleset G_ADD: G_ADD
    widen(slot(3), S32)
"""


def run(*args):
    return subprocess.run([sys.executable, "-m", "gisel", *args],
                          cwd=ROOT, capture_output=True, text=True)


def write(directory, name, text):
    path = Path(directory) / name
    path.write_text(text)
    return path


def project_table():
    """pyproject's [project] table without a TOML dependency on 3.10."""
    text = PYPROJECT.read_text()
    try:
        import tomllib
    except ImportError:  # Python 3.10
        head = text.split("[project]", 1)[1].split("\n[", 1)[0]
        version = re.search(r'^\s*version\s*=\s*"(.*)"', head, re.M)
        dynamic = re.search(r'^\s*dynamic\s*=\s*\[(.*)\]', head, re.M)
        return {"version": version.group(1) if version else None,
                "dynamic": [s.strip().strip('"') for s in
                            (dynamic.group(1).split(",") if dynamic else [])]}
    return tomllib.loads(text)["project"]


class Version(unittest.TestCase):
    def test_one_source_of_truth(self):
        r = run("--version")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), f"gisel {gisel.__version__}")

    def test_packaging_reads_the_package_version(self):
        project = project_table()
        self.assertIn("version", project["dynamic"])
        self.assertIsNone(project["version"],
                          "pyproject must not hardcode the version")


class Commands(unittest.TestCase):
    def test_exactly_the_documented_set(self):
        r = run("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        listed = set(re.search(r"\{([a-z,]+)\}", r.stdout).group(1).split(","))
        self.assertEqual(listed, set(COMMANDS))

    def test_every_command_answers_help(self):
        for command in sorted(COMMANDS):
            r = run(command, "--help")
            self.assertEqual(r.returncode, 0, f"{command}: {r.stderr}")
            self.assertIn("usage:", r.stdout)

    def test_workbench_verb_is_not_a_command(self):
        r = run("diff", "a", "b")
        self.assertEqual(r.returncode, 2)
        self.assertIn("invalid choice", r.stderr)

    def test_packaging_ships_only_the_package(self):
        text = PYPROJECT.read_text()
        self.assertIn('include = ["gisel*"]', text)
        self.assertNotIn("tools*", text)


class ExitCodes(unittest.TestCase):
    """0 = yes, 1 = no, 2 = could not start.  Nothing else."""

    def test_gen_success_is_zero_and_syntax_error_is_two(self):
        with tempfile.TemporaryDirectory() as d:
            good = write(d, "good.gisel", FIXTURE)
            bad = write(d, "bad.gisel", BAD)
            self.assertEqual(
                run("gen", str(good), "--out", f"{d}/good.inc").returncode, 0)
            self.assertEqual(
                run("gen", str(bad), "--out", f"{d}/bad.inc").returncode, 2)
            self.assertEqual(
                run("gen", f"{d}/missing.gisel", "--out", f"{d}/x").returncode, 2)

    def test_check_says_yes_zero_and_no_one(self):
        with tempfile.TemporaryDirectory() as d:
            src = write(d, "a.gisel", FIXTURE)
            out = Path(d) / "a.inc"
            self.assertEqual(run("gen", str(src), "--out", str(out)).returncode, 0)
            self.assertEqual(
                run("check", str(src), "--against", str(out)).returncode, 0)
            out.write_text(out.read_text() + "// drift\n")
            self.assertEqual(
                run("check", str(src), "--against", str(out)).returncode, 1)

    def test_lint_clean_zero_and_error_one(self):
        with tempfile.TemporaryDirectory() as d:
            clean = write(d, "clean.gisel", FIXTURE)
            self.assertEqual(run("lint", str(clean)).returncode, 0)
            bad = write(d, "bad.gisel", SLOT_OUT_OF_RANGE)
            self.assertEqual(run("lint", str(bad)).returncode, 1)

    def test_graph_zero_without_a_cycle_one_with_the_negative_control(self):
        with tempfile.TemporaryDirectory() as d:
            src = write(d, "g.gisel", GRAPH_FIXTURE)
            self.assertEqual(
                run("graph", str(src), "--config", "none").returncode, 0)
            self.assertEqual(
                run("graph", str(src), "--config", "none",
                    "--inject-edge").returncode, 1)

    def test_cases_and_domain_are_zero(self):
        with tempfile.TemporaryDirectory() as d:
            src = write(d, "g.gisel", FIXTURE)
            cases = Path(d) / "q.jsonl"
            r = run("cases", str(src), "--out", str(cases), "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(cases.read_text().strip())
            r = run("domain", str(src), "--out", f"{d}/d.jsonl", "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            stats = json.loads(r.stdout)
            # The flags report how the denominator was narrowed, so a reader
            # can recompute it instead of trusting "points".
            for key in ("raw_points", "truncated", "shape_dropped",
                        "shape_dropped_total", "skipped_opcodes"):
                self.assertIn(key, stats)
            self.assertEqual(stats["raw_points"], stats["points"])
            self.assertFalse(stats["truncated"])


class Determinism(unittest.TestCase):
    """`spec/cli.md` §3: the same input produces byte-identical output."""

    def test_core_bytes_are_stable(self):
        with tempfile.TemporaryDirectory() as d:
            source = write(d, "d.gisel", FIXTURE)
            outs = []
            for i in range(2):
                out = Path(d) / f"d{i}.core"
                r = run("gen", str(source), "--emit=core", "--out", str(out))
                self.assertEqual(r.returncode, 0, r.stderr)
                outs.append(out.read_bytes())
            self.assertEqual(outs[0], outs[1])

    def test_graph_stdout_is_stable(self):
        with tempfile.TemporaryDirectory() as d:
            source = write(d, "g.gisel", GRAPH_FIXTURE)
            first = run("graph", str(source), "--config", "none", "--json")
            second = run("graph", str(source), "--config", "none", "--json")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)


class Streams(unittest.TestCase):
    def test_lint_keeps_diagnostics_off_stdout(self):
        with tempfile.TemporaryDirectory() as d:
            src = write(d, "bad.gisel", SLOT_OUT_OF_RANGE)
            r = run("lint", str(src))
            self.assertEqual(r.returncode, 1)
            self.assertNotIn("out of range", r.stdout)
            self.assertIn("out of range", r.stderr)

    def test_json_only_changes_stdout(self):
        with tempfile.TemporaryDirectory() as d:
            src = write(d, "bad.gisel", SLOT_OUT_OF_RANGE)
            plain = run("lint", str(src))
            machine = run("lint", str(src), "--json")
            self.assertEqual(plain.returncode, machine.returncode)
            doc = json.loads(machine.stdout)
            self.assertEqual(len(doc["errors"]),
                             plain.stderr.count("out of range"))


if __name__ == "__main__":
    unittest.main()
