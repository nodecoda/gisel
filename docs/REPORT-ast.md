# AST 迁移报告：让 `.td` 成为第 5 个渲染器

> 历史快照：本文记录 2026-11-06 的迁移，文中的测试数、`8/8`、`332/743` 条
> 规则都是当轮数字。当前值见 `README.md`（2026-11-11：243 tests / 92 subtests、
> 九份 artifact `9/9`、X86 328 / AArch64 741 条）。

状态：完成。基线 `35ad508`，本次改动不碰 `tests/corpus/*.gisel` 与
`tests/artifacts/*`。唯一新增的模型是 `gisel/ast.py` 的 `Program`。

> 历史说明：本报告写作时 `.td` 仍是第 5 个渲染器，`--emit=table` 也还在。
> 后续 `docs/REPORT-no-td.md` 已移除 `--emit=td`、`gisel/td.py` 和 bootstrap，
> 2026-11-09 又移除了 `--emit=table` 和 `gisel/backend/table.py`。文中涉及
> `.td`/`table` 的“当前状态”请以那两份记录为准。

## 1 拆掉了什么

迁移前，`parse_gisel` 直接把 `.gisel` 降级成 TableGen record 形状的 dict；
五个后端再各自把这层壳剥掉。现在前端只产出 AST，五个后端都吃 AST。

| 旧耦合 | 旧位置 | 现在的状态 |
|---|---|---|
| 解析即降级成 record 模型 | `td.parse_gisel`（已删除） | `ast.parse_program` 产出 `Program`（`gisel/ast.py:500`）；`cli._generate` 只接收 `Program`（`gisel/cli.py:49`） |
| record 名进入语义层 | `td.build_names` / `Names`（已删除） | 规则类型位置是 `LLT | SelectValue | SetValue`；`NameTable` 在 `.td`/`.inc` 出口把值映射回记录名（`gisel/ast.py:742`） |
| 类型是 C++ 文本，后端再解析 | `table.Resolver`（已删除） | `table.table_types` 直接分派结构化 `LLT`（`gisel/backend/table.py:47`）；`collect_classes`/`collect_mem_classes` 不再解析字符串（`:78`） |
| 为 record 形状做规范化 | `dsl.canonicalize_rulesets`（已删除） | `ast.canonicalize_rulesets`（`gisel/ast.py:897`），显式 AST 变换，注释写明“介质约束，不是语言约束” |
| tblgen 默认值泄漏到 CLI | `cli._table_prefix` 的 dict 分支 | 行为不变（仍从 ruleset 名/文件名推导前缀），只改成读 `Program`（`gisel/cli.py:15`） |

另外：

- `dsl.undeclared_features` 的 record-dict 版本删除；`ast.undeclared_features`
  遍历 `Rule.predicate/on/to`（`gisel/ast.py:715`）。
- `dsl.py` 里只为 dev harness 存在的 `main()`、`roundtrip_corpus`、
  `forward_roundtrip`、`normalize_nary` 删除；它们硬编码
  `/home/ubuntu/legalizer-baseline` 与 `llvm-tblgen`，不属于发布路径。
- `td.parse_gisel` 与 `dsl.canonicalize_rulesets` 删除后，仓库里没有第二个
  `.gisel` 文件级解析器。`A.to_record_model` 保留为**测试/oracle 适配器**
  （`gisel/ast.py:863`），生产后端不再调用它。

## 2 AST 规格（最终）

```
Program  := Include* Decl* RuleSet*
Decl     := Feature(name, cxx) | NamedType(name, LLT, source)
          | PredicateDecl(name, pred, source)
          | SelectType(name, arms, otherwise, value)
          | TypeSet(name, members, source_ref, value)
          | TypeList(name, members, value)
RuleSet  := (name, opcodes, rules, comments, coverage, line)
Rule     := { op, action, type_idx, on?, to?, predicate, line }
LLT      := Scalar(bits) | Integer(bits) | Float(bits) | BFloat16
          | Pointer(addrspace, bits|None) | Vector(lanes, scalable, elem)
TypeValue:= LLT | SelectValue | SetValue
```

