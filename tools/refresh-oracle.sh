#!/usr/bin/env bash
# Regenerate tests/artifacts/ from the checked-in corpora.
#
# DEVELOPMENT ONLY.  CI never runs this: the artifacts are the drift baseline
# and only move when a corpus or the generator intentionally changes.
#
# The oracle used to be `llvm-tblgen -gen-legalizer*` output over a `.td` this
# project no longer keeps.  That backend and its `.td` are retired, so the
# baseline is now gisel's own output for the same three corpora; rule fidelity
# is gated by tests/test_import_cxx.py and the end-to-end harness in ab/.
#
#   tools/refresh-oracle.sh        # writes tests/artifacts/, then review git diff
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
OUT=${OUT:-$HERE/tests/artifacts}

mkdir -p "$OUT"
for pair in x86:X86LegalizerInfo aarch64:AArch64LegalizerInfo riscv:RISCVLegalizerInfo; do
  lowercase=${pair%%:*}
  name=${pair##*:}
  for emit in inc check core; do
    case $emit in
      inc) file=$lowercase.inc ;;
      check) file=$lowercase.check.json ;;
      core) file=$lowercase.core.json ;;
    esac
    ( cd "$HERE" && python3 -m gisel gen "tests/corpus/$name.gisel" \
        --emit="$emit" --out "$OUT/$file" )
  done
done

( cd "$OUT" &&
  sha256sum aarch64.inc aarch64.check.json aarch64.core.json \
            riscv.inc riscv.check.json riscv.core.json \
            x86.inc x86.check.json x86.core.json > SHA256 )

echo "oracle refreshed in $OUT"
echo "review \`git diff tests/artifacts\` before committing"
