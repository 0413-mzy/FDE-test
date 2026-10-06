# Stage 3 与已合并数据库基线整合验证

日期：2026-10-06（Asia/Shanghai）。分支 `codex/core-auth-inquiries`，继续
[Draft PR #5](https://github.com/Mark-UM/FDE-test/pull/5)。用户要求完成图片中的下一步，
范围为数据库接入后端、登录会话、权限检查和咨询 API，不包含 Stage 4 或 main 合并。

## 完成项

- 核对远端：契约 PR #2、数据库 PR #3 与修复 PR #6 已合并；main 为
  `58aac3645f9d831ebd6df30a78b849761de4a3ff`。
- Stage 3 的六个 API 原已实现，旧 head `4da63d4` 的 CI 已通过；本次复用现有实现。
- 普通 merge 整合最新 main，提交 `1f54a6c`；没有冲突，不改写现有提交历史。
  包含增量迁移 `0002_nonblank_constraints`，原 `0001` 不变。
- 新增真实 PG 回归：在隔离 schema 的 0001 上登录，升级至 0002 后确认 session ID、
  token 摘要、过期时间不变，列表归属正确，自己的详情可读，同团队他人/跨团队均 403，
  order 返回 CONTEXT_REQUIRED，退出后 401，且仍能重新登录。
- 同步 README、契约状态、架构/范围、Core 计划和执行日志；旧验证记录保留历史观察。
- PR #5 改以 main 为 base，仍保留 Draft 与人工 Review 出口；远端检查见下方记录。

## 本地验证

Python 3.13.13；Docker Engine 29.8.1 / Compose 5.5.1；实际 PostgreSQL **17.11**。
独立容器 `fde-stage3-validation-20261006` 只绑定 `127.0.0.1:55438`，无共享卷，
测试与业务演示只使用本轮新建的虚构数据。测试结束后删除该临时容器。

| 检查 | 命令 / 方式 | 结果 |
| --- | --- | --- |
| 后端 lint | `python -m ruff check --no-cache .` | 通过 |
| 后端格式 | `python -m ruff format --check --no-cache .` | 38 文件通过 |
| 数据库 / API | 设置 TEST_DATABASE_URL 后 `python -m pytest tests/database -q -p no:cacheprovider` | **91 passed**，119.24s，无 skips |
| 后端完整非 DB 回归 | `python -m pytest -m "not database" --sandbox-url http://127.0.0.1:19004 -q -p no:cacheprovider` | **116 passed**，91 deselected，无 skips |
| 前端 | `npm run lint`、`npm run typecheck`、`npm run build` | 全通过；28 modules |
| Compose 配置 | `docker compose --env-file .env.example config --quiet` | 通过 |
| 真实 Product HTTP | Uvicorn + Product 数据库；HTTPX 通过真实 socket 访问 | 登录、权限、详情、order 前置条件、退出通过 |
| 重复 Seed | 隔离数据库上连续执行两次 `python -m app.db.seed` | 成功；不重置流程/密码 |

91 个 PG 测试 = main 的 57 个持久化/迁移测试 + Stage 3 的 34 个 API/事务测试。
覆盖未登录、精确八小时过期边界、撤销、当前 active/role/team 变化、权限分页、统一 403、
Audit 失败回滚及两条独立连接的锁竞争。Stage 3 测试监测六个 Provider 方法，调用数为零。
116 个非 DB 回归中含 **13 个独立 Sandbox 真实 HTTP** 测试，使用既有 FixedClock；
独立 Sandbox 版本 `4131f1c4be7af6a6981e15379214d238228e8fa2`，临时 SQLite 路径，
没有编辑其源码或读取其数据库。它们验证既有 Provider 边界，不等同于 Stage 4 取数验收。

实际 Product 服务的五类账号咨询数量为：agent.a 10、agent.b 1、agent.c 1、
supervisor 11、admin 0。验证自身详情 200、其他客服/跨团队/未知 ID 403、未登录 401、
退出后 me/list 401；有绑定的 order 入口为 409 CONTEXT_REQUIRED，不获取外部事实。
登录使用内存中随机生成的演示密码；报告和普通日志不记录密码/token。

最初 Ruff 与 Vite 缓存遇到本地写权限限制，分别以禁用缓存及正常本地权限重跑通过。
临时 HTTP 服务的首次清理遇到 Windows 文件占用，改为停止完整进程树后重跑通过。
最终后端仅有两项 Starlette/httpx/anyio 依赖弃用警告，没有测试失败或跳过。

## 远端与阶段出口

本次 PR base 为 main；新 head 的 backend、database、frontend、compose 四项 CI
执行结果在提交后补充核验。旧 head 的成功不能替代新基线验证。

待完成：Stage 3 人工 Review/合并、PR #4 静态工作台、main 保护与完整 Compose
build/start 部署验收。本次只启动 PostgreSQL 容器与主机上的 Product/Sandbox 服务，
不声称完整应用容器已联启。HTTPS/登录防暴破部署评审仍在历史待办中。
Evidence/CaseContext、AI、草稿/审核/发送、前端登录与真实外部订单查询均未进入本次实现。
