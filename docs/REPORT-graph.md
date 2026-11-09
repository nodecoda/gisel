# `gisel graph` 实现报告

## 快照

本报告的每个数字都绑定这棵树：

```text
commit   9e59c9d   (2026-11-10)
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
# sha256 2ed41c9e96363b929f4db480fd960fdabd2c1614b0b1cdad2c640cb5772b6cc8

python3 -m gisel graph /tmp/gisel-graph-report/fixture.gisel \
  --config none --inject-edge --json > /tmp/gisel-graph-report/fixture-inject.json
# rc=1  states=4 edges=2 cycles=1
# injected: G_ADD[3] -> G_ADD[1]（原边 1 -> 3 的反向）
# sha256 8609d5a267b914a2aad3189586011a706fb06d92f1e4125b8b39d1e87d06f7ad
```

注入边是必需的负控：没有它，“0 环”可能只是 DFS 没跑到。

## 2 X86 四配置

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --json > /tmp/graph-x86.json
# rc=0, 65.5 s, 373 MB RSS
# sha256 969ccf0b05086041e3b286e06bdf541a43430ad4ffc32ab08a1790412cc597fa
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | shape | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | 66,888 | 24,565 | 24,565 | 30,634 | 6,856 | 1,016 | 3,817 | 10,343 | 3,985 | 0 |
| C1 | 66,877 | 23,874 | 23,874 | 31,349 | 7,777 | 1,020 | 2,857 | 10,343 | 3,974 | 0 |
| C2 | 66,809 | 23,462 | 23,462 | 31,214 | 8,240 | 1,020 | 2,873 | 10,343 | 4,021 | 0 |
| C3 | 66,888 | 24,437 | 24,437 | 30,629 | 7,157 | 1,016 | 3,649 | 10,343 | 3,985 | 0 |

`uncovered` 始终是两个 variadic opcode：`G_INTRINSIC`、`G_INTRINSIC_W_SIDE_EFFECTS`
（bundled opcode manifest 没有固定槽数）。

`shape` 是 shift/rotate 的形状约束丢掉的类元组数（见 §5）；它不含在 `states`
里，也不假装成 `outside`。

## 3 X86 C1 的闭包审计

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --config C1 \
  --check-closure --json > /tmp/graph-x86-c1-closure.json
# rc=1, 20.5 s
# sha256 10396f0baff079c84eaf1f5313b9536449a7ce8407c4f972eae7404fc68af6ff
```

| 指标 | 值 |
|---|---:|
| states | 66,877 |
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

## 3b X86 C1 的 oracle 对齐（已删除）

`tests/cases/x86_ref_dump.jsonl` 已于 2026-11-10 删除，基于它的 oracle 对齐
不再是证据。`--oracle` 机制保留，接受任意 runner 写出的答案文件；仓库测试用
临时构造的小型答案集覆盖它。原 1,408 点的数字只属于历史快照，不再重跑。

## 4 RISC-V：配置相关的内存类型

RISC-V 的 `mem_desc` 里，memory type 是一个配置相关的 `select`
（`XLen == 64 ? s64 : s32`）。旧实现把它原样放进 `set` 的 key，`graph`/`cases`/
`domain` 都会在 `TypeError: unhashable type: 'dict'` 上崩掉；现在按配置展开。

```sh
python3 -m gisel graph tests/corpus/RISCVLegalizerInfo.gisel \
  --features tests/cases/riscv-features.json --config rv64gc --json \
  > /tmp/graph-riscv.json
# rc=0, 172.1 s, 638 MB RSS
# sha256 ecc8b4284baf975614112b260920036a4b17898995ec0da6671d17a9a98019b8
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | shape | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rv64gc | 566,006 | 37,841 | 37,841 | 432,723 | 58,995 | 29,175 | 7,272 | 19,646 | 8,551 | 0 |

`uncovered = ['G_SEXT_INREG', 'G_INTRINSIC', 'G_INTRINSIC_W_SIDE_EFFECTS']`
（imm 轴或 variadic 槽数未给定）。`--check-closure` 在 RISC-V 上没有跑，属于
未覆盖。

## 5 AArch64 baseline：0 个环（去掉 MIR 不可达的形状之后）

