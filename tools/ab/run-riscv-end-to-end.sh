#!/usr/bin/env bash
set -euo pipefail

# run-riscv-end-to-end.sh TREE BUILD INC OUT [STATE]
#
# One command, no manual steps: build both runners from INC, generate the
# 6,301-query set, answer it twice, and diff.  The query set is `gisel cases`
# over the corpus imported from the hand-written upstream C++.
TREE=${1:?usage: run-riscv-end-to-end.sh TREE BUILD INC OUT [STATE]}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
STATE=${5:-$ROOT/.ab/riscv}
EXPECTED_QUERIES=6301
mkdir -p "$OUT" "$STATE"

"$ROOT/tools/ab/build-riscv-runner.sh" "$TREE" "$BUILD" "$INC" "$OUT/runner"

# The query count is part of the contract. If the corpus or an axis changes it,
# stop and review the new question set before trusting the diff.
python3 -m gisel cases "$ROOT/tests/corpus/RISCVLegalizerInfo.gisel" \
  --features "$ROOT/tests/cases/riscv-features.json" \
  --out "$OUT/queries.jsonl" --json
GOT=$(wc -l < "$OUT/queries.jsonl")
if [[ "$GOT" != "$EXPECTED_QUERIES" ]]; then
  echo "query set changed: $GOT lines, expected $EXPECTED_QUERIES" >&2
  exit 1
fi

python3 "$ROOT/tools/ab/run-queries.py" "$OUT/runner.official" \
  "$OUT/queries.jsonl" "$OUT/official.answers.jsonl"
python3 "$ROOT/tools/ab/run-queries.py" "$OUT/runner.ours" \
  "$OUT/queries.jsonl" "$OUT/ours.answers.jsonl"
python3 "$ROOT/tools/ab/diff.py" "$OUT/official.answers.jsonl" \
  "$OUT/ours.answers.jsonl" --json | tee "$OUT/diff.json"
