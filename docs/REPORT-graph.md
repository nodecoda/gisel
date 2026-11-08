# `gisel graph` 实现报告

## 已交付

新增命令：

```sh
python3 -m gisel graph SOURCE --emit=core \
  [--features FEATURES] [--config CONFIG] [--json] \
  [--inject-edge] [--check-closure] [--oracle ORACLE] [--progress]
```

实现位于 `gisel/graph.py`，CLI 注册在 `gisel/cli.py`。`gisel/eval.py` 增加了
`evaluate_with_rule` 和 `rule_matches`，保留现有 `evaluate()` 签名和返回值。规范见
`spec/graph.md`，设计记录见 `docs/DESIGN-graph.md`。

图直接从 `.gisel` 生成 schema 0.4 core 文档，再交给现有 evaluator；没有读取
原型的 `x86.tables.json`，没有生成 MIR，也没有调用 `llc`、TableGen 或 LLVM。

## 验证

### 无环和注入边负控

临时夹具包含一个 `G_ADD` 终结状态和一条加宽边。命令及输出文件 SHA：

```sh
python3 -m gisel graph /tmp/gisel-followup/graph-fixture.gisel \
  --config none --json > /tmp/gisel-followup/fixture-normal.json
# rc=0
# sha256: c75b0ca0fa254f78e1dc3d893764e27ce716cb7bb58e8143a64fc60d1ea496d7
# states=3 edges=1 cycles=0

python3 -m gisel graph /tmp/gisel-followup/graph-fixture.gisel \
  --config none --inject-edge --json > /tmp/gisel-followup/fixture-inject.json
# rc=1
# sha256: 055c5d30347dd1756056411984f75b833d02fe246025b2e896b3befd2bb7a743
# states=3 edges=2 cycles=1
# injected edge: G_ADD[2] -> G_ADD[1]
```

### X86 四配置

命令：

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --json \
  > /tmp/gisel-followup/x86-all-refactor.json
# rc=0
```

输出 SHA-256：

```text
a6fa9724ba3a252fde034051d7b6df702bb956c5efd9102754bcd2c1fddf7cda
```

四个配置的真实结果如下。`outcomes` 始终包含 moves、no-rule、terminal、opaque、
outside、stuck 六个键，零值也显式打印；`terminal` 是终结动作分布。`uncovered`
始终是两个 variadic opcode，因为 bundled opcode manifest 没有固定槽数：
`G_INTRINSIC`、`G_INTRINSIC_W_SIDE_EFFECTS`。

| config | states | edges | moves | no-rule | opaque | outside | stuck | terminal | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | 73,867 | 26,767 | 26,767 | 25,695 | 1,022 | 4,168 | 0 | 16,215 | 0 |
| C1 | 73,856 | 25,895 | 25,895 | 26,520 | 1,026 | 3,159 | 0 | 17,256 | 0 |
| C2 | 73,809 | 25,464 | 25,464 | 26,573 | 1,026 | 3,167 | 0 | 17,579 | 0 |
| C3 | 73,867 | 26,639 | 26,639 | 25,690 | 1,022 | 4,000 | 0 | 16,516 | 0 |

### RISC-V：配置相关的内存类型

RISC-V 的 `mem_desc` 里，memory type 是一个配置相关的 select：

```json
{"select": {"cond": {"kind": "leaf", "name": "hasFeature", "args": ["XLen == 64"]},
            "then": "s64", "else": "s32"}}
```

旧实现把它原样放进 `set`，`gisel graph`、`gisel cases`、`gisel domain` 都会在
`TypeError: unhashable type: 'dict'` 上崩掉。现在先在候选阶段展开：不带
evaluator 的查询/domain 枚举取 `s64` 和 `s32` 的并集，`gisel graph` 再按当前
配置只保留一个分支。RISC-V corpus 因此可以完整跑通：

```sh
python3 -m gisel graph tests/corpus/RISCVLegalizerInfo.gisel \
  --features tests/cases/riscv-features.json --config rv64gc --json \
  > /tmp/gisel-followup/riscv-rv64gc.json
