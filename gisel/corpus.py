"""Bundled corpora: one target name in, a source plus features/axes out.

`tests/corpus` and `tests/cases` in the checkout are canonical; the copies
under `gisel/data/` make an installed wheel usable without a checkout.
`tools/sync-package-data.py` refreshes the copies and
`tests/test_package_data.py` fails if they drift.

The CLIs accept ``--corpus NAME`` so a reader who only has the wheel can run
``gisel cases --corpus x86`` instead of assembling two paths by hand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
MANIFEST = DATA / "corpora.json"


class CorpusError(ValueError):
    """An unknown name, a bad manifest, or a missing bundled file."""


@dataclass(frozen=True)
class Corpus:
    name: str
    source: Path
    features: Path | None
    axes: Path | None


def _manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text())
    except FileNotFoundError:
        raise CorpusError("bundled corpus manifest is missing: %s" % MANIFEST)
    except json.JSONDecodeError as exc:
        raise CorpusError("bad %s: %s" % (MANIFEST, exc))


def names() -> list[str]:
    return sorted(_manifest().get("targets", {}))


def _path(value: str | None) -> Path | None:
    if not value:
        return None
    path = DATA / value
    if not path.is_file():
        raise CorpusError("bundled file is missing: %s" % path)
    return path


def get(name: str) -> Corpus:
    targets = _manifest().get("targets", {})
    if name not in targets:
        raise CorpusError("unknown corpus %r (choose from: %s)"
                          % (name, ", ".join(names())))
    entry = targets[name]
    return Corpus(name=name, source=_path(entry["corpus"]),
                  features=_path(entry.get("features")),
                  axes=_path(entry.get("axes")))
