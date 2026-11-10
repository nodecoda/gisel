# 从规则生成测试用例：有界商算法

> 这份文档是写给文章用的算法说明，不是验收报告。验收证据在
> `docs/REPORT-cases.md`；规范在 `spec/cases.md`；实现在 `gisel/cases.py`。
> 命令、数字都可以直接复现。

## 0 一句话

我们不随机采样类型，也不手写边界清单。我们把「规则对查询的答案」定义成等价
关系，用规则自己写出来的切点把无限的 LLT 空间压成一个有限代表集，再在这个
有限集上取商：

```text
equivalence  每个首命中区域一个代表
boundary     相邻两个答案区域之间的翻转点
outside      没有规则命中的补集
```

产物是**不带答案的查询 JSONL**，不是 MIR，也不跑 `llc`。

## 0.1 术语：轴、维度、长度、槽

这四个词最容易混，先把它们分开：

| 概念 | 定义 | 代码里的名字 | 例子 |
|---|---|---|---|
| **轴**（axis） | 查询空间的一个独立坐标；取一个值就确定该坐标 | `per` 的一项、`configs`、`imm_axis`、mem 行 | `slot(0)` 这根类型轴；config 轴 |
| **维度**（dimension） | 一个 LLT 内部被谓词读取的数值量，只有三种：`bits` / `bytes` / `lanes` | `_dim_of` 返回的 `"bits"/"bytes"/"lanes"`；`_mutate(t, dim, n)` | `bits_of(slot(0)) == 64` 读的是 bits 维 |
| **长度**（length） | 一根轴上候选值的个数；**不是**类型的位宽，也不是 lane 数 | `len(per[i])`、`_product_size(per)` | “slot 0 的轴长是 16” |
| **槽**（slot） | 类型元组的下标；一个槽就是一根类型轴 | `slot(i)`、`nslots`、`_slot_of` | `slot(0)` / `slot(1)` |
| **候选集** | 一根轴上的有限取值集合 | `_candidates`、`_mem_candidates`、`imm_candidates` | `B_slot0 = {s8, s16, ...}` |
| **切点** | 谓词真值翻转的阈值 `N` | `RuleInfo.thresholds` | `N = 64` |
| **点 / 查询** | 每根轴各取一个具体值组成的元组 | `Case`、`q` | `(C1, G_ADD, [s32, s32], None, ())` |
| **类** | 等价关系下的一个等价类 | `graph` 的 class id；cases 的首命中区域 | “`s31` 和 `s32` 不一定同类” |
| **商** | 所有类构成的集合 | `B / ~` | 用例就是从商里挑代表 |
| **状态** | 每根轴取一个**类 id** 的元组（graph 用） | graph 的 state key | `(opcode, class0, class1, mem_class)` |

三句话记住区别：

1. **轴是坐标，维度是尺子，长度是刻度数。**
   `slot(0)` 是轴；`bits` 是维度；这根轴上有 16 个候选值是长度。
2. **lane 数不是“长度”，是类型的一个维度。**
   `v4s32` 的 lane 数是 4；说“v4s32 的长度是 4”会和“轴长”混淆。
3. **点的数量、商的大小、用例的数量是三回事。**
   `|B| = Π 轴长`；`|B/~|` 是类数，`≤ |B|`；用例数只数被 emit 的
   equivalence/boundary/outside，通常远小于 `|B|`。

还有一个容易忽略的区别：

- **`opcode` 不是轴**，它是 ruleset 的标签。一个 ruleset 固定在一个或几个
  opcode 上，轴是它内部的类型槽、config、mem、imm。
- **`--axes` 文件不是“新增一类轴”**，它是每根轴取值的策略：`explicit`
  替换候选集，`derive` 在推导结果上增删。

例子（X86 `G_ADD`）：只有一根类型轴，轴长 16，`|B| = 16`；`G_LOAD` 有两根
类型轴（16 × 16 = 256），再乘上 mem 行；RISC-V `G_SEXT_INREG` 多一根
`imm(0)` 轴（10 个值），总点数 16 × 10。

### 0.2 展平：多维的 LLT 值，单根的槽轴

一个 LLT 不是一个标量，它内部有 kind（scalar / vector / pointer）、bits、
lanes、element、address space。我们**不为这些内部维度各开一根轴**，而是：

