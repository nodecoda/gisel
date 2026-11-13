# 语料链路：从手写 C++ 直接转录（专用一次性工具）

状态：完成。三份主语料（X86 / AArch64 / RISC-V）现在都从上游手写
`*LegalizerInfo.cpp` 构造函数直接转录成 `.gisel`；中间那层 `.td` 不再参与。
后续已扩展到九份语料（ARM / Mips / PowerPC / M68k / WebAssembly / SPIR-V），
当前清单和计数以 `docs/CORPORA.md` 为准。

## 1 结论

```text
upstream *LegalizerInfo.cpp（getActionDefinitionsBuilder 链）
  -> upstream-source/importer/import-cxx.py  （一次性转录，0 拒绝）
  -> tests/corpus/*.gisel
  -> gisel gen --emit={inc,check,core}
```

| 目标 | 源 sha256（前 12 位） | rulesets | rules | 拒绝 |
|---|---|---:|---:|---:|
| X86 | `79f2376096c3` | 63 | 328 | 0 |
| AArch64 | `2b5377c3eedd` | 117 | 741 | 0 |
| RISC-V | `ad529e1f1a9e` | 96 | 402 | 0 |
| M68k | `f796bb977e0b` | 6 | 13 | 0 |

`tests/artifacts/` 的九份产物已按新语料重生成。它们**是 gisel 自己的冻结
输出**，用于抓漂移，不是“与上游逐字节一致”的 oracle；规则保真靠
`upstream-source/importer/import-cxx.py --check` 和 `ab/` 端到端对拍。

AArch64 的 importer `TARGETS` 断言 744 条 builder call；3 条只改类型集合、
不生成独立规则，所以 `gisel lint` 解析到 741 条。

## 2 为什么删掉中间的 `.td`

上游 LLVM main 没有 legalizer 的 `.td`，`llvm-tblgen` 也没有
`-gen-legalizer`。规则只写在 C++ 构造函数里。我们曾在 LLVM 分支上加过
`.td` + emitter，让 gisel 读 `.td`；那等于维护**第二份规则陈述**：上游改
C++，我们改 `.td`，再让 gisel 读 `.td`，任何一层走神都会静默漂移，而且
A/B 还要多一轮“`.td` vs C++”的对拍。

现在只有一份输入：C++ 构造函数。`.td` 后端（`--emit=td`、`gisel bootstrap`、
`gisel/td.py`）已在 `REPORT-no-td.md` 里退役。

## 3 为什么是专用工具，不是通用 C++ 导入器

`upstream-source/importer/import-cxx.py` 只认这些构造函数用到的那一小撮写法。目标表
`TARGETS` 写死了目标、源相对路径、前缀和规则数；`--all --check`
重新转录并和仓库里的 `.gisel` 逐字节对照。规则数变了就报 `DRIFT` 并返回 1，
不会悄悄换一份语料。

这比“通用解析器”更可靠：三个构造函数的差异（`XLen`、`ST`、私有 helper、
`changeTo`、`is_contained`……）不需要抽象成配置项，直接写在翻译器里；上游
改了写法，工具报错，人再改工具——而不是让工具猜。

原则不变：**翻译不了就带行号拒绝，绝不静默丢规则**。下面三个真 bug 都是
这条原则抓出来的。

## 3b 生成名的人工审阅（LLM 提议，表里冻结）

转录器最初给匿名三元表达式起名 `X_sel0` / `X_cond0`，给带接收者的
feature 起名 `A_ST_hasNEON`。这些名字语义没错，但读起来像机器产物。现在
名字分两层：

- **结构化来源优先**：C++ 里有名字的类型（`sMaxScalar`、`s8MaxVector`）
  直接沿用，不再丢成 `selN`。
- **LLM 审阅 + 冻结表**：匿名表达式由模型读定义和用途后提议名字，结果写进
  `SELECT_NAMES` / `FEATURE_NAMES`。key 是去掉 target 前缀后的 C++ 表达式；
  每个 key 必须被命中，没命中的 selector 或残留的 `selN`/`condN` 都报
  `DRIFT`（rc=1），所以上游一改，表就失效而不是悄悄退化。

