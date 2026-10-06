# 当前代码的启动与验证

本页说明第三步商城及保留的客服模块。Stage/Phase 编号仅指旧客服交付。
商城实际范围见 [第三步切片](commerce/step-3-implementation.md)，结果见
[验证记录](verification/2026-10-06-commerce-step-3.md)。

## Local setup

Requires Python 3.12+ and Node.js 22.13+ within Node 22, or Node 24+
(Node 22 LTS is used in CI and Docker).
Docker Compose v2 is required only for the container setup.

Copy `.env.example` to `.env` at the repository root (`cp .env.example .env` on
POSIX, `Copy-Item .env.example .env` on PowerShell). Replace the example password in
both `POSTGRES_PASSWORD` and `DATABASE_URL`; URL-encode special characters in the
URL password. The example contains placeholders, not deployment credentials.

**Containers:** from the repository root:

```sh
docker compose config --quiet
docker compose up --build
```

Open frontend at `http://localhost:5173` and backend health at
`http://localhost:8000/health` (API docs: `http://localhost:8000/docs`). Ports can be
changed in `.env`. Services bind published ports to local loopback. PostgreSQL
uses a persistent named volume and Compose hostname `postgres`. Backend and frontend
source mounts support development reload; restart/rebuild after configuration or
dependency changes. `docker compose down` stops services and preserves database data.
These are development containers, not a production deployment.

**Host processes:** change the `DATABASE_URL` hostname in `.env` to `localhost`
(and use `POSTGRES_PORT` if changed). No database is needed for Phase 0 health.
Settings read the root `.env`; process environment variables take precedence.

```sh
cd backend
python -m venv .venv
# POSIX: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000 --no-access-log
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Host CLI ports are explicit arguments; `BACKEND_PORT` and `FRONTEND_PORT` in `.env`
control Compose port publishing. Set `VITE_API_BASE_URL` to the backend origin before
starting/building Vite (default `http://localhost:8000`). Configure the matching frontend
origin in `CORS_ALLOWED_ORIGINS`; alternate ports are not automatically trusted.

## 商城迁移、账号与双端演示

以下命令在 backend 目录执行，使用显式 DATABASE_URL 连接你的开发 PostgreSQL：

```sh
python -m alembic upgrade head
# 先在当前 shell 设置 APP_ENV=development 与自行选择的 DEMO_SEED_PASSWORD（12..128字符）
python -m app.commerce.seed
```

容器模式改用 `docker compose exec backend python -m alembic upgrade head`。
Seed 密码不自动传入容器；在本地 shell 设置后，用
`docker compose exec -e DEMO_SEED_PASSWORD backend python -m app.commerce.seed`
显式传入（backend 已设置 development）。商城种子不由启动服务隐式重置。


Seed 仅 development/test 运行，重复执行保留已有账号、商品、库存和历史；改密码环境变量
不会覆盖已有账号。不要把密码、Bearer 或真实客户资料写入 Git/普通日志。商城新增迁移
0003，与旧客服 0001/0002 共存；旧客服 Seed 不会生成商城数据。

所有演示账号使用本次显式配置的密码：

| 账号 | 能力 |
| --- | --- |
| customer.a / customer.b | 各自购物车、订单与收货 |
| owner.a / owner.b | shopA / shopB 店主，商品、库存与履约 |
| staff.a | shopA 履约成员，无商品/库存修改权 |
| dual.a | 客户与 shopA 店主，能力分开校验 |
| demo | 独立模拟事件操作者；不具备客户/商家权限 |

种子是虚构商品 A/B/L/Z，覆盖两家店铺、最后一件和缺货。金额为 CNY 整数分，运费/税费0。
前端密码/Bearer仅存内存，刷新后重新登录；购物车和订单仍在服务器数据库中。

用独立浏览器会话演示：

1. customer.a 选购 A 与 B，填写虚构地址下单；按两店生成两张独立订单。
2. 客户在各订单发起模拟付款，状态先为处理中。
3. demo 进入“模拟事件”，分别提交付款成功/失败；客户刷新详情读取实际结果。
4. owner.a 与 owner.b 进入“店铺工作台”，选择本店订单、填写数量创建包裹。
   A 数量为2时可分两次各发1件。
5. demo 对包裹提交运输/异常/送达事件，发生时间不早于出库且不在未来；客户刷新物流。
6. 全部应发商品已发且包裹送达后，客户确认收货。重新登录仍读取已完成订单。

