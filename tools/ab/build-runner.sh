#!/usr/bin/env bash
# Build the A/B query runner against one LLVM build.
#
#   build-runner.sh TREE BUILD OUT [shipping|reference]
#
# shipping  -> link libLLVMX86CodeGen (the .inc currently in BUILD)
# reference -> link the frozen X86LegalizerInfoReference object
set -euo pipefail

TREE=${1:?usage: build-runner.sh TREE BUILD OUT [shipping|reference]}
BUILD=${2:?}
OUT=${3:?}
MODE=${4:-shipping}
CXX=${CXX:-g++}
HERE=$(cd "$(dirname "$0")/../.." && pwd)

# The official side must carry PIN.json `commit` plus every unmerged patch it
# lists; a tree without them answers with pre-patch rules.
"$HERE/tools/ab/check-pin.sh" "$TREE"
SRC=$HERE/tools/ab/query_runner.cpp
mkdir -p "$(dirname "$OUT")"

FLAGS=(
  -DLLVM_BUILD_STATIC -D_DEBUG -D_GLIBCXX_ASSERTIONS
  -D_GLIBCXX_USE_CXX11_ABI=1 -D_GNU_SOURCE
  -D__STDC_CONSTANT_MACROS -D__STDC_FORMAT_MACROS -D__STDC_LIMIT_MACROS
  -I"$BUILD/unittests/Target/X86"
  -I"$TREE/llvm/unittests/Target/X86"
  -I"$BUILD/include"
  -I"$TREE/llvm/include"
  -I"$TREE/llvm/lib/Target/X86"
  -I"$BUILD/lib/Target/X86"
  -fPIC -fno-exceptions -funwind-tables -fno-rtti -std=c++17
  -DNDEBUG -UNDEBUG
)

DEFS=()
OBJS=()
if [ "$MODE" = reference ]; then
  DEFS+=(-DAB_REFERENCE)
  OBJS+=("$BUILD/unittests/Target/X86/CMakeFiles/X86Tests.dir/X86LegalizerInfoReference.cpp.o")
fi

LIBS=(
  "$BUILD/lib/libLLVMX86CodeGen.so.24.0git"
  "$BUILD/lib/libLLVMX86Desc.so.24.0git"
  "$BUILD/lib/libLLVMX86Info.so.24.0git"
  "$BUILD/lib/libLLVMGlobalISel.so.24.0git"
  "$BUILD/lib/libLLVMSelectionDAG.so.24.0git"
  "$BUILD/lib/libLLVMCodeGen.so.24.0git"
  "$BUILD/lib/libLLVMCodeGenTypes.so.24.0git"
  "$BUILD/lib/libLLVMTarget.so.24.0git"
  "$BUILD/lib/libLLVMAnalysis.so.24.0git"
  "$BUILD/lib/libLLVMAsmParser.so.24.0git"
  "$BUILD/lib/libLLVMCore.so.24.0git"
  "$BUILD/lib/libLLVMMC.so.24.0git"
  "$BUILD/lib/libLLVMTargetParser.so.24.0git"
  "$BUILD/lib/libLLVMSupport.so.24.0git"
  -lpthread -ldl -lm -lz
)

"$CXX" "${FLAGS[@]}" "${DEFS[@]}" -c "$SRC" -o "$OUT.o"
"$CXX" -fuse-ld=lld -Wl,-rpath,"$BUILD/lib" "$OUT.o" "${OBJS[@]}" \
  "${LIBS[@]}" -o "$OUT"
echo "$OUT: $MODE"
