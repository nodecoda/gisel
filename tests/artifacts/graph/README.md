# `gisel graph --json` goldens

These are the pre/post-`candidates`-move outputs of `gisel graph --json`.
They exist so a change to the value set, the class partition, or the
successor computation is a byte diff, not an opinion.

| file | command |
|---|---|
| `x86-none.json` | `gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none --json` |
| `riscv-rv64gc.json` | `gisel graph tests/corpus/RISCVLegalizerInfo.gisel --emit=core --features tests/cases/riscv-features.json --config rv64gc --json` |

Both runs exit 1 because `--check-closure` (the default) finds violations:
272 on x86/none and 2,864 on riscv/rv64gc. That is recorded here on purpose;
`cycles=0` is only a conditional statement until closure holds.

Regenerate with `tools/check-graph-golden.sh --record`; verify with
`tools/check-graph-golden.sh`. `SHA256` pins the checked-in bytes so a golden
cannot be "fixed" by hand to make a failing migration pass.
