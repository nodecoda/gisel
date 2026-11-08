#!/usr/bin/env bash
# Capture the official build first, then replace its inc and run ours.
# This ordering matters because both runners use the build's shared library.
#
#   run-end-to-end.sh TREE BUILD QUERIES INC OUT [STATE]
set -euo pipefail

TREE=${1:?usage: run-end-to-end.sh TREE BUILD QUERIES INC OUT [STATE]}
BUILD=${2:?}
QUERIES=${3:?}
INC=${4:?}
OUT=${5:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
STATE=${6:-$ROOT/.ab}
mkdir -p "$OUT"

if [[ ! -f "$STATE/baseline/X86LegalizerInfo.inc" ]]; then
  "$ROOT/tools/ab/snapshot.sh" "$TREE" "$BUILD" "$STATE/baseline"
fi

# The baseline answers are captured before the shared library is changed.
"$ROOT/tools/ab/restore-inc.sh" "$BUILD" "$STATE"
"$ROOT/tools/ab/build-runner.sh" "$TREE" "$BUILD" \
  "$OUT/runner.official" shipping
"$OUT/runner.official" --queries "$QUERIES" > "$OUT/official.answers.jsonl"

"$ROOT/tools/ab/swap-inc.sh" "$BUILD" "$INC" "$STATE"
"$ROOT/tools/ab/build-runner.sh" "$TREE" "$BUILD" \
  "$OUT/runner.ours" shipping
"$OUT/runner.ours" --queries "$QUERIES" > "$OUT/ours.answers.jsonl"

python3 "$ROOT/tools/ab/diff.py" "$OUT/official.answers.jsonl" \
  "$OUT/ours.answers.jsonl" --json | tee "$OUT/diff.json"
