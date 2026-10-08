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
  `docs/commerce/README.md` (`commerce-v1`) governs the behavior.
  On 2026-10-07 the user authorized Step 4: persistent customer/shop conversations,
  unshipped refunds and delivered-item returns/refunds, merchant review and narrow
  simulated refund results, associated money/inventory/state invariants, and UI.
  Additive migration 0004 and real database/browser acceptance are authorized;
  preserve existing orders. Also clarify shop names and manual simulated payments.
  On 2026-10-07 the user then explicitly authorized Step 5: scenario coverage,
  isolated reproducible demos, exception/retry/concurrency regressions and recovery
  usability. Preserve existing orders; deployment is deferred until afterwards.
  After Step 5 the user authorized the user/merchant onboarding category: registration,
  password recovery, merchant application/review, profiles and address books. The user
  selected local simulated email on 2026-10-07; real email is deferred until deployment.
  An additive 0005 migration, protected local mailbox and narrow independent reviewer
  seed/UI are authorized; preserve existing accounts, orders and inventory.
  On 2026-10-07 the user authorized supplementing business record history and local
  database inspection: additive 0006, transaction-atomic before/after snapshots,
  actor/request/source/reason/time and profile/address versions. Preserve all
  existing records; initialize honest current-state baselines, never invent past
  values or copy passwords/tokens/codes. Developer inspection remains local.
  On 2026-10-07 the user authorized completing catalog/shopping experience and
  platform operations: product images/categories/search/filter/favorites/reviews;
  independent platform management/moderation/disputes/arbitration/analytics.
  Additive0007/0008, safe image decoding, new-role explicit seed, transactional
  history and real PostgreSQL/browser acceptance are authorized. Preserve current
  business rows; no old account promotion or deployed migration rewrite.
  On 2026-10-07 the user authorized public demo deployment with RMB100/month maximum.
  The user subsequently declined paid creation and explicitly approved Render Free
  + Neon Free, including storing the new cloud database credential in Render.
  Do not add payment methods or paid resources; accept suspension at free limits.
  Explicit production public-demo configuration, independent cloud PostgreSQL,
  simulated transactions, disabled public mail/account mutations, separate private
  operator credentials, production container and HTTPS publishing are authorized.
  Preserve the existing local database; account signup/agreements and payment
  details are completed by the user. No real payments/carriers, AI or main merge.
  Prior Step 1/2 documentation is delivered in dependent draft PRs #2/#3.
- Subsequent implementation follows `docs/plans/04_core_mvp_next_stage_plan.md`.
  Product scope describes the destination; it does not imply a feature is implemented
  or grant permission to skip the currently requested step.

## 2026-10-07 approved private data center

The user approved a private, read-only database frontend with optional 15-second
refresh, current records, search/filters, related records and before/after history.
Use existing private platform authority; shared visitor accounts gain no access.
All queries use explicit table/field allowlists, safe history projections and bounded
pagination. Do not expose authentication material, database credentials or binary
image payloads. Keep old migrations/business rows unchanged. AI attempts have their
own attempt lifecycle, not full row-version history. Browser and real PostgreSQL
acceptance are required; report blocked browser checks honestly. No main merge,
paid resources or changes to private credentials.

## Existing implementation and compatibility

- On 2026-10-07 the user approved the narrow AI conversation assistance design and
  explicitly requested implementation. DeepSeek may process authorized conversation
  message snapshots to produce brief Chinese summaries and suggested reply drafts.
  Additive migration 0009, generation/usage records, merchant-only UI and relevant
  real PostgreSQL/HTTP/provider/browser acceptance are authorized. Replies require
  human editing and explicit sending through the existing message flow; AI cannot
  change orders, money or permissions. This supersedes earlier AI deferral only for
  this slice. AI monthly budget is uncapped; Render/Neon remain free-only. Credentials
  stay in private backend environment configuration, never Git or frontend bundles.

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

## 2026-10-08 approved logistics scenario controls

The user approved demo-controlled manual collection/transit/dispatch/signature, transport
delay and delivery failure recovery, delayed reports and duplicate event replay. Additive
0010 and transaction-safe history, customer/merchant shared timeline, and real PostgreSQL/
HTTP/browser acceptance are authorized. Preserve old orders and events; no reset or
invented past actor/location/reason. Carrier delivery stays separate from customer
receipt. No real carrier API, automatic progression, public release or main merge in
this slice; use a dependent draft PR.

## 2026-10-08 approved AI logistics context

The user approved merchant conversation assistance reading its explicitly linked
order logistics. Validate order/shop/customer ownership; whitelist bounded status
and tracking facts, never addresses, phone numbers, full tracking identifiers or
credentials. Bind cache/staleness to both messages and logistics. Treat carrier
text as untrusted; distinguish simulation, missing ETA and customer claims.
Safe AI context metadata migration0011 and fictional bounded real DeepSeek
acceptance are authorized; preserve prior attempts/business rows. Manual draft
insert/send remains unchanged. No public release, main merge, automatic reply
or business action in this slice.

On 2026-10-08 the user subsequently explicitly requested publishing the current
experiment progress. This authorizes deploying logistics controls and AI logistics
context to the existing Render Free/Neon Free public demo, preserving cloud data,
private credentials and human-only replies. No main merge or paid resource upgrade.
