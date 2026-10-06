# Core MVP 自动执行日志

日期：2026-10-03。授权：用户要求“自动执行并推进计划”。产品边界以
[Core 计划](01_core_plan.md)为准，契约以 [Stage 1 包](../contracts/README.md)为输入。

## 当前执行范围

2026-10-06 用户要求检查并完成图片中的下一步：继续 PR #5 的 Stage 3，不重复开发。
远端 main 已包含契约 PR #2、数据库 PR #3 与修复 PR #6，SHA 为 `58aac36`。
本次已整合该 main，并新增数据库升级后既有会话/咨询权限的回归测试；同步 PR #5
base 已改为 main，新基线
[CI](https://github.com/Mark-UM/FDE-test/actions/runs/37450116062) 四项全部通过
（实现/测试提交 `cf421fd`）。Stage 3 仍待人工 Review/合并，不开始 Stage 4。

本地结果：91 项真实 PostgreSQL（57 数据库 + 34 API/事务），116 项后端回归（含
13 独立 Sandbox HTTP）全部通过；Ruff、前端 lint/type/build、Compose config 通过。
实际启动 Product Uvicorn + 隔离 PostgreSQL 17.11，五类账号范围 10/1/1/11/0，
详情、403/401、CONTEXT_REQUIRED 与退出撤销通过，重复 Seed 成功。
完整证据见 [Stage 3 main 整合验证](../verification/2026-10-06-stage-3-main-integration.md)。

## 2026-10-03 至 2026-10-04 执行历史

2026-10-04 用户明确授权“继续我的下一阶段”：新增 Stage 3 依赖候选
`codex/core-auth-inquiries` → `codex/core-database`，只交付后端身份会话与咨询读取。
不将第二阶段 PR 未合并误写为已在 main，不自动合并；Stage 4+ 未授权。

1. 检查/提交 Stage 1 文档，创建 `docs/core-mvp-contracts` → main 的审查 PR。
2. Stage 2 数据库候选：SQLAlchemy 2、Alembic、Product PostgreSQL schema、幂等虚构 Seed，
   真 PostgreSQL CI 测试。分支 `codex/core-database` 依赖契约 PR。
3. Stage 2 工作台候选：静态虚构数据，咨询列表/详情、逐包裹证据与质量、草稿审核布局，
   Loading/Empty/Error 展示。分支 `codex/core-workbench-shell` 依赖契约 PR。

本次授权允许先准备依赖契约的候选实现；不假称两名开发者已 Review，不自动合并 main。
Stage 3 的认证/业务 API、Stage 4 Evidence 计算、Stage 5 AI/Validation/批准行为不混入 Stage 2。
两条 Stage 2 PR 合并目标先为契约分支，契约合并后须 rebase main、改 PR base 并重跑 CI。

## 历史基线与验证环境

- origin/main 仍为 `33857e2`；远端已 fetch，无新业务提交；GitHub CLI 登录有效。
- 本机无 Docker、PostgreSQL executable/service；localhost:5432 无连接。
- 数据库验收在独立 CI PostgreSQL 服务执行，不以 SQLite/mock 或跳过结果替代。
- Stage 1 文档检查先运行；发现 AGENTS 中重复的 Stage 1 段落已去重。

## 历史状态（后续合并及本机环境变化见上方更新）

| 交付 | 状态 | 证据 |
| --- | --- | --- |
| Stage 1 契约 PR | [PR #2](https://github.com/Mark-UM/FDE-test/pull/2) 已提交，CI 通过 | `cc2f262`；六份契约、完整 fixture、文档验证记录 |
| Stage 2 数据库/Seed | [Draft PR #3](https://github.com/Mark-UM/FDE-test/pull/3)，CI 全通过 | `eeb9aca`；12 表、迁移/Seed、26 项真实 PostgreSQL 测试；[CI](https://github.com/Mark-UM/FDE-test/actions/runs/37109759410) |
| Stage 2 静态工作台 | [Draft PR #4](https://github.com/Mark-UM/FDE-test/pull/4)，CI 通过 | `d033d95`；13 项 Edge 与 Chromium 测试均通过；[最终 CI](https://github.com/Mark-UM/FDE-test/actions/runs/37129301879) |
| Stage 3 身份授权 / 咨询 API | [Draft PR #5](https://github.com/Mark-UM/FDE-test/pull/5)，CI 全通过，待 Review | `7c91dc7`；116 本地测试（含 13 真实 HTTP）+ 59 真 PG（含新增 33 项 API/事务）通过；[CI](https://github.com/Mark-UM/FDE-test/actions/runs/37178404364) |
| 人工 Review / main 合并 | 未完成 | 不由自动化代签 |
| main 保护 / 容器运行 | 未完成 | 不安装系统服务或修改仓库治理设置 |

每项完成后更新此日志与其验证记录。已提交历史验证文件保留原任务的观察范围。

## 当时的下一步与阶段出口

数据库候选本地 66 个单元 + 13 个真实 Sandbox HTTP 测试通过；26 个数据库测试在 CI
PostgreSQL 17 服务运行并全部通过。本机无 PostgreSQL，不将离线 SQL 生成视为数据库验收。
工作台候选只有本地预览行为；不取数、不产生 Evidence、不执行 Validation/批准/发送。
两条候选均依赖 Stage 1，审查和合并后才作为稳定基线。后续用户已单独授权 Stage 3
依赖候选；它继续保留人工 Review/合并出口，停止在身份与咨询 API，不开始 Stage 4。

第三阶段技术出口已通过，最新实现/验收见
[Stage 3 记录](../verification/2026-10-04-stage-3-access-validation.md)。下次若授权 Stage 4，
应先核对依赖审查/合并基线，再实现手动 resolve 的幂等 Run、Provider 来源记录、不可变
Evidence/Context、来源质量与失败归档，以及只读取当前 Context 的 order 入口。
必须真实 HTTP + FixedClock，保持权限在取数之前及提交前检查；不混入 AI、批准、发送、
重试或缓存。Stage 3 不调用 Provider，不能替代这些第四阶段验收。
