#!/usr/bin/env bash
set -euo pipefail

BUILD=${1:?usage: restore-inc.sh BUILD [STATE]}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
STATE=${2:-$ROOT/.ab}
TREE=${LLVM_TREE:-$(cd "$BUILD/../../trees/$(basename "$BUILD")" && pwd)}
BASE=$STATE/baseline/X86LegalizerInfo.inc
TARGET=$BUILD/lib/Target/X86/X86LegalizerInfo.inc
test -f "$BASE"
cp -p "$BASE" "$TARGET"
touch "$TREE/llvm/lib/Target/X86/GISel/X86LegalizerInfo.cpp"
ninja -C "$BUILD" libLLVMX86CodeGen.so
echo "restored $TARGET"
