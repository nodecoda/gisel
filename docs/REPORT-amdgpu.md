# AMDGPU：最后一个没有接入的 GlobalISel legalizer

一句话：**上游一共 11 个 legalizer 构造函数，语料收了 9 个；BPF 的构造函数是空的，
真正剩下的只有 AMDGPU。** 导入器已经能把 AMDGPU 读成一份**能解析、能 lint**
的语料（792 条规则），但还有 12 条语句拒绝，其中一部分要动 DSL 本身。本轮做
盘点、一个可复现的探针、把“悄悄产出非法文本”这类缺陷堵死，并按 §4 选定的
逃逸点路线落下 `opaque(...)`；语料仍未收。

数字基线（pin `9bfc850b9940`）：

| 项 | 值 |
|---|---:|
| rulesets | 142 |
| rules | 792 |
| refused | 12 |
| builder 调用 | 689 |
| 其中 `opaque` 规则 | 22 处 / 18 条规则 / 10 个不同表达式 |
| lint | 0 error / 7 warning |

## 1 盘点：11 个构造函数

命令（pin 提交 `9bfc850b9940`）：

```sh
git -C <llvm> grep -n "LegalizerInfo::[A-Za-z0-9_]*LegalizerInfo(" \
    9bfc850b9940 -- llvm/lib/Target | sed 's#^[^:]*:##' | cut -d: -f1 | sort -u
```

| target | 行数 | 语料 | 说明 |
|---|---:|---|---|
| AMDGPU | 8,931 | **未收** | 本文 |
| AArch64 | 2,902 | 117 rulesets / 744 rules | 端到端 agree |
| RISCV | 1,917 | 96 / 402 | 端到端 agree |
| SPIRV | 1,431 | 83 / 353 | 端到端 agree，4 条上游断言 |
| X86 | 1,059 | 63 / 328 | 端到端 agree，2 条 deviation |
| Mips | 618 | 48 / 95 | 端到端 agree |
| ARM | 505 | 52 / 96 | 端到端 agree，Thumb1 未覆盖 |
| WebAssembly | 234 | 29 / 109 | 端到端 agree |
| PowerPC | 91 | 15 / 25 | 端到端 agree |
| M68k | 52 | 6 / 13 | 端到端 agree |
| BPF | 20 | 不收 | 构造函数为空，没有任何规则 |

BPF 不是遗漏：`BPFLegalizerInfo::BPFLegalizerInfo(const BPFSubtarget &) {}` 一条规则都
没有，语料会是空文件，对拍只剩“所有查询都 Unsupported”。收它没有信息量，写在这里
比造一个空对拍诚实。

## 2 AMDGPU 的现状：能读成一份合法语料，但还收不了

```sh
python3 tools/import-cxx.py --probe AMDGPU:Amdgpu \
  --src <llvm>/llvm/lib/Target/AMDGPU/AMDGPULegalizerInfo.cpp \
  --out /tmp/amdgpu.gisel --stats
python3 -m gisel lint /tmp/amdgpu.gisel
```

快照：源 `sha256 f597a8cd149aeb22…`（pin `9bfc850b9940`），导入器取本报告所在提交
（`git log -1 -- docs/REPORT-amdgpu.md`）——数字随导入器变化，源 sha 是稳定锚点。

```
142 rulesets, 792 rules, 12 refused
TOTAL  689 calls  793 rules

lint: 0 error(s), 7 warning(s), 792 rule(s)
```

7 条 warning 都是 `arity unknown`（`G_BUILD_VECTOR_TRUNC`、`G_MERGE_VALUES` 等），
与 X86 上已知的那一类相同，不是语法问题。689 个 builder 调用已经能读：
`legalFor`(131)、`scalarize`(101)、`lower`(56)、`clampScalar`(50, 100 条规则)、
`widenScalarToNextPow2`(44)、`customFor`(35)、`minScalar`(35)、
`clampMaxNumElementsStrict`(30, 60 条规则)、`clampMaxNumElements`(24)、
`legalIf`(18)、`moreElementsIf`(18)、`widenScalarFor`(17)、`lowerFor`(15)、
`legalForTypesWithMemDesc`(8, 14 条规则)、`legalForCartesianProduct`(13, 14
条规则) 等。统计表 TOTAL 比正文多 1 条，是构造期 `if (false)` 丢弃的那条。地址空间指针类型（160/128/192
位的 fat pointer）和 43 个 subtarget feature 都已经进语料头部。

### 2.1 先把“能解析”变成硬约束

上一版探针会**悄悄产出解析不了的文本**：`replace(ty(LLT::integer(32)))`、
`clamp_max(...) when ...`、`in(slot(0), AllS32Vectors)`（集合根本没定义）。
这些不影响计数，只让 `--emit=inc` 拿到一份没人能读的语料。