# rc=0, 98s
# sha256: 479074995b32123506b83a888ff47226e8b87924358608625a1a9479491aaff1
```

| config | states | edges | moves | no-rule | opaque | outside | stuck | terminal | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rv64gc | 433,321 | 38,659 | 38,659 | 322,545 | 14,458 | 7,867 | 0 | 49,792 | 0 |

同一语料的其他出口：

```text
gisel cases  --features riscv-features.json -> rc=0, 6,137 cases / 8 configs
gisel domain --features riscv-features.json -> rc=0, 2,261,368 points (282,671/config)
```

`mems=31`，说明 8 个配置的 `s32`/`s64` 分支都进了 domain 轴，没有因为入
`set` 而丢行。

### 更正：早先的 6 个自环是假环

首版曾报告 `cycles=6`，全部是自环：

| opcode | ruleset | 代表类型 | 边 |
|---|---|---|---|
| `G_UMIN` / `G_UMAX` / `G_SMIN` / `G_SMAX` | `X86_UMIN`（corpus 第 190 行） | `s3` | `WidenScalar -> s32` |
| `G_INTRINSIC_ROUNDEVEN` / `G_INTRINSIC_TRUNC` | `X86_INTRINSIC_ROUNDEVEN`（第 767 行） | `s3` | `WidenScalar -> s32` |

复算发现 `s3` 和 `s32` 被并进同一个类（该类有 41 个成员）。原因是类签名只
收集显式谓词，而这两条规则写成 `widen(slot(0), pow2_min(32))`，显式谓词为
`true`；真正区分 `s3`/`s32` 的 guard 是 `eval.shim_guard_and_newtype` 里的
`is_scalar && !is_pow2(size)`，不在谓词 DAG 里。逐点求值：

```text
G_SMAX                 s3 -> WidenScalar(s32) rule0; s32 -> Lower  rule1
G_INTRINSIC_ROUNDEVEN  s3 -> WidenScalar(s32) rule1; s32 -> Libcall rule2
```

LLVM 的 `widenScalarToNextPow2` 本身带 `sizeNotPow2` 谓词
（`X86LegalizerInfo.cpp:182`），所以真实语义是 `s3 -> s32 -> Lower/Libcall`，
终止，不存在死循环。自环是商图不是同余造成的假象。

修复方式是把每条变异规则的隐式 guard 也并入类签名（新增
`eval.rule_matches`，`evaluate()` 签名不变）。修复后 6 个自环全部消失，表里
的 states/edges/opaque 有小幅变化，oracle 仍逐点一致。

### AArch64（第二个 target，仅 baseline）

```sh
python3 -m gisel graph tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json --config baseline --json \
  > /tmp/gisel-followup/aarch64-baseline-refactor.json
# rc=0, 7m04s（旧枚举 16m05s）
# sha256: 78b05352e5e7b13b2b0b377fe7e885d2f3dae7d4c4d0579aa13eb9bbf52bc200
```

| config | states | edges | moves | no-rule | opaque | outside | stuck | terminal | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1,595,464 | 126,474 | 126,474 | 311,539 | 145,365 | 14,271 | 21 | 997,794 | 0 |

首版在同一配置上跑出 20 个 `G_CTTZ` 自环。原因是 `widen(slot(0), same_as(1))`
的 guard 依赖另一个槽，而类签名用的是基线槽类型；`s3` 和 `s8` 因此同类，
`s3 -> s8` 落回本类。`_mutation_slots` 把 `same_as(k)` 的槽号也纳入依赖后，
该轴按具体类型分开（G_CTTZ 变成 62×62=3,844 个状态），20 个自环全部消失。
`same_as` 遇到宽度未知的指针（`p0:*`）现在抛 `unknown_width`，计入 opaque，
而不是 `str > int` 崩溃。

只跑了 baseline 一个配置；另外四个配置和 `--check-closure` 没有跑，AArch64
的闭包状态属于未覆盖。AArch64 图有 159 万状态、单配置 7 分钟。把状态枚举从
“具体类型笛卡尔积”改成“类笛卡尔积 + 成员按需展开”后，耗时从 16m05s 降到
7m04s，RSS 从 1.6 GB 降到约 1.4 GB；输出 SHA 与旧实现逐字节相同
（`78b05352…`），说明状态、边和计数没有因为重构改变。剩下的主要成本是逐状态
求值，而不是枚举本身。

`--progress` 可以按 ruleset 看到进度和耗时；非 tty 默认关闭。

### Oracle 对拍

X86 C1 的完整 oracle 对拍命令：

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --config C1 \
  --oracle tests/cases/x86_ref_dump.jsonl --json \
  > /tmp/gisel-followup/x86-oracle-refactor.json
# rc=0
```

