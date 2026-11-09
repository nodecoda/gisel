# 架构治理计划（Phase 1–2）

状态：**执行中**。Phase 0–P5 已完成并提交；P6 的文档对齐已开始（见 §8）。
D1/D3/D5/D6 按推荐执行；D2/D4 保持现状，不修改 `.gisel` 语法。

## 1 目标与非目标

目标（只解决这四类）：

1. 产品面只有一套事实：`--emit` 的三个产物、退出码、命令表，CI/README/spec
   不再各写一份。
2. 语义模型只有一个入口：AST 节点表、遍历器、LLT 工具各一处，`lint` 与
   `gen` 不再对同一条规则给出不同结论。
3. “有界商”的预算和域各有一个执行点：候选集上限、域内/域外判定、闭包审计
   共用同一谓词。
4. 把已经跑出来的数字写回文档：`REPORT-graph.md` 的 X86 数字、`REPORT-riscv.md`
   的规范化口径、`spec/cli.md` 的 check 口径。

非目标：不碰导入器（`tools/import-cxx.py`）、不复活 `.td`/`table`、不接 AMDGPU、
不实现 MIR 生成/动态 legalize、不改 `.gisel` 语法（除非 §4 的决策点被批准）。

## 2 不变量（任何一步都不能破）

| 编号 | 不变量 | 验证 |
|---|---|---|
| I1 | 9 份语料 `import-cxx --all --check` 全部 match | 见 §6 门禁 2 |
| I2 | 冻结产物 9 份字节不变（`tests/artifacts/SHA256`） | `tests/test_artifacts.py::ArtifactIntegrity` |
| I3 | `escapes` 在三个出口相等：`core.escapes`、`check.escapes`、`host_escapes()` | `tests/test_escape_points.py` |
| I4 | 退出码只有 0/1/2；写盘失败是 2，不是 traceback | `tests/test_cli_io.py` + `spec/cli.md` §2 |
| I5 | `gisel` 包不 import `tools/`、不起外部进程、不联网 | `tests/test_scope.py` |
| I6 | 同一输入逐字节同一输出（含 `graph --json`） | 复查命令见 §6 |

## 3 当前不一致（都是可复现的，不是推测）

1. **check 的口径没有写下来**。`gisel/cli.py:_generate` 对 `emit != "inc"` 都做
   `canonicalize_rulesets`。实测：AArch64 raw 117 rulesets / 741 rules，
   canonical 114 / 743 core rules（`check.json` 报 `rule_sets=114, rules=746,
   core_rules=743, coverage=3`）；RISCV 96/402 → 91/413；X86 63/328 恒等。
   `docs/REPORT-riscv.md:204-216` 说规范化是有意设计，`REPORT` 里 AArch64 却
   写成“恒等”。**结论：check 是 canonical 的，文档要统一。**
2. **lint 与 gen 对同一条规则结论不同**。`narrow(slot(0), 32)`：`lint` rc=0，
   `--emit=inc` rc=2 `no C++ shim for operator 'narrow' over 'slot' to 'int'`。
   原因：`dsl.TARGET_SORTS`、`eval` 的 shim 分支、`llvm_inc.SHIM_TABLE` 是三份表。
3. **规则类型位置有三种输入语言**。`type S32 = LLT::scalar(32)` +
   `legal in(slot(0), [s32])`：`--emit=inc` rc=0、`--emit=check` rc=0、
   `--emit=core` rc=2 `unknown type name 's32'`。`inc` 走 `llvm_inc._canonical`
   的 fallback，`core` 走严格解析。
4. **候选预算不是硬上限**。AArch64 `A_G_ADD` 单槽候选 **105**，默认
   `max_slot_values=16`；`cases._candidates` 用 `keep = max(cap, len(ordered))`
   保证“字面量不被截断”。所以 105 是设计结果，不是 bug——但文档把它写成 16，
   而 `domain` 侧又在 `list(enumerate_domain(...))` 之后才按 `max_points` 截断
   （`gisel/domain.py:279`），两处的“上限”含义不同。
5. **graph 的两套域**。`type V3S32 = LLT::fixed_vector(3, 32)` +
   `widen(slot(0), pow2_min(32))` → `states=2, edges=0, outside=1`：后继 `v3s64`
   被 `_class_key` 判 outside，图不建边。`--check-closure` 对 `outside` 状态只
   记录**代表点**，不展开成员，所以同类里的另一个成员（例如 `s33 → s64`）
   从未被审计。实测夹具：`S3/S33/S64 + widen(slot(0), pow2_min(32))` 只报
   `member=["s3"]`。
