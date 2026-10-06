# Architecture — Product Phase 1 integration foundation

The product authority is [the Core plan](plans/01_core_plan.md). The
[environment plan](plans/03_ecommerce_environment_plan.md) describes an external
test system only. The canonical pipeline below is still a future target. The
explicitly authorized Product Phase 1 adds external integration only, overriding
the old roadmap's Phase 1 database/seed ordering without changing product scope.

Planning synchronized on 2026-10-03: Phase 1 is already in main. Core MVP Stage 1
now delivers [six contracts](contracts/README.md), prepared for human review before database/API/Evidence/AI work.
See [the current execution plan](plans/04_core_mvp_next_stage_plan.md) for dependency
order, responsibilities and acceptance gates; no new business modules are implemented
by that planning update.

## Canonical future pipeline

```text
Inquiry
→ Permission (authentication and order/inquiry authorization)
→ Providers (order, all parcels/logistics, warehouse notes)
→ Normalization
→ Evidence
→ CaseContext
→ LLM structured analysis
→ Validation
→ Human Review
→ MessageProvider
→ Audit / Metrics
```

## Responsibility boundaries

| Component | Owns | Boundary |
| --- | --- | --- |
| UI | Interaction, source/freshness display, draft editing and review | No external business-system calls or authorization decisions |
| Backend | Identity, authorization, orchestration, deterministic rules, freshness and actions | Check access before retrieving/disclosing facts or forming CaseContext |
| Providers | External-system boundaries and transport/error mapping | Return normalized facts with provenance; no implicit policy authority |
| Normalization | Source-field mapping, identifiers, timestamps, complete parcel association | Missing or unknown values remain explicit; do not invent facts |
| Evidence | Traceable facts with source system, record identity and timestamps | Separate facts, plans, uncertainty, conflicts and missing data |
| CaseContext | Minimum authorized evidence for one inquiry | The only business context supplied to AI |
| AI | Interpretation, summarization and wording | No database writes, permissions, freshness decisions or action execution |
| Validation | Schema, evidence references, freshness, risk and unsupported-claim checks | Prevent unsupported or unsafe outputs from flowing forward; fail to human handling |
| Human Review | Final approval of the actual reply text in Core V1 | Edits remain subject to deterministic validation; approval is not permission for high-risk actions |
| MessageProvider | Idempotent dispatch after backend-approved human review | Core V1 uses MockMessageProvider; no real channel send |
| Audit / Metrics | Sources, changes, approvals, send outcome, failures and processing time | Record failed paths as well as success; avoid sensitive payloads in ordinary logs |

**Program owns facts. AI owns interpretation and wording.** Prompts are not
security controls. Warehouse notes and customer messages remain untrusted text,
even when they contain instructions. High-risk actions are not executable in Core V1.

## External systems and data ownership

OrderProvider, LogisticsProvider, WarehouseProvider and MessageProvider now exist
as narrow async protocols. LLMProvider does not exist in this phase. Future product
services must depend on protocols rather than Sandbox payloads. Product PostgreSQL will hold workflow
state; Sandbox SQLite will hold external simulated commerce state. Product code
must not query or share Sandbox database tables.

The original Core baseline is Mock Providers. This phase explicitly adds HTTPX
Sandbox adapters for the implemented S0-S1 service. Its raw schemas and routes
are authoritative for transport; [the canonical contract](external-system-contract.md)
governs returned Product models. Sandbox implementation stays in a separate repository.

```text
DemoCommerce HTTP JSON
→ SandboxClient (timeout, request ID, status mapping, raw schema validation)
→ Sandbox Provider adapter (explicit names, identity checks, source provenance)
→ canonical Product snapshot
```

`app/integrations/models.py` has no HTTP routes or raw Sandbox names. Raw Pydantic
schemas stay inside `integrations/sandbox/`; they never become Product return types.
OrderProvider owns order and parcel discovery. LogisticsProvider accepts one canonical
parcel and reads shipment/events from that source only. It cannot silently discard a
failed parcel. WarehouseProvider and MessageProvider operate independently. No
cross-provider collector, evidence creation or conflict resolution is implemented.

The client assigns an injected Clock's UTC time after each successful HTTP response.
Snapshots preserve nullable source updates; events keep their own fetch timestamp
and event ID provenance. Support inquiries/receipts follow their existing canonical
contract; receipt `sent_at` is source-owned and is never replaced by the Product clock.
SystemClock serves runtime use; FixedClock pins tests to the Sandbox seed reference.

ExternalNotFound, ExternalTimeout, ExternalUnavailable, ExternalInvalidResponse,
ExternalConflict and ExternalRejected retain service, operation, request ID, HTTP
status and source error code. They do not expose raw payload text. HTTP failures
remain failures even if their error body is malformed. Redirects are not followed,
environment proxies are disabled, and no retries or caching are implemented.

Fetching an old record now does not make its business facts current. Application
code will determine freshness from original timestamps and explicit cache/failure
metadata; a cache read must retain its original `fetched_at`. Unknown source update
times remain unknown. Source failure, empty results and partial results are distinct;
a logistics timeout is not proof of a parcel exception. All parcels must be accounted
for before an order-wide statement is made. Runtime freshness behavior is deferred;
the [Stage 1 contract](contracts/evidence-case-context.md) selects versioned default thresholds.
Retries remain outside the Core MVP implementation slice.

## Runtime foundation today

The user authorized Stage 3 on 2026-10-04 and self-review/merge on 2026-10-06. This delivery
implements login/me/logout and permission-scoped Inquiry list/detail through
`api/core.py` and `services/core_access.py`. Connections are lazy, sessions store
only token digests, and reads lock current User → AuthSession → Inquiry in the
same transaction. Failed login and access denial retain safe audit records; SQL
or input text never reaches public errors. Authentication precedes manual closed
request validation. Explicit CORS origins gate browser access. The order route
returns binding/Context precondition errors and performs no Provider calls.
See [the frozen implementation slice](contracts/stage-3-implementation.md).

- FastAPI + Pydantic v2 exposes a deterministic, dependency-independent `/health`.
- Pydantic Settings reads root `.env` and process variables (`APP_ENV`, `DATABASE_URL`,
  `SANDBOX_BASE_URL`, `SANDBOX_TIMEOUT_SECONDS`).
  The URL is masked in representations and is not used to connect in Phase 0.
- React + TypeScript + Vite renders only a static title/status page.
- Development Compose provides backend, frontend and PostgreSQL. Backend startup
  waits for the PostgreSQL container health check, but `/health` never queries it.
- Pytest, Ruff, ESLint, TypeScript, Vite build and Compose config validation form CI.

No Evidence Engine, CaseContext resolver, LLM integration or connected support
workbench is present. Stage 2 static UI remains a separate candidate. No Product send API is added;
SandboxMessageProvider only verifies the simulated external boundary and does not
decide approval. Authorization and approval are required before future exposure.
Stage 2 database PR #3 and fixes PR #6 are merged into main as of 2026-10-06:
persistence dependencies, twelve workflow tables, frozen migration 0001,
incremental nonblank-constraint migration 0002 and demo Seed CLI are implemented.
Stage 3 now uses these
records for sessions and authorized Inquiry reads without startup connections or
workflow mutations. Six historical tables reject UPDATE/DELETE with PostgreSQL
triggers; future Context/draft version relationships remain later service work.
`postgresql+psycopg` remains
the explicit connection convention.