1. 用规则的切点在这个多维值空间里取有限个**完整 LLT**；
2. 每个 slot 得到一根离散轴，轴上的值是完整 LLT；
3. 谓词求值时再把这些值投影到 bits / bytes / lanes 维度上比较。

所以：

```text
展平：LLT 多维值空间  ->  每个 slot 一根候选列表
维度：值内部的数值投影，也是 boundary 的移动方向
轴：  查询积里的一列，不是维度
```

为什么不能把维度拆成轴：

- kind × bits × lanes 不独立：`v4s32` 的 bits 就是 `4 × 32`，lane 数和元素
  位宽不能自由组合；拆开会产生大量不可达的非法 LLT。
- 跨槽谓词（`in_pairs`、`typeDiffersFromMemDesc`、`same_as`）同时读多个槽，
  维度不属于某一根轴。
- 规则只观察少数投影；把每个投影都升成轴，等于把采样问题变成组合爆炸。

一个容易误解的地方：`RuleInfo.thresholds` 写成 `slot -> {(dim, N)}`，看起来
像“维度是槽的属性”。其实它是**这个 ruleset 的谓词在该槽上的观察**，不是轴
的固有属性；换一个 ruleset，同一个槽的阈值集合可以完全不同。

一个副作用：boundary 的 `N±1` 是沿维度对“值”做局部移动，可能落在候选集
`B` 之外。`B` 只约束 equivalence/outside 的枚举，不限制 boundary 的探测。

## 1 问题：为什么不能靠采样

LLT 的空间是无限的：`s1`、`s3`、`s24`、`s31`、`s33`、`v3s32`、`nxv4s32`、
`p0:32`、`p0:64`……规则真正关心的却只是少数几个切点：

```text
in(slot(0), [s8, s32, v4s32])
bits_of(slot(0)) == 64
num_elems(slot(0)) <= 8
is_pow2(slot(0))
in_mem_desc(slot(0), slot(1), mem_slot(0), [...])
imm(0) == 32
```

随机采样会反复落在同一个答案区域里，覆盖率无法解释；全笛卡尔积会爆炸，而且
绝大多数点答案相同；手写清单会随规则漂移。我们要的是：**每个答案区域至少
一个代表，每条规则自己声明过的边界都被碰到。**

## 2 三个对象

查询：

```text
q = (config, opcode, types, mem, imms)
```

答案：

```text
A(q) = (首命中 rule, action, type_idx, new_type)
     = Unsupported                      没有规则命中
```

`config` 是特征真值表的一行。同一组类型在不同 config 下可以是不同答案，所以
商是**按 config 分别取**的。

## 3 商：按答案等价

### 3.1 定义

固定一个 config，定义

```text
q ~ q'  ⇔  A(q) = A(q')
```

`Q/~` 就是答案商。两个类型是否同类，不看位宽像不像，只看**这个 ruleset 的
全部规则对它们的回答是否完全一样**，包括哪条规则先命中。

这和「按谓词向量分类」是同一件事的两种粒度：

- `gisel graph` 用每个原子谓词的三值向量 `(True/False/None)` 做更细的商类，
  用来建商图找环；
- `gisel cases` 直接用答案函数做商，用来出题。

两者共用同一份切点提取 `inspect_ruleset`。

### 3.2 有界：切点闭包

`Q` 无限，但谓词真值只在切点处翻转。于是取一个有限集 `B ⊂ Q`：

```text
B = 每个槽的候选类型 × 内存候选 × 立即数候选 × config
```

候选类型必须满足两条：

1. **包含规则写出的每一个字面量**；
2. **每条阈值 N 的两侧都有代表**（`N-1`、`N`、`N+1`）。

然后枚举 `B`，隐式地建出 `B/~`。这就是「有界商」：不是对无限空间取商，而是
对切点闭包取商。

## 4 算法总览

```text
parse .gisel
  -> canonicalize rulesets
  -> core schema 0.4 document          # 与 gen --emit=core 同一份正常形
  -> for each ruleset:
       inspect_ruleset()               # 提取槽、字面量、阈值、mem、imm
       build B_types / B_mem / B_imm   # 有界代表集
       for each config:
         enumerate B, evaluate first match
         emit equivalence / boundary / outside
  -> JSONL
```

关键点：**测试用例不是第二套模型**。`document()` 走的是和代码生成完全相同的
解析、规范化和 `core_json` 发射路径。规则改了，用例自动跟着变。

