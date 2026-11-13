#!/usr/bin/env python3
"""Deprecated shim: the inventory tool now lives in ``upstream-source``."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = (Path(os.environ.get("UPSTREAM_SOURCE",
                             REPO.parent / "upstream-source"))
        / "importer" / "import-inventory.py")


def main(argv):
    if not TOOL.exists():
        sys.stderr.write(
            "import-inventory moved to %s; set UPSTREAM_SOURCE or clone "
            "upstream-source next to gisel\n" % TOOL)
        return 2
    sys.stderr.write("warning: tools/import-inventory.py moved to %s\n" % TOOL)
    return subprocess.call([sys.executable, str(TOOL), *argv])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
