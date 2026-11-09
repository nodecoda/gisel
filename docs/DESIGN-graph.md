# `gisel graph` 设计

状态：已确认并落地（2026-11-07）。本文定义第一版实现，不改变 `.gisel` 语法和四个既有出口。

## 目标和入口

`gisel graph SOURCE --emit=core [--features FEATURES] [--config CONFIG]`
读取 `SOURCE`，在内存中生成 schema 0.4 core document，交给现有
`gisel.eval.Evaluator` 求值。`--emit` 只接受 `core`，用于明确图的输入是正常形；
命令不读取 `.inc`、`.td`，也不调用 LLVM。

`--features` 复用 `cases`/`domain` 的 JSON truth table。未指定时复用
`cases.derive_features` 的默认配置；指定 `--config` 后只跑该行，否则每个配置
独立建一张图。文本输出按配置打印一个报告块；JSON 输出为
`{"reports": [...]}`，每个 report 都包含下文的固定字段。

## 有限域和类

1. 先用 `cases.document` 得到 canonical core document，再用
   `domain.domain_axes` 取得 core domain types 和 memory rows。指针槽根据
   `domain.load_opcode_slots` 的 `ptype` 使用当前配置的具体指针宽度。
2. 对每个 ruleset 调用 `cases.inspect_ruleset`。它提供该 ruleset 使用的槽、
   类型字面量、位宽/元素数/总大小切点和 memory rows。以这些切点为边界，复用
   `cases` 的候选值逻辑补齐 `N-1/N/N+1`、精确 lane 值和必要的类型邻居；不使用
   固定的笛卡尔积凑数，也不把 `next_pow2` 当作 clamp 的切点。候选集合排序固定，
   以便类 id 和报告可复现。
3. 一个槽的类由该 ruleset 中所有原子谓词的三值结果向量，加上每条带变异规则
   的隐式 shim guard 结果决定。遍历谓词树时，`all`/`any`/`not` 只是结构，
   其他谓词节点按稳定的前序编号；对每个候选类型调用 eval 得到 `True`、
   `False` 或 `None`。相同向量归为同一类，类 id 按 `(向量, 代表类型)` 排序。
   `None` 是 opaque，不能折叠成 `False`。隐式 guard（`is_scalar`、
   `is_pow2`、lane 数等）由 `eval.shim_guard_and_newtype` 计算，也是 evaluator
   实际读取的谓词，必须进入观测向量；否则 `s3` 和 `s32` 会被并类，
   `s3 -> s32` 会退化成假自环（见 REPORT-graph 的更正一节）。
4. 若 ruleset 读 memory（递归看到 `memSlot`、`inMemDesc`、`memTy`、
   ordering 等观察），memory 也建立同样的原子结果类。状态键始终包含
   `(opcode, type_class_0, ..., type_class_n, mem_class)`；不读 memory 的
   ruleset 不放 memory 轴。没有足够 memory rows 时报告 `uncovered`，不静默
   建一个更小的图。

图只使用 opcode manifest 能给出固定类型槽数的 opcode。variadic/未知 arity
的 opcode 记入 `uncovered`，从报告中明确列出；不会把它们当成零槽指令。

## 后继和分类

对每个 `(opcode, class tuple)` 取每个轴的确定性代表成员，调用一个不改变
`eval.evaluate()` 现有签名的 `evaluate_with_rule` 变体，得到即时的
`(action, type_idx, new_type, rule_index)`。规则选择和 shim guard 仍由
`gisel.eval` 完成。

- `Legal`、`Lower`、`Libcall`、`Custom`、`Unsupported`，以及没有 mutation
  的命中，进入 `terminal`，按 action 名计数。
- 没有规则命中时，`evaluate` 的 fallback `Unsupported` 通过
  `rule_index is None` 与真实的 `Unsupported` 规则区分，计入 `no-rule`。
- eval 遇到无法解释的 C++/未知叶子时，当前状态计入 `opaque`；不能把异常或
  `None` 当作谓词为假而继续选后面的规则。
- 非终结 mutation 结果若不在当前 ruleset 的候选类域，计入 `outside`，不建边。
- mutation 结果等于输入类型时计入 `stuck`，不建自环；它既不是 cycle，也不是
  `Legal`。