命名规则：

| 情况 | 处理 | 例子 |
|---|---|---|
| C++ 变量本身有名字 | 沿用 | `sMaxScalar` → `X_sMaxScalar` |
| 嵌套三元的内层 | `<外层名>NoAVX512` | `X_s8MaxVectorNoAVX512` |
| 条件是单个 feature | 直接写进 `select`，删掉 `pred` 别名 | `select X_sse2MaxScalar = if X_HasSSE2 then ...` |
| 条件是复合谓词 | 保留 `pred`，用审阅名 | `pred X_useX87NoSSE1` |
| 接收者前缀 | 去掉 `ST_`/`STI_`，但不同接收者不合并 | `R_hasStdExtZbb` / `R_subtargetInfoHasZbb` |
| 比较表达式 | 按实际关系命名 | `XLen <= ST.getELen()` → `R_XLen_le_ELen` |

`R_ST_hasStdExtZbb` 和 `R_STI_hasStdExtZbb` 看着一样，但 features 表里是两个
独立的配置轴，合成一个会改变语义，所以保留两个名字。这是“重命名”不是
“化简”。

语义保持的证据：三个目标的端到端 A/B 仍然 agree；`inc/core` 产物重新冻结后
测试全绿。名字只影响可读性和产物字节，不影响求值。

## 4 三个真实 bug

1. **`const_eval` 把运行时条件当常量**
   RISC-V 的 `if (XLen == 64)` 里，`XLen` 被当成未知字符串，和 `64` 比较
   得到 `False`，整个分支被静默丢掉（丢 8 条规则）。修法：比较两侧类型不同
   就 `Refuse`，不再猜。现在 `XLen == 64` 保留成命名 feature `R_XLen_64`。

2. **`changeTo(i, j)` 被翻译成 `widen`**
   `changeTo` 改的是**类型本身**（含 lane 数），`widen` 只改元素宽度。AArch64
   `G_ABS` 因此语义错。现在 `changeTo(i, j)` → `same_as(j)`，
   `changeTo(i, Ty)` → `replace(ty(Ty))`，
   `changeElementSizeTo` → `replace(elt_size_to(...))`。

3. **`1u << Log2_32_Ceil(x)` 被当成比较**
   旧的比较切分把 `<<` 的第一个 `<` 当关系运算符，切出 `mul(..., 1u <)`。
   现在按长度优先匹配 `<<`/`>>`，并剥掉 `u`/`LL` 后缀。

另外补齐的写法：`is_contained({...}, x)` 的整型集合展开成析取、非 imm 主语的
`switch` 展开、`imm_idx` 不加 guard、`bool X = ...` 与 `feature(...)` 共用
前缀、`LLT::vector/integer` 走命名类型。

## 5 X86 的两条受审偏离

工具不是“照抄”：有两处有意改写，每处都断言上游文本仍在，上游改了会
`SystemExit`，不会空转。

| 偏离 | 原因 |
|---|---|
| `G_BUILD_VECTOR` 去掉最小 lane clamp（4 条 `clamp_min` + 1 条 `more`） | 加 lane 会把 build vector 变成更大的 build vector，缩回来又是同一个查询，legalizer 死循环；只留最大 clamp，窄 build vector 走 Unsupported |
| `G_CTPOP` 增加 VPOPCNTDQ（512 位以下再加 VLX）的向量 legal | 上游构造函数还没有这段；端到端 A/B 里这些点是 Legal |

## 6 证据

- 转录：三个目标 0 拒绝，`--all --check` 逐字节匹配。
- 生成：`python3 -m unittest discover -q -s tests` 全绿（208 tests）。
- 行为：三个目标的端到端 A/B 全部 agree，0 disagree。
- 计数：`tests/artifacts` 总调用 1074 = 1071 + 3（`immIdx` 3 条，来自
  AArch64；`gisel/ast.py` 的 `canonicalize_rulesets` 已按 opcode 汇总
  `imm_idx` 覆盖信息，修掉了 AArch64 `immIdx` 被最后一块覆盖成 0 的 bug）。

