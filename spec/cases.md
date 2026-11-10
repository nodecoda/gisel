# 测试用例生成（规范，v0.1）

状态: 规范性。实现: `gisel/cases.py`；命令: `gisel cases`。
输入不是第二套模型：`.gisel` 先经与 `gen --emit=core` 相同的解析与规范化，
再从那份 schema-0.4 文档派生用例。

## 1 三种 kind

一条用例是查询 `(config, opcode, types, mem, imms)`；`mem` 通常是
`[mty, align]`，声明 ordering 轴后可以是
`[mty, align, ordering, failure_ordering]`，外加 `kind` / `ruleset` /
`rule` / `reason` 四个标签字段。`kind` 只有三种：

```
equivalence  等价类代表
boundary     等价类边界（答案真的翻转的点）
outside      等价类之外（没有规则命中，落到 Unsupported）
```

`types` 用 Core IR 拼写（`s32`、`v4s32`、`p0:*`、`nxv4s32`），与 `--emit=core`
的 domain 一致；`mem` 是 `[memory_ty, align]` 或 `null`。

行的字段、`mem` 的两/四元组归一、答案行与 join 规则见
`spec/cases-format.md`。

### 1.1 equivalence

对每个 `(config, rule)`，取第一条命中该规则、且所有更早规则都不命中的查询。
它同时满足：

- 该规则的 `predicate` 为真；
- 该规则的隐式 guard（`shim_guard_and_newtype`）为真；
- 前面每条规则要么 predicate 为假，要么隐式 guard 为假。

一个规则若可满足但从未首命中，记为 **shadowed**；若在给定 config 集合下
根本不可满足，记为 **unexercised**。两者都进 `--json` 的统计，不静默丢弃。
`--strict-coverage` 把这两个计数变成退出码 1，并打印前 20 条规则名；它存在的
理由是：分母漏了规则时，对拍会给出“0 分歧”，而那不是等价，只是没问到。

候选集按槽位取「规则字面量 ∪ 字面量的邻居 ∪ 哨兵 ∪ 域类型」，其中**字面量和
邻居必须全部保留**——突变规则只能被“合法集合之外的某个值”触发，把邻居截掉
等于让它永远无见证。域类型排在最后，产品规模超限时先丢它们。首命中搜索在全局
候选集没找到见证时，还会对单条规则做一次定向枚举（只用这条规则自己命名的
类型及其邻居）；这一步失败只说明“有界搜索没找到”，不说明规则是死的。

一个 ruleset 挂多个 opcode 时，用例只写第一个 opcode；规则本身不读 opcode。

### 1.2 boundary

边界不是"字面量旁边的值"，而是**答案发生变化的相邻值**：

1. 取该规则的等价类代表（witness）；
2. 把某个槽替换成 `N-1` / `N` / `N+1`，其中 `N` 来自该 ruleset 的类型字面量、
   `bits_of` / `size_of` / `size_in_bytes_of` / `num_elems` 的比较常量，或
   `is_pow2` 的 2 的幂；
3. 只保留使 `(action, type_idx, new_type)` 或"无规则命中"发生变化的替换。

因此每个 boundary 用例都能指出另一侧的代表：两者答案不同。mem 规则额外生成
对齐 `align-1` / `align+1` 与内存类型位宽 `bits-1` / `bits+1` 的边界。

### 1.3 outside

在采样域里没有任何规则（含隐式 guard）命中的查询，求值器返回
`("Unsupported", 0, invalid)`。每个 `(config, ruleset)` 最多保留
`--max-outside` 条（默认 2）。outside 用例是**查询形状**，不保证是合法 MIR
指令；它测的是规则集的兜底，不是指令合法性。

## 2 config

- `--features FILE`：使用文件里的 config 名与真值表，逐字匹配 oracle。
- 缺省：从文档中出现的 `hasFeature(...)` 表达式派生
  `none`（全假）、`all`（全真）、`only-N`（只把第 N 个置真）。
  这些是**合成 config**，用于覆盖规则，不代表目标真实子目标；要和 oracle
  对拍必须传 `--features`。

