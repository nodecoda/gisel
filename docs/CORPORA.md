# 语料：为了自证，预先做的准备

`tests/corpus/*.gisel` 不是 gisel 的运行前提，而是**项目为了证明自己、预先做的
准备**：我们用自己的工具解析 LLVM 里的手写规则，提取出来写成 `.gisel`，然后
冻结。LLVM 的文件是输入，`.gisel` 是我们的产物。

## 上游到底把规则写在哪

上游 LLVM main 里**没有** legalizer 的 `.td`，`llvm-tblgen` 也没有
`-gen-legalizer`。所有 target 的合法化规则都写在 `*LegalizerInfo.cpp` 的构造
函数里（`getActionDefinitionsBuilder(...)` 链）：X86、AArch64、RISC-V 都一样。

我们的 LLVM 分支加了两样东西：

- `include/llvm/Target/LegalizerInfo.td` + `utils/TableGen/LegalizerInfoEmitter.cpp`
- `llvm-tblgen -gen-legalizer{,-core,-check,-table}`

所以 X86/AArch64 的 `.td` **是我们引入的中间格式**，由手写 C++ 链逐条重述而来
（文件头写着 “Converted from the former hand-written chains ... reviewed rule by
rule”）。RISC-V 没走这条中间格式，直接从 C++ 提取。

## 链路

```text
上游 X86/AArch64LegalizerInfo.cpp（手写 builder 链）
  -> 我们的 .td（逐条重述）
  -> gisel_td.py bootstrap -> .gisel
  -> gisel_td.py gen       -> .td（与重述版逐字节相同）
  -> llvm-tblgen -gen-legalizer -> .inc

上游 RISCVLegalizerInfo.cpp（手写 builder 链）
  -> tools/import-cxx.py -> .gisel
```

| 语料 | 上游规则在哪 | 我们的提取路径 | 冻结对照物 | 能证明 |
|---|---|---|---|---|
| X86 | `X86/GISel/X86LegalizerInfo.cpp` | cpp → 我们的 `.td` → bootstrap → `.gisel` | 我们的 `-gen-legalizer*` 输出 | 生成器保真（Python vs 我们的 C++ emitter） |
| AArch64 | `AArch64/GISel/AArch64LegalizerInfo.cpp` | 同上 | 同上 | 同上 |
| RISC-V | `RISCV/GISel/RISCVLegalizerInfo.cpp` | cpp → `tools/import-cxx.py` → `.gisel` | 没有 emitter；gisel 自己的输出（**自基线**） | 生成器回归；行为靠编译对拍 |
| M68k | `M68kLegalizerInfo.cpp` | 人工转写（探针，13 条） | 无 | 语法可表达性 |
| WebAssembly | `WebAssemblyLegalizerInfo.cpp` | 人工转写（探针，108 条） | 无 | 语法可表达性 |

## 两层证据，别混

1. **生成器保真（字节门）**：同一份 `.td`，gisel 的
   `--emit={inc,check,table,core}` 和我们的 C++ `-gen-legalizer*` 必须逐字节
   一致。它证明 Python 实现没有偏离 C++ emitter；**不**证明 C++ emitter 或
   规则本身和上游行为一致。
2. **规则保真（行为门，工作台）**：把生成的 `.inc` 编进 target，和原手写 C++
   构造函数在同一批查询上对拍。这一步才是“规则没抄错”的证据，属于工作台
   （`tools/ab/`、differential 测试），不属于 gisel。

RISC-V 没有上游 emitter，所以只有第 2 层能对上游负责；它的冻结产物只是第 1 层
的自基线。把自基线说成“与上游逐字节一致”就是越界。

要证明“新规则也能表达”，需要一份不来自上游的独立手写规则集。目前没有，本文
不假装有。

## 撤掉的工具

`.td` bootstrap reader 和 `--emit=td` 都已删除，原因与保留项见
`docs/REPORT-no-td.md`。`tools/import-cxx.py` 留在工作台（`docs/SCOPE.md` §2），
只负责把目标端 C++ 转成 `.gisel`；它不是 gisel 的运行时依赖。

语料是冻结输入：改规则等于改语料，必须重新过产物门（`tests/test_artifacts.py`、
`tests/artifacts/SHA256`）。
