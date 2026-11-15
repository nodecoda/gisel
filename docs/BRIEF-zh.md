# gisel 一页简介

**问题。** LLVM GlobalISel 的合法化规则写在 `*LegalizerInfo.cpp` 的构造函数里，
是一长串 `getActionDefinitionsBuilder(...)` 调用。它既是代码又是数据：能编译，
但没法被查询"覆盖了哪些类型"，测试只能靠手写 MIR，改一条规则的影响面只能跑全量。

**做法。** 把这部分规则抽成一个小语言 `.gisel`，由它生成两样东西：
可以替换上游的 C++ 规则链 `.inc`，和不带答案的测试查询。整条链路不依赖
`llvm-tblgen`。

```text
上游 C++（钉 commit） --import-cxx--> .gisel 语料
    --gen--> inc 规则链        --cases/domain--> 无答案查询
    --gisel-ab--> 两侧真实构建对拍 --> 差异 + 归因
```

| 仓 | 一句话 |
|---|---|
| `gisel` | DSL 编译器 + 出题器（`gen` `check` `lint` `cases` `domain` `eval` `graph`） |
| `gisel-anchor` | 从钉住的 C++ 提取规则，并生成"上游题面" |
| `gisel-ab` | 双实现对拍工作台（`run` `mir` `l3` `cohort`） |

## 三个设计

1. **非图灵完备 + 一个显式逃逸点。** 没有循环/函数/宏，规则结构可完整解析；
   subtarget 条件写成 `feature("...")`，生成器不解析内部，只把它当**配置轴**枚举。
   结论因此分两层：结构层完整理解，谓词层按不透明条件处理。
2. **有限分母。** 谓词只读有限的量（`sizeIs(N)`、`elementTypeIs`、
   `clampMinNumElements`、`pow2`）。把真值翻转的阈值连同 `N±1`、类型边界抽出来，
   得到每根轴上的有限候选集；候选集对翻转封闭，集合外不必再测。
3. **有界商。** 三类用例：等价类代表（每条规则被执行到了吗）、边界点（翻转点写对了
   吗）、outside（漏在哪）。产物不带答案，答案由两侧现场算，避免自证。

同一套算法读不同语料长出不同的轴：X86 没有 imm 轴，RISC-V 的 `G_SEXT_INREG` 有；
AArch64 的 mem 轴带 `select(XLen == 64, s64, s32)`。不是一个 target 一套算法。

## 证据

两个方向分开说：**G/D**（gisel 出题）一致 → 我们的规则没有超出上游；
**U/U-full**（上游出题）一致 → 上游的规则我们没有漏。多步靠归纳：一步答案相同 +
后继函数相同 + 状态集对后继封闭 ⇒ 整个循环相同。

| 层 | 规模（实测） |
|---|---|
| 动作层 G | 9 个后端；x86 3,014 / aarch64 12,559 / riscv 6,086 … |
| 值域全量 D | x86 91,340 / aarch64 8,432,640 / riscv 2,029,976 … |
| 上游题面 U-full | 9 个后端、全配置展开，最大 aarch64 3,505,608 |
| MIR 回放 L2 | 21,128 条建成，diff 0 |
| 全量 lit L3 | x86 / aarch64 / riscv，80,655 个测试逐条比对 |

语料 9 个后端、509 个 ruleset、2,165 条规则，全部可由 pin 的 commit 逐字节重建
（`import-cxx --all --check`）。

## 在上游发现的问题

| 类别 | 例子 | 状态 |
|---|---|---|
| 规则表自相矛盾 | `scalarSameSizeAs` 在两槽不同形时产生 insane mutation | issue #237670，上游修复已合入 |
| 合法化不终止 | X86 窄 `G_BUILD_VECTOR` 加宽→拆回→再拼的死循环 | issue #236649，修复 PR #238277 OPEN |
| 合法 IR 触发断言 | 指针结果走 `changeElementSize` | issue #236651 已提 |
| 规则缺失 | 无 POPCNT 时向量 `ctpop` 没有规则，release 下死循环 | issue #220802，PR #235976 OPEN |

已提 4 个 issue，2 个修复已合入；另有 8 条已定性、待提。
这些不是"跑测试跑出来的"，是出题器问到了手写 MIR 不会问的点。

## 收益

- **回归便宜**：改规则 → 动作层秒级回答"哪些点变了"；上游改规则 → `check` 报产物过期。
- **维护有边界**：语料绑定 pin 的 commit 与 sha；偏离函数断言上游原文仍在，上游一改
  就报错，而不是悄悄失效。
- **完备性有分母**：等价类 × 配置，而不是"写了多少条 MIR"。
- **可审计**：每个数字绑定 pin + sha + 命令；一次完整验证固化成 `cohort-*` tag，
  在干净 clone 里重跑 10 个 gate。

## 没证明什么

- 动作层等价 ≠ 合法化器整体等价。`Custom` 动作体是手写 C++，体内的类型改写不可见；
  因此换 `.inc` 只换规则表，`LegalizerHelper`、custom 体、memdesc、verifier 全部
  保留——策略层是两侧共用的同一份代码。
- U 是"声明的 LLT 宇宙 + 抽样点"，不是全部合法 IR。
- `0 diff` 只说明两侧在这份题面上一致，不说明规则本身正确。

## 入口

```sh
pipx install gisel
gisel demo                                          # lint -> inc -> cases -> graph
gisel cases --corpus x86 --out x86.cases.jsonl
gisel gen   --corpus x86 --emit=inc --out x86.inc
gisel check --corpus x86 --emit=inc --against x86.inc
```
