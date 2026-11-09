# 变更说明：AMDGPU 剩余 10 条拒绝与“表达式级宿主逃逸点”

状态：**待批准**（未改 `spec/grammar.md`、`gisel/dsl.py`、`gisel/eval.py`、任何后端）

## 1 现状

AMDGPU 语料（pin `9bfc850b9940`）当前：

```text
142 rulesets, 794 rules, 10 refused
lint: 0 error(s), 7 warning(s)
```

10 条拒绝里，**5 条不需要改语法**，只是导入器还没读完；另外 **5 条**卡在同一件
事：规则的值/变异里出现了 gisel 无法求值的宿主表达式。本文只针对后者请求批准。

## 2 不需要改语法的 5 条（照常推进，不在此次审批范围）

| 拒绝 | 实际原因 | 为什么不是语法问题 |
|---|---|---|
| `needToSplitMemOp` 局部 lambda 声明 ×1 | 它是构造函数里的局部 helper 声明 | 声明本身可以像 `assert` 一样忽略；三处调用点用现有 `opaque("needToSplitMemOp(Query, ...)")` 承接，helper 在构造函数作用域可见 |
| EXTRACT/INSERT `customIf` 宿主调用 ×2 | lambda 先算局部量 `isLegalVecType`，再和类型条件做 `&&` | `opaque("...")` 本来就是谓词 primary，可与 `and` 组合；补“局部量折叠 + 早返回折成 or”即可 |
| EXTRACT/INSERT `moreElementsIf` `isIllegalRegisterType(ST, VecTypeIdx)` ×2 | `VecTypeIdx` 是 `for (unsigned Op : {...})` 的循环值 | 导入器按每个 Op 展开循环即可；helper 在构造函数作用域可见，现有 `opaque` 能承接 |

这 5 条落地后，拒绝数 10 → 5，但**还不是 0**；剩下的正好是 §3 的 5 条。

## 3 真正需要新层的 5 条

| 规则 | 宿主表达式 | 位置 |
|---|---|---|
| LOAD/STORE `narrowScalarIf` 的变异体 ×2 | `maxSizeForAddrSpace(ST, AS, IsLoad, IsAtomic)`；另外 `split_top` 要能切 `pair<unsigned, LLT>` | 变异 lambda 的值 |
| LOAD/STORE `fewerElementsIf` 的变异体 ×2 | 同上，且 body 有嵌套 `if` / 提前 `return` / `bit_floor` | 变异 lambda 的值 |
| BUILD_VECTOR `moreElementsIf` ×1 | `moreElementsToNextExistingRegClass(0)` | **返回 `LegalizeMutation` 的 helper**，不是类型 |

另外 `needToSplitMemOp`（构造函数局部 lambda）本身不需要新语法：对它的调用可以
写成现有 `opaque(...)`，所以它不再单独算一条。

## 4 三个方案

### 方案 A：不动语法，5 条手写成 deviation

- 语料停在这 5 条“已声明、未转写”的偏差上，和 X86 的 `deviation_*` 同一形态。
- 代价：AMDGPU 永远到不了 0 拒绝，报告里的覆盖率要一直带这个口子。
- 风险：0。

### 方案 B（建议）：只加一个“变异逃逸点”

新语法只有一处，位置固定在变异的第二个参数：

```text
more(slot(0), mutate("moreElementsToNextExistingRegClass(0)"))

fewer(slot(0), replace(int_of_size(select(...))))
  # 不能表达时：
narrow(slot(0), mutate("[=](const LegalityQuery &Query) -> std::pair<unsigned, LLT> { ... }"))
```

契约：

| 出口 | 行为 |
|---|---|
| `--emit=inc` | 变异 lambda 里原样 `return (<字符串>);`；`Query`/`ST` 的可见性和 `opaque` 一致 |
| `--emit=core` | 记进 `escapes`，`kind: "mutation"`，去重 |
| `--emit=check` | 不做求值，不含它的语料字节不变 |
| `gisel eval` | 抛 `EvalError("opaque_mutation", ...)`，是洞不是 false |
| `gisel graph` | 该状态记 `opaque`，计入 opaque 出口，不建边 |
| `gisel cases` | 规则仍然枚举，但答案标为 hole；分母不变，可答数单独统计 |
| `lint` | 只检查字符串闭合；额外 warning：`mutation escape: coverage unknown` |

- 代价：5 条全部变成 opaque 变异；LOAD/STORE 和 BUILD_VECTOR 的答案只能由对拍给出。
- 好处：改动最小（一个 primary + 一个发射分支 + 一个 core 字段），**现在就能到 0 拒绝**。
- 后续可以逐条把它替换成结构化表达式（方案 C），不影响其他规则。

### 方案 C：完全结构化（工作量最大）

需要的语法/原语：

1. `host("C++ 表达式")`：`Int` 类型的宿主值，供 `int_of_size`、比较、`select` 使用。
2. 一个“非原子”ordering 常量（C++ 的 `AtomicOrdering::NotAtomic` 目前没有标签）。
3. 可能还需要 `bit_floor(x)`（`fewerElementsIf` body 里用了 `llvm::bit_floor`）。
4. 变异体读取器支持“提前 return”折成嵌套 `select`。

- 好处：这 5 条仍可被 `eval`/`graph` 求值，覆盖率可以声称到规则级。
- 代价：4 个语法点 + 读取器改造；`fewerElementsIf` 的 body 还有
  `scalarOrVector(ElementCount::getFixed(n), EltTy)` 在 `n == 1` 时退化成标量，
  要确认 `vec_of(1, T)` 的语义与之完全一致，否则会引入静默错误。

## 5 建议

先做 §2 的 5 条（无需批准），把语料推进到 **5 refused**；然后按**方案 B** 落地，
到 **0 refused**，并在报告里明确“5 条规则的变异是受控逃逸点，答案以对拍为准”。
方案 C 作为后续可选的结构化收益，不阻塞本次接入。

## 6 需要批准的具体问题

1. 是否同意方案 B 的新语法 `mutate("...")`（只用于变异目标）？
2. 是否接受“AMDGPU 0 拒绝，但其中 5 条变异为 opaque”这个结论口径？
3. 若不同意 B，是否选 A（停在 5 条 deviation）或 C（继续扩 `host`/`bit_floor`）？

批准后我会按顺序做：§2 的导入器 5 条 → 方案 B 的语法与三出口 → 逐 ruleset
比对规则数 → `--all --check` 9/9 → 全量 pytest → 更新 REPORT-amdgpu → 分笔提交。
