# 分母的归属：一条规则都不能没有见证

状态：完成（2026-11-09）。基线 `c5ac359`。

## 1 链路

```
LLVM C++  --import-cxx-->  .gisel  --gisel cases-->  无答案查询  --对拍--> 两个 runner
```

“我们没漏上游的规则”只能由这条链的前两段保证：

- **C++ → .gisel**：`gisel-anchor/scripts/import-cxx.py` 只接受它认识的构造，别的一律带行号
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
| X86 | 328 | 292 (89.0%) | **317 (96.6%)** | 5 | 6 | 3,014 |
| AArch64 | 743（canonical） | 312 (42.0%) | **575 (77.4%)** | 38 | 130 | 12,559 |
| RISC-V | 413（canonical） | 320 (77.5%) | **355 (85.9%)** | 12 | 46 | 6,086 |

另外加了一次**定向搜索**：全局候选集没找到见证时，单独用该规则自己命名的类型
及其邻居枚举一遍。它只多找到 1 条（AArch64）——说明剩下的不是“搜得不够”，而是
真的被更早的规则盖住了。

## 4 剩下的规则是什么

2026-11-13 复核：X86 是 11 条（5 shadowed + 6 unexercised；多出的
`X_G_CTPOP#3` 是 `de8dbbf` 对齐 PR #235976 后不再被 C2 的向量查询见证）。
AArch64 / RISC-V 仍是 168 / 58 条。

X86 的 6 条 unexercised 有 4 条是 `clamp_min(0, X_s64, 2)` 这类：

```text
clamp_min(0, X_s64, 2)      # 触发条件是“s64 向量且 lane < 2”
```

固定单 lane 向量就是标量，而标量已经被前面的 `legal in(slot(0), [X_s32])`
之类答掉了。这类规则**在上游就是死的**：LLT 造不出这样的值。它们不是我们的
缺口，但也不该被算成“已验证”——现在被单列成 unexercised 并计入退出码。

AArch64 剩下的 171 条集中在 `G_STORE` / `G_LOAD`（多槽 + mem 描述）、
`G_ICMP`、`G_EXTRACT/INSERT_VECTOR_ELT`。2026-11-10 已把这 171 条逐条定性，
并把定向搜索的种子扩到 `on`/`to` 里的目标类型，见证数从 572 升到 584；比较结果槽过滤后为 575；
剩下的 159 条按原因分成四类，见 §9。

## 5 门禁

```sh
gisel cases tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --out /tmp/q.jsonl --strict-coverage
```

有任何规则既没有见证、又不是被证明可满足却遮蔽时，退出码 1，并打印前 20 条：

```text
cases: 11 rule(s) have no witness (6 unexercised, 5 shadowed); the query set
does not cover every rule
  X_G_IMPLICIT_DEF#16: unexercised
  X_G_IMPLICIT_DEF#18: unexercised
  X_G_IMPLICIT_DEF#19: unexercised
  X_G_ADD#9: unexercised
  X_G_AND#11: unexercised
  X_G_CTPOP#3: unexercised
  X_G_LOAD#8: shadowed
  X_G_LOAD#9: shadowed
  X_G_STORE#7: shadowed
  X_G_STORE#8: shadowed
  X_G_FCMP#7: shadowed
```

配 `../gisel-anchor/scripts/import-cxx.py --all --pin ../gisel-anchor/pin/PIN.json --git-repo <llvm> --check` 一起用，就是这条链的
两段证书：**语料 == C++**，且**每条规则都被问过**（剩下的会被点名）。

## 6 没做到的

- AArch64 的 159 条无见证已逐条定性（§9）：95 条谓词在声明域内永假，29 条动作
  守卫永假，17 条被更早的规则盖住，18 条只在查询集没采样的 mem×类型组合里可满足。
  第 18 条不是“上游就是死的”，是 `cases` 的 mem 交叉采样缺口，已明写。
- 见证只保证“问到了这条规则”，不保证“问全了这条规则的每个类型字面量”。
  后者需要在同一份语料上做“每条规则 × 每个字面量”的展开，作为 `cases` 的
  第二个出口。
