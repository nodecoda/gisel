# gisel

A free-form language for GlobalISel legalizer rules, and the toolchain that
turns it into LLVM artifacts **without `llvm-tblgen`**.

```sh
gisel gen   tests/corpus/X86LegalizerInfo.gisel --emit=inc --out x86.inc
gisel check tests/corpus/X86LegalizerInfo.gisel --emit=inc --against x86.inc
gisel gen   tests/corpus/X86LegalizerInfo.gisel --emit=td  --out X86LegalizerInfo.td
```

## Status

| milestone | backend | gate | state |
|---|---|---|---|
| M0 | `--emit=td` | byte-identical to the generated `.td` | done |
| M1 | `--emit=inc` | byte-identical to `-gen-legalizer` | done |
| M2 | `--emit=check` | the `-gen-legalizer-check` JSON | planned |
| M3 | `--emit=table` | the `-gen-legalizer-table` fragment | done |
| M4 | `--emit=core`, `eval` | core JSON / 9632-point differential | scoped (`spec/m4-scope.md`) |

`tests/artifacts/` holds the eight frozen artifacts and their `SHA256`;
`tests/artifacts/SHA256` is the oracle every backend is measured against.

```sh
python3 -m unittest discover -q -s tests      # 9 gates
sha256sum -c tests/artifacts/SHA256           # 8/8
```

## Layout

```
gisel/dsl.py            lexer, parser, core-IR normal form
gisel/td.py             .gisel -> .td (M0, compatibility backend)
gisel/backend/llvm_inc.py  normal form -> .inc (M1)
gisel/eval.py           standalone evaluator (9632 points, 0 disagreements)
spec/m1-coverage.md     shim coverage of the corpus (25 triples, 0 uncovered)
```

Ported emitter logic keeps the LLVM license header and names its source commit
(`d48f5512a162`).
