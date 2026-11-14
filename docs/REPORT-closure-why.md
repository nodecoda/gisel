# 默认分区的闭包缺口：逐条归因（2026-11-14）

> 快照：gisel `b83dad8`（语义修复）+ `30d1d80`（golden 重录）。
> 机器：32 vCPU / 62 GB，Python 3.10.12。所有数字都由下面给出的命令产生。

## 结论先行

默认分区（不 `--refine`）的闭包缺口**不是单一原因**，也不是“上游规则有错”。逐条归因后只有两类：

1. **我们的记账错误**：一个状态的代表点被类里的边界探针（`s129`、`i65`）劫持，
   整个状态被判成 `outside`，图丢掉了 legalizer 实际会走的边。修掉之后
   `outside` 的含义变成“类内所有成员都出域”。
2. **真实的默认分区缺口**：同一个类里的成员被同一条规则送到不同的目标类，
   或命中不同规则。这是“原子”定义本身不区分宽度/跨槽目标造成的，`--refine`
   可以拆开；它不是规则翻译错误。

修完第 1 类之后，剩余违例全部属于第 2 类，且 `--refine` 在 X86 / RISC-V /
WebAssembly / AArch64 上仍然是 `closure.count=0`、`cycles=0`。**签字口径不变：
`--refine` 仍是默认分区之外的必要一步；变的是缺口现在被完整解释，而不是
“2,864 条不知道是什么”。**

| target / config | 修前 closure | 修后 closure | partition | outside | 说明 |
|---|---:|---:|---:|---:|---|
| X86 C0 | 272 | **272** | 227 | 45 | 未受影响；全是宽度类 |
| X86 C1 | 277 | **277** | 232 | 45 | 同上 |
| X86 C2 | 265 | **265** | 224 | 41 | 同上 |
| X86 C3 | 272 | **272** | 227 | 45 | 同上 |
| RISC-V rv64gc | 2,864 | **1,607** | 984 | 623 | 1,580 条是 CTLZ/CTTZ 零毒类 |
| RISC-V rv32gc | 2,674 | **1,387** | 908 | 479 | 同上 |
| RISC-V ristretto / rv64zbb | 62 | **27** | 16 | 11 | 无跨槽类，只剩宽度类 |
| WebAssembly wasm32 | 302 | **272** | 168 | 104 | 211 条是 `G_FCOPYSIGN` 跨槽类 |
| AArch64 baseline | 2,671 | **1,985** | 178 | 1,807 | 1,764 条是 FCOPYSIGN + VECREDUCE |

注意 RISC-V 的 `partition` 从 610 涨到 984：原来被 `outside` 代表点遮住的类，
重选代表点后开始被审计，露出了本来就存在的多目标/不同规则。总数下降、
`partition` 上升不是矛盾，是同一批状态从“没被问”变成“被问出了真实答案”。

## 1 复现命令

```sh
cd /home/ubuntu/llvm/gisel

# X86 四配置（默认分区）
for c in C0 C1 C2 C3; do
  python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
    --features tests/cases/x86-features.json --config "$c" --json \
    > "/tmp/graph-x86-$c.json"
done

# RISC-V
python3 -m gisel graph tests/corpus/RISCVLegalizerInfo.gisel \
  --features tests/cases/riscv-features.json --config rv64gc --json \
  > /tmp/graph-riscv-rv64gc.json

# WebAssembly
python3 -m gisel graph tests/corpus/WebAssemblyLegalizerInfo.gisel \
  --features tests/cases/wasm-features.json --config wasm32 --json \
  > /tmp/graph-wasm32.json

# AArch64 baseline（与 nightly / 闭包计数测试同一条命令：不带 --axes）
python3 -m gisel graph tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json --config baseline --json \
  > /tmp/graph-aarch64.json
```