## 3 对拍契约

`--against ORACLE` 只比较**同时出现在生成集和 oracle 里的查询**：

```
covered  两边都有的查询数
agree    covered 中答案逐字段相等的数量
disagree covered 中答案不同的数量
uncovered 生成集里 oracle 没有对应点的数量
```

- `disagree == 0` 且 `errors == 0` 时，本工具在重叠域上给出子集结论；
- `uncovered` 不是通过，必须在报告里单列；
- `covered == 0` 视为配置错误（config 名或类型拼写不匹配），退出码 2；
- 任何 `disagree` / `errors` 退出码 1。

`agree` 的比较字段是 `(action, type_idx, new_type)`；`new_type` 用
`eval.values_equal`（LLT 的 wildcard / 标量等价规则）比较。

## 4 CLI

```
gisel cases SOURCE --out FILE
             [--features FILE] [--config NAME ...]
             [--against ORACLE] [--queries Q --oracle A]
             [--max-outside N] [--json] [--strict-coverage]
```

退出码：0 成功；1 对拍分歧、求值错误，或 `--strict-coverage` 下有规则
无见证；2 参数/IO/config 错误。
输出是 JSONL，每行一条查询；`gisel eval --cases` 不消费这种文件（它要求
`action/type_idx/new_type` 三列，那是 oracle 的格式）。

### 4.1 从全量 A/B 结果压缩

`--queries Q --oracle A` 是全量对拍之后的回归集入口。`Q` 是不带答案的固定
查询集，`A` 是同一批查询的答案流。工具要求每个 Q 都在 A 中出现；缺失计为
`oracle_missing` 并以失败退出。双方都断言的查询保留为 `oracle_unanswerable`，
不拿它们冒充答案差异。

全量对拍使用工作台命令（不是 gisel 的子命令，见 `docs/SCOPE.md`）：

```sh
python3 ../ab/diff.py official.answers.jsonl ours.answers.jsonl
```

它对完整 key 集合做 join，缺一条或答案不同都失败。主体对拍粒度是
`(config, opcode, types, mem, imms) -> (action, type_idx, new_type)`，不需要
生成一堆 `.ll`/`.mir`。

## 5 显式分析轴

`--axes FILE` 用同一份 target 级值集替换/编辑 `_candidates` 和
`_mem_candidates` 的结果；`profiles.cases` 控制采样上限与边界开关。
没有 `--axes` 时行为逐字节不变。完整 schema、优先级和未覆盖项见
`spec/axes.md`。

## 6 已知边界

- **类型元组必须是一个问得出来的形状。** 候选是逐槽构造的，但多槽 opcode 的槽
  之间有约束（`G_CONCAT_VECTORS` 的目标必须有源的两倍 lane 且元素类型相同，
  `G_SHUFFLE_VECTOR` 的源必须是向量且不能改元素类型，……）。生成器在候选乘积
  之后过一层 `cases.type_shape_ok()`，只保留能对应真实 MIR 指令的元组。
  约束来源分两类，实现里逐条注明：`MachineVerifier.cpp` 的检查，以及 verifier
  没查但 opcode 语义不允许的形状（标 `semantics`）。没有声明的 opcode 不猜，
  保持逐槽独立。被丢掉的候选数必须出现在输出的 `ill_formed` 统计里，不允许
  静默丢弃。
- `imm` 值从规则自身的 `imm(i) == N` / `in(imm(i), [...])` 字面量推导，
  并补 `0` 和 `±1`；profile 的 `imms` 可按下标替换。没有 imm 字面量的规则
  仍无法生成该维度的点。
- mem 用例只从 `inMemDesc` 的字面量表派生；用其它方式读 mem 的规则可能
  unexercised。
- 采样域是有限的：字面量、其 `±1` 邻居、一组 sentinel 类型。boundary 只证明
  "这条边翻转了"，不证明"没有别的边"。
- shadowed/unexercised 是相对**给定 config 集合**的判断，不是全局不可达证明。
