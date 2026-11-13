#!/usr/bin/env python3
"""Deprecated shim: the inventory tool now lives in ``gisel-anchor`` (or the pre-rename ``upstream-source``)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _sibling(env, *names):
    override = os.environ.get(env)
    if override:
        return Path(override)
    for name in names:
        path = REPO.parent / name
        if path.is_dir():
            return path
    return REPO.parent / names[0]


TOOL = _sibling("UPSTREAM_SOURCE", "gisel-anchor", "upstream-source") \
    / "scripts" / "import-inventory.py"


def main(argv):
    if not TOOL.exists():
        sys.stderr.write(
            "import-inventory moved to %s; set UPSTREAM_SOURCE or clone "
            "gisel-anchor next to gisel\n" % TOOL)
        return 2
    sys.stderr.write("warning: tools/import-inventory.py moved to %s\n" % TOOL)
    return subprocess.call([sys.executable, str(TOOL), *argv])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
