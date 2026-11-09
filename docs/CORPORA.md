# 语料：为了自证，预先做的准备

`tests/corpus/*.gisel` 不是 gisel 的运行前提，而是**项目为了证明自己、预先做的
准备**：我们用自己的工具解析 LLVM 里的手写规则，提取出来写成 `.gisel`，然后
冻结。LLVM 的文件是输入，`.gisel` 是我们的产物。

## 上游到底把规则写在哪

上游 LLVM main 里**没有** legalizer 的 `.td`，`llvm-tblgen` 也没有
`-gen-legalizer`。所有 target 的合法化规则都写在 `*LegalizerInfo.cpp` 的构造
函数里（`getActionDefinitionsBuilder(...)` 链）：X86、AArch64、RISC-V 都一样。

我们的 LLVM 分支曾经加过一个中间格式（`include/llvm/Target/LegalizerInfo.td`
+ `utils/TableGen/LegalizerInfoEmitter.cpp` + `-gen-legalizer*`）。**这条链路
已经不走**：语料直接从手写 C++ 构造函数转录。

## 链路

```text
上游 X86/AArch64/RISCVLegalizerInfo.cpp（手写 builder 链）
  -> tools/import-cxx.py -> .gisel
  -> gisel gen --emit={inc,check,core}
```

`tools/import-cxx.py` 是**一次性转录工具**，不是通用 C++ 解析器：它只认这三种
构造函数用到的那一小撮写法，认不出来就带行号拒绝（rc=1），绝不静默丢规则。
**AArch64 的 pin 指向 `trees/explore` 上打过一个小补丁的源文件**：原文在谓词里
对非向量 / scalable 类型调 `LLT::getNumElements()` 和 `getSizeInBits()`，断言构建
在合法查询上直接 abort（见 `2026-11-09-13`）。补丁只把这两类观察改成显式语义
（`numElements()` + `getKnownMinValue()`），**规则内容一字未变**——重新导入与
入库语料逐字节相同。

X86 的两条偏离写在工具里（`X86_DEVIATIONS`），每条都会断言上游文本仍在，改了
上游就报错而不是悄悄失效：

| 偏离 | 原因 |
|---|---|
| `G_BUILD_VECTOR` 去掉最小 lane clamp | 加 lane 会把 build vector 变成更大的 build vector，缩回来又是同一个查询，legalizer 会死循环（上游 issue #236649，修复 PR #238277；实测见 `2026-11-09-14`）；只留最大 clamp，窄 build vector 走 Unsupported |
| `G_CTPOP` 增加 VPOPCNTDQ 的向量 legal | 上游还没有这条规则（PR #235976），语料先带上向量 legalization，冻结答案里这些点是 Legal |

这两条偏离**只相对于 pin**。`PIN.json` 的 `patches` 记录了仓库叠加的 5 个未合
PR（#238306、#238277、#235976、#237650、#239136），工作台构建的官方侧就是
`pin + patches`。所以偏离后的语料和官方侧行为一致：X86 端到端 3,276/3,276、
AArch64 13,199/13,199、RISC-V 6,299/6,299 全部 agree。等这些 PR 合入上游，
把 `commit` 前移，偏离函数会按设计**报错**（它断言旧文本还在），那时删掉它们
即可——这正是它存在的意义。

## 复现：一条命令，钉住计数

导入器是**一次性转录工具**，不是通用 C++ 解析器：目标只有三个，路径和规则数
写死在 `TARGETS` 里，认不出的语句带行号拒绝。重新生成并逐字节对照仓库里的
语料：

```sh
GS_X86_SRC=.../X86LegalizerInfo.cpp \
GS_AARCH64_SRC=.../AArch64LegalizerInfo.cpp \
GS_RISCV_SRC=.../RISCVLegalizerInfo.cpp \
  python3 tools/import-cxx.py --all --check
```

`--check` 只比对、不写盘；任一目标计数漂移或文本不同都返回 1。生成的 `.gisel`
头部记录源文件的 sha256，所以“这份语料来自哪份 cpp”不靠记忆。只跑一个目标：

