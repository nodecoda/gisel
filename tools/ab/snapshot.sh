#!/usr/bin/env bash
# Save the generated baseline include and build provenance.
#
#   snapshot.sh TREE BUILD [OUT] [--force]
set -euo pipefail

TREE=${1:?usage: snapshot.sh TREE BUILD [OUT]}
BUILD=${2:?}
OUT=${3:-$(cd "$(dirname "$0")/../.." && pwd)/.ab/baseline}
INC=$BUILD/lib/Target/X86/X86LegalizerInfo.inc
FORCE=${4:-}
if [[ -e "$OUT/X86LegalizerInfo.inc" && "$FORCE" != "--force" ]]; then
  echo "snapshot.sh: $OUT already contains a baseline; use --force to replace it" >&2
  exit 2
fi
mkdir -p "$OUT"
cp -p "$INC" "$OUT/X86LegalizerInfo.inc"
cp -p "$BUILD/bin/llc" "$OUT/llc" 2>/dev/null || true
cp -p "$BUILD/lib/libLLVMX86CodeGen.so.24.0git" \
  "$OUT/libLLVMX86CodeGen.so.24.0git" 2>/dev/null || true
sha256sum "$INC" > "$OUT/X86LegalizerInfo.inc.sha256"
TREE="$TREE" BUILD="$BUILD" HEAD="$(git -C "$TREE" rev-parse HEAD)" \
  INC_SHA256="$(sha256sum "$INC" | awk '{print $1}')" OUT="$OUT" \
  python3 - <<'PY'
import json
import os
from pathlib import Path

Path(os.environ["OUT"], "provenance.json").write_text(json.dumps({
    "tree": os.environ["TREE"],
    "build": os.environ["BUILD"],
    "git_head": os.environ["HEAD"],
    "inc_sha256": os.environ["INC_SHA256"],
}, indent=2) + "\n")
PY
cat "$OUT/provenance.json"