全量违例用同一条命令的 `closure.violations`（生产默认保留 20 条样例；归因时把
`_CLOSURE_SAMPLE_LIMIT` 调到 `10**9` 取全量）。每个 target 的原始归因 JSON
在 `/tmp/attrib2-*.json`、`/tmp/attrib5-aarch64.json`，字段是
`{target, config, states, edges, outside, count, kinds, violations}`。

## 2 根因 A：代表点被边界探针劫持（已修）

### 现象

一个状态只用一个具体成员命名，旧实现同时把**这个成员的出口**当成整个状态的出口。
有限轴为每个类带了边界探针：`s129` 的 `G_ANYEXT` 会 widen 到 `s256`，`i65` 会
widen 到 `i128`。这些目标不在枚举域里，于是整个状态被判成 `outside`，而类里
`s7`/`s24` 这类普通成员其实有合法的后继边。

RISC-V `rv64gc` 修前 2,254 条 `outside` 里，有 2,144 条是这种
“代表点 outside、成员 moves”；典型一条：

```json
{"state": "G_ADD[7]", "member": ["s7"], "reason": "different outcome",
 "outcome": "moves", "representative": "outside", "kind": "outside"}
```

### 修法

`gisel/graph.py` 的 `_repick_outside_states()`：后继求值之后、闭包审计之前，
对每个 `outcome == "outside"` 的状态按轴顺序找一个 shape-legal 且后继存在的
成员，替换代表点（状态键和类划分不变）。只有类内所有成员都出域时，才保持
`outside`。

### 效果

- RISC-V rv64gc：2,864 → 1,607；`outside` 状态 3,198 → 3,067，边 +97。
- WebAssembly wasm32：302 → 272；`outside` 状态 1,074 → 1,051，边 +17。
- AArch64 baseline：2,671 → 1,985；`outside` 违例 2,493 → 1,807。
- X86：0 变化（X86 的 `outside` 违例本来就是“成员出域、代表点在域内”，没有
  被劫持的状态）。

`tests/test_graph.py` 相应改了两条断言：`outside` 现在等于“类内所有成员都出域”
（`ONLY_OUTSIDE` 夹具），跨域混类只报真正出域的那个成员（`s3`）。

## 3 根因 B：真实的默认分区缺口（不修，交给 `--refine`）

剩下全部是“同一个类的成员落到不同目标类/不同规则”。按 opcode 拆开：

### X86（C0，272 条）

```text
G_ANYEXT 111   G_SEXT 70   G_ZEXT 70   G_CONSTANT_FOLD_BARRIER 3
G_FREEZE 3     G_IMPLICIT_DEF 3   G_PHI 3   G_SMULH 2 ...
```

227 条是 `multiple target classes`，45 条是 `outside`。原因：
`widen(slot(0), pow2)` 的目标是当前宽度的下一个 2 的幂，类的原子签名只记录
“是不是 2 的幂”，不记录“现在是 8 还是 24”，所以 `s7 → s8`、`s24 → s32`、
`s33 → s64` 落在不同类；`s3 → s4` 更是不在枚举域里。`--refine` 按目标类拆开后
闭合（`x86-none-refine.json`：`closure.count=0`）。

### RISC-V rv64gc（1,607 条）

```text
G_CTLZ_ZERO_POISON 790   G_CTTZ_ZERO_POISON 790
其余 27 条：G_FREEZE 3, G_ADD 2, G_AND 2, G_CONSTANT 2, ...
```

1,580 条来自两个零毒计数 opcode。它们的规则把 slot 1 写成 `same_as(0)`：

```text
narrow(slot(0), ty(sXLen))
widen(slot(1), same_as(0))
narrow(slot(1), same_as(0))
```

默认分区里 slot 0 的 `s3` 和 `nxv16s8` 可能同类，但 `same_as(0)` 会把 slot 1
送到 `nxv1s3` 和 `nxv1s16` 等不同目标；这就是跨槽目标没有进原子签名。
`--refine` 按被写入槽的具体目标类型拆类后，`rv64gc` 的 refine 运行是
`closure.count=0`（`riscv-rv64gc-refine.json`）。

