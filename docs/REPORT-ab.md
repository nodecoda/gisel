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
64 位指针，每个配置 26,097 条，共 104,388 条（§4 加上 opcode 形状过滤后是
每配置 25,127 条 / 共 100,508 条；这一节保留当时的快照）。官方生成的
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
生成查询，再分别喂给两个 runner，最后 `tools/ab/diff.py`。

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
llvm-tblgen -gen-legalizer ... | cmp aarch64.inc         # 逐字节一致（本项目后端）
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
  --cases /tmp/a64-e2e/queries.jsonl \
  --answers /tmp/a64-e2e/eval.answers.jsonl

python3 tools/ab/diff.py /tmp/a64-e2e/ours.answers.jsonl \
  /tmp/a64-e2e/eval.answers.jsonl --json
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
python3 tools/ab/diff.py /tmp/a64-e2e/ours.answers.jsonl \
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

## 3 AB harness 首轮 smoke（2026-11-08）

这一节是 `tools/ab/ab.py` 的首轮运行记录，**不是验收结论**；它证明编排、
答案文件、全 key diff、恢复和 ledger 能串起来，同时暴露了两处待归因的差异。

### 3.1 X86：非侵入式 generated-ctor

```sh
head -400 /tmp/x86-domain.jsonl > /tmp/x86-400.jsonl
python3 tools/ab/ab.py run --target x86-ctor \
  --tree /home/ubuntu/llvm/trees/explore \
  --build /home/ubuntu/llvm/builds/explore \
  --queries /tmp/x86-400.jsonl \
  --out /tmp/ab-x86-ctor --state /tmp/ab-state-x86-ctor \
  --compare full
```

结果：

```text
queries=400  agree=400  disagree=0  unanswerable=0
missing_ref=0  missing_ours=0  rc=0
```

`x86-ctor` 只替换 `X86LegalizerInfo` 构造函数，不 swap build 里的库；
因此它可以在共享 build 上跑，不动 `libLLVMX86CodeGen.so`。`x86`（swap）
adapter 已通过 `--dry-run` 校验，真实 swap 留给专用 build。

### 3.2 AArch64：10,271 条全量

```sh
python3 -m gisel cases tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json \
  --axes tests/cases/aarch64-mem-orderings.axes.json \
  --out /tmp/a64-queries.jsonl --json

python3 tools/ab/ab.py run --target aarch64 \
  --tree /home/ubuntu/llvm/trees/explore \
  --build /home/ubuntu/llvm/builds/explore \
  --queries /tmp/a64-queries.jsonl \
  --out /tmp/ab-a64-run --state /tmp/ab-state-a64 \
  --compare full
```

结果：

```text
queries=10271  agree=10219  disagree=52  unanswerable=224
missing_ref=0  missing_ours=0  rc=1
```

52 条的构成（`diff.json` 的 `first_details`）：

```text
status    45   官方侧断言（unanswerable），ours 侧给出 Unsupported
type_idx   7   G_SITOFP 的 v2s63 类点，两侧都 WidenScalar，但改写槽不同
```

这说明 harness 能区分“单侧断言”和“答案不同”，但**还没有归因**。这两个
差异更像“explore 树的官方实现 / 当前语料修订”之间的漂移，不是 harness
自身的 diff 错误；下一轮要用 official/ours/eval 三方矩阵定位。

### 3.3 查询数变化

旧报告里的 10,029 是上一版语料 + axes 的快照；§3 写的时候
`tests/cases/aarch64-mem-orderings.axes.json` 生成 10,271 条，adapter 的
`query_count` 随之写上。§4 修掉生成器形状过滤后是 10,244 条，**以 §4 为准**；
条数变化会被当成契约失败，而不是静默接受。

### 3.4 产物与恢复

- 答案文件逐行平行，`run-queries.py` 把断言点标成对称/单侧 `unanswerable`；
- `diff.json` 含 `mode/agree/disagree/...` 和 `first_details`；
- `ledger.jsonl` 记录 tree HEAD、inc sha、query sha、runner sha、计数；
- `ab.py verify` 对 AArch64 返回 `OK`，build 未被修改。

## 4 归因与收敛：52 → 9（2026-11-08 晚）

§3 的 52 条已经全部归因：**43 条是我们自己的问题，9 条是上游缺陷**。修完
我方两条之后，同一批查询缩小到 10,244 条，结果是：

