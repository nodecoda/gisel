"""The landing pages quote tool output; that quote must be the tool's output.

README's C++ block is a snapshot of `gen --emit=inc`.  Snapshots rot: the
emitter moved to public builders, and both READMEs kept quoting the `core*`
calls it used to print.  Regenerating the include from the page's own heredoc
and comparing line by line turns "the doc is stale" into a failing test.

The parity check is separate: README.zh.md is a translation of README.md, so a
section added on one side and not the other is drift too, and the two files
should keep the same shape even when the prose differs.
"""

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = [ROOT / "README.md", ROOT / "README.zh.md"]

FENCE = re.compile(r"```([A-Za-z0-9_+.-]*)\n(.*?)```", re.S)
HEREDOC = re.compile(r"cat > (\S+) <<'EOF'\n(.*?)\nEOF\n", re.S)
HEADING = re.compile(r"^(#{1,6}) ", re.M)


def fences(text):
    return [(match.group(1), match.group(2))
            for match in FENCE.finditer(text)]


def quoted_inc(path):
    """(demo source, quoted C++ block) for one landing page."""
    source = quoted = None
    for info, block in fences(path.read_text()):
        if info == "sh" and source is None:
            found = HEREDOC.search(block)
            if found and "hello.gisel" in found.group(1):
                source = found.group(2) + "\n"
        elif info == "cpp" and quoted is None:
            quoted = block
    return source, quoted


def generated_inc(source):
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "hello.gisel"
        out = Path(tmp) / "hello.inc"
        src.write_text(source)
        run = subprocess.run(
            [sys.executable, "-m", "gisel", "gen", str(src),
             "--emit=inc", "--out", str(out)],
            cwd=ROOT, capture_output=True, text=True)
        if run.returncode != 0:
            raise AssertionError(run.stdout + run.stderr)
        return out.read_text()


def commands(text):
    """Every command a reader runs, comments and line continuations removed."""
    out = []
    for info, block in fences(text):
        if info != "sh":
            continue
        pending = ""
        for line in block.splitlines():
            line = re.sub(r"\s+#.*$", "", line.rstrip())
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith("\\"):
                pending += line[:-1].strip() + " "
                continue
            out.append((pending + line).strip())
            pending = ""
    return out


def unmatched(quoted, emitted):
    """First quoted line the tool did not print, in order; None when all match."""
    remaining = iter(line.rstrip() for line in emitted.splitlines())
    for line in quoted.splitlines():
        wanted = line.rstrip()
        if not wanted.strip():
            continue
        for candidate in remaining:
            if candidate == wanted:
                break
        else:
            return wanted
    return None


class Quickstart(unittest.TestCase):
    def test_the_quoted_include_is_what_gen_prints(self):
        for page in PAGES:
            source, quoted = quoted_inc(page)
            with self.subTest(page=page.name):
                self.assertIsNotNone(source, "%s: no hello.gisel heredoc" % page.name)
                self.assertIsNotNone(quoted, "%s: no C++ block" % page.name)
                missing = unmatched(quoted, generated_inc(source))
                self.assertIsNone(
                    missing,
                    "%s quotes a line `gen --emit=inc` no longer prints: %r"
                    % (page.name, missing))

    def test_no_landing_page_quotes_a_core_builder(self):
        # The include compiles against an unmodified upstream header; a `core*`
        # call in the docs would tell readers the opposite.
        for page in PAGES:
            for info, block in fences(page.read_text()):
                if info not in ("cpp", "c++", "sh"):
                    continue
                with self.subTest(page=page.name, fence=info):
                    self.assertNotRegex(block, r"(?m)^\s*\.core[A-Z]")


class Parity(unittest.TestCase):
    def test_the_translation_keeps_the_shape_of_the_original(self):
        english, chinese = (page.read_text() for page in PAGES)
        self.assertEqual(
            [len(level) for level in HEADING.findall(english)],
            [len(level) for level in HEADING.findall(chinese)],
            "README.md and README.zh.md disagree on the heading skeleton")
        self.assertEqual(
            [info for info, _ in fences(english)],
            [info for info, _ in fences(chinese)],
            "README.md and README.zh.md disagree on the code blocks")
        # Comments are translated; the commands are not.
        self.assertEqual(commands(english), commands(chinese),
                         "README.zh.md runs different commands than README.md")


if __name__ == "__main__":
    unittest.main()
