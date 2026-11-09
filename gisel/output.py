"""The file boundary shared by the CLI verbs.

`spec/cli.md` §2 gives one exit code to "cannot start", and a path that cannot
be created or written is exactly that.  Verbs must not leak a traceback for a
bad `--out`; they print `<path>: <strerror>` and return 2, the same shape
`gisel gen` already uses.
"""

from __future__ import annotations

import sys
from pathlib import Path


def write_lines(path, lines):
    """Write `lines` to `path`, creating the parent directory.

    Returns 0 on success and 2 on an `OSError`, with the message on stderr.
    A partially written file is left in place: the caller already has the
    error, and truncating it again could destroy the only copy of a prefix.
    """
    try:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as stream:
            for line in lines:
                stream.write(line)
    except OSError as exc:
        print("%s: %s" % (path, exc.strerror or exc), file=sys.stderr)
        return 2
    return 0


def write_text(path, text):
    return write_lines(path, (text,))
