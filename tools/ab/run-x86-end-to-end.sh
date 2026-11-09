#!/usr/bin/env bash
set -euo pipefail

# run-x86-end-to-end.sh TREE BUILD INC OUT [STATE]
#
# The official side is the pinned hand-written X86LegalizerInfo.cpp.  Our side
# replaces only its constructor body with `#include "X86LegalizerInfo.inc"` (the
# gisel output) and rebuilds the same library.  Both sides answer the same
# `gisel cases` query set.
TREE=${1:?usage: run-x86-end-to-end.sh TREE BUILD INC OUT [STATE]}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
STATE=${5:-$ROOT/.ab/x86}
EXPECTED_QUERIES=3027
mkdir -p "$OUT" "$STATE"

restore() {
  python3 "$ROOT/tools/ab/swap-source-ctor.py" restore \
    --target x86 --tree "$TREE" >/dev/null 2>&1 || true
}
cleanup() {
  rc=$?
  restore
  ninja -C "$BUILD" libLLVMX86CodeGen.so >/dev/null 2>&1 || true
  exit "$rc"
}
trap cleanup EXIT

# Start from the upstream text, not from a previous run's patch.
restore
ninja -C "$BUILD" libLLVMX86CodeGen.so

python3 -m gisel cases "$ROOT/tests/corpus/X86LegalizerInfo.gisel" \
  --features "$ROOT/tests/cases/x86-features.json" \
  --out "$OUT/queries.jsonl" --json
GOT=$(wc -l < "$OUT/queries.jsonl")
if [[ "$GOT" != "$EXPECTED_QUERIES" ]]; then
  echo "query set changed: $GOT lines, expected $EXPECTED_QUERIES" >&2
  exit 1
fi

"$ROOT/tools/ab/build-runner.sh" "$TREE" "$BUILD" "$OUT/runner.official" \
  shipping
python3 "$ROOT/tools/ab/run-queries.py" "$OUT/runner.official" \
  "$OUT/queries.jsonl" "$OUT/official.answers.jsonl"

python3 "$ROOT/tools/ab/swap-source-ctor.py" apply \
  --target x86 --tree "$TREE" --inc "$INC"
ninja -C "$BUILD" libLLVMX86CodeGen.so
"$ROOT/tools/ab/build-runner.sh" "$TREE" "$BUILD" "$OUT/runner.ours" shipping
python3 "$ROOT/tools/ab/run-queries.py" "$OUT/runner.ours" \
  "$OUT/queries.jsonl" "$OUT/ours.answers.jsonl"

python3 "$ROOT/tools/ab/diff.py" "$OUT/official.answers.jsonl" \
  "$OUT/ours.answers.jsonl" --json | tee "$OUT/diff.json"
