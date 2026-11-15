# 把 LLVM 的合法化规则变成一门小语言

LLVM GlobalISel 的合法化规则，写在 `*LegalizerInfo.cpp` 的构造函数里，是一长串
`getActionDefinitionsBuilder(G_ADD).legalFor(...)...` 的 builder 调用。它是"代码里
的数据"：能编译，但你要问它"到底覆盖了哪些类型"、"改这一条会影响谁"，只能靠读
和跑。

我做的事，是把它抽出来换成一种规则文本，再由工具链生成代码和测试题。

> **理念：合法化规则不是黑盒，是一张拼图。** 每块拼图都能事先写清楚——opcode、
> 槽位、mem、配置各是一块；也都能被证伪——题面问到它，答错就红。拼好之后只有
> 一份事实源：规则文本，`.inc` 是它的产物；错了改规则，不在生成物上打补丁。
> 等价类让这张拼图**可测试**：类型空间被切成有限块，每块有名字、有代表点、有
> 边界，所以"测够了没有"能回答，而不是靠感觉。

## 一、它现在能干什么

**规则写成文本。** 一条规则一行，可以 lint、可以 diff、可以 review（省略 feature/type 定义）：

```text
ruleset X_ADD: G_ADD
    legal in(slot(0), I32)
    legal (Is64Bit and in(slot(0), I64))
    widen(slot(0), pow2_min(32))
    scalarize(slot(0))
```

**生成可替换的 C++。** `gisel gen --emit=inc` 一条规则对一次 builder 调用，直接
include 进上游构造函数就能编译；`LegalizerHelper`、custom 动作、memdesc、
verifier 一行不动：

```cpp
getActionDefinitionsBuilder(G_ADD)
    .legalFor({I32})
    .legalFor(Is64Bit, {I64})
    .widenScalarToNextPow2(0, 32)
    .scalarize(0);
```

**自动出题。** `gisel cases` 生成不带答案的查询；`gisel domain` 生成规则无关的
值域全量。下面是三条真实查询（只留关键字段）——等价类代表、边界、outside：

```json
{"name":"G_ADD","types":["s16"],   "kind":"equivalence","reason":"first match for rule 0"}
{"name":"G_ADD","types":["s9"],    "kind":"boundary",   "reason":"bits 8 -> 9"}
{"name":"G_ADD","types":["v4s32"], "kind":"outside",    "reason":"no rule fires"}
```

**对拍。** 同一份题面，官方规则表和生成的 inc 各答一遍，逐行比
`(action, type_idx, new_type)`。上面三条的答案：

```text
types     official                        ours                            verdict
s16       Legal                           Legal                           agree
s9        WidenScalar -> s16              WidenScalar -> s16              agree
v4s32     Unsupported                     Unsupported                     agree
```

答案不在题面里，是两侧现场算的——出题人自己填答案，就成了自证。

**看图。** `gisel graph` 在"类型 × 等价类"的有限空间上找环，把"死循环"变成一条
命令能复现的结论。

## 二、收益：为什么说它值

**规则可维护、可审。** 三百行 builder 链变成几十行规则文本，一条规则一个动作、
一个位置、一个条件。lint 查遮蔽和冲突；review 时讨论的是"这条规则该不该在"，
不是"这个 lambda 捕获对不对"。

**测试题自动生成，等价类真的被覆盖。** 不是随机采样：按规则把类型空间切成等价类，
每类至少一个代表点；相邻答案的翻转处给边界点（上面 `s8 -> s9` 就是）；没有规则
命中的地方单列 outside（`v4s32`）。于是"测试写够了吗"第一次有了可数答案——
等价类数 × 配置数。

**每次修改都能回归。** 改一条规则、升级一次 pin，动作层秒级回答"哪些点变了、
变成什么"；需要时再上 MIR 回放和 lit。

