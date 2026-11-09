# 规则语义（v0.1）

状态: 描述性。可执行定义是 `gisel/eval.py`；本文每条都能指到函数或行号。
上游的代数推导见 `llvm-dev/docs/dsl/2026-11-01-legalize-algebra.md` 与
`2026-11-01-legalize-semantics.md`，本文只记录**落地后的口径**。

## 1 域：LLT

六种 kind：`invalid`、`scalar(s)`、`integer(i)`、`float(f)`、`bf16`、
`pointer(as,w)`、`vector(lanes,scalable,elem)`（`eval.py:66-207`）。

- 指针宽度是显式字段，`p0:64` 与 `p0:*` 只在 JSON 拼写上不同：集合内写通配，
  domain 写具体宽度（`core_json.py:1-15`）。
- 相等是 `llt_eq`（`eval.py:302`）：两边都是向量时逐元素比较；任一侧是
  `scalar` 时按 `isScalar()` 的"同宽度即相等"规则（`s32 == i32 == f32`，
  但 `i32 != f32`）。
- 尺寸/对齐以位为单位（`size_in_bits:122`、`align_to:225`）。

## 2 匹配：有序规则，首个命中

`evaluate`（`eval.py:860`）：

1. 按 opcode 找到所有 ruleset（`Evaluator.by_opcode`，保持文件顺序）；
2. 按 ruleset 内规则顺序，取第一条 `predicate` 为真的规则；
3. 该规则的 `on/to` 还要过**隐式 guard**（`shim_guard_and_newtype:718`），
   guard 为假则继续下一条；
4. 都不中则 `("Unsupported", 0, invalid)`（`:863`，对应
   `LegalizerInfo::getAction` 的兜底）。

因此 "legal" 不是点集，是**谓词的析取**：一条 `legal <pred>` 只声明
"pred 为真的点在此处合法"，与后续规则的关系由顺序决定。这与 11-01 §3 的
结论一致，只是落地为单步求值。

## 3 类型槽与 mem 槽

- `slot(i)` 读第 i 个类型（`value:441`）；`type_idx` 由 `on` 推导
  （`dsl.py:445`），终端动作固定 0。
- mem 是**独立槽**：`MemDesc(memory_ty, align, ordering, failure_ordering)`
  （`eval.py:413`），`mem_slot(i)` 索引它（`value:443`），不占类型槽，也不能
  出现在 `on`（`_slot_of:707` 只接受 `slot`）。
- `in_mem_desc(slot(a), slot(b), mem_slot(i), [...])` 同时约束两个类型槽、
  对齐（`>=`）和内存类型宽度（`membership:576`）。memdesc 规则不改写
  mem 槽，只做分类。

## 4 积 vs 对角

- `in_pairs` / `in_triples` 枚举元组：积的子集，逐行比较（`membership:648-671`）。
- 对角约束有两种写法：`same_as(k)` 直接返回 `types[k]`（`value:473`），
  `eq(expr, expr)` 走 `values_equal → llt_eq`（`compare:645`）。二者都表达
  "两个槽必须同型"，不是笛卡尔积。
- `in_pairs(...)` 的 `pair` 行是**允许的元组表**；未列出的组合为假。

## 5 动作

| 动作 | 产生方式 | 结果 |
|---|---|---|
| `Legal/Lower/Custom/Unsupported/Libcall` | 终端规则 | 不改类型 |
| `WidenScalar/NarrowScalar` | `widen/narrow` 或 `clamp_*` 的糖 | 改元素位宽 |
| `MoreElements/FewerElements` | `more/fewer`、`scalarize`、`clamp_*` | 改 lane 数或标量化 |
| `Bitcast` | `bitcast(on, to)` | 换整型 |

每个 lattice 规则都带隐式 guard：目标"更弱"才触发（例如 `widen` 要求当前
位宽 `<` 目标或不是 2 的幂，`shim_guard_and_newtype:718` 起）；guard 为假时
这条规则**不**消费查询，继续往下匹配。`new_type = invalid` 表示"不变"。

`more(slot(i), N)` / `fewer(slot(i), N)`（`changeElementCountTo(i, EC(N))`
的写法）是例外：C++ 的变异没有额外 guard，规则的谓词就是全部条件，所以
`eval` 不再补 `num_elems` 比较，命中即把 lane 数改成 `N`。

`clamp_min(i, elt, n)` / `clamp_max(...)` 在前端就展开成一条 `more`/`fewer`
（四个 guard + `replace(vec_of/scalar_or_vec_of(...))`，`dsl.py:475-497`），
所以 core JSON 里没有 clamp 节点。

## 6 prefer / except

自由格式源里没有独立的 `prefer`/`except` 构造：prefer 落成**更早的规则**，
except 落成**更窄的谓词**（命名 `pred` 或内联 `and not ...`）。这是 11-02
已经做出的选择，记录在 `llvm-dev/decisions/D-20261106-76-the-source-is-free-form.md`。
代价是顺序敏感；收益是每个例外都在源码里看得见。

## 7 终止性

`evaluate` 只回答**一步**：查询 → 动作 + 新类型，不迭代。终止性因此是生成
代码侧的性质：每条 lattice 的目标由构造子限制（`pow2_min`、`ty`、
`same_as`、`clamp`），不会回到更强的类型；11-01 §7 给出论证，`eval.py` 不做
额外检查。**已知边界**：求值器不检测循环规则，也不验证"目标更弱"。

