# M3 scope: `--emit=table`

Reconnaissance for the largest remaining milestone. Everything below is read
off `LegalizerInfoEmitter.cpp:5145-7988` and the frozen artifacts, not guessed.

## What the artifact contains

`x86.table.inc` is 4982 lines, `aarch64.table.inc` 10765. Four sections, in
this order:

| section | starts at (x86 artifact) | source |
|---|---|---|
| environment signature: one bit per feature, `.td` order | `:8` | `emitFeatureSignature` |
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

## Gate

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
