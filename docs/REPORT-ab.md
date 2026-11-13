# 工作台报告：已迁移到 `gisel-ab` 项目

对拍工作台（双 runner 构建、跑查询、diff、归因）已从 gisel 拆到独立项目
`gisel-ab`。这份报告连同它的历史数字一起迁走了：

- 新位置：`/home/ubuntu/llvm/gisel-ab/docs/REPORT-ab.md`（独立仓库 `nodecoda/gisel-ab`，public）
- 需求：`/home/ubuntu/llvm/gisel-ab/docs/REQUIREMENTS-ab.md`
- 契约：`/home/ubuntu/llvm/gisel-ab/CONTRACTS.md`
- 语料转录工具：`/home/ubuntu/llvm/gisel-anchor`（独立仓库
  `nodecoda/gisel-anchor`，public）

本文件只保留指针，避免旧链接 404。gisel 的边界见 `docs/SCOPE.md` §7：
对拍是**用 gisel 做的事**，不是 gisel 的功能。
