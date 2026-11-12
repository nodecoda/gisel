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
  -> upstream-source/import/import-cxx.py -> .gisel
  -> gisel gen --emit={inc,check,core}
```

`upstream-source/import/import-cxx.py` 是**一次性转录工具**，不是通用 C++ 解析器：它只认这三种
构造函数用到的那一小撮写法，认不出来就带行号拒绝（rc=1），绝不静默丢规则。

`--all` 还会在语料目录写 `tests/corpus/import-report.json`：9 个 target 的源文件
sha、`.gisel` sha、rulesets/rules 计数、全量 refused/skipped/ignored/opaque。
生成文件头注释只保留前 40 条 refusal，report **不截断**；`import-cxx --all --check`
同时比 `.gisel` 与 report，`ab/tests/test_import_report.py` 再把 report 的
`corpus_sha256` 钉回随仓发布的语料。
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
| `G_CTPOP` 增加 VPOPCNTDQ 的向量 legal | 上游还没有这条规则（PR #235976），语料先带上向量 legalization，端到端 A/B 里这些点是 Legal |

这两条偏离**只相对于 pin**。`PIN.json` 的 `patches` 记录了仓库叠加的 6 个
PR（#237753、#238306、#238277、#235976、#237650、#239136）；其中 #237753 和
#238306 已在 2026-11 合入上游，但 pin 仍停在它们之前，所以照样要带。工作台
构建的官方侧应当是 `pin + patches`。所以偏离后的语料和官方侧行为一致：X86 端到端 3,019/3,019、
AArch64 12,559/12,559、RISC-V 6,086/6,086 全部 agree（题面为 2026-11-11
计数，答案证据在 `ab/EVIDENCE.json`）。等这些 PR 合入上游，
把 `commit` 前移，偏离函数会按设计**报错**（它断言旧文本还在），那时删掉它们
即可——这正是它存在的意义。

这条前提是机器检查的，不是注释：每个 `build-*-runner.sh` 编译前先跑
`ab/check-pin.sh TREE`，它**按内容**比对 `PIN.json` 的 `official_base.files`——
12 个能改答案的文件的 sha256。官方侧冻结在 `trees/explore` @ `700e551714cc` /
`builds/explore`，与 pin 的三条偏离（AArch64 `numElements()` 硬化、
`memSizeInBytesNotPow2` 的可伸缩读取、`core*` builder）逐条登记在
`official_base.deviations` 里；详见 `ab/docs/OFFICIAL-BASE.md`。

2026-11-11 之前这里只查祖先关系，于是 fork 上未声明的改动（AArch64 的
`numElements()` 断言硬化）混进了官方侧而检查仍报 ok：祖先检查只能证明“pin 和
patch 都在”，不能证明“没有别的改动”。现在内容不一致就 rc=1 并打印是哪个提交
改的。换基线 = 重跑全部证据，成本写在 `ab/docs/OFFICIAL-BASE.md`。

`git log` 里看到那两个 X86 修复**不**代表上游已合——它们只在
`explore/06-review-fixes` 上，`origin/main` 没有。真的合入后，动 `PIN.json` 的
`commit` 和 `patches`，偏离断言和内容检查会一起逼你把两边都改对。确知树是
rebase 过的镜像可用 `GIT_DSL_SKIP_PIN_CHECK=1`。

## 复现：一条命令，钉住计数

导入器是**一次性转录工具**，不是通用 C++ 解析器：目标写死在 `TARGETS` 里
（X86 / AArch64 / RISCV / M68k / WebAssembly / PowerPC / ARM / Mips / SPIRV），
路径和规则数也在那里，认不出的语句带行号拒绝。重新生成并逐字节对照仓库里的语料：

```sh
GS_X86_SRC=.../X86LegalizerInfo.cpp \
GS_AARCH64_SRC=.../AArch64LegalizerInfo.cpp \
GS_RISCV_SRC=.../RISCVLegalizerInfo.cpp \
GS_M68K_SRC=.../M68kLegalizerInfo.cpp \
GS_WEBASSEMBLY_SRC=.../WebAssemblyLegalizerInfo.cpp \
GS_POWERPC_SRC=.../PPCLegalizerInfo.cpp \
GS_ARM_SRC=.../ARMLegalizerInfo.cpp \
GS_MIPS_SRC=.../MipsLegalizerInfo.cpp \
GS_SPIRV_SRC=.../SPIRVLegalizerInfo.cpp \
  python3 ../upstream-source/import/import-cxx.py --all --check \
    --pin ../upstream-source/pin/PIN.json
```

`--check` 只比对、不写盘；任一目标计数漂移或文本不同都返回 1。生成的 `.gisel`
头部记录源文件的 sha256，所以“这份语料来自哪份 cpp”不靠记忆。只跑一个目标：

```sh
python3 ../upstream-source/import/import-cxx.py X86 .../X86LegalizerInfo.cpp \
    --out tests/corpus/X86LegalizerInfo.gisel
