# AMDGPU：最后一个没有接入的 GlobalISel legalizer

一句话：**上游一共 11 个 legalizer 构造函数，语料收了 9 个；BPF 的构造函数是空的，
真正剩下的只有 AMDGPU。** 导入器已经能把 AMDGPU 读成一份**能解析、能 lint**
的语料（627 条规则），但还有 127 条语句拒绝，其中约一半要动 DSL 本身。本轮只做
盘点、一个可复现的探针、以及把“悄悄产出非法文本”这类缺陷堵死；不收语料。

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
142 rulesets, 627 rules, 127 refused
TOTAL  585 calls  639 rules

lint: 0 error(s), 7 warning(s), 627 rule(s)
```

7 条 warning 都是 `arity unknown`（`G_BUILD_VECTOR_TRUNC`、`G_MERGE_VALUES` 等），
与 X86 上已知的那一类相同，不是语法问题。585 个 builder 调用已经能读：
`legalFor`(131)、`scalarize`(101)、`lower`(54)、`clampScalar`(50)、
`widenScalarToNextPow2`(42)、`customFor`(35)、`minScalar`(35)、
`clampMaxNumElements`(24)、`widenScalarFor`(17) 等。地址空间指针类型（160/128/192
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
| `hasBufferRsrcWorkaround(slot(0))` | 目标里的宿主 helper 被原样透传 | 未知调用一律拒绝，不再复制 |
| `size_of(slot(0).getScalarType())` | 少一条 `getScalarType().getSizeInBits()` 折叠 | 补 `bits_of(scalar_of(...))` |
| `in(slot(0), AllS32Vectors)` 悬空 | 文件级 `initializer_list<LLT>` 没读 | 读文件级类型集合与 `LLT` 常量 |
| `ty(MaxRegisterSize)` / `MaxScalar` 未声明 | 文件级 `constexpr unsigned` 没折 | 读文件级整数常量并代入宽度 |
| `LLT::fixed_vector(2, LocalPtr)` 原样输出 | 元素是具名类型的内联向量没有名字 | 合成一条 `type ... = LLT::fixed_vector(2, ...)` |
| `LLT::pointer(AMDGPUAS::GLOBAL_ADDRESS, 64)` | 地址空间枚举 | 与 SPIR-V 一样映射成数字（`AMDGPUAddrSpace.h`） |
| `clamp_max(...) when ...` | 语法里 clamp 不能带 `when` | 拒绝，不产出解析不了的文本 |

这条约束对现有 9 份语料零影响（`--all --check` 9/9 逐字节相同）。

## 3 127 条拒绝：按“要做什么”分类

| 类别 | 条数 | 要做什么 |
|---|---:|---|
| `clampMaxNumElementsStrict` | 30 | DSL 新原语。C++ 把它定义成 `alignNumElementsTo` + `clampMaxNumElements`（`LegalizerInfo.h:1327`）：“先按 N 补 undef 到整倍数，再夹上界”。`clamp_max` 已有，缺“补齐到 N 的倍数” |
| `moreElementsIf` 的 lane 变异体 | 16 | `oneMoreElement` / `moreEltsToNext32Bit` / 依赖子目标的 lane 数，`more(slot, pow2)` 覆盖不了 |
| `if` 块里的 clamp（gated clamp_max） | 12 | 语法缺“带谓词的 clamp”。要么给它加 `when`，要么让 importer 拆成 `actionIf` 形态 |
| 谓词读子目标（`ST`） | 11 | 见 §4；其中 2 条是 `customIf` |
| `widenScalarToNextMultipleOf` | 9 | DSL 新原语：加宽到 Size 的整数倍（不是 next pow2，`LegalizerInfo.h:989`） |
| memdesc 的具名/表达式 align | 7 | `GlobalAlign8 = ST.hasUnalignedBufferAccessEnabled() ? 0 : 8`：align 字段需要一个“配置选的整数”，现在没有拼写 |
| `widenScalarIf` 的变异体 | 7 | `widenScalarOrEltToNextPow2(T, 16)` 的具名拼写（4），bitcast lambda（2），`changeElementSizeTo`（1） |
| `bitcastIf` 的目标类型要算 | 6 | DSL 新原语：bitcast 到表达式给出的类型（`bitcastToRegisterType` 等） |
| `fewerElementsIf` 谓词读 `Query` | 6 | lambda 里 `Query.Types[i].isVector()` 之类的组合，`body_pred` 已能读，缺一条拼写 |
| `narrowScalarIf` 的变异体 / 三参数 | 5 | 变异体读 memdesc（`getScalarTypeFromMemDesc`）3 条；三参数形态 2 条 |
| 宿主任意谓词（host helper / 未知名字） | 4 | 见 §4：`hasBufferRsrcWorkaround`、`MaxRegisterSize` |
| 嵌套集合参数 `{{...}}` | 4 | 便宜：`legalFor`/`lowerFor` 的集合套集合展开 |
| `fewerElementsIf` 的变异体 | 3 | `fewerEltsToSize64Vector` / `scalarize` 作变异体 |
| `clampNumElements` 的元素类型写法 | 3 | `clampNumElements(0, V16S32, V32S32)` 取元素类型的写法 |
| 构造函数里的局部 lambda 变量 | 3 | `auto notValidElt = [=](...)`、`needToSplitMemOp`：需要先把 lambda 存成命名谓词 |
| 其他 | 1 | `minScalarIf(...)` |

粗分：**约 10 条是拼写/常量求值**，**约 100 条要 DSL + `--emit=inc` + `eval` 同步
扩原语**（每个原语都要有语义、lint、单元测试、以及和现网 C++ `LegalizerInfo` 的
一致声明），**11 条是 §4 的设计决定**。

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

现在导入器对这类语句是**拒绝**（4 条），不是透传。选 1 之后，它们会变成带
`feature("...")` 的规则；选 2 才会动语法。

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
2. 定下 §4：逃逸点还是新原语。定了再动 DSL，否则会白改一轮。
3. DSL 原语分批：`align_lanes`（解锁 30 条）→ `widen_to_multiple`（9）→
   lane 数 `+1` / 补到 32 位（16）→ 带谓词的 clamp（12）→ bitcast 到算出来的类型（6）。
4. 0 拒绝之后再进 `PIN.json` / `TARGETS` / cases 配置 / runner，最后才是端到端。
   顺序反了会拿 127 条缺口冒充“已接入”。

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
