#!/usr/bin/env bash
set -euo pipefail

# run-mips-end-to-end.sh TREE BUILD INC OUT
#
# One command, no manual steps: build both runners from INC, generate the
# fixed query set, answer it twice, and diff.  The query count is a contract:
# if the corpus changes it, stop and review the new questions.
TREE=${1:?usage: run-mips-end-to-end.sh TREE BUILD INC OUT}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
EXPECTED_QUERIES=1656
mkdir -p "$OUT"

"$ROOT/tools/ab/build-mips-runner.sh" "$TREE" "$BUILD" "$INC" "$OUT/runner"

python3 -m gisel cases "$ROOT/tests/corpus/MipsLegalizerInfo.gisel" \
  --features "$ROOT/tests/cases/mips-features.json" \
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
# Nine queries ask the same question upstream answers with an assert:
# `G_LOAD` of an unaligned 4-byte memory into a value wider than 32 bits, on a
# subtarget without unaligned access.  The Mips legalizer claims "4 byte load
# and store are legal" and asserts on everything else, but its legal rule only
# names `s32`/`p0` values, so a wider value reaches the assert.  The count is
# pinned so a new class of assert cannot hide here; see
# docs/REPORT-cxx-corpus.md and the upstream issue file.
python3 "$ROOT/tools/ab/diff.py" "$OUT/official.answers.jsonl" \
  "$OUT/ours.answers.jsonl" --allow-ref-asserts 9 --json | tee "$OUT/diff.json"
