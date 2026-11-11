# gisel

设计论证：[文章链接](https://zhuanlan.zhihu.com/p/2102431370098298974)

[简体中文](README.zh.md)

[![ci](https://github.com/nodecoda/gisel/actions/workflows/ci.yml/badge.svg)](https://github.com/nodecoda/gisel/actions/workflows/ci.yml)

A free-form language for GlobalISel legalizer rules, and the toolchain that
turns it into LLVM artifacts **without `llvm-tblgen`**.

gisel has two functions: turn a `.gisel` file into rule artifacts
(`gen`/`check`/`lint`) and generate test cases (`cases`/`domain`).  Importing
LLVM's hand-written legalizer into `.gisel` and the two-implementation A/B
live in the workbench (`tools/`) and are not part of gisel — see
[docs/SCOPE.md](docs/SCOPE.md) for the boundary and the rule that keeps it
fixed.
The loop those tools implement (pin → cases → A/B → attribution) is in
[docs/LOOP.md](docs/LOOP.md).

```sh
# from a checkout: the corpus and frozen artifacts ship with the repo,
# not with the wheel (the wheel carries the opcode and shape tables lint needs).
python3 -m pip install .        # or: python3 -m gisel (no install)
gisel gen   tests/corpus/X86LegalizerInfo.gisel --emit=inc --out x86.inc
gisel check tests/corpus/X86LegalizerInfo.gisel --emit=inc --against x86.inc
gisel lint  tests/corpus/X86LegalizerInfo.gisel   # static checks, no LLVM
gisel cases tests/corpus/X86LegalizerInfo.gisel --out x86.cases.jsonl \
            --features tests/cases/x86-features.json   # equivalence/boundary/outside
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

`--emit=check` and `--emit=core` give the other two shapes from the same
source.  There is no `.td` backend and no table backend: the C++ `.inc` is the
product.

## Commands

Seven commands, one product surface; `spec/cli.md` is the normative contract.

| command | what it does |
|---|---|
| `gen` | emit one artifact: `--emit=inc\|check\|core` |
| `check` | does an artifact still match the source? |
| `lint` | static checks, no artifact |
| `cases` | answerless test queries: equivalence, boundary, outside |
| `domain` | the same space as a full Cartesian enumeration |
| `eval` | answer queries against the schema-0.4 normal form |
| `graph` | build the quotient graph and look for cycles |

Exit codes are shared by all seven: `0` success, `1` the answer is "no" (stale
artifact, lint error, disagreeing answer, a cycle), `2` the run could not start
(usage, IO, syntax).  `2` is never a rule difference.

### The graph, in one command

A legalizer that widens `s24` to `s32` and then narrows it back does not time
out — it loops.  `graph` builds the finite state space (opcode × the class of
every type slot) from the normal form and runs a three-colour DFS on it:

```sh
gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none
gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none \
  --inject-edge                 # negative control: must report a 2-cycle
gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none \
  --check-closure               # the successor must be a function of the state
```

`spec/graph.md` is the contract, `docs/REPORT-graph.md` the evidence.  When
`--check-closure` fails, the graph has holes: `cycles=0` is then a statement
about the partition that was checked, not a proof about the whole domain.

## Architecture

The front end (`gisel/ast.py`) parses `.gisel` into one model: a `Program` of
declarations, rule sets and rules.  Types are structured (`Scalar(32)`,
`Pointer(0, None)`, `Vector(...)`), rule type positions hold those values, and
a rule set is `(name, opcodes, rules)`.  Record names such as `X86_s32`,
`LegalizeFeature<...>` and `LegalizeRuleSet<...>` are not part of the model:
the C++ renderer computes declaration names at its exit through `NameTable`,
and `core`/`check` never see them.  `ast.canonicalize_rulesets` is the
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

Proving that two legalizer implementations answer the same way is done *with*
gisel, not by gisel: `ab/` freezes an answerless query set, runs the
official build and the build carrying the generated `.inc` on that same file,
and compares the two answer streams.  Both directions are closed for X86,
AArch64 and RISC-V: `ab/docs/EVIDENCE-WP2.md` asks gisel's own questions
(no rule is missing upstream), `ab/docs/EVIDENCE-U.md` asks the oracle's
questions (no upstream rule is missing in gisel).  That workbench has its own
report, `docs/REPORT-ab.md`; `docs/SCOPE.md` is the boundary.

What it does not do: it does not generate the `.td` (that backend was
removed), `import-cxx` refuses any statement it cannot translate rather than
guessing, and none of the nine corpora is an independent hand-written second
statement -- they were extracted from LLVM's hand-written C++ constructors
with our own tooling as a preparation for self-proof.  All of them go straight
from the hand-written `.cpp` constructor to `.gisel`
(`upstream-source/import/import-cxx.py`); the `.td` this project once added in between is no
longer used.  `docs/CORPORA.md` says, per corpus, which upstream file it was
extracted from, which reviewed deviations it carries, and what its frozen
artifacts can and cannot prove (all three are self-baselines; rule fidelity
comes from import-cxx --check and the end-to-end A/B).

## Status

| milestone | backend | gate | state |
|---|---|---|---|
| M1 | `--emit=inc` | self-baseline + end-to-end A/B (was: byte-identical to `-gen-legalizer`) | done |
| M2 | `--emit=check` | self-baseline counters (was: the `-gen-legalizer-check` JSON) | done |
| M3 | ~~`--emit=table`~~ | removed 2026-11-09: the table direction is gone, `inc` is the product | dropped |
| M4 | `--emit=core`, `eval` | core JSON (modulo `origin`); evaluator answers any question file | done |
| v0.2 | `lint` | 57 node kinds, 0 errors on all nine corpora | done |
| v0.3 | `imm` axis | M68k 13/13, WebAssembly 109/109 transcribed from C++ | done |
| v0.4 | RISCV corpus (workbench import) | 340 builder calls → 402 rules, 0 refused, `.inc` compiles | done |
| v0.5 | `cases` | equivalence/boundary/outside; X86 3,019 cases, AArch64 12,559 cases | done |
| v0.6 | more A/B targets | M68k 35, WebAssembly 886, PowerPC 94, ARM 1,614, Mips 1,656, SPIRV 5,136 queries; `disagree = 0` on each | done |

`-gen-legalizer*` in the M1–M3 rows is this project's TableGen backend
(`utils/TableGen/LegalizerInfoEmitter.cpp` on the LLVM research branch), not an
upstream-main feature; `docs/CORPORA.md` has the full chain.

Migration and A/B tooling is **workbench**, not a gisel function
(`docs/SCOPE.md`): `upstream-source/import/import-inventory.py` prices a target,
`upstream-source/import/import-cxx.py` turns a constructor into `.gisel` (refusing, exit 1,
any statement it cannot translate), and `ab/` compares two
implementations.  `import-cxx` is a one-shot transcriber for the pinned
constructors, not a general C++ parser: `--all --check` re-transcribes them
and diffs the checked-in corpora, and a rule-count drift fails loudly.  The evidence lives in `docs/REPORT-riscv.md` and
`docs/REPORT-ab.md`.  The transcriber moved to the sibling `upstream-source`
checkout in November 2026; `tools/import-cxx.py` is a one-release forwarding
shim, not an implementation.

`tests/artifacts/` holds the nine frozen C++/JSON artifacts and their
`SHA256`: three each for X86, AArch64 and RISC-V.  Upstream LLVM main has no
legalizer `.td` and no `-gen-legalizer`; the rules live in hand-written
`*LegalizerInfo.cpp` constructors, and the corpora are transcribed from those.
The artifacts are therefore gisel's own frozen output — a drift baseline, not
a byte oracle against a second implementation.  Rule fidelity is checked on
two other layers: `upstream-source import --check` re-transcribes the pinned C++
and must reproduce the checked-in `.gisel` byte for byte, and `ab/`
builds the official legalizer and the one carrying our `.inc`, feeds both the
same answerless query file, and compares the answer streams.
`docs/CORPORA.md` has the chain and the reviewed deviations.

```sh
python3 -m pytest -q                          # 243 passed, 92 subtests
python3 -m unittest discover -q -s tests      # Ran 243 tests
(cd tests/artifacts && sha256sum -c SHA256)   # 9/9
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
gisel cases tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json --out a.cases.jsonl
gisel eval --doc a.core.json --features tests/cases/features.json \
  --cases a.cases.jsonl --answers a.answers.jsonl
# cases=... errors=0
```

`gisel cases` produces questions, not answers.  `--answers` writes what the
evaluator says in the same JSONL shape a compiled runner writes, so
`ab/diff.py` can compare the two answer streams:

```sh
python3 ../ab/diff.py runner.answers.jsonl a.answers.jsonl --json
```

When a runner has already answered the same question file, `gisel cases
--against answers.jsonl` compares only the overlap; `uncovered` is reported
separately and is never counted as a pass.

## Layout

```
gisel/ast.py            Program / declarations / rule sets / structured LLT
gisel/dsl.py            lexer, rule parser, core-IR normal form
gisel/backend/llvm_inc.py  AST -> .inc (M1)
gisel/backend/check_json.py / core_json.py              M2 / M4
gisel/eval.py           standalone evaluator (answers any question file)
gisel/cases.py          equivalence/boundary/outside case generation
gisel/answers.py        answer-file reader (the A/B comparison is ab/diff.py)
gisel/contract.py       shape contract: which type tuples are questions
gisel/domain.py         opcode-slot cartesian enumeration (the other question set)
gisel/graph.py          quotient graph over (opcode, type classes, mem, imm)
gisel/data/opcode-slots.json   283-opcode arity/slot snapshot
gisel/data/contract-shapes.jsonc / contract-aarch64.jsonc  shape tables
spec/m1-coverage.md     shim coverage of the corpus (25 triples, 0 uncovered)
spec/cli.md             the command surface, exit codes, guarantees (normative)
spec/grammar.md         the .gisel grammar and AST, normative
spec/axes.md            the axis/profile format and its compatibility pin
spec/cases.md           what a generated case means, and the subset contract
spec/cases-format.md    the three JSONL projections and their shared key
spec/contract.md        shape contract: which tuples are questions at all
spec/escape-points.md   feature vs opaque: the two host escape points
spec/graph.md           the quotient-graph state, successor and outcomes
spec/semantics.md       what a rule means (and what the evaluator does)
docs/CORPORA.md         per-corpus source, deviations, and evidence layers
docs/LOOP.md            pin -> questions -> A/B -> attribution
docs/REPORT-ast.md      the AST migration: removals, rejected options, boundaries
docs/REPORT-no-td.md    the .td renderer removal and the remaining frozen text
docs/REPORT-cxx-corpus.md  C++ -> .gisel transcription (workbench tool)
docs/ALGORITHM-cases.md  case generation as a bounded quotient (article source)
docs/REPORT-cases.md    case generation: evidence, rejected options
docs/REPORT-coverage.md coverage evidence for the case set
docs/REPORT-graph.md    quotient-graph evidence and the cycle history
docs/DESIGN-graph.md    graph design record
docs/REQUIREMENTS-ab.md  workbench: the differential-testing requirement
docs/REPORT-ab.md       workbench: end-to-end A/B (not a gisel feature)
docs/PLAN-architecture.md  the Phase 1-2 cleanup plan (decisions, PR order)
docs/PLAN-internal-authority.md  fork 内部权威：双向题面、负控、oracle 保全
docs/PROPOSAL-host-escape.md  rejected host-escape proposal (AMDGPU)
docs/SCOPE.md           what gisel is, what only uses it
```

Ported emitter logic keeps the LLVM license header and names its source commit
(`d48f5512a162`).
