#!/usr/bin/env bash
set -euo pipefail

# tools/check-cases-golden.sh [--record] [TARGET...]
#
# Regenerate the answerless query files the reports quote and compare their
# sha256 with tests/artifacts/cases/SHA256.  TARGET is x86, aarch64 or riscv;
# no argument means all three.
#
# The counts are in docs/REPORT-cases.md; this gate is about the bytes.  A
# changed query file is not automatically wrong, but it must be re-recorded
# in the same commit as the explanation.

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RECORD=0
TARGETS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --record) RECORD=1; shift ;;
    x86|aarch64|riscv) TARGETS+=("$1"); shift ;;
    *) echo "usage: $0 [--record] [x86|aarch64|riscv ...]" >&2; exit 2 ;;
  esac
done
[[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=(x86 aarch64 riscv)

OUT=$(mktemp -d "${TMPDIR:-/tmp}/gisel-cases.XXXXXX")
trap 'python3 -c "import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)" "$OUT"' EXIT

cd "$ROOT"
pids=()
for target in "${TARGETS[@]}"; do
  case "$target" in
    x86)
      args=(tests/corpus/X86LegalizerInfo.gisel
            --features tests/cases/x86-features.json) ;;
    aarch64)
      args=(tests/corpus/AArch64LegalizerInfo.gisel
            --features tests/cases/features.json
            --axes tests/cases/aarch64-mem-orderings.axes.json) ;;
    riscv)
      args=(tests/corpus/RISCVLegalizerInfo.gisel
            --features tests/cases/riscv-features.json) ;;
  esac
  (
    python3 -m gisel cases "${args[@]}" --out "$OUT/$target.cases.jsonl" \
      > "$OUT/$target.log" 2>&1
  ) &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || true; done

status=0
for target in "${TARGETS[@]}"; do
  if [[ ! -s "$OUT/$target.cases.jsonl" ]]; then
    echo "cases $target: no output" >&2
    cat "$OUT/$target.log" >&2
    status=1
    continue
  fi
  sha=$(sha256sum "$OUT/$target.cases.jsonl" | cut -d' ' -f1)
  if [[ $RECORD -eq 1 ]]; then
    continue
  fi
  want=$(awk -v name="$target.cases.jsonl" '$2 == name {print $1}' \
    tests/artifacts/cases/SHA256)
  if [[ -z $want ]]; then
    echo "cases $target: missing from tests/artifacts/cases/SHA256" >&2
    status=1
  elif [[ $sha != "$want" ]]; then
    echo "cases $target: sha256 $sha, recorded $want" >&2
    echo "  $(grep -c . "$OUT/$target.cases.jsonl") lines; see docs/REPORT-cases.md" >&2
    status=1
  else
    echo "cases $target: $sha matches"
  fi
done

if [[ $RECORD -eq 1 ]]; then
  {
    for target in "${TARGETS[@]}"; do
      [[ -s "$OUT/$target.cases.jsonl" ]] || continue
      sha256sum "$OUT/$target.cases.jsonl" |
        sed "s#  .*/#  #"
    done
  } | sort -k2 > "$ROOT/tests/artifacts/cases/SHA256"
  echo "cases goldens: recorded ${TARGETS[*]}"
fi
exit $status