**反向测试是内建的。** outside 专门问"这里什么都没有吗"；两侧断言崩溃的点单独
计数、按配置钉死；每个 target 还有"注入一个错 opcode"的负控——负控不红，就说明
检测本身失效了。

## 三、它真的抓到过什么

一个具体例子。上游 X86 处理窄向量的乘加时，会把 `<2 x s32>` "加元素"到
`<4 x s32>`，同时用 `G_UNMERGE_VALUES` + `G_BUILD_VECTOR` 重建出一个**同类型的
窄向量**；下一轮这个 build vector 又拿到一次 "加元素"，worklist 永远不空：

```text
Legalizing: %4:_(<2 x s32>) = G_MUL %2:_, %3:_
.. Increase number of elements
.. .. Changed MI: %12:_(<4 x s32>) = G_MUL %8:_, %11:_
.. .. New MI: %13..%16:_(s32) = G_UNMERGE_VALUES %12:_(<4 x s32>)
.. .. New MI: %4:_(<2 x s32>) = G_BUILD_VECTOR %13:_(s32), %14:_(s32)
```

于是 `llc` 不返回，`timeout 20` 直接 124。**这个环在单点 `getAction()` 里完全
看不出来**——每一步都合法，是"规则之间的来回"。图工具和 MIR 回放才把它变成一个
可复现的查询；上游 issue #236649，修复 PR #238277 已开。

同一类方式还找到：规则表自相矛盾（`scalarSameSizeAs` 在两槽不同形时产生畸形
mutation，issue #237670，修复已合入）、合法 IR 触发断言（指针 bitcount，
#236651）、以及"无 POPCNT 时向量 `ctpop` 没有规则、release 下死循环"（#220802）。
共 4 个 issue，2 个修复已合入。

完整清单（12 个 PR、10 个 issue，含 LoongArch 与 TableGen）在
[UPSTREAM-BLOG-zh.md](UPSTREAM-BLOG-zh.md)。

## 四、原理：三句话

1. **为什么能穷举。** LLT 空间无限，但规则里的谓词只读有限的几个量
   （`sizeIs(N)`、`elementTypeIs`、`clampMinNumElements`、`pow2`）。把让真值翻转
   的阈值抽出来，加上 `N±1` 和类型自身边界，每根轴上就只剩有限个候选点；候选集
   对"翻转"封闭，集合外不必再测。
2. **为什么答案要现场算。** 见上：题面不带答案，两侧各自作答。
3. **为什么比一步就够。** 合法化是循环，但一步答案相同 + 后继函数相同 + 状态集
   对后继封闭，整个循环就相同。闭包是跑出来的，不是假设的。

## 五、效果

- 9 个后端、509 个 ruleset、2,165 条规则，全部能从钉住的 commit 逐字节重建。
- 动作层：9 个后端零差异；值域全量 X86 9 万条、AArch64 843 万条。
- MIR 回放：21,128 条，diff 0。全量 lit：x86 / aarch64 / riscv，80,655 个测试
  逐条比对。

## 六、框架长什么样（放最后）

三个仓库，单向数据流：

```text
上游 C++（钉 commit） --gisel-anchor--> .gisel 语料
   --gisel--> inc 规则链 + 无答案题面
   --gisel-ab--> 两个真实构建分别作答 --> diff + 归因
```

- `gisel-anchor`：只做"把上游事实变成语料"，语料随包分发；
- `gisel`：DSL 编译器 + 出题器，不读 LLVM、不编译；
- `gisel-ab`：对拍工作台，负责换源、构建、比较、冻结证据。

## 七、它不吹的部分

动作层等价不等于合法化器整体等价：`Custom` 的动作体是手写 C++，体内的类型改写
不可见。也正因如此，我们换的只是规则表，策略层两侧是同一份代码。上游题面是
"声明的类型宇宙 + 抽样点"，不是全部合法 IR；`0 diff` 只说明两侧在这份题面上一致，
不说明规则本身正确。
