#!/usr/bin/env bash
set -euo pipefail

# tools/check-nightly-graphs.sh [--record]
#
# The graph configurations too expensive for the PR gate.  They are pinned by
# sha256 in tests/artifacts/graph/nightly/SHA256 and run on a schedule; a
# changed file is a coverage change and must be re-recorded with an
# explanation in docs/REPORT-graph.md.

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RECORD=0
[[ ${1:-} == "--record" && $# -eq 1 ]] && RECORD=1
[[ $# -gt 1 || ( $# -eq 1 && $RECORD -eq 0 ) ]] && {
  echo "usage: $0 [--record]" >&2; exit 2; }

OUT=$(mktemp -d "${TMPDIR:-/tmp}/gisel-nightly.XXXXXX")
trap 'python3 -c "import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)" "$OUT"' EXIT

cd "$ROOT"
CASES=(
  "aarch64-baseline|tests/corpus/AArch64LegalizerInfo.gisel --features tests/cases/features.json --config baseline --refine"
  "x86-C0|tests/corpus/X86LegalizerInfo.gisel --features tests/cases/x86-features.json --config C0 --refine"
  "x86-C1|tests/corpus/X86LegalizerInfo.gisel --features tests/cases/x86-features.json --config C1 --refine"
  "x86-C2|tests/corpus/X86LegalizerInfo.gisel --features tests/cases/x86-features.json --config C2 --refine"
  "x86-C3|tests/corpus/X86LegalizerInfo.gisel --features tests/cases/x86-features.json --config C3 --refine"
  # The other six corpora: one cheap configuration each.  SPIR-V is cases-only:
  # its graph has not finished in 15 minutes, so pinning it here would buy a
  # slow timeout, not coverage.
  "arm-neon|tests/corpus/ARMLegalizerInfo.gisel --features tests/cases/arm-features.json --config armv7a-neon --refine"
  "mips32|tests/corpus/MipsLegalizerInfo.gisel --features tests/cases/mips-features.json --config mips32 --refine"
  "ppc-default|tests/corpus/PowerPCLegalizerInfo.gisel --features tests/cases/ppc-features.json --config default --refine"
  "m68k-default|tests/corpus/M68kLegalizerInfo.gisel --features tests/cases/m68k-features.json --config default --refine"
  "wasm32|tests/corpus/WebAssemblyLegalizerInfo.gisel --features tests/cases/wasm-features.json --config wasm32 --refine"
)

pids=()
for entry in "${CASES[@]}"; do
  IFS='|' read -r name args <<< "$entry"
  (
    rc=0
    # shellcheck disable=SC2086
    python3 -m gisel graph $args --json > "$OUT/$name.json" \
      2> "$OUT/$name.err" || rc=$?
    echo "$rc" > "$OUT/$name.rc"
  ) &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || true; done

status=0
for entry in "${CASES[@]}"; do
  IFS='|' read -r name _ <<< "$entry"
  rc=$(cat "$OUT/$name.rc")
  if [[ $rc -ne 0 ]]; then
    echo "nightly $name: rc=$rc" >&2
    cat "$OUT/$name.err" >&2
    status=1
    continue
  fi
  python3 - "$OUT/$name.json" "$name" <<'PY' || status=1
import json
import sys
path, name = sys.argv[1:3]
reports = json.load(open(path))["reports"]
for report in reports:
    closure = report["closure"]
    if report["cycles"] or closure["count"]:
        raise SystemExit("%s: cycles=%d closure=%d (expected a closed graph)"
                         % (name, report["cycles"], closure["count"]))
PY
  sha=$(sha256sum "$OUT/$name.json" | cut -d' ' -f1)
  if [[ $RECORD -eq 1 ]]; then
    echo "$sha  $name.json" >> "$OUT/manifest"
    continue
  fi
  want=$(awk -v name="$name.json" '$2 == name {print $1}' \
    tests/artifacts/graph/nightly/SHA256)
  if [[ -z $want ]]; then
    echo "nightly $name: missing from tests/artifacts/graph/nightly/SHA256" >&2
    status=1
  elif [[ $sha != "$want" ]]; then
    echo "nightly $name: sha256 $sha, recorded $want" >&2
    status=1
  else
    echo "nightly $name: $sha matches"
  fi
done

if [[ $RECORD -eq 1 ]]; then
  sort -k2 "$OUT/manifest" > tests/artifacts/graph/nightly/SHA256
  echo "nightly graphs: recorded"
fi
exit $status