- `Pointer` 的 `bits=None` 就是 `pN:*`；宽度是字段，不是字符串。
- `SelectValue.legacy_guard` 只记录 core 序列化的历史形态（declaration 走
  `nary`/`not(arg)`，inline `select_type` 走 `all`/`any`），不是语言语义。
- `RuleSet.name` 是输出标签；`core`/`check`/`table` 从不把它当语义。
- `Include` 是 render-only 字段：`.td` 要原样输出 include 行，所以它留在
  AST；没有任何语义层读取它。

## 3 每处 record 词汇的去留

| 词汇 | 去留 | 说明 |
|---|---|---|
| `LegalizeRuleSet<[...]>` | 只在 `.td` | `td._emit_ast_decl`/`emit_td` 输出；AST 用 `RuleSet` |
| `LegalizeFeature<"...">` | 只在 `.td` | AST 用 `Feature(name, cxx)` |
| `LegalizePredicateDag<...>` | 只在 `.td` | AST 用 `PredicateDecl.pred`（语义树） |
| `LegalizeNamedType<"...">` | 只在 `.td` | AST 用 `NamedType(name, LLT, source)` |
| `LegalizeSelectType<...>` | 只在 `.td` | AST 用 `SelectType.value`（`SelectValue`） |
| `LegalizeCoreTypeSet<...>` | 只在 `.td` | AST 用 `TypeSet.value`（`SetValue`） |
| `LegalizeNamedTypeList<...>` | 只在 `.td` | AST 用 `TypeList.members/value` |
| `X86_s32` 等记录名 | `.td`/`.inc`/`table` 的出口 | `NameTable` 在渲染时计算；`--emit=core` 输出 `s32`，`--emit=check` 不涉及 |
| `LLT::scalar(32)` 文本 | `NamedType.source` + `.inc`/`.td`/`table` 输出 | 前端只在 `type` 声明右侧解析一次（`ast._parse_llt`） |
| `include "..."` | AST `Include` + `.td` 输出 | 仅渲染 |

`--emit=table` 的 C++ 前导仍会写 `const LLT X86_s32 = LLT::scalar(32);`：
那是产物要求的拼写，由 `emit_prologue` 在出口重拼，AST 里没有 `X86_`。

## 4 否决了什么

1. **保留 record dict 作为规范模型，再挂一层 AST。** 这会变成第二套 IR，
   而且五个后端仍会各自剥壳。否决。
2. **只让 core/check 吃 AST，td/inc 继续用旧 parser。** 这等于保留两个前端，
   正好违背“`.td` 是第 5 个渲染器”的目标。否决。
3. **把记录名存进 AST 以保留被遮蔽的类型名。** 记录名是渲染细节；存进去会
   把 TableGen 形状重新带回模型。改为 renderer 的 last-declaration-wins 映射。
4. **让 `canonicalize_rulesets` 按语义相等分组（忽略行号）。** 旧变换的 key
   含 `_line`，RISCV 的产物是 91 表 / 413 条；按语义分组会得到 78 / 400，
   改变 core JSON 契约。否决，保留行号并写进注释。
5. **从 AST 删除 `includes`。** `.td` 必须原样输出 include 行；删掉会改
   golden。保留为 render-only 字段。

## 5 迁移顺序与回滚点

1. **Phase 1**：新增 `gisel/ast.py` 与 `to_record_model`；用冻结摘要锁住
   5 份语料的旧 record 模型（`tests/test_ast.py` 的 `MODEL`/`CANON`）。
   回滚点：删 `ast.py`，恢复 `td.parse_gisel` 即可。
2. **Phase 2**：按 `td -> inc -> check -> table -> core` 切换。每切一个都跑
   70 tests、8/8 artifacts、lint 计数与字节 `cmp`。`td`/`inc` 先保留
   “AST -> 局部 record view”的出口转换，`check`/`table`/`core` 直接读 AST。
   回滚点：每个后端一个 commit/补丁，可单独恢复其旧分支。
