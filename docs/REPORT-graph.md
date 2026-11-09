# `gisel graph` 实现报告

## 快照

本报告的每个数字都绑定这棵树：

```text
commit   e44fc0d   (2026-11-10)
version  gisel 0.3.0
targets  X86 / AArch64 / RISC-V corpus at tests/corpus/PIN.json
```

换一棵树重跑，states/edges/opaque/outside 会变。每节的命令都可以原样重放，
`--json` 的输出是对整份 stdout 取 SHA-256。命令都在仓库根目录执行。

```sh
python3 -m gisel graph SOURCE --emit=core \
  [--features FEATURES] [--config CONFIG] [--json] \
  [--inject-edge] [--check-closure] [--oracle ORACLE] [--progress]
```

图直接从 `.gisel` 生成 schema 0.4 core 文档再交给 evaluator；不读原型的
`x86.tables.json`，不生成 MIR，不调用 `llc`/TableGen/LLVM。规范见
`spec/graph.md`，设计记录见 `docs/DESIGN-graph.md`。

## 1 无环和注入边负控

夹具：`G_ADD` 把 `s3` 加宽到 `S32`，`S32` legal、`S64` lower。

```sh
cat > /tmp/gisel-graph-report/fixture.gisel <<'GI'
type S32 = LLT::scalar(32)
type S64 = LLT::scalar(64)

ruleset G_ADD: G_ADD
    legal in(slot(0), S32)
    lower in(slot(0), S64)
    widen(slot(0), ty(S32))
GI

python3 -m gisel graph /tmp/gisel-graph-report/fixture.gisel \
  --config none --json > /tmp/gisel-graph-report/fixture.json
# rc=0  states=4 edges=1 cycles=0
# sha256 19fa888162e09bd1f06bf8401730b81d7b3eb0a89bfba246e005bbcac158017c

python3 -m gisel graph /tmp/gisel-graph-report/fixture.gisel \
  --config none --inject-edge --json > /tmp/gisel-graph-report/fixture-inject.json
# rc=1  states=4 edges=2 cycles=1
# injected: G_ADD[3] -> G_ADD[1]（原边 1 -> 3 的反向）
# sha256 ca478513691faadae24ec99b9c051eb2addc40bb551fb4aa508db930263abebe
```

注入边是必需的负控：没有它，“0 环”可能只是 DFS 没跑到。

## 2 X86 四配置

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --json > /tmp/graph-x86.json
# rc=0, 72.6 s, 425 MB RSS
# sha256 3639cfc0cbd57c9ce930bc7d8d42a0bd42d0112eb0c60dcfd9e7f19146c2d829
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | 77,231 | 26,731 | 26,731 | 37,478 | 7,923 | 1,016 | 4,083 | 3,985 | 0 |
| C1 | 77,220 | 25,869 | 25,869 | 38,421 | 8,844 | 1,020 | 3,066 | 3,974 | 0 |
| C2 | 77,152 | 25,457 | 25,457 | 38,282 | 9,311 | 1,020 | 3,082 | 4,021 | 0 |
| C3 | 77,231 | 26,603 | 26,603 | 37,473 | 8,224 | 1,016 | 3,915 | 3,985 | 0 |

`uncovered` 始终是两个 variadic opcode：`G_INTRINSIC`、`G_INTRINSIC_W_SIDE_EFFECTS`
（bundled opcode manifest 没有固定槽数）。

## 3 X86 C1 的闭包审计

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --config C1 \
  --check-closure --json > /tmp/graph-x86-c1-closure.json
