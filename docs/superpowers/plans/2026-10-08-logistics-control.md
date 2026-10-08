# Logistics Control Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for implementation and independent spec/quality review.

**Goal:** demo账号手动推进可追溯的物流场景。
**Architecture:** 扩展现有Shipment/TrackingEvent及事务与幂等控制；新增安全的demo包裹读取，前端独立物流控制组件复用现有客户端。
**Tech Stack:** PostgreSQL / FastAPI / React / TypeScript.

## Task 1 Backend and frontend slice
- [x] Real PostgreSQL failing regression for stages/ownership/late facts/idempotency/concurrency; run `python /private/tmp/fde-shopping-target.py tests/database/test_logistics_control.py -q`.
- [x] Add migration0010 and model fields; create focused logistics transition module. Keep existing commerce transaction/idempotency wrapper. Extend safe projections and demo read routes; update frozen metadata inventory and old acceptance flows for new valid stages.
- [x] Add focused LogisticsControl UI and helper tests: only current-state actions; event time defaults at submit; repeat identical payload; translated timeline in customer/merchant; all/delivered package selection.
- [x] Run real database suite, Ruff, frontend test/lint/build. Independent spec then quality review and repair findings.
## Task 2 Acceptance and delivery
- [x] Migrate existing local DB additively, preserve prior row counts. New fictional test order/parcel only. Verify normal/exception/late/duplicate through real HTTP; restart persistence and atomic history verified.
- [ ] Browser clicks/screenshots: administrator-policy verification unavailable; no workaround.
- [x] Document scene control usage and exact test results; commit/push draft dependent PR, attach. No main merge or public release in this slice.
