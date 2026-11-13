# Cookbook：8 个任务

每条命令都能直接复制；带「需要 LLVM」的任务要先做第 7 条的 `setup`。
安装（三个包）：

```sh
python3 -m pip install gisel
# PyPI 凭据到位前，另外两个从 GitHub 安装；gisel-ab 会从 PyPI 取 gisel 依赖
python3 -m pip install "git+https://github.com/nodecoda/gisel-anchor"
python3 -m pip install "git+https://github.com/nodecoda/gisel-ab"
```

## 1 自检：这台机器能不能用

```sh
gisel --version
gisel doctor
gisel-anchor --version
gisel-ab --version
gisel-ab doctor --json
```

`gisel doctor` 只看 gisel 自己；`gisel-ab doctor` 看对拍需要的 LLVM、构建、
pin、gisel 版本和上一次运行状态。两项 `tree/build fail` 在没装 LLVM 时是正常的。

## 2 看一份语料：规则和题面

```sh
gisel lint --corpus x86
gisel cases --corpus x86 --out /tmp/x86.jsonl --json
head -1 /tmp/x86.jsonl
```

`cases` 的产物**不带答案**，每行是 `config/name/types/mem/imms`。X86 当前
3,014 条；数量变了说明出题口径变了，先停下来看 `docs/ALGORITHM-cases.md`。

## 3 生成 inc，并检查它没过期

```sh
gisel gen   --corpus x86 --emit=inc   --out /tmp/x86.inc
gisel check --corpus x86 --emit=inc   --against /tmp/x86.inc
```

`gen` 是生成，`check` 是字节级指纹比对。`lint` 不生成任何东西，只做静态检查；
三者都不需要 LLVM，也不需要 `llvm-tblgen`。

## 4 `cases` 与 `domain` 怎么选

```sh
gisel cases  --corpus x86 --out /tmp/x86.cases.jsonl   # 规则感知，约 3 千条
gisel domain --corpus x86 --out /tmp/x86.domain.jsonl  # 声明值域，约 9 万条
```

- `cases`：按规则切点压缩，回答「每条规则/边界被执行到了吗」。
- `domain`：规则无关的笛卡尔积，包含非法组合和求值错误，回答「声明值域里有
  没有规则没覆盖到的角落」。

两者互不包含，不要拿一个当另一个的超集。

## 5 看规则图：环不是超时

```sh
gisel graph --corpus x86 --emit=core --config x86-64-v3
gisel graph --corpus x86 --emit=core --config x86-64-v3 --json
```

退出码：`0` 无环，`1` 有环，`2` 用法/解析错误。加 `--inject-edge` 是负控：
人为加一条回边，必须报 2-环并返回 1；没有这条，0 环可能只是 DFS 没跑。
`--check-closure` 检查「后继是状态上的函数」，不封闭时返回 1 并打印反例。

## 6 从上游 C++ 重新生成语料

```sh
gisel-anchor import --all \
  --git-repo https://github.com/llvm/llvm-project --check
```

`--git-repo` 可以是 checkout 路径或 URL；URL 会按 pin 的 commit 做一次
blobless clone，缓存在 `~/.cache/gisel-anchor`。`--check` 逐字节比对 9 个
target，拒绝数漂移就 rc=1。把 URL 换成自己的 LLVM fork 也可以。

## 7 对拍 L0：同一份查询，两个实现

```sh
gisel-ab setup --llvm /path/to/llvm-project --build /path/to/build
gisel-ab doctor
gisel-ab run --target m68k
```

`setup` 把路径写进 `~/.config/gisel-ab/config.json`，不需要 export。
`run` 构建官方侧和 include 了 inc 的一侧，回答同一份无答案查询，写
`official/ours.answers.jsonl` 和 `diff.json`，结束前把构建树恢复。
M68k 是最短的完整闭环（约 65 秒）；X86 是 3 千条查询的正式门。

## 8 取回冻结证据，离线复核

```sh
gisel-ab evidence fetch --tag cohort-2026-11-14-r12
gisel-ab evidence verify --frozen
```

`fetch` 从 cohort 的 GitHub Release 下载 `evidence-cohort-*.tar.gz`，校验
sha256 后解到 `~/.cache/gisel-ab/evidence/<tag>`；`verify --frozen` 不再跑
LLVM，只比对冻结产物。没有 checkout 也能用。

出问题时先跑：

```sh
gisel-ab bug-report --out /tmp/gisel-ab-bug.json
```

它收集三包版本、cohort 记录、doctor 结论和上一次 run 的 ledger 行，不含
evidence 大文件，可以直接贴进 issue。
