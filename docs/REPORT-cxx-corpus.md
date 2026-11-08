# 语料链路：从手写 C++ 直接转录（专用一次性工具）

状态：完成。三份主语料（X86 / AArch64 / RISC-V）现在都从上游手写
`*LegalizerInfo.cpp` 构造函数直接转录成 `.gisel`；中间那层 `.td` 不再参与。

## 1 结论

```text
upstream *LegalizerInfo.cpp（getActionDefinitionsBuilder 链）
  -> tools/import-cxx.py      （一次性转录，0 拒绝）
  -> tests/corpus/*.gisel
  -> gisel gen --emit={inc,check,table,core}
```

| 目标 | 源 sha256（前 12 位） | rulesets | rules | 拒绝 |
|---|---|---:|---:|---:|
| X86 | `79f2376096c3` | 63 | 328 | 0 |
| AArch64 | `2b5377c3eedd` | 117 | 744 | 0 |
| RISC-V | `ad529e1f1a9e` | 96 | 402 | 0 |

`tests/artifacts/` 的十二份产物已按新语料重生成。它们**是 gisel 自己的冻结
输出**，用于抓漂移，不是“与上游逐字节一致”的 oracle；规则保真靠
`tests/cases/*_ref_dump.jsonl` 的答案门（X86 5632 点、AArch64 9632 点、
RISC-V 19512 点，全部 agree）。

## 2 为什么删掉中间的 `.td`

上游 LLVM main 没有 legalizer 的 `.td`，`llvm-tblgen` 也没有
`-gen-legalizer`。规则只写在 C++ 构造函数里。我们曾在 LLVM 分支上加过
`.td` + emitter，让 gisel 读 `.td`；那等于维护**第二份规则陈述**：上游改
C++，我们改 `.td`，再让 gisel 读 `.td`，任何一层走神都会静默漂移，而且
A/B 还要多一轮“`.td` vs C++”的对拍。

现在只有一份输入：C++ 构造函数。`.td` 后端（`--emit=td`、`gisel bootstrap`、
`gisel/td.py`）已在 `REPORT-no-td.md` 里退役。

## 3 为什么是专用工具，不是通用 C++ 导入器

`tools/import-cxx.py` 只认这三个构造函数用到的那一小撮写法。目标表
`TARGETS` 写死了三个目标、源相对路径、前缀和规则数；`--all --check`
重新转录并和仓库里的 `.gisel` 逐字节对照。规则数变了就报 `DRIFT` 并返回 1，
不会悄悄换一份语料。

这比“通用解析器”更可靠：三个构造函数的差异（`XLen`、`ST`、私有 helper、
`changeTo`、`is_contained`……）不需要抽象成配置项，直接写在翻译器里；上游
改了写法，工具报错，人再改工具——而不是让工具猜。

原则不变：**翻译不了就带行号拒绝，绝不静默丢规则**。下面三个真 bug 都是
这条原则抓出来的。

## 3b 生成名的人工审阅（LLM 提议，表里冻结）

转录器最初给匿名三元表达式起名 `X_sel0` / `X_cond0`，给带接收者的
feature 起名 `A_ST_hasNEON`。这些名字语义没错，但读起来像机器产物。现在
名字分两层：

- **结构化来源优先**：C++ 里有名字的类型（`sMaxScalar`、`s8MaxVector`）
  直接沿用，不再丢成 `selN`。
- **LLM 审阅 + 冻结表**：匿名表达式由模型读定义和用途后提议名字，结果写进
  `SELECT_NAMES` / `FEATURE_NAMES`。key 是去掉 target 前缀后的 C++ 表达式；
  每个 key 必须被命中，没命中的 selector 或残留的 `selN`/`condN` 都报
  `DRIFT`（rc=1），所以上游一改，表就失效而不是悄悄退化。

命名规则：

