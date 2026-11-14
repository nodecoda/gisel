# 五分钟：不装 LLVM 也能把 gisel 跑完

这条路径不需要 LLVM 源码、不需要构建、不需要网络。装完 wheel 就能把
“规则 → 产物 → 问题 → 答案 → 图”整条走一遍。所有输出都是在本机实跑后
抄下来的，不是示意。

## 0 装

```sh
python3 -m venv /tmp/gv && . /tmp/gv/bin/activate
pip install gisel
```

或者一条命令装三件套（pipx → uv tool → venv，哪个有就用哪个）：

```sh
curl -fsSL https://raw.githubusercontent.com/nodecoda/gisel/main/scripts/install.sh | sh
```

需要 Python 3.10+。没有其他依赖。

## 1 先问它能不能干活

```sh
gisel doctor
```

```
gisel doctor
python           ok   3.10.12
version          ok   0.3.3
install          ok   pypi 0.3.3
opcode-slots     ok   schema 1, commit 700e551714cc
contracts        ok   contract-aarch64.jsonc contract-shapes.jsonc
commands         ok   9: gen check cases domain lint eval graph doctor demo
corpora          ok   9 targets: aarch64 arm m68k mips ppc riscv spirv wasm x86
corpus:m68k      ok   c9cd4a22344b M68kLegalizerInfo.gisel
...
16/16 ok
```

`install` 说明这套 gisel 从哪来（`pypi` / `git <commit>` / `checkout <path>`），
支持问题先看这一行。九份语料每份打一个 sha：这些数你可以自己用 `sha256sum` 复算。少一份数据、
Python 太旧、wheel 装坏，都会在这里失败并给 `fix:`，退出码 2。
`--json` 给你同样的东西，形状是 `{ok, checks:[{name,status,detail,fix}]}`。

## 2 一条命令跑完全流程

不想一条条抄命令：

```sh
gisel demo
```

它按 lint → `gen --emit=inc` → `cases` → `graph --refine` 的顺序，用随包
安装的 x86 语料把四个阶段各跑一次，产物写到 `./gisel-demo/`：

```
gisel demo: x86, 4 stages, no LLVM
artifacts: /path/to/gisel-demo

[1/4] lint
$ gisel lint --corpus x86
x86: 0 error(s), 0 warning(s), 328 rule(s)
...
[4/4] build the quotient graph
$ gisel graph --corpus x86 --refine --config C0
# --refine: split classes until the successor is a function (default partition is coarser)
...
verdict     : CONDITIONAL (cycles=0, closure=0, outside=2240, opaque=1187)
closure     : ok (0 violation(s), 0 shown)

demo: ok (23.0 s)
wrote:
  /path/to/gisel-demo/x86.inc
  /path/to/gisel-demo/x86.cases.jsonl
next:
  gisel graph --corpus x86 --json > graph.json   # one config; drop --config for all
  gisel domain --corpus x86 --out domain.jsonl
  gisel check --corpus x86 --emit=inc --against /path/to/gisel-demo/x86.inc
```

用时随机器变，官方 CI 的 4 核 runner 也在 60 秒以内；`--corpus m68k`
是 0.3 秒的冒烟版。`--config` 换配置，`--out` 换目录。demo 只是把下面
这些命令按顺序跑一遍：每个阶段的输出和单独运行时逐字节相同。

## 3 出题

```sh
gisel cases --corpus m68k --out m68k.cases.jsonl
```

```
m68k.cases.jsonl: cases=35 equivalence=14 boundary=11 outside=10
rules=13 witnessed=11 shadowed=2 unexercised=0
```

`--corpus NAME` 是糖：展开成包里那份 `.gisel` 加配套的 features。
九个名字见 `gisel/data/corpora.json`；写错名字会退出码 2 并列出全部名字。

`cases` 出的是**问题**，没有答案。三类：等价类代表点、类边界、域外一档。
`unexercised=0` 表示没有规则被生成出来却没被问到。

