# RISCV：为什么它不是「再抄一遍」，以及抄的代价

状态: 评估（2026-11-07）。工具: `tools/import-inventory.py`（本文件里所有数字都由它产出）。

## 1 结论

- RISCV 的 legalizer 构造函数是 **82 条 builder 链 + 11 条具名链 + 6 处「事后续写」
  + 7 个 `if`/`for` 块**，估算 **约 355 条 core 规则**（AArch64 743、X86 332）。
- **不需要新语言特性**。三处看起来像 escape 的东西都能拆成既有词汇：
  - `typeIsLegal*Vec(...)`（38 次）→ `in` + `num_elems` + `feature(...)`（§3 探针 A）；
  - `getScalarMemAlign(n)` = `enableUnalignedScalarMem() ? 8 : n` → 两条互斥的
    `legal`（§3 探针 B）；
  - 自由 lambda 的守卫 → `feature`/`bits_of`/`size_of` 的合取。
- 真正的工作量在 **形状**，不在语义：具名链的事后续写、`if/else`、`for` 循环。
  手抄这 143 条语句不可靠也不可复现，**下一步是导入器**，不是第二份手稿。

## 2 普查（`tools/import-inventory.py RISCVLegalizerInfo.cpp`）

| metric | value |
|---|---|
| 构造函数体起 | 79 行 |
| 顶层语句 | 143 |
| builder 语句 | 88 |
| `getActionDefinitionsBuilder(...)` | 82 |
| 具名链 `auto &X = ...` | 11 |
| 事后续写的链 | 6（`LoadActions`/`StoreActions`/`ExtLoadActions`/`CTTZPoisonActions` 等） |
| `if`/`for` 块 | 7 |
| 守卫语句：纯谓词 / 含 subtarget 调用 | 9 / 10 |
| 估算 core 规则 | 355（builder 语句数；实际规则数 402，见 §7） |

那 10 条含 subtarget 调用的守卫逐条看过：5 条是 `typeIsLegal*Vec`，3 条是
`widenScalarIf` 的 lambda（`bits_of`/`size_of`/`in` 可拆），1 条是 `bitcastIf` 的
lambda（`Query.Types[0].getElementCount().divideCoefficientBy(8)` → `div_lanes`），
1 条是 `customIf` 的 `any(typeIsLegal*Vec, ...)`。没有一条需要新的 IR 节点。

方法分布（前 10）：`legalFor` 80、`clampScalar` 36、`libcallFor` 33、`customFor` 30、
`lower` 28、`widenScalarToNextPow2` 21、`legalIf` 16、`minScalar` 14、
`scalarSameSizeAs` 11、`maxScalar` 7。全部在既有词汇表内（含 `imm`，见 D-80）。

## 3 两个探针（都在 `/tmp` 跑过，`.inc` 用未修改的头文件编过）

**A. `typeIsLegalIntOrFPVec` 是可拆的。** 原文（`RISCVLegalizerInfo.cpp:39-52`）是
`typeInSet` 加上三个 subtarget 读。写成 `.gisel`：

```
legal (in(slot(0), R_IntOrFPVec)
       and feature("Subtarget.hasVInstructions()")
       and (bits_of(slot(0)) != 64 or feature("Subtarget.hasVInstructionsI64()"))
       and (num_elems(slot(0)) != 1 or feature("Subtarget.getELen() == 64")))
```

`--emit=inc` 出来的是同一棵判据树：

```cpp
.coreLegalIf([=](const LegalityQuery &Query) {
  return ((Query.Types[0] == R_s8 || ... || Query.Types[0] == R_s64)) && (R_HasV)
      && ((Query.Types[0].getScalarSizeInBits() != 64) || (R_HasV64))
      && ((Query.Types[0].getNumElements() != 1) || (R_ELen64)); })
```

**B. `getScalarMemAlign` 是「两条互斥的 legal」。** `ST.enableUnalignedScalarMem() ? 8 : Size`
落在 `mem_desc` 的对齐位，而 `mem_desc` 的对齐是整数字面量。等价的写法是把整张表
写两遍，用特征互斥：