| 情况 | 处理 | 例子 |
|---|---|---|
| C++ 变量本身有名字 | 沿用 | `sMaxScalar` → `X_sMaxScalar` |
| 嵌套三元的内层 | `<外层名>NoAVX512` | `X_s8MaxVectorNoAVX512` |
| 条件是单个 feature | 直接写进 `select`，删掉 `pred` 别名 | `select X_sse2MaxScalar = if X_HasSSE2 then ...` |
| 条件是复合谓词 | 保留 `pred`，用审阅名 | `pred X_useX87NoSSE1` |
| 接收者前缀 | 去掉 `ST_`/`STI_`，但不同接收者不合并 | `R_hasStdExtZbb` / `R_subtargetInfoHasZbb` |
| 比较表达式 | 按实际关系命名 | `XLen <= ST.getELen()` → `R_XLen_le_ELen` |

`R_ST_hasStdExtZbb` 和 `R_STI_hasStdExtZbb` 看着一样，但 features 表里是两个
独立的配置轴，合成一个会改变语义，所以保留两个名字。这是“重命名”不是
“化简”。

语义保持的证据：三个目标的冻结查询答案门全部仍然 agree；`inc/table/core`
产物重新冻结后测试全绿。名字只影响可读性和产物字节，不影响求值。

## 4 三个真实 bug

1. **`const_eval` 把运行时条件当常量**
   RISC-V 的 `if (XLen == 64)` 里，`XLen` 被当成未知字符串，和 `64` 比较
   得到 `False`，整个分支被静默丢掉（丢 8 条规则）。修法：比较两侧类型不同
   就 `Refuse`，不再猜。现在 `XLen == 64` 保留成命名 feature `R_XLen_64`。

2. **`changeTo(i, j)` 被翻译成 `widen`**
   `changeTo` 改的是**类型本身**（含 lane 数），`widen` 只改元素宽度。AArch64
   `G_ABS` 因此语义错。现在 `changeTo(i, j)` → `same_as(j)`，
   `changeTo(i, Ty)` → `replace(ty(Ty))`，
   `changeElementSizeTo` → `replace(elt_size_to(...))`。

3. **`1u << Log2_32_Ceil(x)` 被当成比较**
   旧的比较切分把 `<<` 的第一个 `<` 当关系运算符，切出 `mul(..., 1u <)`。
   现在按长度优先匹配 `<<`/`>>`，并剥掉 `u`/`LL` 后缀。

另外补齐的写法：`is_contained({...}, x)` 的整型集合展开成析取、非 imm 主语的
`switch` 展开、`imm_idx` 不加 guard、`bool X = ...` 与 `feature(...)` 共用
前缀、`LLT::vector/integer` 走命名类型。

## 5 X86 的两条受审偏离

工具不是“照抄”：有两处有意改写，每处都断言上游文本仍在，上游改了会
`SystemExit`，不会空转。

| 偏离 | 原因 |
|---|---|
| `G_BUILD_VECTOR` 去掉最小 lane clamp（4 条 `clamp_min` + 1 条 `more`） | 加 lane 会把 build vector 变成更大的 build vector，缩回来又是同一个查询，legalizer 死循环；只留最大 clamp，窄 build vector 走 Unsupported |
| `G_CTPOP` 增加 VPOPCNTDQ（512 位以下再加 VLX）的向量 legal | 上游构造函数还没有这段；冻结答案里这些点是 Legal |

## 6 证据

- 转录：三个目标 0 拒绝，`--all --check` 逐字节匹配。
- 生成：`python3 -m unittest discover -q -s tests` 全绿（188 tests）。
- 行为：三个目标的冻结查询全部 agree，0 disagree。
- 计数：`tests/artifacts` 总调用 1074 = 1071 + 3（`immIdx` 3 条，来自
  AArch64；`gisel/ast.py` 的 `canonicalize_rulesets` 已按 opcode 汇总
  `imm_idx` 覆盖信息，修掉了 AArch64 `immIdx` 被最后一块覆盖成 0 的 bug）。

## 7 未覆盖

- 换上游修订需要改 `TARGETS` 里的计数并重新生成，不是运行时参数；这是
  有意为之。当前三份输入钉的是和冻结答案同一次构建的源码修订（sha 见上表），
  不一定是最新 upstream；换修订就要连答案一起重冻。
- M68k / WebAssembly 仍是人工转写的小探针，不在 `--all` 里。
- LLVM 研究分支上残留的 `.td` / `-gen-legalizer*` 代码不在本仓库清理范围；
  gisel 这边已经不再读它。