```sh
python3 tools/import-cxx.py X86 .../X86LegalizerInfo.cpp \
    --out tests/corpus/X86LegalizerInfo.gisel
```

钉住的基线（源 sha256 / 规则集 / 规则）：

| 目标 | 源 sha256（前 12 位） | rulesets | rules |
|---|---|---:|---:|
| X86 | `79f2376096c3` | 63 | 328 |
| AArch64 | `2b5377c3eedd` | 117 | 744 |
| RISC-V | `ad529e1f1a9e` | 96 | 402 |

换上游修订不是改参数，而是改工具：计数断言会立刻报 `DRIFT`。

`pred`/`select`/`feature` 的名字经过一轮人工审阅（LLM 提议、表里冻结）：
C++ 里有名字的沿用，匿名的按语义命名，单 feature 条件直接内联进 `select`。
残留的 `X_selN` / `X_condN` 会被测试拦下。详见
`docs/REPORT-cxx-corpus.md` §3b。

| 语料 | 上游规则在哪 | 我们的提取路径 | 冻结对照物 | 能证明 |
|---|---|---|---|---|
| X86 | `X86/GISel/X86LegalizerInfo.cpp` | cpp → `tools/import-cxx.py` → `.gisel` | 无 emitter；gisel 自己的输出（**自基线**）+ 冻结答案 | 生成器回归；规则保真靠 `tests/cases/x86_ref_dump.jsonl` 与工作台对拍 |
| AArch64 | `AArch64/GISel/AArch64LegalizerInfo.cpp` | 同上 | 同上 | 同上 |
| RISC-V | `RISCV/GISel/RISCVLegalizerInfo.cpp` | 同上 | 同上 | 同上 |
| M68k | `M68kLegalizerInfo.cpp` | 人工转写（探针，13 条） | 无 | 语法可表达性 |
| WebAssembly | `WebAssemblyLegalizerInfo.cpp` | 人工转写（探针，108 条） | 无 | 语法可表达性 |

## 证据分三层，别混

1. **转录保真（语料层）**：`tools/import-cxx.py` 从 C++ 构造函数转录，0 拒绝，
   并且重新导入能逐字节复现仓库里的 `.gisel`（`tests/test_import_cxx.py`）。
   有偏离的地方在工具里点名，不是暗改。
2. **规则保真（行为门，工作台）**：每个语料在 `tests/cases/*_ref_dump.jsonl`
   的全部冻结查询上 `gisel eval` 必须一致——X86 5632 点、AArch64 9632 点、
   RISC-V 19512 点全部 agree。更强的证据是把生成的 `.inc` 编进 target、和原
   手写 C++ 构造函数端到端对拍（`tools/ab/`）。
3. **生成器回归（自基线）**：`tests/artifacts/` 是 gisel 自己的冻结输出，用来
   抓语料/生成器漂移。它**不是**“与上游逐字节一致”的证据：`-gen-legalizer`
   那条对照链路已随 `.td` 中间格式一起退役。

把自基线说成“与上游逐字节一致”就是越界。历史上 X86/AArch64 的 `.inc` 确实是
`llvm-tblgen -gen-legalizer` 的逐字节输出；切到 cpp 直连后这个字节 oracle 没有
了，证据换成上面第 1、2 层。

## 撤掉的工具

`.td` bootstrap reader 和 `--emit=td` 都已删除，原因与保留项见
`docs/REPORT-no-td.md`。`tools/import-cxx.py` 留在工作台（`docs/SCOPE.md` §2），
只负责把目标端 C++ 转成 `.gisel`；它不是 gisel 的运行时依赖。

`tools/refresh-oracle.sh`（调 `llvm-tblgen -gen-legalizer*` 刷新 `tests/artifacts/`）
已不再适用：产物现在由 `gisel gen` 自己生成。LLVM 分支里的 `.td` 和
`-gen-legalizer*` 因此只剩历史价值，删除它们不影响 gisel；
`docs/REPORT-cxx-corpus.md` 记录这次切换。

语料是冻结输入：改规则等于改语料，必须重新过产物门（`tests/test_artifacts.py`、
`tests/artifacts/SHA256`）。
