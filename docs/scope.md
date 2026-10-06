# Scope freeze

## Current delivery: Product Phase 1 — External Integration Foundation

Phase 0 foundation remains. This explicitly authorized Phase 1 supersedes the
original roadmap's database/seed phase ordering. In scope: canonical typed snapshots,
SystemClock/FixedClock, four Provider protocols, explicit external errors, HTTPX
Sandbox client and adapters, real HTTP integration tests and supporting documentation.

Out of this phase: persistent domain models, migrations, Product seed data,
authentication/authorization flows, Evidence Engine, CaseContext, AI/LLM calls,
drafting, UI changes, RAG, retries, caching, aggregation, conflict resolution,
freshness policy, Sandbox implementation or real logistics/channel integrations.
Simulated reply dispatch is tested only at the Provider boundary; no Product
approval or send endpoint is exposed.

The user authorized Core MVP Stage 1 on 2026-10-03. This delivery is the
[documentation contract package](contracts/README.md), prepared for two-person review;
it selects future interfaces and rules without implementing them. Database/API/Evidence/AI
remain the separately authorized implementation stages in the [execution plan](plans/04_core_mvp_next_stage_plan.md).

## Future Core V1 in scope

The user's 2026-10-04 next-stage request authorizes Stage 3 as a dependent candidate:
backend login/session/logout, current identity checks, permission-filtered Inquiry
list/detail, safe errors/audits and explicit CORS. It depends on Stage 2 database
PR #3, which is now merged with database fixes into main. The 2026-10-06 request
continues PR #5 on that baseline; Stage 3 review/merge gates remain visible. The order route checks access
and reports missing binding/Context; it does not fetch or disclose fresh facts.
No Stage 4 Evidence/Context computation, AI, draft/review workflow, frontend login,
retry/cache or Sandbox implementation belongs to this slice.

- Order-status support consultation for a small/cross-border ecommerce team.
- Authorized order, all-parcel/logistics and warehouse information retrieval.
- Evidence-based explanation with sources, timestamps and explicit uncertainty.
- Structured analysis and reply drafts with deterministic validation.
- Human review/edit/approval and idempotent mock sending.
- Auditability, basic metrics, and tests of failures, missing/conflicting/stale data.

## Explicitly out of Core V1

- Refund execution, cancellation execution, address modification, payment or
  compensation execution. Requests are routed to manual processes, not executed.
- CRM, ERP, inventory forecasting, marketing or a complete ecommerce platform.
- Multi-tenant SaaS, general Agent platforms, generic customer-service chatbots,
  or autonomous customer service.
- Real logistics/carrier and customer-channel integrations in the baseline release.

## Separate external environment

DemoCommerce Sandbox supplies simulated external facts, support messages and
controllable failures over HTTP. It contains no AI and is not this product's
database or a second ecommerce product. Its roadmap is separate from product
phases. Its S0-S1 HTTP service now exists independently and is consumed here.

Any proposed feature must directly improve the defined order-support workflow
and be authorized for the current phase. Otherwise defer it.
