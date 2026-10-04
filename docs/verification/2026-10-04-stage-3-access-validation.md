# Stage 3 身份授权与咨询 API 验证

日期：2026-10-04；分支 `codex/core-auth-inquiries`，基于 `baec664`（数据库 PR #3）。
远端 main 仍 `33857e2`，PR #2/#3/#4 尚未合并。用户明确授权本阶段依赖候选，不代替 Review。

## 当前观察

- 新增 auth/login、me、logout、Inquiry list/detail 和不取事实的 order 前置条件入口。
- 沿用 12 表迁移；无新 schema。Argon2id 参数复用 Seed，32 字节 token 只存摘要。
- 事务保护当前身份/会话/咨询，固定 Clock；安全 Audit 与变更同事务。
- 封闭输入、认证优先、同形 403、错误脱敏、请求 ID/no-store、显式 CORS。
- 本地 Ruff check/format 通过，37 文件格式正确。
- 本地 `pytest -m "not integration and not database" -q -p no:cacheprovider`：
  **103 passed，72 deselected**。包含新增 37 项纯函数/HTTP 边界检查。
- `pytest tests/database --collect-only` 收集 **59** 项：Stage 2 原有 26 + 新增 33 项
  真实 PG API/事务检查。尚未执行不能算通过，待 CI PostgreSQL job 验证。

新 PG 检查通过 ASGI HTTP + 真实隔离 schema，覆盖登录摘要/Audit、统一凭据失败、退出仅
撤销当前 Session、精确八小时边界、当前角色/team/active 变更、授权分页、同形拒绝、
验证顺序、绑定/Context 错误、Audit 失败回滚和真实锁阻止事务中授权变更。
所有 Stage 3 API 测试监测六个 Sandbox Provider 方法，调用数必须为零。

## 剩余检查与限制

前端 lint/type/build 通过（28 modules）；完整本地后端回归包含临时独立 Sandbox
`4131f1c4` 的真实 HTTP：`pytest -m "not database" --sandbox-url http://127.0.0.1:19004
-q -p no:cacheprovider` 为 **116 passed，59 database deselected，无 skips**，其中 13 个
真实 HTTP。37 个 Python 文件格式检查通过。Compose 与真实 PG CI 待完成。
本机无 PostgreSQL/Docker；不安装系统服务、不用 SQLite/mock DB 代替。
TestClient/anyio 依赖发出弃用警告，测试成功；不隐瞒或声称无警告。
容器 build/start、HTTPS/登录防暴破部署评审、main 保护和人工 Review/合并未完成。
UI 登录、取事实、Evidence/Context、AI、Validation/批准/发送仍未实现。
