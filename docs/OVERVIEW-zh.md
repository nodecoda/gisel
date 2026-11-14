# 系统总览：三个仓库、两件事、一个闭环

> **这不是 gisel 的能力说明。** gisel 本体只有两个功能（转译、出题），边界在
> `docs/SCOPE.md`。本文把 `gisel` / `gisel-anchor` / `gisel-ab` 三个仓库放在一起，
> 回答两个问题：**这套东西做了什么，以及它凭什么说自己可信。**
>
> 文中的数字都绑定输入指纹（pin 的 commit、语料 sha），引用时必须连输入一起引；
> 单独一个「0 diff」不构成结论。

## 先选一条路

| 你现在有什么 | 5 分钟能做什么 | 命令 |
|---|---|---|
| 只有 Python | 装三包，检查安装，出 X86 题面，生成/校验 inc，看图 | `pip install gisel gisel-anchor gisel-ab` → [docs/QUICKSTART-no-llvm.md](QUICKSTART-no-llvm.md) |
| 有 LLVM checkout + ninja build | 记录路径，doctor，跑 M68k 完整对拍 | `gisel-ab setup --llvm DIR --build DIR` → [gisel-ab TUTORIAL](https://github.com/nodecoda/gisel-ab/blob/main/docs/TUTORIAL-m68k.md) |
| 只有 git，没有构建 | 用 URL 重新导入语料，逐字节 check | `gisel-anchor import --all --git-repo URL --check` |

8 个常用任务在 [COOKBOOK-zh.md](COOKBOOK-zh.md)；名词在
[GLOSSARY-zh.md](GLOSSARY-zh.md)。下面的章节解释这些命令为什么成立。

## 0 全图

数据流是单向的：上游事实往下游走，产物不倒流。

```text
gisel-anchor ──(.gisel 语料)──▶ gisel ──(inc + 无答案查询)──▶ gisel-ab ──(答案 + diff)──▶ 归因
       │                                                         ▲
       └───────────────(U 题面 / oracle)────────────────────────┘
```

代码依赖是另一回事，方向也不同：

| 仓 | 依赖谁 | 形态 |
|---|---|---|
| `gisel` | 无 | 不 import 工作台代码；不读 LLVM 源码、不跑 `llvm-tblgen`、不编译、不比较两个实现 |
| `gisel-anchor` | 产品路径无 | 只有测试里用 `python3 -m gisel lint` 校验自己产出的语料，不 import gisel 内部 |
| `gisel-ab` | `gisel` + `gisel-anchor` | 消费 inc、查询与 U 题面 |

换句话说：**gisel-anchor 生产 gisel 的输入，不是 gisel 的下游。** 它和 gisel 的
唯一代码依赖是「测试期调 gisel CLI 验证语料」这一条；gisel 侧由
`tests/test_scope.py` 保证库代码不 import `tools`/`tests`/`docs`，也不起外部进程。

| 仓库 | 一句话 | 主要入口 |
|---|---|---|
| `gisel` | DSL 编译器 + 出题器 | `gen` `check` `lint` `cases` `domain` `eval` `graph` |
| `gisel-anchor` | 从钉住的 C++ 提取规则与「上游题面」 | `scripts/import-cxx.py`、`src/gisel_anchor/oracle/` |
| `gisel-ab` | 双实现对拍工作台 | `ab.py run`、`diff.py`、`closure.py`、`mir-replay.py`、`l3.py`、`cohort.py` |

## 1 gisel：把规则文本变成两样东西

`gisel gen` 有三个出口，用途不同：

| 出口 | 产物 | 谁用 |
|---|---|---|
| `--emit=inc` | C++ 规则链，一条规则一次 builder 调用 | `gisel-ab` 把它 include 进上游构造函数 |
| `--emit=core` | schema 0.4 的正常形 JSON | `eval`、`graph` |
| `--emit=check` | 字节级指纹 | `gisel check` 判断产物是否过期 |

`lint` 是纯静态检查，不需要 LLVM；`eval` 是出题器的分母自检——同一份查询，Python
求值器和编译出来的 C++ 规则必须答得一样；`graph` 读 `--emit=core`，在「类型 ×
类」的有限空间上找环，不跑 `llc`。

**语法上的两个决定**：

1. **非图灵完备**。没有循环、函数定义、宏展开，所以规则结构可以被完整分析。
2. **保留一个显式逃逸点**：`feature("Subtarget.hasAVX512()")` 的谓词内部是宿主
   C++ 字符串。生成器不解析它，只把它当一个**配置轴**按真值表枚举。

于是「读懂规则」分成两层：**结构层完整理解，谓词层按不透明条件处理**。所有涉及
逃逸点的结论都以「配置轴可枚举」为前提，这条契约在 `spec/escape-points.md`，
快照测试在 `tests/test_escape_points.py`。

## 2 语料：只有 C++ → `.gisel` 一条路

```text
pinned *LegalizerInfo.cpp
      │ scripts/import-cxx.py（认 builder 链，不是正则堆）
      ▼
tests/corpus/*.gisel   （冻结，随仓库分发）
```

- 输入是 **commit**，不是工作区：`git show <pin>:<path>`，本地补丁污染不了语料。
- importer 对无意义的谓词名、`select` 做重命名，**语义不变**；拒绝数进契约，漂移
  就 rc=1。
- 输入只有 commit 里的手写 C++ 构造函数；importer 不依赖 `llvm-tblgen`。

代价必须说清楚：importer 不保证零漂移。所以才有第 4 节——对拍证明的不是「翻译
完美」，而是「翻译出来的规则和上游行为一致」。

## 3 出题原理：有界商

### 3.1 为什么不能采样

LLT 空间是无限的（任意位宽、任意 lane 数）。随机采样只能证明「采到的点一致」，
回答不了「有没有漏」。要回答漏没漏，先得有一个**有限的分母**。

### 3.2 四个词

| 概念 | 定义 | 例子 |
|---|---|---|
| **轴** axis | 查询空间的一个独立坐标 | `slot(0)`、config、`imm(0)`、mem 行 |
| **维度** dimension | 一个 LLT 内被谓词读取的数值量，只有 `bits`/`bytes`/`lanes` | `bits_of(slot(0))` |
| **长度** length | 一根轴上候选值的个数 | `slot 0` 轴长 16 |
| **槽** slot | 类型元组的下标；一个槽就是一根类型轴 | `slot(1)` |

一句话：**轴是坐标，维度是尺子，长度是刻度数**。`opcode` 不是轴，是 ruleset 的
标签；`|B| = Π 轴长` 是点数，不是用例数。

### 3.3 切点闭包

规则里的谓词只读有限的几个量（`sizeIs(N)`、`elementTypeIs`、`clampMinNumElements`、
`pow2`、`hasAVX512()`……）。把真值发生翻转的阈值 `N` 抽出来，连同 `N±1`、类型自身
边界、指针宽度，得到每根轴上的**有限候选集**。

候选集对「谓词翻转」封闭，所以集合外的任何点，答案都和集合内某点相同——集合外
不需要再测。这就是把无限压成有限的那一步。几个容易错的细节写在不变量里，例如
`clampMinNumElements` 的 lane 取精确值而不是 next pow2，指针被窄化/加宽后是整数
而不是窄指针（`docs/ALGORITHM-cases.md` §6；`spec/graph.md` 末尾的语义不变量）。

### 3.4 在有限集上取商

把「规则对查询的答案」定义成等价关系，`B/~` 就是商。三类用例正好对应商的三个
部分：

| 类别 | 是什么 | 回答什么 |
|---|---|---|
| **equivalence** | 每个首命中区域一个代表点 | 每条规则被执行到了吗 |
| **boundary** | 相邻答案区域之间的翻转点 | 边界写对了吗 |
| **outside** | 没有规则命中的补集 | 漏在哪 |

产物是**不带答案的查询 JSONL**（`config/name/types/mem/imms`）。答案是两侧现场
算的，避免「出题人自己给答案」的循环论证。

题面有三套，来自两个生成器：

| 题面 | 生成方 | 覆盖什么 | 证明方向 |
|---|---|---|---|
| **G**（`cases`） | gisel | 规则感知的等价类代表 + 边界 + outside | gisel → 上游 |
| **D**（`domain`） | gisel | 规则无关的声明值域全量 | gisel → 上游 |
| **U** / **U-full** | `gisel-anchor/src/gisel_anchor/oracle` | 上游规则表 + 独立 LLT 宇宙；U 按规则区域抽样，U-full 按全部配置展开 | 上游 → gisel |

G 与 D **互不包含**：`cases` 含规则切点（X86 三千条量级），`domain` 含规则无关的
笛卡尔积（当前生成器实测：X86 91,340；AArch64 每配置 936,960；RISC-V 每配置
253,747）和非法组合。U 不是从 gisel 的规则推出来的，它问的不是「gisel 写对了吗」，
而是「上游的规则 gisel 有没有漏」。

两个方向要分开说：

- **G/D 方向**两侧一致：`G ⊆ U`——gisel 的规则上游都有，没有自创行为；
- **U 方向**两侧一致：`U ⊆ G`——上游问到的规则，gisel 都答得出、答得对。

两条都成立，gisel 才有资格当内部权威。九个 target 的 U（采样）与 U-full（全配置
展开）都已跑过，`disagree=0`（双端断言点按 §4.4 单列，不算答案相同），各带一组
「注入错 opcode」负控；证据在 `gisel-ab/docs/EVIDENCE-U.md`，分母在 `gisel-ab/SCOPE.md §7`。

### 3.5 三个 target 的差别在轴，不在算法

同一套框架，每根轴「有没有值」由语料自己决定：X86 没有 imm 轴，RISC-V 的
`G_SEXT_INREG` 有；AArch64 的 mem 轴带 `select(XLen == 64, s64, s32)` 这种
subtarget 条件；指针宽度是配置轴的函数。**不是每个 target 一套算法，是同一算法
读不同语料长出不同的轴。**

算法细节与完整例子：`docs/ALGORITHM-cases.md`；规范：`spec/cases.md`。

## 4 对拍原理

### 4.1 L0 的语义是固定的

```text
key   = (opcode, 每个类型槽的具体类型, mem, 立即数)
value = (action, type_idx, new_type)
```

比的是完整三元组，不是动作名。`widen` 到 s32 和 `widen` 到 s64 是不同答案。

### 4.2 一个点为什么够：后继闭包归纳

legalize 是循环（`widen/narrow/scalarize` 后改类型再来一轮）。直觉上要比整条
轨迹，但可以归纳：

> **一步答案相同 + 后继函数相同 + 状态集对后继封闭 ⇒ 整个循环相同。**

`gisel-ab/closure.py` 把第三步做成可执行：从种子出发，把每个非终结答案的 `new_type`
变成下一条查询，跑到不动点。于是 `S` 不是抽样集，而是「循环能走到的状态集」
本身，归纳成立。

**两个种子缺一不可**：`G`（`cases`，指针写 `p0:*`）与 `D`（`domain`，指针写
`p0:64`）键拼写不同；X86 上两个闭包的交集只有一千多条，拿 `D` 当超集省掉 `G`
是错的。见 `gisel-ab/docs/CLOSURE.md`。

### 4.3 四层，从便宜到贵

| 层 | 比什么 | 何时跑 |
|---|---|---|
| **L0** | `getAction` 单点答案 | 每次改动 |
| **L1** | 上游 `.mir` 回放 `-run-pass=legalizer` | 改动涉及多步/自定义动作 |
| **L2** | 由查询合成 MIR 回放 | 同上，覆盖面更宽 |
| **L3** | 两轮全量 `ninja check-llvm`，逐条比 lit 结果 | 发版前 |

L0 是规则翻译门，MIR 层是行为门（覆盖多步合法化、custom action、verifier）。
一层通过不等于另一层通过。覆盖矩阵在 `gisel-ab/SCOPE.md §7`：九个 target 都有 L0/D/
U-full 和 MIR L2，只有 X86/AArch64/RISC-V 有 L3。

### 4.4 `agree` 的口径要诚实

`agree` 包含**双端都断言崩溃**的点（当前口径是「可观测状态相同」）。所以还拆出：

```text
answered_equal = agree - unanswerable
```

`unanswerable` 是输入超出合法值域、前端没拦、上游自己 `assert` 或崩的点（例如
`G_ANYEXT bf16 → nxv16i8` 触发 `TypeSize` 可伸缩位宽断言）。它们不是翻译错误，
也不该混进「一致」的宣传里；处理方式是按配置钉死数量，数量变了就失败。

## 5 证据体系

每个数字绑定三样东西：**pin 的 commit、输入指纹（sha/blob）、产生它的命令**。

- `pin/PIN.json` 记录九份 C++ 的 commit 与 sha256；`--all --check` 逐字节复现，
  CI 里跑。
- `gisel-ab/cohort.py` 把一次完整验证固化成 `cohort-*` tag：`plan` 列 gate，`tag` 打
  标签，`verify` 在干净 clone 里重跑，`check` 只比对不重跑。`VERIFICATION.json`
  记每个 gate 的输入 blob 指纹，所以「语料变了」能在重新打 tag 之前被发现。
- 独立仓 `gisel-ab` 的 `EVIDENCE.json` 存每轮运行的查询文件与答案 sha；`verify-evidence.sh`
  从冻结的 per-test 文件重算结论，拒绝「换了 `.inc` 但库没变」的组合轮。
- 上游缺陷单独记账：`gisel-anchor/docs/UPSTREAM-ISSUES.json`。

**纪律**：「0 diff」「0 环」「已覆盖」必须带命令和输入指纹。`graph` 的 0 环尤其
如此——商类必须把 shim guard 算进签名，否则 `widen` 会看起来回到自己；0 环是
相对于当前类划分的结论，不是绝对真理。

## 6 这套东西证明了什么，没证明什么

**证明了**（两个方向分开说）：

1. **G/D 方向**（gisel 出题）：两侧答案一致 → **gisel 的规则没有超出上游**
   （`G ⊆ U`），且多步行为对齐（closure + MIR）。
2. **U 方向**（上游出题）：九个 target 的 U 与 U-full 两侧一致 → **上游的规则
   gisel 没有漏**（`U ⊆ G`）；每个 target 都有注入错 opcode 的负控，证明这条链路
   抓得到错。
3. 上游自身的问题（`unanswerable`、断言崩溃、死循环）被单独定性、计数、提 issue
   → 它们没有混进「一致」里。

**没证明**：

- **U 题面的完备性**：U 建在「声明的 LLT 宇宙 + 抽样点」上，`unexercised` /
  `shadowed` 逐条 allowlist，`dropped` 是上游自己不能作答的形状。它是 `U ⊆ G` 的
  分母，不是全部合法 IR；U-full 展开的是配置，不是类型空间。
- 逃逸点内部的谓词语义。
- 闭包不成立时，`graph` 的 0 环不是「无环证明」；非 refine 的 AArch64 闭包是
  opt-in 门，不是常驻门。
- `0 diff` 只说明「两侧在这份题面/这条轨迹上一致」，不说明规则本身正确。

这就是当前系统的可信度边界：**边界内，gisel 可以作为内部权威，用 inc 替换上游
规则；边界外的事，明写在 `gisel-ab/docs/GAPS.md` 和 `gisel-ab/docs/BACKLOG.md` 里，不拿更小
的图或更少的题冒充全量。**

## 7 想深挖，按这个顺序读

| 想知道 | 读 |
|---|---|
| 产品边界（什么算 gisel） | `docs/SCOPE.md` |
| 四步循环（钉版本 → 出题 → 对拍 → 归因） | `docs/LOOP.md` |
| 出题算法与术语 | `docs/ALGORITHM-cases.md`、`spec/cases.md` |
| 语料来源与它能证明什么 | `docs/CORPORA.md` |
| 逃逸点契约 | `spec/escape-points.md` |
| 商图找环 | `spec/graph.md`、`docs/REPORT-graph.md` |
| 出题报告 | `docs/REPORT-cases.md` |
| 对拍范围与结果 | `gisel-ab/SCOPE.md`、`gisel-ab/docs/REPORT-ab.md` |
| 上游出题（U 方向） | `gisel-ab/docs/EVIDENCE-U.md`、`gisel-anchor/src/gisel_anchor/oracle/` |
| 多步等价 | `gisel-ab/docs/CLOSURE.md` |
| 缺口清单 | `gisel-ab/docs/GAPS.md`、`gisel-ab/docs/BACKLOG.md` |
