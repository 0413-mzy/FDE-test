# Commerce History Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development and dispatching-parallel-agents for independent backend history and local database inspection tasks. No concurrent editing of shared files. User explicitly approved execution.

**Goal:** Persist actual business changes with times, attribution and safe before/after snapshots; let the user inspect the existing local DB.

**Architecture:** One additive frozen PostgreSQL migration and row-level trigger recorder; service transaction context; independent read-only CLI. Existing business tables/APIs keep contracts.

**Tech Stack:** PostgreSQL17, Alembic, SQLAlchemy, FastAPI, Python argparse/csv.

## Backend (one isolated owner)
- [x] Create backend/tests/database/test_commerce_history.py with failing realPG tests: query commerce_record_history after two product updates and cart-line delete, assert old/new and timestamps; roll back insert and assert no history committed; replay same API idempotency key and assert unchanged history count.
- [x] Add backend/app/commerce/history.py with RecordHistory mapping, explicit field policy and set_context(db,actor,request,reason=None). Context uses SELECT set_config(:name,:value,true), bound scalar strings and no request body/credential capture.
- [x] Add frozen backend/migrations/versions/0006_commerce_history.py: table/indexes, safe trigger function,29 per-table triggers, baseline SELECT and history immutability triggers. Original migrations unchanged; downgrade only reverses new objects.
- [x] Wire backend/app/commerce/service.py and commerce/router.py,onboarding_router.py for pre-write context and authenticated actor after authorization under mutex. Baseline/seed/direct SQL identified separately. Reasons only bounded noncredential fields.
- [x] Verify actual SQL rollback/DELETE/credential redaction/default edit/payment/refund states, record metadata, no-op and pooled context isolation. Ruff and all database -m 'not integration' plus nonDB regression pass with no skipped acceptance.

## Local inspection (root owner)
- [x] Write scripts/commerce-db.py with argparse mutually-exclusive actions --tables/--describe/--rows/--history; --runtime-file reads private URL internally; values bound and only existing validated table identifiers used.
- [x] SELECT queries run in read-only transaction, count/bounded pagination, ordered id; ordinary rows/export omit known password/token/fingerprint fields. --history requires commerce business entity and optional UUID. CSV export uses exclusive local output creation; no secret URL stdout.
- [x] Meaningful tests assert invalid table/UUID/limit reject; local actualPG queries show new history and never mutate business rows; CLI credential output redacted and CSV source matches.
- [x] Add docs/database.md exact current local wrapper invocation, psql connection params without secrets, \dt/\d and SELECT product/order/history examples, UTC→Malaysia conversion and read-only transaction. Add relevant doc/AGENTS authorization/status links; no fabricated past history.

## Acceptance and delivery (root)
- [x] Spec compliance review followed by quality/security review; fix reported defects.
- [x] Snapshot all existing business rows in original runtime, additive upgrade0006, compare unchanged; identify baseline separately and keep user's registered accounts/data.
- [x] Restart original detached API only, keep Vite/schema/mailbox and verify realbrowser/catalog/login and authorized API GETs. Meaningful freshschema change→history→API restart acceptance.
- [x] Validate links/whitespace, backend/script Ruff, frontend lint/typecheck/build; record exact executed results and externalHTTP scope.
- [x] Create dependent [Draft PR #8](https://github.com/0413-mzy/FDE-test/pull/8) on codex/commerce-user-merchant-onboarding and attach artifact; no main merge/public deployment/next business category.
- Delivery gate: verify exact HEAD CI before final response and record its run URLs/results in the PR description. The PR checks carry current status.
