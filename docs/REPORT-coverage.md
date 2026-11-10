# 分母的归属：一条规则都不能没有见证

状态：完成（2026-11-09）。基线 `c5ac359`。

## 1 链路

```
LLVM C++  --import-cxx-->  .gisel  --gisel cases-->  无答案查询  --对拍--> 两个 runner
```

“我们没漏上游的规则”只能由这条链的前两段保证：

- **C++ → .gisel**：`tools/import-cxx.py` 只接受它认识的构造，别的一律带行号
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
| X86 | 328 | 292 (89.0%) | **319 (97.3%)** | 4 | 5 | 3,217 |
| AArch64 | 743 | 312 (42.0%) | **572 (77.0%)** | 35 | 136 | 12,952 |
| RISC-V | 413 | 320 (77.5%) | **355 (85.9%)** | 12 | 46 | 6,301 |

另外加了一次**定向搜索**：全局候选集没找到见证时，单独用该规则自己命名的类型
及其邻居枚举一遍。它只多找到 1 条（AArch64）——说明剩下的不是“搜得不够”，而是
真的被更早的规则盖住了。

## 4 剩下的 9 / 171 / 58 条是什么

X86 的 5 条 unexercised 有 4 条是 `clamp_min(0, X_s64, 2)` 这类：

```text
clamp_min(0, X_s64, 2)      # 触发条件是“s64 向量且 lane < 2”
```

固定单 lane 向量就是标量，而标量已经被前面的 `legal in(slot(0), [X_s32])`
之类答掉了。这类规则**在上游就是死的**：LLT 造不出这样的值。它们不是我们的
缺口，但也不该被算成“已验证”——现在被单列成 unexercised 并计入退出码。

AArch64 剩下的 171 条集中在 `G_STORE` / `G_LOAD`（多槽 + mem 描述）、
`G_ICMP`、`G_EXTRACT/INSERT_VECTOR_ELT`。共同点是 3 个槽位的组合空间被产品上限
约束，或者需要一个特定 feature 与特定类型的**组合**。这是下一步，不是本轮的
结论。

## 5 门禁

```sh
gisel cases tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --out /tmp/q.jsonl --strict-coverage
```

有任何规则既没有见证、又不是被证明可满足却遮蔽时，退出码 1，并打印前 20 条：

```text
cases: 9 rule(s) have no witness (5 unexercised, 4 shadowed); the query set
does not cover every rule
  X_G_IMPLICIT_DEF#16: unexercised
  ...
```

配 `tools/import-cxx.py --all --llvm-src <llvm> --check` 一起用，就是这条链的
两段证书：**语料 == C++**，且**每条规则都被问过**（剩下的会被点名）。

## 6 没做到的

- AArch64 的 135 条 unexercised 还没有逐条定性。要判“上游就是死的”需要把 LLT
  的构造规则（单 lane 折叠、scalable 与固定向量的关系）编进判定，而不是靠搜索。
- 见证只保证“问到了这条规则”，不保证“问全了这条规则的每个类型字面量”。
  被删掉的 `-gen-legalizer-table-points` 给的是后者。要补回来，得在同一份语料上
  做“每条规则 × 每个字面量”的展开，作为 `cases` 的第二个出口。
- 语料与 C++ 的逐字节一致只覆盖三个钉住的构造函数；第四个 target 是新工具，
  不是新 flag（`tools/import-cxx.py` 的文档头已经这么写）。

## 7 第一次跑出来的东西：一条真分歧

新的见证集第一次跑端到端（X86，3,276 个去重 key）时，`disagree = 1`：

```text
C1  G_UITOFP  (s32, v4s32)   official = Custom   ours(gisel) = Unsupported
```

这里的 `official` 是本分支 `.td` 渲染出来的构造函数，不是上游手写 C++；见 §8.4。

两边的规则都在这儿：

```cpp
// 手写上游 X86LegalizerInfo.cpp
.customIf([=](const Query &Q) {
  return !HasAVX512 && (HasSSE1 && typeIs(0, s32)(Q)) &&
         scalarNarrowerThan(1, Is64Bit ? 64 : 32)(Q);
})
```

`scalarNarrowerThan` 的实现是 `QueryTy.isScalar() && QueryTy.getSizeInBits() < Size`。
`v4s32` 不是标量，所以这条规则**不命中**，继续往下走全是标量守卫的
`clampScalar` / `widenScalarToNextPow2`，也都不命中 → `Unsupported`。

而 `.td` 把它转写成了：

```tablegen
CoreCustom<(CoreAll (CoreNot HasAVX512), ..., (CoreLt (BitsOf (Slot 1)), ...))>
```

丢了 `isScalar` 守卫，而且 `BitsOf` 在向量上读的是元素位宽（32），于是
`32 < 64` 成立 → `Custom`。

也就是说：**gisel 是对的，`.td` 那条转写是错的**。这条分歧正好是「有界商」理论
里那条不变量（`sizeIs` 读总位宽、`elementTypeIs` 读元素位宽）的一个现成反例。

旧的分母（来自 `-gen-legalizer-table-points`）没抓到它：那套点的类型元组里，
这个组合没有作为任何规则的见证出现。新的见证集让它变成了 `disagree = 1`。

结论：`.td` 路径不仅多余，而且已经和手写代码不一致。这也解释了为什么它该被删。

2026-11-09 更新：`.td` 渲染链已经整个删除（emitter、`LegalizerInfo.td`、
`X86/AArch64` 的 `.td`、64 个 TableGen 测试），X86 的官方一侧换回 pin 的
手写 `X86LegalizerInfo.cpp` 后，这条 `G_UITOFP` 差异**消失**——新的一组
3,282 条查询里没有它。第 7 节在这里保留的是"为什么这条链该删"，不是当前结果。

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
../ab/run-aarch64-end-to-end.sh TREE BUILD a64.inc OUT STATE
../ab/run-riscv-end-to-end.sh   TREE BUILD rv.inc  OUT STATE
../ab/run-x86-end-to-end.sh     TREE BUILD x86.inc OUT STATE
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

### 8.4 X86：把对手换成 pin 的手写构造函数

`.td` 渲染链已经删干净（`-gen-legalizer`、`LegalizerInfo.td`、两个 target 的
`.td`、64 个 TableGen 测试、`X86LegalizerTable`）。X86 的构建树文件恢复成
pin `9bfc850b9940` 的手写 `X86LegalizerInfo.cpp`（sha256 `79f2376…`）。
`ab/run-x86-end-to-end.sh` 的做法：

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
没有未归因的差异。查询行数从 3,282 变成 3,217，是形状过滤丢掉的 65 条非法
元组，不是题目被跳过。`PIN.json` 的 `patches` 记录了我们叠在上游 pin 之上的 PR；
等它们合入上游，把 `commit` 前移并删掉 `patches` 和 `X86_DEVIATIONS` 即可。