### 4.1 轴的存在性：结构标记 + 值集，不是一个总开关

代码里没有一张全局的「轴注册表」，也没有 `if values: axis_on` 的统一判断。
每个 ruleset 先做一次统一的观察分类（`RuleInfo`），然后按轴各自的规则决定：

| 轴 | 何时存在 | 值集为空时 | 代码 |
|---|---|---|---|
| config | 总是 | 没有 config → 退出 2 | `cases.py:650` |
| type slot | 总是，每个 slot 一根 | 用默认 `s32` | `_candidates` `cases.py:531-533` |
| mem | 任一规则 `uses_mem` | 没有 `inMemDesc` 行 → **没有 mem 查询点**（覆盖缺口，不静默关轴） | `cases.py:678`、`_queries:623-638` |
| imm | 任一规则读 `imm(i)` | `_imm_tuples` 返回 `[()]`，等于没有 imm 轴 | `imm_candidates:368-397`、`_imm_tuples:400-414` |
| ordering | 任一规则 `uses_ordering` **且** `--axes` 声明 orderings | 回退到 `NotAtomic` | `cases.py:679-682`、`axes.ordering_pairs()` |

所以准确的说法是：**结构标记决定轴是否存在，值集决定轴的长度；空值集在 type /
imm / ordering 上有默认，在 mem 上是覆盖缺口。**

### 4.2 config 轴：一行是一张真值表

config 轴不是固定枚举，而是 feature 真值表的行：

```python
class Features:
    table: dict[str, dict[str, bool]]   # config -> {feature expr: bool}
```

规则侧：

```text
feature X_HasAVX512 = Subtarget.hasAVX512()
```

规范化后是：

```json
{"kind":"leaf","name":"hasFeature","args":["Subtarget.hasAVX512()"]}
```

求值时：

```python
features.get(config, "Subtarget.hasAVX512()")
```

所以每个 target 的 feature 集合由**该 target 的规则文本**决定：

| target | config 行 | feature 表达式前缀 |
|---|---:|---|
| X86 | 4（C0–C3） | `Subtarget.*` |
| AArch64 | 9 | `ST.*`、`TM.getCodeModel()` |
| RISC-V | 8 | `ST.*`、`STI.*`、`XLen 比较` |

表里多出来的键不会影响结果；规则读到的键缺失会直接
`unknown_feature` 报错，不会当成 `false`。这就是为什么 AArch64 语料从
`Subtarget.*` 改成 `ST.*` 时，features 表必须一起改。

没有 `--features` 时，`derive_features` 从文档里的 `hasFeature(...)` 派生
合成行：`none`（全假）、`all`（全真）、`only-N`（只把第 N 个置真）。这些
行只用于覆盖规则，不代表真实子目标；和 oracle 对拍必须传真实表。

## 5 切点提取：`inspect_ruleset`

对每个 ruleset，`inspect_rule` 递归遍历每条规则的 `predicate`、`on`、`to`，
把下面这些信息收集到 `RuleInfo`：

| 字段 | 来源 | 用途 |
|---|---|---|
| `literals[slot]` | `in(slot(i), [T...])`、`in_pairs`、`in_triples`、`typeIs` | 直接候选；永不丢弃 |
| `thresholds[slot]` | 字面量的 bits/lanes；`bits_of`/`size_of`/`size_in_bytes_of`/`num_elems` 与整数的比较；`is_pow2` 的 2 的幂 | 生成 `N-1/N/N+1` 边界 |
| `mem_entries` | `in_mem_desc(..., [[t0,t1,mty,align], ...])` | 内存查询行 |
| `uses_mem` | 任何 `memSlot`/`memSize`/`inMemDesc`/`typeDiffersFromMemDesc` | 是否带 mem 轴 |
| `uses_ordering` | `mem_ordering`/`mem_failure_ordering` | 是否乘 ordering 轴 |
| `imms` / `imm_values` / `imm_thresholds` | `imm(i)`、`imm(i)==N`、`in(imm(i), [...])` | 立即数轴 |

`inspect_ruleset` 同时算出 `nslots`：规则和变异里出现过的最大槽号 +1。后面的
候选集是「每槽一组值」，但答案等价是在**整个类型元组**上判定的——跨槽谓词
（`in_pairs`、`typeDiffersFromMemDesc`）不会被拆成单槽判断。

