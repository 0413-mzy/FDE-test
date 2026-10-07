# Data Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 私有管理员方便浏览当前数据、更新时间和历史修改。

**Architecture:** 使用现有platform资格保护GET-only数据API，服务端固定资源/字段注册。前端统一目录、列表、详情与历史，默认只读且自动刷新关闭。

**Tech Stack:** FastAPI / SQLAlchemy / PostgreSQL / React / TypeScript.

---

### Task 1: Protected read API and meaningful tests
Files: backend/app/commerce/data_center.py, data_router.py, backend/app/main.py, backend/tests/database/test_data_center.py.
- [x] Add failing real PostgreSQL tests: anonymous401, shared roles403, private platform200, forbidden resource404, secret fields absent, parameterized search and filters, current row/history after real business update, deleted baseline reads, max limit, mutation405.
- [x] Run through existing test runtime with isolated schemas; ensure failures arise from missing feature.
- [x] Implement GET /platform/data/access, /platform/data/resources, /platform/data/resources/{resource}, /platform/data/resources/{resource}/{id}, /platform/data/history. Explicit JSON DTOs, read-only transaction after authorize, safe errors/no-store.
- [x] Resources project fixed safe columns from ORM registry; include 36 business table categories plus AI attempts; no auth sessions/secrets/binary/technical request payloads. History uses same field projection.
- [x] Implement ID/text/status/time list filters, bounded offset/limit, stable ordering, qualified relation links. Detail history lookup supports deleted row via historical data.
- [x] Run tests, Ruff/format; update route-inventory test only if it freezes exact routes.

### Task 2: Integrated data UI
Files: frontend/src/DataCenter.tsx, App.tsx, styles.css, frontend/tests/data-center.test.mjs.
- [x] Render private access-gated nav and Chinese resource count catalogue, list search/status/date/pagination, current field detail, related links, global and per-record history with before/after differences.
- [x] Implement timer cleanup, visibility and no-overlap guard; auto refresh defaults off, interval15sec. Success time advances only after success; error visible/retry.
- [x] Add tests for safe read requests/filter encoding and polling behavior; npm test, lint, typecheck/build.

### Task 3: Acceptance and review
- [x] Run actual PostgreSQL/HTTP acceptance on existing local runtime without clearing records; actual mutation and before/after history verified, including API restart persistence.
- [x] Actual browser acceptance: after Codex restart policy verification recovered; local and public private UI verified.
- [x] Independent spec then quality review; fix issues and rerun affected gates.
- [x] Update database/development/README and verification evidence with scope and true history limits; screenshot unavailable because browser acceptance is blocked.
- [x] Commit/push candidate, draft dependent PR, attach PR; never merge main. Public demo release retains Free resources and private platform credentials; report actual release status separately.
