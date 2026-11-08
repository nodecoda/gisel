#!/usr/bin/env bash
set -euo pipefail

# build-riscv-runner.sh TREE BUILD INC OUT
#
# The official runner gets RISCVLegalizerInfo's constructor from the shared
# library. The ours runner links a replacement constructor object first; that
# constructor includes the generated fragment into the same RISCVLegalizerInfo
# class. All other target code remains from the official shared library.
TREE=${1:?usage: build-riscv-runner.sh TREE BUILD INC OUT}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CXX=${CXX:-g++}
mkdir -p "$(dirname "$OUT")"

# The generated constructor includes "RISCVLegalizerInfo.inc" by name, and
# the include path also holds the build's own generated copy.  Materialise the
# caller's INC under that name in a private directory, first on the search
# path, so a stale build artifact can never be linked in by accident.
GENINC="$OUT.generated-inc"
mkdir -p "$GENINC"
cp "$INC" "$GENINC/RISCVLegalizerInfo.inc"

FLAGS=(
  -DLLVM_BUILD_STATIC -D_DEBUG -D_GLIBCXX_ASSERTIONS
  -D_GLIBCXX_USE_CXX11_ABI=1 -D_GNU_SOURCE
  -D__STDC_CONSTANT_MACROS -D__STDC_FORMAT_MACROS -D__STDC_LIMIT_MACROS
  -I"$GENINC"
  -I"$BUILD/unittests/Target/RISCV"
  -I"$TREE/llvm/unittests/Target/RISCV"
  -I"$BUILD/include" -I"$TREE/llvm/include"
  -I"$TREE/llvm/lib/Target/RISCV" -I"$BUILD/lib/Target/RISCV"
  -fPIC -fno-exceptions -funwind-tables -fno-rtti -std=c++17
  -DNDEBUG -UNDEBUG
)

LIBS=(
  "$BUILD/lib/libLLVMRISCVCodeGen.so.24.0git"
  "$BUILD/lib/libLLVMRISCVDesc.so.24.0git"
  "$BUILD/lib/libLLVMRISCVInfo.so.24.0git"
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

"$CXX" "${FLAGS[@]}" -DAB_OFFICIAL -c "$ROOT/tools/ab/riscv_query_runner.cpp" \
  -o "$OUT.official.o"
"$CXX" -fuse-ld=lld -Wl,-rpath,"$BUILD/lib" "$OUT.official.o" \
  "${LIBS[@]}" -o "$OUT.official"

"$CXX" "${FLAGS[@]}" -DAB_OURS -c "$ROOT/tools/ab/riscv_query_runner.cpp" \
  -o "$OUT.ours.o"

"$CXX" "${FLAGS[@]}" -c "$ROOT/tools/ab/riscv_generated_ctor.cpp" \
  -o "$OUT.generated-ctor.o"
"$CXX" -fuse-ld=lld -Wl,-rpath,"$BUILD/lib" "$OUT.ours.o" \
  "$OUT.generated-ctor.o" \
  "${LIBS[@]}" -o "$OUT.ours"
echo "$OUT: official, ours"
