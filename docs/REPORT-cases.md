# 用例生成：从模型派生，而不是手写点集

状态：完成。新增 `gisel/cases.py`（命令 `gisel cases`）与 `spec/cases.md`。
不碰语料、不改四个后端、不改 `eval` 的输入格式。

## 1 为什么是“派生”

规则先被建模成 `Program`，再由它发射 C++/JSON。模型的意义不是多一份文档，
而是让“规则覆盖了哪些点”成为一个**可枚举的对象**：

- 等价类是规则谓词上的区域，不是人手挑的类型；
- 边界是答案真的翻转的相邻值，不是字面量旁边的猜；
- 类外是没有任何规则命中的点，即求值器的 `Unsupported` 兜底。

因此用例不是“再写一遍规则”，而是模型上的操作：解析 → 规范化 → 同一份
schema-0.4 文档 → 三类查询。

## 2 实现

```
gisel cases SOURCE --out FILE [--features FILE] [--config NAME ...]
             [--against ORACLE] [--max-outside N] [--json]
```

- **equivalence**：对每个 `(config, rule)` 取首命中且更早规则不命中的查询；
  mem 规则从 `inMemDesc` 的行派生 `[memory_ty, align]`。
- **boundary**：把代表值替换为 `N-1/N/N+1`（bits、lane、mem 位宽、对齐），
  只保留 `(action, type_idx, new_type)` 或“无命中”发生变化的替换。
- **outside**：采样域中没有规则命中的查询，每个 `(config, ruleset)` 取
  `--max-outside` 条。
- 统计：`witnessed / shadowed / unexercised`。shadowed 表示规则可满足但从未
  首命中；unexercised 表示给定 config 集合下不可满足。两者都显式报告。

默认 config 从文档里的 `hasFeature(...)` 派生（`none` / `all` / `only-N`），
只用于覆盖规则；与 oracle 对拍必须传 `--features`，否则 config 名对不上。
`covered == 0` 直接退出 2，避免把“没对上”当成“全过”。

## 3 证据

生成与对拍（本机，2026-11-07）：

| target | configs | cases | eq | boundary | outside | rules | witnessed | shadowed | unexercised | oracle covered | disagree | time |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| X86 | 4（C0–C3） | 2,935 | 946 | 1,717 | 272 | 332 | 290 | 14 | 28 | 365 | 0 | 1.7 s |
| AArch64 | 9 | 11,847 | 3,279 | 7,629 | 939 | 743 | 363 | 71 | 309 | 663 | 0 | 15 s |
| M68k | 派生 2 | 82 | 28 | 46 | 8 | 13 | 11 | 2 | 0 | — | — | 0.1 s |
| WebAssembly | 派生 2 | 884 | 424 | 392 | 68 | 109 | 97 | 8 | 4 | — | — | 2.4 s |

对拍口径：只比较生成集与冻结 dump 的交集。

- X86：`covered=365 / agree=365 / disagree=0 / uncovered=2570`
- AArch64：`covered=663 / agree=663 / disagree=0 / uncovered=11184`

这就是“子集”的准确说法：**在重叠域上，我们的答案与现有系统逐字段一致**。
`uncovered` 不是通过——它只是还没有 oracle 答案。

更强的全量证据仍是原有门禁：AArch64 9,632 + X86 5,632 + RISCV 19,512 =
34,776 点，0 分歧（`gisel eval`）。

样例（X86，`G_LOAD`）：

```json
{"config":"C0","name":"G_LOAD","types":["s8","p0:*"],"mem":["s8",1],
 "kind":"equivalence","ruleset":"X86_LOAD","rule":0,"reason":"first match for rule 0 (mem)"}
{"config":"C1","name":"G_IMPLICIT_DEF","types":["s79"],"mem":null,
 "kind":"boundary","ruleset":"X86_IMPLICIT_DEF","rule":1,"reason":"bits 80 -> 79"}
```

## 4 否决的方案

| 方案 | 否决理由 |
|---|---|
| 随机采样 MIR/类型 | 测的是采样器，不是规则；覆盖率不可解释 |
| 全笛卡尔积 | 类型 × lane × kind 爆炸，且绝大多数点落在同一个等价类 |
| 手写边界清单 | 与规则漂移；新增规则时不会自动长出用例 |
| 把 uncovered 计入通过 | 把“没验证”说成“验证过”，正是本轮要避免的 |
| 直接从 `.inc`/C++ 反推用例 | 需要先理解产物，等于把模型复制到第二处 |

## 5 已知边界

- `imm` 值从规则的 `imm(i) == N` / `in(imm(i), [...])` 字面量推导，并补
  `0` 和 `±1`。2026-11-08 起 `Wasm_SEXT_INREG#0` 已能命中；见
  `tests/test_axes_imm.py`。
- mem 用例只从 `inMemDesc` 字面量派生；其它读 mem 的方式可能 unexercised。
- 采样域有限：字面量、`±1` 邻居、一组 sentinel。boundary 证明“这条边翻转”，
  不证明“没有别的边”。
- shadowed/unexercised 是相对给定 config 集合的判断，不是全局不可达证明。
- outside 是查询形状，不保证是合法 MIR 指令。
- 生成文件是“查询”，不是 oracle；`gisel eval --cases` 需要
  `action/type_idx/new_type` 三列，所以不能直接吃这种文件。对拍入口是
  `gisel diff`；`gisel cases --queries --oracle` 只负责压缩已完成的全量结果。

## 5.1 imm 轴补充（2026-11-08）

`gisel cases` 现在会为读 `imm(i)` 的规则生成 `imms` 非空的查询，
`gisel domain` 也会把同一组 imm 值并进笛卡尔积。WebAssembly 的
`G_SEXT_INREG` 从 unexercised 变为 witnessed（`imms=[8]` 命中规则 0）。
全量 A/B 数字尚未用新查询重跑，上表的 `cases/covered` 仍是 2026-11-07 的
结果；重跑后需要同时更新第 6 节。

## 6 全量端到端 A/B（2026-11-07）

X86 的无答案域由 `gisel domain` 生成：C0/C3 使用 32 位指针，C1/C2 使用
64 位指针，每个配置 26,097 条，共 104,388 条。官方生成的
`X86LegalizerInfo.inc` 先运行一次，再替换为 gisel 生成的 `.inc` 并重编
`X86CodeGen`，两次都读取同一个 JSONL 文件。

结果：`ref=104388 ours=104388 matched=104388 agree=104388`，
`disagree=0 missing_ref=0 missing_ours=0 errors=0`。其中 1,152 条查询在
两边都触发 LLVM 断言，输出为对称的 `unanswerable`，单独计数，不混入答案差异。

全量答案随后压缩成 8,922 条回归用例；`oracle_missing=0`、`oracle_errors=0`、
`evaluator_errors=0`。这些答案来自端到端 runner；Python evaluator 只负责给
压缩后的用例标注规则，不作为 A/B 结论。

AArch64 使用同一套端到端流程，但题目生成算法固定为 LLVM 的 1,190 个
`AArch64LegalizerTablePointsForTest.inc` 点：按九个固定配置过滤不可表示的
类型，规范化 LLT，按完整查询键去重，并把 9,591 作为硬校验值。结果为：
`ref=9591 ours=9591 matched=9591 agree=9591`，`disagree=0`，缺失和错误均为
0。压缩得到 4,168 条回归查询，其中 equivalence 3,159、boundary 656、
outside 353，`oracle_missing=0`、`evaluator_errors=0`。
