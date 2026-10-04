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
数据库 tests 在真实 PostgreSQL CI 执行：**26 passed，22.81s，无 skip**。

本机没有 PostgreSQL/Docker，真实 PostgreSQL 测试必须由本 PR 的 database CI job 证明。
该 job 使用独立 PostgreSQL 17 服务；每条测试创建并只清理自己生成的 schema。
实现提交 `eeb9aca418438b8d9fc078be562919e2c19b869f` 的
[PR CI run 37109759410](https://github.com/Mark-UM/FDE-test/actions/runs/37109759410)
全部成功：backend 66 个单元测试、database 26 个真实 PG 测试、frontend lint/type/build、
Compose config。database job `111165226471` 日志确认执行数量和时间，不采用跳过结果。
PG 测试覆盖迁移 up/down/up、ORM/schema 一致性、幂等 Seed 与 Argon2id、外键/版本/幂等
约束、失败与空结果、六表 append-only、Approval 唯一性、乐观锁、原来源时间保留。

2026-10-04 审查澄清：上述乐观锁测试仅证明同事务内旧版本写入被拒绝，未证明两个独立
事务并发；跨行同 Inquiry/team 的语义检查留给 Stage 3–5 服务测试。原结果是历史基线，
不覆盖新增空白字符回归。后续修复见 [审查修复记录](2026-10-04-database-review-fixes.md)。

数据库候选的技术检查已通过；两名开发者 Review 和 main 合并仍未完成。
容器 build/start 仍未验证，不能以 Compose config 代替运行验收。
