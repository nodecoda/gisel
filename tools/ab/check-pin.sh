#!/usr/bin/env bash
set -euo pipefail

# check-pin.sh TREE [PIN]
#
# The official side of the A/B harness is not bare upstream: it is the pin
# commit plus the unmerged PRs listed in PIN.json `patches`.  The corpus
# deliberately encodes the post-patch behaviour (see the deviations in
# upstream-source/import/import-cxx.py), so a tree that lacks one of those commits makes the
# official runner answer with pre-patch rules and every covered query shows up
# as a disagreement that looks like a translation error.
#
# Refuse that tree up front instead.  Both halves are checked: HEAD must
# descend from `commit`, and every `patches[].commit` must be an ancestor of
# HEAD.  A tree with no git metadata (a tarball build) is left alone.
TREE=${1:?usage: check-pin.sh TREE [PIN]}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PIN=${2:-${GS_PIN:-$ROOT/../upstream-source/pin/PIN.json}}

if ! git -C "$TREE" rev-parse --git-dir >/dev/null 2>&1; then
  echo "pin check: $TREE has no git metadata, skipping" >&2
  exit 0
fi

python3 - "$TREE" "$PIN" <<'PY'
import json, os, subprocess, sys

tree, pin_path = sys.argv[1], sys.argv[2]
pin = json.load(open(pin_path))
base = pin["commit"]
patches = pin.get("patches", [])

def git(*args):
    return subprocess.run(["git", "-C", tree] + list(args),
                          capture_output=True, text=True)

def is_ancestor(commit):
    return git("merge-base", "--is-ancestor", commit, "HEAD").returncode == 0

head = git("rev-parse", "--short=12", "HEAD").stdout.strip()
branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

if os.environ.get("GIT_DSL_SKIP_PIN_CHECK") == "1":
    print("pin check: skipped by GIT_DSL_SKIP_PIN_CHECK=1", file=sys.stderr)
    sys.exit(0)

missing = []
if not is_ancestor(base):
    missing.append(("base", base, "the pin commit itself"))
for p in patches:
    if not is_ancestor(p["commit"]):
        missing.append(("patch", p["commit"],
                        "#%s %s" % (p["pr"], p["title"])))

if missing:
    print("pin check: %s (%s) cannot back the corpus." % (head, branch),
          file=sys.stderr)
    for _, commit, what in missing:
        print("  missing %s  %s" % (commit, what), file=sys.stderr)
    print("The official side would answer with pre-patch rules, so the "
          "deviations in tools/import-cxx.py would look like ours.\n"
          "Build from a tree that has PIN.json `commit` and every "
          "`patches[].commit`, or update PIN.json first.", file=sys.stderr)
    sys.exit(1)

print("pin check: %s + %d patches at %s (%s)"
      % (base[:12], len(patches), head, branch))
PY
