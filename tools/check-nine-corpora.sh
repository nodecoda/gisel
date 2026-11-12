#!/usr/bin/env bash
set -euo pipefail

# tools/check-nine-corpora.sh [--record] [--out DIR] [--manifest FILE]
#
# Every shipped corpus must generate byte-identical inc/check/core output.
# Unlike tests/test_artifacts.py (three checked-in files), this covers all
# nine corpora and stores only a SHA256 manifest, not 1.9 MB of duplicates.
#
#   --record            rewrite tests/artifacts/nine/SHA256 from this run
#   --out DIR           use DIR instead of a temporary directory
#   --manifest FILE     compare against FILE (default: the checked-in one)
#
# A corpus added or removed without updating the manifest is an error.

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RECORD=0
OUT=""
MANIFEST="$ROOT/tests/artifacts/nine/SHA256"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --record) RECORD=1; shift ;;
    --out) OUT=${2:?}; shift 2 ;;
    --manifest) MANIFEST=${2:?}; shift 2 ;;
    *) echo "usage: $0 [--record] [--out DIR] [--manifest FILE]" >&2; exit 2 ;;
  esac
done

cleanup=""
if [[ -z $OUT ]]; then
  OUT=$(mktemp -d "${TMPDIR:-/tmp}/gisel-nine.XXXXXX")
  cleanup=$OUT
fi
mkdir -p "$OUT"
trap 'if [[ -n $cleanup ]]; then python3 -c "import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)" "$cleanup"; fi' EXIT

cd "$ROOT"
count=0
for corpus in tests/corpus/*.gisel; do
  base=$(basename "$corpus" LegalizerInfo.gisel)
  case "$base" in
    X86) name=x86 ;;
    AArch64) name=aarch64 ;;
    RISCV) name=riscv ;;
    ARM) name=arm ;;
    Mips) name=mips ;;
    PowerPC) name=ppc ;;
    M68k) name=m68k ;;
    WebAssembly) name=wasm ;;
    SPIRV) name=spirv ;;
    *) echo "unknown corpus: $corpus" >&2; exit 2 ;;
  esac
  for emit in inc check core; do
    python3 -m gisel.cli gen "$corpus" --emit="$emit" \
      --out "$OUT/$name.$emit" >/dev/null
  done
  count=$((count + 1))
done
if [[ $count -ne 9 ]]; then
  echo "expected 9 corpora, found $count" >&2
  exit 2
fi

if [[ $RECORD -eq 1 ]]; then
  mkdir -p "$(dirname "$MANIFEST")"
  (cd "$OUT" && sha256sum * | sort -k2) > "$MANIFEST"
  echo "recorded $count corpora in $MANIFEST"
  exit 0
fi

if [[ ! -f $MANIFEST ]]; then
  echo "missing manifest: $MANIFEST (run with --record)" >&2
  exit 2
fi
# -c reads the names relative to the current directory.
(cd "$OUT" && sha256sum -c "$MANIFEST" --quiet)
echo "nine corpora: $count targets byte-identical"
