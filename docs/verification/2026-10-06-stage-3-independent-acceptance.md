# Stage 3 独立复验与 Stage 4 数据交接

日期：2026-10-06（Asia/Kuala_Lumpur）。用户委托数据/测试侧由 Codex 承担。
结论：本轮静态审查未发现明确 Stage 3 缺陷；已有后端及 PostgreSQL 测试独立重跑通过。
这是 AI 辅助复验，不是另一位人类开发者批准，也不证明完整 Core MVP 或部署完成。
本轮无运行时代码、迁移或测试行为修改；不编造修复记录。

## 1. 固定基线与当前 GitHub 状态

- main：`8469971982a82369c94ab9387ab73d55f6caf6a6`；复核时远端未变化。
- Stage 3 审查固定点：`58aac3645f9d831ebd6df30a78b849761de4a3ff`。
- [PR #5](https://github.com/Mark-UM/FDE-test/pull/5) 已于 `2026-10-06T10:45:46Z` 合并。
- [main CI 37451921878](https://github.com/Mark-UM/FDE-test/actions/runs/37451921878)
  对该完整 SHA 的 backend/database/frontend/compose 四个 job 均 success。
  这是 GitHub 观察，不冒称本轮本机 frontend/Compose 执行。
- [PR #4](https://github.com/Mark-UM/FDE-test/pull/4) 仍 OPEN/DRAFT，base
  为 `docs/core-mvp-contracts`；本轮不修改、合并或要求必须先合并它才能做后端 Stage 4。
- main branch protection API 为 404，effective rules API 为 `[]`；
  本次可见状态未发现保护规则，未修改设置。

## 2. 两个独立静态审查维度

| Standards 审查 | Spec 审查 |
| --- | --- |
| 明确缺陷 0；检查架构/范围、凭据与敏感日志、数据库事务/锁、CORS、错误边界及测试 | 明确契约违反 0；逐项核对 Stage 3 slice、core-api/data/lifecycle 与实现/测试 |
| 当前身份、摘要存储、User → Session → Inquiry 锁顺序、安全 Audit/回滚符合本阶段约束 | Agent/Supervisor/Admin 范围、未知/无权同形 403、先认证后请求验证、8h 固定 expiry/退出符合契约 |
| 未夹带 Evidence/AI/发送/高风险操作，启动和 health 不连库 | `/order` 的 422/409 是冻结切片，不把尚未实现的 Stage 4 200 当缺陷 |

两位审查 agent 只读检查代码与契约，不执行测试；以下运行结果由主 agent 独立取得。
这仍是对同一已有测试套件的复跑，不声称新建了完全独立的验收测试集。

### 非 Stage 3 缺陷，但 Stage 4 必须处理的实现依赖

1. `backend/app/main.py:52–53` 当前只允许 GET/POST，以及 Authorization/
   Content-Type/X-Request-Id。浏览器 resolve 使用 Idempotency-Key 时须显式允许并测试；
   Stage 5 PATCH 另行扩展。
2. `backend/app/api/core.py:28–43` 故意捕获 ApiError 后提交安全 Audit。
   resolver 必须区分拒绝、刻意持久化 FAILED run 与异常部分写入，不能直接复用包装器。
3. `docs/contracts/core-lifecycle.md` 要求网络请求位于开始/结束短事务之间；
   RUNNING 占用、清旧指针、版本递增、返回后重查授权及人工中断恢复均待实现。
4. 闭合 Context/Evidence schema、来源编排与引用链/freshness 规则仍未实现。

部署防暴破、HTTPS、body 在缓冲前限制、会话/Audit 保留策略属于运行审查事项；
不作为本轮冻结 Stage 3 的新增验收要求，也不声称它们已完成。

## 3. 本轮运行证据

原 Lexar 工作区未挂载。仅在 `/private/tmp/fde-acceptance-gMbYCO/repo` 克隆 main，
创建 `codex/stage-3-acceptance-stage-4-readiness`，未更改用户原工作区。
使用现有临时 venv，但显式 `PYTHONPATH=.`，确认导入的是该 checkout 的 backend/app。
环境：macOS、Python 3.12.14、PostgreSQL 17.11（Homebrew）。

| 检查 | 本轮观察 |
| --- | --- |
| `PYTHONPATH=. APP_ENV=test pytest -m 'not integration and not database' -q` | 103 passed、104 deselected、1 warning，1.07s，exit 0 |
| `ruff check .` | All checks passed，exit 0 |
| `ruff format --check .` | 38 files already formatted，exit 0 |
| `PYTHONPATH=. APP_ENV=test TEST_DATABASE_URL=<独立库> pytest tests/database -q -x` | 91 passed、0 skipped、1 warning，50.58s，exit 0 |

pytest/Ruff 实际来自 `/private/tmp/fde-review-venv/bin/`，执行位置 backend/。
数据库 URL 只指向本轮临时 Unix socket，没有密码或外部数据库。
两套测试均出现 Starlette TestClient 关于 httpx 的 deprecation warning，已保留观察，
不为文档交接升级依赖。103+91 是两个不重叠测试选择；13 个 integration 测试未运行。

### 执行受阻和恢复记录（环境问题，不是业务修复）

- 首轮受限 initdb 因 `shmget ... Operation not permitted` 失败，未启动实例。
- 获准在沙箱外启动同一个专用临时库后，受限 pytest 仍不能连接 socket，91 项 setup errors；
  单次 psycopg 连接复核错误为 `Operation not permitted`，不是业务断言失败。
- 同基线/库使用获准的测试进程重跑，91 项全部通过；没有为了通过修改代码、约束或测试。
- 临时 cluster `/private/tmp/fde-acceptance-pg-3ZOEuR/data`，role/database
  `fde_acceptance`、socket 目录同父目录、port 55439；`listen_addresses=''`，不监听 TCP。
  local trust 仅用于受限临时 socket；host auth 为 scram，不是部署配置。
- 测试自行创建并删除其随机 `fde_test_<uuid>` schema；没有连接/清理原数据库。
  结束后 `pg_ctl stop -m fast` 返回 server stopped；临时库/日志保留，未自动删除目录。

## 4. 本轮交付与下一目标

- [Stage 4 场景覆盖与缺口](../testing/2026-10-06-stage-4-scenario-coverage.md)：
  精确区分 11 个来源场景、现有 Provider assertions 与待补 resolver/故障/权限测试。
- [Evidence/CaseContext 数据验收标准](../testing/2026-10-06-evidence-case-context-acceptance.md)：
  规定引用、原时间、部分失败、质量、权限、历史版本、幂等及事务签收出口。
- [执行计划](../superpowers/plans/2026-10-06-data-acceptance-readiness.md)。

应用负责人下一目标：按冻结契约实现不调用 AI 的 Stage 4 Evidence/CaseContext，
数据/测试侧依据上述清单验收。此处交付准备材料，不自动开始其服务或 Stage 5 AI。
后续缺陷必须先记录场景、预期/实际、根因、修复提交与回归结果。

## 5. 本轮没有验证或完成的出口

独立 Sandbox 13 项 HTTP 未重跑；完整 Compose build/start、浏览器端到端、真实模型 eval
未运行；PR #4、main 保护未处理。已有 PG/API 测试走真实隔离 PostgreSQL + ASGI TestClient，
不是独立 Uvicorn 网络部署。已有存储模型/测试不证明 Stage 4 服务已具备语义/版本约束。
Stage 4 尚无实际验收结果，本轮文档以单独 PR 交付，不自动合并 main。