现在 `transcribe()` 在写盘前用 `gisel.ast.parse_program` 解析自己生成的文本：
解析失败就报出第一处错误、rc=1、**不写文件**。本轮靠这条约束抓出并修掉的：

| 症状 | 原因 | 修法 |
|---|---|---|
| `Amdgpu_ST_getGeneration >= ty(AMDGPUSubtarget::SEA_ISLANDS)` | 枚举常量被当成类型 | 与常量比较的子目标读法成一类 opaque feature |
| `replace(ty(LLT::integer(32)))` | `I32` 是大写，`t.name` 只查小写 `i32` | 两种拼写都查 |
| `hasBufferRsrcWorkaround(slot(0))` | 目标里的宿主 helper 被原样透传 | lambda 体是单条 `return` 时转成 `opaque("...")`；其余未知调用仍拒绝 |
| `size_of(slot(0).getScalarType())` | 少一条 `getScalarType().getSizeInBits()` 折叠 | 补 `bits_of(scalar_of(...))` |
| `in(slot(0), AllS32Vectors)` 悬空 | 文件级 `initializer_list<LLT>` 没读 | 读文件级类型集合与 `LLT` 常量 |
| `ty(MaxRegisterSize)` / `MaxScalar` 未声明 | 文件级 `constexpr unsigned` 没折 | 读文件级整数常量并代入宽度 |
| `LLT::fixed_vector(2, LocalPtr)` 原样输出 | 元素是具名类型的内联向量没有名字 | 合成一条 `type ... = LLT::fixed_vector(2, ...)` |
| `LLT::pointer(AMDGPUAS::GLOBAL_ADDRESS, 64)` | 地址空间枚举 | 与 SPIR-V 一样映射成数字（`AMDGPUAddrSpace.h`） |
| `clamp_max(...) when ...` | 语法里 clamp 不能带 `when` | 拒绝，不产出解析不了的文本 |

这条约束对现有 9 份语料零影响（`--all --check` 9/9 逐字节相同）。

## 3 12 条拒绝：按“要做什么”分类

| 类别 | 条数 | 要做什么 |
|---|---:|---|
| `bitcast` 的复杂 lambda 体 | 4 | `fewerElementsIf`/`widenScalarIf` 里多行的 `std::pair` 体（LOAD/STORE/MERGE/UNMERGE） |
| `narrowScalarIf` 三参数形态 | 2 | 谓词 + 变异 + 变异 |
| `customIf` 谓词里的宿主 register-class 查询 | 2 | `SIRegisterInfo::getSGPRClassForBitWidth(...)` 在 `&&` 表达式内部，不是整条谓词 |
| `isIllegalRegisterType(ST, VecTypeIdx)` | 2 | 第二参是构造函数变量（循环里算出来的 slot），不是整数字面量，谓词值逃逸不敢猜 |
| 构造函数里的局部 lambda | 1 | `needToSplitMemOp` |
| `moreElementsToNextExistingRegClass` | 1 | 返回 `LegalizeMutation` 的 helper，不是谓词；属于变异侧原语 |

本轮清掉的十二类（原 30 + 12 + 9 + 14 + 6 + 11 + 7 + 4 + 3 + 3 + 2 + 1）走的是 §6 第 3 步的原语：

- `clampMaxNumElementsStrict`（30 条）→ `align_lanes` + `clamp_max` 两条规则；
- `if` 块里的 clamp（12 条）→ `clamp_min/max ... when P`；
- `widenScalarToNextMultipleOf`（9 条）→ `widen(slot(i), multiple_of(N))`，
  `multiple_of` 本来就有，补的是加宽形态（`LegalizerInfo.h:989` 的 `alignTo`）；
- lane 变异体（14 条）→ 读 helper 的函数体：`more/fewer(slot(i), replace(<LLT 表达式>))`，
  值层补 `add`/`sub`（`mul`/`udiv`/`align_to` 已有）；
- bitcast 到算出来的类型（6 条）→ 内联 `static LLT` helper 的早返回（`select`）、
  `LLT::integer(N)`、以及 `bitcastIf` 的 inline lambda；
- 变异 lambda 形态（11 条）→ `scalarize(i)` 展开成 `replace(elem_of(...))`，
  `changeElementSizeTo` 接受变量下标，`widenScalarOrEltToNextPow2(i, Min)` 展开成
  `replace(elt_size_to(..., pow2_at_least(...)))`（变异本身没有 pow2 隐式 guard）；
- memdesc 的具名/表达式 align（7 条）→ align 允许“配置选的整数”
  （`GlobalAlign8 = ST.hasUnalignedBufferAccessEnabled() ? 0 : 8`），导入器把整张表
  按 gate 拆成互斥的两份；纯整数表达式（`2 * 8`）在导入期折成 16；
