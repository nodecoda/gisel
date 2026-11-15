# 三周，12 个 PR，10 个 issue：我在 LLVM 上游修的那些"边界组合"

> 复核时间 2026-11-15（GitHub API）。数字口径：PR 12 个 = 6 已合入 / 5 评审中 / 1 自查重复后自关；
> issue 10 个 = 2 已修 / 1 判重关闭 / 7 待处理。改动 2112 行，含测试。

## 起因：一个永远不返回的 `llc`

事情从这段 IR 开始，平平无奇的 `<2 x i32>` 乘法：

```llvm
define void @f(ptr %p, ptr %q) {
  %a = load <2 x i32>, ptr %p
  %b = load <2 x i32>, ptr %q
  %r = mul <2 x i32> %a, %b
  store <2 x i32> %r, ptr %p
  ret void
}
```

`llc -global-isel -O0` 跑它，不崩溃、不报错，**也不返回**。`-global-isel-abort=1/2` 都切不出来，
因为 abort 机制只在"合法化失败"时触发，而这里是合法化器在两条规则之间反复自我调度——一个 livelock。

这个 bug 后来是 issue [#236649](https://github.com/llvm/llvm-project/issues/236649)、PR
[#238277](https://github.com/llvm/llvm-project/pull/238277)。但它真正有意思的地方是：
顺着它往下挖，能找到一整族同一形状的错误。

## 背景：GlobalISel 的规则表是"代码里的数据"

GlobalISel 每个后端都有一段这样的代码（`lib/Target/X86/GISel/X86LegalizerInfo.cpp`）：

```cpp
getActionDefinitionsBuilder(G_AND)
    .legalFor({S64})
    .clampScalar(0, S64, S64)
    .bitcastIf(typeIsNot(0, V4S32), changeTo(0, V4S32));
```

它看起来像声明，实际是一串可执行的 builder 调用。每条规则 = **谓词**（这条类型什么条件下匹配）
+ **mutation**（匹配上之后把类型改成什么）。两者写在同一个链式调用里，编译器不会检查它们是否自洽。

于是就有了一整类 bug：**谓词说的事，和 mutation 干的事不一致**。断言构建（`mutationIsSane()`）
会当场炸掉；release 构建把断言编译掉，把一个非法步骤交给合法化器继续跑——要么 generate 出静默错码，
要么越界读。

## 一、规则谓词里的三种"差一点"

### 1. 拿元素宽度去比总宽度

`minScalarSameAs` / `maxScalarSameAs` 的语义是"换元素宽度、保留元素个数"，对应的 mutation 是
`changeElementSizeTo()`。但它们的谓词拿**元素宽度**去比对方的**总宽度**。对 `<4 x s32>` 就是 32 比 128：

- `maxScalarSameAs()` 认为 `<4 x s32>` 和自己匹配 → 产生一个 no-op mutation → 断言炸；
- `minScalarSameAs()` 要求对方元素宽度大于整个向量 → 对向量永远不成立 → 一条死规则。

修法是把两边都改成按元素宽度比（PR [#237753](https://github.com/llvm/llvm-project/pull/237753)，已合入）。

### 2. 窄化的时候把 lane 数也带走了

同一族里还有一处：`maxScalarEltSameAsIf` 判断要不要窄化是对的（比元素宽度），
但返回的 mutation 是**另一个 slot 的整个类型**——lane 数一起搬过去了，甚至能把标量变成向量。

这就是 issue [#237670](https://github.com/llvm/llvm-project/issues/237670)：断言版被 `mutationIsSane()` 拒绝，
release 版把非法步骤喂给合法化器。修法是只窄化"正在合法化的那个类型"的元素宽度
（PR [#238306](https://github.com/llvm/llvm-project/pull/238306)，已合入）。

顺便说一句，这两个 bug 都不是被"读代码"读出来的，而是被一个更上游的 abort 顶出来的——见第二节。

### 3. 加宽"合法化"，然后自己转圈

回到开头那个 livelock。X86 对 `<2 x i32>` 的 `G_BUILD_VECTOR` 用了"加宽到原生宽度"这条规则，
但加宽的实现是：造一个更宽的 build vector，再把尾部元素删掉（`buildDeleteTrailingVectorElements`），
而删尾部的实现会生成 `G_UNMERGE_VALUES` + **重新造一个窄的 `G_BUILD_VECTOR`**——类型正是刚才要合法化的那个。
合法化器把它捡起来，再来一遍。

artifact combiner 其实会把 unmerge 折回去，但它折的只是副本，那个窄指令是 mutation 自己造出来的，
每一轮都会新建一条。所以关掉 combiner 也没用。

修法：这条规则只保留"元素数上限"的 clamp，窄 build vector 直接报 unsupported，
`-global-isel-abort=2` 就能干净地回退 SelectionDAG（PR [#238277](https://github.com/llvm/llvm-project/pull/238277)，评审中）。

## 二、一次 abort 拆成五个 PR

上面三个 bug 的入口，是一个 X86 向量 `G_CTPOP` 的合法化 abort（issue
[#220802](https://github.com/llvm/llvm-project/issues/220802)，PR
[#235976](https://github.com/llvm/llvm-project/pull/235976)）。

我没打算一次修完，但 review 的过程把它拆开了：RKSimon 要求"先把 128 位那条路单独做成 yak shave"。
于是这条链变成：

| 顺序 | PR | 内容 | 状态 |
| --- | --- | --- | --- |
| 1 | #237753 | `min/maxScalarSameAs` 按元素宽度比较 | 已合入（RKSimon） |
| 2 | #237650 | GlobalISel emitter 选一个"装得下被抽取值"的亚寄存器类 | 评审中 |
| 3 | #238306 | `maxScalarEltSameAsIf` 保留 lane 数 | 已合入 |
| 4 | #235976 | X86 向量 `G_CTPOP` 规则 + 12 种宽度 × SDAG/FastISel/GISel 测试 | 已 approve，等前置落地后 rebase |

第 2 条本身也值得说一句：`getMatchingSubClassWithSubRegs()` 在覆盖同一批寄存器的几个类里按**声明顺序**
打破平局，于是 X86 上从一个 `v4i32` 抽 `sub_xmm` 会选到 `FR16X` 而不是 `VR128X`——
寄存器覆盖是对的，但这个类装不下取出来的值，ISel 拒收那条 COPY。修法是让 emitter 优先选
"有被抽取值类型"的那个类（PR [#237650](https://github.com/llvm/llvm-project/pull/237650)）。

到最后一个 PR 只剩规则表加一个测试文件。过程中我学到的是：**reviewer 要的不是"你一次修好了"，
而是"每一步都能单独 review、单独回滚"**。

## 三、LoongArch：不是崩溃，是错 1 ulp

GlobalISel 那批是"炸给你看"，LoongArch 这批是"安静地算错"，更难查。

### `fptosi(frint(x))` 可以是一条指令

`floor/ceil/trunc/roundeven` 的结果在浮点域里已经是精确整数，所以后面那次"向零取整转整数"
不会再引入误差。后端的做法是老老实实选两条指令。既然语义等价，就可以直接选一条带舍入模式的
`[x]vftintr{m,p,z,ne}`。

这条改动（PR [#239694](https://github.com/llvm/llvm-project/pull/239694)，827 行）没碰 ISD、没加 DAG combine、
没改合法化器，纯 TableGen 的 multiclass 模式覆盖，48 个新测试函数覆盖四种舍入模式 × 等宽/窄/长/无符号四种形态。
另外在 qemu-loongarch64 上对着标量参考跑了 16 条序列、每条 20 万次，零不一致。

### 向量 `uitofp` 到 f32 舍入了三次

`uitofp <N x i64> to <N x float>` 在 LASX 上对 `0x8080808080808080` 会算出 `0x5f008080`，
正确答案是 `0x5f008081`。原因很朴素：通用的 half-word 展开把高低 32 位分别转成浮点再相加，
中间舍入了三次。LoongArch 没有无符号 64→32 转换指令，所以改成标量合法化器用的 round-to-odd 序列；
能不能走原生有符号指令，取决于符号位能不能被证明是 0（`nneg` 标记或 known bits）。

PR [#239880](https://github.com/llvm/llvm-project/pull/239880)，已合入。qemu 上随机 350 万个 lane
加 80 万个 nneg 快路径 lane 对拍，零差异。

### lld 只放松了一半的 TLS 序列

LoongArch 的 TLS LE 序列是"`lu12i.w`/`add.d` 算地址 + `R_LARCH_TLS_LE_LO12_R` 取低 12 位"，
靠 `R_LARCH_RELAX` 标记告诉链接器可以改写。ELF ABI 允许这个标记**和序列里的任意一条重定位同 offset**，
不要求排在后面。lld 的实现只检查"紧跟在我后面那条重定位"，于是标记在前时：

- 地址计算的两条指令被删掉了（放松了一半）；
- 取低 12 位的消费者没被改写成 `$tp` 相对。

结果是一个从没初始化的寄存器算出来的地址，运行期段错误。PR
[#240284](https://github.com/llvm/llvm-project/pull/240284)（评审中）改成记住"这组指令被我删过"，
无条件放松它的消费者；测试用 `yaml2obj` 同时造规范顺序和"标记在前"两种 object，一次链接两个。

顺手记一个教训：直接让 `relaxable()` 接受"标记在前"是不够的。TLS DESC→LE 转换会在同 offset 追加合成重定位，
标记会被算到错的那条头上。

### 补测试和自查重复，也算贡献

- 上游修的通用 bug（软浮点下 `llvm.minimum/maximum` 的 libcall），只带了 RISC-V 测试，LoongArch 没覆盖；
  补上（PR [#240280](https://github.com/llvm/llvm-project/pull/240280)，已合入），并验证"删掉修复后测试真的失败"。
- PR [#240277](https://github.com/llvm/llvm-project/pull/240277) 修的是 LSX 下 sext 非法向量类型的崩溃，
  提之前没查到 #222250 已经在修同一个根因。发现后我自己关了它，把额外测试形态补到 #222250 上。

## 四、报 issue 也是产出

这一个月也开了 10 个 issue。其中一半是"顺着一个 abort 挖出来的兄弟 bug"，另一半是顺手撞见的：

| # | 状态 | 模块 | 一句话 |
| --- | --- | --- | --- |
| [241631](https://github.com/llvm/llvm-project/issues/241631) | open | AArch64 | `arm64_32` 上 `<2 x ptr>` 的 `G_SHUFFLE_VECTOR`：规则假设指针 64 位，bitcast 到 `<2 x i64>` 尺寸变了 |
| [241630](https://github.com/llvm/llvm-project/issues/241630) | open | PowerPC | `G_AND/OR/XOR` 的 `bitcastIf(typeIsNot(v4s32))` 没查 128 位宽，任何其它向量宽度都触发断言 |
| [241336](https://github.com/llvm/llvm-project/issues/241336) | open | AArch64 | `arm64_32` 上 `<4 x ptr>` 参数在 CallLowering 里做 size-changing bitcast |
| [240795](https://github.com/llvm/llvm-project/issues/240795) | open | lldb | `lldb-aarch64-windows` 上 `test_run_python_os_step` 自 11-09 起约 44% 失败，附 20 次红 build 的统计 |
| [238799](https://github.com/llvm/llvm-project/issues/238799) | 已修 | TableGen | multiclass 里的 `dump` + `defm X : MC, C` 让 `AddParentClass` 空指针解引用；别人用 #238812 修好 |
| [238797](https://github.com/llvm/llvm-project/issues/238797) | open | TableGen | `!head/!tail` 作用在"延迟求值后为空"的列表上：断言版 abort、release 版越界读 |
| [238796](https://github.com/llvm/llvm-project/issues/238796) | 判重 | TableGen | 上一条的重复项，我自己关了 |
| [237670](https://github.com/llvm/llvm-project/issues/237670) | 已修 | GlobalISel | `maxScalarEltSameAsIf` 返回对方整个类型，lane 数不等时断言 |
| [236651](https://github.com/llvm/llvm-project/issues/236651) | open | GlobalISel | `scalarSameSizeAs` 会去改指针寄存器的元素尺寸，而且 verifier 放过了这种操作数形状 |
| [236649](https://github.com/llvm/llvm-project/issues/236649) | open | X86 | `<2 x i32>` `G_BUILD_VECTOR` 让合法化器 livelock，且 `-global-isel-abort` 切不出来 |

写 issue 的模板基本固定：最小复现（能贴进 `llc` 的 IR / MIR / `.td`）、失败断言的原文、
**根因定位到文件和函数**、一个建议修法、以及"这个 IR 是合法的"的论证。
[#238799](https://github.com/llvm/llvm-project/issues/238799) 从开到被别人的 #238812 修好用了 6 天，
我没有参与修复——但它省了后面每个人一次 `llvm-tblgen` core dump。

## 附录：12 个 PR

| PR | 状态 | 模块 | 一句话 |
| --- | --- | --- | --- |
| [235828](https://github.com/llvm/llvm-project/pull/235828) | 合入 | GlobalISel/IRTranslator | `<1 x Ty>` 的 insertelement 被翻译成自拷贝，源数据丢失 |
| [237753](https://github.com/llvm/llvm-project/pull/237753) | 合入 | GlobalISel/LegalizerInfo | 元素宽度比总宽度：一个 no-op mutation、一条死规则 |
| [238306](https://github.com/llvm/llvm-project/pull/238306) | 合入 | GlobalISel/LegalizerInfo | 窄化时把 lane 数一起改了 |
| [239694](https://github.com/llvm/llvm-project/pull/239694) | 合入 | LoongArch LSX/LASX | `fptosi(frint(x))` 融成一条带舍入模式的转换 |
| [239880](https://github.com/llvm/llvm-project/pull/239880) | 合入 | LoongArch LASX | 向量 `uitofp` 到 f32 三重舍入，错 1 ulp |
| [240280](https://github.com/llvm/llvm-project/pull/240280) | 合入 | LoongArch | 补 `minimum/maximum` lowering 的测试 |
| [235976](https://github.com/llvm/llvm-project/pull/235976) | 评审中 | X86/GlobalISel | 向量 `G_CTPOP` 合法化 abort，补 AVX512 规则 |
| [237650](https://github.com/llvm/llvm-project/pull/237650) | 评审中 | GlobalISel/emitter | 亚寄存器结果类选错，ISel 拒收 COPY |
| [238277](https://github.com/llvm/llvm-project/pull/238277) | 评审中 | X86/GlobalISel | `G_BUILD_VECTOR` 用加宽来合法化导致 livelock |
| [239136](https://github.com/llvm/llvm-project/pull/239136) | 评审中 | TableGen | 延迟空列表上的 `!head/!tail` 改成 fatal error |
| [240284](https://github.com/llvm/llvm-project/pull/240284) | 评审中 | lld/LoongArch | TLS LE 序列只放松了一半，运行期段错误 |
| [240277](https://github.com/llvm/llvm-project/pull/240277) | 自关 | LoongArch | sext 非法向量类型崩溃；与 #222250 重复，改去那边补测试 |

## 最后：这些 bug 的共同点

它们几乎都不是"某个算法写错了"，而是**边界组合没被覆盖**：`<1 x Ty>`、非 2 的幂的 lane 数、
32 位指针、宽类型被拆开、延迟求值后为空的列表。GlobalISel 尤其明显：合法化规则是 N 个后端 ×
若干算子 × 类型形状的组合空间，人肉读代码和手写 MIR 都只能覆盖其中一小块。

这也是我后来开始做 gisel 的原因——把规则表从 C++ 构造函数里抽出来，变成可以被查询、被出题、
被两个实现对拍的东西。上面这些 bug 里，至少 `minScalarSameAs` 和 `maxScalarEltSameAsIf` 这两条，
用"谓词 ↔ mutation 语义一致性"这一条性质就能自动查出来。
