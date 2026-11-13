#!/usr/bin/env python3
"""Copy tests/corpus and tests/cases into the package data directory.

The checkout keeps the canonical corpus under `tests/` because frozen
artifacts record `tests/corpus/...` as the origin of every ruleset.  An
installed wheel needs the same files under `gisel/data/`, or `--corpus NAME`
cannot work without a checkout.

    tools/sync-package-data.py          # refresh the copies
    tools/sync-package-data.py --check  # rc=1 if the copies drifted

Copies are byte-identical; files deleted from `tests/` are deleted from the
package too, so a stale file cannot ride into a wheel.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    (ROOT / "tests" / "corpus", ROOT / "gisel" / "data" / "corpus", "*.gisel"),
    (ROOT / "tests" / "cases", ROOT / "gisel" / "data" / "cases", "*.json"),
    # The workbench's frozen-evidence check regenerates these .inc files; the
    # copies let it run from an installed wheel.  Only the top-level three:
    # the rest of tests/artifacts/ is build output, not an input.
    (ROOT / "tests" / "artifacts", ROOT / "gisel" / "data" / "artifacts", "*.inc"),
)


def check() -> int:
    bad = 0
    for src, dst, pattern in PAIRS:
        wanted = {path.name for path in src.glob(pattern)}
        for name in sorted(wanted):
            target = dst / name
            if not target.is_file():
                print("missing: %s" % target.relative_to(ROOT), file=sys.stderr)
                bad += 1
            elif target.read_bytes() != (src / name).read_bytes():
                print("differs: %s" % target.relative_to(ROOT), file=sys.stderr)
                bad += 1
        if dst.is_dir():
            for extra in sorted(dst.iterdir()):
                if extra.is_file() and extra.name not in wanted:
                    print("stale:   %s" % extra.relative_to(ROOT),
                          file=sys.stderr)
                    bad += 1
    if bad:
        print("%d file(s) out of sync; run tools/sync-package-data.py" % bad,
              file=sys.stderr)
        return 1
    print("package data: in sync")
    return 0


def sync() -> int:
    for src, dst, pattern in PAIRS:
        dst.mkdir(parents=True, exist_ok=True)
        wanted = {path.name for path in src.glob(pattern)}
        for name in sorted(wanted):
            (dst / name).write_bytes((src / name).read_bytes())
        for extra in sorted(dst.iterdir()):
            if extra.is_file() and extra.name not in wanted:
                extra.unlink()
                print("removed stale %s" % extra.relative_to(ROOT))
    print("package data: synced")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="compare instead of writing; rc=1 on drift")
    args = ap.parse_args(argv)
    return check() if args.check else sync()


if __name__ == "__main__":
    sys.exit(main())