结果：`total=1408 matched=1408 agree=1408 disagree=0 errors=0 uncovered=0`，
命令返回 `rc=0`。图定位状态后仍使用同一个 `eval.Evaluator` 比较 action、
type index 和 new type，没有另写一套规则语义。

## 闭包和 outside

`--check-closure` 会枚举状态保存的全部成员，检查代表点的 winning rule、
mutation 和目标类是否对整个类一致。它不会自动细化分区。一个临时夹具把
非 2 次幂向量通过 `more(..., pow2)` 推到未声明的 lane，报告：

```text
outside=1
closure.ok=false
reason=outside
```

因此域外不再被静默 continue；它单独计入 `outside`，闭包检查也会把它作为反例。

审计本身扫描全部状态，输出只保留前 20 条样例，`count` 记录真实违规总数。
首版在累计 20 条后直接 `break`，而 X86 排在前面的违规是 `v17s32` 的
`outside`，所以 `G_SMAX` 的 `s3/s32` 规则分歧根本没被检查到；这也是假环
没有被闭包拦住的第二个原因。

完整 X86 C1 的当前结果：

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --config C1 --check-closure
# rc=1, closure=FAILED, count=3465 (stored 20)
```

构成不是单一原因：3,159 条是代表状态本身落在有限域外（`outside`），
82 条是某个成员被变异推出域外（`outside` + `mutation`），224 条是同一状态类
映射到多个目标类，例如：

```text
G_ANYEXT[1,0] -> G_ANYEXT[0,0], G_ANYEXT[6,0], G_ANYEXT[7,0]
```

多目标类的原因是 widen 的目标类型是 `pow2ceil(具体位宽)`：同一个 guard 类里
的 `s3` 和 `s33` 分别落到 `s32` 和 `s64`。这是 mutation 粒度，不是谓词粒度。
按规范默认不自动细化，`--refine` 尚未实现；因此当前的 `cycles=0` 只覆盖代表
点后继，闭包失败的状态不能拿这张图证明无环。文本输出把违例压成单行，例如：

```text
closure     : FAILED (3465 violation(s), 3 shown)
  closure: G_ANYEXT[1,0] targets=G_ANYEXT[0,0] | G_ANYEXT[6,0] | G_ANYEXT[7,0] reason=multiple target classes
```

## 与 `sim/graph.py` 的差异

- 输入从原型私有 `x86.tables.json` 改为 `.gisel -> core schema 0.4 -> eval`。
- outside 是图报告字段，并且参与闭包失败判断；原型只在 runtime fallback 路径中
  累计。
- 闭包检查位于图构建之后，对商类的全部成员审计；默认不细化分区。
- opaque、no-rule、outside、stuck 分开统计；原型的 table cell 状态更接近
  `unknown/none/outside`。
- `--inject-edge` 是命令行负控，不需要读者写 Python 片段。

## 未覆盖和限制

- variadic opcode 没有固定类型槽数，当前明确列在 `uncovered`，没有拿零槽图冒充
  完整覆盖。
- memory 轴使用 ruleset 中 `in_mem_desc` 的有限 rows；没有显式内存描述的任意
  ordering/descriptor 域不会被凭空枚举。memory type 为配置相关 `select` 时先
  按分支展开，RISC-V 的 `s32`/`s64` 两个分支都进了轴；`gisel graph` 再按配置
  收敛到一个分支。
- 状态按类的笛卡尔积枚举，成员在闭包和 oracle 定位时按需展开；这减少了重复
  状态，但不会改变类划分，也不会把未声明的具体类型凭空加进图。
- `--progress` 在每个 ruleset 结束后向 stderr 打印 `[i/N] opcode: states, 秒数`；
  非 tty 默认关闭。AArch64 的瓶颈仍是逐状态求值，不是枚举本身。
- `--refine` 尚未实现，默认分区不会被自动修改。
- AArch64 只验证了 baseline 配置；其余配置和 AArch64 的闭包审计未跑。单配置
  7 分钟、159 万状态，候选域还没有按 ruleset 收窄。
- X86 C1 的闭包审计仍有 3,465 条违例（3,159 条 outside 状态、82 条成员
  outside、224 条 `multiple target classes`）；在这些状态上后继不是类函数，
  `cycles=0` 不能外推成“整个语料无死循环”的证明。要闭合这个缺口，需要实现
  按 mutation 目标细化的 `--refine`，并重新跑四配置。
- 早先报告的 6 个“自然环”已确认是类划分漏掉隐式 guard 造成的假环，不是
  LLVM 规则的真实死循环。

