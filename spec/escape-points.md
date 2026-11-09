# 逃逸点：`feature` 与 `opaque`

状态：规范性（2026-11-09）。适用于 `.gisel` v0.1 与 core schema 0.4。

DSL 在**结构层**是封闭的：opcode、slot、动作、谓词组合、断言值都由 gisel
完整理解。它只在两处把宿主 C++ 原样转抄出去，这两处就是本文定义的**逃逸点**
（host escape point）。逃逸点不是缺陷，而是设计取舍；代价是分析范围必须分层
陈述，不能一边保留任意 C++，一边宣称无条件完整理解每条规则。

## 0 一句话

| 口 | 一句话 | 分析时怎么处理 |
|---|---|---|
| `feature` | 构造函数期求值的 Bool，进配置轴 | 按配置枚举展开；不求值表达式内部 |
| `opaque` | 规则谓词里的宿主 Bool，gisel 不求值 | 洞（hole），不是 `false`；不参与等价类划分 |

**没有第三个口。** 变异（`widen`/`narrow`/`more`/`fewer`/`replace`/`mutate`）
的位置目前不接受宿主表达式；见 §4。

## 1 边界总表

| | `feature NAME = <C++>` | `opaque("<C++>")` |
|---|---|---|
| 语法位置 | 顶层声明右侧 | 只作谓词 primary |
| 求值时机 | legalizer **构造函数** | 每次 `getAction` 的规则 lambda |
| 可见对象 | `ST`/`STI`/`TM`/`Subtarget`/`XLen`、已声明 feature 名、命名空间常量 | 上列对象 + `Query`（lambda 参数） |
| 必须是 Bool | 是（Gisel 不类型检查，C++ 编译期兜底） | 是（同上） |
| `--emit=inc` | 生成 `bool NAME = <C++>;`，按依赖拓扑排序 | 在规则里生成 `(<C++>)` |
| `--emit=core` | 只以 `hasFeature` 叶子的表达式出现 | 去重写入顶层 `escapes` |
| `--emit=check` | 不出现 | `escapes` 的值 = 不同 `opaque` 表达式的条数 |
| 进配置轴 | 是（被规则引用时） | 否 |
| `gisel eval` | 查 feature 真值表；缺行报 `unknown_feature` | 抛 `EvalError("opaque")` |
| `gisel graph` | 每个配置一张图 | 该状态计 `opaque`，不建边 |
| `gisel cases` | 按配置派生/过滤题面 | 不能给出确定答案；不是 `false` |

## 2 `feature`：配置轴

### 2.1 契约

`feature NAME = <expr>` 声明一个**构造函数期**的 C++ bool。`--emit=inc` 把它
原样写成构造函数 prologue 里的 `bool NAME = <expr>;`，因此 `<expr>` 只能读
构造函数作用域可见的东西：

- 允许：`ST`、`STI`、`TM`、`Subtarget`、`XLen` 这类构造期对象；
- 允许：同一文件里已声明的 `feature` 名（SPIR-V 的
  `Spv_IsExtendedInts = Spv_hasArbitraryPrecisionInts || ...`）；
- 允许：`CodeModel::Small`、`SPIRV::Extension::...` 这类命名空间常量；
- **禁止**：`Query`、`MMODescr`、`MMO`、`MI`、`MRI`、`MF`——它们只在
  `getAction` 的查询/机器指令作用域里存在。

最后一条由 `gisel/ast.py:feature_scope_error` 在解析期强制：命中即
`path:line: feature F reads 'Query'; ...`，退出码 2。这是**整标识符**黑名单，
不是 C++ 解析器；它只拦“必然编译不过”的写法，不承诺理解表达式语义。

`feature` 右侧的完整 C++ 类型正确性不由 gisel 保证：gisel 不持有 `Subtarget`
接口。写错成员名、返回非 Bool，只有 C++ 编译期能发现。这是明确的**不承诺**。

规则里使用 feature 有两种写法，语义相同：

```gisel
feature HasAVX = Subtarget.hasAVX()
legal (HasAVX and in(slot(0), X86_Vec256))
legal feature("Subtarget.hasAVX()")      // 兼容旧语料；新语料写名字
```

`feature("...")` 的表达式文本必须与某个 `feature NAME = ...` 完全一致；否则
`lint` 与三个 `gen` 后端都报 `undeclared feature expression`。这条门禁在
`cli._generate` / `cli._lint` 共用，不由某个后端单独决定。

### 2.2 分析范围

- 一个 feature 只有**被规则引用**时才成为配置轴；声明了但没规则用，不产生题。
- `gisel cases` 默认从 `hasFeature` 叶子派生 `none` / `all` / `only-N` 配置，
  或用 `--features` 读显式真值表。所有结论都以“枚举到的配置”为前提。
- gisel 不推理 feature 表达式之间的布尔关系（例如
  `HasBWI = hasAVX512() && hasBWI()` 与 `HasAVX512` 的蕴含）。配置轴没枚举全，
  完备性就不成立；这是配置轴层的边界，不是结构层的漏洞。

## 3 `opaque`：谓词洞

### 3.1 契约

`opaque("<C++>")` 只能出现在**谓词**位置。它把宿主 C++ bool 原样转抄进规则
lambda：

```gisel
legal opaque("isLoadStoreLegal(ST, Query)")
```

- `--emit=inc`：`return (isLoadStoreLegal(ST, Query));`
- `--emit=core`：表达式去重后进入顶层 `escapes`，源文件顺序；
- `--emit=check`：`escapes` 计数与 core 数组长度一致；
- `gisel eval`：抛 `EvalError("opaque", ...)`，是洞，不是 `false`；
- `gisel graph`：状态记 `opaque` 出口，不建后继边；
- `gisel cases`：含该 guard 的规则不能由 gisel 给出确定答案；严格覆盖率会把
  它暴露成无 witness / 未覆盖，而不是悄悄当成不匹配；
