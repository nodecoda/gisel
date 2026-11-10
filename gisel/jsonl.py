"""Stable query/answer JSONL API for consumers outside this package.

The A/B workbench imports **this module and nothing else** from gisel.  It is
the contract behind ``spec/cases-format.md``: key construction, answer rows,
LLT text, value equality, and the feature table loader.  Internal modules
(``gisel.cases``, ``gisel.eval``) may change; this surface changes only with a
schema-version bump, and the workbench pins it with a contract test.
"""

from __future__ import annotations

from .answers import answer, key, load
from .llt import spell as llt_text
from .eval import EvalError, Features, load_features, values_equal

__all__ = [
    "answer",
    "key",
    "load",
    "llt_text",
    "EvalError",
    "Features",
    "load_features",
    "values_equal",
]
