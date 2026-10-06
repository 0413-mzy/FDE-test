# Commerce Step 3 implementation plan

**Goal:** persistent customer/merchant purchase-and-fulfillment demo and simulation console.
**Architecture:** additive commerce tables, separate sessions, transactional services/API;
React views read the same backend, never browser-only business state.
**Stack:** existing FastAPI/Pydantic/SQLAlchemy/PostgreSQL/Alembic + React/TypeScript/Vite.
**Execution:** superpowers:dispatching-parallel-agents for independent backend/frontend
ownership, TDD and ordered spec/quality reviews. Root owns integration, docs and publication.

## Backend task

Files: backend/app/commerce/*, migrations/versions/0003_commerce.py, migrations/env.py,
app/main.py, tests/database/test_commerce*.py and tests/test_commerce*.py.

- [ ] Failing real-PG migration/seed/identity/catalog tests, then additive implementation.
- [ ] Closed auth/catalog/SKU/inventory/Cart API from docs/commerce/api.md.
- [ ] Failing two-shop checkout/payment/cancel/expiry/last-unit concurrency tests, then services.
- [ ] Failing partial-shipment/tracking/receipt and ownership/replay tests, then services.
- [ ] Enforce current auth, expected versions, original replay payload, stock/amount conservation,
      15-minute expiry and whole-checkout atomicity; PG and Ruff pass with old APIs unchanged.

Seed names: customer.a/customer.b, owner.a/owner.b, staff.a, demo, dual.a. A/B/L/Z SKU
fixtures, entirely fictional; explicit shared demo password. Order.after_sale_cases=[]
until Step 4; no message/refund routes or tables. No edits to frozen 0001/0002 migrations.

## Frontend task

Files: frontend/* only. API from frozen docs/commerce/api.md; no mock fallback.

- [ ] Failing Node built-in client/state tests for error/keys/session handling.
- [ ] Typed client, in-memory Bearer, new-action keys versus safe retry, no localStorage facts.
- [ ] Chinese catalog/customer, merchant owner/staff and narrow demo-console views.
- [ ] Wire Cart/address/checkout/payment; product/SKU/inventory; partial shipment/tracking/expiry/receipt.
- [ ] CNY from minor units, simulation badges, times, loading/empty/error/access states,
      keyboard-accessible responsive forms; lint/typecheck/build/client tests pass.

## Root integration/review/delivery

- [ ] Isolated PostgreSQL and baseline; combined real HTTP tests authored independently.
- [ ] Actual Product/Vite/browser workflows across customer, merchant and demo roles.
- [ ] Two-shop purchase, payments, partial shipment, tracking/receipt; screenshots and stock checks.
- [ ] Full backend/PG and independent Sandbox HTTP regression, frontend checks, Compose CI.
- [ ] Spec review and fixes first, then quality/security review and fixes.
- [ ] Update README/development/API implementation inventory/acceptance evidence honestly.
- [ ] Commit/push/attach draft PR based on Step 2, inspect CI; no main merge or Step 4.

Behavior cycle: write test → observe RED → implement smallest behavior → GREEN → refactor.
Example integration contract:
```python
response = client.post('/api/commerce/v1/customer/checkouts', headers=customer_headers,
                       json={'expected_version': cart['version'], 'address': address})
assert response.status_code == 201
assert len(response.json()['order_ids']) == 2
```
Command: backend `python -m pytest -q` with TEST_DATABASE_URL and --sandbox-url supplied;
frontend `npm test`, `npm run lint`, `npm run typecheck`, `npm run build`.
Skip is not integration acceptance; isolated schema cleanup cannot target existing records.