## 7 未覆盖

- 换上游修订需要改 `TARGETS` 里的计数并重新生成，不是运行时参数；这是
  有意为之。当前三份输入钉的是和 A/B 同一次构建的源码修订（sha 见上表），
  不一定是最新 upstream；换修订就要连 A/B 的官方侧一起重建。
- M68k 已转正（见 §9），WebAssembly 已转正（见 §10），PowerPC 已转正（见 §11），
  ARM 已转正（见 §12）。
- LLVM 研究分支上残留的 `.td` / `-gen-legalizer*` 代码不在本仓库清理范围；
  gisel 这边已经不再读它。

## 8 追补：`widenScalarOrElt…` 曾被压成标量拼写（2026-11-08）

A/B 归因（`docs/REPORT-ab.md` §4.2）发现 16 条 `G_SITOFP` / `G_FPTOSI`
差异：上游 `widenScalarOrEltToNextPow2OrMinSize(1)` 会把 `v2i63` 的元素
widen 到 64，我们生成的 inc 不动，随后另一条 `changeElementSize(0, 63)`
造出 `f63`，在断言构建里直接 `UNREACHABLE`。

原因是转录器把三个 C++ 方法合并成了同一个 `widen(slot(i), pow2)`：

| 方法 | 谓词 | 现在的拼写 |
|---|---|---|
| `widenScalarToNextPow2` | `isScalar() && !pow2(总位宽)` | `widen(slot(i), pow2)` |
| `widenScalarOrEltToNextPow2` | `!pow2(元素位宽)` | `widen(elem_of(slot(i)), pow2)` |
| `widenScalarOrEltToNextPow2OrMinSize`（无 MinSize） | 同上（`MinSize=0` 时等价） | 同上 |
| `widenScalarOrEltToNextPow2OrMinSize(n)` / `(select)` | `narrowerThan(n) or !pow2` | `widen(slot(i), n / select)` |

`v2i63` 的总位宽 126 不是 2 的幂，但标量谓词先看 `isScalar()`，所以旧拼写
静默不命中。修复后重生成 AArch64 语料只改 2 行，`tests/artifacts/aarch64.*`
同步重生成；RISC-V / X86 语料逐字节不变（X86 源已漂移，比较时按单目标跑）。

## 9 M68k 转正（2026-11-09）

M68k 的构造函数是 52 行、6 条 builder 链、13 条规则，没有任何 helper 或
subtarget 条件，是验证“新增一个 target 只差一个 `TARGETS` 条目”的最小样本。
它现在和另外三个目标一样：

- 语料从 pin `9bfc850b9940` 的 `M68kLegalizerInfo.cpp` 转录，0 拒绝，
  `.gisel` 逐字节可复现；
- 查询集 41 条（单 `default` 配置）；
- 端到端 41/41 agree、0 disagree、0 unanswerable：
  `ab/run-m68k-end-to-end.sh TREE BUILD m68k.inc OUT`。

M68k 是 LLVM 的 experimental target，构建时要加
`LLVM_EXPERIMENTAL_TARGETS_TO_BUILD=M68k`；`toolset/configure.sh` 已支持这个
环境变量。它的 runner 用的是 `ab/query_runner_common.h`，每目标文件约
30 行；其余 target 的接入按同一模板走。

## 10 WebAssembly 转正（2026-11-09）

WebAssembly 原本是人工转写的探针（108 条，用来找 imm 轴的缺口）。它现在和
M68k 一样走 `import-cxx`：

- 语料从 pin `9bfc850b9940` 的 `WebAssemblyLegalizerInfo.cpp` 转录，
  **29 rulesets / 109 rules / 0 refused**，`.gisel` 逐字节可复现；
- 查询集 886 条（`wasm32`/`wasm64` × `±sign-ext` 四个配置）；
- 端到端 **886/886 agree、0 disagree、0 unanswerable**：
  `ab/run-wasm-end-to-end.sh TREE BUILD wasm.inc OUT`。

