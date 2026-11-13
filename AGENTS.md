# gisel 协作规则

本文件是仓库内的执行面。与 `docs/SCOPE.md`、`spec/escape-points.md` 一起读；
三者冲突时，以更严格的审批要求为准。

## 0 最高优先级：扩语法必须经用户批准

**任何改变 `.gisel` 写法或分析承诺的改动，必须先取得用户（项目负责人）的
明确批准。未获批准不得实施，不得以“顺手”“为了导入某个 target”为理由绕过。**

需要批准的范围：

- 文法：`spec/grammar.md`、`gisel/dsl.py` 的词法、原语表、规则形态；
- 语义节点：`gisel/eval.py` 的值节点与谓词节点集合；
- 产物映射：`gen --emit={inc,check,core}` 三个后端对应的节点；
- 宿主逃逸口：`feature`、`opaque`，以及未来任何变异侧宿主表达式；
- `escapes` 字段的语义、去重规则、计数口径；
- `spec/escape-points.md` 里的契约本身。

流程固定为三步：

1. 写 `docs/PROPOSAL-*.md`：新写法、各出口语义、对现有语料/冻结产物的影响、
   验证计划、被拒绝的替代方案；
2. **停下**，等用户明确说“批准/可以/按这个做”；
3. 只实现被批准的部分，不扩大范围。

判断标准只有一句：**`.gisel` 的写法或分析承诺变了没有。** 变了就是语法/契约
变更；拿不准时按“是”处理，停下来问。用户批准一次只覆盖那一次提案，不构成
对同类改动的长期授权。

## 1 不需要批准、可以自动推进

- `tools/import-cxx.py` 对新 C++ 形态的识别（产物仍是同一套 `.gisel` 写法）；
- 测试、文档、数据表、CLI 参数（不改变语言契约）；
- 不改变节点集合的重构、性能优化、错误信息改进；
- 让实现重新符合既有规范的一致性修复（例如 `escapes` 计数必须等于实际
  `opaque` 条数）。

遇到需要扩语法才能导入的 target：停在 `deviation_*` 或“已声明、未转写”，
记录到报告/issue，**不要扩语法**。AMDGPU 已决定跳过，不要重新捡回。

## 2 逃逸点纪律

- 只承认两个口：`feature`（配置轴）和 `opaque`（谓词洞）。没有第三个。
- `feature` 是构造函数期 Bool，只能读 `ST`/`STI`/`TM`/`Subtarget`/`XLen`、
  已声明 feature 名和命名空间常量；**不得读** `Query`/`MMODescr`/`MMO`/
  `MI`/`MRI`/`MF`。
- `opaque` 只能出现在谓词位置，不是配置轴，不参与等价类划分，不被求值。
- 不得把宿主表达式塞进类型、变异或配置轴来“先跑通再说”。
- `--emit=core` 的 `escapes` 数组、`--emit=check` 的 `escapes` 计数、
  `ast.host_escapes()` 三者必须相等。审计命令见 `spec/escape-points.md` §6。

## 3 验证门禁

提交前至少跑：

```bash
python3 -m pytest -q
python3 ../gisel-anchor/scripts/import-cxx.py --all \
  --pin ../gisel-anchor/pin/PIN.json \
  --git-repo /home/ubuntu/llvm/llvm-project --check   # 必须 9/9
```

改动涉及 `feature`、`opaque` 或 `escapes` 时，额外跑
`spec/escape-points.md` §6 的审计命令。不得手改 `tests/artifacts/` 来让测试
通过；冻结产物只能由 `tools/refresh-oracle.sh` 按已批准的变更刷新。

## 4 提交与边界

- 一笔提交一个主题，信息用小写祈使前缀：`gisel:`、`import-cxx:`、`cases:`、
  `eval:`、`docs:`。
- gisel 本体只有两个功能：规则转译、用例生成。对拍、双 runner、归因属于
  工作台，界线见 `docs/SCOPE.md`；不要把工作台能力写进产品 CLI 或产品报告。
- 不复活 `.td` 后端，不动已冻结语料，除非该次变更已获批准。
