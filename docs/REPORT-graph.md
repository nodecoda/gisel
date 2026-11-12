# `gisel graph` 实现报告

## 快照

本报告的每个数字都绑定这棵树：

```text
commit   dd031e4   (2026-11-13, the four graph goldens)
         a56dd66   (2026-11-13, the jsonl/session refactor; graph output unchanged)
version  gisel 0.3.0
targets  X86 / AArch64 / RISC-V corpus at ../upstream-source/pin/PIN.json
goldens  tests/artifacts/graph/{x86-none,riscv-rv64gc}{,-refine}.json
gate     tools/check-graph-golden.sh   (bytes + rc + closure.count)
```

换一棵树重跑，states/edges/opaque/outside 会变。2026-11-10 之前用旧
有限域算出的数字保留在 §6 的更正里。每节的命令都可以原样重放；
x86/none 与 riscv/rv64gc 的 `--json` 输出已经逐字节冻结在
`tests/artifacts/graph/`，`tools/check-graph-golden.sh` 重跑四条命令并同时
比较 rc、`closure.count` 与字节。命令都在仓库根目录执行。

```sh
python3 -m gisel graph SOURCE --emit=core \
  [--features FEATURES] [--config CONFIG] [--json] \
  [--inject-edge] [--check-closure | --no-check-closure] \
  [--oracle ORACLE] [--progress]
```

图直接从 `.gisel` 生成 schema 0.4 core 文档再交给 evaluator；不读原型的
`x86.tables.json`，不生成 MIR，不调用 `llc`/TableGen/LLVM。规范见
`spec/graph.md`，设计记录见 `docs/DESIGN-graph.md`。2026-11-12 起闭包审计
**默认开启**（`--no-check-closure` 关闭），所以下文中未写 `--refine` 的
`rc=1` 都是默认行为，而不是额外选项造成的。

### 两套口径

| 口径 | 命令 | rc | closure | 用途 |
|---|---|---:|---:|---|
| 默认 | 不带 `--refine` | 1 | 272 / 2,864 | 记录“代表点商图上 0 环，但分区不是同余”的覆盖缺口 |
| 签字 | `--refine` | 0 | 0 | `cycles=0` 且后继是状态上的函数 |

`--refine` 不把所有变异都拉回域内：`outside` 仍然计数（x86 2,240；
riscv 3,622），它们没有出边，是汇点，所以不产生环。默认口径的 `rc=1`
是记录值，不是失败；签字口径的 `rc=0` 也不是“没有覆盖缺口”，只是
“缺口不再是闭包反例”。

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
# rc=1（闭包审计默认开启，四个配置都没闭包）, 89.4 s
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | shape | classes | cycles | closure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | 68,667 | 27,935 | 27,935 | 30,504 | 6,856 | 1,177 | 2,195 | 11,945 | 4,031 | 0 | 272 |
| C1 | 68,656 | 26,285 | 26,285 | 31,190 | 7,657 | 1,181 | 2,343 | 11,945 | 4,020 | 0 | 277 |
| C2 | 68,588 | 25,885 | 25,885 | 31,055 | 8,120 | 1,181 | 2,347 | 11,945 | 4,067 | 0 | 265 |
| C3 | 68,667 | 27,740 | 27,740 | 30,518 | 7,037 | 1,177 | 2,195 | 11,945 | 4,031 | 0 | 272 |

2026-11-12 在 `028f581` 复测（图实现无改动，`de8dbbf` 对齐 X86 CTPOP 与
`08bfd1c`/`e226856` 的向量 lane 处理抬高了 states/edges）；JSON 的 SHA-256 是
`37385728c13f9fbe85d1ba5156b0806cd32423972eaf4691590881dde1c8da13`。

`uncovered` 始终是两个 variadic opcode：`G_INTRINSIC`、`G_INTRINSIC_W_SIDE_EFFECTS`
（bundled opcode manifest 没有固定槽数）。