为了做到 0 拒绝，转录器补了三处（都是拼写归一，不是新增语义）：

| C++ | 处理 | 为什么不是语义改动 |
|---|---|---|
| `LLT::floatIEEE(32/64)` | `_llt_float_ieee()` → `LLT::float32()/float64()` | 同一个 LLT；DSL 只认命名捷径 |
| `LLT::integer(ST.hasAddr64() ? 64 : 32)` | 通用三元 → `select … if HasAddr64`（原来硬编码 RISC-V 的 `XLen == 64`） | 特征相关的宽度本来就落成 `select`，只是条件文本现在来自源码 |
| `Wasm_i32` 与 `Wasm_p0i_lo` 同为 `LLT::integer(32)` | `_declare_pair()` 复用已声明的名字 | 一个 LLT 一个名字；否则 `.inc` 发射器按值取名会把规则里的 `Wasm_i32` 折成最后声明的那个别名 |

第三个还暴露了 `.inc` 的一个既有事实：AST 在解析时把具名类型解析成 LLT 值，
发射器只能按**值**取回名字，所以同名值有多个名字时“最后声明者赢”。语料因此
保持“一个 LLT 一个名字”，RISC-V 的 `sDoubleXLen_lo`（= `sXLen_hi`）随之并入
`sXLen_hi`，`tests/artifacts/riscv.*` 同步重生成（语义逐条相同，只有行号/名字变化，
`strip_origin` 后 JSON 相等）。

两个配置轴都是构造函数真正读的：`ST.hasAddr64()`（wasm32 vs wasm64）与
`ST.hasSignExt()`（`mvp` vs `generic` CPU）。前者改 `p0` 宽度和
`p0i/p0s` 两个 select，后者改 `G_SEXT_INREG` 的 legal 规则——两条都在
抽样查询里验证过会翻转答案，不是恒真轴。

## 11 PowerPC 转正（2026-11-09）

PowerPC 的构造函数 91 行、15 个规则集 / 25 条规则，两处曾拒绝转录，现在 0 拒绝：

| C++ | 处理 |
|---|---|
| `static LegalityPredicate isRegisterType(unsigned)` | 新增：`parse_helpers` 收录“整段 lambda 体”的 helper，`local_pred` 逐语句内联（早返回、局部变量、`if (c) { ... }` 块） |
| `bitcastIf(typeIsNot(0, V4S32), changeTo(0, V4S32))` | 新增：`bitcastIf` 的 mutation 是直接的 `changeTo(...)` 时走 `mutation()`，不再当作 pair/lambda |

顺带修了两个内联细节：`parse_helpers` 先剥行注释（否则 `// ...` 会和下一条语句
粘在一起），以及 `Query.Types[i].getElementType().getSizeInBits()` 要先于
`getSizeInBits()` 规则改写，否则会生成 `size_of(slot(0).getElementType())`。

查询集 98 条（单 `default` 配置，`powerpc64le`），端到端
**98/98 agree、0 disagree、1 unanswerable**：

```
../ab/run-ppc-end-to-end.sh TREE BUILD ppc.inc OUT
{"agree": 98, "disagree": 0, "unanswerable": 1}
```

那 1 条是 `G_AND v16s32`：官方构造函数自己也 abort，两侧一致，所以不是规则差异，
是上游缺陷——`bitcastIf(typeIsNot(0, V4S32), changeTo(0, V4S32))` 的谓词
没限制宽度，而 `Bitcast` 的 `mutationIsSane` 要求新旧类型位宽相等。复现和补丁写法
记在 `/home/ubuntu/admin/upstream-issues/2026-11-09-15-gisel-ppc-bitcast-size-assert.md`
（待提 issue）。

## 12 ARM 转正（2026-11-09）

ARM 的构造函数 214 行、52 个规则集 / 96 条规则。它的 legalizer 不在 `GISel/`
子目录，路径是 `lib/Target/ARM/ARMLegalizerInfo.cpp`；`import-cxx.py` 里 ARM 的
`rel` 和 `FEATURE_NAMES` 都按这个路径来。