# rc=1, 22.3 s
# sha256 337c6b520ee344b4c33e79d12b752fcf6396f00228807144edf62eb6fceffbdd
```

| 指标 | 值 |
|---|---:|
| states | 77,220 |
| closure.ok | false |
| closure.count | 321 |
| kinds.partition | 228 |
| kinds.outside | 93 |
| cycles（代表点商图） | 0 |

321 的构成：

- `partition`：同一类里的成员落到多个目标类（集中在 `G_ANYEXT` 等按宽度走不同
  `changeTo` 的规则）；
- `outside`：同一类里既有成员在域内、又有成员被推到声明域外。

`--check-closure` 的语义在 2026-11-10 改过（见 `spec/graph.md` §负控和闭包）：
它现在审计**每个非 opaque 状态的全部成员**，不再只审计有出边的代表点；域外
判定统一到 `graph.Domain.successor`。因此本表与 2026-11-08 的“3,465 条
multiple target classes”不可直接比较——旧数字按状态计，新数字只计混合类。

**`cycles=0` 的前提**：只在代表点商图上成立。完整的无环证明需要
`--check-closure` 通过；当前它不通过，所以结论应写成“代表点商图上没有环，
闭包未成立”。这不是 LLVM 的死循环，是分区/覆盖面尚未补齐。

## 4 RISC-V：配置相关的内存类型

RISC-V 的 `mem_desc` 里，memory type 是一个配置相关的 `select`
（`XLen == 64 ? s64 : s32`）。旧实现把它原样放进 `set` 的 key，`graph`/`cases`/
`domain` 都会在 `TypeError: unhashable type: 'dict'` 上崩掉；现在按配置展开。

```sh
python3 -m gisel graph tests/corpus/RISCVLegalizerInfo.gisel \
  --features tests/cases/riscv-features.json --config rv64gc --json \
  > /tmp/graph-riscv.json
# rc=0, 2m53s
# sha256 a9c46c4422f72da62bf430213b965987b8545024c8db8d70d6c517f3f70f798c
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rv64gc | 585,652 | 42,895 | 42,895 | 443,249 | 62,187 | 29,175 | 8,146 | 8,551 | 0 |

`uncovered = ['G_SEXT_INREG', 'G_INTRINSIC', 'G_INTRINSIC_W_SIDE_EFFECTS']`
（imm 轴或 variadic 槽数未给定）。`--check-closure` 在 RISC-V 上没有跑，属于
未覆盖。

## 5 AArch64 baseline：147 个环

```sh
python3 -m gisel graph tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json --config baseline --json \
  > /tmp/graph-a64.json
# rc=1（有环）, 7m59s
# sha256 a7924bcdd420388bd7e6f76cb0e7990a08c64532505e7420a366ad615e382c15
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1,196,559 | 201,764 | 201,764 | 461,871 | 280,021 | 223,747 | 29,156 | 15,773 | **147** |

`uncovered = ['G_SEXTLOAD', 'G_LOAD', 'G_STORE', 'G_INDEXED_LOAD',
'G_INDEXED_SEXTLOAD', 'G_INDEXED_ZEXTLOAD', 'G_INTRINSIC',
'G_INTRINSIC_W_SIDE_EFFECTS']`（memory/imm 轴或 variadic 槽数未给定）。

### 环在哪里

147 条全部是 `G_ASHR` 的 2-环，样本形如：

```text
G_ASHR[31,36] -> G_ASHR[31,42] -> G_ASHR[31,36]
G_ASHR[32,36] -> G_ASHR[32,42] -> G_ASHR[32,36]
```

具体类型追踪（同一个 evaluator，不走商图）确认了这条链：

```text
G_ASHR (nxv16i8, s32)
  rule 20  NarrowScalar slot1 -> s8    # narrow(slot(1), same_as(0)) when vector
G_ASHR (nxv16i8, s8)
  rule  4  WidenScalar  slot1 -> s32   # widen(slot(1), ty(A_s32)) = clampScalar(1,s32,s64)