## 6 构造有限代表集 B

### 6.1 类型

每个槽的候选按顺序拼：

```text
1. 规则字面量（全部）
2. 邻居 _neighbours()
3. 兜底 sentinel
4. core domain 里声明的类型（最后，超限时先丢它）
```

`_neighbours` 生成：

- 标量/指针：位宽 `bits-1`、`bits+1`；float 只取 `16/32/64/80/128`；
- 向量：lane `±1`，加 `1/2/4/8/16/32/64` 的精确值（只靠 `±1` 会漏
  `v4s8` 这种跨幂的切点），fixed ↔ scalable 翻转；
- `bf16` ↔ `f16`。

sentinel 是 `s32, s64, s8, s16, s128, s1, s3, s7, s24, s31, s33, s63, s65,
v4s32, v2s64, v16s8, nxv1s8, v3s32, nxv4s32, p0:64, p0:32, p0:128, p0:*,
f16, f32, f64, bf16`。它们保证「规则什么字面量都没写」时也能出一个普通见证，
并且能探到域外形状。

两个界，性质不同：

- 每槽默认 16 个（`--axes` 的 `cases.max_slot_values` 可改），但它是**软预算**：
  字面量和邻居永远保留，只有域类型受 16 约束。所以单槽实际候选数可以超过 16，
  AArch64 `G_ADD` 实测 105。`cases` 的 stats 打印 `slot_budget`、`candidate_max`、
  `candidate_over_budget`，读者不必猜测这条轴有多宽；
- 整个笛卡尔积超过 20,000 时，从**最宽的轴**尾部逐个删。这是硬界。

字面量和邻居都排在域类型前面，所以产品超限时**先丢域类型**。这一点是硬约束，
不是排序偏好：突变规则（`widen` / `clamp_min` / `scalarize` …）只能被「合法集合
之外的某个值」触发，而这个值就是某个字面量的邻居。曾经的实现把截断长度取成
`max(cap, len(literals))`，于是一个槽位的字面量一旦达到 `cap`，邻居就被整批
裁掉，AArch64 有 406 条规则因此**永远没有见证**——对拍照样报 0 分歧，因为根本
没问。修复后的对照数字见 `docs/REPORT-coverage.md`。

`--strict-coverage` 把「无见证的规则数」变成退出码 1，让这件事不能再沉默。

#### 形状：槽不是独立轴

上面的候选是**逐槽**构造的，但一个查询的多个槽不是互相独立的：LLVM 的
generic opcode 对槽之间的关系有约束。`G_CONCAT_VECTORS` 的结果必须有源的两倍
lane 数、且元素类型相同；`G_SHUFFLE_VECTOR` 的源必须是向量、且不能改元素类型。
直接对逐槽候选做笛卡尔积，就会造出这种形状：

```text
G_CONCAT_VECTORS  (v16s8, v2s32)     # concat 两个 v2s32 得到 v4s32，不是 v16s8
G_SHUFFLE_VECTOR  (v16s8, s32)       # 源是标量
G_FPTOSI_SAT      (v2i64, f16)       # 标量和 2-lane 向量配对
```

这些不是"难测的点"，是**问不出来的点**：真实的 MIR 里它们不可能出现。把官方的
legalizer 叫过去，它会在 `LegalizeRuleSet::apply` 的
`mutationIsSane(Rule, Query, Mutation)` 上直接断言（AArch64 上 108 条）。

所以候选乘积之后要过一层形状过滤。它不是"跳过不好测的输入"，而是**把问题限定
在能被问出来的集合里**——分母必须先于答案成立。

约束的来源分三档，每一条都要能指回依据：

| 来源 | 含义 | 例 |
|---|---|---|
| `MachineVerifier.cpp` | 上游 verifier 就拒绝的形状 | `G_CONCAT_VECTORS`（1602 行）、`G_SHUFFLE_VECTOR`（1945 行） |
| `semantics` | verifier 没查，但 opcode 的定义不允许 | `G_FPTOSI_SAT` 的 lane 一致性；`G_CONCAT_VECTORS` 的元素类型一致 |
| 未列出 | 不猜 | 其余 opcode 的槽仍然是独立轴 |

