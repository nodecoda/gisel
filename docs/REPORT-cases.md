# 用例生成：从模型派生，而不是手写点集

状态：完成。新增 `gisel/cases.py`（命令 `gisel cases`）与 `spec/cases.md`。
不碰语料、不改四个后端、不改 `eval` 的输入格式。

> 算法本身（有界商、切点、三类用例的推导）见 `docs/ALGORITHM-cases.md`；
> 本文只保留实现证据、快照和否决方案。

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

生成与对拍（本机，2026-11-08 重测）：

| target | configs | cases | eq | boundary | outside | rules | witnessed | shadowed | unexercised | time |
|---|---|---|---|---|---|---|---|---|---|---|
| X86 | 4（C0–C3） | 3,027 | 1,117 | 1,522 | 388 | 328 | 319 | 4 | 5 | 1.8 s |
| AArch64 | 9 | 12,595 | 5,225 | 6,292 | 1,078 | 743 | 584 | 35 | 124 | 3m17s |
| RISC-V | 8 | 6,149 | 2,242 | 3,059 | 848 | 413 | 355 | 12 | 46 | 2m11s |
| M68k | 派生 2 | 84 | 28 | 36 | 20 | 13 | 11 | 2 | 0 | 0.6 s |
| WebAssembly | 派生 2 | 978 | 426 | 376 | 176 | 109 | 98 | 8 | 3 | 0.6 s |

（2026-11-08 切 cpp 语料后重测；`docs/ALGORITHM-cases.md` 有同一份数字。
cases 比 2026-11-07 少，因为候选轴不再发明 LLVM 构造不出来的类型：固定 1 车道
向量归一成元素类型，float 位宽只取 16/32/64/80/128。见 `spec/axes.md` §4。）

生成器只负责产题；“答案对不对”不在这里证明。`tests/cases/*_ref_dump.jsonl`
及其交集统计已于 2026-11-10 删除，当前答案证据只有 `ab/` 的端到端对拍：
同一份无答案查询喂给官方构建和 include 了我们 `.inc` 的构建，比较答案流。

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
  `action/type_idx/new_type` 三列，所以不能直接吃这种文件。对拍入口是工作台的
  `ab/diff.py`；`gisel cases --queries --oracle` 只负责压缩已完成的全量
  结果。

## 5.1 imm 轴补充（2026-11-08）

`gisel cases` 现在会为读 `imm(i)` 的规则生成 `imms` 非空的查询，
`gisel domain` 也会把同一组 imm 值并进笛卡尔积。WebAssembly 的
`G_SEXT_INREG` 从 unexercised 变为 witnessed（`imms=[8]` 命中规则 0）。
全量 A/B 数字尚未用新查询重跑，上表的 `cases/covered` 仍是 2026-11-07 的
结果；重跑后需要同时更新第 6 节。

## 5.2 ordering 轴补充（2026-11-08）

`mems.orderings` 现在会为读 `mem_ordering` 的 ruleset 乘上
`(ordering, failure_ordering)` 采样点，导出的查询 `mem` 为 4 元组。AArch64
（`--features tests/cases/features.json`）的对照（2026-11-08 重测）：

```sh
python3 -m gisel cases tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json --json --out /tmp/a64-noorder.jsonl
# witnessed 313 / shadowed 28 / unexercised 402 / cases 9,705

python3 -m gisel cases tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json \
  --axes /tmp/a64-order.axes.json --json --out /tmp/a64-order.jsonl
# mems.orderings = [Unordered, Acquire, Release, SequentiallyConsistent]
# witnessed 317 / shadowed 29 / unexercised 397 / cases 9,732

# 同上再加 NotAtomic
# witnessed 319 / shadowed 28 / unexercised 396 / cases 10,029
```

8 条读 ordering 的规则里，6 条从 unexercised 变为 witnessed：
`AArch64_LOAD#0/#1`、`AArch64_SEXTLOAD#0`、`AArch64_STORE#0/#1/#2`。
`AArch64_INDEXED_LOAD#0`、`AArch64_INDEXED_SEXTLOAD#0` 仍未命中，原因不是
ordering（可能是类型/谓词组合），留给下一轮定位。

**`NotAtomic` 必须显式列出来。** `mems.orderings` 是替换而不是追加，只写四种
原子序时 `mem_ordering >= Unordered` 恒为真，普通非原子 load 规则
（`AArch64_SEXTLOAD#1/#3`）就再也不会被见证。`tools/check-axes.py` 会直接把
这句话打出来，加上 `NotAtomic` 后 witnessed 317 → 319。

端到端对拍是工作台流程，见 `docs/REPORT-ab.md`。

## 6 对拍

端到端 A/B（拿 gisel 生成的 `.inc` 替换现网实现、逐条比较答案）是**工作台**
流程，不是用例生成的一部分，见 `docs/REPORT-ab.md`。
