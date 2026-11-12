"""Stable query/answer JSONL API for consumers outside this package.

The A/B workbench imports **this module and nothing else** from gisel.  It is
the contract behind ``spec/cases-format.md``: key construction, answer rows,
LLT text, value equality, the feature table loader, and the one reader for
query/answer files.

The file boundary and the row boundary are separate:

* :func:`read_rows` owns files: blank lines, bad lines (``file:line``),
  duplicate keys, and the strict/lenient choice.
* :func:`parse_query` / :func:`parse_answer` own one row: field names, types,
  and the LLT spelling.  ``eval.prepare_query`` uses these, not its own IO.

Internal modules (``gisel.cases``, ``gisel.eval``) may change; this surface
changes only with a schema-version bump, and the workbench pins it with a
contract test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .eval import EvalError, Features, load_features, values_equal
from .eval import fmt_oracle_llt, collapse_extended, parse_case_llt
from .eval import parse_answer_row, parse_query_row
from .llt import spell as llt_text

# Row-level aliases: the file boundary calls these too.
parse_query = parse_query_row
parse_answer = parse_answer_row

__all__ = [
    "JsonlError",
    "Row",
    "answer",
    "key",
    "load",
    "read_rows",
    "parse_query",
    "parse_answer",
    "parse_type",
    "format_type",
    "format_oracle_type",
    "make_query",
    "make_answer",
    "llt_text",
    "EvalError",
    "Features",
    "load_features",
    "values_equal",
]


class JsonlError(ValueError):
    """A bad or conflicting JSONL row, named by file and line."""

    def __init__(self, path, line, message):
        self.path = str(path)
        self.line = int(line)
        self.message = message
        super().__init__("%s:%d: %s" % (self.path, self.line, message))


@dataclass(frozen=True)
class Row:
    """One parsed row: the raw dict, its key, and its answer (or None)."""

    path: str
    line: int
    raw: dict
    key: tuple
    answer: tuple | None


def parse_type(text, *, extended=True):
    """Parse a Core IR or LLT::print spelling and optionally collapse kinds."""
    if not isinstance(text, str) or not text:
        raise EvalError("bad_llt", "LLT must be a non-empty string")
    value = parse_case_llt(text)
    return value if extended else collapse_extended(value)


def format_type(value):
    """The Core IR spelling accepted by :func:`parse_type`."""
    return llt_text(value)


def format_oracle_type(value):
    """The ``LLT::print`` spelling used by answer files."""
    return fmt_oracle_llt(value)


def key(row):
    """The structural key of a query/answer row (the A/B contract)."""
    parsed = parse_query_row(row, require=False)
    return (parsed["config"], parsed["name"], parsed["types"],
            parsed["mem"], parsed["imms"])


def answer(row):
    """The answer tuple of an answer row."""
    return parse_answer_row(row)


def _looks_like_answer(row, answers):
    if answers is not None:
        return answers
    return "action" in row or "status" in row


def read_rows(path, *, strict=True, answers=None):
    """Read a JSONL file into :class:`Row` values.

    Returns ``(rows, errors)``.  With ``strict=True`` the first bad line or
    conflicting duplicate raises :class:`JsonlError` and no partial result is
    returned.  With ``strict=False`` the same condition becomes an entry in
    ``errors`` and the rows that did parse are returned; callers must treat a
    non-empty error list as a failure before using the rows.

    An identical duplicate key with an identical answer is merged.  The same
    key with a different answer is an error: one of the two rows would
    otherwise be silently dropped.
    """
    path = str(path)
    rows = []
    errors = []
    seen = {}
    with open(path) as stream:
        for lineno, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                parsed = parse_query_row(raw)
                row_key = (parsed["config"], parsed["name"], parsed["types"],
                           parsed["mem"], parsed["imms"])
                row_answer = (parse_answer_row(raw)
                              if _looks_like_answer(raw, answers) else None)
            except (ValueError, KeyError, TypeError, EvalError) as exc:
                error = JsonlError(path, lineno, str(exc))
                if strict:
                    raise error from exc
                errors.append(error)
                continue
            if row_key in seen:
                if seen[row_key].answer != row_answer:
                    error = JsonlError(
                        path, lineno,
                        "conflicting duplicate key %r" % (row_key,))
                    if strict:
                        raise error
                    errors.append(error)
                continue
            row = Row(path, lineno, raw, row_key, row_answer)
            seen[row_key] = row
            rows.append(row)
    return rows, errors


def load(path, *, strict=False):
    """Read an answer file into ``(key -> answer, error count)``.

    Kept for the historical ``answers.load`` API.  Errors are written to
    stderr, exactly like the old reader, and a non-empty count means the
    caller must fail.
    """
    import sys

    rows, errors = read_rows(path, strict=strict)
    for error in errors:
        print(error, file=sys.stderr)
    return {row.key: row.answer for row in rows}, len(errors)


def _spell(value):
    return value if isinstance(value, str) else format_type(value)


def make_query(config, name, types, mem=None, imms=()):
    """Build a query row with canonical Core IR spellings."""
    row = {"config": config, "name": name,
           "types": [_spell(value) for value in types],
           "mem": None, "imms": [int(value) for value in imms]}
    if mem is not None:
        row["mem"] = ([_spell(mem[0]), int(mem[1])]
                      + [str(value) for value in mem[2:4]])
    return row


def make_answer(config, name, types, action, *, type_idx=0,
                new_type="LLT_invalid", mem=None, imms=()):
    """Build an answer row that round-trips through :func:`answer`."""
    row = make_query(config, name, types, mem=mem, imms=imms)
    row.update({"action": action, "type_idx": int(type_idx),
                "new_type": _spell(new_type)})
    return row