3. **Phase 3**：删除 `build_names`/`Names`/`collect_named_sets`/`Resolver`/
   `normalize_llt`/旧 `parse_gisel`/旧 `canonicalize_rulesets`，把 bootstrap
   的命名逻辑收进 `_ScaffoldNames`（`gisel/td.py:257`）。回滚点：恢复这些
   函数与 `parse_gisel`；产物不受影响，因为 Phase 2 已经证明 AST 路径逐字节
   一致。

## 6 产物证据（本次运行）

```
python3 -m unittest discover -q -s tests          # 70 tests OK
(cd tests/artifacts && sha256sum -c SHA256)       # 8/8
gisel lint X86LegalizerInfo.gisel                 # 0 error, 5 warning, 332 rules
gisel lint AArch64LegalizerInfo.gisel             # 0 error, 5 warning, 743 rules
gisel gen X86... --emit=inc | cmp x86.inc         # byte-identical
gisel gen X86... --emit=td  | cmp golden/x86.td   # byte-identical
check/table/core for x86 & aarch64                # byte-identical (core modulo origin)
gisel bootstrap golden/x86.td x86.core.json       # 与 corpus 逐字节相同
gisel gen RISCV... --emit=inc                     # 402 rules, 0 rejects
gisel eval aarch64.core.json ...                  # 当时的 9632 点答案表，已删除
```

## 7 已知边界

1. **被遮蔽的 NamedType 在规则里不可区分。** `NameTable` 和旧
   `build_names` 一样是“后声明者胜”。RISCV 有 `R_sXLen_lo` 与 `R_s32`
   都归一化成 `s32`，但语料只在 `select R_sXLen = if ... else R_sXLen_lo`
   的声明里用被遮蔽名，规则本身用 `R_s32`；因此产物不受影响。若未来语料
   在规则里直接写被遮蔽名，AST 无法保留这个拼写。届时的最小修法是给
   `NamedType` 加 render-only `source_name`，而不是把记录名放回语义。
2. **未声明的类型名以字符串暂存。** `parse_program` 对规则位置解析不到的
   名字保留原文，交给 J1 报 `unknown type name`；`gen` 在出口拒绝
   （`CoreJson.type_json`/`NameTable.value_name`）。合法程序的规则类型位置
   全是结构化值；`tests/test_ast.py` 对 5 份语料断言了这一点。
3. **`type_set` 声明的成员是 eager 解析。** `type_set X = [s8]` 若 `s8`
   没有声明，会在 parse 阶段失败（exit 2）；旧前端会保留到 lint。这是
   唯一一处对非法输入的行为收紧；现有语料与测试不受影响。
4. **`bootstrap` 的 `--title` 默认值改为从 `.td` 的记录前缀推导。**
   这是为了让 `bootstrap --td tests/golden/x86.td ...` 直接重建
   `X86LegalizerInfo.gisel`（文件名是 `x86.td`，不能只靠 stem）。显式
   `--title` 仍是原语义。
5. **grep 门禁的字面命中。** `grep -rn 'LLT::scalar\|LegalizeFeature\|X86_' gisel/ --include=*.py`
   只剩 10 行，全部在渲染器/反向读取器里：
   - `gisel/dsl.py` 的 `TdEmitter`/`_llt_leaf`；
   - `gisel/td.py` 的 `_emit_ast_decl`/`SCAFFOLD_CLASSES`/bootstrap 注释；
   - `gisel/backend/llvm_inc.py` 生成的 C++ 拼写；
   - `gisel/backend/table.py` 生成的 C++ 注释。
   前端不再出现 `LLT::scalar` 字面量：`ast._parse_llt` 用通用的
   `LLT::<kind>(args)` 分派解析 `type` 声明。没有命中的是“把 record 名/
   C++ 文本当语义输入解析”的代码——那类代码已经删除。
6. **`to_record_model` 仍存在。** 它是 `tests/test_ast.py` 的冻结摘要
   适配器，生产路径不调用；保留它是为了让迁移前后的字段级对照可复现，
   不是第二套模型。