`shape` 是 shift/rotate 的形状约束丢掉的类元组数（见 §5）；它不含在 `states`
里，也不假装成 `outside`。

与 2026-11-10 早些时候的快照相比，C1 的 states 从 66,877 降到 65,275、
edges 从 24,943 降到 24,282、outside 从 1,788 降到 1,656：差异来自比较类
`G_ICMP`/`G_FCMP` 的结果槽过滤（type0 必须是整数），而不是规则或分区变了。
`shape` 从 10,343 升到 11,945，因为被过滤掉的比较结果类元组不再建状态。

## 3 X86 C1 的闭包审计

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --config C1 \
  --json > /tmp/graph-x86-c1-closure.json
# rc=1, 20.5 s（闭包审计默认开启；--no-check-closure 才会回到 0）
```

| 指标 | 值 |
|---|---:|
| states | 68,656 |
| closure.ok | false |
| closure.count | 277 |
| kinds.partition | 232 |
| kinds.outside | 45 |
| cycles（代表点商图） | 0 |

加上 `--refine` 后闭包成立：

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --config C1 \
  --check-closure --refine --json > /tmp/graph-x86-c1-refine.json
# rc=0, 23.0 s
# states 69,098; classes 4,020 -> 4,063 (+43, 1.1%); cycles 0
# closure {ok: true, count: 0}
```

277 的构成：

- `partition` 232：同一类里的成员落到多个目标类（集中在 `G_ANYEXT` 等按宽度走
  不同 `changeTo` 的规则）。
- `outside` 45：同一类里既有成员在域内、又有成员被推到**枚举域外**。2026-11-10
  逐条看完全部 45 条，只剩两类真实中间类型：
  - `s256`（41）：`G_ANYEXT` 的 `widenScalarToNextPow2(0, 8)` 作用在轴里的
    `s129`（`s128` 的 +1 邻居）上，上游确实先得到 `s256`，再由下一条
    `clampScalar(0, s8, sMaxScalar)` 收回 `s128`；
  - `v128s8`（4）：`G_CONSTANT_FOLD_BARRIER` 的 `moreElementsToNextPow2(0)`
    把轴里的 `v65s8` 推到 `v128s8`，再由 `clampNumElements` 收回 `v64s8`。

  这两类不是规则错误，也不是图算错：它们是 mutation 的真实中间类型。把
  `s256` / `v128s8` 补进轴只会把 `outside` 改记成 `partition`（同一个类仍然
  落到多个目标类），所以让闭包成立的手段是 `--refine`，不是补一个类型字面量。

另一类曾被记成 outside 的 41 条 `f8` 是**伪查询**，已修：`G_FCMP` 的 type0 是
比较结果，只能是整数；旧轴把 `f16` 放进 slot 0，于是 `clampScalar(0, s8, s8)`
把它窄成 `f8`。`analysis.type_shape_ok` 现在拒绝浮点结果（`G_ICMP` 同样拒绝
指针/浮点结果），所以 X86 的 outside 从 86 降到 45，states 从 66,877 降到
65,275，edges 从 24,943 降到 24,282（当时快照；现为 §2 的 68,656 / 26,285）。

`--check-closure` 的语义在 2026-11-10 改过（见 `spec/graph.md` §负控和闭包）：
它现在审计**每个非 opaque 状态的全部成员**，不再只审计有出边的代表点；域外
判定统一到 `graph.Domain.successor`。因此本表与 2026-11-08 的“3,465 条
multiple target classes”不可直接比较——旧数字按状态计，新数字只计混合类。

**`cycles=0` 的前提**：不带 `--refine` 时只在代表点商图上成立；带 `--refine`
时闭包成立，0 环是完整结论。`--refine` 改变第 2 篇的“原子”定义，所以默认
关闭，由调用者显式选择。闭包审计本身自 2026-11-12 起默认开启：未 refine 的
四个大 target 默认 `rc=1`，读者要么带 `--refine` 拿完整结论，要么显式写
`--no-check-closure` 承担“0 环只是条件结论”。

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
# rc=0（2026-11-11 在 dad5a61 重跑；2026-11-13 带 --refine 进夜间档）
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | shape | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rv64gc | 521,899 | 28,925 | 28,925 | 413,778 | 46,884 | 29,114 | 3,198 | 30,313 | 8,001 | 0 |

