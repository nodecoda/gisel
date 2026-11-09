# M3: `--emit=table` -- DONE

> 2026-11-09: `--emit=table` 已移除。本文保留为当时的范围记录；现在只有
> `inc` / `check` / `core`。
> 2026-11-10: 文中引用的冻结答案表（含 9,632 点差分）已删除，不再是门禁。

Result (2026-11-06): `gisel gen --emit=table` reproduces both fragments byte
for byte -- `x86.table.inc` 4982 lines, `aarch64.table.inc` 10765 lines -- from
`gisel/backend/table.py` (one module, ~470 lines) with no `llvm-tblgen` and no `.td` input.

Two corrections to the plan below, both found while implementing:

1. **The semantic gate is not ours to run.** The table-vs-chain differential
   already lives in the tree's unit tests (`X86LegalizerInfoDifferentialTest`,
   `AArch64LegalizerTableTest`), and it consumes the same generated fragment.
   Ran now on the current tree:
   - `AArch64Tests --gtest_filter=*Differential*`: **9632 compared, 0
     disagreements**, 114/114 tables answer, 0 opaque.
   - `X86Tests --gtest_filter=*Differential*`: 32 tests passed, corpus
     manifest 825448 atoms.
   Because the fragment is byte-identical, both hold for our output by
   construction.  A separate Python table interpreter would be a second
   implementation of the same semantics, not more evidence.
2. **`endsUnconditional` never fires on a core rule** (:7090 returns false when
   `isCoreRule(Last)`), so every evaluator ends with the `Unsupported` return.
   That is 63 and 114 tail returns, not a special case per rule set.

The reconnaissance below is what the implementation was built from.

# M3 scope: `--emit=table`

Reconnaissance for the largest remaining milestone. Everything below is read
off `LegalizerInfoEmitter.cpp:5145-7988` and the frozen artifacts, not guessed.

## What the artifact contains

`x86.table.inc` is 4982 lines, `aarch64.table.inc` 10765. Four sections, in
this order:

| section | starts at (x86 artifact) | source |
|---|---|---|
| environment signature: one bit per feature, declaration order | `:8` | `emitFeatureSignature` |
| type classes: `TableScalar/Pointer/Integer/Float/Vector` | `:~60` | `collectClasses`, `resolve` |
| memory-descriptor classes + alignment classes + slot partitions | `:79` | `collectMemClasses` |
| one evaluator per rule set | `:305` | `translateCoreRule`, `run` |

## The stages

1. `resolve` (:5157) — an LLT expression text to `TableType`s: it splits
   `?:` conditionals and pattern-matches `LLT::scalar(N)`, `pointer`,
   `integer(N)`, `float16/32/64`, `fixed_vector(N, T)`,
   `scalable_vector(N, T)`, `scalarOrVector(ElementCount::getFixed(N), T)`.
   Named types are resolved through `NamedTypes` first.
2. `collectClasses` / `collectMemClasses` — the class universe of the target,
   and the descriptor axis (a vector of pointers is its own class here).
3. `collectCoreRuleTuples` / `collectRuleTuples` — per rule, the (operator,
   observation, target) tuples it can produce, so one rule can expand to
   several table rows.
4. `translateRule` / `translateCoreRule` — one rule to an evaluator fragment;
   returns false plus a `Why` when the rule has no table translation.  Those
   are the `entries_without_table_translation` /
   `rule_sets_without_table_translation` counters M2 already reports as 0.
5. `EmitPrologue` — the shared prefix of every evaluator.
6. `runRuleIndex` — `-legalizer-table-rule-index` mode (default prefix "X86",
   :5048).

## Gate (as scoped before implementation)

- `x86.table.inc`, `aarch64.table.inc` byte-identical (SHA pinned in
  `tests/artifacts/SHA256`).
- The AArch64 evaluator agreement: 9632 points, 0 disagreements, against the
  same case table `gisel/eval.py` already passes.  This is the semantic half of
  the gate: byte equality says the table is spelled right, the differential
  says it means the same thing.

## Known risks

- The class partition is not a simple enumeration: it is derived from the
  corpus' own LLT expressions, so any resolve bug cascades into every
  descriptor and every evaluator.
- `scalarOrVector(ElementCount::getFixed(N), T)` with a conditional lane count
  (X86 `s8MaxVector` and friends) expands to several classes; byte equality
  will catch a wrong expansion, but only after the whole file is generated.
- This is the only backend where a "correct" reimplementation can still be
  wrong: byte equality plus the 9632-point differential are both required.

## Order of work

1. `resolve` + `collectClasses` behind a `--dump-classes` debug mode; diff the
   class list against the artifact's section 2 before writing any evaluator.
2. `emitFeatureSignature` + `collectMemClasses` (sections 1 and 3).
3. `EmitPrologue` + `translateCoreRule` for the terminal actions only; recheck
   byte equality per rule set, smallest first (X86 has 63).
4. `translateRule` for the lattice rows, then `runRuleIndex`.
5. Differential run against `gisel/eval.py` cases.
