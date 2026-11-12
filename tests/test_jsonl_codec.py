"""The JSONL boundary is a codec: files and rows are separate layers.

`spec/cases-format.md` already defines the policy: a duplicate with the same
answer merges, a duplicate with a different answer is an error, and a bad line
carries `file:line`.  These tests pin the codec; the four readers that used to
implement their own policy are pinned in `test_jsonl_readers.py`.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gisel import eval as E, jsonl


def query(name="G_ADD", types=("s32",), config="C0", mem=None, imms=None):
    row = {"config": config, "name": name, "types": list(types)}
    if mem is not None:
        row["mem"] = mem
    if imms is not None:
        row["imms"] = imms
    return row


def answer_row(name="G_ADD", types=("s32",), action="Legal",
               new_type="LLT_invalid", config="C0", type_idx=0):
    row = query(name, types, config)
    row.update({"action": action, "type_idx": type_idx, "new_type": new_type})
    return row


def write(rows):
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    with handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return Path(handle.name)


class TypeSpelling(unittest.TestCase):
    def test_core_spelling_round_trips(self):
        for text in ("s32", "i32", "f64", "bf16", "p0:*", "p0:64",
                     "v4s32", "nxv4s32", "LLT_invalid"):
            with self.subTest(text=text):
                self.assertEqual(jsonl.format_type(jsonl.parse_type(text)), text)

    def test_oracle_spelling_is_accepted_and_normalised(self):
        self.assertEqual(jsonl.format_type(jsonl.parse_type("<4 x s32>")),
                         "v4s32")
        self.assertEqual(
            jsonl.format_type(jsonl.parse_type("<vscale x 4 x s32>")),
            "nxv4s32")
        self.assertEqual(jsonl.format_type(jsonl.parse_type("p0")), "p0:64")
        self.assertEqual(jsonl.format_oracle_type(
            jsonl.parse_type("p0:*")), "p0")

    def test_extended_false_collapses_kinds(self):
        self.assertEqual(jsonl.parse_type("i32", extended=False),
                         ("scalar", 32))
        self.assertEqual(jsonl.parse_type("bf16", extended=False),
                         ("scalar", 16))
        self.assertEqual(jsonl.parse_type("p0:*", extended=False),
                         ("pointer", 0, "*"))


class QuerySchema(unittest.TestCase):
    def test_missing_config_and_name_are_errors(self):
        with self.assertRaises(E.EvalError):
            jsonl.parse_query({"name": "G_ADD", "types": ["s32"]})
        with self.assertRaises(E.EvalError):
            jsonl.parse_query({"config": "C0", "types": ["s32"]})

    def test_types_must_be_an_array_of_strings(self):
        with self.assertRaises(E.EvalError):
            jsonl.parse_query({"config": "C0", "name": "G_ADD",
                               "types": "s32"})
        with self.assertRaises(E.EvalError):
            jsonl.parse_query({"config": "C0", "name": "G_ADD",
                               "types": [32]})

    def test_mem_is_null_or_two_or_four_elements(self):
        with self.assertRaises(E.EvalError):
            jsonl.parse_query(query(mem=["s64"]))
        with self.assertRaises(E.EvalError):
            jsonl.parse_query(query(mem=["s64", "8"]))
        parsed = jsonl.parse_query(query(mem=["s64", 8]))
        self.assertEqual(parsed["mem"],
                         (("scalar", 64), 8, "NotAtomic", "NotAtomic"))

    def test_imms_must_be_integers(self):
        with self.assertRaises(E.EvalError):
            jsonl.parse_query(query(imms=["0"]))
        self.assertEqual(jsonl.parse_query(query(imms=[0, 1]))["imms"], (0, 1))

    def test_tolerant_mode_keeps_the_key_contract(self):
        parsed = jsonl.parse_query({"types": ["s32"]}, require=False)
        self.assertIsNone(parsed["config"])
        self.assertIsNone(parsed["name"])
        self.assertEqual(parsed["types"], (("scalar", 32),))


class AnswerSchema(unittest.TestCase):
    def test_unanswerable_is_not_an_action(self):
        row = query()
        row.update({"status": "unanswerable", "reason": "no rule"})
        self.assertEqual(jsonl.parse_answer(row), ("unanswerable", "no rule"))

    def test_action_and_type_idx_are_checked(self):
        with self.assertRaises(E.EvalError):
            jsonl.parse_answer({"status": "answered", "type_idx": 0})
        with self.assertRaises(E.EvalError):
            jsonl.parse_answer({"action": "Legal", "type_idx": "0"})

    def test_missing_new_type_is_invalid(self):
        self.assertEqual(jsonl.parse_answer({"action": "Lower"}),
                         ("answered", "Lower", 0, ("invalid",)))


class Reader(unittest.TestCase):
    def test_bad_line_names_file_and_line_and_returns_nothing(self):
        path = write([answer_row(), answer_row("G_SUB", types=("s64",))])
        with open(path, "a") as stream:
            stream.write("{not json}\n")
        with self.assertRaises(jsonl.JsonlError) as caught:
            jsonl.read_rows(path)
        self.assertEqual(caught.exception.line, 3)
        self.assertIn(str(path), str(caught.exception))
        self.assertIn(":3:", str(caught.exception))

    def test_non_strict_returns_partial_rows_and_errors(self):
        path = write([answer_row(), {"config": "C0"}])
        rows, errors = jsonl.read_rows(path, strict=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(errors), 1)

    def test_identical_duplicate_merges_and_conflict_is_an_error(self):
        same = write([answer_row(), answer_row()])
        rows, errors = jsonl.read_rows(same, strict=False)
        self.assertEqual((len(rows), len(errors)), (1, 0))

        different = write([answer_row(),
                           answer_row(action="WidenScalar", new_type="s64")])
        with self.assertRaises(jsonl.JsonlError):
            jsonl.read_rows(different)
        rows, errors = jsonl.read_rows(different, strict=False)
        self.assertEqual((len(rows), len(errors)), (1, 1))

    def test_answerless_queries_are_rows_too(self):
        path = write([query(), query(name="G_SUB")])
        rows, errors = jsonl.read_rows(path)
        self.assertEqual((len(rows), len(errors)), (2, 0))
        self.assertIsNone(rows[0].answer)


if __name__ == "__main__":
    unittest.main()
