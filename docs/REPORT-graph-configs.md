# graph 全配置矩阵（AArch64 / RISC-V）

这份表是**测量记录**，不是 PR 门。PR 只锁 5 个 golden，nightly 锁 10 个配置；
这里把 AArch64 的 9 个配置和 RISC-V 的 8 个配置各跑一遍，回答“一个配置能不能
代表全部”。

生成命令（在仓库根目录，4 vCPU / 62 GB，Python 3.10.12）：

```sh
# AArch64：9 个配置
for c in baseline small-cm fullfp16 sve bf16 cssc rcpc3 lse outline-atomics; do
  /usr/bin/time -f '%e %M' \
    python3 -m gisel graph tests/corpus/AArch64LegalizerInfo.gisel \
      --emit=core --features tests/cases/features.json --config "$c" \
      --refine --json > "/tmp/matrix-r17/a64-$c.json"
done

# RISC-V：8 个配置
for c in rv64gc rv32gc rv64gcv rv32gcv rv64zbb rv64zfh ristretto rv32zilsd; do
  /usr/bin/time -f '%e %M' \
    python3 -m gisel graph tests/corpus/RISCVLegalizerInfo.gisel \
      --emit=core --features tests/cases/riscv-features.json --config "$c" \
      --refine --json > "/tmp/matrix-r17/riscv-$c.json"
done
```

> 采集时 gisel 工作树基于 r16 `e80302b` 加 r17 的 `verdict` 改动。

## 结果

| target | config | wall s | RSS MB | states | edges | classes | cycles | closure | outside | opaque | verdict | rc |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| AArch64 | baseline | 576.1 | 1374 | 1105268 | 188580 | 15336 | 0 | 0 | 12825 | 204803 | conditional | 0 |
| AArch64 | bf16 | 578.5 | 1374 | 1105268 | 188580 | 15336 | 0 | 0 | 12825 | 204803 | conditional | 0 |
| AArch64 | cssc | 578.0 | 1374 | 1105276 | 188580 | 15344 | 0 | 0 | 12825 | 204811 | conditional | 0 |
| AArch64 | fullfp16 | 575.7 | 1374 | 1105251 | 188492 | 15319 | 0 | 0 | 11956 | 204803 | conditional | 0 |
| AArch64 | lse | 575.2 | 1374 | 1105268 | 188580 | 15336 | 0 | 0 | 12825 | 204803 | conditional | 0 |
| AArch64 | outline-atomics | 572.5 | 1374 | 1105268 | 188496 | 15336 | 0 | 0 | 12825 | 204803 | conditional | 0 |
| AArch64 | rcpc3 | 576.1 | 1374 | 1105268 | 188580 | 15336 | 0 | 0 | 12825 | 204803 | conditional | 0 |
| AArch64 | small-cm | 580.0 | 1374 | 1105268 | 188580 | 15336 | 0 | 0 | 12825 | 204803 | conditional | 0 |
| AArch64 | sve | 586.8 | 1373 | 1105251 | 188492 | 15319 | 0 | 0 | 11956 | 204803 | conditional | 0 |
| RISC-V | ristretto | 273.2 | 612 | 521470 | 29296 | 8036 | 0 | 0 | 2510 | 28692 | conditional | 0 |
| RISC-V | rv32gc | 244.1 | 614 | 522766 | 31347 | 8056 | 0 | 0 | 3166 | 29146 | conditional | 0 |
| RISC-V | rv32gcv | 272.3 | 614 | 522766 | 31222 | 8056 | 0 | 0 | 3166 | 29146 | conditional | 0 |
| RISC-V | rv32zilsd | 240.9 | 614 | 522766 | 31347 | 8056 | 0 | 0 | 3166 | 29146 | conditional | 0 |
| RISC-V | rv64gc | 245.4 | 613 | 522996 | 29356 | 8054 | 0 | 0 | 3622 | 29260 | conditional | 0 |
| RISC-V | rv64gcv | 273.5 | 613 | 522996 | 29323 | 8054 | 0 | 0 | 3622 | 29260 | conditional | 0 |
| RISC-V | rv64zbb | 245.1 | 611 | 521470 | 29662 | 8036 | 0 | 0 | 2510 | 28692 | conditional | 0 |
| RISC-V | rv64zfh | 249.2 | 613 | 522996 | 29023 | 8054 | 0 | 0 | 3622 | 29260 | conditional | 0 |

## 怎么读

- **17/17 rc=0、cycles=0、closure=0。** 在 `--refine` 下，后继是状态上的函数；
  这张表里没有环。
- **`verdict` 全是 `conditional`，这是定义使然**：`outside` 和 `opaque` 非零。
  `outside` 是变异把类型推出有限域的计数（这些边不建，可达性因此不完整），
  `opaque` 是谓词里有逃逸洞的状态。把它们算进 `safe` 会把“没覆盖”说成“安全”，
  所以 `safe` 只留给四项全零的图；真实 target 读 `conditional` 时看括号里的计数。
- **AArch64 的配置差异很小**：9 个配置 states 在 1,105,251–1,105,276 之间，
  `outside` 只有 `fullfp16`/`sve` 是 11,956，其余 12,825。说明这些 feature 主要
  影响规则分支，不改变类型轴；换配置不能换来新的类型覆盖。
- **RISC-V 的差异来自位宽**：`rv32*` 的 states 522,766、`outside` 3,166；
  `rv64*` 的 states 522,996、`outside` 3,622；`zbb`/`ristretto` 状态略少
  （521,470）。`rv64gcv`/`rv32gcv` 的 edges 比无 V 的少几十到一百多条，
  是向量规则分支的差异。
- **成本**：AArch64 单配置约 9.6 分钟、1.37 GB；RISC-V 约 4–4.6 分钟、0.61 GB。
  17 个配置并发 8 跑完约 25 分钟。AArch64 是当前的单点上限，`--jobs` 的收益
  主要在这里。

## 未覆盖

- 这张表只跑 `--refine`；默认分区的 closure 违例数见 `REPORT-graph.md` §8。
- 没有跑 imm 轴/ordering 轴的全配置组合；只有带 `--axes` 的配置才进这两个轴。
- SPIR-V 不在表里：`spirv64-kernel` 在 200,000 状态处以 `state_limit` 停止，
  没有图结论。
