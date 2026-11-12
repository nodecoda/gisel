"""The four JSONL readers share one codec.

`answers.load`, `cases.index_oracle`, `graph.oracle_check` and
`eval.prepare_query` used to implement four different duplicate-key and bad-line
policies.  These tests pin the one they now share.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from gisel import answers, cases, eval as E, graph, jsonl


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


class ReadersAgree(unittest.TestCase):
    def test_the_four_readers_share_keys_and_normalisation(self):
        path = write([answer_row(), answer_row("G_SUB", types=("s64",),
                                               action="WidenScalar",
                                               new_type="s64")])
        rows, errors = jsonl.read_rows(path)
        self.assertEqual(errors, [])

        loaded, load_errors = answers.load(path)
        self.assertEqual(load_errors, 0)
        self.assertEqual(set(loaded), {row.key for row in rows})

        indexed = cases.index_oracle(path)
        self.assertEqual(set(indexed), {row.key for row in rows})

        # `graph.oracle_check` reads the same file; with no states it counts
        # every point as uncovered but still parses every row.
        report = SimpleNamespace(config="C0", class_tables=None, states={})
        result = graph.oracle_check(report, str(path), None, True)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["uncovered"], 2)

        # `eval.prepare_query` uses the row codec, not its own `q[...]` access.
        parsed = E.parse_query_row(query())
        types, mems, imms, _collapse = E.prepare_query(
            SimpleNamespace(extended=lambda config: True), query())
        self.assertEqual(tuple(types), parsed["types"])
        self.assertEqual(tuple(imms), parsed["imms"])
        self.assertEqual(mems, [])

    def test_graph_oracle_check_rejects_a_bad_line(self):
        path = write([answer_row()])
        with open(path, "a") as stream:
            stream.write("{oops}\n")
        report = SimpleNamespace(config="C0", class_tables=None, states={})
        with self.assertRaises(jsonl.JsonlError):
            graph.oracle_check(report, str(path), None, True)

    def test_cases_index_oracle_rejects_a_conflicting_duplicate(self):
        path = write([answer_row(),
                      answer_row(action="Lower")])
        with self.assertRaises(jsonl.JsonlError):
            cases.index_oracle(path)
