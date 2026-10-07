# 当前代码的启动与验证

本页说明第三/四步商城及保留的客服模块。Stage/Phase 编号仅指旧客服交付。
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

以下命令在 backend 目录执行，使用显式 DATABASE_URL 连接你的开发 PostgreSQL。
迁移/商城Seed读取进程环境：仅复制根目录.env不会把值导入shell；运行CLI前需显式设置
DATABASE_URL、APP_ENV和DEMO_SEED_PASSWORD（不要把值提交Git）：

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
0003/0004/0005，与旧客服 0001/0002 共存；旧客服 Seed 不会生成商城数据。

所有演示账号使用本次显式配置的密码：

| 账号 | 能力 |
| --- | --- |
| customer.a / customer.b | 各自购物车、订单、消息、收货与售后申请 |
| owner.a / owner.b | shopA / shopB 店主，商品、库存、履约、消息与售后审核/退款 |
| staff.a | shopA 履约/消息成员，可读售后，无审核/退款或商品/库存修改权 |
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
第四步新增消息与模拟售后；真实支付和真实物流仍未接入。

7. 客户从商品联系店铺建立通用会话，或从订单“联系店铺 · 此订单”建立订单会话；
   商家进入“店铺消息”读取并回复，双方点击刷新获取新消息。
8. 已付未发订单选“未发货退款”，填写部分数量与原因；店主在订单中批准或拒绝。
   批准后店主发起模拟退款，demo在模拟事件台提交成功/失败；失败后店主可重新发起。
9. 已送达商品选“退货退款”（14天窗口）；批准后客户登记虚构退货运单。
   店主确认收到全部申请数量并明确选择回库/不回库，再发起模拟退款。
10. 双方刷新查看金额、退款数量和履约状态；回库发生于收退货时，退款不会再次回库。

付款/退款PENDING不会按等待时间自动成功；必须使用独立demo账号手动提交结果。
每张订单显示所属店铺：shopA由owner.a处理，shopB由owner.b处理。
已有数据库只运行alembic upgrade head，不为升级删除或重新播种订单。

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

第四步使用 [commerce-step4-browser-acceptance.cjs](../scripts/commerce-step4-browser-acceptance.cjs)：
同样在全新隔离schema/Seed中运行，必需 `COMMERCE_UI_URL` 与 `COMMERCE_PASSWORD_FILE`，
其余模块/浏览器/截图变量同上。未设置CHROME_EXECUTABLE时，第四步脚本默认本机macOS Chrome；
其他系统需显式设置已安装浏览器路径。

从仓库根目录运行 `node scripts/commerce-step4-browser-acceptance.cjs`。
`COMMERCE_SCENARIO` 选择下列之一；**每个场景都要另外新建schema并迁移/Seed**，不能连续复用已经修改的库存：

| 场景 | 内容 |
| --- | --- |
| partial-return（默认） | 消息、未发部分退款失败后重试、余量发货、送达后退货回库再退款 |
| full-refund | 全部未发数量退款，订单取消/财务已退款 |
| shipped-partial-refund | 发1件后退款未发1件，订单成为全部有效量已发 |
| return-no-restock | 已送达商品退货退款，明确不回库 |
| reject-withdraw | 拒绝及客户撤销，保留历史且金额/库存不变 |

各场景均验证通用/订单会话、纯文本消息、STAFF只读售后、重新登录持久化及移动端宽度。
脚本通过页面写入，仅使用额外授权GET核实订单和库存，不直接读库或重置schema。

## 第五步统一演示入口

安装backend开发依赖（运行Python需要SQLAlchemy/Alembic/uvicorn），frontend先npm ci。
显式设置APP_ENV=development或test，TEST_DATABASE_URL指向允许创建schema的隔离PostgreSQL。
运行器拒绝production、缺失URL、非psycopg和自带search_path/options的URL。
不要使用生产数据库；TEST_DATABASE_URL不通过命令行参数提供。

从仓库根目录运行：

```sh
python scripts/commerce-demo.py --scenario interactive
# 需要Playwright模块及浏览器；变量说明沿用上面的浏览器配置表。
python scripts/commerce-demo.py --scenario all --evidence-dir /tmp/commerce-evidence
python scripts/commerce-demo.py --scenario exceptions
```

每次创建commerce_demo_<uuid>，执行现有迁移/商城Seed；不drop、truncate、重置任何schema。
密码随机生成，0600临时文件、0700目录；只打印文件路径。interactive所有Seed账号使用此密码，
用户customer.a/b、商家owner.a/b、员工staff.a、模拟操作demo、组合角色dual.a，以及独立入驻审核reviewer。
DEMO仍需人工明确提交付款/退款结果，待处理不会自动成功。

场景purchase复用第三步；partial-return、full-refund、shipped-partial-refund、return-no-restock、
reject-withdraw复用第四步；exceptions验证改价冲突恢复、地址保留、旧价格快照、付款失败重试和
物流异常恢复；onboarding验证注册恢复、地址簿、审核开店及新店购买。all按顺序执行八个场景，每个另建schema，不能互相消耗库存。
脚本退出只停止自己启动的API/Vite/浏览器；schema保留，可供调查，不修改当前5179演示库。

