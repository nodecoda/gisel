#!/usr/bin/env bash
# Install an inc, rebuild X86CodeGen, and restore the baseline on failure.
#
#   swap-inc.sh BUILD INC [STATE]
set -euo pipefail

BUILD=${1:?usage: swap-inc.sh BUILD INC [STATE]}
INC=${2:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
STATE=${3:-$ROOT/.ab}
TREE=${LLVM_TREE:-$(cd "$BUILD/../../trees/$(basename "$BUILD")" && pwd)}
TARGET=$BUILD/lib/Target/X86/X86LegalizerInfo.inc
BASE=$STATE/baseline/X86LegalizerInfo.inc

test -f "$INC"
test -f "$TARGET"
mkdir -p "$(dirname "$BASE")"
if [[ ! -f "$BASE" ]]; then
  cp -p "$TARGET" "$BASE"
fi

restore() {
  cp -p "$BASE" "$TARGET"
  touch "$TREE/llvm/lib/Target/X86/GISel/X86LegalizerInfo.cpp"
}
cleanup() {
  rc=$?
  if [[ "$rc" -ne 0 ]]; then
    restore
    ninja -C "$BUILD" libLLVMX86CodeGen.so || true
  fi
  exit "$rc"
}
trap cleanup EXIT

cp "$INC" "$TARGET"
touch "$TREE/llvm/lib/Target/X86/GISel/X86LegalizerInfo.cpp"
ninja -C "$BUILD" libLLVMX86CodeGen.so

want=$(sha256sum "$INC" | awk '{print $1}')
got=$(sha256sum "$TARGET" | awk '{print $1}')
if [[ "$want" != "$got" ]]; then
  echo "swap-inc: generated include was overwritten during build" >&2
  exit 1
fi
trap - EXIT
echo "installed $TARGET ($got)"