- 其余结果把新类型重新分类，在同一 opcode 内建立一条边，边标签包含 action、
  `type_idx` 和 rule index。mutation 永远不改变 opcode。

输出至少包含 `config/states/edges/outcomes/terminal/opaque/outside/cycles`，并
附带 `no-rule/stuck/uncovered` 和注入边信息。DFS 使用三色标记，遍历顺序固定；
最多输出五条环，每条最多六个节点。`--inject-edge` 取排序后的第一条非自环
边 `k -> m`，加入 `m -> k`，保证负控产生 2-环；没有非自环时才退回第一条边。

## 闭包检查

> 2026-11-10 更新：审计对象从“有变异的代表点”扩到**每个非 opaque 状态的全部
> 成员**；域外判定统一到 `graph.Domain.successor`（声明域 + 类表两个条件）。
> 全部成员都在域外的类不再算 closure 违规，只有混合类算。`--refine` 已实现，
> 且会把“无后继”的成员单独成桶。
>
> 另一处 2026-11-10 的修正：两个类型槽不是永远独立。通用 MIR verifier 要求
> shift/rotate 的两个操作数同为标量或同为向量，所以 `(v16i8, s32)` 不是可问的
> 查询。类元组找不到形状合法的成员组合时不建状态，计 `shape`；这不是规则集
> 语义，`cases.type_shape_ok` 是它的唯一实现。AArch64 上一版报的 147 个
> `G_ASHR` 2-环就是这样消失的（见 `docs/REPORT-graph.md` §5）。
> 下面的原始设计保留为当时的记录。

`--check-closure` 不改变分区。对每个状态的每个类轴，枚举该类的所有成员，
并取这些成员的笛卡尔积，重新执行同一条命中规则和 mutation。所有结果必须：

1. 仍落在当前 ruleset 的类型/memory 候选域；
2. 映射到唯一的目标类状态；
3. 使用与代表点相同的 action、type index 和 mutation。

若同一源类得到两个不同目标类，打印源成员、mutation、两个目标类及对应类型，
并返回 1。审计扫描全部状态，输出只截断样例。默认不自动细化；第一版不实现
`--refine`，因此不会改变第 2 篇定义的原子分区。

这留下一个已知缺口：widen 的目标是 `pow2ceil(具体位宽)`，同一 guard 类里的
`s3` 和 `s33` 会分别落到 `s32` 和 `s64`。完整 X86 C1 因这类 mutation 粒度
产生 3,465 条 `multiple target classes`。在这些状态上“后继是类函数”不成立，
`cycles=0` 只覆盖代表点后继；补齐需要按 mutation 目标做定点细化的 `--refine`。

## Oracle 检查和退出码

`--oracle FILE` 接受任意 runner 写出的答案 JSONL（与 `tools/ab/diff.py` 读的
格式相同），把每个 query 映射到图状态，比较图状态的即时 action/type index/new
type。代表点与答案不一致、query 无法落入图域、或 opaque/outside 被错误当成
普通状态都算失败。它不默认读取任何文件，避免把测试数据变成图的输入；仓库里
不再有冻结答案文件，测试用的是临时构造的小型答案集。

- `0`：没有环，且请求的闭包检查通过；
- `1`：发现环、注入边产生环、闭包不封闭或 oracle 校验失败；
- `2`：参数、core 解析、feature 配置、未知 arity 或无法建立有限域。

## 已确认的不变量

实现直接复用 `gisel.eval` 的 LLT 和 shim mutation：指针变更宽度后变成整数，
没有 8 位指针；`set_lanes` 使用 clamp 的精确值；位宽/元素数上界通过当前
feature 行求值；谓词保持 `True/False/None` 三值；`sizeIs` 取总位宽而
`elementTypeIs` 取元素位宽；域外是 `outside`；不变 mutation 是 `stuck`。
这些分别对应原型 `sim/model.py` 的 `apply_mutation`、`eval_int_expr`、
`eval_pred`，以及 `sim/runtime.py` 的 `index_of`/`legalize` 分支。

