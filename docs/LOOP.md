# 四步：钉版本 -> 出题 -> 对拍 -> 归因

这套系统的每个结论都必须是这四步里某一步的产物，而不是“我们记得”。下面写清
每一步的入口、产物，以及哪一步有证书。

```text
1 钉版本 / 提取   upstream-source/pin/PIN.json ──import──> tests/corpus/*.gisel
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
python3 ../upstream-source/import/import-cxx.py --all \
  --pin ../upstream-source/pin/PIN.json \
  --git-repo /home/ubuntu/llvm/llvm-project --check
# 六个 target 各打印 "read … from 9bfc850b9940" 和 ": matches"
```

为什么必须用 commit：A/B 的官方一侧要打本地补丁（例如 AArch64 的
`getNumElements()`，见 `2026-11-09-13`），工作区里的文件已经不是 pin 的内容。
提取只认 pin，补丁就污染不了语料。

产物：`tests/corpus/{X86,AArch64,RISCV,M68k,PowerPC,WebAssembly,ARM}LegalizerInfo.gisel`。规则数和拒绝数
写进工具的 `TARGETS`，漂移就 rc=1。

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
（X86 3,027 / AArch64 12,583 / RISC-V 6,149 / M68k 35 / PowerPC 94 /
WebAssembly 886 / ARM 1,614 / Mips 1,656），
变了就停下来看新题目。

## 3 对拍

```sh
../ab/run-end-to-end.sh         TREE BUILD x86.jsonl x86.inc OUT STATE
../ab/run-aarch64-end-to-end.sh TREE BUILD a64.inc  OUT STATE
../ab/run-riscv-end-to-end.sh   TREE BUILD rv.inc   OUT STATE
../ab/run-m68k-end-to-end.sh    TREE BUILD m68k.inc OUT
../ab/run-ppc-end-to-end.sh     TREE BUILD ppc.inc  OUT
../ab/run-wasm-end-to-end.sh    TREE BUILD wasm.inc OUT
../ab/run-arm-end-to-end.sh     TREE BUILD arm.inc  OUT
../ab/run-mips-end-to-end.sh    TREE BUILD mips.inc OUT
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
| 我们的翻译 / emitter / 求值 | 改 `upstream-source/import/import-cxx.py`、`gisel/backend/*`、`gisel/eval.py`，然后重跑 1–3 |
| 查询生成（题目本身不合法） | 改 `gisel/cases.py`，重算查询数并更新 pin |
| 上游 | 落 `/home/ubuntu/admin/upstream-issues/`，不在构建树里“顺手修掉”当作结论 |
| 未定性 | 在 `docs/REPORT-*.md` 里写“未覆盖”，不许并进 agree |

每次归因的结论落 `docs/REPORT-*.md`，并带上产生它的命令、查询数、两侧 ignore 的
种类和数量。

## 当前状态（2026-11-09）

| target | 查询行 | 去重 key | 一致 | 分歧 | 两侧都断言 | 备注 |
|---|---:|---:|---:|---:|---:|---|
| AArch64 | 12,583 | 12,583 | 12,583 | 0 | 0 | — |
| RISC-V | 6,149 | 6,147 | 6,147 | 0 | 2 | 2 条两侧都断言 |
| X86 | 3,027 | 3,021 | 3,021 | 0 | 0 | 6 条重复 key（3027 行 → 3021 key） |
| M68k | 35 | 35 | 35 | 0 | 0 | 单配置，规则 13 条 |
| PowerPC | 94 | 94 | 94 | 0 | 0 | 单配置，规则 25 条；断言那条已落到 `unanswerable`（两侧一致） |
| WebAssembly | 886 | 886 | 886 | 0 | 0 | wasm32/wasm64 × ±sign-ext，规则 109 条 |
| ARM | 1,614 | 1,614 | 1,614 | 0 | 0 | 7 配置（soft-float / VFP2 / VFP4 / NEON / V5T / HW divide / AEABI），规则 96 条；Thumb1 未覆盖（构造函数直接 return，见 REPORT §12） |
| Mips | 1,656 | 1,656 | 1,647 | 0 | 0 | 5 配置（MSA / MIPS32r2 / 非对齐访问），规则 95 条；9 条官方侧断言、我们侧给答案（上游 4 字节非对齐 load 断言，`--allow-ref-asserts 9`） |
| SPIRV | 5,136 | 5,136 | 5,132 | 0 | 4 | 6 配置（kernel/shader × spirv32/64 × 扩展集），规则 353 条；4 条两侧都断言（上游 `changeElementSizeTo` 传了元素数量，读 `Query.Types[16]`，`--expect-unanswerable 4`） |

2026-11-09 在 `fe98bba`（SPIRV 接入后）把上表 9 个 target 的端到端脚本全部重跑了一遍，
结论不变：`m68k 35 / wasm 886 / ppc 94 / arm 1,614 / mips 1,656 / riscv 6,149 /
aarch64 12,583 / x86 3,027 / spirv 5,136` 条查询，`disagree = 0`；
`ppc` 的 1 条、`mips` 的 9 条（`ref_asserted`）、`spirv` 的 4 条（两侧都断言）与表里一致。

X86 的 19 条原本是“语料对齐上游修复、官方侧还没修”的单边差异。把
`patches`（`PIN.json`）落到树上、官方侧也具备修复后，两侧给出同一个
`Unsupported`，差异归零。

AArch64 的 117 条要拆成两层看：PR #238306 修好官方侧的 `mutationIsSane` 后
暴露成 9 条真实分歧，那是我们的 importer 把 `maxScalarEltSameAsIf` 翻错了；
修完后还剩 108 条两侧都断言。

那 108 条不是上游的锅，是**我们自己造的非法查询**：逐槽候选做笛卡尔积，
造出了 `(v16s8, v2s32)`、`(v16s8, s32)`、`(v2i64, f16)` 这类真实 MIR 里不可能
出现的类型组合，官方 legalizer 正确地拒绝了它们。加了 opcode 形状约束之后
108 条归零，规则见证数不变（572）。详见 `docs/ALGORITHM-cases.md` 的
「形状：槽不是独立轴」。

查询行数因此从 13,199 / 3,282 变成 12,952 / 3,217；RISC-V 没有这类形状，
6,301 不变。
