# 分母的归属：一条规则都不能没有见证

状态：完成（2026-11-09）。基线 `c5ac359`。

## 1 链路

```
LLVM C++  --import-cxx-->  .gisel  --gisel cases-->  无答案查询  --对拍--> 两个 runner
```

“我们没漏上游的规则”只能由这条链的前两段保证：

- **C++ → .gisel**：`tools/import-cxx.py` 只接受它认识的构造，别的一律带行号
  拒绝；`--check` 要求重新导入的结果与入库语料**逐字节相同**。所以语料不是
  “我们记得的规则”，是“C++ 里写着的规则”。
- **.gisel → 查询**：每条规则至少要有一个查询把它**首命中**。少一条，对拍仍会
  报 0 分歧——因为根本没问。

第二条过去没有保证。本文记录把它变成可检查的门禁时，发现并修掉的两个 bug。

## 2 两个 bug

**2.1 候选截断把邻居全丢了**（`gisel/cases.py:_candidates`）

```python
ordered += [neighbours...]
per.append(ordered[:max(cap, len(lit))])
```

一个槽位的字面量数量一旦 ≥ `cap`（默认 16），截断长度就等于字面量个数，
**所有邻居都被砍掉**。而突变规则（`widen` / `clamp_min` / `scalarize` …）只能被
“合法集合之外的某个值”触发。结果是 AArch64 有 406 条规则永远无见证。

修法：字面量和邻居**必须全部保留**，只截断排在最后的域类型（产品规模超限时
先丢的也是它们）。

**2.2 一维向量的 scalable 翻转**（`gisel/cases.py:_neighbours`）

邻居生成里有一步是翻转 `scalable` 位。对 `nxv1s64` 它产出 `v1s64`——一个固定
单 lane 向量，按定义**就是** `s64`。之前这些规则从来没有见证，所以这个拼写从没
被生成过；修了 2.1 之后它们第一次出现，被 `test_no_generated_case_names_a_fixed_
one_lane_vector` 抓个正着。

## 3 数字

三个 target，同一套 `cases` 口径（AArch64 带 `--axes aarch64-mem-orderings.axes.json`）：

| target | 规则 | 修复前 有见证 | 修复后 有见证 | shadowed | unexercised | 查询数 |
|---|---:|---:|---:|---:|---:|---:|
| X86 | 328 | 292 (89.0%) | **319 (97.3%)** | 4 | 5 | 3,291 |
| AArch64 | 743 | 312 (42.0%) | **572 (77.0%)** | 36 | 135 | 13,217 |
| RISC-V | 413 | 320 (77.5%) | **355 (85.9%)** | 12 | 46 | 6,301 |

另外加了一次**定向搜索**：全局候选集没找到见证时，单独用该规则自己命名的类型
及其邻居枚举一遍。它只多找到 1 条（AArch64）——说明剩下的不是“搜得不够”，而是
真的被更早的规则盖住了。

## 4 剩下的 9 / 171 / 58 条是什么

X86 的 5 条 unexercised 有 4 条是 `clamp_min(0, X_s64, 2)` 这类：

```text
clamp_min(0, X_s64, 2)      # 触发条件是“s64 向量且 lane < 2”
```

固定单 lane 向量就是标量，而标量已经被前面的 `legal in(slot(0), [X_s32])`
之类答掉了。这类规则**在上游就是死的**：LLT 造不出这样的值。它们不是我们的
缺口，但也不该被算成“已验证”——现在被单列成 unexercised 并计入退出码。

AArch64 剩下的 171 条集中在 `G_STORE` / `G_LOAD`（多槽 + mem 描述）、
`G_ICMP`、`G_EXTRACT/INSERT_VECTOR_ELT`。共同点是 3 个槽位的组合空间被产品上限
约束，或者需要一个特定 feature 与特定类型的**组合**。这是下一步，不是本轮的
结论。

## 5 门禁

```sh
gisel cases tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --out /tmp/q.jsonl --strict-coverage
```

有任何规则既没有见证、又不是被证明可满足却遮蔽时，退出码 1，并打印前 20 条：

```text
cases: 9 rule(s) have no witness (5 unexercised, 4 shadowed); the query set
does not cover every rule
  X_G_IMPLICIT_DEF#16: unexercised
  ...
```

配 `tools/import-cxx.py --all --llvm-src <llvm> --check` 一起用，就是这条链的
两段证书：**语料 == C++**，且**每条规则都被问过**（剩下的会被点名）。

## 6 没做到的

- AArch64 的 135 条 unexercised 还没有逐条定性。要判“上游就是死的”需要把 LLT
  的构造规则（单 lane 折叠、scalable 与固定向量的关系）编进判定，而不是靠搜索。
- 见证只保证“问到了这条规则”，不保证“问全了这条规则的每个类型字面量”。
  被删掉的 `-gen-legalizer-table-points` 给的是后者。要补回来，得在同一份语料上
  做“每条规则 × 每个字面量”的展开，作为 `cases` 的第二个出口。
- 语料与 C++ 的逐字节一致只覆盖三个钉住的构造函数；第四个 target 是新工具，
  不是新 flag（`tools/import-cxx.py` 的文档头已经这么写）。
