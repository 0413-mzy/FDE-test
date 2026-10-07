# Commerce Step 4 Implementation Plan

> **For agentic workers:** Follow the frozen commerce-v1 contracts. Use test-driven-development and dispatching-parallel-agents for independent backend/frontend ownership; the coordinator integrates and reviews both.

**Goal:** Connect persistent customer/shop conversations and partial refunds/returns to the existing commerce platform, preserving existing orders.

**Architecture:** Extend the modular monolith and Commerce transaction/auth/idempotency boundary. Add migration 0004 without rewriting deployed migrations. Backend owns quantities, amount, permissions and state; React renders authorized DTOs and uses the existing immutable pending-write client.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, React/TypeScript, Node tests, real Chrome acceptance.

## 1. Backend — independent ownership

- [x] Add failing real PostgreSQL tests in `backend/tests/database/test_commerce_step4.py`: messages, ownership, suspended shops, deduplication; unshipped/return refund lifecycle; windows, version/auth/replays; stock/money/history and atomicity/concurrency.
- [x] Implement new models and additive `backend/migrations/versions/0004_commerce_after_sales.py`; extend commerce inputs/schemas/views/router and small domain modules as needed.
- [x] Implement all 16 remaining frozen routes in `docs/commerce/api.md`, plus REFUND demo queue/result.
- [x] Add authorized shop names to current order reads and new snapshots. Historical stored idempotent responses must still replay exactly; never rewrite old response snapshots with current facts.
- [x] Block shipping on active unshipped cases and receipt/address changes on any active case. Refund amounts use selected immutable line prices, successful totals never exceed paid totals.
- [x] Run new tests RED before implementation, then GREEN, and full backend suite against real PostgreSQL and independent Sandbox HTTP. Ruff lint/format.

## 2. Frontend — independent ownership

- [x] Extend `frontend/src/types.ts`, add `Messages.tsx` and `AfterSales.tsx`, integrate App/Customer/Merchant/Orders/Demo.
- [x] Customer: shop/order conversations, pure-text messages, partial case quantity selection, withdraw/register return. Merchant OWNER: decisions, receive with explicit restock, initiate/retry refund. STAFF: read/message only.
- [x] Display order shop name and explicit manual DEMO payment/refund instructions. Reuse account-scoped pending-write handling, refresh authorized data after mutations and exact retries.
- [x] Add meaningful pure helper/client tests before changing their behavior. Preserve established visual design and mobile layout.
- [x] Run npm test, lint, typecheck and build.

## 3. Coordinator — integration and delivery

- [x] Freeze additive shop_name read DTO field and historical replay compatibility in API docs before implementation.
- [x] Use isolated schemas/services for QA; preserve the user's current runtime orders.
- [x] Review backend and frontend against lifecycle/permissions/contracts, correct material findings, rerun affected tests.
- [x] Extend `scripts/commerce-browser-acceptance.cjs` or add Step4 script to execute messages, partial unshipped refund and delivered return refund through independent customer/merchant/demo browser contexts.
- [x] Verify failure/retry, stock conservation, permissions, persistence, and mobile flow. Save safe screenshots and verification records.
- [x] Update README, scope, architecture, development, acceptance and execution log with actual results and limitations.
- [x] Additively migrate the existing demo schema and restart services only after validation. No reset or user-order modifications.
- [x] Commit/push Step4 branch and create/attach dependent draft PR, then inspect final-head CI. Do not merge main or proceed to Step5.
