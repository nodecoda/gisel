# `gisel graph` 规范

`gisel graph SOURCE --emit=core` 在 schema 0.4 正常形上建立有限商图，检查
legalizer 变异是否可能形成环。它只使用 `gisel.eval` 的 LLT、谓词和 shim
语义，不生成 MIR，不运行 `llc`、TableGen 或 LLVM。

## 输入和配置

`--emit` 目前必须是 `core`。命令先执行与 `gisel cases` 相同的
`cases.document`，因此 ruleset 已经 canonicalize，规则节点就是四个出口共同
使用的正常形。`--features FILE` 使用配置到 feature truth table 的 JSON；没有
提供时，使用 `cases.derive_features` 生成的 `none/all/only-N` 配置。重复的
`--config NAME` 将配置域限制为指定行。

opcode 的类型槽数量和 pointer 槽来自 `gisel/data/opcode-slots.json`，缺失时
回退到 generic opcode manifest。没有固定 arity 的 opcode 不建图，写入
`uncovered`；规则读取 `imm(i)` 但 `--axes` 没有提供该下标时同样写入
`uncovered`。它们不能被假装成零槽状态或 opaque。

每个 ruleset 的类型候选来自 `cases.inspect_ruleset` 和 `cases._candidates`：
声明的 core 类型、规则中的字面量、阈值两侧的切点和稳定的哨兵类型。候选集合
是有限且确定的，按 canonical LLT 文本排序。`domain` 中的指针通配符按
`--pointer-width` 解析。提供 `--oracle` 时，oracle 中的类型和内存点只作为
额外候选加入，以便逐点覆盖检查；它们不参与规则语义。

`--axes FILE` 可以把这份值集显式化：explicit 模式下候选轴就是 profile 声明的
类型/内存，不再追加切点；derive 模式仍保留切点。`profiles.graph.skip` 可跳过
opcode（精确或家族前缀），输出多一行 `skipped`。schema 与未覆盖项见
`spec/axes.md`。

## 状态和类

状态按“类”的笛卡尔积枚举：每个类型槽的候选是 `inspect_ruleset` 给出的切点
类型所属的类，而不是具体类型点。状态保存每轴的类 id，具体成员在需要时由
`_state_members` 展开；这样状态数由类数量决定，不再把同一类里的每个类型点
重复建节点。传入 `--oracle` 时，oracle 类型只扩展候选轴，使每个 dumped 点都能
定位到某个类。

一个状态键是：

```text
(opcode, type_class_0, ..., type_class_n, mem_class?, imm_class?)
```

只有 ruleset 的谓词递归读取 `memSlot`/内存描述时才有 `mem_class`（内存值
包含 `(mty, align, ordering, failure_ordering)`，ordering 由 `--axes` 的
`mems.orderings` 提供）；只有提供 `--axes` 且规则读取 `imm(i)` 时才有
`imm_class`。读 ordering 但没有 `mems.orderings`、或读 imm 但没有对应
`imms` 下标时，该 opcode 写入 `uncovered`。内存候选
来自 `in_mem_desc` 的行，并保存 memory type 和 alignment；不读内存的 ruleset
不携带这个轴。

memory type 可以是一个配置相关的 `select` 节点（例如 RISC-V 的
`if XLen == 64 then s64 else s32`）。没有 evaluator 时，候选轴取两个分支的
并集，确保查询生成和 domain 枚举覆盖所有配置；`gisel graph` 在具体配置下
按 `--features` 的真值表只保留所选分支，因此同一个状态键不会混入另一个配置
的内存类型。类型槽里的 `select` 类型同理，先展开成 LLT 拼写再进入候选集合。

一个类型类是该 ruleset 所有**原子谓词节点**的三值观察向量，加上每条带变异的
规则**隐式 shim guard** 的取值向量，两者都相同的类型集合。
`all`、`any`、`not`、`nary` 只负责遍历，`leaf`、比较、membership 和类型观察
节点是原子。原子值严格保留 `True`、`False`、`None`；`None` 表示 evaluator
遇到了无法解释的 feature 或逃逸节点，不能折叠为 `False`。跨多个类型槽的原子
无法用一个槽的 unary 类表达，相关槽保留具体类型，以免错误合并关系。