```text
queries=10244  agree=10235  disagree=9  unanswerable=224
missing_ref=0  missing_ours=0  errors=0  rc=1
```

三方矩阵（official / ours / gisel eval）：

```text
matrix = {all_agree: 10011, both_assert: 224, official_assert: 9}
owner  = {query: 9}
```

224 条 `both_assert` 两边同位置断言，输出对称，不进差异；`all_agree` 里已经
包含 ours 编译产物与 eval 的逐条一致。

### 4.1 36 条：生成器给了 MIR 验证器不接受的形状

`G_MERGE_VALUES f128, nxv16i8` 这类查询，官方侧 abort：

```text
LLVM ERROR: cannot implicitly convert a scalable size to a fixed-width size
             in `TypeSize::operator ScalarTy()`     AArch64LegalizerInfo.cpp:1206
```

但根因不在 LLVM 的 legalizer。`MachineVerifier.cpp:1502-1510` 明确规定
`G_MERGE_VALUES` 只能合并标量；同一份形状写成 MIR 会在 verifier 就被拒：

```text
*** Bad machine code: G_MERGE_VALUES cannot operate on vectors ***
```

也就是说这批查询**没有到达 legalizer 的路径**，是 domain 把“不可表示的
形状”当成了题面。修法（我方）：

- `gisel/cases.py` 新增 `type_shape_ok(opcode, types)`，按 verifier 的形状
  约束裁剪：`G_MERGE_VALUES` 全标量；`G_UNMERGE_VALUES` 要么全标量，要么
  全向量且元素类型与 scalability 一致（它是 `G_CONCAT_VECTORS` 的逆）。
- `gisel/cases.py::_queries` 和 `gisel/domain.py::enumerate_domain` 共用它。

计数影响：AArch64 查询 10,271 → 10,244；X86 domain 每个配置 26,097 →
25,127（4 个配置 104,388 → 100,508）。**这不是缩小覆盖面**：被去掉的形状
没有任何 `llc` 输入能产生。

### 4.2 16 条：`widenScalarOrElt…` 被转录成了标量版本

`G_SITOFP` / `G_FPTOSI` 的 `v2i63` 点，官方 widen 元素到 `v2i64`，我们却
落到后面的 `changeElementSize(0, 63)`，造出 `f63`：

```text
ours runner: Wrong SizeInBits for IEEE Floating point!  LowLevelType.h:151
eval       : WidenScalar slot 0 -> f63
```

差异来自 C++ 方法被压成同一个拼写：

| 上游方法 | 谓词 | 语料（修复前） |
|---|---|---|
| `widenScalarToNextPow2` | `sizeNotPow2` → `isScalar() && !pow2(总位宽)` | `widen(slot(i), pow2)` |
| `widenScalarOrEltToNextPow2(OrMinSize)` | `scalarOrEltSizeNotPow2` → `!pow2(元素位宽)` | 也是 `widen(slot(i), pow2)` |

`v2i63` 总位宽 126、元素 63：标量谓词不命中，元素谓词命中。`pow2` 是标量
拼写，所以我们的规则静默失效。

修法（我方）：`tools/import-cxx.py` 区分三种方法，`...OrElt...` 一律输出
`widen(elem_of(slot(i)), pow2)`（`MinSize=0` 时两种 `...OrElt...` 谓词相同；
显式 `MinSize` 仍走 `widen(slot(i), <int|select>)`）。重生成语料只改了 2 行
（`A_FPTOSI` 一条、`A_SITOFP` 一条），`tests/artifacts/aarch64.*` 跟着重生成。

### 4.3 剩下 9 条：上游缺陷，已落盘

`G_UNMERGE_VALUES nxv16i8, nxv16i8`（以及任何 scalable 拆分的真实形状）在
官方 `legalIf` 里对 scalable 源类型做 `switch (getSizeInBits())`，隐式转
`uint64_t` 直接 abort。合法 MIR、单 pass 可复现，已按 `admin/AGENTS.md` §4.1
写到：

```text
/home/ubuntu/admin/upstream-issues/2026-11-08-12-gisel-aarch64-unmerge-scalable-assert.md
```

状态：待搜重后提单。ours 侧（gisel 生成的 inc）对同一查询返回
`Unsupported`，不崩，也不参与这条缺陷。

### 4.4 本轮指纹

