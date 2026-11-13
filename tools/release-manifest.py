#!/usr/bin/env python3
"""Write RELEASE.json: the three-repo cohort and the artifacts it names.

    tools/release-manifest.py [--out PATH] [--cohort NAME]

Reads the sibling checkouts (`AB_SRC` / `UPSTREAM_SOURCE`, default
`../gisel-ab` and `../gisel-anchor`, falling back to the pre-rename `../ab`
and `../upstream-source`).  A manifest for a dirty worktree is a lie, so a
dirty repo is an error; commit first.

The manifest records commits, every corpus sha, the graph and case goldens,
and the frozen official base.  `repos.ab` is the commit *before* this
manifest: the manifest commit adds only RELEASE.json, so a manifest that
named its own commit could never be written.  It also refuses to record a
cohort whose consumers check out a different gisel than `HEAD`.

It does not tag or publish anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sibling(env, *names):
    """Resolve a sibling checkout: explicit env, then each name in order."""
    override = os.environ.get(env)
    if override:
        return Path(override)
    for name in names:
        path = ROOT.parent / name
        if path.is_dir():
            return path
    return ROOT.parent / names[0]


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args],
                                   text=True).strip()


def head(path):
    return git(path, "rev-parse", "HEAD")


def dirty(path):
    return bool(git(path, "status", "--porcelain"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def gisel_version():
    text = (ROOT / "gisel" / "__init__.py").read_text()
    match = re.search(r'__version__ = "([^"]+)"', text)
    if not match:
        raise SystemExit("release-manifest: no __version__ in gisel/__init__.py")
    return match.group(1)


def checkout_refs(path):
    """The gisel refs a consumer workflow checks out, in file order."""
    workflow = path / ".github" / "workflows" / "ci.yml"
    if not workflow.exists():
        return []
    refs = []
    repository = None
    for line in workflow.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("repository:"):
            repository = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("ref:") and repository == "nodecoda/gisel":
            refs.append((workflow, stripped.split(":", 1)[1].strip()))
        elif stripped.startswith("- ") or stripped.startswith("uses:"):
            repository = None
    return refs


def stale_refs(repos, gisel_commit):
    """Consumer workflows that check out a gisel other than `gisel_commit`."""
    stale = []
    for name, path in repos:
        for workflow, ref in checkout_refs(path):
            if ref != gisel_commit:
                stale.append("%s:%s checks out %s"
                             % (name, workflow.relative_to(path), ref[:12]))
    return stale


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
    parser.add_argument("--cohort", default="cohort-2026-11-13",
                        help="the tag this manifest will be frozen under")
    args = parser.parse_args(argv)

    ab = sibling("AB_SRC", "gisel-ab", "ab")
    upstream = sibling("UPSTREAM_SOURCE", "gisel-anchor", "upstream-source")
    for name, path in (("gisel-ab", ab), ("gisel-anchor", upstream)):
        if not (path / ".git").exists():
            return fail("%s is not a git checkout (%s)" % (name, path))

    repos = {"gisel": ROOT, "ab": ab, "upstream_source": upstream}
    dirty_repos = [name for name, path in repos.items() if dirty(path)]
    if dirty_repos:
        return fail("dirty worktree: %s" % ", ".join(sorted(dirty_repos)))

    gisel_commit = head(ROOT)
    stale = stale_refs((("gisel-ab", ab), ("gisel-anchor", upstream)),
                       gisel_commit)
    if stale:
        return fail("consumer CI does not pin gisel %s: %s"
                    % (gisel_commit[:12], "; ".join(stale)))

    pin = json.loads((upstream / "pin" / "PIN.json").read_text())
    corpus = {p.name: sha(p)
              for p in sorted((ROOT / "tests" / "corpus").glob("*.gisel"))}
    payload = {
        "schema": 1,
        "cohort": args.cohort,
        "version": gisel_version(),
        "note": "Commits are the code commits.  `repos.ab` is the commit "
                "before this manifest: the manifest commit adds only this "
                "file, so it cannot name itself.  Re-run the gates at those "
                "commits, not after.",
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
            "python3 scripts/import-cxx.py --all --pin pin/PIN.json --check",
            "scripts/pin/make-base.sh TREE DEST --verify",
            "gisel-ab/verify-evidence.sh",
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
