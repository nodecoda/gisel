#!/usr/bin/env bash
set -euo pipefail

# build-query-runner.sh TREE BUILD INC OUT TARGET RUNNER CTOR
#
# One A/B pair for any target whose legalizer constructor can be replaced:
#
#   official  links libLLVM<TARGET>CodeGen and uses its constructor;
#   ours      links the same libraries plus a replacement constructor object,
#             placed first, whose body is the generated `.inc`.
#
# TARGET is the LLVM target directory name (M68k, WebAssembly, PowerPC, ...).
# RUNNER and CTOR are paths to the per-target C++ files; everything else is
# derived so a new target does not need another 80-line build script.
TREE=${1:?usage: build-query-runner.sh TREE BUILD INC OUT TARGET RUNNER CTOR}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
TARGET=${5:?}
RUNNER=${6:?}
CTOR=${7:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CXX=${CXX:-g++}

# The generated constructor includes "<TARGET>LegalizerInfo.inc" by name; the
# build tree also holds its own copy.  Materialise the caller's INC under that
# name in a private directory, first on the search path, so a stale artifact
# can never be linked in by accident.
GENINC="$OUT.generated-inc"
mkdir -p "$GENINC"
cp "$INC" "$GENINC/${TARGET}LegalizerInfo.inc"

FLAGS=(
  -DLLVM_BUILD_STATIC -D_DEBUG -D_GLIBCXX_ASSERTIONS
  -D_GLIBCXX_USE_CXX11_ABI=1 -D_GNU_SOURCE
  -D__STDC_CONSTANT_MACROS -D__STDC_FORMAT_MACROS -D__STDC_LIMIT_MACROS
  -I"$GENINC"
  -I"$BUILD/unittests/Target/$TARGET"
  -I"$TREE/llvm/unittests/Target/$TARGET"
  -I"$BUILD/include" -I"$TREE/llvm/include"
  -I"$TREE/llvm/lib/Target/$TARGET" -I"$BUILD/lib/Target/$TARGET"
  -fPIC -fno-exceptions -funwind-tables -fno-rtti -std=c++17
  -DNDEBUG -UNDEBUG
)

LIBS=(
  "$BUILD/lib/libLLVM${TARGET}CodeGen.so.24.0git"
  "$BUILD/lib/libLLVM${TARGET}Desc.so.24.0git"
  "$BUILD/lib/libLLVM${TARGET}Info.so.24.0git"
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

"$CXX" "${FLAGS[@]}" -DAB_OFFICIAL -c "$RUNNER" -o "$OUT.official.o"
"$CXX" -fuse-ld=lld -Wl,-rpath,"$BUILD/lib" "$OUT.official.o" \
  "${LIBS[@]}" -o "$OUT.official"

"$CXX" "${FLAGS[@]}" -DAB_OURS -c "$RUNNER" -o "$OUT.ours.o"
"$CXX" "${FLAGS[@]}" -c "$CTOR" -o "$OUT.generated-ctor.o"
"$CXX" -fuse-ld=lld -Wl,-rpath,"$BUILD/lib" "$OUT.ours.o" \
  "$OUT.generated-ctor.o" "${LIBS[@]}" -o "$OUT.ours"

echo "$OUT: official, ours"
