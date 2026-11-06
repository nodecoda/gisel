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
| 估算 core 规则 | 355 |

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