三处新增，都是 ARM 自己的形状：

| C++ | 处理 |
|---|---|
| `static bool AEABI(const ARMSubtarget &ST) { return A \|\| B \|\| C; }`，用成 `if (AEABI(ST))` | 新增 `parse_helpers` 的 `static bool` 分支 + `local_bool`：作为 `if` gate 时按它拼的析取式内联，而不是当成 `LegalityPredicate` |
| `REMBuilder.libcallFor({s32})` | `libcallForCartesianProduct` 早就在分支里，`libcallFor` 只差一个动作名 |
| `bool A_HasHWDivide = (!ST.isThumb() && ...) \|\| (ST.isThumb() && ...)` 跨行 | `feature()` 和 `bool X = ...` 都先把表达式折成一行：feature 声明是一行，声明文本同时是求值 key |

剩下两条拒绝是 `setFCmpLibcallsAEABI()` / `setFCmpLibcallsGNU()`（第 153 行）。
它们不产生规则：只填 `FCmp32/64Libcalls` 数组，供 `legalizeCustom()` 的
`G_FCMP` 分支用，规则形里没有对应物。现在由 `DATA_TABLE_INITIALISERS`
点名跳过，**计数并打印**，同时写进 `.gisel` 文件头：

```
ARM: 52 rulesets, 96 rules, 0 refused
  skipped line 153: setFCmpLibcallsAEABI() (data table, not a rule)
  skipped line 153: setFCmpLibcallsGNU() (data table, not a rule)
```

这是“不是规则所以不转录”，不是“翻译不了就跳过”：名单是显式的，输出可见，
`--check` 仍逐字节复现。

### 12.1 配置轴

构造函数自己读的谓词有 9 个（`isThumb1Only` 只做早退，不进规则）。实际取值不是
猜的：先用一个探针程序把候选 triple/CPU 的 `ARMSubtarget` 真值打出来，再写进
`tests/cases/arm-features.json`：

| config | triple / CPU | 起点 |
|---|---|---|
| `armv7a-neon` | `armv7-linux-gnueabihf` / `cortex-a7` | VFP4 + NEON + HW divide |
| `armv7a-nodiv` | 同上 / `-hwdiv,-hwdiv-arm` | 只关 HW divide |
| `armv7a-a5` | `cortex-a5` | VFP4、无 divide |
| `armv6-arm1176` | `armv6-linux-gnueabihf` / `arm1176jzf-s` | NEON 关 |
| `armv4t` | `armv4t-linux-gnueabi` / `arm7tdmi` / `+soft-float` | 无 V5T、无 VFP2、软浮点 |
| `thumbv7m` | `thumbv7m-none-eabi` / `cortex-m3` | M-profile，无 FPU |
| `armv7-soft` | `armv7-linux-gnueabi` / `generic` / `+soft-float` | 软浮点 + NEON |

这一步抓到一个真错：`cortex-a5` 的 `hasVFP4Base()` 是**真**（VFPv4-D16），我第一版
按“A5 老”写成假，1,614 条里 `G_FMA s32` 一条从 Legal 变 Libcall——`ab.py` 的
三方矩阵（官方 / 我们 / 求值器）直接把它挑出来了。改真值后归零。

### 12.2 结果

```
python3 -m gisel gen tests/corpus/ARMLegalizerInfo.gisel --emit=inc --out /tmp/arm.inc
../ab/run-arm-end-to-end.sh TREE BUILD /tmp/arm.inc OUT
{"agree": 1614, "disagree": 0, "unanswerable": 0}

python3 ../ab/ab.py run --target arm --tree TREE --build BUILD \
  --queries OUT/queries.jsonl --out OUT2
target=arm compare=full queries=1614 agree=1614 disagree=0 unanswerable=0 rc=0
```

`bundle.json` 的三方矩阵是 `all_agree 1614`：官方库、生成的构造函数、gisel 求值器
三者同答案。

### 12.3 未覆盖

