#!/usr/bin/env bash
set -euo pipefail

# build-m68k-runner.sh TREE BUILD INC OUT
#
# Thin per-target entry for build-query-runner.sh, so `ab.py` keeps its
# uniform `builder TREE BUILD INC PREFIX` contract.
TREE=${1:?usage: build-m68k-runner.sh TREE BUILD INC OUT}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)

exec "$ROOT/tools/ab/build-query-runner.sh" "$TREE" "$BUILD" "$INC" "$OUT" \
  M68k "$ROOT/tools/ab/m68k_query_runner.cpp" \
  "$ROOT/tools/ab/m68k_generated_ctor.cpp"
