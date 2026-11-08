#!/usr/bin/env bash
# build-x86-ctor-runner.sh TREE BUILD INC OUT
#
# The official runner uses the library's X86LegalizerInfo constructor.  The
# ours runner links a replacement constructor object first; that object
# includes the generated fragment into the same X86LegalizerInfo class.  All
# other target code remains from the official shared library.
set -euo pipefail

TREE=${1:?usage: build-x86-ctor-runner.sh TREE BUILD INC OUT}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CXX=${CXX:-g++}

# Keep the generated include under its expected name in a private directory,
# first on the search path, so a stale build artifact cannot be linked in.
GENINC="$OUT.generated-inc"
mkdir -p "$GENINC"
cp "$INC" "$GENINC/X86LegalizerInfo.inc"

FLAGS=(
  -DLLVM_BUILD_STATIC -D_DEBUG -D_GLIBCXX_ASSERTIONS
  -D_GLIBCXX_USE_CXX11_ABI=1 -D_GNU_SOURCE
  -D__STDC_CONSTANT_MACROS -D__STDC_FORMAT_MACROS -D__STDC_LIMIT_MACROS
  -I"$GENINC"
  -I"$BUILD/unittests/Target/X86"
  -I"$TREE/llvm/unittests/Target/X86"
  -I"$BUILD/include"
  -I"$TREE/llvm/include"
  -I"$TREE/llvm/lib/Target/X86"
  -I"$BUILD/lib/Target/X86"
  -fPIC -fno-exceptions -funwind-tables -fno-rtti -std=c++17
  -DNDEBUG -UNDEBUG
)

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

"$CXX" "${FLAGS[@]}" -c "$ROOT/tools/ab/query_runner.cpp" \
  -o "$OUT.official.o"
"$CXX" -fuse-ld=lld -Wl,-rpath,"$BUILD/lib" "$OUT.official.o" \
  "${LIBS[@]}" -o "$OUT.official"

"$CXX" "${FLAGS[@]}" -c "$ROOT/tools/ab/query_runner.cpp" \
  -o "$OUT.ours.o"
"$CXX" "${FLAGS[@]}" -c "$ROOT/tools/ab/x86_generated_ctor.cpp" \
  -o "$OUT.generated-ctor.o"
"$CXX" -fuse-ld=lld -Wl,-rpath,"$BUILD/lib" "$OUT.ours.o" \
  "$OUT.generated-ctor.o" "${LIBS[@]}" -o "$OUT.ours"
echo "$OUT: official, ours"