第二档必须单独标出来，因为它弱于第一档。例子很实在：`G_CONCAT_VECTORS` 的
verifier 只比较 lane 总数，**不比较元素类型**，所以 `(v4s32, v2s16)` 能过
verifier，然后让 legalizer 断言。concat 的定义是"把两个同元素类型的向量粘起来"，
所以这条按语义过滤；但它是语义推断，不是抄 verifier。

还有一类约束不在候选乘积里，而在槽表里：`opcode-slots.json` 的 `ptype` 标出
**这个槽只能是指针**（`G_LOAD` 的地址、`G_ATOMICRMW_*` 的 `ptype1`）。这些槽不
参与 24 类型枚举，只取当前配置的 `p0:{width}`——否则会造出"地址是 f128"这种
点。2026-11-11 之前槽表只扫 `def` 自己的 body，`def G_ATOMICRMW_OR :
G_ATOMICRMW_OP;` 这类定义拿不到 `ptype`，AArch64 domain 因此多出 211,680 条
非法点。现在生成器会跟一层 class body，两个表由同一次解析产出。

过滤点有两处，缺一不可：

- `_queries()` 在乘积时丢，省掉后面的求值开销；
- `generate()` 的 `emit()` 再兜一层，因为 boundary 和定向 witness 两条路径会
  **直接构造**类型，不经过乘积。

丢弃必须被计数，不能静默：

```text
ill-formed=15582 (G_CONCAT_VECTORS 3435, G_FPTOSI_SAT 7951,
                  G_MERGE_VALUES 288, G_SHUFFLE_VECTOR 3628,
                  G_UNMERGE_VALUES 280)
```

数字同时出现在文本输出和 `--json` 的 `stats.ill_formed` /
`stats.ill_formed_opcodes` 里。它回答的是"我们主动放弃了多少个百分点"，
而不是藏起来。

还有两个连带的地方不修就会把覆盖数虚高：

1. **定向搜索也要形状感知**。`_satisfiable` 和 `_rule_witness` 会用默认值填
   规则没有枚举的槽；默认值可能和已选值不组成合法形状。修复前它们会"找到"
   一个问不出来的查询，于是规则被记为已覆盖。`_compatible_types()` 枚举所有
   合法的填充，两个搜索都从它取。
2. **没有字面量的槽要镜像别的槽**。`G_SHUFFLE_VECTOR` 的规则只写 `slot(0)`，
   `slot(1)` 的候选就只剩 domain 的前 16 个，里面可能一个同元素向量都没有，
   于是合法配对根本凑不出来。`_candidates()` 现在让这种槽先用同一 ruleset
   其它槽的字面量。

效果（AArch64，同一棵树）：

| | 过滤前 | 过滤后 |
|---|---:|---:|
| 查询 | 13,199 | 12,952 |
| 两侧都断言 | 108 | **0** |
| 有见证的规则 | 572 | **572** |

规则覆盖没有下降是这条约束的验收条件：如果过滤让某条规则失去见证，说明要么
约束写错了，要么那条规则真的只能被非法输入触发——两种都要停下来看，不能拿
"分母变小了"当成功。

### 6.2 内存

内存行来自 `in_mem_desc` 的 `(t0, t1, mty, align)`：

- `mty` 可能是配置相关的 `select`，两个分支都展开成具体 LLT；
- 生成 `align-1 / align+1` 和 `mty` 位宽的 `bits-1 / bits+1` 作为边界；
- 读 `mem_ordering` 的 ruleset 再乘 `(ordering, failure_ordering)` 采样点
  （由 `--axes` 的 `mems.orderings` 提供；没提供时只采样 `NotAtomic`）；
- `in_mem_desc` 的行会和少量「无关类型元组」交叉，用来命中
  `typeDiffersFromMemDesc` 这种「槽和内存类型不一致」的规则。

### 6.3 立即数

`imm(i)` 的候选 = 规则里出现的值 ∪ `{0}` ∪ 每个值 `±1`，每个 ruleset 的
组合上限 32。没有规则读 `imm(i)` 时，`imms` 为空。

### 6.4 界可以被显式声明

`--axes` 把「界」从隐式采样变成可审阅的输入：

- `types.mode = "derive"`：在推导结果上 `add` / `remove`；
- `types.mode = "explicit"`：用声明的一组类型**替换**推导结果；
- `mems.rows` / `mems.orderings` / `imms` 同理；
- `profiles.cases.max_slot_values`、`boundaries`、`max_outside` 控制预算。

