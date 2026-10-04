# Ecommerce Order Support Assistant

Small/cross-border ecommerce support agents answer questions such as “Where is my
order?” by manually collecting facts from order systems, logistics systems, and
warehouse notes. This product will bring those facts together into traceable
evidence and help an agent prepare a careful reply.

**Current implementation: Product Phase 1 — External Integration Foundation.**
Canonical snapshots, clocks, four Provider protocols and DemoCommerce HTTP adapters
are implemented and tested against the independent S0-S1 service. This explicitly
authorized phase supersedes the original roadmap's Phase 1 database/seed ordering.
Main still exposes only `GET /health`. This dependent candidate implements Stage 3
backend authentication and permission-scoped Inquiry reads using Stage 2 Product
persistence. There is no Evidence Engine, CaseContext resolver, AI, retry or cache.
The static workbench remains a separate candidate in PR #4; this branch's frontend
is the foundation shell.

This candidate branch adds **Stage 2 Product persistence**: SQLAlchemy records,
an explicit Alembic migration and a development/test Seed CLI. Database connections
are created lazily for business requests; startup and /health remain independent.
Stage 3 depends on database PR #3 and remains pending developer review.

## Core V1 target

Inquiry → Authentication / Authorization → Order lookup → All parcels / Logistics
→ Warehouse notes → Evidence → CaseContext → Structured LLM analysis → Validation
→ Human review → Mock send → Audit / Metrics.

**Program owns facts. AI owns interpretation and wording.** Backend code controls
permissions, deterministic rules, freshness, and actions. Important claims must
trace to evidence. Facts, plans, and uncertainty stay distinct; cached/old data
cannot be presented as live. External systems enter through Provider interfaces.
Human review is required before sending.

This is not a general chatbot, SaaS/Agent platform, CRM, ERP, or ecommerce platform.
Core V1 excludes autonomous support, multi-tenancy, payment, inventory forecasting,
marketing, and execution of refunds, cancellations, address changes, or compensation.

## Two-person Core MVP delivery

The active collaboration goal is a Core-only minimum vertical slice:

```text
Inquiry → authorized facts → Evidence → CaseContext → structured AI draft
→ deterministic validation → human edit and approval
```

DemoCommerce Sandbox expansion is not part of this delivery slice. Existing Sandbox
adapter code remains available, but the team will not add Sandbox features while
building the Core MVP.

The two-person ownership model is:

- **Data, test and AI owner:** database design, SQLAlchemy models, Alembic migrations,
  seed data, database and scenario tests, LLM integration and AI evaluation.
- **Application owner:** repositories, services, APIs, permissions, deterministic
  Evidence/CaseContext construction, validation, frontend and deployment.
- **Shared:** contracts, pull-request review, stage acceptance and end-to-end demo.

Branches represent short-lived deliverables rather than people. `main` is the only
long-lived stable branch; direct pushes are not part of the workflow. The intended
sequence is contracts → database/workbench shell → order/inquiry API → Evidence and
CaseContext → AI draft/validation → workbench/end-to-end acceptance. Each branch is
created from an updated `main`, merged by reviewed PR after its checks pass, and then
deleted.

See the complete responsibilities, branch names, commands, dependencies, PR rules
and Definition of Done in
[the two-person Core MVP workflow](docs/superpowers/specs/2026-09-22-core-mvp-two-person-workflow-design.md).