- 语料与 C++ 的逐字节一致只覆盖 `TARGETS` 里钉住的九个构造函数；新 target
  是新工具/新条目，不是新 flag（importer 的文档头已经这么写）。

## 7 一个反例：`sizeIs` 与 `elementTypeIs`

X86 的查询里出现过一次 `G_UITOFP (s32, v4s32)` 的判读分歧。手写上游的规则是：

```cpp
.customIf([=](const Query &Q) {
  return !HasAVX512 && (HasSSE1 && typeIs(0, s32)(Q)) &&
         scalarNarrowerThan(1, Is64Bit ? 64 : 32)(Q);
})
```

`scalarNarrowerThan` 的实现是 `QueryTy.isScalar() && QueryTy.getSizeInBits() < Size`。
`v4s32` 不是标量，这条规则**不命中**，继续往下走全是标量守卫的 `clampScalar` /
`widenScalarToNextPow2`，也都不命中 → `Unsupported`。

任何把「元素位宽 32 < 64」当成命中的转写都会答 `Custom`。这正是 `sizeIs`（总位宽）
与 `elementTypeIs`（元素位宽）不能互换的现成反例，也就是 `spec/graph.md` 不变量
第 5 条。X86 的官方一侧就是 pin 的手写构造函数，当前查询集里两侧一致（§8.4）。

## 8 第二、第三个 target 的端到端（2026-11-09）

同一条链：`cpp -> import-cxx -> .gisel -> cases -> 查询 -> 两侧 runner`。
`official` 一侧是构建树里的**手写 C++** 构造函数；`ours` 一侧把
`gisel gen --emit=inc` 的片段编进同一个类，其余代码仍来自官方共享库。
两边读同一份查询 JSONL，比 `(action, type_idx, new_type)`。

| target | 查询行 | 去重 key | 两侧都答 | 一致 | 分歧 | 两侧都断言 |
|---|---:|---:|---:|---:|---:|---:|
| AArch64 | 12,952 | 12,952 | 12,952 | 12,952 | **0** | 0 |
| RISC-V | 6,301 | 6,299 | 6,299 | 6,299 | **0** | 0 |
| X86 | 3,217 | 3,211 | 3,211 | 3,211 | **0** | 0 |

`一致` 把“两侧都断言”也算作一致（两家都没答出来）；`两侧都答` 才是真正被问出
答案的去重 key 数。官方侧是 `pin + PIN.json:patches` 构建的树。

复现命令：

```sh
../gisel-ab/run-aarch64-end-to-end.sh TREE BUILD a64.inc OUT STATE
../gisel-ab/run-riscv-end-to-end.sh   TREE BUILD rv.inc  OUT STATE
../gisel-ab/run-x86-end-to-end.sh     TREE BUILD x86.inc OUT STATE
```

### 8.1 这一轮修掉的四个问题

跑 AArch64 第一次就炸了，四个都不是"两边规则不一样"：

1. **runner 不解析 `p0:*`**（AArch64）。`p0:*` 是"宽度由 config 决定"，RISC-V runner
   早就按 subtarget 解析，AArch64 runner 直接 `return 2`。13,199 条里第一批
   `outside` 查询就撞上。修法与 RISC-V 相同：按 config 的指针宽度解析。
2. **runner 不传 `imms`**（三个 runner 都有）。`G_SEXT_INREG` 这类规则会读
   `Query.Immediates`，而 runner 构造 `LegalityQuery` 时没给，规则索引空数组
   → `ArrayRef` 越界断言。RISC-V 的 20 条 unanswerable 全是它，修完是 0。
3. **`num_elems(slot)` 对非向量吐 1**（`gisel/backend/llvm_inc.py`）。
   `eval.num_elems` 和 release 构建的 `LLT` 都是 0（标量/指针带的
   `ElementCount` 就是 0），emit 却写 `: 1`。两处 gisel 自己不一致。
