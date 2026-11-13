"""Every verb named in the docs exists; every relative doc link resolves.

This is a drift gate, not a style check: the landing page and cookbook are
the first thing a reader runs, so a renamed verb or a moved file must fail
here before it fails in someone's terminal.
"""

import importlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "README.zh.md"] + sorted(
    (ROOT / "docs").glob("*.md"))
# Historical reports may quote commands that no longer exist; only the
# entry-point documents are a promise to the reader.
ENTRY_DOCS = [ROOT / "README.md", ROOT / "README.zh.md"] + [
    ROOT / "docs" / name for name in (
        "OVERVIEW-zh.md", "COOKBOOK-zh.md", "QUICKSTART-no-llvm.md",
        "LOOP.md", "SCOPE.md")]


def _verbs(package, attr):
    try:
        module = importlib.import_module(package)
    except ImportError:
        return None
    return set(getattr(module, attr))


FENCE = re.compile(r"```[a-z]*\n(.*?)```", re.S)
COMMAND = re.compile(r"^(?:python3 -m |\./)?(gisel(?:-ab|-anchor)?)\s+([a-z][a-z-]*)")


def _commands(path):
    for block in FENCE.findall(path.read_text()):
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = COMMAND.match(line)
            if match:
                yield match.group(1), match.group(2)


class Verbs(unittest.TestCase):
    def test_commands_in_code_fences_exist(self):
        known = {
            "gisel": _verbs("gisel.cli", "COMMANDS"),
            "gisel-ab": _verbs("gisel_ab.cli", "VERBS"),
            "gisel-anchor": _verbs("gisel_anchor.cli", "VERBS"),
        }
        for path in ENTRY_DOCS:
            for tool, verb in _commands(path):
                if known[tool] is None:
                    continue
                with self.subTest(path=path.name, tool=tool, verb=verb):
                    self.assertIn(verb, known[tool])


class Links(unittest.TestCase):
    def test_relative_markdown_links_resolve(self):
        pattern = re.compile(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)")
        for path in DOCS:
            for target in pattern.findall(path.read_text()):
                if "://" in target:
                    continue
                with self.subTest(path=path.name, target=target):
                    self.assertTrue((path.parent / target).is_file(),
                                    "%s -> %s" % (path.name, target))


if __name__ == "__main__":
    unittest.main()