As of 2026-10-03, Phase 1 is merged into `main`; the collaboration documents remain
on `docs/core-mvp-contracts`. **Stage 1: Core MVP contracts** are now prepared as a
documentation package, pending the two developers' review and merge. Read the
[contract index and decisions](docs/contracts/README.md), then the six linked contracts.
Stage 2 candidates are [database PR #3](https://github.com/Mark-UM/FDE-test/pull/3)
and [workbench PR #4](https://github.com/Mark-UM/FDE-test/pull/4), with passing checks.
The user's 2026-10-04 request authorizes Stage 3 as a dependent candidate on PR #3.
See [current delivery status and the six next-stage tasks](docs/plans/04_core_mvp_next_stage_plan.md).
Main protection, developer review/merge and container startup verification remain
outstanding. Candidate preparation does not replace those gates.

## Repository

```text
backend/                    FastAPI, environment settings, tests, Dockerfile
  app/integrations/         Canonical models, protocols, explicit external errors
    sandbox/                Raw HTTP schemas, client, explicit source adapters
  app/core/clock.py         SystemClock and deterministic FixedClock
  app/api/core.py           Stage 3 session and Inquiry HTTP endpoints
  app/services/core_access.py  Current identity/ownership and transactional reads
  tests/integration/        Real HTTP tests (opt in with --sandbox-url)
frontend/                   React + TypeScript + Vite shell, Dockerfile
docs/
  plans/01_core_plan.md      Authoritative product roadmap
  plans/03_ecommerce_environment_plan.md  Future external Sandbox specification
  superpowers/specs/         Approved delivery and collaboration designs
  architecture.md           Responsibility boundaries and future pipeline
  scope.md                  Phase 0 and Core V1 scope
  external-system-contract.md  Conceptual external data contract
.github/workflows/ci.yml     Lint, tests, type/build, Compose configuration checks
AGENTS.md                   Persistent coding instructions
.env.example                Development configuration template
docker-compose.yml          Backend, frontend, PostgreSQL
```

The original root-level plans were moved unchanged into `docs/plans/` using the
canonical filenames above. Historical filenames referenced inside the plans refer
to those same documents.

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
control Compose port publishing. The frontend currently makes no API calls.

## Stage 3 backend API candidate

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
| `GET /api/v1/inquiries/{id}/order` | Authorized placeholder: 422 if unbound, otherwise 409 CONTEXT_REQUIRED |

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

See [the Stage 3 slice](docs/contracts/stage-3-implementation.md) and
[validation status](docs/verification/2026-10-04-stage-3-access-validation.md).

## Checks

From `backend/`, with its virtual environment active:

```sh
ruff check .
ruff format --check .
pytest
```

From `frontend/`:

```sh
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

### Latest validation status

Stage 3 candidate on 2026-10-04: **116 local tests passed**, including all 13 real
Sandbox HTTP tests; **59 real PostgreSQL tests passed** in CI (26 persistence + 33
API/transaction cases). Ruff, frontend lint/type/build and Compose configuration
also passed. Review and container startup remain pending. See the
[Stage 3 observed record](docs/verification/2026-10-04-stage-3-access-validation.md).

On 2026-10-03, local backend lint/format, all **70 tests (13 real HTTP integration
tests, no skips)**, frontend lint/typecheck/build and runtime `/health` passed.
The fetched main baseline's GitHub backend/frontend/compose jobs also passed.
Local Docker is unavailable; container build/startup has not been verified.
See [the observed validation record](docs/verification/2026-10-03-repository-sync-validation.md)
for exact revisions and evidence. The [2026-09-23 basic record](docs/verification/2026-09-23-phase-1-basic-validation.md)
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

See [contract mappings and differences](docs/external-system-contract.md) for S10's
actual logistics 404 (distinct from S01's successful empty parcels), source timestamp
ownership, typed failures, and idempotency. Fixed seed scenarios have no unknown
statuses or malformed payloads; supplemental unit tests cover those conditions.

## Limitations and next work

No support workflow or send endpoint is exposed. Provider send is a low-level
integration operation; authorization/approval will be implemented before exposure.
There is no automatic retry, cache, partial-result aggregator or freshness policy.
If events fail after shipment retrieval, the operation raises the typed failure,
rather than returning an apparently complete shipment. A parcel without tracking
cannot be queried yet and produces a local ValueError without HTTP.

SQLAlchemy 2, Alembic, psycopg and Argon2id are available for explicit Stage 2 CLI
work. They do not connect a database, authenticate users or implement workflows
when `/health` starts. HTTPX remains the external integration dependency.
React Router and TanStack Query are deferred until there are workflows to route
or fetch. Frontend dependencies are locked in `package-lock.json`; Python uses
bounded dependency ranges and does not yet have a full transitive lock.

## Product database and demo Seed (Stage 2 candidate)

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
one-Approval uniqueness and an optimistic-lock write. If the URL is absent they
visibly skip; skips do not satisfy the Stage 2 exit gate. CI provides disposable
PostgreSQL 17 and runs these tests separately without skips.

Model references and JSON are storage structures; Stage 3–5 services must still
enforce same-Inquiry/team, source schema, Context version, Validation and approval
preconditions in transactions. No record insertion is an authorization grant.
Implementation references: [SQLAlchemy declarative](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html),
[Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html),
[psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).