```

钉住的基线（源 sha256 / 规则集 / 规则）：

| 目标 | 源 sha256（前 12 位） | rulesets | rules |
|---|---|---:|---:|
| X86 | `79f2376096c3` | 63 | 328 |
| AArch64 | `2b5377c3eedd` | 117 | 741 |
| RISC-V | `ad529e1f1a9e` | 96 | 402 |
| M68k | `f796bb977e0b` | 6 | 13 |
| WebAssembly | `c6409b1d4eb1` | 29 | 109 |
| PowerPC | `4ca6a62b6f43` | 15 | 25 |
| ARM | `b86441eb03f4` | 52 | 96 |
| Mips | `3660b66b709c` | 48 | 95 |
| SPIRV | `e404ba675047` | 83 | 353 |

表里的 `rules` 是 `gisel lint`/`ast.parse_program` 解析到的规则数。AArch64 的
importer `TARGETS` 断言 744 条 builder call，其中 3 条（`replace(...)` /
`clamp_max(...)`）只改类型集合、不生成独立规则，所以入库语料解析为 741 条；
`import-cxx --check` 比较的是生成文本的字节，不是这个计数。

换上游修订不是改参数，而是改工具：计数断言会立刻报 `DRIFT`。

`pred`/`select`/`feature` 的名字经过一轮人工审阅（LLM 提议、表里冻结）：
C++ 里有名字的沿用，匿名的按语义命名，单 feature 条件直接内联进 `select`。
残留的 `X_selN` / `X_condN` 会被测试拦下。详见
`docs/REPORT-cxx-corpus.md` §3b。

| 语料 | 上游规则在哪 | 我们的提取路径 | 证据 | 能证明 |
|---|---|---|---|---|
| X86 | `X86/GISel/X86LegalizerInfo.cpp` | cpp → upstream-source import → `.gisel` | 转录 check + gisel 自基线 + 端到端 A/B | 生成器回归；规则保真靠 `ab/` |
| AArch64 | `AArch64/GISel/AArch64LegalizerInfo.cpp` | 同上 | 同上 | 同上 |
| RISC-V | `RISCV/GISel/RISCVLegalizerInfo.cpp` | 同上 | 同上 | 同上 |
| M68k | `M68k/GISel/M68kLegalizerInfo.cpp` | cpp → upstream-source import → `.gisel` | gisel 自己的输出 + 41 条端到端对拍 | 生成器回归；规则保真靠 `ab/run-m68k-end-to-end.sh` |
| PowerPC | `PowerPC/GISel/PPCLegalizerInfo.cpp` | cpp → upstream-source import → `.gisel` | gisel 自己的输出 + 98 条端到端对拍 | 生成器回归；规则保真靠 `ab/run-ppc-end-to-end.sh` |
| WebAssembly | `WebAssembly/GISel/WebAssemblyLegalizerInfo.cpp` | cpp → upstream-source import → `.gisel` | gisel 自己的输出 + 886 条端到端对拍 | 生成器回归；规则保真靠 `ab/run-wasm-end-to-end.sh` |
| ARM | `ARM/ARMLegalizerInfo.cpp` | 同上 | gisel 自己的输出 + 1,614 条端到端对拍 | 生成器回归；规则保真靠 `ab/run-arm-end-to-end.sh` |
| Mips | `Mips/MipsLegalizerInfo.cpp` | 同上 | gisel 自己的输出 + 1,656 条端到端对拍 | 生成器回归；规则保真靠 `ab/run-mips-end-to-end.sh` |
| SPIRV | `SPIRV/SPIRVLegalizerInfo.cpp` | 同上 | gisel 自己的输出 + 5,136 条端到端对拍 | 生成器回归；规则保真靠 `ab/run-spirv-end-to-end.sh`（4 条两侧都断言，`--expect-unanswerable 4`） |

## 证据分三层，别混

1. **转录保真（语料层）**：`upstream-source/import/import-cxx.py` 从 C++ 构造函数转录，0 拒绝，
   并且重新导入能逐字节复现 gisel 仓库里的 `.gisel`
   （`upstream-source/import/tests/test_import_cxx.py`）。
   有偏离的地方在工具里点名，不是暗改。
2. **规则保真（行为门，工作台）**：`gisel cases` 生成无答案查询，
   `ab/` 把它同时喂给官方构建和 include 了我们 `.inc` 的构建，比较两侧
   的答案流。这是端到端证据，不经过任何中间表。
3. **生成器回归（自基线）**：`tests/artifacts/` 是 gisel 自己的冻结输出，用来
   抓语料/生成器漂移。它**不是**“与上游逐字节一致”的证据。

`tests/cases/*_ref_dump.jsonl` 及其 `EvaluatorCorpus` 门禁已于 2026-11-10
删除。那批“参考实现 → 冻结答案 → 用 gisel 复算”的表是 table 时代的取巧，
方向是反的；现在只认 `c++ → gisel`，证据只保留上面三层。

## 撤掉的工具

`.td` bootstrap reader 和 `--emit=td` 都已删除，原因与保留项见
`docs/REPORT-no-td.md`。`import-cxx.py` 已迁到独立仓库 `upstream-source/import/`（`docs/SCOPE.md` §7），
只负责把目标端 C++ 转成 `.gisel`；它不是 gisel 的运行时依赖。gisel 里只留一个
release 的转发 shim。

`tools/refresh-oracle.sh` 直接调 `gisel gen --emit={inc,core,check}` 刷新
`tests/artifacts/`。它不再碰 `llvm-tblgen -gen-legalizer*`，因为那套后端和它读的
`.td` 已经删除；冻结产物是 gisel 自己的输出（漂移基线），不是第二个实现。
`docs/REPORT-cxx-corpus.md` 记录这次切换。

语料是冻结输入：改规则等于改语料，必须重新过产物门（`tests/test_artifacts.py`、
`tests/artifacts/SHA256`）。
