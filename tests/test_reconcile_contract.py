"""The reconciliation tool: crash contract must be a subset of unanswerable."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "reconcile-contract.py"


def row(name, types, **extra):
    base = {"config": "C0", "name": name, "types": types, "mem": None,
            "imms": [], "action": "Legal", "type_idx": 0,
            "new_type": "LLT_invalid"}
    base.update(extra)
    return base


QUERIES = [
    row("G_EXTRACT_VECTOR_ELT", ["s32", "s32", "s32"]),      # crashes
    row("G_EXTRACT_VECTOR_ELT", ["s32", "v2s32", "s32"]),    # real MIR
    row("G_EXTRACT_VECTOR_ELT", ["v2s32", "v2s32", "s32"]),  # verifier only
    row("G_CTPOP", ["f32", "f32"]),                          # verifier only
    row("G_ADD", ["s32", "s32"]),                            # fine
]


def write(path, rows):
    with open(path, "w") as stream:
        for r in rows:
            stream.write(json.dumps(r) + "\n")


class Reconcile(unittest.TestCase):
    def run_tool(self, queries, answers):
        tmp = tempfile.mkdtemp(prefix="ab-reconcile-")
        q = Path(tmp) / "queries.jsonl"
        a = Path(tmp) / "answers.jsonl"
        write(q, queries)
        write(a, answers)
        done = subprocess.run(
            [sys.executable, str(TOOL), str(q), str(a), "--json"],
            capture_output=True, text=True)
        return done, json.loads(done.stdout) if done.stdout else {}

    def answers(self, *unanswerable):
        out = []
        for index, query in enumerate(QUERIES):
            if index in unanswerable:
                extra = {"status": "unanswerable", "reason": "asserted"}
                if index == 0:
                    extra["assert_site"] = "LowLevelType.h:511"
                out.append(dict(query, **extra))
            else:
                out.append(query)
        return out

    def test_crash_contract_is_a_subset_of_unanswerable(self):
        done, report = self.run_tool(QUERIES, self.answers(0, 3))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(report["predicted_crash"], 1)
        self.assertEqual(report["observed"], 2)
        self.assertEqual(report["crash_minus_observed"], 0)
        self.assertEqual(report["observed_minus_crash"], 1)
        self.assertEqual(report["observed_minus_crash_by_opcode"], {"G_CTPOP": 1})
        self.assertEqual(report["predicted_verifier"], 3)
        self.assertEqual(report["verifier_minus_observed"], 1)
        self.assertEqual(report["sites"], {"LowLevelType.h:511": 1})

    def test_predicted_crash_that_answered_fails(self):
        done, report = self.run_tool(QUERIES, self.answers(3))
        self.assertEqual(done.returncode, 1)
        self.assertEqual(report["crash_minus_observed"], 1)

    def test_missing_answer_fails(self):
        done, report = self.run_tool(QUERIES, self.answers(0, 3)[:-1])
        self.assertEqual(done.returncode, 1)
        self.assertEqual(report["missing_answers"], 1)

    def test_duplicate_query_key_is_rejected(self):
        done, _ = self.run_tool(QUERIES + [QUERIES[0]], self.answers())
        self.assertEqual(done.returncode, 2)


if __name__ == "__main__":
    unittest.main()