- `gisel lint`：只检查字符串闭合，不检查 C++ 语义。

`opaque` 的作用域比 `feature` 大：`Query` 是规则 lambda 的参数，构造函数里的
`ST`/`STI` 被 `[=]` 捕获，两者都可见。因此它适合接住 target 文件里的任意
helper；代价是答案只能由对拍给出。

### 3.2 不承诺

- 不参与等价类划分，不进配置轴；
- 不承诺是 Bool，不承诺无副作用，不承诺可终止；
- 含 `opaque` 的规则，gisel 不宣称“有遗漏/无冗余/无环”这类结论；
- 不能把类型结构藏进 `opaque`：如果一条规则的**类型测试**本身是不透明的，
  等价类的分母就失去依据，题面只剩结构骨架。

## 4 第三个口：变异侧（当前不存在）

变异位置不接受宿主表达式。`widen(slot(0), opaque("host()"))` 在解析期即
`expected expr, got STR`，退出码 2。AMDGPU 需要的
`mutate("moreElementsToNextExistingRegClass(0)")` 提案见
`docs/PROPOSAL-host-escape.md`，状态是**不采纳（2026-11-09）**。

将来若要新增变异逃逸口，必须先经批准，并同时定义：

1. `--emit=inc` 的拼接位置与作用域；
2. `--emit=core` 的 `escapes` 记录方式（必须能区分谓词口与变异口）；
3. `eval` 的洞错误码（例如 `opaque_mutation`）；
4. `graph` 的出口计数、`cases` 的 hole 标记、`lint` 的 warning；
5. 对现有语料与冻结产物的影响。

只加语法、不定义这五项，等于把不可分析性藏进产物，不允许。

## 5 分析范围矩阵

| 问题 | 只有 `feature` | 规则含 `opaque` |
|---|---|---|
| 有遗漏吗 | 在枚举到的配置轴下可答 | 结构层可答；谓词层不可答 |
| 有冗余吗 | 结构层可查；谓词重叠按配置展开 | 不能判该规则的谓词重叠 |
| 会死循环吗 | 动作转移图可查，按配置分图 | 该状态计 `opaque`，可达性有缺口 |
| 写多少测试够 | 分母 = 类型等价类 × 配置轴 | 分母不变，可答数单独统计 |
| 对吗 | 与参考实现对拍 | 只能靠对拍；gisel 不推理 |

这就是“结构封闭 + 显式受控逃逸”的准确含义：**结构层完整理解，谓词层按
注册表/不透明条件处理，结论必须带范围。**

## 6 不变量与审计

- **I1**：同一份 `.gisel`，`--emit=core` 的 `escapes` 数组与 `--emit=check`
  的 `escapes` 计数必须相等，且都等于 `ast.host_escapes(program)` 的长度。
- **I2**：`escapes` 去重、保持源文件顺序；`grep -c 'opaque("'` 是**出现次数**，
  有重复时会大于数组长度，不能直接当审计等式。
- **I3**：`feature` 右侧不得出现 §2.1 的查询作用域名。
- **I4**：`opaque` 只出现在谓词位置；变异位置必须继续报解析错误。
- **I5**：新增任何宿主 C++ 通道都必须经项目负责人批准，并更新本文与
  `spec/grammar.md`。

审计命令（对每份语料都应成立）：

```bash
python3 - <<'PY'
from pathlib import Path
from gisel import ast
for p in sorted(Path("tests/corpus").glob("*.gisel")):
    gs = ast.parse_program(p.read_text())
    print(p.name, len(ast.host_escapes(gs)))
PY
```

```bash
python3 -m gisel gen tests/corpus/X86LegalizerInfo.gisel \
  --emit=core --out /tmp/x.core.json
python3 -m gisel gen tests/corpus/X86LegalizerInfo.gisel \
  --emit=check --out /tmp/x.check.json
python3 -c 'import json; print(len(json.load(open("/tmp/x.core.json"))["escapes"]), json.load(open("/tmp/x.check.json"))["escapes"])'
```

## 7 当前清点（2026-11-09，pin 语料）

| 语料 | 规则 | feature 声明 | `opaque` 出现 |
|---|---:|---:|---:|
| AArch64 | 744 | 10 | 0 |
| ARM | 96 | 10 | 0 |
| M68k | 13 | 0 | 0 |
| Mips | 95 | 3 | 0 |
| PowerPC | 25 | 0 | 0 |
| RISC-V | 402 | 25 | 0 |
| SPIR-V | 353 | 6 | 0 |
| WebAssembly | 109 | 2 | 0 |
| X86 | 328 | 16 | 0 |

九份语料全部只用了 `feature` 这一个口；`opaque` 目前是**已定义、已测试、
但语料未使用**的通道（`tests/test_opaque.py` 锁住语义）。因此把 `check` 的
`escapes` 从硬编码 0 改成真实计数，不改变任何冻结产物。

## 8 变更控制

以下改动属于**逃逸点契约**，必须先写 `docs/PROPOSAL-*.md` 并经项目负责人
（用户）明确批准：

- 新增/删除宿主 C++ 通道；
- 改变 `feature` 的允许作用域，或把 `opaque` 扩展到谓词之外；
- 改变 `escapes` 的语义、去重规则或计数口径；
- 把 `opaque` 纳入等价类/配置轴/自动求值。

判断标准与 `docs/SCOPE.md` §6 一致：**`.gisel` 的写法或分析承诺变了没有。**
变了就停，等批准。仓库根 `AGENTS.md` 是这条规则的执行面。
