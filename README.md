# gisel

[![ci](https://github.com/nodecoda/gisel/actions/workflows/ci.yml/badge.svg)](https://github.com/nodecoda/gisel/actions/workflows/ci.yml)

A free-form language for GlobalISel legalizer rules, and the toolchain that
turns it into LLVM artifacts **without `llvm-tblgen`**.

```sh
# from a checkout: the corpus and frozen artifacts ship with the repo,
# not with the wheel (the wheel carries the opcode table lint needs).
python3 -m pip install .        # or: python3 -m gisel (no install)
gisel gen   tests/corpus/X86LegalizerInfo.gisel --emit=inc --out x86.inc
gisel check tests/corpus/X86LegalizerInfo.gisel --emit=inc --against x86.inc
gisel gen   tests/corpus/X86LegalizerInfo.gisel --emit=td  --out X86LegalizerInfo.td
gisel lint  tests/corpus/X86LegalizerInfo.gisel   # static checks, no LLVM
```

## Five minutes

One rule set, four rules, no LLVM build, no `llvm-tblgen`:

```sh
git clone https://github.com/nodecoda/gisel && cd gisel
mkdir -p /tmp/demo && cat > /tmp/demo/hello.gisel <<'EOF'
include "llvm/Target/LegalizerInfo.td"
include "llvm/Target/Target.td"

feature Is64Bit = Subtarget.is64Bit()
type I32 = LLT::scalar(32)
type I64 = LLT::scalar(64)

ruleset X_ADD: G_ADD
    legal in(slot(0), I32)
    legal (feature("Subtarget.is64Bit()") and in(slot(0), I64))
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

`--emit=td`, `--emit=check`, `--emit=table` and `--emit=core` give the other four
shapes from the same source.

What it does not do: it is not the build path for upstream LLVM (the `.td` is
still what the tree consumes), `import-cxx` refuses any statement it cannot
translate rather than guessing, and none of the five corpora is an independent
hand-written second statement -- they are bootstrapped, imported or transcribed.

## Status

| milestone | backend | gate | state |
|---|---|---|---|
| M0 | `--emit=td` | byte-identical to the generated `.td` | done |
| M1 | `--emit=inc` | byte-identical to `-gen-legalizer` | done |
| M2 | `--emit=check` | the `-gen-legalizer-check` JSON | done |
| M3 | `--emit=table` | the `-gen-legalizer-table` fragment | done |
| M4 | `--emit=core`, `eval` | core JSON (modulo `origin`) / 34,776-point differential, 0 disagreements | done |
| v0.2 | `lint` | 57 node kinds, 0 errors on both corpora | done |
| v0.3 | `imm` axis | M68k 13/13, WebAssembly 109/109 transcribed from C++ | done |
| v0.4 | `import-cxx` | RISCV: 340 builder calls → 402 rules, 0 refused, `.inc` compiles | done |

`tools/import-inventory.py` answers "what would it cost to migrate target X?" by
censusing a hand-written constructor (method histogram, chain shapes, guards);
`tools/import-cxx.py` does the migration itself: it parses a `*LegalizerInfo.cpp`
constructor and writes `.gisel`, refusing (exit 1) any statement it cannot
translate.  `docs/REPORT-riscv.md` records both for the largest remaining
target: 340 builder calls → 402 rules, 0 refusals, and the generated `.inc`
compiles against the unmodified `LegalizerInfo.h`.

`tests/artifacts/` holds the eight frozen artifacts and their `SHA256`; the
corpus is derivable, not hand-tuned: `gisel bootstrap` reproduces both `.gisel`
files byte for byte from the frozen `.td` + core JSON (asserted in the suite).
`tests/artifacts/SHA256` (relative paths) is the oracle every backend is measured
against; `tools/refresh-oracle.sh` re-derives it from a built LLVM tree (development
only — generation never runs llvm-tblgen).

```sh
python3 -m unittest discover -q -s tests      # 57 gates, ~10 s
(cd tests/artifacts && sha256sum -c SHA256)   # 8/8
```

`gisel lint` runs the J1/J2b/J3a/J3b checks over the normal form and prints
`path:line: RULESET: message` (exit 1 on errors, 2 on parse/IO).  It needs no
LLVM source tree: the opcode arity table ships in `gisel/data/`.

Errors point at the source, not at a synthetic string:

```
$ gisel gen bad.gisel --emit=td --out x.td
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