没有 `--axes` 时行为不变。这一点对文章很重要：有界商的「界」不是藏在校验和
里的魔法，而是一个可以写出来、审阅、版本化的文件。

## 7 三类用例

### 7.1 equivalence：首命中区域的代表

枚举 `B` 的每个点，用与 `gisel eval` 相同的语义求值：

```text
for q in B:
    res = first rule whose predicate is true
          and whose implicit shim guard succeeds
    if res is None: continue
    fires[(config, rule_index)].append(q)
```

对每个 `(config, rule)` 取第一条（mem 规则最多 4 条）作为 equivalence 用例。
它满足：

- 本规则 predicate 为真；
- 本规则隐式 guard 为真；
- 更早的规则要么 predicate 为假，要么 guard 失败。

所以它是「这条规则首命中区域」的见证，也是答案商里一个类的代表。

隐式 guard 必须算进去：`widenScalarToNextPow2`、`clampScalar` 这些变异自带
`is_scalar`/`is_pow2`/lane 数检查。如果只按谓词分类，`s3` 和 `s32` 会被并成
一类，`s3 -> s32` 看起来就像回到自己。

### 7.2 boundary：答案翻转的相邻点

取该规则的 witness，对它的每个阈值 `N` 做：

```text
for slot, (dim, N) in thresholds(rule):
    for probe in (N-1, N, N+1):
        q' = witness with slot resized to probe
        if A(q') != A(witness):  emit boundary(q')
```

`dim` 可以是 `bits`、`bytes`、`lanes`；内存另有 `align±1`、`mty bits±1`；
立即数是 `N-1/N+1`；ordering 规则换 ordering 组合。

只保留答案真的变化的点。因此每条 boundary 都能指出另一侧的代表：**两点答案
不同**。`N` 本身通常和 witness 答案相同，会被过滤掉。

注意边界比较的是 `(action, type_idx, new_type)`，不含 rule index；它找的是
「动作翻转」，比 equivalence 的区域粒度粗一层。这是有意的：边界要的是行为
差异，不是规则编号差异。

### 7.3 outside：商的补集

`B` 里没有任何规则命中的点：

```text
A(q) = Unsupported
```

每个 `(config, ruleset)` 最多保留 `--max-outside` 条（默认 2）。mem 规则额外
插入 `s3` / `p0:64` 这类探测，专门打兜底路径。

outside 用例是**查询形状**，不保证是合法 MIR 指令；它测的是「没有规则命中时
系统怎么回答」，不是指令合法性。

### 7.4 shadowed / unexercised

不是每条规则都能被见证：

- **shadowed**：规则本身可满足，但被更早的规则挡住，从未首命中；
- **unexercised**：在给定 config 集合下，用同一套有界候选也找不到满足
  predicate + guard 的点。

`_satisfiable` 只枚举该规则实际读的槽，其它槽用默认值，逐 config 试 mem 和
imm。两者都写进 `--json` 统计，不静默丢。

## 8 一个完整例子

X86 规则：

```text
legal (X_UseX87 and in(slot(0), [X_s80]))
```

1. `inspect_rule` 从 `in` 取出字面量 `s80`，写入 `literals[0]`；
   `_add_literal` 同时把 `bits=80` 写入 `thresholds[0]`。
2. `_candidates` 生成 `s79`、`s80`、`s81`。
3. 枚举求值：`s80` → Legal；`s79`、`s81` → 落到后面的 widen。
4. 生成 boundary：

```json
{"types":["s79"], "kind":"boundary", "reason":"bits 80 -> 79"}
```

同一招在 `G_IMPLICIT_DEF` 的 `s128` 上给出 `s127`；在 RISC-V
`G_SELECT` 的 `clampScalar(0, s32, R_maxScalar)` 上给出 32/64 两侧的边界。

## 9 压缩路径：全量 A/B → 回归集

上面的算法是「从规则直接出题」。还有一条下游路径，用于把全量对拍结果压成
回归集：

```sh
gisel cases SOURCE --queries full-queries.jsonl --oracle answers.jsonl ...
```

规则：

- `queries` 固定测试总体，`oracle` 必须给每条查询一个答案；缺一条算
  `oracle_missing`，失败；
