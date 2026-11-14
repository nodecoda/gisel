"""Docs that quote a run must quote one the repo can reproduce or freeze.

Two shapes, two rules:

* A transcript of a cheap command (the graph fixture: four states) is replayed
  here and compared byte for byte, so a stale hash fails the suite instead of
  teaching a reader an old number.
* A table that comes from an expensive run is bound to the artifact the repo
  freezes (the `--config none` golden), and the doc stops quoting numbers for
  the runs that are not frozen.

The instruction rule is the third: a "bump the version" example must not carry
a literal version, because the literal is wrong the moment it works.
"""

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "REPORT-graph.md"
QUICKSTART = ROOT / "docs" / "QUICKSTART-no-llvm.md"
RELEASING = ROOT / "docs" / "RELEASING.md"
GOLDEN = ROOT / "tests" / "artifacts" / "graph" / "x86-none.json"

FENCE = re.compile(r"```([A-Za-z0-9_+.-]*)\n(.*?)```", re.S)
HEREDOC = re.compile(r"cat > (\S+fixture\.gisel) <<'GI'\n(.*?)\nGI\n", re.S)
EXPECT = re.compile(r"# rc=(\d+)\s+states=(\d+) edges=(\d+) cycles=(\d+)\n"
                    r"(?:#(?! sha256)[^\n]*\n)*"
                    r"# sha256 ([0-9a-f]{64})")


def sh_blocks(text):
    return [block for info, block in FENCE.findall(text) if info == "sh"]


class GraphFixture(unittest.TestCase):
    def setUp(self):
        self.block = next(block for block in sh_blocks(REPORT.read_text())
                          if "fixture.gisel" in block)
        found = HEREDOC.search(self.block)
        self.assertEqual(found is not None, True, "REPORT-graph lost its fixture")
        self.source = found.group(2) + "\n"
        self.expectations = EXPECT.findall(self.block)
        self.assertEqual(len(self.expectations), 2,
                         "expected an rc/state/sha line per command")

    def replay(self, extra=()):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "fixture.gisel"
            src.write_text(self.source)
            run = subprocess.run(
                [sys.executable, "-m", "gisel", "graph", str(src),
                 "--config", "none", "--json", *extra],
                cwd=ROOT, capture_output=True, text=True)
            self.assertIn(run.returncode, (0, 1), run.stderr)
            # The report redirects stdout (`> fixture.json`); hash those bytes.
            return (run.returncode,
                    hashlib.sha256(run.stdout.encode()).hexdigest(),
                    json.loads(run.stdout))

    def test_the_plain_run_is_what_the_report_quotes(self):
        rc, digest, payload = self.replay()
        want = self.expectations[0]
        self.assertEqual((str(rc), digest), (want[0], want[4]))
        report = payload["reports"][0]
        self.assertEqual((report["states"], report["edges"], report["cycles"]),
                         tuple(int(x) for x in want[1:4]))

    def test_the_injected_edge_run_is_what_the_report_quotes(self):
        rc, digest, payload = self.replay(("--inject-edge",))
        want = self.expectations[1]
        self.assertEqual((str(rc), digest), (want[0], want[4]))
        report = payload["reports"][0]
        self.assertEqual((report["states"], report["edges"], report["cycles"]),
                         tuple(int(x) for x in want[1:4]))


class FrozenTable(unittest.TestCase):
    ROW = re.compile(r"^\|\s*C0\s*\|(.*)\|\s*$", re.M)

    def test_the_c0_row_is_the_frozen_golden(self):
        row = self.ROW.search(REPORT.read_text())
        self.assertIsNotNone(row, "REPORT-graph lost its C0 row")
        header = next(line for line in REPORT.read_text().splitlines()
                      if line.startswith("| config | states |"))
        names = [cell.strip() for cell in header.strip("|").split("|")]
        cells = [cell.strip() for cell in row.group(1).split("|")]
        quoted = {name: int(value.replace(",", ""))
                  for name, value in zip(names[1:], cells)
                  if name not in ("config", "closure")}
        report = json.loads(GOLDEN.read_text())["reports"][0]
        numbers = {
            "states": report["states"],
            "edges": report["edges"],
            "moves": report["outcomes"]["moves"],
            "no-rule": report["outcomes"]["no-rule"],
            "terminal": report["outcomes"]["terminal"],
            "opaque": report["opaque"],
            "outside": report["outside"],
            "shape": report["shape"],
            "classes": report["classes"],
            "cycles": report["cycles"],
        }
        for name, value in numbers.items():
            if name in quoted:
                self.assertEqual(quoted[name], value, name)


class InstructionLiterals(unittest.TestCase):
    def test_the_version_bump_example_has_no_literal(self):
        text = RELEASING.read_text()
        for info, block in FENCE.findall(text):
            with self.subTest(fence=info):
                self.assertNotRegex(block, r'__version__ = "\d')

    def test_the_doctor_sample_quotes_the_running_version(self):
        sys.path.insert(0, str(ROOT))
        import gisel
        text = QUICKSTART.read_text()
        found = re.findall(r"^version\s+ok\s+(\S+)$", text, re.M)
        self.assertEqual(len(found), 1, "QUICKSTART's doctor sample lost its version line")
        self.assertEqual(found[0], gisel.__version__,
                         "QUICKSTART quotes a version the package no longer is")


if __name__ == "__main__":
    unittest.main()