6. **`REPORT-graph.md` 的数字和实现已经分叉**：文档写 72,956 / 26,085 / 6 cycles，
   当前快照是 73,915 / 26,767 / 0；那 6 个“自然环”是 guard 未进类签名时的
   商类假阳性（`G_SMAX`/`G_SMIN`/`G_UMAX`/`G_INTRINSIC_*` 自环）。

## 4 决策点（需要拍板）

| # | 问题 | 选项 A（推荐） | 选项 B | 影响 |
|---|---|---|---|---|
| D1 | `check` 描述哪一层？ | **canonical**：check/core 都按 artifact 形比较；在 `spec/cli.md` 与 `spec/cases.md` 写明，并修正 AArch64 的“恒等”说法 | raw：为 raw builder 单开一套冻结产物 | A 只改文档；B 新增产物面 |
| D2 | `opaque` 出现在 type-position `select_type` 的 guard 里 | **允许并计数**（现状）：`core.escapes`/`check.escapes`/`host_escapes()` 三处相等；`cases` 对该 ruleset 报 `unexercised`（实测 0 case） | 禁止：parse 期拒绝 | A 不改语法；B 收窄语法，需你批准 |
| D3 | `pred` / `select` / inline `select_type` 三套 guard | **统一求解、分开序列化**：AST 统一成谓词 normal form；`legacy_guard` 只保留为 core JSON 的序列化 provenance（产物字节不变） | 三套各自维护 | A 是纯重构；B 继续三份逻辑 |
| D4 | inline `select_type` 在规则类型位置 | **承认现状**：parser 早已接受，Phase 0 修好了 core/inc 的实现崩溃；在 `spec/grammar.md` 补一行“type position 也接受 inline `select_type`” | 拒绝（收窄），把 `spec/grammar.md:173` 的“必须是已声明名字”变成硬约束 | B 需要你批准；A 只是让文档追上 parser |
| D5 | 候选预算的语义 | **软上限**：`max_slot_values` 是“至少这么多，且所有字面量必留”；在 `cases` 的 stats 里打印实际每槽候选数 | 硬上限：截断到 16，牺牲字面量 | A 保住 witness；B 会让部分规则永远无 witness |
| D6 | graph 的 `outside`/closure | **域判定单一谓词** `Domain.contains()`；图按代表点计数，closure 逐成员审计并分别计数 `partition`/`outside` | 保持现状（代表点制） | A 会改变 graph 输出数字，需重跑文档 |

D2/D4 若选 B 都属于收窄语法，按 `AGENTS.md` 必须你明确批准；其余四项是文档/
重构口径，可按推荐执行。

## 5 PR 序列

| 阶段 | 内容 | 交付物 | 风险 |
|---|---|---|---|
| P0 ✅ | 内联 select 修复、`host_escapes` 覆盖、写盘 rc=2、table 残留清理 | 3 笔提交（见 §7） | 无 |
| P1 | 单一事实源：`spec/cli.md` 写 check 口径；`REPORT-graph.md` 按当前快照重写数字与“假阳性”结论；`REPORT-riscv.md` 口径互链 | 文档 + `test_scope` 断言 | 低 |
| P2 | 抽 `gisel/llt.py`（LLT 解析/打印/bits/lanes/mutate）与 `gisel/analysis.py`（`document`/`derive_features`/`inspect_ruleset`/`type_value_spellings`） | 纯移动 + 再导出，行为不变 | 中（导入面大） |
| P3 | 抽 `gisel/nodes.py`：节点 kind 表、`walk_nodes`、`(op, observation, target)` 形状表；`host_escapes`/`undeclared_features`/lint 共用 | 删掉三份重复遍历 | 中 |
| P4 | CLI 单次解析：`prepare(emit)` 返回 `(program, doc)`，check/core 的 canonical 策略显式化；`lint` 与 `gen` 共用同一张 shim 表 | `lint`/`gen` 对 `narrow(slot(0), 32)` 结论一致 | 中 |
| P5 | 有界商单点：`Domain.contains()`、候选预算单点、closure 逐成员审计；`graph` 改迭代 DFS | graph 输出新增字段，数字重跑 | 中高 |
| P6 | 收尾：`--check-closure` 失败是否默认 rc=1 的产品口径（D6 决定后）；spec/REPORT 全量对齐 | `spec/graph.md`、`REPORT-graph.md` | 低 |

