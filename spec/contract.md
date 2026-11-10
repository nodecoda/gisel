# 形状契约：哪些类型元组不是问题

状态：2026-11-11。数据在 `gisel/data/contract-shapes.jsonc`，解释器在
`gisel/contract.py`，消费者是 `analysis.type_shape_ok`。

## 1 契约过滤的是问题，不是答案

一条查询是 `(opcode, types, mem, imms)`。不是每个类型元组都能从 IR 走到
legalizer：`G_CONCAT_VECTORS` 的目标必须是向量、移位的两侧必须同为标量或
同为向量、`G_MERGE_VALUES` 只合并标量。问这些元组，得到的答案没有对应的
`llc` 输入；有时上游还会在返回动作前断言。

`type_shape_ok` 只回答“这个元组能不能成为问题”。它从不决定一条合法查询的
答案——那是 `eval`/`inc` 的事。这两件事混在一起，就会把“上游算错了”误判成
“这个问题不该问”。

## 2 表的形状

```jsonc
{
  "schema": "gisel-contract/1",
  "rules": [
    {"opcode": "G_CONCAT_VECTORS", "min_slots": 2,
     "checks": [{"slot": 0, "kind": "vector"},
                {"slot": 1, "kind": "vector"},
                {"relation": "dest_lanes_double", "slots": [0, 1]},
                {"relation": "same_element", "slots": [0, 1]}],
     "source": "MachineVerifier.cpp:1602-1619"}
  ]
}
```

- 一个 opcode 一条规则；重复即加载失败。
- `checks` 全部成立才留在契约内；`any_of` 表示“任一支成立”（`G_UNMERGE_VALUES`
  的标量形与向量形）。
- `short_ok: true` 表示槽数少于 `min_slots` 时视为在契约内（移位的单槽查询
  不会走到 verifier 的检查）。
- **`source` 必填**。没有出处的形状断言是猜测，加载时直接 `ValueError`。
  出处要么是 `MachineVerifier.cpp:NNNN`，要么显式写 `semantics: ...`（verifier
  没有该 opcode 的分支）。
- 加载做 schema、kind、relation 的白名单校验；不认识的名字直接失败，不静默
  忽略。

## 3 实测：`unanswerable` 的主体不是“上游 bug”，是域卫生

AArch64 baseline（2026-11-11，`ab/docs/EVIDENCE-domain.md`）：

```text
双端断言 39,056
  38,416  G_EXTRACT_VECTOR_ELT，三个槽全是标量   LowLevelType.h:511
     322  G_CTPOP/CTLZ/CTTZ/CTLS/移位，浮点/指针  LowLevelType.h:151
     234  同上，mutation 对指针 changeElementSize  LowLevelType.h:429
      52  G_FPTOSI/FPTOUI，规则产生不合法 mutation  LegalizerInfo.cpp:200
      32  G_FPTOSI/FPTOUI，两侧崩在不同处（见 §4）  fatal / LegalizerInfo.cpp:200
```

`G_EXTRACT_VECTOR_ELT` 的 verifier 规则是“源必须是向量”
（`MachineVerifier.cpp:2020`），表里没有这一条，所以 24³ 个标量三元组全被
当成问题问了，全部在 `getElementType()` 上断言。**它们占 98.3%。**

这不是 39k 个上游缺陷，而是一条缺失的形状规则。把它加进表会让每个配置的
题面少 38,416 条、`unanswerable` 从 39,056 降到 640。这会改变所有已冻结的
分母，所以本轮**只测量、不改表**：先让数字可解释，再决定要不要收窄域。

剩下的 640 条才是契约层面的真问题：verifier 不拒绝这些形状（或不检查这些
opcode），规则却在上游断言。它们是下一轮 upstream issue 的候选，不是 gisel
的翻译错误——两侧字节一致。

## 4 已知分歧：同一个“不可答”，崩在不同处

32 条 `G_FPTOSI`/`G_FPTOUI`（可伸缩向量目标）官方和我方都不可答，但：

```text
official  LLVM ERROR: cannot implicitly convert a scalable size to a
          fixed-width size in TypeSize::operator ScalarTy()   (report_fatal_error)
ours      assert(mutationIsSane(...)) at LegalizerInfo.cpp:200
```

原因在生成代码的谓词：上游写 `Query.Types[0].getSizeInBits() > 64`，`TypeSize`
与整数比较时走隐式 `ScalarTy()`，可伸缩类型直接 fatal；我们的 `bits_of()`
落到 `getKnownMinValue() > 64`，于是继续走到 `narrowScalarIf` 并触发
`mutationIsSane`。

两边都没有给出动作，所以不影响 `disagree=0`；但它说明“同为不可答”不等于
“同一条路径”。`ab/diff.py --assert-sites` 把两者分开计数（`same` /
`mismatch` / `missing`），不把 `mismatch` 算进 `disagree`。改谓词语义要动
`.gisel` 语义和生成器，按治理规则先报批。

## 5 已知窄处（保留行为，显式记录）

`G_UNMERGE_VALUES` 的条目复刻的是现行过滤器，不是 verifier 原文：向量源 +
标量目标的常见形式（`v2s32 -> s32, s32`）今天会被丢掉
（`REPORT-coverage §9.5`）。表里用 `source: "legacy: ..."` 标出。放宽它会
给每个域新增问题，属于同一类分母决策。

## 6 不做

- 不用这张表预测 `unanswerable`。实测表明只有“源必须向量”这一类形状能
  干净预测崩溃；其余断言取决于规则命中顺序和 mutation 细节，形状层预测
  必然要么漏、要么误伤。`unanswerable` 只能测，不能推。
- 不把表当成答案的一部分：表变了只改变“问什么”，不改变“答什么”。