- **Thumb1 没有配置。** 构造函数在 `if (ST.isThumb1Only()) { verify(...); return; }`
  处返回，一个规则都不注册；`.gisel` 没有“这个 subtarget 一张表都没有”的写法，
  所以带上 Thumb1 只会得到一条由构造决定的全量分歧。这是语言缺口，记在这里而不是
  靠少列配置糊过去。
- **`setFCmpLibcalls*` 的表没有对拍。** 它走 `legalizeCustom()`，不在 `getAction()`
  的返回面上；`G_FCMP` 的 action（`custom`）是对拍过的，表内容不是。
- `A_G_SREM#3`（`not AEABI && not HW divide` 的 libcall 分支）在真实 ABI 下取不到：
  试过的 triple 全部 `isTargetAEABI()` 为真。cases 把它报成 `unexercised`。
- `A_G_LOAD#1` 是 `unsupportedIfMemSizeNotPow2()` 那条 `unsupported`，在查询集里
  `unexercised`：mem 轴上的候选（s8/s16/s32/s64/p0）字节数全是 2 的幂，没有一条
  能走到它。
- `A_G_LOAD#3`（VFP2 下的 `narrow(slot(0), ty(A_s32))`）是 `shadowed`：同轴上先命中
  的 `legal`（s64 + align 32）把它挡在前面。
- 这三条和 WebAssembly 报的 `shadowed/unexercised` 是同一口径：列出来、不静默，
  也不为了清零去改分区。

## 13 Mips 转正（2026-11-09）

Mips 的 legalizer 也在 `lib/Target/Mips/MipsLegalizerInfo.cpp`（没有 `GISel/`
子目录），构造函数 264 行、48 rulesets / 95 rules。它一开始有 7 条拒绝，分四种形状：

| C++ | 处理 |
|---|---|
| `CheckTyN(0, Query, {s32})` | `query_helper()`：纯查询函数，内联成 `in(slot(0), [...])` |
| `CheckTy0Ty1MemSizeAlign(Query, {{v, p, bits, allowUnaligned}, ...})` | 内联成“一项一个析取分支”：两个槽、内存类型的位宽、以及（除非该项声明允许非对齐）`bits <= align_of(mem_slot(0))` |
| `isUnalignedMemmoryAccess(a, b)` | 就是 `a > b` |
| `assert(...);`（构造函数和 lambda 里都有） | 跳过：断言是构建期契约，不是规则的一部分 |

第三条断言里有个坑：`CheckTy0Ty1MemSizeAlign` 的第一个分支要求“内存位宽是 2 的幂”，
但这条由每个分支的常量相等隐含了，所以直接按分支展开就够，不需要额外的 `is_pow2`。

`bool NoAlignRequirements = true;` 这种**常量** bool 现在折进环境，不再变成
`feature Mips_NoAlignRequirements = true` 这样的假配置轴；`true`/`false` 也进了
`const_eval`。

配置轴三个，先用探针打出 `MipsSubtarget` 真值再写表：

| config | CPU / mattr | MSA | MIPS32r2 | 非对齐访问 |
|---|---|---:|---:|---:|
| `mips32` | `mips32` | ✗ | ✗ | ✗ |
| `mips32r2` | `mips32r2` | ✗ | ✓ | ✗ |
| `mips32r6` | `mips32r6` | ✗ | ✓ | ✓ |
| `mips32r5-msa` | `mips32r5` `+msa,+fp64` | ✓ | ✓ | ✗ |
| `mips32r6-msa` | `mips32r6` `+msa,+fp64` | ✓ | ✓ | ✓ |

MSA 要求 `+fp64`，否则 `createTargetMachine` 直接 abort。

### 13.1 结果

```
../ab/run-mips-end-to-end.sh TREE BUILD /tmp/mips.inc OUT
{"agree": 1647, "disagree": 0, "ref_asserted": 9}
```

1,656 条查询里 1,647 条两侧同答案，9 条**官方侧断言、我们侧给答案**。那 9 条是
同一形状：`G_LOAD` 读 4 字节非对齐内存、值槽比 32 位宽（`s33`/`s63`/`s64`），
发生在不支持非对齐访问的三个配置上。上游 `customIf` 里