商品与库存页面可创建草稿、SKU、调整库存、编辑价格和发布/归档；服务端处理版本冲突。
付款预留15分钟，GET不自动清理库存；客户取消/付款或 DEMO 指定订单到期结算触发事务。
不确定的写请求保留原请求重试，禁止通过刷新版本重复扣库存或重复发货。
模拟控制台仅development/test注册；生产环境没有结果注入端点。
消息、退款、退货、真实支付与真实物流尚未实现，不作为本次演示步骤。

## Backend APIs (Stage 3 baseline + Stage 4 feature branch)

Migrate and seed the Product PostgreSQL database using the explicit commands below
before using business endpoints. No database is required for /health. Test identities
are `agent.a`, `agent.b`, `agent.c`, `supervisor`, and `admin`; passwords come from your
explicit development/test `DEMO_SEED_PASSWORD`, never a repository default.

| Endpoint | Behavior |
| --- | --- |
| `POST /api/v1/auth/login` | Closed JSON username/password; opaque token with fixed 8h expiry |
| `GET /api/v1/auth/me` | Current active identity/role/team, requires Bearer |
| `POST /api/v1/auth/logout` | Revoke current session; empty 204 |
| `GET /api/v1/inquiries?limit=20&offset=0` | Authorized summaries; stable newest-first pagination |
| `GET /api/v1/inquiries/{id}` | Agent's assigned Inquiry or Supervisor's same-team Inquiry |
| `POST /api/v1/inquiries/{id}/resolve-context` | Closed expected_lock_version + Idempotency-Key; collect, persist and build Context |
| `GET /api/v1/inquiries/{id}/runs/{run_id}` | Authorized run status, error, version and busy state |
| `GET /api/v1/inquiries/{id}/contexts/{context_id}` | Authorized immutable Context/history, with is_current |
| `GET /api/v1/inquiries/{id}/order` | Current Context's stored canonical order, original timestamps and reevaluated freshness; no source call |

To resolve, submit `{"expected_lock_version": 1}` with the current Inquiry version,
Bearer authorization and a unique nonblank `Idempotency-Key` header. A new usable
Context returns 201; exact completed replay returns 200 without more source calls.
RUNNING replay returns 202 and Location. Required source failure saves FAILED and
returns its safe source error with run_id. Optional shipment/warehouse failures save
PARTIAL and a DEGRADED Context; they do not invent a business exception or empty success.

New resolution clears current Context/Draft before HTTP and never restores them
after failure. Old Contexts remain authorized history. The final transaction checks
the current session, permission and bindings again before publishing any facts.
Context quality is its creation-time result; `/order` reevaluates freshness from
the original times using that Context's stored policy. No current Context returns
409 CONTEXT_REQUIRED; missing order binding returns 422 ORDER_REFERENCE_MISSING.

Admin has no business access and receives an empty list. Unknown and forbidden Inquiry
UUIDs both return the same 403. Request validation follows identity/ownership checks;
caller role/team/order values cannot grant access. Responses are no-store, with a
validated/generated X-Request-Id. Error bodies never echo credentials, input values,
SQL or connection configuration. Login/failed-login/logout/access-denied audits are
transactional and contain only safe internal metadata.
The documented launch command and container disable raw URL access logs, which
could otherwise record caller-supplied query content; use the safe Audit records.

Use `/docs` to inspect the API. To try requests from that page, also explicitly add
the trusted API page origin (for example `http://localhost:8000`) to the allowed
origins below; it is not silently authorized by the server. Keep Bearer tokens only in memory.
Do not log or persist it in URL/localStorage. `CORS_ALLOWED_ORIGINS` is an explicit JSON
origin array; default [] rejects Origin-bearing business requests. `.env.example`
allows only the two local frontend origins on 5173; change it when your port changes.
Compose passes the same setting. No cookie authentication is used. Deployment must
use HTTPS; login abuse protection and deployment review remain future operational gates.

See [the Stage 3 slice](contracts/stage-3-implementation.md) and
[validation status](verification/2026-10-04-stage-3-access-validation.md).

## Checks

From `backend/`, with its virtual environment active:

```sh
ruff check .
ruff format --check .
pytest
```

From `frontend/`:

```sh
npm test
npm run lint
npm run typecheck
npm run build
```

From the repository root, validate without a personal `.env`:

```sh
docker compose --env-file .env.example config --quiet
```

CI runs unit tests (`pytest -m "not integration and not database"`), a separate
real PostgreSQL database job, and the lint/build/config checks.
The independent Sandbox is not available in this repository's CI; real HTTP tests
must run separately as described below, and skipped tests do not prove integration.
`/health` returns exactly
`{"status":"ok","service":"ecommerce-order-support-backend"}`; it reports
process liveness, not database connectivity or external-system readiness.

