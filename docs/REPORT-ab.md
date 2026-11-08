# 工作台报告：新旧规则实现的对拍（A/B）

这是**工作台报告**，不是 gisel 的功能报告（边界见 `docs/SCOPE.md`）。它记录的
是“拿 gisel 生成的 `.inc` 去替换现网实现，然后逐条比较答案”的过程和结论：

- 工具链是 `tools/ab/`（双 runner）和 `tools/refresh-oracle.sh`；
- 题目来自 `gisel cases`，答案来自编译出来的两个 legalizer；
- 结论只说明**同一批查询上两个实现一致**，不说明规则本身正确，也不说明
  gisel 之外的东西被验证过。

`docs/REPORT-cases.md` 只讲 gisel 的用例生成（算法、证据、被否决的方案），
两者不要混着读。

## 1 全量端到端 A/B（2026-11-07）

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

AArch64 使用同一套端到端流程，但题目生成算法固定为 LLVM 的
`AArch64LegalizerTablePointsForTest.inc` 点（当时 1,190 个）：按九个固定配置
过滤不可表示的类型，规范化 LLT，按完整查询键去重，并把 9,591 作为硬校验值。
结果为：`ref=9591 ours=9591 matched=9591 agree=9591`，`disagree=0`，缺失和
错误均为 0。压缩得到 4,168 条回归查询，其中 equivalence 3,159、boundary 656、
outside 353，`oracle_missing=0`、`evaluator_errors=0`。

这一段是 11-07 的记录。后来的两个改动让它过时了：TypeSize 取 known-min、
`G_GLOBAL_VALUE` 恢复 `p0` 约束（domain 1,190 → 1,191）。当前的 AArch64 结论
以 §2 为准。

## 2 端到端对拍：AArch64 的 4 元组 mem（2026-11-08）

题目不是 LLVM 的 1,191 个 table point，而是 `gisel cases` 生成的 10,029 条
查询：九个配置，`mems.orderings = [NotAtomic, Unordered, Acquire, Release,
SequentiallyConsistent]`，其中 1,395 条带 `[mty, align, ordering,
failure_ordering]`。轴文件 `tests/cases/aarch64-mem-orderings.axes.json` 入库，
重跑上面的 `gisel cases` 得到逐字节相同的 10,029 条。

这一轮两个 runner 来自**同一个** explore 构建：`runner.official` 用官方构造
函数，`runner.ours` 只替换成 gisel 生成的 `AArch64LegalizerInfo.inc`。整个
流程是一条命令（`tools/ab/run-aarch64-end-to-end.sh`，参数和被替换的文件见
§2.4）：

```sh
tools/ab/run-aarch64-end-to-end.sh "$TREE" "$BUILD" \
  tests/artifacts/aarch64.inc /tmp/a64-e2e
```

脚本内部先跑 `gisel cases`（`--axes tests/cases/aarch64-mem-orderings.axes.json`）
生成查询，再分别喂给两个 runner，最后 `gisel diff`。

结果分两段。修掉 §2.1 的两个 TypeSize 洞之后是
`10,005 / 24 / 179`；再把 §2.2 的两条语料 bug 修掉之后是：

```text
queries=10,029  agree=10,029  disagree=0  unanswerable=179  errors=0
```

`agree` 把两边都答不了的 179 条也算作一致，所以 10,029 = 9,850 条真题 + 179
条对称的 `unanswerable`。两个答案文件 `official3.jsonl` 与 `ours3.jsonl` 的
SHA-256 相同（`3c12728a…`）：不是“语义等价”，是逐字节相同的输出。

179 条在两个 runner 上完全同位置，是同一批 LLVM 断言（`G_ADD` 的 scalable
向量等），输出对称的 `unanswerable`，不计入分歧。上一轮报告的 206 不能逐条
对比：那一轮官方 runner 链的是 ct-instr-trunk，这一轮两侧都换成 explore
同一棵树。

### 2.1 修掉的两个 TypeSize 洞

| 条数 | opcode | 修复前 | 根因 |
|---:|---|---|---|
| 36 | G_LOAD | official `Unsupported`，ours 断言 | gisel 的 `.inc` 和 `.td` emitter 都把 `SizeInBytesOf` 渲染成 `getSizeInBytes()`，再交给 `isPowerOf2_32`。`LLT` 返回 `TypeSize`，scalable 时隐式转整数直接 `reportFatalInternalError`。 |
| 36 | G_STORE | 修完上面后 official 单边断言 | 手写 C++ 的 `memSizeInBytesNotPow2` 也在把 `TypeSize` 往 `has_single_bit<uint32_t>` 里塞；同一个洞，只是这次在参考实现里。 |

两处都改成先取 known minimum，语义与 `memSizeNotByteSizePow2` 一致：

