# `gisel graph` 实现报告

## 快照

本报告的每个数字都绑定这棵树：

```text
commit   799968c   (2026-11-10, the finite-domain fix)
version  gisel 0.3.0
targets  X86 / AArch64 / RISC-V corpus at tests/corpus/PIN.json
```

换一棵树重跑，states/edges/opaque/outside 会变。2026-11-10 之前用旧
有限域算出的数字保留在 §6 的更正里。每节的命令都可以原样重放，
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
# rc=0, 65.8 s
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | shape | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | 66,888 | 26,630 | 26,630 | 30,634 | 6,856 | 1,016 | 1,752 | 10,343 | 3,985 | 0 |
| C1 | 66,877 | 24,943 | 24,943 | 31,349 | 7,777 | 1,020 | 1,788 | 10,343 | 3,974 | 0 |
| C2 | 66,809 | 24,543 | 24,543 | 31,214 | 8,240 | 1,020 | 1,792 | 10,343 | 4,021 | 0 |
| C3 | 66,888 | 26,416 | 26,416 | 30,629 | 7,157 | 1,016 | 1,670 | 10,343 | 3,985 | 0 |

`uncovered` 始终是两个 variadic opcode：`G_INTRINSIC`、`G_INTRINSIC_W_SIDE_EFFECTS`
（bundled opcode manifest 没有固定槽数）。

`shape` 是 shift/rotate 的形状约束丢掉的类元组数（见 §5）；它不含在 `states`
里，也不假装成 `outside`。

与上一版的差别全部来自有限域的定义，不是规则或分区变了：轴里本来就有的哨兵
（`s32`/`s64`/`s128`/`f16`/`f32`/`f64`…）现在算域内，于是原先记成 `outside`
的代表点变成 `moves`。states 不变，C1 的 edges 从 23,874 涨到 24,943，
outside 从 2,857 降到 1,788，正好一一对应。

## 3 X86 C1 的闭包审计

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --config C1 \
  --check-closure --json > /tmp/graph-x86-c1-closure.json
# rc=1, 20.5 s
```

| 指标 | 值 |
|---|---:|
| states | 66,877 |
| closure.ok | false |
| closure.count | 318 |
| kinds.partition | 232 |
| kinds.outside | 86 |
| cycles（代表点商图） | 0 |

加上 `--refine` 后闭包成立：

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --config C1 \
  --check-closure --refine --json > /tmp/graph-x86-c1-refine.json
# rc=0, 20.4 s
# states 67,360; classes 3,974 -> 4,017 (+43, 1.1%); cycles 0
# closure {ok: true, count: 0}
```

318 的构成：

- `partition`：同一类里的成员落到多个目标类（集中在 `G_ANYEXT` 等按宽度走不同
  `changeTo` 的规则）；
- `outside`：同一类里既有成员在域内、又有成员被推到**枚举域外**。剩下的 86 条
  是真正的覆盖债：X86 上目标集中在 `s256`（41）、`f8`（41）、`v128s8`（4）——
  这些宽度/形状没有任何候选轴枚举到。

`--check-closure` 的语义在 2026-11-10 改过（见 `spec/graph.md` §负控和闭包）：
它现在审计**每个非 opaque 状态的全部成员**，不再只审计有出边的代表点；域外
判定统一到 `graph.Domain.successor`。因此本表与 2026-11-08 的“3,465 条
multiple target classes”不可直接比较——旧数字按状态计，新数字只计混合类。

**`cycles=0` 的前提**：不带 `--refine` 时只在代表点商图上成立；带 `--refine`
时闭包成立，0 环是完整结论。`--refine` 改变第 2 篇的“原子”定义，所以默认
关闭，由调用者显式选择。

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
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | shape | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rv64gc | 566,006 | 41,915 | 41,915 | 432,723 | 58,995 | 29,175 | 3,198 | 19,646 | 8,551 | 0 |

`uncovered = ['G_SEXT_INREG', 'G_INTRINSIC', 'G_INTRINSIC_W_SIDE_EFFECTS']`
（imm 轴或 variadic 槽数未给定）。

闭包：`count=2,864`（`partition 610` / `outside 2,254`），rc=1。
`--refine` 只把类从 8,551 拆到 8,582（+31），closure 仍是
`count=2,802`（`partition 594` / `outside 2,208`），rc=1。

RISC-V 是唯一一个“refine 几乎不动”的大 target：它的违规集中在跨槽规则
（`G_LOAD`/`G_STORE`/条件 `same_as`），而当前 refine 是逐轴、单槽的，拆不动。
这说明**剩下的缺口是有限域，不是分区**：要过闭包，得让候选轴对变异封闭，
而不是继续细化类。

## 5 AArch64 baseline：0 个环（去掉 MIR 不可达的形状之后）

