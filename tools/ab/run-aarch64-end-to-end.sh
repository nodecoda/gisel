#!/usr/bin/env bash
set -euo pipefail

# run-aarch64-end-to-end.sh TREE BUILD INC OUT [STATE]
#
# One command, no manual steps: build both runners from INC, generate the
# 12,952-query set, answer it twice, and diff.  The query set is `gisel cases`
# with the recording axes file, not LLVM's table points, because the ordering
# axis only exists in the query generator.
TREE=${1:?usage: run-aarch64-end-to-end.sh TREE BUILD INC OUT [STATE]}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
STATE=${5:-$ROOT/.ab/aarch64}
EXPECTED_QUERIES=12952
mkdir -p "$OUT" "$STATE"

"$ROOT/tools/ab/build-aarch64-runner.sh" "$TREE" "$BUILD" "$INC" \
  "$OUT/runner"

if [[ ! -f "$STATE/libLLVMAArch64CodeGen.so.24.0git" ]]; then
  cp -p "$BUILD/lib/libLLVMAArch64CodeGen.so.24.0git" \
    "$STATE/libLLVMAArch64CodeGen.so.24.0git"
  sha256sum "$BUILD/lib/libLLVMAArch64CodeGen.so.24.0git" > \
    "$STATE/libLLVMAArch64CodeGen.so.sha256"
fi

# The query count is part of the contract. If the corpus or an axis changes it,
# stop and review the new question set before trusting the diff.
python3 -m gisel cases "$ROOT/tests/corpus/AArch64LegalizerInfo.gisel" \
  --features "$ROOT/tests/cases/features.json" \
  --axes "$ROOT/tests/cases/aarch64-mem-orderings.axes.json" \
  --out "$OUT/queries.jsonl" --json
GOT=$(wc -l < "$OUT/queries.jsonl")
if [[ "$GOT" != "$EXPECTED_QUERIES" ]]; then
  echo "query set changed: $GOT lines, expected $EXPECTED_QUERIES" >&2
  exit 1
fi

# A query that trips an LLVM assertion kills the process; run-queries.py
# restarts after it and marks it `unanswerable`, so the answer files stay
# parallel to the query file.
python3 "$ROOT/tools/ab/run-queries.py" "$OUT/runner.official" \
  "$OUT/queries.jsonl" "$OUT/official.answers.jsonl"
python3 "$ROOT/tools/ab/run-queries.py" "$OUT/runner.ours" \
  "$OUT/queries.jsonl" "$OUT/ours.answers.jsonl"
python3 "$ROOT/tools/ab/diff.py" "$OUT/official.answers.jsonl" \
  "$OUT/ours.answers.jsonl" --json | tee "$OUT/diff.json"