```cpp
assert(QueryMemSize != 32 && "4 byte load and store are legal");
```

的前提不成立：它的 `legalIf` 只给 `s32`/`p0` 声明了 32 位访问，值槽更宽时
根本到不了 `legalIf`。这是上游缺陷，不是规则差异：

```sh
llc -mtriple=mips-unknown-linux-gnu -mcpu=mips32r2 -global-isel \
    -run-pass=legalizer -o /dev/null /tmp/mips-load.mir
llc: .../MipsLegalizerInfo.cpp:144: ... Assertion `QueryMemSize != 32 && "4 byte load and store are legal"' failed.
```

MIR 和补丁建议落在
`/home/ubuntu/admin/upstream-issues/2026-11-09-16-gisel-mips-4byte-unaligned-load-assert.md`。

这一类在 `diff.py` 里是**显式**的：`--allow-ref-asserts 9` 把它记成已知类别，
数量对不上就 rc=1。它不是“忽略”，是“钉住”：新增一类断言会让数字变，跑挂。

### 13.2 顺带修的两处出题缺陷（影响所有 target）

Mips 的断言把两个一直存在的问题顶了出来，修在 `gisel/cases.py`，因此**所有
target 的查询数都变了**（LOOP.md 里的表是新的）：

1. **MMO 的对齐必须是 2 的幂。** boundary 探针原来用 `align ± 1`，会造出
   `align 15` 这种 MMO；上游 `isUnalignedMemmoryAccess` 在断言构建里第一件事就是
   `assert(isPowerOf2_64(AlignInBits))`。现在探的是相邻的 2 的幂（`align/2`、`align*2`）。
2. **读内存的 opcode 必须带内存描述符，且内存位宽不能超过值槽。**
   `G_LOAD` 少一个 MMO 时上游会读 `MMODescrs[0]`（空 ArrayRef → 断言）；
   `QueryMemSize <= Size` 也是上游自己写下的契约。这两条现在在 `emit()` 这个
   唯一出口上判，boundary/outside 探针也走同一条路。

计数从 X86 3,217 / AArch64 12,952 / RISC-V 6,301 / M68k 41 / WebAssembly 942 /
PowerPC 98 / ARM 1,670 变成 3,027 / 12,583 / 6,149 / 35 / 886 / 94 / 1,614，
每个 target 都按新题面重跑过对拍，`disagree = 0` 不变。

### 13.3 未覆盖

- `Mips_G_ZEXT#0` / `Mips_G_TRUNC#0` 是 `legal not true`（C++ 里
  `.legalIf([](const LegalityQuery &) { return false; })`），cases 记成
  `unexercised`——它本来就不可满足，不是漏题。
- `Mips_G_ZEXTLOAD#1/#2` 是 `shadowed`：同轴上更早的规则先命中。
- `legalizeCustom()` 里 Mips 自己拆 load/store 的逻辑不在对拍面内：
  我们只比 `getAction()`，不比后续的 legalize 结果（和 PPC、ARM 同一口径）。

## 14 SPIRV：第一个“配置不在 triple 里”的目标

SPIRV 是第 9 个接入 A/B 的目标，也是第一个不能靠 triple 表达全部配置的目标：
legalizer 读 `ST.isShader()`、`ST.getPointerSize()`、`ST.canUseExtInstSet(OpenCL_std)`
和四个扩展查询，而 triple 只决定指针宽度。runner 的写法是上游自己验证过的：
用 `spirv{32,64}-unknown-unknown` 建 subtarget（environment 是 `Unknown`，允许
`setEnv`），再 `initAvailableExtensions` + `setEnv(Kernel|Shader)`，最后构造 legalizer。
共享的 `query_runner_common.h` 为此加了一个默认为空的 `tweakSubtarget` 钩子，其它
target 的代码逐字节不变。

### 14.1 语料

`upstream-source/importer/import-cxx.py SPIRV`：83 rulesets / 353 rules / 0 refused。0 拒绝的关键是
在 importer 里补了 SPIRV 用到的写法：