```sh
python3 -m gisel graph tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json --config baseline --json \
  > /tmp/graph-a64.json
# rc=0, 455.0 s, 1.4 GB RSS
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | shape | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1,152,444 | 199,410 | 199,410 | 452,941 | 275,101 | 211,204 | 13,788 | 44,115 | 15,773 | **0** |

`uncovered = ['G_SEXTLOAD', 'G_LOAD', 'G_STORE', 'G_INDEXED_LOAD',
'G_INDEXED_SEXTLOAD', 'G_INDEXED_ZEXTLOAD', 'G_INTRINSIC',
'G_INTRINSIC_W_SIDE_EFFECTS']`（memory/imm 轴或 variadic 槽数未给定）。

闭包（不带 refine）：`count=2,671`（`partition 178` / `outside 2,493`），rc=1。
带 refine：**`count=0`，rc=0**；states 1,152,444 → 1,153,067，classes
15,773 → 15,916（+143, 0.9%），cycles 0。所以 AArch64 的 0 环在 `--refine`
下是完整结论。

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

数字变化（同一命令、同一配置，2026-11-08）：

```text
states  1,196,559 -> 1,152,444      (-44,115 = shape)
edges     201,764 ->   189,983
opaque    223,747 ->   211,204
outside    29,156 ->    23,215
cycles        147 ->         0
```

`shape` 正好等于 states 的减少量：被删掉的每一个类元组都只贡献状态，没有贡献
一条边。

## 6 其它 target 的闭包（2026-11-10 补测）

同一套命令，`--check-closure`，多配置 target 跑全部配置：

| target | configs | states | closure.count | partition | outside | refine 后 | rc |
|---|---:|---:|---:|---:|---:|---:|---:|
| ARM | 7 | 15,629 | **0** | 0 | 0 | — | 0 |
| Mips | 5 | 23,972 | **0** | 0 | 0 | — | 0 |
| PowerPC | 1 | 7,911 | **0** | 0 | 0 | — | 0 |
| M68k | 1 | 1,232 | **0** | 0 | 0 | — | 0 |
| WebAssembly | 4 | 27,588 | 302 | 168 | 134 | 143（1,945→2,008 类） | 1 |
| SPIR-V | 6 | — | 未覆盖 | — | — | — | — |

WebAssembly 的残余：12 条显式 `i128`（轴里只有 `i8`/`i16`/`i32`/`i64`），
其余是 `G_FCOPYSIGN` 等类里“代表点在域外、成员在域内”的跨域混合。refine 只能
拆到 143，说明这里同样缺的是轴，不是分区。

SPIR-V 的单个配置 `spirv64-kernel` 在 420 s 内没有跑完（图规模超过 AArch64），
所以没有闭包数字。它不能拿别的 target 的数字代替。

## 7 2026-11-10 的更正：`outside` 曾经用错有限域

老实现里有两个类型宇宙：

- 图的候选轴来自 `cases._candidates`，固定带一组哨兵（`s32`/`s64`/`s128`/
  `f16`/`f32`/`f64`/`s3`/`s7`…），所以这些值会成为状态成员；
- `outside` 的判定却用 `domain_axes`，只认 `.gisel` 里声明过的类型。

于是“已经作为状态枚举出来的值”被当成域外：Mips / ARM 的语料一条 float 类型
都没声明，`f16 -> f32` 明明是轴里两个有类的值，却被记成 `outside`；X86 C1、
RISC-V、AArch64 同样丢掉了大量真实边。

修法（`799968c`）：有限域 = 轴实际携带的值集（声明类型 ∪ 规则字面量与切点 ∪
稳定哨兵；`--axes` explicit 模式仍是 profile 的值集）。`Domain.successor` 的
两个条件不变，只是 (a) 从“`.gisel` 声明过”改成“本次图枚举过”。

效果：

| target | closure（修前） | closure（修后） | edges |
|---|---:|---:|---|
| X86 C1 | 321 (P228/O93) | 318 (P232/O86) | 23,874 → 24,943 |
| AArch64 baseline | 2,629 (P178/O2,451) | 2,671 (P178/O2,493) | 189,983 → 199,410 |
| RISC-V rv64gc | 4,139 (P378/O3,761) | 2,864 (P610/O2,254) | 37,841 → 41,915 |
| ARM | 67 (O67) | **0** | — |
| Mips | 67 (O67) | **0** | — |
| PowerPC | 11 (O11) | **0** | — |
| M68k | 12 (O12) | **0** | — |
| WebAssembly | 357 (P133/O224) | 302 (P168/O134) | — |

四个小 target 的违例全部消失，说明那 157 条是记账错误，不是规则缺口。X86 /
AArch64 在 `--refine` 下闭包成立；RISC-V / WebAssembly 的残余是真正的轴缺口
（`s256`、`f8`、`v128s8`、`i128` 等没有枚举），refine 拆不动。

## 8 历史更正：6 个自环是假环

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

## 9 未覆盖

- AArch64 只跑了 `baseline`；另外四个配置的图和闭包没有跑。单配置约 8 分钟、
  1.15M states 是当前的成本上限。
- RISC-V 的 imm 轴、ordering 轴没有跑；闭包在 `rv64gc` 上跑过，未通过（§4）。
- SPIR-V 单配置 420 s 超时，没有图和闭包数字。
- `G_INTRINSIC*` 等 variadic opcode 的槽数没有进 manifest，因此被报成
  `uncovered`，不是 0 环证据的一部分。
- `--refine` 是逐轴、单槽的：跨槽规则（`G_LOAD`/`G_STORE`/`same_as` 条件）
  拆不动，所以 RISC-V/WebAssembly 的残余不能靠 refine 掩盖。
