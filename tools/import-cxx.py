#!/usr/bin/env python3
"""Deprecated shim: the transcriber now lives in ``upstream-source``.

Kept for one release so existing commands keep working.  Set
``UPSTREAM_SOURCE`` to override the sibling checkout location.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = (Path(os.environ.get("UPSTREAM_SOURCE",
                             REPO.parent / "upstream-source"))
        / "import" / "import-cxx.py")


def main(argv):
    if not TOOL.exists():
        sys.stderr.write(
            "import-cxx moved to %s; set UPSTREAM_SOURCE or clone "
            "upstream-source next to gisel\n" % TOOL)
        return 2
    sys.stderr.write("warning: tools/import-cxx.py moved to %s\n" % TOOL)
    return subprocess.call([sys.executable, str(TOOL), *argv])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