### Historical support-module validation status

Stage 4 results and evidence are maintained in the
[current verification record](verification/2026-10-06-stage-4-validation.md).
The records below describe historical revisions, not a substitute for this branch's checks.

Stage 3 candidate on 2026-10-04: **116 local tests passed**, including all 13 real
Sandbox HTTP tests; **59 real PostgreSQL tests passed** in CI (26 persistence + 33
API/transaction cases). Ruff, frontend lint/type/build and Compose configuration
also passed. Review and container startup remain pending. See the
[Stage 3 observed record](verification/2026-10-04-stage-3-access-validation.md).

On 2026-10-03, local backend lint/format, all **70 tests (13 real HTTP integration
tests, no skips)**, frontend lint/typecheck/build and runtime `/health` passed.
The fetched main baseline's GitHub backend/frontend/compose jobs also passed.
Local Docker is unavailable; container build/startup has not been verified.
See [the observed validation record](verification/2026-10-03-repository-sync-validation.md)
for exact revisions and evidence. The [2026-09-23 basic record](verification/2026-09-23-phase-1-basic-validation.md)
is historical and was based on reported results only.

## Sandbox integration and real HTTP tests

The boundary is `DemoCommerce HTTP JSON → Sandbox adapter → canonical Product snapshot`.
Product consumers use the protocols; raw fields and routes are confined to the
adapter. OrderProvider reads orders and lists parcels; LogisticsProvider reads one
canonical parcel's shipment/events. The caller accounts for each parcel independently.
WarehouseProvider preserves notes, and MessageProvider reads inquiries/records replies.
No Provider calls another Provider or resolves contradictory sources.

In the independent **demo-commerce-sandbox** checkout (locally a sibling directory):

```sh
uv sync --locked
# Optional: set SANDBOX_DB_PATH to a new temporary SQLite filename in your shell.
uv run uvicorn app.main:app --host 127.0.0.1 --port 9000
```

Do not reset a shared Sandbox. A fresh database is seeded automatically; tests
use unique reply keys and create three simulated replies per idempotency test run.
The Product never imports Sandbox code or reads its database. Source timestamps
are fixed relative to `2026-09-20T06:00:00Z`; integration tests use FixedClock at
that instant. Receipt `sent_at` remains source-owned actual acceptance time.

Configure `SANDBOX_BASE_URL` and positive `SANDBOX_TIMEOUT_SECONDS` in root `.env`
or the process environment. S0-S1 has **no API key**. For a Product container calling
a host Sandbox on Docker Desktop, change the URL to `http://host.docker.internal:9000`
and ensure the Sandbox is reachable from the container; host loopback inside the
container points to the container itself. No client is created by `/health`.

From `backend/`, with its environment active and Sandbox already running:

```sh
pytest --sandbox-url http://127.0.0.1:9000
# Only the real HTTP suite, with individual scenario results:
pytest tests/integration -v --sandbox-url http://127.0.0.1:9000
```

`INTEGRATION_SANDBOX_URL` is an alternative to the explicit flag. Without either,
the integration suite is visibly skipped; if a URL is supplied but unavailable,
tests fail rather than falling back to mocks. `SANDBOX_BASE_URL` configures runtime
clients; the separate integration opt-in prevents accidental test writes.

Adapters are used via `async with SandboxClient(Settings(), clock) as client`;
pass that client to the concrete Provider. Omit `clock` to use SystemClock. Exiting
closes HTTP connections. Only the adapter handles `/api/...` paths and source JSON.

