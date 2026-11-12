#!/usr/bin/env python3
"""Write RELEASE.json: the three-repo cohort and the artifacts it names.

    tools/release-manifest.py [--out PATH]

Reads the sibling checkouts (`AB_SRC` / `UPSTREAM_SOURCE`, default `../ab`
and `../upstream-source`).  A manifest for a dirty worktree is a lie, so a
dirty repo is an error; commit first.

The manifest records commits, every corpus sha, the graph and case goldens,
and the frozen official base.  It does not tag or publish anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args],
                                   text=True).strip()


def head(path):
    return git(path, "rev-parse", "HEAD")


def dirty(path):
    return bool(git(path, "status", "--porcelain"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest_file(path):
    rows = {}
    for line in path.read_text().splitlines():
        if line.strip():
            digest, name = line.split()
            rows[name] = digest
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="default: $AB_SRC/RELEASE.json")
    args = parser.parse_args(argv)

    ab = Path(os.environ.get("AB_SRC", ROOT.parent / "ab"))
    upstream = Path(os.environ.get(
        "UPSTREAM_SOURCE", ROOT.parent / "upstream-source"))
    for name, path in (("ab", ab), ("upstream-source", upstream)):
        if not (path / ".git").exists():
            return fail("%s is not a git checkout (%s)" % (name, path))

    repos = {"gisel": ROOT, "ab": ab, "upstream_source": upstream}
    dirty_repos = [name for name, path in repos.items() if dirty(path)]
    if dirty_repos:
        return fail("dirty worktree: %s" % ", ".join(sorted(dirty_repos)))

    pin = json.loads((upstream / "pin" / "PIN.json").read_text())
    corpus = {p.name: sha(p)
              for p in sorted((ROOT / "tests" / "corpus").glob("*.gisel"))}
    payload = {
        "schema": 1,
        "cohort": "v0.3.0",
        "note": "Commits are the code commits; the release tag adds only this "
                "manifest.  Re-run the gates at those commits, not after.",
        "repos": {name: head(path) for name, path in repos.items()},
        "pin": {
            "commit": pin["commit"],
            "official_base_files": pin["official_base"]["files"],
        },
        "corpus_sha256": corpus,
        "cases_sha256": manifest_file(
            ROOT / "tests" / "artifacts" / "cases" / "SHA256"),
        "graph_goldens_sha256": {
            p.name: sha(p)
            for p in sorted((ROOT / "tests" / "artifacts" / "graph").glob("*.json"))
        },
        "nightly_graphs_sha256": manifest_file(
            ROOT / "tests" / "artifacts" / "graph" / "nightly" / "SHA256"),
        "gates": [
            "python3 -m unittest discover -q -s tests",
            "bash tools/check-nine-corpora.sh",
            "bash tools/check-graph-golden.sh",
            "bash tools/check-cases-golden.sh",
            "bash tools/check-nightly-graphs.sh",
            "python3 tools/check-claims.py",
            "python3 import/import-cxx.py --all --pin pin/PIN.json --check",
            "pin/make-base.sh TREE DEST --verify",
            "ab/verify-evidence.sh",
        ],
    }
    out = Path(args.out) if args.out else ab / "RELEASE.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("release manifest: %s (%d corpora, %d graph goldens)"
          % (out, len(corpus), len(payload["graph_goldens_sha256"])))
    for name, commit in sorted(payload["repos"].items()):
        print("  %-16s %s" % (name, commit))
    return 0


def fail(message):
    print("release-manifest: %s" % message, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