- 两边都标成 `unanswerable` 的查询保留统计，不冒充答案差异；
- 对每个 `(config, ruleset, rule)` 最多保留 4 个 witness；
- 在同一个 `(config, opcode, mem, imms)` 组内按类型排序，相邻两条 oracle
  答案不同就记一条 boundary，每组最多 24 条；
- 没有规则命中的查询按 outside 保留，每个 `(config, opcode)` 最多 2 条。

这条路径的意义：用例集是从**端到端真实运行**的答案里压出来的，不是拿生成器
自证。

## 10 和 `domain`、`graph` 的关系

- `gisel domain`：枚举与规则无关的 D*。轴来自 opcode 声明的槽位
  （`gisel/data/opcode-slots.json`）、源文件声明的类型、内存行、imm 和
  ordering。它是全量 A/B 的固定题面，不偏向任何规则。
- `gisel cases`：规则感知的有界商，用于覆盖和回归。它比 domain 小得多，
  但每个点都有「为什么在这里」的理由。
- `gisel graph`：用原子谓词向量显式建商类，再建商图找环。它和 cases 共用
  `inspect_ruleset` 的切点，是同一理论的两个消费者。

X86、4 个 config 的 domain 实测是 91,340 条查询、113 个 opcode、24 个类型、
23 个内存行；cases 只有 3,019 条，但覆盖了答案区域和边界。

domain 先过一层**opcode 形状**约束，再谈值域：`G_MERGE_VALUES` 只能合并标量，
`G_UNMERGE_VALUES` 的向量形式要求各槽元素类型和 scalability 一致
（`MachineVerifier.cpp`）。这些形状在 verifier 就被拒、到不了 legalizer，
所以不算题面。X86 的形状过滤后每配置 23,793 条；2026-11-10 又把比较指令
结果槽不是整数的点过滤掉（`G_ICMP`/`G_FCMP` 的 type0 只能是整数），剩
22,835 条（4 个配置 91,340）。

### 10.1 三个 target 的轴差异

生成器里没有 `if target == "X86"` 这种分支。三个 target 的差别全部来自数据：
规则文本、类型/内存声明、feature 真值表，以及可选的 `--axes` 文件。轴还是
同一组，变的是**哪些轴被规则激活**、**轴上放什么值**。

| | X86 | AArch64 | RISC-V |
|---|---|---|---|
| config | 4（C0–C3） | 9（baseline + 单特性变体） | 8（rv32/rv64 × G/C/V/Zbb/Zfh/Zilsd） |
| rulesets / rules | 63 / 328 | 114 / 743 | 91 / 413 |
| 类型声明 | 24 | 49 | 46 |
| `select` 类型 | 12（AVX/AVX512 的最大向量） | 0 | 3（`sXLen`、`sDoubleXLen`、`maxScalar`） |
| 可伸缩向量 | 无 | 有（SVE `nxv`） | 有（V `nxv`） |
| 指针宽度 | `p0:*`，按 config 32/64 | 固定 64 | `p0:*`，按 config 32/64（XLen） |
| 读内存的规则 | 21 | 24 | 26 |
| 读 ordering 的规则 | 0 | 8 | 0 |
| 读 imm 的规则 | 0 | 0 | 1（`G_SEXT_INREG`） |
| `LLT::getUseExtended()` | false | true | false |

**X86**：config 轴是 SSE2 / AVX / AVX512 这些子目标级别，C0/C3 是 32 位、
C1/C2 是 64 位；类型轴里 12 个 `select` 把「最大向量」表达成 AVX 级别相关的
选择。没有 ordering，也没有 imm。

**AArch64**：config 轴是 9 行「baseline + 单特性」；类型轴同时包含 NEON 固定
向量和 SVE `nxv`；指针固定 64。8 条规则读 `mem_ordering`，但 ordering 轴默认
不激活——不传 `--axes tests/cases/aarch64-mem-orderings.axes.json` 时它们只会
落到 unexercised。加上之后：cases 9,911 → 10,271，witnessed 315 → 321，
unexercised 403 → 397。

**RISC-V**：config 轴同时带 `XLen`/`ELen`；类型轴有 3 个 XLen 相关的 `select`
和 V 扩展的 `nxv`；指针宽度就是 XLen，所以 `p0:*` 在 32/64 两种 config 下
分别解析。内存类型里还有 `select(XLen == 64, s64, s32)` 这种配置相关的
`mty`，两个分支都会被展开。唯一读 imm 的规则是 `G_SEXT_INREG`，所以 imm 轴
只对它激活。