4. **`f80` 被当成可构造的类型**（`gisel/cases.py`）。`x86_fp80` 在 LLT 里是
   `scalar(80)`，`LLT::floatIEEE(80)` 是 `llvm_unreachable`；查询还没问就崩。
   `_FLOAT_BITS` 去掉 80。

### 8.2 从 117 条两侧都断言到 0：上游一层、我们两层

原本 117 条在两侧都撞 `mutationIsSane`
（`llvm/lib/CodeGen/GlobalISel/LegalizerInfo.cpp`）。拆开之后是两件事：

1. **上游框架层**（PR #238306）。`maxScalarEltSameAsIf` 把 lane 数当成标量
   类型索引，官方侧因此产出不合法的 `NarrowScalar`。合上这个 PR 后，官方侧能
   答了——也把我们的问题暴露出来。
2. **我们的 importer**。`maxScalarEltSameAsIf` 被转录成
   `narrow(slot(k), replace(same_as(j)))`，生成器照字面翻成
   `make_pair(k, Query.Types[j])`，于是 slot 1（标量 shift 量）被换成 slot 0
   的**整个向量类型**，`mutationIsSane` 当场断言。`minScalarEltSameAsIf` 那条
   分支本来就写对了（`widen(slot(k), same_as(j))` → `coreMinScalarSameAs`）。
   修法是让 max 分支对称地落到 `coreMaxScalarSameAs`：它比较的是
   `getScalarSizeInBits()`，对向量就是元素位宽，正是这条 API 的原意。
   修完这 9 条 `G_SHL` 两侧一致。

剩下 108 条**不是上游的锅，是我们自己造的非法查询**：

```text
G_CONCAT_VECTORS 90   G_FPTOSI_SAT 9   G_SHUFFLE_VECTOR 9
```

逐条查下去，它们都是同一种东西：

```text
G_CONCAT_VECTORS (v16s8, v2s32)   concat 两个 v2s32 得到 v4s32，不是 v16s8
G_SHUFFLE_VECTOR (v16s8, s32)     源是标量
G_FPTOSI_SAT     (v2i64, f16)     标量和 2-lane 向量配对
```

`gisel/cases.py` 的候选是逐槽构造再取笛卡尔积，槽之间没有形状约束，于是造出
了真实 MIR 里不可能出现的类型组合。换成合法形状，同一个 opcode、同一个 config
立刻能答（`(v16s8, v8s8)` → Legal，`(v2i64, v2f16)` → WidenScalar）。所以
官方侧断言不是缺陷，**它正确地拒绝了非法输入**；这也不该提上游 issue。

修法是在候选乘积之后加 opcode 形状约束（来源是 `MachineVerifier.cpp` 的检查
加上 opcode 语义），并且**计数打印**被丢掉了多少：

```text
ill-formed=15582 (G_CONCAT_VECTORS 3435, G_FPTOSI_SAT 7951,
                  G_MERGE_VALUES 288, G_SHUFFLE_VECTOR 3628,
                  G_UNMERGE_VALUES 280)
```

修完 AArch64 的 108 条断言归零，规则见证数仍是 572（过滤不吃覆盖）。算法细节
见 `docs/ALGORITHM-cases.md` 的「形状：槽不是独立轴」。

### 8.3 AArch64 上游缺陷：`getNumElements()` 的调用面

修 runner 之前，官方一侧有 **133 条**直接 abort，全部是
`AArch64LegalizerInfo.cpp` 的谓词在标量或 scalable 向量上调
`LLT::getNumElements()` / `getSizeInBits()`。已落到
`/home/ubuntu/admin/upstream-issues/2026-11-09-13-gisel-aarch64-element-count-assert.md`。

本机在 `trees/explore` 上按建议补丁修了（`numElements()` helper +
`getKnownMinValue()`），AArch64 才从 133 条 abort 变成 0。**这是本地补丁**，
提交上游前必须先搜重；语料 pin 的 sha 已随之指向打过补丁的源文件，规则内容未变
（重新导入逐字节相同）。

