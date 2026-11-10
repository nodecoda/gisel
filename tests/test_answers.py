"""Answer files: the reader, which is all gisel owns.

`gisel.answers` only reads answer JSONL — `cases --queries`/`--oracle` needs
that.  The full-set comparison, its report and its exit codes belong to the
`ab` project: comparing two implementations is done *with* gisel, not by
gisel (`docs/SCOPE.md` §7).
"""

import json
import tempfile
import unittest

from gisel import answers


def row(name, types, action="Legal", new_type="LLT_invalid", config="C0"):
    return {"config": config, "name": name, "types": types, "mem": None,
            "imms": [], "action": action, "type_idx": 0, "new_type": new_type}


def write(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in rows:
        f.write(json.dumps(r) + "\n")
    f.close()
    return f.name


class Reader(unittest.TestCase):
    """`gisel.answers` is a reader; it does not compare."""

    def test_identical_duplicate_is_merged(self):
        path = write([row("G_ADD", ["s32"]), row("G_ADD", ["s32"])])
        got, errors = answers.load(path)
        self.assertEqual((len(got), errors), (1, 0))

    def test_conflicting_duplicate_is_an_error(self):
        path = write([row("G_ADD", ["s32"]),
                      row("G_ADD", ["s32"], "WidenScalar", "s64")])
        got, errors = answers.load(path)
        self.assertEqual((len(got), errors), (1, 1))


if __name__ == "__main__":
    unittest.main()
