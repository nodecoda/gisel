# AMDGPU：最后一个没有接入的 GlobalISel legalizer

一句话：**上游一共 11 个 legalizer 构造函数，语料收了 9 个；BPF 的构造函数是空的，
真正剩下的只有 AMDGPU。** 导入器已经能读它的大半（597 个 builder 调用 / 651 条规则），还差 119 条语句，
其中约一半要动 DSL 本身，不是改拼写就能补的。本轮只做盘点和一个可复现的探针，
不收语料。

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

## 2 AMDGPU 的现状：能读，但还收不了

```sh
python3 tools/import-cxx.py --probe AMDGPU:Amdgpu \
  --src <llvm>/llvm/lib/Target/AMDGPU/AMDGPULegalizerInfo.cpp --stats
```

快照：源 `sha256 f597a8cd149aeb22…`（pin `9bfc850b9940`），导入器取本报告所在提交
（`git log -1 -- docs/REPORT-amdgpu.md`）——数字随导入器变化，源 sha 是稳定锚点。

```
142 rulesets, 655 rules, 113 refused
TOTAL  597 calls  655 rules
```

597 个 builder 调用已经能读：`legalFor`(131)、`scalarize`(101)、`lower`(54)、
`clampScalar`(50)、`widenScalarToNextPow2`(42)、`customFor`(35)、`minScalar`(35)、
`clampMaxNumElements`(24)、`widenScalarFor`(17) 等。地址空间指针类型
（`BufferFatPtr` 160、`RsrcPtr` 128、`BufferStridedPtr` 192）和 43 个 subtarget
feature 都已经进语料头部，说明类型/特征这两层不是障碍。

`--probe` 只保证计数和拒绝项可信：wrapper 重命名表是全局的，探针没经过 `PIN.json`
钉名字，所以它生成的标识符不能直接收货。

## 3 113 条拒绝：按“要做什么”分类

| 类别 | 条数 | 要做什么 |
|---|---:|---|
| `clampMaxNumElementsStrict` | 30 | DSL 新原语。C++ 把它定义成 `alignNumElementsTo` + `clampMaxNumElements`（`LegalizerInfo.h:1327`），也就是“先按 N 补 undef 到整倍数，再夹上界”。`clamp_max` 已有，缺的是“把 lane 数补齐到 N 的倍数”这一步 |
| `widenScalarToNextMultipleOf` | 9 | DSL 新原语：加宽到 Size 的整数倍（不是 next pow2，`LegalizerInfo.h:989`） |
| `moreElementsIf` 的 `oneMoreElement` / `moreEltsToNext32Bit` / 读 `ST` 的谓词 | 16 | 变异体是“lane 数 +1 / 补到 32 位倍数 / 依赖子目标”的表达，DSL 的 `more(slot, pow2)` 覆盖不了 |
| `legalIf` 的谓词读到 `ST`（子目标） | 9 | 见 §4，这是设计决定 |
| `fewerElementsIf` 谓词读 `Query` | 6 | 谓词 lambda 里出现 `Query.Types[0].isVector()` 这类组合；`body_pred` 应该能读，当前被拒说明缺一条拼写 |
| memdesc align 是具名常量（`GlobalAlign8` / `GlobalAlign32` / `2 * 8`） | 7 | 便宜：`parse_aligns` 只认字面量，把文件内 `const Align` 常量求值即可 |
| `narrowScalarIf` 的变异体读 memdesc（`getScalarTypeFromMemDesc(0)`） | 3 | 需要新的记忆描述读取原语 |
| `narrowScalarIf(...)` 三参数形态 | 2 | DSL 侧要有“自定义变异体”的位置；否则退化成 `lower` |
| `bitcastIf` 的目标类型是算出来的（`bitcastToRegisterType` / `bitcastToVectorElement32` / lambda） | 6 | DSL 新原语：bitcast 到表达式给出的类型 |
| `widenScalarIf` 的变异体是 `widenScalarOrEltToNextPow2(T, 16)` / bitcast lambda | 6 | 前 4 条是拼写，后 2 条同 bitcast |
| `customIf` / `customFor` 的谓词读 `ST` | 2 | 同 §4 |
| `legalFor`/`lowerFor` 参数是嵌套集合 `{{S32}, {S64}}` | 4 | 便宜：集合套集合的展开 |
| `legalForCartesianProduct(AllS32Vectors)` 传的是局部变量 | 2 | 便宜：把文件内 `SmallVector<LLT>` 常量展开 |
| 其余单条 | 11 | `clampNumElements` 的元素类型写法 3、`fewerElementsIf` 的变异体 3、`minScalarIf(...)`、`changeElementSizeTo`、以及两条构造函数里的局部 lambda 变量 4；逐条看 |