- 嵌套集合参数（4 条）→ 按 C++ 重载解析读内层 arity：1 元素是
  `initializer_list<LLT>`（只约束 slot 0），2/3 元素才是 pair/tuple
  （`in_pairs`/`in_triples`）；
- `getScalarTypeFromMemDesc`（3 条）→ 变异 helper 的 body 读
  `Query.MMODescrs[0].MemoryTy`：目标类型写成
  `replace(int_of_size(size_of(mem_ty(mem_slot(0)))))`，谓词 lambda 里的
  `MemTy.isScalar()` 折成 `sort_of(mem_ty(mem_slot(0))) == scalar`；
- `clampNumElements` 的元素类型（3 条）→ 从向量常量的名字取元素
  （`V16S32` → `S32`），大小写两种拼写都查已声明的标量，不合成
  `Amdgpu_s32` 这种未声明名；
- `notValidElt` 二参 lambda（2 条）→ 局部谓词 helper 的第二参是 slot：
  逐调用点把 `TypeIdx` 绑成 `LitTyIdx`/`BigTyIdx` 的值再内联；
- `minScalarIf(P, i, T)`（1 条）→ `widen(slot(i), ty(T)) when P`；谓词里读
  文件级 `MaxRegisterSize` 时折成 1024。谓词表达式内部的宿主调用
  （`SIRegisterInfo::...`）现在明确拒绝并报出表达式，不再产出解析不了的文本。
  上面六批都只动导入器，没有新增语法。

## 4 真正的分水岭：文件内的 C++ 谓词

AMDGPU 的 load/store 规则里有：

```cpp
Actions.legalIf([=](const LegalityQuery &Query) -> bool {
  return isLoadStoreLegal(ST, Query);
});
Actions.customIf([=](const LegalityQuery &Query) -> bool {
  return hasBufferRsrcWorkaround(Query.Types[0]);
});
```

`isLoadStoreLegal` / `hasBufferRsrcWorkaround` / `shouldBitcastLoadStoreType` 是
`AMDGPULegalizerInfo.cpp` 里几千行的辅助函数，不是 `LegalizerInfo.h` 的谓词代数。
gisel 只有两条路：

1. **当 `feature(...)` 逃逸点**：`--emit=inc` 原样透传，生成的 `.inc` 可以编译、
   可以和现网逐点对拍；但 `eval` / `cases` / `graph` 判不了它，等价类会把它算作
   不透明叶，测试用例的“分母”在这几条规则上是空的。
2. **给 DSL 加“引用宿主谓词”的原语**，并在 `spec` 里明写：这类规则的答案只能由
   对拍给出，不能由 gisel 自己推。

两条路都能做 AMDGPU 的对拍，差别是**能不能声称“语料自己覆盖了这些规则”**。这与
X86 `feature("Subtarget.is64Bit()")` 是同一个决定，只是 AMDGPU 把它从“子目标开关”
放大成“几千行辅助逻辑”。建议选 1，并在报告里把“不透明规则”的条数和 opcode 列清
——这是“结构封闭 + 显式逃逸”这条设计线的自然延伸，不要为了完整性把它裁成 0。

**已选路 1 并落地。** 语法里新增 `opaque("...")`（与 `feature` 并列的主谓词，
见 `spec/grammar.md` §5）：`--emit=inc` 把它拼回 `return (<expr>);`，
`--emit=core` 写进 `escapes`，`gisel eval` 对它抛 `EvalError`（洞，不是 false）。
导入器现在把“lambda 体是单条 `return <宿主表达式>`”的谓词转成 `opaque(...)`：

```
Opaque (10 host predicate(s), copied as `opaque(...)`; the generated C++ evaluates them, gisel cannot):
  isRegisterClassType(ST, 0)(Query)
  isRegisterClassType(ST, 1)(Query)
  isLoadStoreLegal(ST, Query)
  hasBufferRsrcWorkaround(Query.Types[0])
  shouldBitcastLoadStoreType(ST, Query.Types[0], Query.MMODescrs[0].MemoryTy)
  shouldWidenLoad(ST, Query, G_LOAD)
  isRegisterType(ST, 0)(Query)
  isRegisterType(ST, 1)(Query)
  notValidElt(Query, LitTyIdx)
  notValidElt(Query, BigTyIdx)
```

当前 22 处（18 条规则）走这条口，10 个不同表达式：

```
isRegisterClassType(ST, 0)(Query)                                          x2
isRegisterClassType(ST, 1)(Query)                                          x1
isLoadStoreLegal(ST, Query)                                                x3
hasBufferRsrcWorkaround(Query.Types[0])                                    x2
shouldBitcastLoadStoreType(ST, Query.Types[0], Query.MMODescrs[0].MemoryTy) x2
shouldWidenLoad(ST, Query, G_LOAD)                                         x1
isRegisterType(ST, 0)(Query)                                               x4
isRegisterType(ST, 1)(Query)                                               x3
notValidElt(Query, LitTyIdx)                                               x2
notValidElt(Query, BigTyIdx)                                               x2
```

