# 用例与答案文件格式（规范，v0.1）

状态：规范性。相关实现：`gisel/cases.py`（查询）、`gisel/domain.py`（题面）、
`gisel/eval.py`（答案）、`gisel/answers.py`（读入）。上层对拍命令
`ab/diff.py` 属于工作台，不在 gisel 的产品面内。

## 1 三种文件，一个 key

JSONL，一行一个对象。三种文件不是三套模型：

| 文件 | 谁写 | key | 标注 | 答案 |
|---|---|---|---|---|
| 查询文件（cases） | `gisel cases` | 有 | 有 | 无 |
| 题面文件（domain） | `gisel domain` | 有 | 无 | 无 |
| 答案文件（answers） | `gisel eval --answers`、外部 runner、冻结 dump | 有 | 无 | 有 |

key 固定为：

```text
(config, name, types, mem, imms)
```

`kind` / `ruleset` / `rule` / `reason` 是标注，不参与 key，也不参与答案比较；
消费者必须忽略它们，并允许它们缺失。行序无语义；同一 key 出现多次时按答案
合并，答案冲突必须报错。

## 2 查询行

必填：`config`、`name`、`types`、`mem`、`imms`。

```json
{"config":"C0","name":"G_IMPLICIT_DEF","types":["s1"],"mem":null,"imms":[],
 "kind":"equivalence","ruleset":"X_G_IMPLICIT_DEF","rule":0,
 "reason":"first match for rule 0"}
```

- `config`：非空字符串，必须能命中特性表的一行。
- `name`：opcode 文本，例如 `G_ADD`。
- `types`：LLT 文本数组，按 slot 顺序；拼写用 Core IR（`s32`、`i32`、`f16`、
  `v4s32`、`nxv4s32`、`p0:64`）。`p0:*` 是“宽度由 config 决定”的通配，
  只允许出现在查询里；答案侧要 join 必须写成同一具体宽度。
- `mem`：`null`，或 `[mty, align]`，或
  `[mty, align, ordering, failure_ordering]`。写方在
  `ordering == failure_ordering == "NotAtomic"` 时**可以**省略后两项；
  读方必须把缺省补成 `("NotAtomic", "NotAtomic")`。非 `NotAtomic` 必须写
  四元组。
- `imms`：整数数组；读方把缺失当作 `[]`，写方应显式写 `[]`。

## 3 答案行

在 key 的五个字段之外，二选一：

```json
{"config":"C0","name":"G_ADD","types":["s32"],"mem":null,"imms":[],
 "action":"Legal","type_idx":0,"new_type":"LLT_invalid"}
```

```json
{"config":"C0","name":"G_ADD","types":["s32"],"mem":null,"imms":[],
 "status":"unanswerable","reason":"..."}
```

- `action`：legalizer 动作名（`Legal`、`Lower`、`Libcall`、`Custom`、
  `Unsupported`、`WidenScalar`、`NarrowScalar`、`FewerElements`、
  `MoreElements`、`ClampScalar`、`ClampMaxNumElements`、`Scalarize`、
  `Unmerge` 等，以 `spec/semantics.md` 为准）。
- `type_idx`：被改写的 slot 下标；无改写时为 `0`。
- `new_type`：改写后的 LLT 文本；没有新类型时写哨兵 `"LLT_invalid"`，
  它不是 LLT，不能拿去解析成类型。
- `status: "unanswerable"`：双方都明确拒绝回答的查询；它不算答案差异，也不
  算通过。

答案文件必须原样回显 key 的五个字段（尤其是 `types` 的拼写）；
`eval --answers` 就是这样做的。外部 runner 若把 `p0:*` 解析成 `p0:64`，
必须同时改写查询文件，否则两侧 key 对不上，只能算 `uncovered`。

## 4 join 与去重

- 子集对拍（`gisel cases --against`）：只比较交集，报告
  `covered` / `agree` / `disagree` / `uncovered`；`uncovered` 不是通过。
- 全量对拍（`ab/diff.py`）：要求两侧 key 集合相等；一侧缺失即失败。
- key 的相等是**解析后的结构相等**，不是文本相等；但 `p0:*` 与 `p0:64`
  不相等（通配不是具体宽度）。
- 重复 key：答案相同 → 合并；答案不同 → 报错，不允许静默取第一条。

## 5 标准化到什么程度

**要标准化：**

1. 五个 key 字段的名字、类型和缺省；
2. LLT 的 Core IR 拼写；
3. `mem` 的两/四元组归一规则；
4. 答案三元组 `(action, type_idx, new_type)` 与 `unanswerable` 状态；
5. `LLT_invalid` 哨兵。

**不标准化：**

1. 不要求三种文件合成一个 schema：标注字段只属于 cases；
2. 不要求行序、缩进、字段顺序；
3. 不规定外部 runner 怎么生成答案，只规定它写出来的行。

**尚未覆盖（明写，不冒充）：**

- 没有 `format` 版本字段。三种文件目前靠字段集合区分；将来加
  `"format": "gisel.cases/1"` 需要同时决定旧文件是否必须接受缺失。
- `p0:*` 没有按 config 自动解析。`cases` 保留通配，`domain` 使用单一
  `--pointer-width`；两者对 32/64 位混合 config 都不完整，指针点目前大量
  落在 `uncovered`。
- `mem` 的答案侧 join 历史上只看二元组；本轮已把读入口统一到
  `gisel/answers.py` 的归一化，但没有重跑带 mem 的全量 A/B。

## 6 最小校验

读入一行后至少检查：

```text
config 是字符串且非空
name 是字符串且非空
types 是字符串数组
mem 是 null 或长度 2/4 的数组，mty 可解析，align 是整数
imms 是整数数组（缺省 []）
答案行恰有 answered 三元组或 unanswerable 状态之一
```

不满足即报错并带文件名/行号；不要跳过坏行继续，否则 join 会把“没读进来”
伪装成“没差异”。
