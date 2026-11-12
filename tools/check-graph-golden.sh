#!/usr/bin/env bash
set -euo pipefail

# tools/check-graph-golden.sh [--record] [--out DIR]
#
# Regenerate the four graph goldens and compare bytes with the checked-in
# copies.  Two families are recorded on purpose:
#
#   * the default partition (no --refine) finds no cycle but leaves closure
#     violations; those runs exit 1 and the count is the coverage gap;
#   * the refined partition makes the successor a function of the state, so
#     the run exits 0 with closure.count == 0.
#
# Exit 2 is a usage/parse error and always fails this gate.  Exit 1 is only
# accepted for the no-refine family, and only when that family still reports
# the recorded closure gap.

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

# name | expected rc | arguments
CASES=(
  "x86-none|1|tests/corpus/X86LegalizerInfo.gisel --emit=core --config none"
  "riscv-rv64gc|1|tests/corpus/RISCVLegalizerInfo.gisel --emit=core --features tests/cases/riscv-features.json --config rv64gc"
  "x86-none-refine|0|tests/corpus/X86LegalizerInfo.gisel --emit=core --config none --refine"
  "riscv-rv64gc-refine|0|tests/corpus/RISCVLegalizerInfo.gisel --emit=core --features tests/cases/riscv-features.json --config rv64gc --refine"
)

# The four runs are independent and dominated by two ~200 s RISC-V cases.
# Launch them together and check them in order; the recorded rc files keep
# the failure report deterministic.  Peak RSS is bounded by the two RISC-V
# runs (~1.5 GB each) plus one X86 run, well under a 7 GB runner.
pids=()
for entry in "${CASES[@]}"; do
  IFS='|' read -r name _ args <<< "$entry"
  (
    rc=0
    # shellcheck disable=SC2086
    python3 -m gisel graph $args --json > "$OUT/$name.json" 2> "$OUT/$name.err" || rc=$?
    echo "$rc" > "$OUT/$name.rc"
  ) &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || true; done

for entry in "${CASES[@]}"; do
  IFS='|' read -r name want_rc args <<< "$entry"
  rc=$(cat "$OUT/$name.rc")
  if [[ $rc -ne $want_rc ]]; then
    echo "graph $name: rc=$rc, expected $want_rc" >&2
    cat "$OUT/$name.err" >&2
    exit 1
  fi
  python3 - "$OUT/$name.json" "$name" "$want_rc" <<'PY'
import json
import sys

path, name, want = sys.argv[1], sys.argv[2], int(sys.argv[3])
reports = json.load(open(path))["reports"]
if not reports:
    raise SystemExit("%s: no reports" % name)
for report in reports:
    closure = report["closure"]
    if not closure["checked"]:
        raise SystemExit("%s: closure was not checked" % name)
    total = sum(closure["kinds"].values())
    if total != closure["count"]:
        raise SystemExit("%s: closure.count=%d but kinds sum to %d"
                         % (name, closure["count"], total))
    if want == 0:
        if report["cycles"] or closure["count"]:
            raise SystemExit("%s: expected a closed graph, got cycles=%d "
                             "closure=%d" % (name, report["cycles"],
                                             closure["count"]))
    elif closure["count"] == 0:
        raise SystemExit("%s: expected a recorded closure gap, got none" % name)
PY
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
  echo "graph goldens: recorded (2 default, 2 refined)"
else
  echo "graph goldens: 4 configurations byte-identical (2 default, 2 refined)"
fi