- `gisel/backend/llvm_inc.py`：`SizeOf` / `SizeInBytesOf` 输出
  `getSizeInBits().getKnownMinValue()` / `getSizeInBytes().getKnownMinValue()`。
- `utils/TableGen/LegalizerInfoEmitter.cpp`：同样两个 observer。
- `lib/CodeGen/GlobalISel/LegalityPredicates.cpp`：
  `memSizeInBytesNotPow2` 使用 `getSizeInBytes().getKnownMinValue()`。

为什么是 known minimum：`LegalizerCore.td` 把 `SizeOf` 和 `SizeInBytesOf` 都声明
为 `SortInt`；gisel 的 evaluator 也一直按 known-min 整数比较。生成代码和参考
实现现在都遵守这条契约，而不是依赖 `TypeSize` 的隐式转换。

验证（explore 树 + 对应构建）：

```text
python3 -m unittest discover -q -s tests                  # 151 tests OK
llvm-lit -s -j24 llvm/test/TableGen                      # 544 passed
GlobalISelTests --gtest_filter='LegalizerInfoTest.*'     # 4 passed
llvm-tblgen -gen-legalizer ... | cmp aarch64.inc         # 逐字节一致
llvm-tblgen -gen-legalizer-table ... | cmp aarch64.table.inc  # 逐字节一致
```

### 2.2 修掉的两条语料 bug（24 条）

| 条数 | opcode | official | ours（修复前） | 根因 |
|---:|---|---|---|---|
| 16 | G_SMIN | Lower | WidenScalar→s32 | 基线是 `.minScalar(HasCSSC, 0, s32)`：`minScalar(bool,...)` 是**构造期**开关，非 CSSC 配置里这条 widen 根本不存在。语料写成无条件 widen，于是 `bf16`、`i8` 被我们加宽，基线直接 lower。 |
| 8 | G_GLOBAL_VALUE | Unsupported | Legal | 基线 `.legalFor({p0})`，语料写成 `legal not AArch64_SmallCodeModel`，漏了类型约束，把 `s32` 也判成 Legal。 |

改动（语料 + 生成侧 `.td` 必须同时改，否则 oracle 会用旧规则生成）：

```text
tests/corpus/AArch64LegalizerInfo.gisel:321
-    widen(slot(0), ty(AArch64_s32))
+    widen(slot(0), ty(AArch64_s32)) when all_of(AArch64_HasCSSC)

tests/corpus/AArch64LegalizerInfo.gisel:928
-    legal not AArch64_SmallCodeModel
+    legal (not AArch64_SmallCodeModel and slot(0) == ty(AArch64_p0))

llvm/lib/Target/AArch64/GISel/AArch64LegalizerInfo.td:326
-    CoreWiden<(Slot 0), (Ty AArch64_s32)>,
+    CoreWidenIf<(Slot 0), (Ty AArch64_s32), (CoreAll AArch64_HasCSSC)>,

llvm/lib/Target/AArch64/GISel/AArch64LegalizerInfo.td:960
-    CoreLegal<(CoreNot AArch64_SmallCodeModel)>,
+    CoreLegal<(CoreAll (CoreNot AArch64_SmallCodeModel), (CoreEq (Slot 0), (Ty AArch64_p0)))>,
```

写成 `all_of(...)` 而不是裸 `AArch64_HasCSSC`、写成 `slot(0) == ty(...)` 而不是
`in(slot(0), ...)` 不是为了好看：core 正常形要求 guard 是 dag，单类型成员是
`eq`；两个出口（`--emit=inc` 和 tblgen 的 `-gen-legalizer`）要逐字节对上，语料
就得跟 `.td` 同一种拼写。

### 2.3 分母自检：eval 的答案 vs 跑起来的 inc

对拍最怕“题目和答案都来自同一处”。补一条 gate：把同一份 10,029 条查询直接喂
给 `gisel eval`，再和 `runner.ours`（真的把 `aarch64.inc` 编译进去的那一个）
逐条 diff：

```sh
python3 -m gisel eval --doc tests/artifacts/aarch64.core.json \
  --features tests/cases/features.json \
  --cases /tmp/a64-ord-cases3.jsonl \
  --answers /tmp/a64-fixed/eval.answers.jsonl

python3 -m gisel diff /tmp/a64-fixed/ours3.jsonl \
  /tmp/a64-fixed/eval.answers.jsonl --json
```

结果：9,850 条两侧都有答案的查询 **0 分歧**；剩下 179 条是 C++ 侧断言、
evaluator 侧照常回答，diff 把它们记成 disagree —— 这是预期的，它们就是 §2
里那批对称 `unanswerable`，不是规则分歧。`--answers` 是这一轮给 `gisel eval`
新增的模式（`--cases` 里没有期望值时用）。