`uncovered = ['G_SEXT_INREG', 'G_INTRINSIC', 'G_INTRINSIC_W_SIDE_EFFECTS']`
（imm 轴或 variadic 槽数未给定）。

闭包：`count=2,864`（`partition 610` / `outside 2,254`），rc=1。
其中 2,208 条集中在 `G_CTLZ_ZERO_POISON` / `G_CTTZ_ZERO_POISON`：规则
`widen(slot(1), same_as(0))` 是跨槽变异，旧 refine 只看“写回本槽”的变异，
拆不开这个类。

2026-11-11 在 `dad5a61` 重跑：`--check-closure` 仍是 `count=2,864`
（`partition 610` / `outside 2,254`），rc=1；把 refine 扩到跨槽目标后，
`--refine` 得到 **`count=0`，rc=0**，classes 8,001 → 8,050（+49），
states 522,992，edges 29,356，cycles 0。

## 5 AArch64 baseline：0 个环（去掉 MIR 不可达的形状之后）

```sh
python3 -m gisel graph tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json --config baseline --json \
  > /tmp/graph-a64.json
# rc=0（2026-11-11 在 dad5a61 重跑；2026-11-13 带 --refine 进夜间档）
```

| config | states | edges | moves | no-rule | terminal | opaque | outside | shape | classes | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1,104,645 | 188,035 | 188,035 | 424,556 | 274,504 | 204,751 | 12,799 | 54,910 | 15,193 | **0** |

`uncovered = ['G_SEXTLOAD', 'G_LOAD', 'G_STORE', 'G_INDEXED_LOAD',
'G_INDEXED_SEXTLOAD', 'G_INDEXED_ZEXTLOAD', 'G_INTRINSIC',
'G_INTRINSIC_W_SIDE_EFFECTS']`（memory/imm 轴或 variadic 槽数未给定）。

闭包（不带 refine）：`count=2,671`（`partition 178` / `outside 2,493`），rc=1。
带 refine：**`count=0`，rc=0**；states 1,104,645 → 1,105,268，classes
15,193 → 15,336（+143, 0.9%），edges 188,580，cycles 0。所以 AArch64 的
0 环在 `--refine` 下是完整结论。

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

同一套命令（闭包审计默认开启；下表 `rc` 指 `--refine` 之后的退出码，未 refine
时只对 `closure.count=0` 的 target 为 0），多配置 target 跑全部配置。ARM / Mips 的
`states` 是单配置值（各配置的状态数相同），不是 7 个配置之和：

| target | configs | states | closure.count | partition | outside | refine 后 | rc |
|---|---:|---:|---:|---:|---:|---:|---:|
| ARM | 7 | 14,721 | **0** | 0 | 0 | — | 0 |
| Mips | 5 | 22,968 | **0** | 0 | 0 | — | 0 |
| PowerPC | 1 | 7,402 | **0** | 0 | 0 | — | 0 |
| M68k | 1 | 1,232 | **0** | 0 | 0 | — | 0 |
| WebAssembly | 4 | 26,818 | 302 | 168 | 134 | **0**（1,945→2,013 类） | 0 |
| SPIR-V | 6 | — | 未覆盖 | — | — | — | — |

WebAssembly 的 302 条残余：12 条显式 `i128`（轴里只有 `i8`/`i16`/`i32`/`i64`），
其余是 `G_FCOPYSIGN` 等类里“代表点在域外、成员在域内”的跨域混合。把 refine
扩到跨槽目标后，**`--refine` 得到 `count=0`，rc=0**；classes 1,945 → 2,013
（+68），states 27,096，edges 18,869。

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