本轮顺手补掉的两类（6 条）：构造函数里的 `assert(...)` 当 plumbing 忽略（2 条），`sameSize(0, 1)` 翻成 `size_of(slot(0)) == size_of(slot(1))`（4 条）。

粗分：**约 20 条是拼写/常量求值（一天量级）**，**约 60 条要 DSL + `--emit=inc` +
`eval` 同步扩原语**（每个原语都要有语义、lint、单元测试、以及和现网 C++
`LegalizerInfo` 的一致声明），**9 条是 §4 的设计决定**。

## 4 真正的分水岭：文件内的 C++ 谓词

AMDGPU 的 load/store 规则里有：

```cpp
Actions.legalIf([=](const LegalityQuery &Query) -> bool {
  return isLoadStoreLegal(ST, Query);
});
Actions.bitcastIf([=](const LegalityQuery &Query) -> bool {
  return shouldBitcastLoadStoreType(ST, Query.Types[0], Query.MMODescrs[0].MemoryTy);
}, bitcastToRegisterType(0));
```

`isLoadStoreLegal` / `shouldBitcastLoadStoreType` / `hasBufferRsrcWorkaround` 是
`AMDGPULegalizerInfo.cpp` 里几千行的辅助函数，不是 `LegalityInfo.h` 的谓词代数。
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

## 5 与端到端对拍的距离

导入器 0 拒绝之后，AMDGPU 还有 runner 侧的三件事：

1. `AMDGPULegalizerInfo(const GCNSubtarget &, const GCNTargetMachine &)` 要一个
   `GCNTargetMachine`，不像 RISCV/SPIRV 拿 `Subtarget` 就够；runner 要么建一个
   最小 TM，要么只复用 constructor 需要的那部分。
2. 子目标特征多（43 个 feature），配置轴要挑代表点（`gfx900`/`gfx90a`/`gfx1100`/
   `gfx1200` + wave32/64），不是把 `TARGETS` 里的配置全乘起来。
3. `cases` 的笛卡尔积在 AMDGPU 上会爆：142 rulesets，3~4 槽的 ruleset 不少。
   X86 74k 状态已经 68 秒；AMDGPU 直接全量必然不可跑，需要按 ruleset 分块 + 只取
   声明过的类型（`gisel cases` 已有的等价类压缩要先用上，再测一次规模）。

## 6 建议顺序

1. 便宜项先清：`assert`、`sameSize`、具名 align、嵌套集合、局部类型集合展开
   （预计 119 → 约 95）。
2. 定下 §4：逃逸点还是新原语。定了再动 DSL，否则会白改一轮。
3. DSL 原语分批：`align_lanes`（解锁 30 条）→ `widen_to_multiple`（9）→
   lane 数 `+1` / 补到 32 位（16）→ bitcast 到算出来的类型（6）。
4. 0 拒绝之后再进 `PIN.json` / `TARGETS` / cases 配置 / runner，最后才是端到端。
   顺序反了会拿一个 119 条缺口冒充“已接入”。

## 7 复现

```sh
cd /home/ubuntu/llvm/gisel
python3 tools/import-cxx.py --probe AMDGPU:Amdgpu \
  --src /home/ubuntu/llvm/trees/explore/llvm/lib/Target/AMDGPU/AMDGPULegalizerInfo.cpp \
  --stats
```

`--probe` 不写文件、不做 `PIN.json` 的计数漂移检查；它的输出就是本报告 §2/§3 的
数字。源文件 sha256 变了（上游改了 AMDGPU legalizer）就重跑，别用本文的数字。
