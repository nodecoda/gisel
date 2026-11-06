# `.gisel` grammar (v0.1)

状态: 规范性。实现: `gisel/td.py:513`（`parse_gisel`，文件级）与
`gisel/dsl.py:149`（`Parser`，规则级）。语料: `tests/corpus/*.gisel`
（778 + 1310 行，1075 条规则，有 `.td` 对照）；
另有两份**无 `.td` 的探针语料** `M68kLegalizerInfo.gisel`（44 行 / 13 条）与
`WebAssemblyLegalizerInfo.gisel`（228 行 / 108 条），见 `docs/REPORT-wasm.md`。
另有导入器产物 `RISCVLegalizerInfo.gisel`（402 条规则 / 96 个 ruleset，由
`tools/import-cxx.py` 从 C++ 构造函数生成，见 `docs/REPORT-riscv.md` §7）；
它没有 `.td` 对照，只作为「语料是否可表达」的证据。
任何语法改动都必须让这几份语料 round-trip。

## 1 词法

- 行注释 `// ...`；空行忽略（`td.py:520-524`）。
- 缩进敏感：规则体用 Python 风格 `INDENT`/`DEDENT` 分组，只计前导空格
  （`dsl.py:99-115`）。
- 标识符 `[A-Za-z_][A-Za-z0-9_]*`；关键字就是这些标识符（无保留字表）。
- 类型字面量（`dsl.py:84-85`）:
  `[nx]v<lanes>` 可选前缀 + `s<bits> | i<bits> | f<bits> | bf16 | p<as>:<bits> | p<as>:*`。
  例: `s32`、`i8`、`f16`、`bf16`、`p0:64`、`p0:*`、`v4s32`、`nxv16i8`、`v2p0:*`。
- 整数、双引号字符串、标点 `( ) , [ ] :`、比较符 `== != <= >= < >`。
- 长规则可在括号内换行续写；`_join_continuations`（`td.py:482`）按括号深度拼接。

## 2 文件结构

```
program    := { toplevel }
toplevel   := include | decl | ruleset
include    := "include" STRING                     // 原样进 .td
decl       := feature | named_type | select_type | predicate | type_set | type_list

feature    := "feature" ID "=" <C++ bool expr>      // 余下整行原文
named_type := "type"    ID "=" <C++ LLT expr>       // 例 LLT::scalar(32)
select_type:= "select"  ID "= if" predicate "then" type "else" type
predicate  := "pred"    ID "=" pred
type_set   := "type_set"  ID "=" "[" type {"," type} "]" | ID ".Elems"
type_list  := "type_list" ID "=" "[" type {"," type} "]"
```

`feature`/`type` 的右侧是**原文**，只有 `select`/`pred`/`type_set` 会被解析
（`td.py:361-365` 的 `DECL_RE`）。名字区分大小写；生成 `.td` 时再解析回
target 的记录名（`td.py:317` `build_names`）。

## 3 规则集

```
ruleset    := "ruleset" ID ":" opcode { opcode } NEWLINE INDENT { statement } DEDENT
statement  := "note" STRING | "imm_idx" "(" INT ")" | rule

rule       := terminal | lattice | scalarize | clamp
terminal   := ("legal"|"lower"|"custom"|"unsupported"|"libcall") pred
lattice    := ("widen"|"narrow"|"more"|"fewer") "(" expr "," expr ")"
              [ "when" pred ]
bitcast    := "bitcast" "(" expr "," expr ")" [ "when" pred ]
scalarize  := "scalarize" "(" expr ")" [ "when" pred ]
clamp      := ("clamp_min"|"clamp_max") "(" INT "," type "," expr ")"
```

- 一个 `ruleset` 可以挂多个 opcode；规则按书写顺序匹配（`evaluate:860`）。
- `note` 是注释的载体（进 `.td` 的 `Comments`）；`imm_idx(n)` 是覆盖标记，
  不是 core 规则（`tests/test_artifacts.py:90` 计数 1078 = 1075 + 3）。
- `clamp_min/max` 是**语法糖**，前端展开成一条 `more`/`fewer` 规则：四个 guard
  （是向量、不是可伸缩向量、元素类型相等、lane 数越界）加
  `replace(vec_of(n, elem_of(slot(i))))`（`dsl.py:478-497`）。

