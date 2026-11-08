# 需求：LLVM legalizer 差分对拍工作台（AB harness）

状态：需求草案 v0.1。**这是工作台需求，不是 gisel 产品需求**；边界见
`docs/SCOPE.md`。实现对现有 `tools/ab/` 的归纳与缺口清单，不改变 gisel 的
两个功能。

## 0 名称

- 中文叫“对拍”或“差分测试”；英文是 **differential testing**。
- 本仓库的工作台叫 **AB harness**（`tools/ab/`）。不要叫 `gisel diff`：
  对拍动词已经移出产品 CLI。

## 1 目标

给定四个钉住的输入：

1. 一个 LLVM tree + build（官方分支，`.gisel` 就是从这棵树转出的）；
2. 一份 `.gisel` 源，或预生成的 `.inc`；
3. 一份 feature 真值表 / `--axes`；
4. 一份无答案查询 JSONL（`gisel cases` 或 `gisel domain`）；

产出：

- 官方实现的答案文件；
- include 我们 `.inc` 的实现答案文件；
- 逐 key 的差异报告；
- 可归因的 bundle（给 AI/人读）；
- 可重复的 ledger（每次跑了什么、输入是什么、差多少）。

成功标准：

1. **一条命令**跑完“官方构建 → 替换 inc → 重建 → 跑查询 → 对拍 → 恢复”。
2. 相同输入产生逐字节相同的答案和相同的 SHA。
3. 任何差异都能定位到 key、opcode、config、规则/产物。
4. 基线永远能恢复；失败不污染 build。
5. Phase 1 只比 `action`；Phase 2 比 `(action, type_idx, new_type)`。
   **Phase 1 不是最终验收**：action 相同、new_type 不同仍是差异。

## 2 非目标

- 不证明规则本身正确，只证明两个实现在查询集上一致。
- 不生成 MIR、不跑 `llc`、不做指令选择；只调用目标 `LegalizerInfo` 的
  `getAction`。
- 不调用 LLM；AI 归因在工具外，工具只产出确定性的 bundle。
- 不是 gisel 子命令；不随 wheel 发布。
- 不覆盖全部 subtarget；只覆盖 feature 表里的 config。
- 不把 `unanswerable` 当通过；它只表示“这次查询没有答案”。

## 3 端到端流程

### Stage 0 preflight

- 校验 tree/build/target adapter 匹配；记录 tree `HEAD`、build 配置、编译器版本。
- 校验查询文件：key 唯一、config 在表里、LLT 可解析、`mem/imms` 形状合法。
- 取得 baseline snapshot（inc、目标库、provenance）；没有就创建并冻结。
- 加锁，禁止两个 run 同时改同一个 build。

### Stage 1 生成 inc

- `gisel gen --emit=inc`；记录 sha256；可选 `gisel check`。
- 输入是预生成 inc 时，同样记录 sha 和来源。
- **唯一变量原则**：两侧必须同 tree HEAD、同 build flags、同 runner 源码；
  唯一允许的差异是 legalizer inc。

### Stage 2 官方答案

- 用 baseline inc/库构建 `runner.official`。
- 跑查询，写 `official.answers.jsonl`。
- 必须在 swap **之前**捕获；或让 `runner.official` 绑定 baseline 库副本，
  不能依赖 build 目录当前状态。

### Stage 3 替换并构建 ours

- 把 inc 安装到目标 include 路径（优先隔离副本，不改源码树）。
- 只重建目标库（例如 `libLLVMX86CodeGen.so`）。
- 校验安装后的 sha == 生成 sha；不一致立即失败。
- 构建 `runner.ours`，跑同一份查询，写 `ours.answers.jsonl`。

### Stage 4 恢复

- 无论成功失败，恢复 baseline inc 并重建；校验 sha。
- 用 `trap` 保证异常路径也恢复；恢复失败要显式报错，不能静默。

### Stage 5 对拍

- 对完整 key 集合做 join；分类：
  `agree / disagree / unanswerable(both) / missing_ref / missing_ours / error`。