每个阶段独立可回滚：P2/P3 不改行为，P4/P5 各带自己的测试，产物只在
`tools/refresh-oracle.sh` 里刷新。

## 6 验证门（每阶段结束都跑）

```sh
# 1. 单元测试（当前 305 passed / 94 subtests；P2 起应只增不减）
python3 -m pytest -q

# 2. 语料与上游一致（9/9 matches，0 refused）
python3 tools/import-cxx.py --all --pin tests/corpus/PIN.json \
  --git-repo /home/ubuntu/llvm/llvm-project --check

# 3. 冻结产物不变
python3 -m pytest -q tests/test_artifacts.py::ArtifactIntegrity

# 4. 三个 target 的 core 生成 + 自检
for t in X86 AArch64 RISCV; do
  python3 -m gisel gen tests/corpus/${t}LegalizerInfo.gisel \
    --emit=core --out /tmp/$t.core.json
done
```

`graph` 的数字只在 P5 后允许变化，且必须把「命令 + sha + 输出」写进
`docs/REPORT-graph.md`。AArch64 baseline 的候选积（前一轮实测约 1.17M states，
900 s 未跑完）不在本轮修复范围；P5 只要求“可中断、可解释”，不承诺跑完。

## 7 已交付

| 提交 | 内容 |
|---|---|
| `066a9d6` | inline `select_type` 的元组 bug；`inc` 渲染内联 select；`walk_nodes` 覆盖 `SelectValue`/`SetValue`/`on`/`to` |
| `04c4c86` | `gisel/output.py`；`cases`/`domain` 写盘失败返回 2；`graph` 只算一次 `public()` |
| `6ff8af4` | CI/README/spec/RELEASING 去掉 `--emit=table`；历史报告加状态头；两个 meta-test |
| `5e56918` | 本文（Phase 1–2 计划） |
| `575df3d` | `gisel/llt.py`：tuple LLT 的 spell/bits/lanes/mutate/neighbours 单一实现 |
| `2074d5c` | `gisel/analysis.py`：document/derive_features/inspect_rule(set)/imm_candidates/type_value_spellings；`graph`/`domain` 不再反向依赖 `cases` 私有函数 |
| `b993b0c` | 分析读规则的**全部**字段（`on`/`to`/内联 select）；feature 只出现在 mutation 里也不再丢配置轴 |
| `db07b3b` | lint 与 `.inc` 共用 `shim_for`；所有出口都拒绝未声明类型（`[s32]` 不再 inc 能过、core 不能过） |
| `e44fc0d` | `graph.Domain.successor` 单点判定域外；closure 审计每个非 opaque 状态的全部成员；`--refine` 把“无后继”成员单独分桶；迭代 DFS |
| `ed1c005` | `cases` 打印软预算（`slot_budget`/`candidate_max`/`candidate_over_budget`） |
| `15c4fc3` | 文档对齐：`check`/`core` 是 canonical 形；graph/riscv 报告按快照重写 |
| `9e59c9d` | 形状过滤上移到 `analysis.type_shape_ok`，补 shift/rotate 条款；`graph` 对类元组做形状可行性判定并输出 `shape` |

验证：`310 passed, 94 subtests passed`；`import-cxx --all --check` 9/9 matches。

## 8 剩余

- P6 已完成：`docs/REPORT-graph.md` 绑定 `9e59c9d`；AArch64 的 147 个
  `G_ASHR` 2-环定性为 MIR 不可达形状（verifier 拒绝 `(vector, scalar)`），
  加形状过滤后 cycles=0，见报告 §5。
- D5 已落地：`cases` 的 stats 打印 `slot_budget` / `candidate_max` /
  `candidate_over_budget`；`spec/axes.md` 与 `docs/ALGORITHM-cases.md`
  已改成“软预算”。
- `analysis._walk_info` 与 `ast.walk_nodes` 已经是一套遍历；lint 的
  `TARGET_SORTS` 与 shim 表仍是两份，合表属于后续重构（不在 P0–P5 的验收里）。
