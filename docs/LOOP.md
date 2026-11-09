# 四步：钉版本 -> 出题 -> 对拍 -> 归因

这套系统的每个结论都必须是这四步里某一步的产物，而不是“我们记得”。下面写清
每一步的入口、产物，以及哪一步有证书。

```text
1 钉版本 / 提取   PIN.json ──import-cxx──> tests/corpus/*.gisel
2 出题            .gisel ──gisel cases──> queries.jsonl（无答案）
3 对拍            官方程序 + 我们的 inc，同一份 queries ──> official/ours.answers.jsonl, diff.json
4 归因            diff 的 owner ──> 改 gisel / 记录上游 issue / 记报告
```

## 1 钉版本，提取规则

**入库的语料来自一个 commit，不是某人的工作区。** 见
`tests/corpus/PIN.json`：

```json
{"commit": "9bfc850b9940…",
 "sources": {"X86": {"path": "…/X86LegalizerInfo.cpp", "sha256": "79f2376…"}, …}}
```

证书命令（读 `git show <commit>:<path>`，不读工作区）：

```sh
python3 tools/import-cxx.py --all --pin tests/corpus/PIN.json \
  --git-repo /home/ubuntu/llvm/llvm-project --check
# 三个 target 各打印 "read … from 9bfc850b9940" 和 ": matches"
```

为什么必须用 commit：A/B 的官方一侧要打本地补丁（例如 AArch64 的
`getNumElements()`，见 `2026-11-09-13`），工作区里的文件已经不是 pin 的内容。
提取只认 pin，补丁就污染不了语料。

产物：`tests/corpus/{X86,AArch64,RISCV}LegalizerInfo.gisel`。规则数和拒绝数写进
工具的 `TARGETS`，漂移就 rc=1。

## 2 出题

```sh
python3 -m gisel cases tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json \
  --axes tests/cases/aarch64-mem-orderings.axes.json \
  --out /tmp/a64.jsonl --json            # 加 --strict-coverage 做门禁
```

产物是一行一个查询的 JSONL，**不带答案**：`config/name/types/mem/imms`。
口径（等价类、边界、outside、见证）在 `spec/cases.md` 和
`docs/ALGORITHM-cases.md`；每个 target 的查询数是契约的一部分，脚本里写死
（X86 3,282 / AArch64 13,199 / RISC-V 6,301），变了就停下来看新题目。

## 3 对拍

```sh
tools/ab/run-end-to-end.sh         TREE BUILD x86.jsonl x86.inc OUT STATE
tools/ab/run-aarch64-end-to-end.sh TREE BUILD a64.inc  OUT STATE
tools/ab/run-riscv-end-to-end.sh   TREE BUILD rv.inc   OUT STATE
```

官方一侧必须是**从 pin 的 C++ 构建出来的构造函数**；我们的一侧把
`gisel gen --emit=inc` 的片段编进同一个类，其余代码仍用官方共享库。两侧读同一份
JSONL，比 `(action, type_idx, new_type)`。

产物：

```text
OUT/official.answers.jsonl   OUT/ours.answers.jsonl   OUT/diff.json
```

`diff.json` 里 `agree/unanswerable/disagree` 分开计数；**两侧都断言不等于答案相同**，
它只说明这题没被真正问出来。

## 4 归因

`diff.json` 的每条差异带 `class` 和 `owner`：

| 归因 | 动作 |
|---|---|
| 我们的翻译 / emitter / 求值 | 改 `tools/import-cxx.py`、`gisel/backend/*`、`gisel/eval.py`，然后重跑 1–3 |
| 查询生成（题目本身不合法） | 改 `gisel/cases.py`，重算查询数并更新 pin |
| 上游 | 落 `/home/ubuntu/admin/upstream-issues/`，不在构建树里“顺手修掉”当作结论 |
| 未定性 | 在 `docs/REPORT-*.md` 里写“未覆盖”，不许并进 agree |

每次归因的结论落 `docs/REPORT-*.md`，并带上产生它的命令、查询数、两侧 ignore 的
种类和数量。

## 当前状态（2026-11-09）

| target | 查询 | 一致 | 分歧 | 两侧都断言 | 备注 |
|---|---:|---:|---:|---:|---|
| AArch64 | 13,199 | 13,082 | 0 | 117 | 上游 `mutationIsSane`，未定性 |
| RISC-V | 6,301 | 6,299 | 0 | 0 | — |
| X86 | 3,282 | 3,257 | 19 | 0 | 全部是 `G_BUILD_VECTOR` 的**有意偏离**：上游窄 build vector 加 lane 会死循环（`2026-11-09-14`），语料改为 `Unsupported` |
