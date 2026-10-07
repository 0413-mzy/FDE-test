# Commerce history and local database access

2026-10-07: user approved the previously proposed business change history and profile/address version history, explicitly asking to add it to the database and explain access/querying. This implementation uses that approval; no further approval gate is required for routine implementation.

## Decision

Use additive0006 PostgreSQL row triggers on the29 business tables (34 commerce tables minus business_audits, idempotency_records, simulation_events, anonymous_requests, auth_rate_events). Unlike service-only snapshots, triggers cover direct SQL, intermediate flushes and physical cart-line deletion and roll back with business writes. Unlike event sourcing, existing models and APIs remain authoritative. No unrelated frontend/API redesign.

New append-only commerce_record_history stores id(sequence),entity_table,entity_id,operation(BASELINE/INSERT/UPDATE/DELETE),before_data,after_data,changed_fields,actor_id,actor_username,db_role,request_id,action,reason,recorded_at. Strict explicit per-table field allowlists; password hashes, token/code digests, raw request bodies and fingerprints never copied. Credentials changing are indicated only by safe changed-field names. Profile/address/message business content is private developer database data; no anonymous HTTP history reader.

The trigger records every actual row change; no-op updates may be ignored. History is part of the same transaction, ordered by monotonically allocated id (gaps after rollback are normal). recorded_at is actual DB observation time, timestamptz UTC; old business times remain in snapshots and carrier occurred_at remains distinct. Baseline captures existing current state at upgrade, not invented earlier changes. Existing created_at/updated_at/version remain and order snapshots are never rewritten.

Transaction-local context carries authenticated actor and sanitized HTTP action/request identifier. Public auth is anonymous unless identity truly established; direct SQL/seed/migration have identifiable db_role and source, never fabricate customer attribution. Explicit noncredential reasons are bounded; absent reason stays null. Context cannot leak across pooled connections. Do not log credential values while capturing context. DB triggers reject UPDATE/DELETE/TRUNCATE of history in ordinary usage; database owners can deliberately change schema, so no claim of protection against superusers.

Migration frozen SQL with reverse downgrade only for isolated tests. Alembic tables/old migrations stay unchanged. Baselines/history never mutate existing business rows.

## Local inspection

Add scripts/commerce-db.py: explicit --runtime-file or DATABASE_URL, --tables, --describe TABLE, --rows TABLE (bounded limit), --history TABLE --id UUID and --export PATH CSV. Closed read-only operations, parameterized values and validated quoted identifiers, read-only transaction. Credentials/digests excluded from ordinary rows and exports. Never prints connection URL or traceback credentials. Root provides a private local wrapper using the existing runtime pointer, plus real psql commands with read-only transaction and schema configuration. No new public DB listener, GUI install, deployment, AI or main merge.

## Acceptance

Real PostgreSQL: baseline unchanged prior rows; every supported table has trigger; product price old/new; profile/address edits and soft deletion; cart physical deletion and checkout cleanup; order/payment/refund/reviewer transitions; actor and reason context; public/direct SQL attribution; rollback/no-op/duplicate retry; pool context isolation; sensitive values excluded; history immutable; migration roundtrip. Root tests local CLI read/export and validates unchanged old data during live0006 upgrade; restarts original API, rechecks legacy and user data. Relevant backend/frontend/script checks and dependent draftPR follow onboardingPR7; exact-head CI checked before final delivery.