- `auto &X = cond ? A : B` 类型集别名（`Types.set_alias`）；
- `unsigned N = cond ? a : b` 与 `= ST.getPointerSize()`（`int_ternary`）；
- `for (auto Opc : getTypeFoldingSupportedOpcodes())` + `switch`，展开成 28 个 opcode；
- `fewerElementsIf` / `changeElementSizeTo` / `typeOfLongVectors` 等 helper 内联；
- `this->ST = &ST` / `GR = ...` 归入“constructor plumbing”，在生成 ctor 里补回；
- `G_STRICT_*` 在 `opcode-slots.json` 里跟随基类 opcode 的槽数（`ConstrainedInstruction<G_XXX>`）。

生成的 `.inc` 不依赖任何 LLVM 头文件改动：`fewer(slot, N)` 通过公开的
`LegalizeRuleSet::fewerElementsIf(pred, changeElementCountTo(...))` 表达，
而不是给 `LegalizerInfo.h` 加一个 `core` 方法（那条路试过，`actionIf` 是 private，
最终选了公开 API）。

### 14.2 对拍

```
../ab/run-spirv-end-to-end.sh TREE BUILD /tmp/spirv.inc OUT
{"agree": 5136, "disagree": 0, "unanswerable": 4}
```

5,136 条查询（6 配置），5,132 条两侧同答案，0 条分歧；4 条两侧都断言，是同一个
上游缺陷：`SPIRVLegalizerInfo.cpp:336` 在 `fewerElementsIf` 里把
`changeElementCountTo(0, ElementCount::getFixed(MaxVectorSize))` 写成了
`changeElementSizeTo(0, MaxVectorSize)`。重载解析选中的是
`changeElementSizeTo(TypeIdx, FromTypeIdx)`，于是去读 `Query.Types[16]`，
而 `G_SPLAT_VECTOR` 只有 2 个类型槽。查询固定为 4 条（`--expect-unanswerable 4`），
新增一类断言会让数字变、跑挂。issue 落在
`/home/ubuntu/admin/upstream-issues/2026-11-09-17-gisel-spirv-splat-vector-element-count-overload.md`。

### 14.3 对拍抓出来的三个 importer/emitter 缺陷

SPIRV 第一次把“同一个配置选择在多个参数位置出现”和“feature 引用 feature”带进语料：

1. **feature 声明顺序。** `Spv_IsExtendedInts` 读 `Spv_hasArbitraryPrecisionInts`，
   但 emitter 按字母序输出，生成的 C++ 引用未声明变量。现在按依赖拓扑排序，
   依赖闭包一起输出，成环报错。
2. **选择集在多个位置必须相关。** `legalForCartesianProduct(allowedVectorTypes,
   allowedVectorTypes)` 的 `allowedVectorTypes` 是三元的；按位置独立展开会造出
   `isShader and not isShader` 这种不可达规则，而且带着错误的操作数集合。现在
   同名引用只展开一次，各位置取同一分支。
3. **`vectorElementCountIsLessThanOrEqualTo` 少了固定向量守卫。** 上游是
   `isFixedVector() && count <= N`；我们原来的 `num_elems(scalar) <= N` 对标量读 0，
   于是 0 <= 4 成立，SPLAT/UNMERGE 的标量查询被错判成 `Legal`。新增
   `is_fixed_vector(type)` 谓词（DSL、eval、inc 三处），`_count_cmp` 统一带上守卫。

修完这三处后 SPIRV 的 18 条分歧归零。

### 14.4 未覆盖

- 4 条 `G_SPLAT_VECTOR` 查询两侧都断言（见 14.2），没有答案可比。
- `legalizeCustom()` 的 SPIR-V 专属 legalize 不在对拍面内，只比 `getAction()`。
- 扩展轴只枚举了 legalizer 真正读取的四个：`SPV_ALTERA_arbitrary_precision_integers`、
  `SPV_KHR_bit_instructions`、`SPV_INTEL_int4`（经 `IsExtendedInts`）、`SPV_EXT_long_vector`。
