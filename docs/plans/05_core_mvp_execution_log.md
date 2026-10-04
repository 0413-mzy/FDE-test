# Core MVP 自动执行日志

日期：2026-10-03。授权：用户要求“自动执行并推进计划”。产品边界以
[Core 计划](01_core_plan.md)为准，契约以 [Stage 1 包](../contracts/README.md)为输入。

## 当前执行范围

1. 检查/提交 Stage 1 文档，创建 `docs/core-mvp-contracts` → main 的审查 PR。
2. Stage 2 数据库候选：SQLAlchemy 2、Alembic、Product PostgreSQL schema、幂等虚构 Seed，
   真 PostgreSQL CI 测试。分支 `codex/core-database` 依赖契约 PR。
3. Stage 2 工作台候选：静态虚构数据，咨询列表/详情、逐包裹证据与质量、草稿审核布局，
   Loading/Empty/Error 展示。分支 `codex/core-workbench-shell` 依赖契约 PR。

本次授权允许先准备依赖契约的候选实现；不假称两名开发者已 Review，不自动合并 main。
Stage 3 的认证/业务 API、Stage 4 Evidence 计算、Stage 5 AI/Validation/批准行为不混入 Stage 2。
两条 Stage 2 PR 合并目标先为契约分支，契约合并后须 rebase main、改 PR base 并重跑 CI。

## 基线与验证环境

- origin/main 仍为 `33857e2`；远端已 fetch，无新业务提交；GitHub CLI 登录有效。
- 本机无 Docker、PostgreSQL executable/service；localhost:5432 无连接。
- 数据库验收在独立 CI PostgreSQL 服务执行，不以 SQLite/mock 或跳过结果替代。
- Stage 1 文档检查先运行；发现 AGENTS 中重复的 Stage 1 段落已去重。

## 状态

| 交付 | 状态 | 证据 |
| --- | --- | --- |
| Stage 1 契约 PR | [PR #2](https://github.com/Mark-UM/FDE-test/pull/2) 已提交，CI 通过 | `cc2f262`；六份契约、完整 fixture、文档验证记录 |
| Stage 2 数据库/Seed | [Draft PR #3](https://github.com/Mark-UM/FDE-test/pull/3)，CI 全通过 | `eeb9aca`；12 表、迁移/Seed、26 项真实 PostgreSQL 测试；[CI](https://github.com/Mark-UM/FDE-test/actions/runs/37109759410) |
| Stage 2 静态工作台 | [Draft PR #4](https://github.com/Mark-UM/FDE-test/pull/4) 已提交 | `745089a`；六个虚构场景；lint/type/build 与 13 项 Edge 浏览器测试通过；Chromium CI 待执行 |
| 人工 Review / main 合并 | 未完成 | 不由自动化代签 |
| main 保护 / 容器运行 | 未完成 | 不安装系统服务或修改仓库治理设置 |

每项完成后更新此日志与其验证记录。已提交历史验证文件保留原任务的观察范围。

## 下一步与阶段出口

数据库候选本地 66 个单元 + 13 个真实 Sandbox HTTP 测试通过；26 个数据库测试在 CI
PostgreSQL 17 服务运行并全部通过。本机无 PostgreSQL，不将离线 SQL 生成视为数据库验收。
工作台候选只有本地预览行为；不取数、不产生 Evidence、不执行 Validation/批准/发送。
两条候选均依赖 Stage 1，审查和合并后才作为 Stage 3 基线。Stage 3 将实现身份/咨询 API，
本次停止在 Stage 2 可审查交付；不自动越过 Review 进入业务 API 编码。
