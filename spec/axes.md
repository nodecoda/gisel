# `--axes`：显式分析轴规范

`gisel cases`、`gisel domain`、`gisel graph` 接受一个旁路文件：

```sh
python3 -m gisel graph SOURCE --emit=core \
    --axes SOURCE.axes.json --config x86-64-v3 --json
```

它只影响**分析**，不进入代码生成：`gen`/`check`/`lint`/`eval` 以及
`inc`/`check`/`core` 三个出口都不读它，`tests/artifacts/*.core.json`
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
  仍写 2 元组，保持旧文件兼容。`tools/ab/diff.py`、`gisel eval` 和
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

- `cases.max_slot_values`：每个 type slot 的候选**软预算**（默认 16）。软的意思是：规则里的每个字面量及其邻居永远保留，只有域类型受它约束，
  所以单槽候选数可以超过 16（AArch64 `G_ADD` 实测 105）。`cases` 的 stats
  打印 `slot_budget` / `candidate_max` / `candidate_over_budget`。
- `cases.boundaries`：`false` 时关闭边界探测（`max_boundary_per_rule = 0`）。
- `cases.max_outside`：每个 (config, opcode) 的 outside 上限。
  `--max-outside` 显式给出时覆盖 profile。
- `domain.max_points`：大于 0 时截断输出，并在 stderr 打印截断前后数量。
- `domain.full`：本版本只支持 `true`。
- `graph.skip`：跳过 opcode；精确匹配或家族前缀匹配
  （`G_INTRINSIC` 也跳过 `G_INTRINSIC_WO_CHAIN` 等）。输出多一行 `skipped`。
- `graph.state`：可选轴只有 `["types", "mem"]`（顺序无关），写了别的轴会以
  rc=2 报错。`imm` 不需要列：只要 profile 里有 imm 轴，imm 类就自动进入状态键；
  ordering 不单独进键，它和 `mty`/`align` 一起进内存类。

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
- `profiles.graph.state` 含有 `types`/`mem` 以外的轴。

## 4. 兼容性保证

- 无 `--axes`：三个命令的输出与引入前逐字节一致。当前回归 SHA：
  - X86 四配置 `graph --features tests/cases/x86-features.json --json`
    → `38f2114e9fb688202a598dde023302b0b94e558109025477c5ef41ae275a7840`
  - RISC-V `graph --features tests/cases/riscv-features.json --config rv64gc --json`
    → `ffa98abd0599fd7f33d27972c2123faf0de6ee9ffe88452baf470ddd90d52969`
  - 与引入 `--axes` 时相比，这两个 SHA 变过一次，是刻意的：候选轴不再发明
    LLVM 构造不出来的类型——固定 1 车道向量归一成元素类型（`v1s8` → `s8`），
    float 位宽只取 16/32/64/80/128（不再有 `f31`/`f33`）。X86 C0 因此从
    73,867 state / 26,767 edge 降到 73,407 / 26,686，0 环结论不变。
- 空 profile（`{"version": 1}`）与无 profile 逐字节一致（见
  `tests/test_axes.py`）。
- `gen`/`check`/`lint`/`eval` 不接受 `--axes`；传入即 argparse rc=2。

## 5. 未覆盖

- 内存 ordering 的 AArch64 graph 全量数字尚未重跑；cases 侧四个配置合计：
  无轴 313 witnessed / 28 shadowed / 402 unexercised，只列四种原子序
  317 / 29 / 397，再加上 `NotAtomic` 是 319 / 28 / 396（`AArch64_SEXTLOAD#1`
  和 `#3` 就是被漏掉的那两条普通 load 规则）。
- `cases` 的按配置指针宽度：仍输出 `p0:*`。
- `graph` 在 derive 模式下用 `cases._candidates` 生成切点，该函数仍按 64 位解析
  规则字面量指针；`bind.pointer_width` 只作用于声明类型和 explicit 模式。
- 漂移检查是独立工具（见 §6），不是 `gisel` 子命令，也不进入 CI 默认路径；
  `graph` 的 `uncovered`/`unwitnessed` 仍然是运行时那一侧的信号。

## 6. 漂移检查

`tools/check-axes.py SOURCE --axes FILE [--features FILE] [--json] [--strict]`
只回答一个问题：这份 profile 还会不会采样到规则自己点名的值。退出码
0 = 没有缺口，1 = 有缺口，2 = 用法/解析错误。

- **type**：规则里的每个类型拼写都必须能被 profile 解析（未知名字、配置相关的
  `select` 名字都是缺口）。`derive` 模式下被 `types.remove` 删掉的字面量是缺口；
  `explicit` 模式下未列出的字面量只打 `info:`，因为显式轴本来就是有意的替换
  ——`--strict` 才把它升级成缺口。`p0:*` 这类通配指针宽度代表一族具体宽度，
  只检查可解析性，不要求出现在值集里。
- **mem**：`(mty, align)` 行同样分 derive/explicit；derive 下被 `mems.remove`
  删掉是缺口。
- **imm**：`imm(i) == N`、`in(imm(i), [...])` 里的每个字面量都必须在采样值里；
  `imm(i) < N` 这类阈值要求采样值在两侧都有，否则比较只有一个分支被走到。
- **ordering**：每条 `mem_ordering` / `mem_failure_ordering` 比较都必须有一个
  满足它的采样值；当序格上存在不满足的值时，也必须有一个不满足的采样值。

ordering 这条不是吹毛求疵：`mems.orderings` 一写就是**替换**默认的
`[("NotAtomic", "NotAtomic")]`。只列 `[Unordered, Acquire, Release,
SequentiallyConsistent]` 时 `mem_ordering >= Unordered` 恒为真，普通非原子
load 规则就再也不会被见证——工具会直接把这句话打出来。

无 profile（派生轴）时 X86 / RISC-V / WebAssembly / M68k 都是 0 缺口，因为
`_candidates` 保证规则字面量一定在候选集里。AArch64 是例外：它的规则读了
ordering，而派生轴默认只有 `NotAtomic`，工具报 4 条 `is never true`。这正是
“没显式声明轴”的代价，不是误报。
