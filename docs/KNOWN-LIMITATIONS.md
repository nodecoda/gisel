# 已知限制（一页）

这份清单只写“现在做不到/没测到”的事。每条都指向能复现它的命令或报告；
不在这里的结论，按对应报告的门来读。

## 图（`gisel graph`）

1. **默认分区在 X86 / AArch64 / RISC-V 上不闭合。** 默认 `--check-closure`
   会报告 `closure.count > 0`（X86 四个配置 265–277；AArch64 baseline 2,493；
   RISC-V rv64gc 2,864），命令按规范返回 1，`verdict` 是 `conditional`。
   签字口径是 `--refine` + `closure.count=0` + `outside=0`，此时 `verdict=safe`。
   见 `spec/graph.md` 的 “verdict” 与 `docs/REPORT-graph.md` §8。
2. **`cycles=0` 不是 `rc=0`。** 读结论时必须同时读 `closure`、`outside`、
   `opaque` 和 `verdict`；只看 `cycles` 会把条件结论当成证明。
3. **全配置矩阵是测量，不是 PR 门。** AArch64 9 个配置、RISC-V 8 个配置的
   数字在 `docs/REPORT-graph-configs.md`；PR 门只锁 5 个 golden，nightly 锁
   10 个配置。
4. **SPIR-V 没有图结论。** `spirv64-kernel --refine` 在 200,000 状态处确定性地
   以 rc=2 / `unsupported_scale` 停止（约 15 秒），没有 cycles/closure 数字。
5. **variadic opcode 不建图。** `G_INTRINSIC*` 等没有固定槽数，进 `uncovered`，
   不是“0 环”证据的一部分。
6. **imm / ordering 轴没有全量跑。** 只有带 `--axes` 的配置才会进这两个轴；
   RISC-V 的 imm 轴、无 ordering profile 的内存点没有全配置矩阵。

## 题面（`cases` / `domain`）

7. `domain` 是**规则无关的声明值域**，不是“合法值域”：里面有非法组合，也有
   求值错误；它也不包含 `s7`/`s31` 这类未声明的切点。`cases` 与 `domain`
   互不包含，别拿一个的分母当另一个的。
8. "谁都没答"（`unanswerable`）与 `agree` 分开计数；读一致率时不能把它算进
   分母或分子。

## 对拍（`gisel-ab`）

9. 只比 `getAction()` 这一个点，不比 MIR、不跑 `llc`、不比机器码。多轮结果
   的一致性依赖单轮一致这个前提，不是逐条重放。
10. `mir` / `l3` 需要 LLVM tree 和 build；`setup` 只记录路径，不构建 LLVM。

## 发布

11. `gisel 0.3.0`、`gisel-anchor 0.2.0`、`gisel-ab 0.9.0` 已在 PyPI（2026-11-14）。
    更早的文档里“从 GitHub 装”的写法已删除；如果看到旧缓存，按 PyPI 页为准。
12. AMDGPU 按约定不接；不在任何 target 表里。

## 不打算做

- 不为凑“全绿”把 `--refine` 设成默认：那会改变第 2 篇论证里的“原子”定义。
- 不做 Web UI、服务化、LLVM 构建自动化。