效果（2026-11-10 快照；当前主表数字已按 `dad5a61` 更新，见 §2/§4/§5）：

| target | closure（修前） | closure（修后） | edges |
|---|---:|---:|---|
| X86 C1 | 321 (P228/O93) | 277 (P232/O45) | 23,874 → 24,282 |
| AArch64 baseline | 2,629 (P178/O2,451) | 2,671 (P178/O2,493) | 189,983 → 197,779 |
| RISC-V rv64gc | 4,139 (P378/O3,761) | 2,864 (P610/O2,254) | 37,841 → 38,165 |
| ARM | 67 (O67) | **0** | — |
| Mips | 67 (O67) | **0** | — |
| PowerPC | 11 (O11) | **0** | — |
| M68k | 12 (O12) | **0** | — |
| WebAssembly | 357 (P133/O224) | 302 (P168/O134) | — |

四个小 target 的违例全部消失，说明那 157 条是记账错误，不是规则缺口。X86 /
AArch64 在 `--refine` 下闭包成立。

剩下的 `outside` 不是同一种东西，抽样（每个 target 的 JSON 最多保留 20 条
样例）可以分开：

- X86 45：`s256`（41）和 `v128s8`（4），都是 mutation 的真实中间类型；
  `f8`（41）是伪查询，已由比较结果槽过滤修掉。
- AArch64 2,493：样本是 `nxv1s8 -> nxv1s32`、`v7f16 -> v7f32`，以及
  “代表点在域外、成员在域内”的混合类（`s7`、`bf16`）。
- RISC-V 2,254：2,208 条是 `G_CTLZ_ZERO_POISON` / `G_CTTZ_ZERO_POISON` 的
  跨槽 `same_as(0)` 类；其余是 `G_ADD`/`G_AND` 等宽度类。
- WebAssembly 134：12 条显式 `i128`，其余是 `G_FCOPYSIGN` 等类的跨域混合。

这些 `outside` 都不是规则错误；它们是有限轴没有枚举到的中间类型或跨槽目标。
把 refine 扩到跨槽目标后，**X86 / AArch64 / RISC-V / WebAssembly 四个大
target 在 `--refine` 下全部 `closure.count=0`、`cycles=0`**。所以“0 环”的
可签字写法统一为：`--refine`（闭包默认开启，也可显式写 `--check-closure
--refine`），并带上各报告的类数增量。

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
- RISC-V 的 imm 轴、ordering 轴没有跑；闭包在 `rv64gc` 上跑过，`--refine` 后通过（§4）。
- SPIR-V 单配置 420 s 超时，没有图和闭包数字。
- `G_INTRINSIC*` 等 variadic opcode 的槽数没有进 manifest，因此被报成
  `uncovered`，不是 0 环证据的一部分。
- `--refine` 已扩到跨槽目标（按被写入槽的具体目标类型拆），所以 RISC-V/
  WebAssembly 也能到 `closure.count=0`。它仍是 opt-in，因为会改变“原子”定义。
- PR 门禁只收 x86/none、x86/none-refine、riscv/rv64gc、riscv/rv64gc-refine
  四个 golden（`tools/check-graph-golden.sh`，并行后约 3m27s）。
- 夜间档按 sha256 锁定十个配置：AArch64 baseline、X86 C0–C3，以及
  ARM/ARMv7a-NEON、MIPS32、PPC default、M68k default、wasm32 各一个
  （`tools/check-nightly-graphs.sh`，`nightly.yml`）。不进 PR 门，因为单是
  AArch64 就要约 8 分钟、1.15M states。2026-11-13 录制：10 个配置并行
  8m44s，全部 `cycles=0` 且 `closure.count=0`。
- SPIR-V 只进 cases 门禁，不进 graph 夜间档：`spirv64-kernel --refine`
  15 分钟未完成，钉进去只会得到一个慢超时，不是覆盖。