## 4 表达式

```
expr   := INT | type | ID | call | "imm" "(" INT ")"
call   := ID "(" [ expr {"," expr} ] ")"
```

`ID` 三种含义：零元构造子（`pow2`、ordering 标签）、命名类型/谓词、函数调用。
一元观察子与构造子见 `dsl.py:66-82`（`UNARY_CALL`、`BINARY_CALL`）；
`slot(i)`、`mem_slot(i)`、`imm(i)` 是特例（`dsl.py:45`、`ZERO_ARG`）。

`imm(i)` 读 `Query.Immediates[i]`，sort 是 `Int`，只能出现在谓词里（不是类型，
不能当 `widen` 的目标）。它没有 arity 可检查：`GenericOpcodes.td` 只描述类型槽，
所以 `imm(9)` 不会被 J3b 拦下。

## 5 谓词

```
pred       := conj { "or" conj }
conj       := unary { "and" unary }
unary      := "not" unary | primary
primary    := "(" pred ")" | "true" | "feature" "(" STRING ")"
            | membership | expr ("=="|"!="|"<"|"<="|">"|">=") expr
            | expr                              // 布尔观察子可单独作谓词

membership := "in" "(" expr "," (type | "[" (type | INT) {"," (type | INT)} "]") ")"
            | "in_pairs"   "(" expr "," expr "," "[" pair {"," pair} "]" ")"
            | "in_triples" "(" expr "," expr "," expr "," "[" triple {"," triple} "]" ")"
            | "in_mem_desc" "(" expr "," expr "," expr "," "[" memrow {"," memrow} "]" ")"

pair    := "[" type "," type "]"
triple  := "[" type "," type "," type "]"
memrow  := "mem_desc" "(" type "," type "," type "," INT ")"
```

- `or`/`and`/`all_of`/`any_of` 都是 n 元、扁平（对应 `CoreAny`/`CoreAll`）。
- 规则里的类型**必须是已声明的名字**：`type` / `select` / `type_set` 任一。
  `in(slot(0), i32)` 里的 `i32` 是 LLT 字面拼写，不是名字，J1 报
  `unknown type name 'i32'`。这条不是风格要求——三个发射后端都要把名字解析回
  记录名（`core_json.type_name` / `td._type` / `llvm_inc._type`），字面拼写在
  其中任何一处都没有对应的记录可指。`type` 声明的右侧才是 LLT 表达式。
- `in(slot(i), S)` 的 `S` 可以是单类型、内联集合或命名 `type_set`；
  `in(imm(i), [8, 16])` 是立即数集合。集合是**同质**的：`in` 的左侧 sort 必须
  与集合元素 sort 一致（`Int` 集合配 `imm`，`Type` 集合配 `slot`），否则 J1 报
  `in: Int set cannot test Type (element sort mismatch)`。
- 单个立即数写作比较：`imm(0) == 32`（`immIs`），不像类型那样有「单元素集合就是
  类型本身」的退化写法。
- 集合字面量只能作为 `in*` 的**最后一个**实参——这是文法结构，不是约定
  （`dsl.py:285-311`）。
- `mem_desc(t0, t1, mt, align)`：两槽类型 + 内存类型 + 对齐（位）。

## 6 正常形（schema 0.4）

`--emit=core` 输出的 JSON 是契约：`schema/version/config/escapes/domain/rulesets`，
每条规则 `{predicate, op, on, to, action, type_idx?, origin}`。
`domain.imms` 是谓词里出现过的 `imm(i)` 的**下标**集合（升序去重），
和 `domain.types` 并列；LLVM 侧的同名字段目前恒为 `[]`（`LegalizerInfoEmitter.cpp:4933`）。三处重拼
（记录名→LLT、指针通配符、`select` 类型）见 `gisel/backend/core_json.py:1-15`
与 `spec/m4-scope.md`。

## 7 静态诊断（`gisel lint`）

`gisel lint SOURCE [--manifest PATH] [--json] [--max-errors N]` 在不调用
LLVM 的前提下检查每条规则：