## 8 语义差分（三个 target）

| target | 答案表 | 规模 | 结果 |
|---|---|---|---|
| AArch64 | `tests/cases/a64_ref_dump.jsonl` | 9632 | 0 分歧 / 0 error |
| X86 | `tests/cases/x86_ref_dump.jsonl` | 5632（1408 点 × 4 配置） | 0 分歧 / 0 error |
| RISCV | `tests/cases/riscv_ref_dump.jsonl` | 19512（2439 点 × 8 配置） | 0 分歧 / 0 error |

答案表从树内参考实现导出（`llvm-dev/tests/{aarch64,x86}-oracle/`），
`gisel eval` 用我们的 core JSON 复算，由 `tests/test_artifacts.py::EvaluatorCorpus`
固化。X86 表用的是 Core 拼法（`p0:32`），因为 `LLT::print` 会丢掉指针宽度；
求值器两种拼法都接受（`parse_case_llt`）。

X86 表补上了 AArch64 语料从未触发的 schema 形状，并因此修掉四类真 bug：
`{"kind":"nary","op":"all_of"}`、`{"kind":"not","arg":...}` 的 DAG 拼法、
集合元素里的 `select` 类型（`p0:*, if Is64Bit then s64 else s32`）、
以及 `p0:*` 通配指针（按地址空间匹配、不比较宽度）。

RISCV 表来自真实 `RISCVLegalizerInfo` 构造函数链接出的 2439 个点，8 个配置
（`rv64gc`/`rv32gc`/`rv64gcv`/`rv32gcv`/`rv64zbb`/`rv64zfh`/`ristretto`/`rv32zilsd`），
由 `llvm-dev/tests/riscv-oracle/` 导出。它暴露了两条求值器与真实 LLT 的偏差：

- **extended-kind 开关**。`LLT::float16()`、`LLT::integer(32)`、bfloat16 只有
  在 `LLT::getUseExtended()` 打开时才是独立 kind；该开关由 target machine 设置，
  只有 AArch64/AMDGPU/WebAssembly 打开（`AArch64TargetMachine.cpp:241`），
  RISCV/X86 从未打开。所以 RISCV 里 `f16` 的运行值就是 `scalar(16)`，
  `changeElementSize(64)` 给出 `s64` 而不是 `f64`。求值器按 feature 表的
  `LLT::getUseExtended()` 行折叠（`collapse_extended`），AArch64 为 true，
  X86/RISCV 为 false。
- **memdesc 的 TypeSize 判等**。`TypePairAndMemDesc::isCompatible`
  （`LegalizerInfo.h:176-184`）比较 `getSizeInBits()` 的 `TypeSize`，
  scalable 与 fixed 不同值：`<vscale x 4 x s8>`（scalable 32）不匹配 `s32`
  （fixed 32）。只比已知最小值会把 18 条向量 G_LOAD/G_STORE 误判成 Legal
  （应为 Custom）。

两类都先出现在 RISCV 语料；AArch64/X86 的 9632/5632 在修正前后均保持 0 分歧。

## 9 规范形的表粒度

C++ 的 `getActionDefinitionsBuilder(Op)` 每调用一次就追加一张表，`getAction`
按表序、表内按规则序取第一条命中的，所以"一个 opcode 两张表"是合法 C++：第二张
只回答第一张没回答的查询。但冻结的 C++ `.inc` 与 core JSON 形状是"一 opcode
一张表"，这是既有产物的契约。

所以发射前做一次规范化（`ast.canonicalize_rulesets`）：对每个 opcode，把它出现的
所有表按书写顺序拼接；规则序列仍相同的 opcode 继续共享一张表。首命中顺序不变，
答案不变。

这是**产物约束，不是语言约束**：`.gisel` 的 `ruleset` 可以自由地重复 opcode，
模型（`Program`）也保留原样；只有 `--emit=inc`（以及为了维持既有 normal-form
契约的 `--emit=core`）需要一 opcode 一表。`canonicalize_rulesets` 因此是 AST 上
的一个显式变换，注释里写明了它为什么存在。

- X86（63 表 / 328 条）没有重复 opcode → 恒等变换。
- AArch64（117 表 / 741 条）有 6 个重复 opcode（`G_GLOBAL_VALUE` / `G_SPLAT_VECTOR`
  的双 builder，以及 `G_BZERO` / `G_MEMSET` / `G_MEMCPY` / `G_MEMMOVE` 的 MOPS 与
  非 MOPS 两条链）→ 合并后 114 表 / 743 条（共享规则只复制一次）；`imm_idx`
  覆盖标记按 opcode 取并集。
- RISCV 有 11 个重复 opcode（`G_CTLZ` 的 Zbb / 非 Zbb 两条链）→ **96 表 / 402 条
  变成 91 表 / 413 条**（共享的 Zbb 规则只复制一次）；`19512 / 0 / 0` 不变。

## 10 用例生成

`spec/cases.md` 定义如何从本文的语义派生用例：等价类是首个命中的规则区域，
边界是答案真的翻转的相邻值，类外是落到 `Unsupported` 的点。生成器只调用
`evaluate` / `bool_value` / `shim_guard_and_newtype`，不引入第二套求值规则。