### 8.4 X86：对手是 pin 的手写构造函数

X86 的构建树文件是 pin `9bfc850b9940` 的手写 `X86LegalizerInfo.cpp`
（sha256 `79f2376…`）。
`gisel-ab/run-x86-end-to-end.sh` 的做法：

1. restore → `ninja libLLVMX86CodeGen` → 这是**现网**，跑一遍查询；
2. `swap-source-ctor.py apply --target x86`：只把构造体换成
   `#include "X86LegalizerInfo.inc"`（gisel 产物），其余翻译单元不变；
3. `ninja` 后跑第二遍，`diff.py`。

结果（合并 `PIN.json` 里记录的 5 个 PR 之后重跑）：

| 查询行 | 去重 key | 一致 | 分歧 | 两侧都断言 |
|---:|---:|---:|---:|---:|
| 3,217 | 3,211 | 3,211 | 0 | 0 |

19 条 `G_BUILD_VECTOR` 全部归零。原因是这 19 条一开始就不是翻译错误，而是
**单边差异**：语料已经按上游修复（`Unsupported`）写，而官方侧还是修前的
`MoreElements`。把 PR #238277 落到树上、官方侧拿到同一个修复后，两侧一致。

同一轮里 AArch64 从 `13,082 一致 / 0 分歧 / 117 两侧都断言` 变成
`12,952 / 0 / 0`，RISC-V 保持 `6,299 / 0 / 0`。AArch64 那 117 条里先有 9 条
是我们的 importer 翻错了 `maxScalarEltSameAsIf`，剩下 108 条是我们自己造的
非法形状查询，都在本节修掉（见 §8.2）。

也就是说：**X86 现在 3,211/3,211 一致**，19 条已知死循环的偏离在两侧都消失，
没有未归因的差异。X86 查询行数从 3,282 变成 3,019，是形状过滤（含比较结果槽）
丢掉的非法元组，不是题目被跳过。`PIN.json` 的 `patches` 记录了我们叠在上游 pin 之上的 PR；
等它们合入上游，把 `commit` 前移并删掉 `patches` 和 `X86_DEVIATIONS` 即可。

## 9 AArch64 的 168 条无见证：逐条定性（2026-11-10）

命令：

```sh
python3 -m gisel cases tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json \
  --axes tests/cases/aarch64-mem-orderings.axes.json \
  --out /tmp/a64.jsonl --strict-coverage --json
# 743 rules, 575 witnessed, 168 unwitnessed (130 unexercised, 38 shadowed)
```

机器可读的逐条清单在 `docs/coverage/AArch64-unwitnessed.json`（每条带源码行、
分类、被谁盖住或为什么不可能）。汇总：

| 分类 | 条数 | 判定 |
|---|---:|---|
| `dead-predicate` | 101 | 谓词在声明域里对任何类型都为假 |
| `dead-guard` | 29 | 谓词能成立，但动作的隐式 shim 守卫永远为假 |
| `dominated` | 20 | 谓词能成立，但每个采样点都被更早的规则先答掉 |
| `satisfiable-outside-query-product` | 18 | 在更宽的轴里可满足，但当前查询集没采到那个 mem×类型组合 |

### 9.1 这一轮多找到的 12 条：目标类型也是种子

旧实现只用 `in(...)` 里的类型字面量做定向搜索的种子。`clamp_max(0, s32, 4)`
这类规则的类型只出现在 `to` 里（`vecOf(numElems(ty(v4s32)), elemOf(slot(0)))`），
`literals` 为空，搜索于是退到单个默认点 `s32`，永远触发不了。

修法（`gisel/analysis.py:inspect_rule`）是另记一个 `targets` 字段：把 `on`/`to`
里的 `ty(...)` 也作为该槽的种子，**但不并入 `literals`**——`literals` 决定主候选
轴，并进去会改变基础查询集。定向搜索用 `literals | targets`，于是
`clamp_max(s32, 4)` 的种子 `v4s32` 带来邻居 `v8s32`，这条规则第一次有了见证。

