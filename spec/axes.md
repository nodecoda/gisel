# `--axes`：显式分析轴规范

`gisel cases`、`gisel domain`、`gisel graph` 接受一个旁路文件：

```sh
python3 -m gisel graph SOURCE --emit=core \
    --axes SOURCE.axes.json --config x86-64-v3 --json
```

它只影响**分析**，不进入代码生成：`gen`/`check`/`lint`/`eval` 以及
`inc`/`check`/`table`/`core` 四个出口都不读它，`tests/artifacts/*.core.json`
保持冻结。没有 `--axes` 时，三个命令的行为与引入本文件之前逐字节一致。

文件解决的是“同一个 target 的类型/内存值集被三个后端各自重新推导”的问题：
值集只声明一次，采样方式留在各命令自己的 profile 里。

## 1. Schema（version 1）

```json
{
  "version": 1,
  "types": {
    "mode": "derive",
    "values": [],
    "add": ["s16"],
    "remove": ["s3"]
  },
  "mems": {
    "mode": "derive",
    "rows": [["s8", "p0:64", "s8", 8]],
    "remove": [],
    "orderings": [],
    "failure_orderings": []
  },
  "imms": {"0": [8, 16, 32]},
  "bind": {
    "configs": "tests/cases/x86-features.json",
    "pointer_width": {"rv32gc": 32, "rv64gc": 64},
    "extended": {"C0": false}
  },
  "profiles": {
    "cases": {"max_slot_values": 16, "boundaries": true, "max_outside": 2},
    "domain": {"full": true, "max_points": 0},
    "graph": {"state": ["types", "mem"], "skip": ["G_INTRINSIC"]}
  }
}
```

顶层只允许 `version/types/mems/imms/bind/profiles`。`version` 必须是 `1`。

### types / mems

- `mode: "derive"`（默认）先使用命令现有的推导结果，再执行 `add`/`rows`
  追加和 `remove` 删除。
- `mode: "explicit"` 用 `values`（types）或 `rows`（mems）**替换**推导结果；
  `types.values` 在 explicit 模式下必填。
- type 值可以是源文件里声明的 `type`/`select` 名字，也可以是规范 LLT
  （`s16`、`p0:64`、`v4s8` 等）。`select` 名字是配置相关类型，必须写出具体的
  分支 LLT，不能直接把整个 `select` 当作一个值。
- mem 行沿用 `mem_desc(t0, t1, mty, align)` 四元组；只有 `mty` 和 `align`
  进入查询，`t0/t1` 参与规则匹配。

### imms

`imms` 的 key 必须是规则里真实读取的 `imm(i)` 下标，值必须是 int 列表；
profile 给某个下标的值会**替换**该下标的推导值。

`cases` 和 `domain` 默认从规则自身的字面量推导 imm 值：`imm(0) == 32`、
`in(imm(0), [8, 16])` 给出 `{8, 16, 32}`，再补 `0` 和每个字面量的 `±1`。
因此 `G_SEXT_INREG` 这类规则现在会被真正执行，而不是统计成 unexercised。
单个 ruleset 的 imm 组合上限为 32，超出时按排序后的前 32 个值取样。

`graph` 不默认发明 imm 值：没有 `--axes` 提供该下标时，读 imm 的 opcode 写入
`uncovered`（不是把每个状态算成 `opaque`）。提供 axis 后，imm 进入状态键：

```text
(opcode, type_class_0, ..., mem_class?, imm_class?)
```

imm 类由“只读 imm 的谓词”的取值向量划分；同时读类型/内存和 imm 的谓词会把
每个 imm 点单独成类（保守但不会误并）。

### orderings

`mems.orderings`/`failure_orderings` 必须是已知标签（`NotAtomic`、`Unordered`、
`Monotonic`、`Acquire`、`Release`、`AcquireRelease`、
`SequentiallyConsistent`）。声明 `orderings` 就开启这个轴：

- 采样点是 `(ordering, failure_ordering)` 的笛卡尔积；`failure_orderings`
  缺省为 `["NotAtomic"]`。
- `cases`/`domain` 只对**读取 `mem_ordering`/`mem_failure_ordering` 的
  ruleset** 乘上 ordering 点；不读 ordering 的 ruleset 行为不变。
- 导出的查询 `mem` 变成 4 元组
  `[mty, align, ordering, failure_ordering]`；默认 `NotAtomic/NotAtomic`
  仍写 2 元组，保持旧文件兼容。`gisel diff`、`gisel eval` 和
  `tools/ab` 的两个 C++ runner 都接受两种形状。