```sh
python3 -m gisel graph tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json --config baseline --json \
  > /tmp/graph-a64.json
# rc=0, 455.0 s, 1.4 GB RSS
# sha256 cf09eea9d830ab87f9f73acc2d709e463a641afd7f19dcaf0d93c9c1e13a4655
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | shape | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1,152,444 | 189,983 | 189,983 | 452,941 | 275,101 | 211,204 | 23,215 | 44,115 | 15,773 | **0** |

`uncovered = ['G_SEXTLOAD', 'G_LOAD', 'G_STORE', 'G_INDEXED_LOAD',
'G_INDEXED_SEXTLOAD', 'G_INDEXED_ZEXTLOAD', 'G_INTRINSIC',
'G_INTRINSIC_W_SIDE_EFFECTS']`（memory/imm 轴或 variadic 槽数未给定）。

### 上一版报的 147 个环是什么

全部是 `G_ASHR` 的 2-环，样本形如：

```text
G_ASHR[31,36] -> G_ASHR[31,42] -> G_ASHR[31,36]
```

日志里的具体类型是 `(<16 x i8>, s32)`——向量源 + 标量移位量，走这条链：

```text
G_ASHR (nxv16i8, s32)
  rule 20  NarrowScalar slot1 -> s8    # narrow(slot(1), same_as(0)) when vector
G_ASHR (nxv16i8, s8)
  rule  4  WidenScalar  slot1 -> s32   # widen(slot(1), ty(A_s32)) = clampScalar(1,s32,s64)
G_ASHR (nxv16i8, s32)                  # 回到起点
```

### 为什么这 147 个环不是上游死循环

三条证据，都在本机 `llc` 上跑过（`builds/explore`，带 PR 238306）：

1. **MIR verifier 拒绝这个形状**。把 `(v16i8, s32)` 的 `G_ASHR` 写成 MIR 喂给
   `llc -mtriple=aarch64 -run-pass=legalizer`：

   ```text
   *** Bad machine code: Shifts and rotates require operands to be either all
   scalars or all vectors ***
   ```

   MIR parser 在进 legalizer 之前就 abort；加 `-verify-machineinstrs=false`
   也一样，因为 MIR 解析本身会 verify。所以这个查询没有合法输入。
2. **形状合法的组合不环**。`(v16i8, v4i32)`（同为向量）在带补丁的构建上被
   `maxScalarEltSameAsIf` 收成 `(v16i8, v4i8)` 后 legal，rc=0；未打补丁的
   `builds/pr-lane` 在同一条规则上断言 `mutationIsSane` 失败——这正是 PR
   238306 修的东西，也说明补丁后的 mutation 只改元素宽度、不改形状。
3. **legalizer 自己不会造出混合形状**：补丁后的目标是
   `Types[TypeIdx].changeElementSize(...)`，向量仍是向量。从合法输入出发，
   到不了 `(vector, scalar)`。

结论：147 是“把两个类型槽当独立轴叉乘”的产物，不是规则表里的活锁，也不是
上游 bug。修复不在规则侧，而在有限域：`cases.type_shape_ok` 增加 shift/rotate
条款（引用 `MachineVerifier.cpp`），`graph` 对每个类元组找**至少一个**形状合法
的成员组合，找不到就不建状态，并把数量记成 `shape`。

数字变化（同一命令、同一配置）：

```text
states  1,196,559 -> 1,152,444      (-44,115 = shape)
edges     201,764 ->   189,983
opaque    223,747 ->   211,204
outside    29,156 ->    23,215
cycles        147 ->         0
```

`shape` 正好等于 states 的减少量：被删掉的每一个类元组都只贡献状态，没有贡献
一条边。

仍然成立的前提：`--check-closure` 没有在 AArch64 上跑；0 环是代表点商图上的
结论，闭包未验证。

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

- AArch64 baseline 已重跑（§5），但另外四个配置和 `--check-closure` 没有跑。
  单配置约 8 分钟、1.15M states 是当前的成本上限。
- RISC-V 的 `--check-closure`、imm 轴和 ordering 轴没有跑。
- `gisel graph` 不生成 MIR、不跑 `llc`；§5 的定性用 `llc` 手工做了三次单点
  验证，那不是命令的一部分。
- `G_INTRINSIC*` 等 variadic opcode 的槽数没有进 manifest，因此被报成
  `uncovered`，不是 0 环证据的一部分。
