"""Non-refined closure counts that the byte goldens do not cover.

`tests/artifacts/graph/*.json` pins X86-none, RISC-V rv64gc, and wasm32.
AArch64 baseline is the expensive one: the unrefined run takes about five
minutes, so it is opt-in with GS_SLOW=1.  The count is not a cosmetic number:
it is the size of the partition gap that `--refine` has to close before
"cycles=0" can be signed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNTS = json.loads(
    (ROOT / "tests/artifacts/closure-counts.json").read_text())["counts"]


def run(name, args, expected, slow=False):
    if slow and os.environ.get("GS_SLOW") != "1":
        raise unittest.SkipTest("set GS_SLOW=1 for the %s closure run" % name)
    found = subprocess.run(
        [sys.executable, "-m", "gisel", "graph", *args, "--json"],
        cwd=ROOT, capture_output=True, text=True)
    if found.returncode not in (0, 1):
        raise AssertionError("%s: rc=%d\n%s"
                             % (name, found.returncode, found.stderr[-800:]))
    report = json.loads(found.stdout)["reports"][0]
    closure = report["closure"]
    if closure["count"] != expected:
        raise AssertionError("%s: closure.count=%d, recorded %d"
                             % (name, closure["count"], expected))
    if report["cycles"]:
        raise AssertionError("%s: cycles=%d" % (name, report["cycles"]))


class ClosureCounts(unittest.TestCase):
    def test_wasm32(self):
        run("wasm32",
            ["tests/corpus/WebAssemblyLegalizerInfo.gisel",
             "--features", "tests/cases/wasm-features.json",
             "--config", "wasm32"],
            COUNTS["wasm32"])

    def test_aarch64_baseline(self):
        run("aarch64-baseline",
            ["tests/corpus/AArch64LegalizerInfo.gisel",
             "--features", "tests/cases/features.json",
             "--config", "baseline"],
            COUNTS["aarch64-baseline"], slow=True)


if __name__ == "__main__":
    unittest.main()
