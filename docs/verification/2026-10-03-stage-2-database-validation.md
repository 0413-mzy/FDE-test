# Stage 2 数据库候选验证

依赖 [契约 PR #2](https://github.com/Mark-UM/FDE-test/pull/2)。本分支实现 Product schema，
不是身份/API/Evidence/AI/批准行为。详情见 [执行日志](../plans/05_core_mvp_execution_log.md)。

- 新增 SQLAlchemy 12 个工作流表、冻结初始 Alembic migration、显式 Seed CLI。
- PostgreSQL 约束区分空数组与失败，维持版本/幂等唯一性与外键；6 个历史表有 append-only trigger。
- UTC 绑定拒绝 naive/non-UTC；JSON 保留 canonical 原值/源时间；Seed 不重置已有工作流和密码。
- 普通日志隐藏 SQL 参数；密码从临时配置读取，只保存 Argon2id 哈希；production Seed 拒绝。
- models/迁移不会被 `/health` 连接或使用。跨行授权和 Context/Validation 前置条件留给后续服务。

本地：`ruff check --no-cache .` 通过；29 个 Python 文件格式检查通过；
`pytest -m "not integration and not database" -q -p no:cacheprovider` 为 66 passed。
`alembic upgrade head --sql` 可生成 PostgreSQL DDL（12 个 Product 表 + alembic_version），
这不代替真实数据库测试。

依赖变更后又启动了独立临时 Sandbox（port 19003、独立临时 SQLite，不改变共享服务），执行
`pytest -m "not database" -q -p no:cacheprovider --sandbox-url http://127.0.0.1:19003`：
**79 passed，26 database tests 明确 deselected**，包含 13 个真实 HTTP 集成测试，无 skips。
数据库 tests 已 collect 为 26 项，等待真实 PostgreSQL CI，不把 collect 当作执行通过。

本机没有 PostgreSQL/Docker，真实 PostgreSQL 测试必须由本 PR 的 database CI job 证明。
该 job 使用独立 PostgreSQL 17 服务；每条测试创建并只清理自己生成的 schema。
当前尚未取得此 job 结果，不宣称 Stage 2 数据库出口已通过。容器 build/start 仍未验证。