一个容易忽略的语义差别：`LLT::getUseExtended()` 不新增轴，但它决定
`f16`/`bf16`/`i32` 是不是独立 kind。AArch64 为 true，X86/RISC-V 为 false，
所以同一个 `f16` 在 RISC-V 上按 `scalar(16)` 处理。轴相同，值语义不同。

## 10.2 产物格式：一份 key，三种投影

`gisel cases` 写查询，`gisel domain` 写题面，`gisel eval --answers` 或外部
runner 写答案。三者共用同一个 key：

```text
(config, name, types, mem, imms)
```

差别只在附加字段：cases 多 `kind` / `ruleset` / `rule` / `reason`（标注，
消费者忽略），答案多 `action` / `type_idx` / `new_type` 或
`status:"unanswerable"`。格式规范见 `spec/cases-format.md`。

标准化的是 key 语义，不是“所有文件一个 schema”：`mem` 读方接受
`[mty, align]` 与 `[mty, align, ordering, failure_ordering]` 两种写法，
缺省补 `NotAtomic`；全量对拍要求 key 集合相等，子集对拍只报告交集。
`p0:*` 仍是一个已知缺口：查询保留通配，答案侧常写具体宽度，这类点只能算
`uncovered`，不能算通过。

## 11 规模与实测

命令：

```sh
python3 -m gisel cases tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --out /tmp/x86-cases.jsonl --json

python3 -m gisel cases tests/corpus/AArch64LegalizerInfo.gisel \
  --features tests/cases/features.json --out /tmp/a64-cases.jsonl --json

python3 -m gisel cases tests/corpus/RISCVLegalizerInfo.gisel \
  --features tests/cases/riscv-features.json --out /tmp/rv-cases.jsonl --json
```

当前语料实测（2026-11-10，逐项见 `docs/REPORT-cases.md`）：

| target | configs | cases | equivalence | boundary | outside | rules | witnessed | shadowed | unexercised | 时间 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| X86 | 4 | 3,019 | 1,109 | 1,522 | 388 | 328 | 318 | 5 | 5 | 1.8 s |
| AArch64 | 9 | 12,559 | 5,191 | 6,290 | 1,078 | 743 | 575 | 38 | 130 | 3m17s |
| RISC-V | 8 | 6,086 | 2,242 | 2,996 | 848 | 413 | 355 | 12 | 46 | 2m11s |

早期基于冻结 dump 的交集对拍（`x86_ref_dump.jsonl` 等）已于 2026-11-10
删除；那些数字只属于历史快照，不再作为证据。现在的 G 侧证据是
`ab/EVIDENCE.json` 里的 `G/*` 与 `D/x86`，由 `ab/verify-evidence.sh` 校验。

复杂度上界很粗：`O(configs × Π_slots |B_slot| × rules)`。真正的约束是
`|B| ≤ 20,000`、每槽 16 个候选、boundary 每条规则 24 条，所以时间是
秒级到十几秒，不需要 LLVM。

## 12 这个方法证明了什么，没证明什么

**证明了：**

- 每个被见证的规则，都有一个满足 predicate + guard 的具体查询；
- 每条被保留的 boundary，两侧答案确实不同；
- 生成集和 oracle 的交集上，答案逐字段一致（`disagree=0`）。

**没证明：**

- 「所有规则都可达」：shadowed/unexercised 会明确列出来；
- 「没有漏掉别的边界」：只探测规则写出来的阈值；组合条件、没有字面量的
  薄区域可能漏；
- 「outside 是合法指令」：它只是查询形状；
- 「生成集覆盖了 oracle 全量」：`uncovered` 单列，不算通过。

这就是有界商的诚实口径：**给的是下界和可解释的覆盖面，不是完备性证明。**

## 13 可以直接引用的句子

- 「测试用例不是手写的点集，而是规则答案商上的代表。」
- 「有界不是随机采样：每个字面量都保留，每条阈值两侧都取代表。」
- 「equivalence 证明规则可达，boundary 证明动作翻转，outside 证明兜底路径。」
- 「uncovered 不是通过——它只说明还没有答案。」
- 「格式标准化的是 key 语义，不是把所有产物合成一个 schema。」
