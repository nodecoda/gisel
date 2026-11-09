"""The SCOPE boundary, enforced.

`docs/SCOPE.md` says what belongs to gisel and what belongs to the workbench;
`spec/cli.md` §3 says a gisel run never starts another program, opens no
socket and reads no file it was not given.  These tests keep both statements
true while the package grows.
"""

import ast
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "gisel"
SPEC_CLI = ROOT / "spec" / "cli.md"

# Modules that would make "no external program, no network" false.
FORBIDDEN_IMPORTS = {
    "asyncio", "ftplib", "http", "imaplib", "multiprocessing",
    "smtplib", "socket", "subprocess", "telnetlib", "urllib",
}
FORBIDDEN_CALLS = {
    "os.system", "os.popen",
    "os.execv", "os.execl", "os.execvp", "os.spawnv", "os.spawnl",
}
# The dependency direction is workbench -> library, never the reverse.
FORBIDDEN_INTERNAL = {"tools", "tests", "docs"}


def modules():
    for path in sorted(PACKAGE.rglob("*.py")):
        yield path, ast.parse(path.read_text(), filename=str(path))


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


class NoExternalSideEffects(unittest.TestCase):
    def test_no_process_or_network_import(self):
        found = []
        for path, tree in modules():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                for name in names:
                    if name in FORBIDDEN_IMPORTS:
                        found.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}")
        self.assertEqual(found, [], "gisel must stay pure Python over files")

    def test_no_process_call(self):
        found = []
        for path, tree in modules():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = dotted(node.func)
                    if name in FORBIDDEN_CALLS:
                        found.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}")
        self.assertEqual(found, [], "gisel must not spawn programs")

    def test_library_never_imports_the_workbench(self):
        found = []
        for path, tree in modules():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                for name in names:
                    if name in FORBIDDEN_INTERNAL:
                        found.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}")
        self.assertEqual(found, [], "tools/ imports gisel, not the other way round")


class WorkbenchBoundary(unittest.TestCase):
    """A/B comparison is done *with* gisel, not by gisel (docs/SCOPE.md §2)."""

    def test_the_package_does_not_compare_implementations(self):
        from gisel import answers
        self.assertFalse(hasattr(answers, "compare"),
                         "the full-set comparison belongs to tools/ab/diff.py")

    def test_the_workbench_owns_the_comparison(self):
        text = (ROOT / "tools" / "ab" / "diff.py").read_text()
        self.assertIn("def compare(", text)


class BundledData(unittest.TestCase):
    """The wheel ships snapshots of LLVM tables; each must name its origin."""

    def test_every_table_declares_schema_and_source(self):
        for path in sorted((PACKAGE / "data").glob("*.json")):
            doc = json.loads(path.read_text())
            with self.subTest(table=path.name):
                self.assertIn("schema", doc)
                self.assertIn("source", doc)

    def test_opcode_slots_name_the_source_revision(self):
        doc = json.loads((PACKAGE / "data" / "opcode-slots.json").read_text())
        self.assertRegex(doc.get("source_commit", ""), r"^[0-9a-f]{40}$")


class Packaging(unittest.TestCase):
    def test_only_the_package_is_wheel_content(self):
        text = (ROOT / "pyproject.toml").read_text()
        include = re.search(r'^include\s*=\s*\[(.*)\]\s*$', text, re.M)
        self.assertIsNotNone(include, "pyproject has no explicit package list")
        names = [part.strip().strip('"\'') for part in include.group(1).split(",")]
        self.assertEqual(names, ["gisel*"], names)


class License(unittest.TestCase):
    def test_spdx_expression_and_the_file_ship(self):
        text = (ROOT / "pyproject.toml").read_text()
        # PEP 639: an SPDX expression, and the file in the wheel.  The old
        # `license = {file = "LICENSE"}` form dumped the whole text into the
        # metadata and shipped no license file at all.
        self.assertIn('license = "Apache-2.0 WITH LLVM-exception"', text)
        self.assertIn('license-files = ["LICENSE"]', text)
        self.assertNotIn("license = {file", text)


class EmitIsTheProductSurface(unittest.TestCase):
    """`--emit` names the artifacts the product still ships.

    `table` was removed on 2026-11-09.  Four hand-written places used to list
    it (the CLI choices, CI, RELEASING.md, spec/cli.md); this test keeps them
    from drifting apart again.
    """

    def test_the_three_backends(self):
        from gisel.cli import BACKENDS
        self.assertEqual(set(BACKENDS), {"inc", "check", "core"})

    def test_no_workflow_still_generates_a_table(self):
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertNotIn("--emit=table", text)
        self.assertNotIn(".table.inc", text)

    def test_the_cli_contract_lists_three_products(self):
        text = SPEC_CLI.read_text()
        self.assertNotIn("`--emit` 的四个值", text)
        self.assertIn("`--emit` 的三个值", text)


class SpecMatchesCommands(unittest.TestCase):
    """`spec/cli.md` is normative, so its table must equal the real surface."""

    def test_command_table_is_the_cli(self):
        from gisel.cli import COMMANDS as implemented
        table = set(re.findall(r"^\| `([a-z]+)` \|", SPEC_CLI.read_text(), re.M))
        self.assertEqual(table, set(implemented))


if __name__ == "__main__":
    unittest.main()
