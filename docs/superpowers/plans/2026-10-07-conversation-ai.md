# Conversation AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement the single cohesive feature task; use test-driven-development and obtain independent specification and quality reviews.

**Goal:** Let authorized merchants manually generate a brief Chinese conversation summary and an editable suggested reply with DeepSeek.

**Architecture:** An isolated merchant API takes a server-authorized immutable message snapshot, records a bounded generation lease, releases database locks before HTTP calls, validates structured model output, then rechecks authorization and persists results and usage. Existing message sending remains the only sending mechanism. Additive migration 0009 preserves prior records. A merchant-only card shows coverage, age, stale state, failures and a button to insert a draft.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic/PostgreSQL, httpx, Pydantic, React/TypeScript, pytest and frontend tests.

## Task 1 — Implement the complete vertical slice

File responsibilities: new `backend/app/commerce/ai_provider.py` owns redaction, chunking, DeepSeek JSON protocol and output validation; new `ai_models.py`, `ai_service.py`, `ai_router.py` own generation storage, leases, authorization and HTTP contract. Add `backend/migrations/versions/0009_conversation_ai.py`, import models in migration metadata, add secret settings in `backend/app/core/config.py`, and mount the router in the existing app. `frontend/src/ConversationAI.tsx` owns the card; `Messages.tsx` inserts drafts into the existing editor and refreshes stale status. New dedicated backend/provider/database and frontend tests own acceptance. Update route inventory expectations where necessary, without weakening authorization checks.

- [x] Write meaningful failing tests first for authorized generation, customer/other-shop denial, missing key, replay/cache, pending lease, stale state and failure preservation; run them to confirm the feature is absent.
- [x] Implement GET and POST `/api/commerce/v1/merchant/shops/{shop}/conversations/{conversation}/ai-assistance`. POST accepts an empty body and the existing idempotency header. GET returns availability, latest successful result, latest attempt and stale state. Never accept caller-supplied messages or model instructions.
- [x] Store request ID/key, snapshot hash and source message IDs/count, actor, state/times, model/prompt version, summary fields, draft, safe errors and actual token usage. Unique request replay and one active generation per conversation; bounded persistent account/global rate checks. Expired leases allow recovery. Recheck permissions after the external call and before returning cached content.
- [x] Use configurable `deepseek-flash` with `thinking.type=disabled`, official HTTPS endpoint, JSON-object response, finite timeouts/output limits and no automatic retries after uncertain billing. All snapshot messages must be covered through chunk summaries; reject oversized conversations explicitly. Validate lengths and source references, redact recognizable secrets/contact details, and never log raw requests/responses or credentials.
- [x] Write independent real HTTP-server protocol tests for success, malformed/empty JSON, errors, redaction and long conversations. Record usage from completed partial chunk calls even if a later call fails.
- [x] Add a merchant-only card with concise Chinese fields, DeepSeek processing notice, generated time/coverage, stale/failure/pending status, manual generate/update and insert draft. Preserve the editable input and explicit existing Send button.
- [x] Run focused tests, then backend Ruff/pytest, real PostgreSQL isolated-schema tests and frontend tests/lint/type/build. Preserve original runtime database until migration acceptance passes.

## Task 2 — Review, real-provider acceptance and delivery

- [x] Obtain a separate specification review and address gaps, then obtain independent code-quality/security review and address findings.
- [x] Test the actual supplied credential using only fictional conversation content and protected local configuration. Report authentication/balance/network failures honestly; never replace them with mocked success.
- [x] Run browser acceptance for merchant generation, editable draft, explicit sending, new-message stale marking and cross-shop/customer isolation. Verify additive migration leaves existing rows intact.
- [x] Document configuration, provider limitations, privacy scope, database contents and exact fresh verification commands/results in README/development/verification docs; record current narrow AI authorization in AGENTS/scope.
- [ ] Commit and push `codex/commerce-conversation-ai`, create and attach a dependent draft PR against `codex/commerce-public-demo-deployment`, verify CI. Do not merge main.
- [ ] Configure and publish only to the existing free Render/Neon deployment after required credential-destination authorization. Verify deployed commit, readiness and real persisted result. If credential verification or deployment is blocked, deliver the tested code/PR and state the specific remaining gate.
