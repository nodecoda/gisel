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
| M2 | `--emit=check` | the `-gen-legalizer-check` JSON | done |
| M3 | `--emit=table` | the `-gen-legalizer-table` fragment | done |
| M4 | `--emit=core`, `eval` | core JSON (modulo `origin`) / 9632-point differential | done |

`tests/artifacts/` holds the eight frozen artifacts and their `SHA256`;
`tests/artifacts/SHA256` is the oracle every backend is measured against.

```sh
python3 -m unittest discover -q -s tests      # 20 gates, ~4 s
sha256sum -c tests/artifacts/SHA256           # 8/8
```

## Evaluating without LLVM

`--emit=core` produces the schema-0.4 normal form, and `gisel eval` answers
queries against it without any LLVM binary:

```sh
gisel gen tests/corpus/AArch64LegalizerInfo.gisel --emit=core --out a.core.json
gisel eval --doc a.core.json \
  --features tests/cases/features.json --cases tests/cases/a64_ref_dump.jsonl
# cases=9632 disagreements=0 errors=0
```

`tests/cases/a64_ref_dump.jsonl` is the frozen AArch64 differential
(9632 points) dumped from the in-tree reference; `tests/cases/features.json`
is the subtarget truth table it was recorded with.

## Layout

```
gisel/dsl.py            lexer, parser, core-IR normal form
gisel/td.py             .gisel -> .td (M0, compatibility backend)
gisel/backend/llvm_inc.py  normal form -> .inc (M1)
gisel/backend/check_json.py / table.py / core_json.py   M2 / M3 / M4
gisel/eval.py           standalone evaluator (9632 points, 0 disagreements)
spec/m1-coverage.md     shim coverage of the corpus (25 triples, 0 uncovered)
spec/grammar.md         the .gisel grammar, normative
spec/semantics.md       what a rule means (and what the evaluator does)
```

Ported emitter logic keeps the LLVM license header and names its source commit
(`d48f5512a162`).
