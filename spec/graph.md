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
`uncovered`；它们不能被假装成零槽状态。

每个 ruleset 的类型候选来自 `cases.inspect_ruleset` 和 `cases._candidates`：
声明的 core 类型、规则中的字面量、阈值两侧的切点和稳定的哨兵类型。候选集合
是有限且确定的，按 canonical LLT 文本排序。`domain` 中的指针通配符按
`--pointer-width` 解析。提供 `--oracle` 时，oracle 中的类型和内存点只作为
额外候选加入，以便逐点覆盖检查；它们不参与规则语义。

## 状态和类

一个状态键是：

```text
(opcode, type_class_0, ..., type_class_n, mem_class?)
```

只有 ruleset 的谓词递归读取 `memSlot`/内存描述时才有 `mem_class`。内存候选
来自 `in_mem_desc` 的行，并保存 memory type 和 alignment；不读内存的 ruleset
不携带这个轴。

一个类型类是该 ruleset 所有**原子谓词节点**的三值观察向量相同的类型集合。
`all`、`any`、`not`、`nary` 只负责遍历，`leaf`、比较、membership 和类型观察
节点是原子。原子值严格保留 `True`、`False`、`None`；`None` 表示 evaluator
遇到了无法解释的 feature 或逃逸节点，不能折叠为 `False`。跨多个类型槽的原子
无法用一个槽的 unary 类表达，相关槽保留具体类型，以免错误合并关系。

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
`opaque`、`outside`、`cycles`。最多打印 5 条环，每条最多 6 个节点。

## 负控和闭包

`--inject-edge` 取排序后的第一条真实边 `k -> m`，加入 `m -> k`。没有真实边
时命令返回 2，因为负控无法构造；有边时 DFS 应至少报告一个 2-环并返回 1。

`--check-closure` 对每个有变异的状态枚举该状态的全部成员。每个成员必须使用
同一条规则并映射到同一个目标状态类；变异推出有限域、规则变化、stuck 或得到
多个目标类，都会打印成员和原因并返回 1。该选项不改变类划分，也不实现默认
细化；因此它是对“后继是状态函数”前提的审计。

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