| 文件 | sha256 |
|---|---|
| `tests/corpus/AArch64LegalizerInfo.gisel` | `df5a0d8d1020b9c5…` |
| `tests/artifacts/aarch64.inc` | `bf58c71f2ba8193b…` |
| `tests/artifacts/aarch64.core.json` | `fad7c0881e6a01ba…` |
| 10,244 条查询 | `5670b99944b1f92b…` |
| `runner.official` / `runner.ours` | `0af9d83a0a9e9112…` / `8650c0060b7014a8…` |
| official / ours 答案 | `f3b7baa56ac2b54f…` / `fad6618722293175…` |

复现：

```sh
python3 -m gisel cases tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json \
  --axes tests/cases/aarch64-mem-orderings.axes.json \
  --out /tmp/a64-queries2.jsonl --json

python3 tools/ab/ab.py run --target aarch64 \
  --tree /home/ubuntu/llvm/trees/explore \
  --build /home/ubuntu/llvm/builds/explore \
  --queries /tmp/a64-queries2.jsonl \
  --out /tmp/ab-a64-eval2 --state /tmp/ab-state-a64 \
  --compare full
```

### 4.5 仍未覆盖

- 224 条对称断言只证明“两边都不答”，没有归因到具体断言；要在崩溃点上
  逐个取栈才能说是 LLVM 的问题。
- 查询仍只覆盖 `gisel cases` 的等价类 / 边界 / 域外，不是任意 LLT。
- 配置仍是 `tests/cases/features.json` 的 9 个，不是全部 subtarget 组合。

## 5 单步一致为什么能推出多轮一致（2026-11-09）

前面的对拍只比 `getAction()` 一次返回值（§3），不比合法化跑完的最终结果。
这一节说明为什么**在这个模型里前者足以推出后者**，以及这个推导成立需要的
前提；前提没满足的部分单独列出，不并进结论。

### 5.1 命题

记一个状态

```text
S = (opcode, 类型向量, mem)
getAction(S) = (action, type_idx, new_type)      # 单步，已逐条比过
T(S)         = 把 mutation 作用到 S 上得到的新状态
```

合法化就是反复迭代 `T`，直到 `action` 是终结动作（`Legal` / `Lower` /
`Libcall` / `Custom` / `Unsupported`）。

> **命题**：若对所有可达状态 `S` 都有
> `getAction_ours(S) = getAction_ref(S)`，且 `T` 在两边是同一个函数，
> 则两边的整条合法化序列逐项相同，最终结果相同。

证明是归纳：首项相同 → 状态相同 → 下一项相同 → …；终止条件只由
`action` 决定，而 `action` 相同。

### 5.2 `T` 为什么是同一个函数

不是假设，是构造上的：AArch64 / RISC-V 的 ours runner 只多链了一个替身
构造函数（§3.1），`LegalizerHelper`、各 `legalize*`、`Custom` 回调、
`Libcall` 展开全部来自官方 `.so`。`T` 的输入只有
`(action, type_idx, new_type, 原指令)`，这四项我们逐项比过。

X86 的 `swap-library` 策略换的是整张表，但 `LegalizerHelper` 同样没动。

所以 §5.1 的第二个条件在三个 target 上都是白送的；真正要验的是第一个。

### 5.3 第一个条件的三个子前提

| # | 前提 | 含义 | 现状 |
|---|---|---|---|
| ① | 覆盖 | 可达状态都落在枚举出来的图里 | X86 93–94%，RISC-V 94.9%，AArch64 81.1% |
| ② | 闭包 | `T` 把同一个类映到同一个类 | **未通过** |
| ③ | 谓词可判定 | 类划分不是猜的 | opaque 状态占比见表 |

①②③ 缺一，命题就只在“已建图且闭包成立”的子集上成立，不能外推。

### 5.4 已证覆盖的实测数字

`covered = states - opaque - outside`，`outside` 是后继跑出声明域的状态，
它们的边没建，所以归纳在那里断掉。

