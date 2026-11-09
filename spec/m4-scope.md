# M4 scope: `--emit=core` + `gisel eval`

> 2026-11-10: 文中引用的 9,632 点冻结答案表已删除，不再是门禁。当前的语义
> 证据是 `tools/ab/` 端到端对拍。

Probe result (2026-11-06): the rule bodies are **already the same object**.  Take
X86 rule 0, canonicalise our record names (`X86_s8` -> `s8`), drop the four
envelope keys (`origin`, `ruleset`, `rule_index`, `schema`), and compare with
`tests/artifacts/x86.core.json`:

```
diff key predicate: elems ["p0", "s1", ...] vs ["p0:*", "s1", ...]
```

That is the only difference in that rule.  So M4 is not a translation problem;
it is three small pieces plus an envelope.

## 1 Canonical spelling

The normal form names types by record (`X86_p0`); the core JSON names LLTs
(`p0:64` in the domain, `p0:*` inside a set).  `dsl.py` already owns
`normalize_llt`/`_llt` for this; the wildcard form is the one thing it does not
currently produce.

## 2 Domain

```
"domain": {"types": ["p0:64", "s1", "s128", "s16", ...], "imms": [], "mems": [],
           "orderings": [], "q0": []}
```

X86 has 32 named types and a 22-entry domain, so the domain is *derived*, not a
copy: it is sorted lexicographically (`s128` before `s16`), it spells the
pointer with its width, and vector-of-pointer types (`v2p0`, `v4p0`) are
absent.  The derivation rule is the open question for M4; it has to be read off
`LegalizerInfoEmitter::runCore`, not guessed.

## 3 Envelope

`schema`/`version` are constants; `config` is
`{"triple":"unspecified","cpu":"unspecified","features":[],"pointer_width":64}`;
`escapes` is `[]` for both corpora.

## 4 `origin`

Per rule: `{"source": <path>, "line": <n>}`.  Ours would point at the `.gisel`
line, so the gate is field equality after dropping
`origin` -- exactly the allowance the plan made (AC5).

## Gate

- X86 and AArch64: core JSON equal to the baseline after removing `origin` and
  `line`, field by field, with the key order preserved inside each rule (the
  rule body is emitted compactly, one rule per line).
- `gisel eval` on the resulting document: 9632 points, 0 disagreements (the
  evaluator already passes this against the baseline document, so the check is
  that our document feeds it identically).
