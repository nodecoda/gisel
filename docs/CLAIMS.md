# 对外结论与它的门

每一行是一条会被读者当成结论的话。`command` 必须能从本仓库根目录直接跑，
`expected` 是判据，`gate` 是跑它的 CI job（`local` 表示发版前手工跑）。
跨仓结论（`import --check`、`check-pin.sh`、`verify-evidence.sh`）的门在
`upstream-source` / `ab` 自己的 CI 里，不在这张表重复。

新增/修改结论时先改这张表，再改文档。`tools/check-claims.py` 在 CI 里检查：
命令引用的脚本/文件存在、判据非空、表不为空。

| claim | command | expected | gate |
|---|---|---|---|
| 九份语料的 inc/check/core 与冻结清单一致 | `bash tools/check-nine-corpora.sh` | rc=0 | `nine corpora are byte-identical` |
| 全部单测通过 | `python3 -m unittest discover -q -s tests` | rc=0 | `unit tests` |
| 九份冻结产物的 sha 清单一致 | `bash -c 'cd tests/artifacts && sha256sum -c SHA256'` | rc=0；9/9 OK | `unit tests` |
| X86 语料 lint 干净 | `python3 -m gisel.cli lint tests/corpus/X86LegalizerInfo.gisel` | rc=0；0 errors | `static checks` |
| X86 inc 可从语料生成 | `python3 -m gisel.cli gen tests/corpus/X86LegalizerInfo.gisel --emit=inc --out /tmp/x86.inc` | rc=0；文件非空 | `every backend without llvm-tblgen` |
| X86 默认 partition 0 环但 closure 不闭合 | `python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none --json` | rc=1；cycles=0；closure 与 golden 相同 | `golden` |
| X86 `--refine` 后后继是状态上的函数 | `python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none --refine --json` | rc=0；cycles=0；closure.count=0 | `golden` |
| RISC-V `rv64gc --refine` 后 0 环且闭包成立 | `python3 -m gisel graph tests/corpus/RISCVLegalizerInfo.gisel --emit=core --features tests/cases/riscv-features.json --config rv64gc --refine --json` | rc=0；cycles=0；closure.count=0 | `golden` |
| 负控：注入一条回边必须报 2 环 | `python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none --inject-edge --json` | rc=1；cycles>=1 | `golden` |
| X86 题面是 3,014 条 | `python3 -m gisel cases tests/corpus/X86LegalizerInfo.gisel --features tests/cases/x86-features.json --out /tmp/x86.jsonl` | `cases=3014` | `golden` |
| AArch64 题面是 12,559 条 | `python3 -m gisel cases tests/corpus/AArch64LegalizerInfo.gisel --features tests/cases/features.json --axes tests/cases/aarch64-mem-orderings.axes.json --out /tmp/a64.jsonl` | `cases=12559` | `nightly` |
| RISC-V 题面是 6,086 条 | `python3 -m gisel cases tests/corpus/RISCVLegalizerInfo.gisel --features tests/cases/riscv-features.json --out /tmp/rv.jsonl` | `cases=6086` | `nightly` |
| X86 domain 是 91,340 条 | `python3 -m gisel domain tests/corpus/X86LegalizerInfo.gisel --features tests/cases/x86-features.json --out /tmp/x86-domain.jsonl` | `points=91340` | local（约 2 秒） |