浏览器完成后，运行器授权GET客户全部订单，停止并重新启动自己的API，再GET比较完整订单与售后
记录；同时用真实HTTP验证401和重复JSON/query拒绝。不会把TestClient当socketHTTP证据。
results.json记录场景、重启数量、源码HEAD/dirty标识/源码树SHA256；失败和自动运行被中断明确记录，
返回非零。源码树hash包括tracked与非ignored新文件，用于识别未提交验收，不输出凭证。
日志和连接元数据只在受保护临时目录，不能提交Git或作为公开演示资料。

运行器安全回归：`python -m unittest discover -s scripts/tests`。
业务回归：backend目录的`pytest tests/database/test_commerce*.py -q`（要求TEST_DATABASE_URL，跳过不算验收）。
[54项映射](commerce/step-5-coverage.json)已关联本次实际节点结果；
[第五步验收](verification/2026-10-07-commerce-step-5.md)保存执行命令、覆盖范围和限制。

## 本地模拟邮件与入驻

当前采用 `commerce-onboarding-v1`，没有真实邮件服务。统一演示入口自动创建私有模拟邮箱，
初始化独立 `reviewer`（与虚构演示账号使用同一受保护随机密码文件），`all`现在包含九个场景。
仅注册新用户时使用自行选择的12..128字符密码；新注册账号不能在邮箱验证前登录。

```sh
python scripts/commerce-demo.py --scenario interactive
python scripts/commerce-demo.py --scenario onboarding
```

interactive 输出 `mailbox_dir` 和 `password_file` 路径。邮箱验证码仅环境操作者可从本机查看：

```sh
cd backend
python -m app.commerce.mailbox /absolute/private/mailbox --email new.user@example.com
```

该CLI明确显示验证码供本机人工验证；不要将输出、邮件文件或密码文件加入Git/普通日志。
页面不提供匿名邮箱查看器。目录0700、邮件与隐藏HMAC密钥文件0600；需要保留该目录和密钥，
才能在进程重启后继续安全重放原认证请求。真实部署前应接入真实邮件适配器和生产密钥管理。
自管开发启动需显式配置 `COMMERCE_MAILBOX_DIR=/absolute/private/mailbox`，只支持development/test。
缺配置拒绝相关流程503；邮箱交付失败同键保持失败，用新请求重发验证或恢复，不重复创建账号。

自管已有库先 `alembic upgrade head`，再显式初始化审核员：

```sh
python -m app.commerce.onboarding_seed
```

它只在development/test且显式DEMO_SEED_PASSWORD时新增reviewer，不覆盖既有账号密码或资格。
审核员可查看入驻申请并批准/拒绝；客户和DEMO不能审核。批准后申请人在账户中心刷新资格，
进入新店商品/SKU/库存页面，上架后所有客户通过原购物流程购买。
用户账户中心提供资料、邮箱绑定、改密码、地址簿及申请历史；重置/修改密码撤销全部旧会话。
地址簿预填结账地址，用户可继续编辑此次草稿；保存地址簿不会更改既有订单地址快照。

入驻真实浏览器脚本为 `scripts/commerce-onboarding-browser-acceptance.cjs`，在原浏览器环境变量
之外需要 `COMMERCE_MAILBOX_DIR`。该脚本只通过本机文件读取测试账号模拟码，业务写入全部经页面。

## 数据库只读查看与历史

见[本机数据库查询说明](database.md)。`scripts/commerce-db.py` 支持列出表、字段、当前行、按业务表/UUID查询历史、私有CSV导出与默认只读psql。正常迁移命令仍为 `alembic upgrade head`；0006是新增历史对象，不清空已有账户、订单或库存。

## 商品体验与平台运营

已有开发数据库先执行 `alembic upgrade head`，然后在backend目录、显式development/test和DEMO_SEED_PASSWORD配置下运行：

```sh
python -m app.commerce.platform_seed
```

只新增独立虚构 `platform` 账号，密码使用受保护的演示密码配置；若该用户名已存在，保持原账号不变。统一演示入口会显式执行这一seed。该账号拥有平台运营入口，审核员reviewer继续只处理入驻。
图片由后端校验、解码并重编码PNG，原始上传限制3MiB、最多1600万像素、每商品最多8张。图片二进制保存在独立数据库表；普通查询/CSV和历史快照不输出图片字节。

```sh
python scripts/commerce-demo.py --scenario experience-operations
python scripts/commerce-demo.py --scenario all
```

新增浏览器场景覆盖图片分类筛选、收藏、评价回复、举报处理恢复、店铺限制、争议证据及仲裁后模拟退款、报表和移动端布局。它使用新的隔离schema，保留原有本机数据；需要与原场景相同的Playwright/Chrome配置。
具体操作规则见[领域说明](commerce/shopping-and-platform.md)。报表统计已成功模拟支付/退款，净额不是利润。
