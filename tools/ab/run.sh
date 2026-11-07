#!/usr/bin/env bash
# Run both answerers on one fixed query file and compare the complete streams.
#
#   run.sh QUERIES [OUT] [REFERENCE_RUNNER] [OURS_RUNNER]
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
QUERIES=${1:?usage: run.sh QUERIES [OUT] [REFERENCE_RUNNER] [OURS_RUNNER]}
OUT=${2:-$ROOT/.ab/results}
REF=${3:-${AB_REFERENCE_RUNNER:-$ROOT/.ab/runner.reference}}
OURS=${4:-${AB_OURS_RUNNER:-$ROOT/.ab/runner.shipping}}
mkdir -p "$OUT"
"$REF" --queries "$QUERIES" > "$OUT/reference.answers.jsonl"
"$OURS" --queries "$QUERIES" > "$OUT/ours.answers.jsonl"
python3 -m gisel diff "$OUT/reference.answers.jsonl" \
  "$OUT/ours.answers.jsonl" --json | tee "$OUT/diff.json"