## 4 全量题面（对照用）

```sh
gisel domain --corpus m68k --out m68k.domain.jsonl
```

```
m68k.domain.jsonl: points=112 configs=default types=5 mems=5 opcodes=12 shape_dropped=0 skipped=0
```

`domain` 是规则无关的声明值域笛卡尔积，`cases` 是规则感知的压缩。两者**互不包含**：
`domain` 里有 `cases` 不会生成的非法组合，`cases` 里有 `domain` 的形状过滤丢掉的点。
比较分母时先弄清你用的是哪一个。

## 5 生成产物

```sh
gisel gen --corpus m68k --emit=inc  --out m68k.inc
gisel gen --corpus m68k --emit=core --out m68k.core.json
```

```
m68k.inc: 6 rule sets, 13 rules
m68k.core.json: 6 rule sets, 13 rules
```

`.inc` 是给 C++ 的；`.core.json` 是 schema 0.4 的正常形，`eval` 和 `graph`
吃这个。`check` 可以验证产物没过期（默认忽略 origin，`--strict-origin` 才比）：

```sh
gisel check --corpus m68k --emit=core --against m68k.core.json
# m68k.core.json: up to date
```

## 6 自己回答这批问题

```sh
gisel eval --doc m68k.core.json \
  --features "$(python3 -c 'from gisel import corpus; print(corpus.get("m68k").features)')" \
  --cases m68k.cases.jsonl --answers answers.jsonl
```

（`eval` 的 `--features` 还没有 `--corpus` 简写；`corpus.get()` 给出配套的
特性表路径，`--doc`/`--cases` 都是上一步的真实文件。）

```
cases=35 errors=0
actions: {"Legal": 9, "NarrowScalar": 2, "Unsupported": 18, "WidenScalar": 6}
```

每条答案长这样：

```json
{"config":"default","name":"G_ADD","types":["s7"],"mem":null,"imms":[],
 "action":"WidenScalar","type_idx":0,"new_type":"s8"}
```

这是**我们这套规则**给出的答案。它和上游 C++ 是否一致，需要 LLVM 才能判，
那是 `gisel-ab` 的事（`gisel-ab/docs/TUTORIAL-m68k.md`）。没有 LLVM 时能证明的是：
规则能被解析、能出题、能被这套语义回答，且答案可复现。

## 7 找环

```sh
gisel graph --corpus m68k
```

```
states      : 1232
edges       : 387
classes     : 138
outcomes    : {'moves': 387, 'no-rule': 768, 'opaque': 0, 'outside': 0, 'stuck': 0, 'terminal': 77}
terminal    : {'Legal': 77}
cycles      : 0
closure     : ok (0 violation(s), 0 shown)
```

图上 0 环，且闭包成立（每个类的所有成员在变异后落回同一个类）。这两个条件
要一起读：闭包不成立时，0 环只是“在代表点上没找到环”。

## 8 这一页证到了什么

- 证到：`pip install gisel` 之后，九份语料可直接出题；题库可复算；求值可复现；
  M68k 的商图 0 环且闭包成立。
- 没证：这套规则和上游 LLVM 一致。那需要 pin 的 LLVM 树和构建，见
  `gisel-ab/docs/TUTORIAL-m68k.md`。

## 9 常见问题

| 现象 | 原因 | 动作 |
|---|---|---|
| `doctor` 报 `opcode-slots fail` | wheel 装坏或数据被删 | 重装：`pip install --force-reinstall gisel` |
| `--corpus` 报 `unknown corpus` | 名字拼错 | 用 stderr 里列出的九个名字 |
| `graph` 报 `closure: fail` | 这个 target 的类划分不封闭 | 先看 `closure kinds:`；这是分析结论，不是安装问题 |
| `gen` 报语法错误 | 源文件不是合法 `.gisel` | `gisel lint <file>` 给出行号 |
