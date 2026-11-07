# gisel

设计论证：[文章链接](https://zhuanlan.zhihu.com/p/2102431370098298974)

[![ci](https://github.com/nodecoda/gisel/actions/workflows/ci.yml/badge.svg)](https://github.com/nodecoda/gisel/actions/workflows/ci.yml)

A free-form language for GlobalISel legalizer rules, and the toolchain that
turns it into LLVM artifacts **without `llvm-tblgen`**.

```sh
# from a checkout: the corpus and frozen artifacts ship with the repo,
# not with the wheel (the wheel carries the opcode table lint needs).
python3 -m pip install .        # or: python3 -m gisel (no install)
gisel gen   tests/corpus/X86LegalizerInfo.gisel --emit=inc --out x86.inc
gisel check tests/corpus/X86LegalizerInfo.gisel --emit=inc --against x86.inc
gisel lint  tests/corpus/X86LegalizerInfo.gisel   # static checks, no LLVM
gisel cases tests/corpus/X86LegalizerInfo.gisel --out x86.cases.jsonl \
            --features tests/cases/x86-features.json \
            --against tests/cases/x86_ref_dump.jsonl   # equivalence/boundary/outside
```

## Five minutes

One rule set, four rules, no LLVM build, no `llvm-tblgen`:

```sh
git clone https://github.com/nodecoda/gisel && cd gisel
mkdir -p /tmp/demo && cat > /tmp/demo/hello.gisel <<'EOF'
feature Is64Bit = Subtarget.is64Bit()
type I32 = LLT::scalar(32)
type I64 = LLT::scalar(64)

ruleset X_ADD: G_ADD
    legal in(slot(0), I32)
    legal (Is64Bit and in(slot(0), I64))
    widen(slot(0), pow2_min(32))
    scalarize(slot(0))
EOF

python3 -m gisel lint /tmp/demo/hello.gisel
# /tmp/demo/hello.gisel: 0 error(s), 0 warning(s), 4 rule(s)

python3 -m gisel gen   /tmp/demo/hello.gisel --emit=inc --out /tmp/demo/hello.inc
python3 -m gisel check /tmp/demo/hello.gisel --emit=inc --against /tmp/demo/hello.inc
# /tmp/demo/hello.inc: up to date
```

The generated `.inc` is the C++ chain, one call per rule:

```cpp
  bool Is64Bit = Subtarget.is64Bit();

  const LLT I32 = LLT::scalar(32);
  const LLT I64 = LLT::scalar(64);

  getActionDefinitionsBuilder(G_ADD)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == I32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == I64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .scalarize(0);
```

`--emit=check`, `--emit=table` and `--emit=core` give the other three
shapes from the same source.  There is no `.td` backend: the C++ `.inc` is the
product.

## Architecture

The front end (`gisel/ast.py`) parses `.gisel` into one model: a `Program` of
declarations, rule sets and rules.  Types are structured (`Scalar(32)`,
`Pointer(0, None)`, `Vector(...)`), rule type positions hold those values, and
a rule set is `(name, opcodes, rules)`.  Record names such as `X86_s32`,
`LegalizeFeature<...>` and `LegalizeRuleSet<...>` are not part of the model:
the C++ renderer computes declaration names at its exit through `NameTable`,
and `core`/`check`/`table` never see them.  `ast.canonicalize_rulesets` is the
one AST transform before emission; it exists to keep the emitted C++ and the
frozen core JSON at one table per opcode, not because the language forbids it.
`docs/REPORT-ast.md` records the AST migration; `docs/REPORT-no-td.md` records
the removal of the `.td` renderer.

Test cases are derived from that same model, not written by hand:
`gisel cases` emits one representative per equivalence class (rule region),
boundaries where the answer actually flips (`N-1`/`N+1` on bits, lanes,
memory size and alignment), and outside probes that fall through to
`Unsupported`.  `--against` compares only the overlap with an oracle dump;
`uncovered` is reported separately and is never counted as a pass.
`spec/cases.md` is the contract, `docs/REPORT-cases.md` the evidence.

For the end-to-end X86 check, first freeze an answerless JSONL query set, then
run the official build and the build containing the generated `.inc` on that
same file. The query file is the test set; it does not expand into thousands
of `.ll` or `.mir` files. `tools/ab/` contains the snapshot, replacement,
runner, and diff scripts. `run-end-to-end.sh` captures official answers before
replacing the shared library, then captures ours and runs the full diff. Queries
that assert in both builds remain in the stream as symmetric `unanswerable`
results.

For AArch64, the fixed domain comes from LLVM's generated
`AArch64LegalizerTablePointsForTest.inc`, not from a Cartesian product. The
algorithm filters each of its 1,190 points by the nine fixed configurations,
serializes LLTs canonically, removes duplicate
`(config, opcode, types, mem, imms)` keys, and requires the resulting 9,591
queries. A changed count stops the run for review. Both answerers then consume
that saved JSONL file.

What it does not do: it does not generate the upstream `.td` (that backend was
removed), `import-cxx` refuses any statement it cannot translate rather than
guessing, and none of the five corpora is an independent hand-written second
statement -- they were bootstrapped, imported or transcribed before the
bootstrap reader was removed.

## Status

| milestone | backend | gate | state |
|---|---|---|---|
| M1 | `--emit=inc` | byte-identical to `-gen-legalizer` | done |
| M2 | `--emit=check` | the `-gen-legalizer-check` JSON | done |
| M3 | `--emit=table` | the `-gen-legalizer-table` fragment | done |
| M4 | `--emit=core`, `eval` | core JSON (modulo `origin`) / 34,776-point differential, 0 disagreements | done |
| v0.2 | `lint` | 57 node kinds, 0 errors on both corpora | done |
| v0.3 | `imm` axis | M68k 13/13, WebAssembly 109/109 transcribed from C++ | done |
| v0.4 | `import-cxx` | RISCV: 340 builder calls → 402 rules, 0 refused, `.inc` compiles | done |
| v0.5 | `cases` | equivalence/boundary/outside; X86 3,278 cases (375 oracle-covered), AArch64 10,920 cases (645 oracle-covered), 0 disagreements | done |

`tools/import-inventory.py` answers "what would it cost to migrate target X?" by
censusing a hand-written constructor (method histogram, chain shapes, guards);
`tools/import-cxx.py` does the migration itself: it parses a `*LegalizerInfo.cpp`
constructor and writes `.gisel`, refusing (exit 1) any statement it cannot
translate.  `docs/REPORT-riscv.md` records both for the largest remaining
target: 340 builder calls → 402 rules, 0 refusals, and the generated `.inc`
compiles against the unmodified `LegalizerInfo.h`.

`tests/artifacts/` holds the eight frozen C++/JSON artifacts and their
`SHA256`.  They are the oracle every backend is measured against.  The corpus
is frozen as historical input; the `.td` bootstrap reader was removed, so the
corpus is no longer regenerated from `.td`.  `tools/refresh-oracle.sh` can
re-derive the C++/JSON oracle from a built LLVM tree (development only —
generation never runs llvm-tblgen).

```sh
python3 -m unittest discover -q -s tests      # 90 tests, ~12 s
(cd tests/artifacts && sha256sum -c SHA256)   # 8/8
```

`gisel lint` runs the J1/J2b/J3a/J3b checks over the normal form and prints
`path:line: RULESET: message` (exit 1 on errors, 2 on parse/IO).  It needs no
LLVM source tree: the opcode arity table ships in `gisel/data/`.

Errors point at the source, not at a synthetic string:

```
$ gisel gen bad.gisel --emit=inc --out x.inc
bad.gisel:6: expected ,, got ID ('pow2')      # exit 2
```

## Evaluating without LLVM

`--emit=core` produces the schema-0.4 normal form, and `gisel eval` answers
queries against it without any LLVM binary:

```sh
gisel gen tests/corpus/AArch64LegalizerInfo.gisel --emit=core --out a.core.json
gisel eval --doc a.core.json \
  --features tests/cases/features.json --cases tests/cases/a64_ref_dump.jsonl
# cases=9632 disagreements=0 errors=0

gisel gen tests/corpus/X86LegalizerInfo.gisel --emit=core --out x.core.json
gisel eval --doc x.core.json \
  --features tests/cases/x86-features.json --cases tests/cases/x86_ref_dump.jsonl
# cases=5632 disagreements=0 errors=0
```

`tests/cases/a64_ref_dump.jsonl` is the frozen AArch64 differential
(9632 points) dumped from the in-tree reference; `tests/cases/features.json`
is the subtarget truth table it was recorded with.

## Layout

```
gisel/ast.py            Program / declarations / rule sets / structured LLT
gisel/dsl.py            lexer, rule parser, core-IR normal form
gisel/backend/llvm_inc.py  AST -> .inc (M1)
gisel/backend/check_json.py / table.py / core_json.py   M2 / M3 / M4
gisel/eval.py           standalone evaluator (9632 points, 0 disagreements)
gisel/cases.py          equivalence/boundary/outside case generation
spec/m1-coverage.md     shim coverage of the corpus (25 triples, 0 uncovered)
spec/grammar.md         the .gisel grammar and AST, normative
spec/cases.md           what a generated case means, and the subset contract
docs/REPORT-ast.md      the AST migration: removals, rejected options, boundaries
docs/REPORT-no-td.md    the .td renderer removal and the remaining frozen text
docs/REPORT-cases.md    case generation: algorithm, evidence, rejected options
spec/semantics.md       what a rule means (and what the evaluator does)
```

Ported emitter logic keeps the LLVM license header and names its source commit
(`d48f5512a162`).