`isRegisterType(ST, 0)` 这类是**谓词值**（`LegalityPredicate = std::function<bool(const
LegalityQuery&)>`），必须补 `(Query)` 才能在规则 lambda 里当 bool 用。导入器只在
“文件里确实声明了 `LegalityPredicate <名字>(`、且最后一个实参是整数字面量”时才这么
翻译；`isIllegalRegisterType(ST, VecTypeIdx)` 的第二参是循环变量，不猜，继续拒绝。

实现上踩过一个坑：`isRegisterType(ST, TypeIdx)` 的谓词体转调同名的 `bool` 重载，
直接内联会无限递归（第一版把整条 builder 链炸成 `RecursionError`，规则静默消失）。
现在内联栈挡住同名重入，失败才退回 `opaque`。

这条口子也修掉了一个统计错误：头部原先把“解析到、但所在语句因别的理由被拒绝”的
谓词也算进去（13），现在只列真正出现在正文里的（10 个不同表达式 / 22 处）。

## 5 与端到端对拍的距离

导入器 0 拒绝之后，AMDGPU 还有 runner 侧的三件事：

1. `AMDGPULegalizerInfo(const GCNSubtarget &, const GCNTargetMachine &)` 要一个
   `GCNTargetMachine`，不像 RISCV/SPIRV 拿 `Subtarget` 就够；runner 要么建一个
   最小 TM，要么只复用 constructor 需要的那部分。
2. 子目标特征多（43 个 feature），配置轴要挑代表点（`gfx900`/`gfx90a`/`gfx1100`/
   `gfx1200` + wave32/64），不是把配置全乘起来。
3. `cases` 的笛卡尔积在 AMDGPU 上会爆：142 rulesets，3~4 槽的 ruleset 不少。
   X86 74k 状态已经 68 秒；AMDGPU 直接全量必然不可跑，需要按 ruleset 分块 + 只取
   声明过的类型（`gisel cases` 的等价类压缩要先用上，再测一次规模）。

## 6 建议顺序

1. ~~便宜项先清：`assert`、`sameSize`、文件级常量/类型集合、地址空间枚举。~~
   本轮已完成，并顺带堵住“悄悄产出非法文本”。
2. ~~定下 §4：逃逸点还是新原语。~~ 已选**逃逸点**并落地 `opaque(...)`，含
   谓词值形态 `opaque("helper(ST, i)(Query)")`（解锁 6 条规则）。
3. DSL 原语分批：~~`align_lanes`（30）~~、~~带谓词的 clamp（12）~~ 已完成；
   ~~`widen_to_multiple`（9）~~、~~lane 数 `+1` / 补到 32 位（14）~~、
   ~~bitcast 到算出来的类型（6）~~、~~变异 lambda 形态（11）~~、
   ~~memdesc 具名/表达式 align（7，导入器侧，无语法变更）~~、
   ~~嵌套集合参数（4，导入器侧，无语法变更）~~、
   ~~`getScalarTypeFromMemDesc`（3，导入器侧，无语法变更）~~、
   ~~`clampNumElements` 元素类型（3，导入器侧，无语法变更）~~、
   ~~`notValidElt` 二参 lambda（2，导入器侧）~~、
   ~~`minScalarIf`（1，导入器侧）~~ 已完成。
   剩下 12 条里只有 MERGE/UNMERGE 的 2 条是纯导入器工作（需要一个
   “赋值 + if 改写”的变异 body 读取器）；其余 10 条都卡在宿主值或宿主谓词：
   `maxSizeForAddrSpace`（4）、`getSGPRClassForBitWidth`（4）、
   `moreElementsToNextExistingRegClass` 的循环（1）、`needToSplitMemOp`（1）。
   这些需要“表达式里的宿主逃逸点”这一层设计，属于语法/契约变更，按约定先
   出变更说明等批准，不直接动手。
4. 0 拒绝之后再进 `PIN.json` / `TARGETS` / cases 配置 / runner，最后才是端到端。
   顺序反了会拿 12 条缺口冒充“已接入”。

## 7 复现

```sh
cd /home/ubuntu/llvm/gisel
python3 tools/import-cxx.py --probe AMDGPU:Amdgpu \
  --src /home/ubuntu/llvm/trees/explore/llvm/lib/Target/AMDGPU/AMDGPULegalizerInfo.cpp \
  --stats
```

`--probe` 不写文件（除非给 `--out`）、不做 `PIN.json` 的计数漂移检查；它的输出就是
本报告 §2/§3 的数字。源文件 sha256 变了（上游改了 AMDGPU legalizer）就重跑，别用
本文的数字。
