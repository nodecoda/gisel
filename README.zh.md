# gisel

设计论证：[文章链接](https://zhuanlan.zhihu.com/p/2102431370098298974)

[English](README.md) · 简体中文

[![ci](https://github.com/nodecoda/gisel/actions/workflows/ci.yml/badge.svg)](https://github.com/nodecoda/gisel/actions/workflows/ci.yml)

一门用于描述 GlobalISel 合法化规则的自由形式语言，以及一套**不依赖
`llvm-tblgen`** 就能把规则变成 LLVM 产物的工具链。

gisel 只有两个功能：把 `.gisel` 文件变成规则产物
（`gen`/`check`/`lint`），以及生成测试用例（`cases`/`domain`）。把 LLVM
手写的 legalizer 导入 `.gisel`、以及双实现对拍，属于工作台（`tools/`），
不是 gisel 本体——边界和固定规则见 [docs/SCOPE.md](docs/SCOPE.md)。
那套工具实现的循环（钉版本 → 出题 → 对拍 → 归因）见
[docs/LOOP.md](docs/LOOP.md)。

```sh
# 从 checkout 运行：语料和冻结产物随仓库分发，不随 wheel 分发
# （wheel 里带的是 lint 需要的 opcode 表和形状表）。
python3 -m pip install .        # 或者：python3 -m gisel（不安装）
gisel gen   tests/corpus/X86LegalizerInfo.gisel --emit=inc --out x86.inc
gisel check tests/corpus/X86LegalizerInfo.gisel --emit=inc --against x86.inc
gisel lint  tests/corpus/X86LegalizerInfo.gisel   # 静态检查，不需要 LLVM
gisel cases tests/corpus/X86LegalizerInfo.gisel --out x86.cases.jsonl \
            --features tests/cases/x86-features.json   # 等价类 / 边界 / 域外
```

## 五分钟上手

一个 ruleset，四条规则，不构建 LLVM，不用 `llvm-tblgen`：

```sh
git clone https://github.com/nodecoda/gisel && cd gisel
mkdir -p /tmp/demo && cat > /tmp/demo/hello.gisel <<'EOF'
feature Is64Bit = Subtarget.is64Bit()
type I32 = LLT::scalar(32)
type I64 = LLT::scalar(64)

ruleset X_ADD: G_ADD
    legal in(slot(0), I32)
    legal (Is64Bit and in(slot(0), I64))
    widen(slot(0), pow2_min(32))
    scalarize(slot(0))
EOF

python3 -m gisel lint /tmp/demo/hello.gisel
# /tmp/demo/hello.gisel: 0 error(s), 0 warning(s), 4 rule(s)

python3 -m gisel gen   /tmp/demo/hello.gisel --emit=inc --out /tmp/demo/hello.inc
python3 -m gisel check /tmp/demo/hello.gisel --emit=inc --against /tmp/demo/hello.inc
# /tmp/demo/hello.inc: up to date
```

生成的 `.inc` 就是 C++ builder 链，一条规则一个调用：

```cpp
  bool Is64Bit = Subtarget.is64Bit();

  const LLT I32 = LLT::scalar(32);
  const LLT I64 = LLT::scalar(64);

  getActionDefinitionsBuilder(G_ADD)
      .coreLegalIf([=](const LegalityQuery &Query) { return (Query.Types[0] == I32); })
      .coreLegalIf([=](const LegalityQuery &Query) { return (Is64Bit) && ((Query.Types[0] == I64)); })
      .coreWidenScalarToNextPow2([](const LegalityQuery &) { return true; }, 0, 32)
      .scalarize(0);
```

`--emit=check` 和 `--emit=core` 从同一份源文件给出另外两种形状。没有
`.td` 后端，也没有 table 后端：C++ `.inc` 就是产品。

## 命令

七个命令，一个产品面；`spec/cli.md` 是规范契约。

| 命令 | 做什么 |
|---|---|
| `gen` | 生成一种产物：`--emit=inc\|check\|core` |
| `check` | 产物是否仍然和源文件一致？ |
| `lint` | 静态检查，不产生产物 |
| `cases` | 无答案测试查询：等价类、边界、域外 |
| `domain` | 同一空间的全量笛卡尔枚举 |
| `eval` | 用 schema-0.4 正常形回答查询 |
| `graph` | 建商图并找环 |

七个命令共用同一套退出码：`0` 成功，`1` 结论是“否”（产物过期、lint
报错、答案不一致、有环），`2` 这次运行根本没开始（用法、IO、语法错误）。
`2` 永远不代表规则差异。

### 一条命令看懂图

一个 legalizer 把 `s24` 加宽到 `s32`，然后再窄回去，不会超时——它会死循环。
`graph` 从正常形建立有限状态空间（opcode × 每个类型槽的类），在它上面跑
三色 DFS：

```sh
gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none
gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none \
  --inject-edge                 # 负控：必须报出一个 2-环
gisel graph tests/corpus/X86LegalizerInfo.gisel --emit=core --config none \
  --no-check-closure            # 跳过审计（cycles=0 因此失去前提）
```

`spec/graph.md` 是契约，`docs/REPORT-graph.md` 是证据。闭包审计**默认开启**：
只要有类成员落到枚举域外或落到不同的后继类，命令就返回 1，这时 `cycles=0`
只是“在被检查的那个划分上没找到环”，不是对整个定义域的证明。`--refine`
会拆开违规的类；X86 C1 用 `--refine` 后 rc=0（`docs/REPORT-graph.md` §3）。

## 架构

前端（`gisel/ast.py`）把 `.gisel` 解析成唯一模型：一个由声明、ruleset 和
规则组成的 `Program`。类型是结构化的（`Scalar(32)`、`Pointer(0, None)`、
`Vector(...)`），规则的类型位置持有这些值，一个 ruleset 是
`(name, opcodes, rules)`。`X86_s32`、`LegalizeFeature<...>`、
`LegalizeRuleSet<...>` 这类记录名不属于模型：C++ 渲染器在出口通过
`NameTable` 计算声明名，`core`/`check` 从不看这些名字。
`ast.canonicalize_rulesets` 是发射前唯一的 AST 变换；它的存在是为了让生成的
C++ 和冻结的 core JSON 保持“一个 opcode 一张表”，不是因为语言禁止一个
opcode 有多张表。AST 迁移记录在 `docs/REPORT-ast.md`；`.td` 渲染器的移除
记录在 `docs/REPORT-no-td.md`。

测试用例也从同一个模型派生，不是手写的：`gisel cases` 为每个等价类
（规则区域）生成一个代表点，为答案真正翻转的地方生成边界
（位宽、lane、内存大小和对齐上的 `N-1`/`N+1`），以及落到 `Unsupported`
的域外探针。`--against` 只比较生成集和 oracle 的交集；`uncovered` 单独
报告，永远不会被算成通过。`spec/cases.md` 是契约，`docs/REPORT-cases.md`
是证据。

证明两个 legalizer 实现答案一致，是**借助** gisel 完成，而不是 gisel 的
功能本身：`ab/` 冻结一份无答案查询集，把同一份文件同时喂给官方构建和
带我们生成 `.inc` 的构建，再比较两侧的答案流。X86、AArch64、RISC-V 三个
target 的双向对拍都已闭合：`ab/docs/EVIDENCE-WP2.md` 用 gisel 自己的题面
提问（确认上游没有漏掉 gisel 的规则），`ab/docs/EVIDENCE-U.md` 用 oracle
的题面提问（确认 gisel 没有漏掉上游规则）。这套工作台有自己的报告
`docs/REPORT-ab.md`；边界见 `docs/SCOPE.md`。

它不做什么：不生成 `.td`（这个后端已经移除）；`import-cxx` 对任何翻译
不了的语句直接拒绝，而不是猜；九份语料中没有一份是独立手写的第二份规则
陈述——它们都是我们用自己的工具，从 LLVM 手写 C++ 构造函数里提取出来，
作为自证准备的。所有语料都直接从手写 `.cpp` 构造函数到 `.gisel`
（`upstream-source/import/import-cxx.py`）；项目曾在中间加过的 `.td` 已经
不再使用。`docs/CORPORA.md` 逐份说明语料来自哪个上游文件、带哪些经过审查的
偏离，以及冻结产物能证明什么、不能证明什么（三套产物都是自基线；规则保真
来自 import-cxx --check 和端到端 A/B）。

## 状态

| 里程碑 | 后端 | 门禁 | 状态 |
|---|---|---|---|
| M1 | `--emit=inc` | 自基线 + 端到端 A/B（早期标准：与 `-gen-legalizer` 逐字节一致） | 完成 |
| M2 | `--emit=check` | 自基线计数（早期标准：`-gen-legalizer-check` 的 JSON） | 完成 |
| M3 | ~~`--emit=table`~~ | 2026-11-09 移除：table 方向已放弃，`inc` 才是产品 | 已移除 |
| M4 | `--emit=core`、`eval` | core JSON（忽略 `origin` 字段）；求值器能回答任意查询文件 | 完成 |
| v0.2 | `lint` | 57 种节点，九份语料 0 error | 完成 |
| v0.3 | `imm` 轴 | M68k 13/13、WebAssembly 109/109 从 C++ 转录 | 完成 |
| v0.4 | RISCV 语料（工作台导入） | 340 条 builder 调用 → 402 条规则，0 拒绝，`.inc` 可编译 | 完成 |
| v0.5 | `cases` | 等价类 / 边界 / 域外；X86 3,019 条，AArch64 12,559 条 | 完成 |
| v0.6 | 更多 A/B target | M68k 35、WebAssembly 886、PowerPC 94、ARM 1,614、Mips 1,656、SPIRV 5,136 条查询；每个 target `disagree = 0` | 完成 |

M1–M3 行里的 `-gen-legalizer*` 是本项目在 LLVM 研究分支上加的 TableGen
后端（`utils/TableGen/LegalizerInfoEmitter.cpp`），不是上游 main 的功能；
完整链路见 `docs/CORPORA.md`。

迁移和对拍工具属于**工作台**，不是 gisel 的功能
（`docs/SCOPE.md`）：`upstream-source/import/import-inventory.py` 估算接入
一个 target 的成本，`upstream-source/import/import-cxx.py` 把构造函数变成
`.gisel`（遇到任何翻译不了的语句就退出 1，绝不静默丢规则），`ab/` 比较两个
实现。`import-cxx` 是面向钉住版本构造函数的专用一次性转录器，不是通用 C++
解析器：`--all --check` 会重新转录并和入库语料逐字节比对，规则数漂移会
直接报错。证据在 `docs/REPORT-riscv.md` 和 `docs/REPORT-ab.md`。转录器已在
2026 年 11 月迁到同级 `upstream-source` checkout；`tools/import-cxx.py` 只是
保留一个 release 的转发 shim，不是实现。

`tests/artifacts/` 保存九份冻结的 C++/JSON 产物及其 `SHA256`：
X86、AArch64、RISC-V 各三份。上游 LLVM main 没有 legalizer 的 `.td`，也没有
`-gen-legalizer`；规则写死在手写的 `*LegalizerInfo.cpp` 构造函数里，语料就是
从那里转录的。因此这些产物是 gisel 自己的冻结输出——一个漂移基线，不是对
第二个实现的逐字节 oracle。规则保真在另外两层检查：
`upstream-source import --check` 重新转录钉住的 C++，必须逐字节复现入库的
`.gisel`；`ab/` 构建官方 legalizer 和带我们 `.inc` 的 legalizer，喂同一份
无答案查询文件，比较两侧答案流。完整链路和经过审查的偏离见
`docs/CORPORA.md`。

```sh
python3 -m pytest -q                          # 243 passed, 92 subtests
python3 -m unittest discover -q -s tests      # Ran 243 tests
(cd tests/artifacts && sha256sum -c SHA256)   # 9/9
```

`gisel lint` 在正常形上跑 J1/J2b/J3a/J3b 检查，打印
`path:line: RULESET: message`（有 error 退出 1，解析/IO 错误退出 2）。它不需要
LLVM 源码树：opcode arity 表随 `gisel/data/` 分发。

错误指向源文件，而不是合成字符串：

```
$ gisel gen bad.gisel --emit=inc --out x.inc
bad.gisel:6: expected ,, got ID ('pow2')      # exit 2
```

## 不依赖 LLVM 求值

`--emit=core` 生成 schema-0.4 正常形，`gisel eval` 不需要任何 LLVM 二进制
就能回答查询：

```sh
gisel gen tests/corpus/AArch64LegalizerInfo.gisel --emit=core --out a.core.json
gisel cases tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json --out a.cases.jsonl
gisel eval --doc a.core.json --features tests/cases/features.json \
  --cases a.cases.jsonl --answers a.answers.jsonl
# cases=... errors=0
```

`gisel cases` 产出的是问题，不是答案。`--answers` 把求值器的回答写成和编译
出来的 runner 相同的 JSONL 形状，这样 `ab/diff.py` 就能比较两条答案流：

```sh
python3 ../ab/diff.py runner.answers.jsonl a.answers.jsonl --json
```

当某个 runner 已经回答过同一份查询文件时，`gisel cases --against
answers.jsonl` 只比较交集；`uncovered` 单独报告，永远不算通过。

## 目录

```
gisel/ast.py            程序 / 声明 / ruleset / 结构化 LLT
gisel/dsl.py            词法器、规则解析器、core-IR 正常形
gisel/backend/llvm_inc.py  AST -> .inc（M1）
gisel/backend/check_json.py / core_json.py              M2 / M4
gisel/eval.py           独立求值器（回答任意查询文件）
gisel/cases.py          等价类 / 边界 / 域外用例生成
gisel/answers.py        答案文件读取器（对拍本身在 ab/diff.py）
gisel/contract.py       形状契约：哪些类型元组才算问题
gisel/domain.py         opcode 槽位笛卡尔枚举（另一套题面）
gisel/graph.py          (opcode, 类型类, mem, imm) 上的商图
gisel/data/opcode-slots.json   283 条 opcode 的 arity/槽位快照
gisel/data/contract-shapes.jsonc / contract-aarch64.jsonc  形状表
spec/m1-coverage.md     语料的 shim 覆盖率（25 个三元组，0 未覆盖）
spec/cli.md             命令面、退出码、保证（规范性）
spec/grammar.md         .gisel 语法和 AST（规范性）
spec/axes.md            轴/profile 格式及其兼容性钉子
spec/cases.md           生成用例的含义，以及子集契约
spec/cases-format.md    三种 JSONL 投影及其共享 key
spec/contract.md        形状契约：哪些元组根本不算问题
spec/escape-points.md   feature 与 opaque：两个宿主逃逸点
spec/graph.md           商图的状态、后继和出口
spec/semantics.md       一条规则是什么意思（以及求值器做什么）
docs/CORPORA.md         每份语料的来源、偏离和证据分层
docs/LOOP.md            钉版本 -> 出题 -> 对拍 -> 归因
docs/REPORT-ast.md      AST 迁移：移除项、否决方案、边界
docs/REPORT-no-td.md    .td 渲染器移除及剩余冻结文本
docs/REPORT-cxx-corpus.md  C++ -> .gisel 转录（工作台工具）
docs/ALGORITHM-cases.md  作为有界商的用例生成（文章底稿）
docs/REPORT-cases.md    用例生成：证据、否决方案
docs/REPORT-coverage.md 用例集的覆盖证据
docs/REPORT-graph.md    商图证据和环的历史
docs/DESIGN-graph.md    graph 设计记录
docs/REQUIREMENTS-ab.md  工作台：差分测试需求
docs/REPORT-ab.md       工作台：端到端 A/B（不是 gisel 功能）
docs/PLAN-architecture.md  Phase 1-2 清理计划（决策、PR 顺序）
docs/PLAN-internal-authority.md  fork 内部权威：双向题面、负控、oracle 保全
docs/PROPOSAL-host-escape.md  被否决的宿主逃逸点提案（AMDGPU）
docs/SCOPE.md           gisel 是什么，什么只是“用 gisel 做的事”
```

移植的 emitter 逻辑保留 LLVM 许可证头，并注明来源 commit
（`d48f5512a162`）。