| target | config | states | opaque | outside | covered | 比例 |
|---|---|---:|---:|---:|---:|---:|
| X86 | C0 | 73,431 | 1,012 | 4,071 | 68,348 | 93.1% |
| X86 | C1 | 73,420 | 1,016 | 3,062 | 69,342 | 94.4% |
| X86 | C2 | 73,350 | 1,016 | 3,074 | 69,260 | 94.4% |
| X86 | C3 | 73,431 | 1,012 | 3,903 | 68,516 | 93.3% |
| AArch64 | baseline | 763,488 | 128,581 | 15,605 | 619,302 | 81.1% |
| RISC-V | rv64gc | 423,342 | 14,409 | 7,358 | 401,575 | 94.9% |

八个 RISC-V 配置的 `cycles` 全为 0、`stuck` 全为 0；X86 四个配置同理。

`--check-closure` 把违例分成两类：`partition`（同一个类被推到多个目标类，
即 ② 不成立）和 `outside`（变异把类型推出声明域，即 ① 的缺口）。

| target | config | 默认 partition / outside | `--refine` 后 | classes |
|---|---|---:|---:|---:|
| X86 | C1 | 224 / 3,148 | **0** / 3,148 | 3,853 → 3,878 |
| RISC-V | rv64gc | 7 / 7,358 | **0** / 7,358 | 7,536 → 7,548 |
| AArch64 | baseline | 27 / 15,605 | **0** / 15,605 | 13,328 → 13,413 |

② 在三个 target 上已经可以关掉。默认分区确实把 `s3` 和 `s129` 并成一类
（widen 的目标依赖具体位宽，`pow2ceil` 让同一个 guard 类里的成员落到不同
宽度），`--refine` 按“成员落在哪个目标类”把它们分开，后继就重新成为类的
函数。X86 C1 的 224 条 `multiple target classes` 全部消失。

剩下的全是 ①：`outside`。例如 `G_ANYEXT s129 → s256`，`s256` 不在声明类型
里，图不为它建格。这不是分区问题，扩大声明域或加轴才能收掉，细化无能为力。

`--refine` 默认关闭，因为它改变第 2 篇的“原子”定义；命令行必须显式写。

### 5.5 所以多轮对拍不是下一步

② 已经修好（`--refine`），① 还留着 6%–19% 的口子。所以现在能说的是：
**在已覆盖的那部分状态上，多轮结果由单步唯一决定**；剩下的 `outside` 是
覆盖面缺口，不是等价性问题。

在这个前提下造 MIR 跑一遍 `llc`，得到的是“另一份实现比对”，不是新的信息。

多轮仍有独立价值，但那是另一个目的：**给上游找缺陷**（见 §5.6），不是给
本项目做 A/B 结论。

### 5.6 这份语料对上游的价值

查询集本身就是给现网的回归语料，不依赖“我们和现网一致”这个结论：

- 每条查询是 `(config, opcode, 类型, mem, imms)` 的一个点，与实现无关；
- 规模：X86 3,273 / AArch64 10,244 / RISC-V 6,140；
- 可直接落成 `.mir`，用 `llc -run-pass=legalizer` 跑（已在本树验证可行：

  ```sh
  llc -mtriple=aarch64 -run-pass=legalizer q.mir
  ```

  MIR 里 GlobalISel 类型写成 `<16 x s8>` / `<vscale x 16 x i64>`，不是
  `v16s8`）。

这条路径能暴露单步对拍看不到的两类问题：`mutationIsSane` 失败（§4.5 的
224 条对称断言里有实例）和合法化不收敛。它属于工作台，不属于 gisel 本体。

### 5.7 指纹与复现

| 文件 | sha256 |
|---|---|
| `tests/corpus/X86LegalizerInfo.gisel` | `04841d45f101b629…` |
| `tests/corpus/AArch64LegalizerInfo.gisel` | `df5a0d8d1020b9c5…` |
| `tests/corpus/RISCVLegalizerInfo.gisel` | `ea5d23f8ec814b4b…` |
| `gisel/graph.py` | `efe5d9b75b851a65…` |
| `gisel/eval.py` | `15a953dc67c45bfb…` |
| `gisel/cases.py` | `63b0db408275fb4c…` |

```sh
# 覆盖率与环检测
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --emit=core --features tests/cases/x86-features.json --config C1 --json

python3 -m gisel graph tests/corpus/AArch64LegalizerInfo.gisel \
  --emit=core --features tests/cases/features.json --config baseline --json

python3 -m gisel graph tests/corpus/RISCVLegalizerInfo.gisel \
  --emit=core --features tests/cases/riscv-features.json --config rv64gc --json

# 闭包（失败时 rc=1 并打印反例）
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --emit=core --features tests/cases/x86-features.json --config C1 \
  --check-closure

# 闭包 + 细化（partition 违规归零，只剩 outside）
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --emit=core --features tests/cases/x86-features.json --config C1 \
  --check-closure --refine
```