- `disagree` 再分：`action`、`type_idx`、`new_type`。
- Phase 1 只比 `action`；Phase 2 比三元组。
- 输出 `diff.json` + 前 N 条人类可读差异。

### Stage 6 三方校验

同一批查询再跑 `gisel eval --answers`，形成三方矩阵：

| official | ours(inc) | eval | 归因 |
|---|---|---|---|
| = | ≠ | = | inc 转译问题 |
| = | = | ≠ | evaluator 问题 |
| ≠ | = | = | 规则差异（或官方差异） |
| ≠ | ≠ | ≠ | 查询/规则/多处问题 |

这是“归因”的核心证据；只跑两侧只能知道“不同”，不能知道“哪一层不同”。

### Stage 7 归因 bundle

- 按 `(owner, matrix, diff class, opcode, config, ruleset, rule)` 分组。
- 每条给：最小查询、官方答案、ours 答案、eval 答案、规则号/源位置。
- 输出机器可读 JSON + 人类可读 Markdown。
- 不调用 LLM；AI 读 bundle 后给修改建议。

`owner` 是归因方向，不是结论：

| owner | 典型矩阵类 | 处理 |
|---|---|---|
| `ours` | `translation` / `ours_assert` / `evaluator` | 改 `.gisel`、importer、inc emitter 或 evaluator；重跑 |
| `ours-or-upstream` | `rule` | 先对源文件修订；确认是转写漂移还是上游变化 |
| `llvm-or-query` | `official_assert`（有规则命中） | 先验查询合法性；确认是上游缺陷再记录 |
| `query` | `official_assert`（无规则命中） | 改 generator/axes/过滤；不要先怪 LLVM |
| `unknown` | `multiple` / `missing` | 保留在 bundle，不急着改 |

**LLVM 侧问题落盘**：确认是 LLVM 的问题后，先按
`/home/ubuntu/admin/AGENTS.md` §4.1 写到 `/home/ubuntu/admin/upstream-issues/`，
不要直接开 GitHub issue。记录至少包含：tree HEAD、build 配置、target/config、
最小查询、official/ours/eval 三方答案、inc/runner sha、断言栈或复现命令。

### Stage 8 ledger / loop

- 追加 run 记录：`run_id`、时间、tree HEAD、build、target、source sha、
  inc sha、query sha、runner sha、各分类计数。
- 官方答案缓存：key = `(tree HEAD, baseline inc sha, query sha, runner sha)`；
  未变则复用，只重跑 ours。
- 修复后重跑；差异应单调收敛；历史保留，便于回答“哪次修改引入了差异”。

## 4 功能需求

| # | 需求 |
|---|---|
| FR1 | **target adapter**：X86/AArch64/RISC-V 各一份配置，声明 include 路径、库名、重建目标、构造函数、config 表；核心流程不含 `if target == ...` |
| FR2 | **baseline 隔离**：复制 baseline inc/库；`runner.official` 绑定副本，不依赖 build 当前状态 |
| FR3 | **查询契约**：按 `spec/cases-format.md`；查询行不得带答案字段；重复 key 冲突报错 |
| FR4 | **答案契约**：答案行原样回显 key；`unanswerable` 单列；`LLT_invalid` 哨兵 |
| FR5 | **全量 join**：一侧缺失即失败；不允许只比交集还宣称通过 |
| FR6 | **崩溃恢复**：查询触发 LLVM 断言时重启 runner，把该条标 `unanswerable`，保持答案与查询逐行平行 |
| FR7 | **确定性**：固定排序、无时间戳进入答案；同输入同字节 |
| FR8 | **恢复安全**：`trap` + 锁 + sha 校验；失败不留下被改的 build |
| FR9 | **三方校验**：official / ours / eval 同一批查询 |
| FR10 | **归因 bundle**：分组、最小查询、规则号、源位置、三方答案 |
| FR11 | **缓存与 ledger**：官方答案按 hash 缓存；每次 run 追加 ledger |
| FR12 | **Phase 1/2**：`--compare=action` 与 `--compare=full`；默认 full，action 只作 smoke |
| FR13 | **负控**：故意改坏一条规则，工具必须 rc=1，并指出精确 key |
| FR14 | **进度与超时**：分阶段日志、计数、耗时；单查询可选超时 |
| FR15 | **CI smoke**：小查询集上跑通“构建→对拍→恢复”，不需要全量 |

