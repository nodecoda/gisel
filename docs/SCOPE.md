# SCOPE：gisel 是什么，不是“用 gisel 能做成什么”

这份文件是边界的唯一出处。新加一个命令、脚本或报告之前，先按这里的判定规则
归位；归类不确定就是设计没想清楚，不是文档问题。

## 1 gisel 本体

gisel 只有**两个**功能，都只读 `.gisel`（以及它自己吐出的 `.core.json`），
全程不跑 `llvm-tblgen`、不编译 LLVM、不读 LLVM 源码。

| # | 功能 | 入口 | 输入 → 输出 |
|---|---|---|---|
| 1 | **转译**：把规则文本变成规则产物 | `gen --emit={inc,check,core}`、`check`、`lint` | `.gisel` → C++ / JSON；`check` 只比对字节，`lint` 只报诊断 |
| 2 | **用例生成**：把规则空间变成有限的题 | `cases`、`domain` | `.gisel` + feature 真值表 + 轴 → 无答案查询 JSONL（等价类 / 边界 / 域外） |

具体命令、参数和退出码是规范：`spec/cli.md`。加一个命令等于加一块产品面，
两份文件（本文 + `spec/cli.md`）都得改。

配套的内部件，不单独算功能：

- `eval`：schema-0.4 正常形的求值器。它是 `cases` 的**分母自检**手段——同一份
  查询既给 evaluator 答，也给编译出来的规则答，两边必须一致。
- `graph`：读 `--emit=core` 的静态分析（商图找环）。它同样不碰 LLVM。
- `gisel/data/*.json`：opcode 槽位/arity 的**快照**，`opcode-slots.json` 记录
  冻结时的 LLVM `source_commit`。生成它要 LLVM，但 gisel 运行时只读这份随包
  数据。

## 2 工作台：用 gisel 完成的，不是 gisel 的功能

| 工具 | 做什么 | 用 gisel 的哪个出口 |
|---|---|---|
| `tools/import-cxx.py` | 一次性转录三个钉住的 legalizer C++ 构造函数 → `.gisel` | 目标端：产出 gisel 的输入 |
| `llvm-dev/tools/gisel_td.py` | `.gisel` → `.td`（给 llvm-tblgen 用） | 复用 `gisel/ast.py` 的 AST |
| `tools/refresh-oracle.sh` | 跑 `llvm-tblgen` 刷新 `tests/artifacts/` | 校验 `gen` 的字节一致 |
| `tools/ab/*` | 双 runner 构建、跑查询、对拍、归因 | `gen --emit=inc` + `cases` |
| `tools/ab/diff.py` | 对拍：比较两个答案文件，出行/JSON 报告和退出码 | 读答案文件用 `gisel.answers`；比较与退出码在本文件 |

这一层的共同特征：**输入或对照物来自 gisel 之外**（LLVM 源码、llvm-tblgen、
编译产物、另一个实现的答案）。它们是 gisel 产物的**消费者**：gisel 出 `.inc`
和无答案查询，工作台拿这两样去和 LLVM 对拍。它们证明的是“两条规则实现相同”，
不是“gisel 有这个能力”。对拍本身——比较、归因、退出码——不属于 gisel。

物理边界：`pyproject.toml` 只打包 `gisel*`，`tools/` 和 `docs/` 不随 wheel
发布。工作台脚本是仓库内的开发工具，不是产品面。

语料的来源同样按这条分：`tests/corpus/` 是**输入**，由工作台工具从上游手写的
`*LegalizerInfo.cpp` 规则转出后冻结（X86/AArch64 中途经过本项目引入的 `.td`）；
每份语料的来源和它能证明什么见 `docs/CORPORA.md`。

## 3 判定规则

新东西放哪边，只看两个问题：

1. **输入是什么？** `.gisel` 或 `.core.json` → 本体；LLVM 源码、`.td`、
   llvm-tblgen 输出、编译出的 runner → 工作台。
2. **跑不跑外部程序？** 只读文件、纯 Python → 本体；起 `llvm-tblgen`、`g++`、
   `llc`，或者比较两个实现的答案 → 工作台。

报告也按这条分：出现 `llvm-project`、`llvm-tblgen`、`runner`、`对拍`、
`A/B` 字样的，是**工作台报告**，标题和开头必须写明，不能当成 gisel 的能力
宣传。

## 4 已经发生过的越界（如实记录）

| 位置 | 越界形态 | 处置 |
|---|---|---|
| `docs/REPORT-cases.md` §6–§7 | 对拍结果住在用例生成报告里，读起来像 gisel 的能力 | 已整体搬到 `docs/REPORT-ab.md`，并在文首写明是工作台报告 |
| `gisel diff` | 对拍动词住在产品 CLI 里，和两个功能并列 | 已移出：命令和比较逻辑都在 `tools/ab/diff.py`；`gisel/answers.py` 只留读取器，供 `cases --queries` 用；`gisel` 不再有 `diff` 子命令 |
| `tools/import-cxx.py` 放在 gisel 仓库 | 容易被当成 gisel 的功能 | 不随 wheel 发布；本文第 2 节列明它是目标端工具 |
| `cases --against <llvm dump>` | 看起来像运行时依赖 LLVM | 它读的是冻结在 `tests/` 的 oracle，不是运行时依赖 |
| `eval --answers` | 为对拍加的出口 | 属于求值器本身（答案就是它的输出），归本体 |
| `gisel/answers.py` | 曾经是 `gisel/diff.py` 连同 CLI 一起 | 只留答案文件读取器；比较和命令都在工作台，依赖方向保持“工具 → 库” |

## 5 一句话

gisel 只负责“规则文本 ↔ 规则产物 / 查询”。**证明两条规则实现一致，是工作台
拿 gisel 做的事**；工作台可以反复跑、归因、修语料，但它的结论不改变 gisel 的
功能清单。
