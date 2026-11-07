# `gisel graph` 实现报告

## 已交付

新增命令：

```sh
python3 -m gisel graph SOURCE --emit=core \
  [--features FEATURES] [--config CONFIG] [--json] \
  [--inject-edge] [--check-closure] [--oracle ORACLE]
```

实现位于 `gisel/graph.py`，CLI 注册在 `gisel/cli.py`。`gisel/eval.py` 增加了
`evaluate_with_rule`，保留现有 `evaluate()` 签名和返回值。规范见
`spec/graph.md`，设计记录见 `docs/DESIGN-graph.md`。

图直接从 `.gisel` 生成 schema 0.4 core 文档，再交给现有 evaluator；没有读取
原型的 `x86.tables.json`，没有生成 MIR，也没有调用 `llc`、TableGen 或 LLVM。

## 验证

### 无环和注入边负控

临时夹具包含一个 `G_ADD` 终结状态和一条加宽边。命令及输出文件 SHA：

```sh
python3 -m gisel graph /tmp/gisel-followup/graph-fixture.gisel \
  --config none --json > /tmp/gisel-followup/fixture-normal.json
# rc=0
# sha256: 13967680aedaaa0c0d0b05c132fbe018c99bb895372426ae34469c674f6487a2
# states=2 edges=1 cycles=0

python3 -m gisel graph /tmp/gisel-followup/graph-fixture.gisel \
  --config none --inject-edge --json > /tmp/gisel-followup/fixture-inject.json
# rc=1
# sha256: d0a7cf663b6519cbb9b27b3fc7e3036370984017e9648b2a23aa2c0dc3e09443
# states=2 edges=2 cycles=1
# injected edge: G_ADD[1] -> G_ADD[0]
```

### X86 四配置

命令：

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --json \
  > /tmp/gisel-followup/x86-all-final.json
```

该命令因为完整 X86 语料确实包含自然环而返回 `rc=1`。输出 SHA-256：

```text
510e6af74469818e9fad0624cde486739bb993de029991617a9a7a5889ea28e8
```

四个配置的真实结果如下。`outcomes` 的五类是 moves、no-rule、opaque、outside、
terminal；`terminal` 是终结动作分布。`uncovered` 始终是两个 variadic opcode，
因为 bundled opcode manifest 没有固定槽数：`G_INTRINSIC`、
`G_INTRINSIC_W_SIDE_EFFECTS`。

| config | states | edges | moves | no-rule | opaque | outside | terminal | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C0 | 72,956 | 26,085 | 26,085 | 25,579 | 964 | 4,160 | 16,168 | 6 |
| C1 | 72,956 | 25,213 | 25,213 | 26,396 | 980 | 3,158 | 17,209 | 6 |
| C2 | 72,909 | 24,782 | 24,782 | 26,449 | 980 | 3,166 | 17,532 | 6 |
| C3 | 72,956 | 25,957 | 25,957 | 25,574 | 964 | 3,992 | 16,469 | 6 |

完整语料的 6 个自然环样例集中在 `G_INTRINSIC_ROUNDEVEN`、
`G_INTRINSIC_TRUNC`、`G_SMAX`、`G_SMIN`、`G_UMAX` 等状态；这说明图命令确实
会报告环，而不是以超时模拟检查。专门的 G_ADD 无环夹具验证了“正常路径 rc=0，
注入边 rc=1”的负控契约。

### Oracle 对拍

X86 C1 的完整 oracle 对拍命令：

```sh
python3 -m gisel graph tests/corpus/X86LegalizerInfo.gisel \
  --features tests/cases/x86-features.json --config C1 \
  --oracle tests/cases/x86_ref_dump.jsonl --json \
  > /tmp/gisel-followup/x86-oracle.json
```

结果：`total=1408 matched=1408 agree=1408 disagree=0 errors=0 uncovered=0`，
命令返回 `rc=0`。图定位状态后仍使用同一个 `eval.Evaluator` 比较 action、
type index 和 new type，没有另写一套规则语义。

## 闭包和 outside

`--check-closure` 会枚举状态保存的全部成员，检查代表点的 winning rule、
mutation 和目标类是否对整个类一致。它不会自动细化分区。一个临时夹具把
非 2 次幂向量通过 `more(..., pow2)` 推到未声明的 lane，报告：

```text
outside=1
closure.ok=false
reason=outside
```

因此域外不再被静默 continue；它单独计入 `outside`，闭包检查也会把它作为反例。

## 与 `sim/graph.py` 的差异

- 输入从原型私有 `x86.tables.json` 改为 `.gisel -> core schema 0.4 -> eval`。
- outside 是图报告字段，并且参与闭包失败判断；原型只在 runtime fallback 路径中
  累计。
- 闭包检查位于图构建之后，对商类的全部成员审计；默认不细化分区。
- opaque、no-rule、outside、stuck 分开统计；原型的 table cell 状态更接近
  `unknown/none/outside`。
- `--inject-edge` 是命令行负控，不需要读者写 Python 片段。

## 未覆盖和限制

- variadic opcode 没有固定类型槽数，当前明确列在 `uncovered`，没有拿零槽图冒充
  完整覆盖。
- memory 轴使用 ruleset 中 `in_mem_desc` 的有限 rows；没有显式内存描述的任意
  ordering/descriptor 域不会被凭空枚举。
- `--refine` 尚未实现，默认分区不会被自动修改。
- 完整 X86 语料的自然环是当前 DSL 规则图的真实结果；本实现不会把它们删掉来
  强行得到 `cycles=0`。无环验收使用独立的 G_ADD 夹具。

