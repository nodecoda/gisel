#!/usr/bin/env bash
set -euo pipefail

# tools/check-graph-golden.sh [--record] [--out DIR]
#
# Regenerate the two graph goldens and compare bytes with the checked-in
# copies.  `graph` exits 1 when `--check-closure` finds violations (both
# recorded runs do); exit 2 is a usage/parse error and must fail this gate.

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RECORD=0
OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --record) RECORD=1; shift ;;
    --out) OUT=${2:?}; shift 2 ;;
    *) echo "usage: $0 [--record] [--out DIR]" >&2; exit 2 ;;
  esac
done

cleanup=""
if [[ -z $OUT ]]; then
  OUT=$(mktemp -d "${TMPDIR:-/tmp}/gisel-graph.XXXXXX")
  cleanup=$OUT
fi
mkdir -p "$OUT"
trap 'if [[ -n $cleanup ]]; then python3 -c "import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)" "$cleanup"; fi' EXIT

cd "$ROOT"

CASES=(
  "x86-none|tests/corpus/X86LegalizerInfo.gisel --emit=core --config none"
  "riscv-rv64gc|tests/corpus/RISCVLegalizerInfo.gisel --emit=core --features tests/cases/riscv-features.json --config rv64gc"
)

for entry in "${CASES[@]}"; do
  name=${entry%%|*}
  args=${entry#*|}
  rc=0
  # shellcheck disable=SC2086
  python3 -m gisel graph $args --json > "$OUT/$name.json" 2> "$OUT/$name.err" || rc=$?
  if [[ $rc -gt 1 ]]; then
    echo "graph $name: rc=$rc" >&2
    cat "$OUT/$name.err" >&2
    exit 1
  fi
  if [[ $RECORD -eq 1 ]]; then
    cp "$OUT/$name.json" "$ROOT/tests/artifacts/graph/$name.json"
  else
    cmp "$OUT/$name.json" "$ROOT/tests/artifacts/graph/$name.json" || {
      echo "graph $name: output changed (see reported diff)" >&2
      exit 1
    }
  fi
done

if [[ $RECORD -eq 1 ]]; then
  ( cd "$ROOT/tests/artifacts/graph" && sha256sum ./*.json | sed 's#\./##' > SHA256 )
  echo "graph goldens: recorded"
else
  echo "graph goldens: 2 configurations byte-identical"
fi
