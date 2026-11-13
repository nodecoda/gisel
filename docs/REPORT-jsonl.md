# JSONL 边界审计（W3.4a）

日期：2026-11-13。对象：`gisel.jsonl` 公共面与 `gisel` 内部四个 JSONL 读者。

## 1 结论

1. 规则不是待选方案，已经写在 `spec/cases-format.md`：
   - `:84` 重复 key：答案相同 → 合并；答案不同 → 报错，不允许静默取第一条。
   - `:125` 字段不满足即报错并带文件名/行号；不要跳过坏行继续。
2. 代码没有全部做到：
   - `gisel/cases.py:872` `index_oracle` 用 `setdefault` 静默保留第一条；
   - `gisel/graph.py:947` `oracle_check` 直接 `json.loads`，坏行没有 `file:line`；
   - `gisel/eval.py:920` `prepare_query` 直接取 `q["types"]`/`q["mem"]`，缺字段抛 `KeyError`；
   - 只有 `gisel/answers.py:36` `load` 实现了规范（同答案跳过、异答案报错），但它返回
     “部分字典 + errors”，调用方仍可能忽略 errors。
3. 现有数据不需要迁移：4 个答案缓存共 17,264 行，0 坏行、0 重复、0 冲突。
   所以 W3.4 是“代码追上规范”，不是“改数据/改契约”。

## 2 人口普查

命令：

```bash
python3 tools/jsonl-census.py /home/ubuntu/llvm/gisel-ab/.ab/*/cache/official/*.jsonl
```

| target | 行数 | 坏行 | 重复 | 冲突 |
|---|---:|---:|---:|---:|
| aarch64 | 12,559 | 0 | 0 | 0 |
| x86 | 3,014 | 0 | 0 | 0 |
| mips | 1,656 | 0 | 0 | 0 |
| m68k | 35 | 0 | 0 | 0 |
| 合计 | 17,264 | 0 | 0 | 0 |

说明：`.ab/**/cache/official/*.jsonl` 是 `gisel-ab` 工作台的本机缓存，不进任何仓库；
它是当前能拿到的最大真实答案集，但不是冻结发布物。普查工具只读，不改文件。

## 3 策略（W3.4b/c 要实现的）

- 文件边界：`read_rows(path, strict=True)` 返回 `(rows, errors)`；strict 下坏行立即
  抛 `JsonlError(file, line, msg)`，不返回半条。
- 行边界：`parse_query/parse_answer` 校验五个 key 字段与答案三元组；
  `eval.prepare_query` 只走行边界，不新增 IO。
- 重复键：同答案合并（幂等重跑）；异答案硬错误，带 `file:line` 和两个答案。
- 公共面：`answer/key/load/llt_text` 保留兼容导出；`llt_text` 标 deprecated，
  等 oracle 有本地实现后再删（W3.6）。
- 不给 `--allow-duplicate` / `--skip-bad` 这类让门变绿的开关。

## 4 不在本轮范围

- 不改 JSONL 的字段名、LLT 拼写或 key 归一规则（`spec/cases-format.md` 仍是 SSOT）。
- 不引入 gzip/CSV/Parquet。
- 不改变 `.ab` 缓存的存放位置或命名。