### 2.4 复现与指纹

```sh
# 1) 语料 → .inc/.core
python3 -m gisel gen tests/corpus/AArch64LegalizerInfo.gisel \
  --emit=inc --out /tmp/a64-fixed/AArch64LegalizerInfo.inc

# 2) oracle 跟着 .td 重生成（llvm-tblgen 来自同一个 explore 构建）
TREE=/home/ubuntu/llvm/trees/explore BUILD=/home/ubuntu/llvm/builds/explore \
  tools/refresh-oracle.sh

# 3) 一条命令：两个 runner + 10,029 条查询 + diff
tools/ab/run-aarch64-end-to-end.sh "$TREE" "$BUILD" \
  tests/artifacts/aarch64.inc /tmp/a64-e2e

# 4) 分母自检（§2.3）
python3 -m gisel eval --doc tests/artifacts/aarch64.core.json \
  --features tests/cases/features.json \
  --cases /tmp/a64-e2e/queries.jsonl --answers /tmp/a64-e2e/eval.answers.jsonl
python3 -m gisel diff /tmp/a64-e2e/ours.answers.jsonl \
  /tmp/a64-e2e/eval.answers.jsonl --json
```

本轮输入与产物（SHA-256，前 16 位）：

| 文件 | sha256 |
|---|---|
| `tests/corpus/AArch64LegalizerInfo.gisel` | `0a54f35444177f78b…` |
| `tests/artifacts/aarch64.inc` | `67077b8e249266b4…` |
| `tests/artifacts/aarch64.table.inc` | `20017c2d8a834400d…` |
| `tests/artifacts/aarch64.core.json` | `cf71476ba00211ae…` |
| 10,029 条查询 | `f3419d32581e9575…` |
| `runner.official` / `runner.ours` | `0af9d83a0a9e9112…` / `04ee725919c496a2…` |
| official / ours 答案 | `1c590364bd7a51b4…`（两侧逐字节相同） |
| eval 答案 | `927a2b0a9a5a38a0…` |

llvm-project 侧：`85a4da33012a`（TypeSize 取 known-min）与 `e88a24a0fe84`
（本轮两条 guard）。`.td` 不是手改的：它由 `llvm-dev/tools/gisel_td.py gen` 从
`.gisel` 生成，本轮补上 `dsl_spike` 的 feature 名谓词后，`gen` 对 AArch64 和 X86
两份 `.td` 都逐字节复现，`check` 通过。AArch64 单元测试的 reviewed domain 因此
从 1,190 个 table point 变成 1,191（多出 `G_GLOBAL_VALUE` 的 `p0`），两个
differential test 仍然 0 分歧（1,191 点 × 9 配置，9,641 条可比较）。

查询集是用**修好之后**的语料重生成的，所以个别点换掉了：`G_SMIN` 的 `bf16`
不再是一条 widen（新语料里它落到 lower），`G_GLOBAL_VALUE` 多出 `bf16`/`f128`
这些非 `p0` 的类型。条数仍是 10,029。

一个踩过的坑：`aarch64_generated_ctor.cpp` 按名字 include
`AArch64LegalizerInfo.inc`，而构建目录的 `unittests/Target/AArch64/` 下也有一份
自己生成的同名文件。第一版 `run-aarch64-end-to-end.sh` 直接把
`tests/artifacts/aarch64.inc` 传进去，结果先命中的是那份**旧的**生成文件，跑出
96 条假分歧。现在 `build-aarch64-runner.sh` 先把 `INC` 复制到
`<OUT>.generated-inc/AArch64LegalizerInfo.inc` 并把这个目录放在 `-I` 最前，
传什么文件名都不会再串。

### 2.5 这轮证明了什么，没证明什么

证明的：在同一棵 explore 树、同一批 10,029 条查询上，我们转写的 AArch64 规则
生成的 C++ 与现网手写 legalizer 逐条一致；oracle 的 C++ 与我们生成的 C++
`cmp` 逐字节相同；evaluator 与编译出来的生成代码也逐条一致。这是一条能对外
展示的“不差于现网基线 + 三处口径互相钉死”的证据。

没证明的：

- 规则**本身**对不对。语料是照着现网转写的，这轮只证明转写忠实；上游规则是否
  漏了某个类型组合，对拍看不见。
- 179 条 C++ 断言没有归因。它们在两侧同位置，说明不是规则分歧，但断言本身
  是 LLVM 的问题，本轮未覆盖。
- 配置只覆盖 `tests/cases/features.json` 的 9 个，不是全部 subtarget 组合；
  查询形状只覆盖 `gisel cases` 的等价类 + 边界 + 域外，不是任意 LLT。
