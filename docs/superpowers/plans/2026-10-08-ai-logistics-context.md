# AI Logistics Context Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development with independent spec and quality review.

**Goal:** 现有摘要和建议回复依据授权关联订单的物流事实。
**Architecture:** 服务端安全有界上下文+依赖指纹，传递至每段DeepSeek请求并持久化安全快照；前端展示事实依据与物流陈旧状态。
**Tech Stack:** FastAPI / PostgreSQL / React / DeepSeek HTTP.

## Task 1 Implementation and automated acceptance
- [ ] Add meaningful failing PG tests for linked order ownership, unlinked no cross-search, no PII, logistics-only stale/cache, updates duringproviderI/O, bounded multi-parcel and historical legacy snapshots.
- [ ] Implement focused backend ai_context.py and integrate ai_service/provider snapshots. Optional0011 migration+model metadata and safe data-center fields. Existing source semantics honest for oldattempts; validate newreferencessafely.
- [ ] Update merchant AI panel and source facts/refresh button; existing human-only insert/send remains. Provider HTTP tests inspect payload each chunk andmerge, safe prompt/outputreferences.
- [ ] Run targetPG/HTTP tests, frontendtest/lint/build, Ruff. Spec then quality reviewers inspect final code and fix findings.
## Task 2 Real acceptance and delivery
- [ ] Preserve original local DB with additive migration; prepare fictional linked conversation to existing newtestorder/parcel. Generate actualDeepSeek shortChinese response and inspect facts, no inventedETA, no automatic message send.
- [ ] Change logistics only, verify stale and new snapshot generation. Boundmodelcalls; recordactualusage/results. Browser acceptance if allowed, honest blocker otherwise.
- [ ] Fullbackend regression, docs/links/credentialscan, commit/push and dependent draftPR attach. No publicrelease/mainmerge.