## 5 数据契约

- **query**：`(config, name, types, mem, imms)` + 可选标注；
- **answer**：key + `action/type_idx/new_type` 或
  `status:"unanswerable"`；
- **diff**：key、ref、ours、eval、分类、ruleset/rule、源位置；
- **ledger**：run 元数据 + 计数 + 所有 sha；
- 归一化与去重规则以 `spec/cases-format.md` 为准；答案按 key 排序后哈希。

## 6 非功能需求

- 不联网；Python 只用标准库；C++ runner 复用现有 LLVM build。
- X86 104,388 条：官方 + ours 各跑一遍，目标在分钟级；diff 在秒级。
- 增量重跑：官方答案缓存命中时，只重建/重跑 ours。
- 跨 target：adapter 驱动；新增 target 不改核心流程。
- 安全：源码树只读；build 可恢复；并发互斥。
- 可观测：每阶段打印输入 sha、耗时、计数、rc。
- 可复现：同 tree/build/inc/query ⇒ 同答案 SHA。

## 7 验收标准

1. **负控**：把某条 `legal` 改成 `unsupported`，工具 rc=1，diff 精确列出受影响的 key。
2. **恢复**：跑完后 build 的 inc sha == baseline；`git status` 干净。
3. **确定性**：同输入跑两遍，答案文件 SHA 相同。
4. **全量**：`missing_ref=0`、`missing_ours=0`；`unanswerable` 两侧对称才计 agree。
5. **三方**：official/ours/eval 矩阵能区分“规则差异 / 转译差异 / evaluator 差异”。
6. **Phase 2**：构造一个 action 相同、`new_type` 不同的点，`--compare=action`
   必须不把它当通过。
7. **跨 target**：X86、AArch64、RISC-V 各一条命令跑通。
8. **ledger**：记录 tree HEAD、inc sha、query sha、runner sha、计数。
9. **文档**：一页 runbook，能从头复现一次完整 run。

## 8 现状与差距

已有：

- `snapshot.sh` / `swap-inc.sh` / `restore-inc.sh`：X86 的基线快照、替换、恢复；
- `build-runner.sh` / `build-aarch64-runner.sh`：双 runner 构建；
- `run-end-to-end.sh` / `run-aarch64-end-to-end.sh`：分阶段跑查询；
- `run-queries.py`：断言崩溃恢复；
- `diff.py`：全量 join、分类、退出码。

差距：

- 没有 target adapter，X86/AArch64 脚本各写一套；RISC-V 没有端到端脚本。
- 官方 runner 依赖“swap 前捕获”，没有绑定 baseline 库副本。
- 没有三方校验一体化；eval 对比是手工步骤。
- 没有归因 bundle、ledger、官方答案缓存。
- 没有负控 CI；`docs/REPORT-ab.md` 的数字还是旧快照。
- 规则到 `.gisel` 行号没有 source map；目前只能到 `(ruleset, rule)`。

## 9 开放问题

1. 两个独立 build 目录，还是一个 build + baseline 库副本？建议后者，省构建时间。
2. Phase 1 的查询集用 `cases` 还是 `domain`？建议 `domain` 做全量 A/B，
   `cases` 做回归；两者都记录 query sha。
3. 官方 build 随 rebase 变化时，缓存如何失效？按 tree HEAD + baseline inc sha。
4. 断言归因：两侧同位置断言算 `unanswerable`；单侧断言必须算差异。
5. 规则行号：短期用 `(ruleset, rule)`；长期由 importer 写入 source map。
6. AI 归因的输入边界：bundle 只含确定性证据，不含模型猜测。