| 检查 | 内容 | 实现 |
|---|---|---|
| J1 | 表达式/谓词的 sort（Type/Int/Bool/Kind/Set/Ordering/MemDesc） | `dsl.py:_tc` |
| J2b | 比较两侧 sort 相同且可比较；`select` 分支同 sort | 同上 |
| J3a | action 的 `(operator, target-sort)` 全函数 | `TARGET_SORTS` |
| J3b | `slot(i)` 的 `i < arity` | `check_rule` |

诊断格式 `path:line: RULESET: message`；`--json` 输出
`{source, errors[], warnings[], rules}`。退出码：0 无 error，1 有 error，
2 源/IO/解析错误。

arity 来自随包分发的 `gisel/data/generic_opcodes.json`（283 条，从
`GenericOpcodes.td` 的 `def`/`class` 继承链重建；`tools/gen-opcode-table.py`
仅开发期重算）。10 条变参指令（`G_PHI`、`G_INTRINSIC*` 等）没有固定 arity：
lint 对其 `slot` 上界跳过并输出一条 ruleset 级 warning，不静默通过。

## 8 已知边界

- 缩进只认空格；`\t` 不参与层级计算（语料全部用空格）。
- `type` 右侧做**形状检查**：只接受 `LLT::scalar/integer/pointer/`
  `fixed_vector/scalable_vector/float*`，可嵌套；无法规范化时 `parse_gisel`
  直接拒绝（exit 2）。任意 C++ 常量表达式（如 `LLT::scalar(8*4)`）会被拒——
  这是刻意的：能规范化才能进 core JSON 与 `.td` 的 `LegalizeNamedType`。
- `feature` 右侧**不检查**：它是 target 特定的任意 C++ bool 表达式，gisel
  不持有 `Subtarget` 接口；错误只能由 C++ 编译期暴露。
- 规则里的 `feature("...")` 必须与某个 `feature NAME = ...` 的表达式文本完全
  一致，否则 `gen --emit=inc` 报 `undeclared feature expression`。
- 顶层声明顺序即 `.td` 中的声明顺序；`include` 行原样保留，由 `--emit=td` 输出。
- `type_set X = Y.Elems` 是引用，不是拷贝（`td.py:129-131`）。
- 语法错误报 `path:line: message`（exit 2），行号是 `.gisel` 的物理行；
  被续行拆开的规则报该语句的起始行（`td.py:482` 的 line map）。
- `lint` 只做单步静态检查，不求值、不检查终止性；求值见 `gisel eval`。
- `imm(i)` 没有下界检查（见 §4）：`imm(7)` 在只有 1 个立即数的指令上不会被 lint 拦下。
- `--emit=td` 会把立即数规则写成 `(CoreIn (Imm 0), [8, 16])`，而 LLVM 侧的
  `LegalizerCore.td` 还没有 `CoreImm`；AArch64/X86 不用 imm，所以现有 8 份产物不受
  影响。要让生成的 `.td` 能被 `llvm-tblgen` 吃下，`LegalizerCore.td` 需补一个
  `CoreImm`（sort `Int`）并让 `CoreIn` 接受 Int 集合。
- 多 opcode 的 ruleset 用 `min(arity)` 做 J3b（`dsl.py:check_rules`），这是
  保守下界，不是 per-opcode 精确检查。
- 导入器（`tools/import-cxx.py`）的产物暴露了三条表达边界，均**不改语法**：
  - 整型 subtarget 值（`ST.getXLen()`）不是 `feature`（bool）：用在比较右侧时
    换成 `select(feature("XLen == 64"), 64, 32)`。`feature` 只有 Bool 一种 sort。
  - `select` 的条件只认**名字**（`feature` 或 `pred` 记录，`td.py:_parse_sel`），
    内联的 `feature("...")` 复合表达式要先落成 `pred`；类型位置的 ternary 同理。
  - `in(slot(i), X)` 的第二参是类型或类型集，不是 `ty(...)` 表达式
    （`dsl.py:313` `parse_set_or_type`）——`typeIs(i, T)` 要译成裸 `T`。
- 同一 opcode 允许多个 `ruleset`（C++ 里多次 `getActionDefinitionsBuilder`），
  按书写顺序匹配；但 `--emit=td` 的 def 名必须唯一，所以导入器会给重名的加
  `_2` 后缀。core JSON 里它们仍是两个 ruleset，`eval` 按 `by_opcode` 的顺序遍历。
