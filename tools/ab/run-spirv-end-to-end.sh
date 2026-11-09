#!/usr/bin/env bash
set -euo pipefail

# run-spirv-end-to-end.sh TREE BUILD INC OUT
#
# One command, no manual steps: build both runners from INC, generate the
# fixed query set, answer it twice, and diff.  The query count is a contract:
# if the corpus changes it, stop and review the new questions.
#
# The four unanswerable queries are a shared assert: SPIRVLegalizerInfo.cpp
# passes `MaxVectorSize` where `changeElementSizeTo` expects a type index
# (`changeElementCountTo(0, ElementCount::getFixed(...))` was meant), so both
# sides abort on G_SPLAT_VECTOR with 32 elements.  `--expect-unanswerable 4`
# pins the count; a new class of assert cannot hide there.  See
# docs/REPORT-cxx-corpus.md and admin/upstream-issues.
TREE=${1:?usage: run-spirv-end-to-end.sh TREE BUILD INC OUT}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
EXPECTED_QUERIES=5136
mkdir -p "$OUT"

"$ROOT/tools/ab/build-spirv-runner.sh" "$TREE" "$BUILD" "$INC" "$OUT/runner"

python3 -m gisel cases "$ROOT/tests/corpus/SPIRVLegalizerInfo.gisel" \
  --features "$ROOT/tests/cases/spirv-features.json" \
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
  "$OUT/ours.answers.jsonl" --expect-unanswerable 4 --json | tee "$OUT/diff.json"
