# `gisel graph --json` goldens

These are the outputs of `gisel graph --json` on three configurations, in two
partitions. They exist so a change to the value set, the class partition, the
successor computation, or the closure audit is a byte diff, not an opinion.

| file | command | rc | closure |
|---|---|---|---|
| `x86-none.json` | `gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none --json` | 1 | 272 = 45 outside + 227 partition |
| `riscv-rv64gc.json` | `gisel graph tests/corpus/RISCVLegalizerInfo.gisel --emit=core --features tests/cases/riscv-features.json --config rv64gc --json` | 1 | 2,864 = 2,254 outside + 610 partition |
| `wasm-wasm32.json` | `gisel graph tests/corpus/WebAssemblyLegalizerInfo.gisel --emit=core --features tests/cases/wasm-features.json --config wasm32 --json` | 1 | 302 = 134 outside + 168 partition |
| `x86-none-refine.json` | same as the first, plus `--refine` | 0 | 0 |
| `riscv-rv64gc-refine.json` | same as the second, plus `--refine` | 0 | 0 |

## Two statements, not one

The default partition answers "are there cycles on the finite axes we declared?"
It is **not** a closed quotient: closure reports where a class member lands in a
different outcome or an undeclared type, and the run exits 1. That is recorded
on purpose, not a failing golden.

The refined partition splits those classes until every member has one successor
class. It exits 0 with `closure.count == 0`, so the signed statement is:

> `cycles = 0` on the declared axes, with the class partition closed under the
> mutation (`--refine`), and `outside` reported separately.

`--refine` does not make every mutation land inside the domain. `outside`
increases (2,240 on x86, 3,622 on riscv) and those states have no outgoing edge:
they are sinks, so they cannot create a cycle. They are counted, never silently
dropped.

## Regenerating

`tools/check-graph-golden.sh --record` rewrites all five files and `SHA256`;
`tools/check-graph-golden.sh` reruns the commands and compares bytes. The
script also asserts the exit code per family and `closure.count ==
sum(closure.kinds)`, so neither "record a red run as green" nor "record a green
run as red" passes. `SHA256` pins the checked-in bytes so a golden cannot be
"fixed" by hand to make a failing migration pass.
