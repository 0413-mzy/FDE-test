# Stage 4 validation record

Date: 2026-10-06, Asia/Kuala_Lumpur. User authorized the next stage and delegated
routine implementation choices. Feature branch: codex/core-evidence-context.
Baseline main: 8469971982a82369c94ab9387ab73d55f6caf6a6.
Contracts: core-mvp-v1; core-policy-v1 / freshness-v1.

## Baseline observed in this execution

- Updated clean local main by fast-forward from 58aac36 to 8469971; created feature branch.
- 103 existing non-database/non-integration backend tests passed.
- 91 existing real PostgreSQL tests passed, no skips.
- 13 existing independent Sandbox HTTP tests passed, no skips.
- Frontend lint, typecheck and build passed (28 modules).

The PostgreSQL 17 instance is newly initialized under a task-specific temporary
directory, uses a task-specific test role/database and Unix socket, port 55439,
listen_addresses empty. Per-test fde_test_<uuid> schemas are isolated and cleaned by
the existing fixture. No existing database is read/reset and no system service is
registered. The independent Sandbox is a temporary clone of
4131f1c4be7af6a6981e15379214d238228e8fa2, bound to 127.0.0.1:19005 with a new temporary
SQLite path. Product uses HTTP only, never imports Sandbox code or reads its database.

## Implementation checks and regression evidence

Task 1: 50 pure Context/collection tests passed plus 11 new real Sandbox HTTP
collector/builder scenarios. Contract review and subsequent code-quality review
completed by separate AI reviewers; this is not independent human approval.

Failing-first regression evidence included overwritten fetched_at, misclassified
inquiry format failure, scalar returned for an array operation, foreign fetch target,
duplicate Evidence partition reference, equivalent-instant structured event conflict,
and invalid canonical quantity type. Each received an observed RED before the final
GREEN implementation. Six Product fixture disclosures and references are checked;
these fixtures are not represented as live Sandbox captures.

The new full Product transaction + Sandbox HTTP test initially failed with 404 vs
expected 201 because resolve-context did not exist. It is maintained separately from
the pure collector tests. A real historical Context read then exposed strict JSON-vs-Python timestamp
validation (HTTP 500); saved payload validation was corrected and regression tested.

Task 2 contract and final code-quality reviews approved the implementation after
adding rejected-request audit coverage. Reviews are AI self-review, not developer
approval. Coverage includes concurrent replay, stale locks, authorization/binding
changes during HTTP, historical association, atomic rollback and targeted recovery.

Final local verification:

- `pytest -q --sandbox-url http://127.0.0.1:19005 -p no:cacheprovider`, with the
  disposable `TEST_DATABASE_URL`: **316 passed, no skips**, 79.12 seconds. One pre-existing Starlette/httpx
  deprecation warning remains.
- Separate database regression: 121 passed, 11 combined integration tests deselected.
- Separate non-database regression: 184 passed, 132 database tests deselected.
- `ruff check .` passed; `ruff format --check .` passed (51 files).
- `npm run lint`, `npm run typecheck`, `npm run build` passed.
- `git diff --check` and repository-local documentation link checks passed.

An additional smoke script ran Product Uvicorn on a real socket with PostgreSQL
and default HTTP Sandbox adapters: scenarios 2/4/11 succeeded, 8/9 were partial,
12 failed safely; health, login/logout, Context/order reads and idempotent replay
passed. Its isolated schema and Product process were cleaned after execution.
No credentials or customer data were saved in repository files.

Feature branch published to `0413-mzy/FDE-test`; draft
[PR #1](https://github.com/0413-mzy/FDE-test/pull/1) created and attached to the chat.
[CI for implementation commit 18da35c](https://github.com/0413-mzy/FDE-test/actions/runs/37463063888)
has passed backend, frontend and Compose configuration jobs; database job is still
running at this document update. CI excludes optional independent Sandbox tests;
those were executed locally through real HTTP above. Local Docker is unavailable.
The temporary Sandbox and PostgreSQL processes were stopped after validation.

## Scope and remaining gates

No AI, drafting, approval/send, cache/retry, frontend work or Sandbox expansion.
Full Compose container build/start and browser end-to-end workflows are separate
unverified gates; config validation alone cannot prove them. The static workbench
and readiness-document PRs remain separate upstream deliveries.
