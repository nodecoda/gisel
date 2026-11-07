#!/usr/bin/env bash
set -euo pipefail

# run-aarch64-end-to-end.sh TREE BUILD INC OUT [STATE]
TREE=${1:?usage: run-aarch64-end-to-end.sh TREE BUILD INC OUT [STATE]}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
STATE=${5:-$ROOT/.ab/aarch64}
mkdir -p "$OUT" "$STATE"

"$ROOT/tools/ab/build-aarch64-runner.sh" "$TREE" "$BUILD" "$INC" \
  "$OUT/runner"

if [[ ! -f "$STATE/libLLVMAArch64CodeGen.so.24.0git" ]]; then
  cp -p "$BUILD/lib/libLLVMAArch64CodeGen.so.24.0git" \
    "$STATE/libLLVMAArch64CodeGen.so.24.0git"
  sha256sum "$BUILD/lib/libLLVMAArch64CodeGen.so.24.0git" > \
    "$STATE/libLLVMAArch64CodeGen.so.sha256"
fi

# The domain size is part of the contract. If LLVM changes the generated
# table-point include, stop and review the new question set.
AARCH64_EXPECTED_QUERIES=9591 "$OUT/runner.domain" > "$OUT/queries.jsonl"
"$OUT/runner.official" --queries "$OUT/queries.jsonl" > \
  "$OUT/official.answers.jsonl"
"$OUT/runner.ours" --queries "$OUT/queries.jsonl" > \
  "$OUT/ours.answers.jsonl"
python3 -m gisel diff "$OUT/official.answers.jsonl" \
  "$OUT/ours.answers.jsonl" --json | tee "$OUT/diff.json"