## 6 三个 target 的全量构建 + 全量 check-llvm（2026-11-09）

§1–§5 比的都是 `getAction()` 的答案。这一节换了口径：把 X86、AArch64、RISC-V
三份 `tests/artifacts/*.inc` 分别替换进现网的 legalizer 构造函数，重新编译，
然后跑**完整**的 `ninja check-llvm`。判据只有一条：不新增失败。

### 6.1 拦路的第一件事：`legalizer-info-validation.mir`

这一节记录走到全绿之前踩到的两个坑。第一个在 lit 侧：第一次换完 `.inc` 之后，
AArch64 和 RISC-V 的 `test/CodeGen/<target>/GlobalISel/legalizer-info-validation.mir`
变红。这个测试不看答案，看的是 `LegalizerInfo::verify()` 的调试输出：哪些
type/imm index 被规则覆盖了。

根因不是规则不同，是**入口不同**。上游大量使用声明式入口：

```cpp
.legalFor({s32}).widenScalarToNextPow2(0).clampScalar(0, s32, s64)
```

它们只给被点名的 type index 记一个已覆盖位。带 predicate 的自由入口
（`legalIf` / `customIf` / `core*To` …）则调用 `markAllIdxsAsCovered()`，
把所有位一次性点亮。语料里这两者被展平成同一种规则，第一版 `.inc` 就一律
生成自由入口，于是 verifier 打印 `SKIPPED: user-defined predicate detected`
而基线打印 `the first uncovered type index: 2, OK`。两者都 `return true`，
但文本比对不过——而且丢掉的是“覆盖面”这条信息本身。

### 6.2 生成侧补的三件事（`gisel/backend/llvm_inc.py`）

1. **还原声明式入口。** 规则 guard 恰好是“类型元组成员”时，按形状发
   `legalFor` / `lowerFor` / `libcallFor` / `customFor` / `unsupportedFor`
   （`FOR_OVERLOADS` 记录每个名字存在哪些 arity/gate 重载），以及
   `widenScalarFor`、`clampMinNumElements` / `clampMaxNumElements`。两种拼写都认：
   `in/inPairs/inTriples`，和 `slot(0) == T and slot(1) == T` 的合取。
2. **还原构造期 `if`。** `if (ST.hasX()) { build } else { build2 }` 被 importer
   展平成了逐规则 guard；重新抽出来才能保住 aliasing：只有一边被 build 时，
   另一个 opcode 保持零规则，组的第一个 opcode 才是 aliasing representative。
   纯 `if`（没有 else）只在“整组规则携带同一个 gate”时还原——否则那是上游逐规则
   写的 `legalFor(Pred, ...)`，提升到 builder 层会改变 verifier 的输出、也会让
   组丢掉 aliasing。嵌套的分支按递归还原（`_group`）。
3. **覆盖自检。** 上一条一旦判错，就可能把一个 ruleset 拆成“永远存在的一半”
   和“可能为空的一半”。所以发完之后算一遍：对每个 opcode，把**不在任何 `if`
   里**的规则覆盖到的 type index 合起来，必须覆盖满 arity 或者一个都没有；否则
   把涉及该 opcode 的 ruleset 退出“允许提升”集合重发。互补门（`X` / `!X`）算作
   必然成立，所以 `legalFor(Pred, …)` + `libcallFor(!Pred, …)` 照旧提升。
   这一条把 RISC-V `G_SPLAT_VECTOR` 那种“`hasVInstructions` 其实是内联谓词而不是
   构造期开关”的情况挡在了提升之外。

另外两个小口子：

- `gisel/data/opcode-slots.json` 增加了 `imm`（generic 立即数槽数，由
  `tools/gen-opcode-slots.py` 从 `GenericOpcodes.td` 重新冻结）。`xxxFor` 只记
  type index，而 `legalIf` 连 imm 一起点亮；像 `G_PREFETCH`（1 type / 3 imm）
  这种 opcode 换成 `legalFor({p0})` 会让 imm 检查变成 FAIL。
