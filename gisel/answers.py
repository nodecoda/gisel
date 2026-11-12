"""Compatibility facade for the JSONL reader.

The implementation moved to :mod:`gisel.jsonl` so the four readers share one
policy; this module keeps the internal ``gisel.answers`` import path working.
"""

from __future__ import annotations

from .jsonl import answer, key, load

__all__ = ["answer", "key", "load"]
