#!/usr/bin/env bash
set -euo pipefail

# build-aarch64-runner.sh TREE BUILD INC OUT
#
# The official runner gets AArch64LegalizerInfo's constructor from the shared
# library. The ours runner links a replacement constructor object first; that
# constructor includes the generated fragment into the same AArch64LegalizerInfo
# class. All other target code remains from the official shared library.
TREE=${1:?usage: build-aarch64-runner.sh TREE BUILD INC OUT}
BUILD=${2:?}
INC=${3:?}
OUT=${4:?}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)

# The official side must carry PIN.json `commit` plus every unmerged patch it
# lists; a tree without them answers with pre-patch rules.
"$ROOT/tools/ab/check-pin.sh" "$TREE"
CXX=${CXX:-g++}
mkdir -p "$(dirname "$OUT")"

# The generated constructor includes "AArch64LegalizerInfo.inc" by name, and
# the include path also holds the build's own generated copy.  Materialise the
# caller's INC under that name in a private directory, first on the search
# path, so a stale build artifact can never be linked in by accident.
GENINC="$OUT.generated-inc"
mkdir -p "$GENINC"
cp "$INC" "$GENINC/AArch64LegalizerInfo.inc"

FLAGS=(
  -DLLVM_BUILD_STATIC -D_DEBUG -D_GLIBCXX_ASSERTIONS
  -D_GLIBCXX_USE_CXX11_ABI=1 -D_GNU_SOURCE
  -D__STDC_CONSTANT_MACROS -D__STDC_FORMAT_MACROS -D__STDC_LIMIT_MACROS
  -I"$GENINC"
  -I"$BUILD/unittests/Target/AArch64"
  -I"$TREE/llvm/unittests/Target/AArch64"
  -I"$BUILD/include" -I"$TREE/llvm/include"
  -I"$TREE/llvm/lib/Target/AArch64" -I"$BUILD/lib/Target/AArch64"
  -fPIC -fno-exceptions -funwind-tables -fno-rtti -std=c++17
  -DNDEBUG -UNDEBUG
)

LIBS=(
  "$BUILD/lib/libLLVMAArch64CodeGen.so.24.0git"
  "$BUILD/lib/libLLVMAArch64Desc.so.24.0git"
  "$BUILD/lib/libLLVMAArch64Info.so.24.0git"
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

"$CXX" "${FLAGS[@]}" -DAB_OFFICIAL -c "$ROOT/tools/ab/aarch64_query_runner.cpp" \
  -o "$OUT.official.o"
"$CXX" -fuse-ld=lld -Wl,-rpath,"$BUILD/lib" "$OUT.official.o" \
  "${LIBS[@]}" -o "$OUT.official"

"$CXX" "${FLAGS[@]}" -DAB_OURS -c "$ROOT/tools/ab/aarch64_query_runner.cpp" \
  -o "$OUT.ours.o"

"$CXX" "${FLAGS[@]}" -c "$ROOT/tools/ab/aarch64_generated_ctor.cpp" \
  -o "$OUT.generated-ctor.o"
"$CXX" -fuse-ld=lld -Wl,-rpath,"$BUILD/lib" "$OUT.ours.o" \
  "$OUT.generated-ctor.o" \
  "${LIBS[@]}" -o "$OUT.ours"

"$CXX" "${FLAGS[@]}" -c "$ROOT/tools/ab/aarch64_domain_dump.cpp" \
  -o "$OUT.domain.o"
"$CXX" -fuse-ld=lld -Wl,-rpath,"$BUILD/lib" "$OUT.domain.o" \
  "${LIBS[@]}" -o "$OUT.domain"
echo "$OUT: official, ours, domain"