- `gisel/cli.py` 的 `inc` 出口不再合并同一 opcode 的多个 builder。手写 C++ 本来
  就会对同一个 opcode 建两次链，这个结构可被 verifier 观测到。

### 6.3 第二个红点：我们自己测试代码的变量遮蔽（已修）

上一版 §6 把基线里唯一那条红点（`ReferenceAnswersAreSpread`，
`Expected: (Legal) > (100u), actual: 4 vs 100`）当成“与本轮无关的既有失败”。
这个判断是错的：它不是上游的毛病，是**我们新写的测试自己写错了**。

根因是变量遮蔽。测试里把计数器声明成 `unsigned Legal` / `unsigned
Unsupported`，遮蔽了 `LegalizeActions::Legal` / `LegalizeActions::Unsupported`
枚举量，于是

```cpp
Legal += Step.Action == Legal;        // 左边是计数器，右边也是计数器
```

比的不是动作，是计数器自己，计数值永远上不去。用临时插桩打印直方图，真实分布是：

```text
action=0 (Legal)          511
action=1 (NarrowScalar)    10
action=6 (Lower)           70
action=7 (Libcall)        224
action=8 (Custom)          15
action=9 (Unsupported)    317
total                    1408
```

修法：计数器改名 `NumLegal` / `NumUnsupported` / `NumMutating`，比较一律写全
`LegalizeActions::Legal` 等，并在测试里留注释说明为什么不能叫 `Legal`。改完再用
`grep` 扫了一遍 `unsigned Legal|Unsupported|Custom|Lower|Libcall` 这种写法，
全仓没有第二处（唯一命中是 `ConstantRangeTest` 的 lambda 形参，无关）。

这一处修在 explore 树的工作区里
（`llvm/unittests/Target/X86/X86LegalizerInfoDifferentialTest.cpp`），和该分支上
其它未提交的实验性改动在一起，没有单独提交。

### 6.4 结果：基线 + 四轮，全部 0 失败

五轮的口径都是：**先 `ninja all` 做全量构建，再 `ninja check-llvm` 跑全量测试**
（RelWithDebInfo，assertions ON，`LLVM_ENABLE_PROJECTS=clang`，
`LLVM_TARGETS_TO_BUILD=X86;AArch64;RISCV`）。每轮先换 `.inc`，跑完 `restore`
回官方实现。

| 轮 | 替换的 target | `ninja all` | Total | Passed | Failed | `check-llvm` rc |
|---|---|---:|---:|---:|---:|---:|
| 基线 | 无（三份都是官方实现） | 0 | 80,629 | 54,920 | 0 | 0 |
| 1 | X86 | 0 | 80,629 | 54,920 | 0 | 0 |
| 2 | AArch64 | 0 | 80,629 | 54,920 | 0 | 0 |
| 3 | RISC-V | 0 | 80,629 | 54,920 | 0 | 0 |
| 4 | 三个同时 | 0 | 80,629 | 54,920 | 0 | 0 |

`ninja all` 每次都真的重编了受影响的 target（X86 轮 53 步、AArch64 轮 58 步、
RISC-V 轮 53 步、三合一 53 步，都包含 `libclang-cpp` 重链接），不是空转。

五轮的 `Skipped 62 / Unsupported 25,576 / Expectedly Failed 71` 也逐条相同。
也就是说：三个 target 分别替换、以及三个同时替换，全量结果和基线**逐条相同**，
既没有新增失败，也没有多出来的 unsupported。

第 4 轮（三份同时替换）另外抓的两个数：

```text
$ ./bin/llvm-lit -q test/CodeGen/AArch64/GlobalISel/ \
    test/CodeGen/RISCV/GlobalISel/ test/CodeGen/X86/GlobalISel/
Total Discovered Tests: 1534          # 0 failed

$ ./unittests/Target/X86/X86Tests --gtest_filter='*Legalizer*'
[  PASSED  ] 3 tests.
X86 legalizer differential: 1408 points x 10 configs, 14080 compared
```

gisel 自身：

```text
$ python3 -m unittest discover -q -s tests     # 210 tests OK
$ (cd tests/artifacts && sha256sum -c SHA256)  # 12/12 OK
```

### 6.5 输入指纹

