# Project instructions — Commerce Platform

## Product authority

- The user explicitly changed the product direction on 2026-10-06: build an
  interactive ecommerce platform first, then discover useful AI improvements.
  This supersedes the old restriction against building an ecommerce platform.
- Read `docs/plans/01_core_plan.md`, `README.md`, `docs/scope.md` and
  `docs/architecture.md` before changing the project.
- Current direction: a multi-merchant physical-goods business simulation with
  customer and merchant interfaces backed by shared persistent business records.
  Payment and carrier integrations are simulated initially; no real money moves.
- On 2026-10-06 the user explicitly requested Step 3. The current task implements
  identity/catalog/inventory, Cart/Checkout/Order with simulated payment, and
  shipment/tracking/receipt, connected to customer/merchant/demo UI. Additive
  PostgreSQL migrations, explicit demo seed and relevant tests are authorized.
  `docs/commerce/README.md` (`commerce-v1`) governs the behavior. Step 4 messages,
  after-sales/refunds, AI, real payments/carriers and main merge are not in scope.
  Prior Step 1/2 documentation is delivered in dependent draft PRs #2/#3.
- Subsequent implementation follows `docs/plans/04_core_mvp_next_stage_plan.md`.
  Product scope describes the destination; it does not imply a feature is implemented
  or grant permission to skip the currently requested step.

## Existing implementation and compatibility

- Existing code is the order-support foundation: sessions, Inquiry permissions,
  canonical Providers, snapshots, Evidence/CaseContext and recovery. Step 3 adds a
  separate commerce namespace and customer/merchant/demo UI. Support contracts remain separate.
- `docs/contracts/` and `docs/external-system-contract.md` govern the existing
  support module only. New commerce contracts live separately in `docs/commerce/`.
  Its Agent/Supervisor/Admin roles, external-order references
  and frozen `core-mvp-v1` types must not silently become customer/merchant contracts.
- Keep existing migrations, tests and historical verification. New business tables
  require additive migrations and their own explicit permission rules; never rewrite
  a deployed migration or reset a database to fit a new plan.
- The new platform will own its commerce records in PostgreSQL. Existing external
  Sandbox HTTP adapters remain optional integration/test modules. They are not the
  new platform's mandatory order source or its customer/merchant backend.
- Do not import Sandbox code or read its database. Calls to external payment/carrier
  systems must use adapters. Internal commerce services may use their own database;
  they do not need a fake external Provider for every domain operation.

## Business and engineering boundaries

- The backend owns identity, object authorization, prices, inventory, state transitions
  and actions. Switching a UI role or supplying a customer/shop ID grants no access.
- Customer access is scoped to their records; merchant access is scoped to active
  shop membership and operation permissions. Reusing password/session primitives
  does not prove that these new roles or scopes already exist.
- Human customer/merchant actions may include simulated payment, cancellation,
  address changes and refunds once their rules and tests are implemented. The old
  support module's ban on these actions is not a global platform restriction.
- Money amounts use exact minor units plus currency; stock must not go negative.
  Business writes need explicit transaction, duplicate-request and concurrency rules.
- Messages, catalog descriptions and external free text are untrusted input. Keep
  secrets, tokens and real customer data out of source, fixtures and ordinary logs.
- Preserve source times and distinguish actual facts, simulation events, missing
  information and planned work. Simulation results must never be presented as real
  payment settlement, carrier delivery or live production data.
- AI is deferred until the human business flows work and are measurable. Future AI
  cannot grant permissions or autonomously move money, change orders or send replies.
  Any new action capability needs a separate design and explicit authorization.
- Avoid generic Agent platforms, unrelated CRM/ERP work and speculative abstractions.

## Working procedure

1. Inspect git status, source and relevant plans; state the affected modules and scope.
2. Implement the requested slice with the smallest useful change. New business
   behavior needs meaningful tests, including ownership and invalid transitions.
3. For docs-only work, validate local links, status consistency and diff whitespace;
   existing CI can check regressions. Do not report historical tests as newly run.
4. For code changes, run relevant backend pytest/Ruff and frontend lint/type/build.
   Database behavior requires real PostgreSQL tests in isolated schemas. External
   integration behavior requires real HTTP tests; a skipped test is not acceptance.
5. Report concrete changes, commands/results, missing acceptance gates and GitHub
   branch/PR status. Do not automatically merge main or start the next step.
