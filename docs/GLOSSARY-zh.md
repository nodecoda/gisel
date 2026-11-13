# 术语表

| 词 | 一句话 | 不要和什么混 |
|---|---|---|
| **ruleset** | `.gisel` 里绑定一个 opcode 的规则块 | 不是一张表；生成后才成为 C++ 规则链 |
| **corpus** | 从一个 pinned C++ 文件转写出来的 `.gisel` 语料 | 不是测试用例；它是出题的输入 |
| **pin** | 上游 commit + 每个源文件 sha256 的冻结记录 | 不是分支名；工作区改动不影响它 |
| **inc** | `gisel gen --emit=inc` 生成的 C++ 片段 | 不是完整 legalizer；被 include 进构造函数 |
| **core** | `--emit=core` 的 schema 0.4 正常形 JSON | 不是答案；`eval`/`graph` 读它 |
| **G 题面** | `gisel cases`：规则感知的等价类 + 边界 + outside | 不是 `domain`；两者互不包含 |
| **D 题面** | `gisel domain`：规则无关的声明值域全量 | 包含非法组合，不是「合法值域」 |
| **U 题面** | `gisel-anchor` 从上游规则表生成的题面 | 方向相反：证明上游规则 gisel 没漏 |
| **U-full** | U 按全部配置展开 | 不是采样；规模更大，用于全量门 |
| **等价类 / 商** | 谓词取值向量相同的查询归为一类，规则答案在类内不变 | 不是随机分组；划分由原子谓词决定 |
| **切点** | 谓词真值发生翻转的阈值 `N`（含 `N±1`） | 不是所有边界；类型自身边界另算 |
| **outside** | 没有规则命中的补集，或变异把类型推出已声明域 | 不是 no-rule；后者是 eval 返回 Unsupported |
| **opaque** | 谓词内部逃逸到 C++，三值为 None 的洞 | 不是 False；表拒绝为它建格 |
| **L0** | `getAction` 单点答案对拍 | 不是整条 legalize 轨迹 |
| **L1** | 上游 `.mir` 回放 `-run-pass=legalizer` | 不是 L0；覆盖多步/自定义动作 |
| **L2** | 由无答案查询合成 MIR 再回放 | 不是 L1；题面由我们生成 |
| **L3** | 两轮全量 `check-llvm`，逐条比 lit 结果 | 不是总量比较；测试增删也算差异 |
| **cohort** | 一次冻结：三仓 commit + 语料/证据指纹 + tag | 不是日期；`rN` 是发布单元 |
| **frozen evidence** | cohort Release 里的 `evidence-*.tar.gz` | 不是源码；校验 sha 后离线复核 |
| **adopt** | 把上游官方基线纳入我们的证据链 | 不是覆盖；旧基线仍可复核 |
| **escape point** | `feature("...")` 的宿主谓词字符串 | 不是漏洞；按配置轴枚举，内部不参与规则推理 |