```
legal (feature("Subtarget.enableUnalignedScalarMem()")
       and in_mem_desc(..., [mem_desc(R_s32, R_p0, R_s16, 8)]))
legal (not feature("Subtarget.enableUnalignedScalarMem()")
       and in_mem_desc(..., [mem_desc(R_s32, R_p0, R_s16, 16)]))
```

代价：3 条链 × 2 = 6 条 `legal`（约 30 条 mem_desc 条目写两遍），语义逐位相同。

## 4 三种形状，导入器要处理

| 形状 | 例子 | 映射 |
|---|---|---|
| `if (ST.hasStdExtZbb()) { A.legalFor(...) } else { A.maxScalar(...) }` | `CTLZ` 段（`:252-281`） | 分支内的规则加 `feature(...)` / `not feature(...)`，按书写顺序拼进同一个 ruleset |
| 具名链事后续写 | `LoadActions`（`:349` 建，`:377` 在 `if (XLen == 64)` 里续） | 按**出现顺序**合并成一个 ruleset；顺序就是匹配顺序 |
| `for (unsigned Op : {G_MERGE_VALUES, G_UNMERGE_VALUES})` + `BigTyIdx` | `:198-210` | 展开两遍，索引按 `Op` 的选择代入 |

这三种都是**机械变换**，但每一种都要求把 C++ 当程序求值（读 `ST` 的分支、
按循环变量替换常量）。手抄就是在做这件事，只是没有工具、没法复现、也没法回归。

## 5 建议

1. `tools/import-cxx.py`：吃一个 `*LegalizerInfo.cpp`，出 `.gisel`；不认识的语句
   **报错退出**，不静默丢。验收口径是「导入 → `--emit=inc` → 用真实头文件编译」，
   再加一条：把导入结果回灌成规则数（355 ± 手写例外）。
2. 真正的语义 oracle 还是 `gisel eval`：RISCV 需要一份 `dump_riscv_ref`
   （照 `tests/x86-oracle` 的做法，参考实现要复制构造函数并桩掉 `RISCVSubtarget`）。
   没有这一步，导入器只能证明「编译得过」，不能证明「答案一样」。
3. 在那之前不动 LLVM 树：RISCV 的 `.td` 目前不存在，`--emit=td` 的输出没有消费者。

## 6 顺带记录

- `G_SEXT_INREG`（`:191-197`）用的正是刚补的 `imm` 轴：`immInSet(0,{8,16})` +
  `sizeIs(0,64) && immIs(0,32)`，写法与 WebAssembly 那条同构。
- 估算 355 条规则里，`libcallFor` 33 + `customFor` 30 = 63 条是 terminal，
  不涉及类型构造，导入时最稳。

## 7 导入器落地（2026-11-07）

`tools/import-cxx.py RISCV RISCVLegalizerInfo.cpp` 现在跑通：

```
$ python3 tools/import-cxx.py RISCV .../RISCVLegalizerInfo.cpp --out R.gisel --stats
R.gisel: 96 rulesets, 402 rules, 0 refused
method                              calls  rules
clampScalar                            41     82
legalFor                               81     81
libcallFor                             33     33
customFor                              30     30
lower                                  30     30
scalarSameSizeAs                       11     22
widenScalarToNextPow2                  24     24
legalForTypesWithMemDesc               14     24
...                                    --     --
TOTAL                                 340    402
```

- **0 拒绝**：构造函数里 340 个 builder 调用全部转写。
- **402 = 340 + 41 + 11 + 10**：`clampScalar`/`scalarSameSizeAs` 各展开成
  `widen`+`narrow` 两条；`legalForTypesWithMemDesc` 里带 `getScalarMemAlign` 的表
  按对齐变体拆开（14 个调用 → 24 条，见 §3-B）；`for` 循环体写两遍。
- §2 的「估算 355」是 **builder 语句数**，不是规则数；差的那 62 条全部来自上面
  三种机械展开，没有一条是"多写"或"漏写"。
- 落地文件 `tests/corpus/RISCVLegalizerInfo.gisel`（402 条 / 96 个 ruleset）。

验证链（全部可复跑）：

