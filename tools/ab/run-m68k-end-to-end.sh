#!/usr/bin/env bash
set -euo pipefail

# run-m68k-end-to-end.sh TREE BUILD INC OUT
#
# One command, no manual steps: build both runners from INC, generate the
# 41-query set, answer it twice, and diff.  The query count is a contract: if
# the corpus or a feature axis changes it, stop and review the new questions.
TREE=${1:?usage: run-m68k-end-to-end.sh TREE BUILD INC OUT}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
EXPECTED_QUERIES=41
mkdir -p "$OUT"

"$ROOT/tools/ab/build-m68k-runner.sh" "$TREE" "$BUILD" "$INC" "$OUT/runner"

python3 -m gisel cases "$ROOT/tests/corpus/M68kLegalizerInfo.gisel" \
  --features "$ROOT/tests/cases/m68k-features.json" \
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