效果：AArch64 572 → 584 条见证。随后比较结果槽过滤（`G_ICMP`/`G_FCMP` 的
type0 必须是整数）撤掉了 9 条只靠非法比较形状成立的见证，落到 575；这 9 条
按原因归入 6 条 `dead-predicate` 和 3 条 `dominated`。三个 target 的查询集都
随这个过滤变化，当前数字以本节表格为准。

### 9.2 101 条 `dead-predicate`：LLT 造不出触发值

最大的一类是 `clamp_min(0, s32, 2)`（G_ADD/G_MUL/… 共几十条）：

```text
predicate: sortOf(slot0)==vector && elemOf(slot0)==s32 && numElems(slot0) < 2
```

`numElems < 2` 要求固定单 lane 向量，而 LLT 把 `v1s32` 折叠成 `s32`；标量又
不满足 `sortOf==vector`。这个谓词在 LLT 的值空间里**没有模型**。上游保留它
是防御性的，但它不是我们的见证缺口。

这一类还包括 `G_ICMP`/`G_EXTRACT_VECTOR_ELT` 里“元素类型 + lane 数”相互矛盾的
组合，以及 `G_VECREDUCE_*` 的标量/向量交叉。

### 9.3 29 条 `dead-guard`：动作的隐式守卫永假

典型是 `scalarize(slot(0)) when bits_of(slot(0)) > 64`：
`shim_guard_and_newtype` 对 `scalarize` 要求 `is_vector(t)`，而满足
`bits_of > 64` 的标量早就被前面的 `widen/narrow` 处理掉；向量又先被
`clamp_max` 收窄。谓词能成立，守卫永远不成立。

`G_FPTOSI`/`G_SITOFP` 的 4 条也在这里：源类型和目标类型被前面的 legal 规则
先吃掉，剩下的合法输入不满足动作守卫。

### 9.4 17 条 `dominated`：被更早的规则盖住

每条都附了“谁先答”的计数。例如：

```text
A_G_IMPLICIT_DEF#6  widen(elem_of(slot(0)), min_vector_size(64))
  <2 x s16>  -> 规则 #1 legal 先答（27 次）
  <4 x s16>  -> 规则 #5 more(pow2) 先答（36 次）
```

这些规则在 LLVM 的 first-match 语义下不可达；它们是上游规则表的冗余项，不是
gisel 翻错。

### 9.5 18 条 `satisfiable-outside-query-product`：查询集的采样缺口

全部是 mem opcode（`G_LOAD` 5、`G_STORE` 4、`G_SEXTLOAD` 3、`G_ZEXTLOAD` 3、
`G_INDEXED_LOAD` 2、`G_INDEXED_SEXTLOAD` 1）。`_queries` 对 mem 规则只做两件事：

1. 用 `inMemDesc` 行自己的 `(t0, t1)` 配一个描述符；
2. 再拿**前 4 个**类型元组和描述符交叉。

`widen(slot(0), pow2_min(8))` 需要 `s31`（非 pow2），而 `s31` 不在前 4 个元组里，
于是查询集里没有 `(s31, p0) + 描述符` 这一点。`_satisfiable` 用完整候选轴能证明
它可满足，但 `cases` 没出这道题。

这是**已知缺口**，不是不可达证明。修法是把 mem 交叉从“前 4 个元组”换成
“每个 mem 行 × 每条突变规则的目标类型邻域”，代价是 AArch64 查询数会从 12.6k
涨到约 20k；本轮不做，先把它钉在清单里。

### 9.6 复现与门禁

```sh
# 逐条清单（本轮快照）
python3 -m gisel cases ... --strict-coverage --json > stats.json
python3 tools/coverage-report.py tests/corpus/AArch64LegalizerInfo.gisel \
  stats.json docs/coverage/AArch64-unwitnessed.json
```

`--strict-coverage` 仍然是 rc=1：159 条没有见证。门禁的语义没变——“所有规则都被
问过”还不成立；变的是每一条都有了原因，而不是一个笼统的 171。