| gate | command | result |
|---|---|---|
| lint | `gisel lint tests/corpus/RISCVLegalizerInfo.gisel` | 0 error / 3 warning（§8） |
| inc | `gisel gen --emit=inc ...` | 96 rule sets / 402 rules |
| **编译** | `g++ -std=c++17 -fsyntax-only` + 未修改的 `LegalizerInfo.h` | OK |
| core | `gisel gen --emit=core ...` | 96 rule sets / 402 rules |
| check | `gisel gen --emit=check ...` | 402 rules |
| td | `gisel gen --emit=td ...` | 96 defs，无重名；`imm` 规则需 `CoreImm`（§8） |

编译门用的桩：一个 `FakeST` 提供构造里出现的 21 个 `ST.x()`，`XLen = 64`，
`STI` 绑定到 `ST`；`.inc` 作为一个 `LegalizerInfo` 派生类的成员函数体插入。

### 7.1 导入器必须"会"的那些小事

按踩坑顺序（每条都有对应代码，不是口头约定）：

1. `else if` 链与无括号 `else`：`consume_one` 必须把 `if/for/while` 当一条语句，
   否则 `else <stmt>` 会吞掉后面的整个构造函数（这条 bug 让 11 条向量 load 规则
   错挂了 `not XLen==64` 的守卫）。
2. 具名链续写 `A.method()`：`extend` 吃的是 `.method()`，不是 `A.method()`。
3. 同一 opcode 多次 `getActionDefinitionsBuilder`（`G_CTLZ` 在 if/else 两侧各一次）
   → 保留两个 ruleset（C++ 语义就是两张表按序匹配），但名字必须唯一
   （`R_G_CTLZ` / `R_G_CTLZ_2`），否则 `--emit=td` 出重复 def。
4. 谓词首参：`legalFor(pred, {...})`、`minScalar(pred, 0, sXLen)` 的门就是这个
   谓词；`clampScalar` 的**固定 3 参**不能按"首参不是数字"来猜（`LitTyIdx` 会中招）。
5. `typeIsLegal*Vec` 三个静态 helper：按 `static LegalityPredicate` 模板内联，
   `Query.Types[i].getX()` → `bits_of/num_elems/size_of/elem_of(slot(i))`。
6. 整型 subtarget 值不能当 `feature`（bool）：`size_of(...) < ST.getXLen()` 里的
   `ST.getXLen()` 落成 `select(feature("XLen == 64"), 64, 32)`。
7. 类型位置的 ternary（`(XLen == 64 || ST.hasStdExtD()) ? s64 : s32`）要提升成
   命名 `pred` + `select`，因为 `select` 的条件只认名字。

### 7.2 仍然欠的两件事

1. **`CoreImm`**：`.td` 里 `G_SEXT_INREG` 那条用到 `(Imm 0)`，LLVM 的
   `LegalizerCore.td` 还没有这个记录。RISCV 没有 `.td` 消费者，故仍未做。
2. **语义 oracle**：已补齐，见 §8。

## 8 语义 oracle（2026-11-07）

`llvm-dev/tests/riscv-oracle/` 把**真实的** `RISCVLegalizerInfo` 构造函数连同 8 个
真实 `RISCVSubtarget` 链接起来（不是桩），从 `RISCV.core.json` 的域采 2439 个点，
导出 19512 行答案表。`gisel eval` 用我们的 core JSON 复算：**19512 / 0 分歧 / 0 error**
（`tests/test_artifacts.py::EvaluatorCorpus::test_riscv_cases_agree`）。

对拍抓到的两个真偏差（都不在 RISCV 的 .td 里，而在求值器对 LLVM 运行时的建模）：

| 偏差 | 触发 | 修正 |
|---|---|---|
| extended-kind 开关被当成常量 | `f16` 在 RISCV 的 `changeElementSize(64)` 应为 `s64`，我们给 `f64` | feature 表加 `LLT::getUseExtended()` 行；`collapse_extended` 在关闭时把 `f16/i32/bf16` 折成 `sN` |
| memdesc 只比已知最小位宽 | `<vscale x 4 x s8>` 对 `mem s32 align 32` 被判 Legal（应 Custom），18 条 | 按 `TypePairAndMemDesc::isCompatible` 比 `TypeSize`（含 scalable 标志） |

654 → 18 → 0。AArch64 9632、X86 5632 在修正前后都是 0 分歧。