G_ASHR (nxv16i8, s32)                  # 回到起点
```

对全部 49×49 个具体类型对做 12 步追踪：**285 条具体环**，全部是
`slot0 = nxv16i8`（以及同类小元素向量）且 `slot1` 在 8/16 与 32 之间往返；
54 个查询因 payload 不支持（指针/元素宽度）抛异常，按 graph 的既有规则算
opaque。

### 归因

`AArch64LegalizerInfo.cpp:253-265` 的链条同时包含：

- `.clampScalar(1, s32, s64)`：把 shift amount 抬到至少 32 位；
- `.maxScalarEltSameAsIf(isVector(0), 1, 0)`：把 shift amount 压到 slot 0 的
  元素宽度（v16i8 → 8 位）。

两者方向相反。对 `(v16i8, s32)` 这种混合查询，任何一遍 legalize 都会在两个
状态之间往返，商图上就是 2-环。

### 这算不算上游 bug

需要分开说，不能直接下结论：

1. **IR 层可能不可达**。LLVM IR 要求 shift 的两个操作数同型，`(v16i8, s32)`
   不会从合法 IR 直接产生；它可能由 combine 或别的 target 变换构造出来，但
   本仓库没有证据。
2. **上游的字面语义更奇怪**。`maxScalarEltSameAsIf` 的目标是
   `Query.Types[SmallTypeIdx]` **整个类型**（这里就是 v16i8），不是
   `changeElementSize(8)`。把 s32 “narrow” 成 128 位的向量，会被 legalizer 的
   mutation 断言拒绝。
3. **我们的语料对这条规则是显式 deviation**：`tools/import-cxx.py:2611-2620`
   把它落成 `narrow(slot(k), same_as(j))`，注释说明 `replace(same_as(k))` 会
   产生 vector-where-scalar，触发 `mutationIsSane`。所以这 147 条环首先是
   *模型* 里的环，是否对应上游运行时行为要单独判定。

结论：**这是一个待定性的发现，不是 `cycles=0` 的反例失败**。登记为上游
triage 事项；在定性之前，AArch64 的图结论写成“`G_ASHR` 在混合
vector/scalar 查询上存在 2-环，可达性待确认”。

### AArch64 的其他未覆盖项

- 另外四个配置没有跑；`--check-closure` 没有跑。
- 单配置 8 分钟、1.2M 状态是当前的成本上限；AArch64 的候选积仍然偏大。

## 6 历史更正：6 个自环是假环

首版在 X86 上报告 `cycles=6`，全部是自环：

| opcode | ruleset | 代表类型 | 边 |
|---|---|---|---|
| `G_UMIN`/`G_UMAX`/`G_SMIN`/`G_SMAX` | `X86_UMIN` | `s3` | `WidenScalar -> s32` |
| `G_INTRINSIC_ROUNDEVEN`/`G_INTRINSIC_TRUNC` | `X86_INTRINSIC_ROUNDEVEN` | `s3` | `WidenScalar -> s32` |

原因：类签名只收集显式谓词，而这两条规则写成 `widen(slot(0), pow2_min(32))`，
显式谓词是 `true`；真正区分 `s3`/`s32` 的 guard 是 shim 里的
`is_scalar && !is_pow2(size)`，不在谓词 DAG 里。`s3` 和 `s32` 因此同类，
`widen -> s32` 看起来回到自己。LLVM 的 `widenScalarToNextPow2` 本身带
`sizeNotPow2` 谓词，真实语义是 `s3 -> s32 -> Lower/Libcall`，终止。

修复方式：把每条变异规则的隐式 shim guard 并入类签名（`eval.rule_matches`，
`evaluate()` 签名不变）。6 个自环全部消失。

## 7 未覆盖

- AArch64 baseline 及另外四个配置没有在当前 commit 上重跑；`--check-closure`
  也未跑。AArch64 的候选积（约 1.17M states）不在本轮优化范围。
- RISC-V 的 `--check-closure`、imm 轴和 ordering 轴没有跑。
- 图只做静态商图，不实现“动态跑一遍 legalize 循环”；MIR/`llc` 不在范围。
- `G_INTRINSIC*` 等 variadic opcode 的槽数没有进 manifest，因此被报成
  `uncovered`，不是 0 环证据的一部分。