| 文件 | sha256 |
|---|---|
| `tests/artifacts/x86.inc` | `c9b39260bb0e4cd6…` |
| `tests/artifacts/aarch64.inc` | `dbb97efba96c6f80…` |
| `tests/artifacts/riscv.inc` | `cbd91241c15878b7…` |
| `gisel/backend/llvm_inc.py` | `bcf46945678cd661…` |
| `tools/ab/swap-source-ctor.py` | `a2597b8ab96c284a…` |
| llvm 树 | `e88a24a0fe84` |

三份 `.inc` 都是本轮从 `tests/corpus/*.gisel` 重新 `gisel gen --emit=inc` 出来的，
和 `tests/artifacts/` 里入库的产物逐字节相同（`sha256sum` 一致）之后才拿去替换。

### 6.6 复现

```sh
cd /home/ubuntu/llvm/gisel
python3 -m gisel gen tests/corpus/X86LegalizerInfo.gisel     --emit=inc --out /tmp/swapinc/x86.inc
python3 -m gisel gen tests/corpus/AArch64LegalizerInfo.gisel --emit=inc --out /tmp/swapinc/aarch64.inc
python3 -m gisel gen tests/corpus/RISCVLegalizerInfo.gisel   --emit=inc --out /tmp/swapinc/riscv.inc

# 基线
cd /home/ubuntu/llvm/builds/explore && ninja all && ninja check-llvm

# 每轮：换 -> ninja all（全量构建）-> ninja check-llvm（全量测试）-> 恢复
cd /home/ubuntu/llvm/gisel
python3 tools/ab/swap-source-ctor.py apply --target x86 \
  --build /home/ubuntu/llvm/builds/explore --inc /tmp/swapinc/x86.inc
cd /home/ubuntu/llvm/builds/explore && ninja all && ninja check-llvm

cd /home/ubuntu/llvm/gisel
python3 tools/ab/swap-source-ctor.py restore --target x86 --build /home/ubuntu/llvm/builds/explore
python3 tools/ab/swap-source-ctor.py apply --target aarch64 \
  --tree /home/ubuntu/llvm/trees/explore --inc /tmp/swapinc/aarch64.inc
cd /home/ubuntu/llvm/builds/explore && ninja all && ninja check-llvm

cd /home/ubuntu/llvm/gisel
python3 tools/ab/swap-source-ctor.py restore --target aarch64 --tree /home/ubuntu/llvm/trees/explore
python3 tools/ab/swap-source-ctor.py apply --target riscv \
  --tree /home/ubuntu/llvm/trees/explore --inc /tmp/swapinc/riscv.inc
cd /home/ubuntu/llvm/builds/explore && ninja all && ninja check-llvm

# 三个同时
cd /home/ubuntu/llvm/gisel
python3 tools/ab/swap-source-ctor.py apply --target x86 \
  --build /home/ubuntu/llvm/builds/explore --inc /tmp/swapinc/x86.inc
cd /home/ubuntu/llvm/builds/explore && ninja all && ninja check-llvm

# 收工，恢复
cd /home/ubuntu/llvm/gisel
python3 tools/ab/swap-source-ctor.py restore --target x86     --build /home/ubuntu/llvm/builds/explore
python3 tools/ab/swap-source-ctor.py restore --target aarch64 --tree  /home/ubuntu/llvm/trees/explore
python3 tools/ab/swap-source-ctor.py restore --target riscv   --tree  /home/ubuntu/llvm/trees/explore
```

### 6.7 这轮证明了什么，没证明什么

证明的：我们生成的 `.inc` 换掉三个 target 的合法化规则之后，`ninja all` 全量
构建 rc=0，全量测试和基线逐条相同——`80,629` 条发现、`54,920` 通过、`0` 失败，
分别换和一起换都是这个数。`legalizer-info-validation.mir` 逐字通过，说明覆盖面
（不只是答案）也和现网一致。

没证明的：

- `.inc` 文本和上游手写的 C++ 不逐字节相同，只保证 `getAction()` 的行为和
  verifier 的报告一致。中间形态（规则顺序之外的结构、变量命名）是等价的另一
  种写法。
- 覆盖自检对 `opcode-slots.json` 里没有 arity 的 opcode（ATOMICRMW 家族）跳过，
  那些 opcode 的提升安全性没有静态论证，只由 lit 覆盖。
- 判据是“与基线完全相同”，不是“规则本身正确”。两边一起错的情况这套对拍抓不到。
- X86 的差分单测修复还在 explore 分支的工作区里，没有单独提交。
