# CLI 契约

这是 gisel 产品面的规范：哪些命令存在、各自的输入输出、退出码。边界（什么
不算 gisel 的功能）见 `docs/SCOPE.md`。

## 1 命令表

gisel 只有这七个命令。新增一个命令等于新增一块产品面，必须先改本文。

| 命令 | 做什么 | 输入 | 输出 |
|---|---|---|---|
| `gen` | 把规则文本发射成一种产物 | 源文件、`--emit`、`--out` | 产物文件；stdout 一行统计 |
| `check` | 产物是否与源文件一致 | 源文件、`--emit`、`--against` | 一致时 stdout 一行；不一致时 stderr 输出 unified diff |
| `lint` | 静态检查，不产生产物 | 源文件、可选 `--manifest` | stderr 诊断，stdout 汇总（`--json` 时是机器可读汇总） |
| `cases` | 生成无答案的测试查询 | 源文件或 `--corpus NAME`、`--features`、可选 `--axes`/`--queries`/`--oracle`/`--ruleset` | 查询 JSONL 文件；stdout 统计 |
| `domain` | 枚举无答案查询域（笛卡尔积） | 源文件或 `--corpus NAME`、可选 `--features`/`--axes` | 查询 JSONL 文件 |
| `eval` | 用 schema-0.4 正常形回答查询 | `--doc`、`--features`、`--cases` | 汇总或 `--answers OUT` 的答案 JSONL |
| `graph` | 在类型×类空间上建商图并找环 | 源文件、`--emit=core` | stdout 报告（`--json` 可机读） |

`--emit` 的三个值对应三类产物，后缀只是约定：`inc`（C++ 链）、`check`
（JSON）、`core`（schema-0.4 JSON）。`table`（C++ 表）已于 2026-11-09 移除，
见 `spec/m3-scope.md`。

`check` 比较的是**产物形**，不是源文件的 builder 边界：`--emit=check` 与
`--emit=core` 在生成前先做 `canonicalize_rulesets`（同一 opcode 的多条
builder 链按文档顺序拼成一张表）；`--emit=inc` 保留源文件的 builder 边界，
因为那正是手写 C++ 构造函数的形状。因此同一份 `.gisel` 在 `check`/`core` 与
`inc` 下的 ruleset 数可能不同（X86 是恒等；AArch64 117→114、RISC-V 96→91），
这不是漂移，是契约。`lint` 的行号始终指向源文件。

`cases` 与 `domain` 产出的是**问题**，不是答案文件；答案由外部 legalizer 或
`eval` 给出，比较命令在工作台（`ab/diff.py`）。

`domain --json` 打印的统计必须能复算分母：`raw_points`（截断前）、`truncated`、
`points`（写盘行数）、`shape_dropped`/`shape_dropped_total`（被形状过滤丢掉的
**类型元组**，不是查询）、`skipped_opcodes`（连槽表都不知道 arity 的 opcode，
目前只有 `G_INTRINSIC*`）。形状过滤发生在 mem/imm 乘积之前，所以一个被丢掉的
元组本来会变成 `len(mem_axis) × len(imm_tuples)` 条查询——单位必须写在字段名
和文档里，否则分母不可复算。

`cases --ruleset NAME`（可重复）只生成指定 ruleset 的查询；`NAME` 可以是
`.gisel` 里的 `ruleset` 名，也可以是它挂的 opcode。名字拼错是用法错误（退出码
2），不是“这个 ruleset 没有查询”。大 target 用这个参数分块跑，块之间按
ruleset 不重叠。

`cases` 与 `domain` 还接受 `--corpus NAME` 代替位置参数：名字取自随包发布的
`gisel/data/corpora.json`（`x86 aarch64 riscv arm mips ppc m68k wasm spirv`），
展开成一个 `.gisel` 加配套的 `--features`/`--axes`。它是纯粹的糖：同一 target
用 `--corpus` 和用两个显式路径必须写出逐字节相同的文件。同时给位置参数和
`--corpus` 是用法错误（退出码 2），不猜哪个赢；名字拼错同样退出 2，并列出
可选名字。

捆绑语料的**规范副本**在 `tests/corpus`、`tests/cases`：冻结产物把
`tests/corpus/...` 记成每条规则的出现位置，所以目录布局不动。wheel 里带的是
`gisel/data/corpus`、`gisel/data/cases` 下的逐字节副本，由
`tools/sync-package-data.py` 生成；CI 用 `--check` 挡住漂移，副本与 checkout
不一致就失败。这样 `pip install gisel` 之后不需要 checkout 也能直接出题。

## 2 退出码

所有命令共用这三个码，没有别的：

| 码 | 含义 | 例子 |
|---:|---|---|
| 0 | 成功 | 产物已写出；`check` 一致；`lint` 无 error；`graph` 无环 |
| 1 | 输入合法，但结论是“否” | `check` 产物过期；`lint` 有 error；`eval` 对不上；`graph` 有环或闭包不成立 |
| 2 | 无法开始 | 用法错误、文件读不到、语法错误、manifest/特性表坏了、写盘失败 |

`2` 不是“结论是否定”的意思：它表示这次运行没有完成，结论无意义。脚本里
应该把 `2` 当失败处理，并且不要把它归因成规则差异。

## 3 全局约定

- **不调用外部程序**：不跑 `llvm-tblgen`、编译器、`llc`；不联网。唯一的
  外部依赖是随包发布的 `gisel/data/`（槽表、契约与捆绑语料）。
- **确定性**：同样的输入产生逐字节相同的输出。没有时间戳、随机数或字典序
  之外的隐式排序；`gen` 的产物可以直接进 `check`。
- **流分离**：结论/产物走 stdout（`gen` 写文件），人类可读的诊断走 stderr。
  `--json` 只改变 stdout 的形态，不改变退出码。
- **源文件是唯一输入**：产物的内容不依赖文件名。
- **不做的事**：不生成 MIR/LLVM IR，不执行 legalizer，不修改被检查的源文件。

## 4 版本

`gisel --version` 打印 `gisel <package version>`，版本只有一个来源：
`gisel/__init__.py` 的 `__version__`，打包元数据从它读取。`--version` 不读
文件、不构造解析器之外的任何对象，可以在任何目录运行。