See [contract mappings and differences](external-system-contract.md) for S10's
actual logistics 404 (distinct from S01's successful empty parcels), source timestamp
ownership, typed failures, and idempotency. Fixed seed scenarios have no unknown
statuses or malformed payloads; supplemental unit tests cover those conditions.

## Existing support-module limitations

No support workflow or send endpoint is exposed. Provider send is a low-level
integration operation; authorization/approval will be implemented before exposure.
There is no automatic retry or cache. Stage 4 collects explicit per-source/per-parcel
outcomes and applies the frozen freshness policy without filling gaps from old runs.
If events fail after shipment retrieval, the operation raises the typed failure,
rather than returning an apparently complete shipment. A parcel without tracking
cannot be queried yet and produces a local ValueError without HTTP.

SQLAlchemy 2, Alembic, psycopg and Argon2id are available for explicit Stage 2 CLI
work. They do not connect a database, authenticate users or implement workflows
when `/health` starts. HTTPX remains the external integration dependency.
React Router and TanStack Query are deferred until there are workflows to route
or fetch. Frontend dependencies are locked in `package-lock.json`; Python uses
bounded dependency ranges and does not yet have a full transitive lock.

## Product database and demo Seed (merged Stage 2)

Use Product PostgreSQL only. Migrations read the process `DATABASE_URL`, using
`postgresql+psycopg`; for a host CLI use localhost instead of Compose's `postgres`
hostname. Configure the URL/password in your shell, never in command-line arguments
or source. Then from `backend/`:

```sh
python -m alembic upgrade head
python -m alembic current
# Explicit development/test only; set DEMO_SEED_PASSWORD securely in the shell first.
python -m app.db.seed
```

Seed requires `APP_ENV=development` or `test` and an explicit 12–128 character
`DEMO_SEED_PASSWORD`; production is rejected before database access. It inserts
two demo teams, five users (agent.a/b/c, supervisor, admin), and twelve fixed
Inquiry bindings. It hashes passwords with the contract's Argon2id parameters
and never resets existing passwords, ownership or workflow. It does not copy
orders, parcels or Sandbox data. Clear the temporary password environment variable
after use. Downgrade is destructive; only use it on a disposable test database.

To run actual PostgreSQL tests, configure `TEST_DATABASE_URL` for an isolated
development/test server where the test role can create schemas:

```sh
pytest tests/database -q
```

Tests create uniquely named `fde_test_<uuid>` schemas and clean up only those
schemas. They validate migration upgrade/downgrade/re-upgrade, ORM/schema agreement,
Seed idempotency, keys/FKs/enums/UTC, empty-vs-failed JSON, append-only history,
one-Approval uniqueness and rejection of a stale-version write in one transaction.
That test is not evidence of two independent concurrent transactions; Stage 3–5
service tests must verify actual concurrency and semantic ownership. If the URL is absent they
visibly skip; skips do not satisfy the Stage 2 exit gate. CI provides disposable
PostgreSQL 17 and runs these tests separately without skips.

Revision `0002_nonblank_constraints` upgrades the seven nonblank checks using
PostgreSQL POSIX `[:space:]` (including spaces, tabs and line breaks). It validates
but does not trim or rewrite text. Existing whitespace-only values abort the upgrade
transaction; investigate in a controlled environment rather than deleting records
or disabling history triggers. Frozen revision `0001_core_mvp` is unchanged.
Downgrading to 0001 restores its weaker checks and is not a production workaround.

Model references and JSON are storage structures; Stage 3–5 services must still
enforce same-Inquiry/team, source schema, Context version, Validation and approval
preconditions in transactions. No record insertion is an authorization grant.
Implementation references: [SQLAlchemy declarative](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html),
[Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html),
[psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).

Review fixes and their RED/GREEN validation evidence are recorded in
[the 2026-10-04 database review log](verification/2026-10-04-database-review-fixes.md).
Database PR integration, native PostgreSQL 17 migration/Seed validation and local
instance safety notes are in [the local database validation record](verification/2026-10-04-database-local-integration.md).

## 可选真实浏览器验收

[commerce-browser-acceptance.cjs](../scripts/commerce-browser-acceptance.cjs)通过页面和真实API
执行两店下单、两次付款、三包裹（含分批发货）、模拟送达与两单确认收货。
仅在**新建隔离schema、完成迁移和商城Seed**的演示环境运行；脚本不负责清库/重置，
也不适用于已有订单/库存变化的演示库。失败会关闭自己创建的浏览器并只打印安全步骤。

需要可用的Playwright模块与浏览器，这是可选验收工具，不增加生产运行依赖。
设置以下环境变量后，从仓库根目录运行 `node scripts/commerce-browser-acceptance.cjs`：

| 变量 | 用途 |
| --- | --- |
| COMMERCE_UI_URL | 前端地址，默认http://localhost:5173 |
| COMMERCE_PASSWORD_FILE | 必需：仅本机可读的演示密码文件路径，内容与Seed一致 |
| COMMERCE_SCREENSHOT_DIR | 输出截图目录，默认/tmp/fde-commerce-browser-evidence |
| CHROME_EXECUTABLE | 可选：已安装Chrome可执行文件；不设置则使用Playwright自带浏览器 |
| PLAYWRIGHT_MODULE | 可选：已安装Playwright模块路径；不设置则require('playwright') |

前端/API时钟需正常同步；模拟物流时间不能早于出库或晚于服务端当前时间。
脚本等待具体HTTP成功和队列变化，不把等待若干秒当作付款/物流成功证据。
