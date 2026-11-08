#!/usr/bin/env bash
# Regenerate tests/artifacts/ from a built LLVM tree.
#
# DEVELOPMENT ONLY.  `gisel gen` and CI never call llvm-tblgen; this script
# exists so the frozen oracle can follow an upstream legalizer change instead
# of pinning the project to one commit forever.
#
# The oracle was last produced from llvm-project d48f5512a162.
#
#   TREE=/path/to/llvm-project BUILD=/path/to/build tools/refresh-oracle.sh
set -euo pipefail

TREE=${TREE:-/home/ubuntu/llvm/trees/explore}
BUILD=${BUILD:-/home/ubuntu/llvm/builds/explore}
HERE=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$HERE/tests/artifacts}
TBLGEN=$BUILD/bin/llvm-tblgen

test -x "$TBLGEN" || { echo "no llvm-tblgen at $TBLGEN" >&2; exit 1; }

for T in X86 AArch64; do
  L=$(echo "$T" | tr 'A-Z' 'a-z')
  TD=$TREE/llvm/lib/Target/$T/GISel/${T}LegalizerInfo.td
  test -f "$TD" || { echo "no $TD" >&2; exit 1; }
  INC=(-I"$TREE/llvm/lib/Target/$T" -I"$TREE/llvm/include" -I"$TREE/llvm/lib/Target")
  "$TBLGEN" -gen-legalizer       "${INC[@]}" "$TD" -o "$OUT/$L.inc"
  "$TBLGEN" -gen-legalizer-check "${INC[@]}" "$TD" -o "$OUT/$L.check.json"
  "$TBLGEN" -gen-legalizer-core  "${INC[@]}" "$TD" -o "$OUT/$L.core.json"
done

( cd "$OUT" && sha256sum aarch64.inc aarch64.check.json aarch64.core.json \
    x86.inc x86.check.json x86.core.json > SHA256 )

echo "oracle refreshed in $OUT"
echo "review \`git diff tests/artifacts\`: the frozen C++/JSON oracle changed,"
echo "the core JSON legitimately differs in origin/line only"