隐式 guard 同样是谓词：`widen(slot, pow2_min(n))` 只在
`is_scalar && !is_pow2(size)` 成立时命中，`scalarize` 只在向量上命中，等等。
这些 guard 由 `eval.shim_guard_and_newtype` 计算，不在显式谓词 DAG 里。只看
显式谓词会把 X86 `G_SMAX` 的 `s3` 和 `s32` 并成一类，使 `s3 -> s32` 落回
同一个类而退化成自环；把 guard 并入观测向量后两者分开，`s32` 正确落到
`lower`。这是补全 evaluator 实际读取的谓词，不是为凑数而细化分区。

类 id 只在当前 ruleset/轴内有意义，按向量稳定排序。默认绝不自动细化这个
分区；`--check-closure` 发现不封闭时报告反例并失败。

## 后继和出口

每个状态取一个确定性代表点，调用 `eval.evaluate_with_rule`，该函数是
`eval.evaluate` 的加性变体，返回原有三元答案并附加 winning rule index；
`evaluate` 的签名和行为不变。

- `Legal`、`Lower`、`Libcall`、`Custom`、`Unsupported` 是 `terminal`，另外
  按动作名计数。
- 没有规则命中时 evaluator 的 `Unsupported` fallback 通过没有 rule index
  识别，计入 `no-rule`。
- evaluator 或原子观察遇到未实现/逃逸节点时，计入 `opaque`。
- mutation 结果不在当前有限候选域时，计入 `outside`，不建边。
- mutation 没有改变目标类型时，计入 `stuck`，不建边，也不当作环。
- 其余结果在同一 opcode 内重新分类并建一条边；mutation 不得改变 opcode。

边标签包含 action、type index 和 `(ruleset_index, rule_index)`。DFS 使用三色
标记，文本和 JSON 都输出 `config`、`states`、`edges`、`outcomes`、`terminal`、
`opaque`、`outside`、`cycles`。`outcomes` 始终包含 `moves`、`no-rule`、
`terminal`、`opaque`、`outside`、`stuck` 六个键，零值也显式打印，避免读者把
“没有这个字段”误读成“没有发生”。最多打印 5 条环，每条最多 6 个节点。

## 负控和闭包

`--inject-edge` 取排序后的第一条真实边 `k -> m`，加入 `m -> k`。没有真实边
时命令返回 2，因为负控无法构造；有边时 DFS 应至少报告一个 2-环并返回 1。

`--check-closure` 对每个有变异的状态枚举该状态的全部成员。每个成员必须使用
同一条规则并映射到同一个目标状态类；变异推出有限域、规则变化、stuck 或得到
多个目标类，都会打印成员和原因并返回 1。审计扫描全部状态，输出最多保留 20
条样例，`count` 记录真实违规总数；不会因为样例满额而提前停止。文本输出把每个
样例压成单行（`state`、`member`、`mutation`、`targets`、`reason`），不打印
Python dict。`outside` 状态本身也计入违例，因此 `count` 同时覆盖“代表状态在
域外”和“某个成员被变异推出域外”两种情况。该选项不改变
类划分，也不实现默认细化；因此它是对“后继是状态函数”前提的审计。完整 X86
语料仍有 `multiple target classes` 违规，因为 widen 的新类型依赖具体位宽
（`pow2ceil`），同一个 guard 类里的 `s3` 和 `s33` 会分别落到 `s32` 和 `s64`；
在 `--refine` 实现之前，这类状态的“0 环”只覆盖代表点后继。

## Oracle 和退出码

`--oracle FILE` 对同配置的每个 JSONL 点先定位图状态，再用同一个 evaluator 比较
`(action, type_idx, new_type)`。缺失状态、答案差异和 evaluator 错误都会打印到
JSON 字段 `oracle` 并使命令返回 1。oracle 只用于检查，不是图的输入规则。

- `0`：没有环，且闭包/oracle 检查（若请求）通过；
- `1`：发现环、注入边成环、闭包失败或 oracle 不一致；
- `2`：参数、解析、配置、有限域或负控构造错误。

实现必须保持以下语义：指针变宽/变窄后是整数，不构造 8 位指针；clamp lane
使用精确值；条件位宽和 lane 上界按当前配置求值；谓词保持三值；`sizeIs`
读取总位宽，`elementTypeIs` 读取元素位宽；域外是 `outside`；不变 mutation
是 `stuck`。