- `graph` 在没有 `mems.orderings` 时把读 ordering 的 opcode 写入
  `uncovered`，不把状态算成 `opaque`；提供 axis 后 ordering 进入内存值的
  第 3/4 位，内存类按谓词取值划分。

### bind

- `bind.configs`：特征真值表路径，相对 profile 文件所在目录解析。命令行显式
  给出 `--features` 时以命令行为准。
- `bind.pointer_width`：按配置给出指针宽度；`domain` 和 `graph` 按配置使用它，
  缺省回退 `--pointer-width`。`cases` 仍以 `p0:*` 通配符生成，由下游 runner
  按配置解析。
- `bind.extended`：按配置覆盖 `LLT::getUseExtended()`；`cases`/`domain`/`graph`
  在绑定后应用。未列出的配置沿用真值表。

### profiles

- `cases.max_slot_values`：每个 type slot 的候选上限（默认 16）。
- `cases.boundaries`：`false` 时关闭边界探测（`max_boundary_per_rule = 0`）。
- `cases.max_outside`：每个 (config, opcode) 的 outside 上限。
  `--max-outside` 显式给出时覆盖 profile。
- `domain.max_points`：大于 0 时截断输出，并在 stderr 打印截断前后数量。
- `domain.full`：本版本只支持 `true`。
- `graph.skip`：跳过 opcode；精确匹配或家族前缀匹配
  （`G_INTRINSIC` 也跳过 `G_INTRINSIC_WO_CHAIN` 等）。输出多一行 `skipped`。
- `graph.state`：本版本只支持 `["types", "mem"]`（顺序无关）；`imm`/`ordering`
  尚未进入状态键，写了会以 rc=2 报错，而不是静默忽略。

## 2. 三个命令如何使用同一个值集

| 命令 | 值集来源 | 采样方式 |
|---|---|---|
| `cases` | `axes.apply_types` / `axes.apply_mems` 作用于 `_candidates` / `_mem_candidates` | 等价类见证、阈值边界、outside 探测 |
| `domain` | `domain.effective_axes(source, width, axes)` | 类型 × mem × 配置全积（或 `max_points`） |
| `graph` | 同一份 `domain.effective_axes`；explicit 模式下不再追加 `_candidates` 的切点 | 商类状态 + 三色 DFS |

`graph` 在 `derive` 模式下仍会追加规则切点和哨兵类型（环检测需要它们作为
代表点）；`explicit` 模式下候选轴就是 profile 的值集，规则用到但未声明的
类型不会被偷偷加回来——它们会表现为 `outside`/`opaque`，这是有意的漂移信号。
`--oracle` 的类型仍作为诊断输入追加，以便逐点对齐。

## 3. 错误处理

任何 schema 或绑定错误都以 `gisel <cmd>: <path>: <message>` 打到 stderr，
退出码 2。包括：

- 未知顶层/子层字段、非法 `version`、非法 `mode`；
- type 不能被解析，或引用了配置相关的 `select` 名字；
- mem 行不是四元组、align 不是整数；
- `imm` 下标没有出现在任何谓词里；
- `bind.pointer_width` / `bind.extended` 引用了真值表里不存在的配置；
- `profiles.graph.state` 含有尚未实现的轴。

## 4. 兼容性保证

- 无 `--axes`：三个命令的输出与引入前逐字节一致。当前回归 SHA：
  - X86 四配置 `graph --features tests/cases/x86-features.json --json`
    → `a6fa9724ba3a252fde034051d7b6df702bb956c5efd9102754bcd2c1fddf7cda`
  - RISC-V `graph --features tests/cases/riscv-features.json --config rv64gc --json`
    → `479074995b32123506b83a888ff47226e8b87924358608625a1a9479491aaff1`
- 空 profile（`{"version": 1}`）与无 profile 逐字节一致（见
  `tests/test_axes.py`）。
- `gen`/`check`/`lint`/`eval` 不接受 `--axes`；传入即 argparse rc=2。

## 5. 未覆盖

- 内存 ordering 的 AArch64 graph 全量数字尚未重跑；cases 侧已确认 8 条
  ordering 规则中 6 条从 unexercised 变为 witnessed。
- `cases` 的按配置指针宽度：仍输出 `p0:*`。
- `graph` 在 derive 模式下用 `cases._candidates` 生成切点，该函数仍按 64 位解析
  规则字面量指针；`bind.pointer_width` 只作用于声明类型和 explicit 模式。
- `graph` 的 `state` 轴选择：只支持 `types` + `mem`；`imm`/`ordering` 未实现。
- 显式轴的漂移检查（profile 漏掉规则使用的类型/imm/ordering 时自动失败）
  尚未做成独立工具；目前靠 `outside`/`opaque` 计数和 `--oracle` 暴露。