其余 27 条和 X86 同型：`s3 → s4` 出域，`s7/s24/s33 → s8/s32/s64` 多目标。
rv32gc 是 33 条（多几条 32 位宽度类），ristretto/rv64zbb 只有 27 条
（这两个配置没有走到零毒计数的跨槽规则）。

### WebAssembly wasm32（272 条）

```text
G_FCOPYSIGN 211   G_ADD/G_AND/G_CONSTANT/G_MUL/... 各 4
```

`G_FCOPYSIGN` 的两条规则是 `widen(slot(1), same_as(0))` 与
`narrow(slot(1), same_as(0))`，和 RISC-V 的零毒类是同一形状；211 条全部是
跨槽类。其余 61 条是整数/浮点宽度类。`--refine` 后 wasm32 也是
`closure.count=0`（nightly `wasm32.json`）。

### AArch64 baseline（1,985 条）

```text
G_FCOPYSIGN 588
G_VECREDUCE_AND / OR / XOR 各 441（合计 1,323）
G_SDIVREM / G_SREM / G_UDIVREM / G_UREM 各 7 ...
```

- `G_FCOPYSIGN` 588：与 wasm 同型的跨槽 `same_as(0)`，成员如
  `(s3, bf16) → v2s3`。
- `G_VECREDUCE_*` 1,323：向量归约把 lane 数减半（`nxv16i8 → nxv8i8`），
  `nxv8i8` 不在枚举轴里（`outside` 392 × 3），另有 49 × 3 多目标。
- 其余是 `v16s8 → v16s32` 这类元素宽度中间类型出域。

178 条 `partition` 全是 `multiple target classes`；1,807 条是 `outside`。
AArch64 的 refine 运行仍然是 `closure.count=0`、`cycles=0`（nightly
`aarch64-baseline.json`）。

## 4 一个被拒绝的修法（记录理由）

归因过程中试过：把跨槽 mutation 的**读轴**也做成 raw（每个具体值一类），
理由是 `same_as(0)` 的目标取决于读轴。它在 RISC-V/WebAssembly 上效果很好
（1,607 → 27、272 → 61），但：

- AArch64 baseline 的状态数从 **1,104,645 涨到 5,811,265**（峰值 6.2 GB），
  closure 仍是 **1,985**（P178/O1807），一条都没少；
- 它改变了 `spec/graph.md` 定义的“原子”，不是记账修复；
- 项目约束是“不为凑数调分类粒度”，且扩语法/改类定义需要单独批准。

所以本 cohort 不采用；跨槽目标继续由 `--refine` 处理（它按被写入槽的具体
目标类型拆，代价远小于把读轴全 raw）。如果以后要做“默认分区也覆盖跨槽”，
应该作为新的原子定义提案单独评审，而不是混进这次修复。

## 5 未覆盖

- AArch64 只归因了 `baseline`；其余 8 个配置的默认分区（不 refine）没有重跑。
  它们的 refine 数字在 `REPORT-graph-configs.md`，但那份矩阵早于本次 repick，
  默认分区计数不适用。
- SPIR-V 仍在 `--max-states 200000` 处 `unsupported_scale`，没有图。
- `outside` 的中间类型（`s4`、`nxv8i8`、`v16s32`、`v2s3`）没有补进轴；补进去
  会把 `outside` 改记成 `partition`，不会让默认分区闭合。
- RISC-V 的 imm / ordering 轴仍未在默认分区下归因。

## 6 对签字口径的影响

- 旧的“X86 272 / RISC-V 2,864 / wasm32 302 / AArch64 2,671”不再引用；
  当前值是 272 / 1,607 / 272 / 1,985。
- 结论仍是：默认分区的 `cycles=0` 是代表点商图上的条件结论；可签字的
  “无环”必须带 `--refine`（`closure.count=0`），并同时打印
  `outside` / `opaque`。
- 本次没有发现上游规则错误，也没有新增 upstream issue。
