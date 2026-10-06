# Data-owner acceptance and Stage 4 readiness plan

> Execution is scoped to acceptance and documentation. Later service implementation
> requires a separate task; do not interpret the original roadmap as permission.

**Goal:** Independently check merged Stage 3 and give the application owner a precise
Stage 4 scenario/quality handoff without adding runtime behavior.

**Architecture:** Review the Stage 3 diff against its frozen slice; rerun existing
tests on an isolated PostgreSQL instance. Convert accepted contracts and observed
Provider coverage into explicitly pending Stage 4 acceptance requirements.

**Tech Stack:** Python 3.12, pytest/Ruff, PostgreSQL 17, Markdown, GitHub PR/checks.

## Work checklist

- [x] Pin main `8469971982a82369c94ab9387ab73d55f6caf6a6` and review base `58aac36`.
- [x] Read repository authority documents and frozen Stage 3/Context contracts.
- [x] Run separate read-only Standards and Spec reviews; record their findings separately.
- [x] Rerun backend and real PostgreSQL suites; distinguish failed execution attempts,
  selected tests, external HTTP tests not rerun, and CI observations.
- [x] Write `docs/verification/2026-10-06-stage-3-independent-acceptance.md`.
- [x] Write `docs/testing/2026-10-06-stage-4-scenario-coverage.md` with source-level
  coverage versus unimplemented resolver behavior and supplementary fixtures.
- [x] Write `docs/testing/2026-10-06-evidence-case-context-acceptance.md` with quality,
  provenance, authorization, versioning and failure exit criteria.
- [x] Link handoff documents from README; validate links and diff whitespace.
- [x] Stop the disposable PostgreSQL instance and record remaining limitations.
- [x] Commit/push a `codex/` documentation branch and open a PR to main; do not merge.
  Published as [PR #7](https://github.com/Mark-UM/FDE-test/pull/7).

## Boundaries

Do not modify migrations, runtime APIs, AI/Provider behavior, shared Sandbox,
production data, PR #4 or branch protection. If a real Stage 3 defect appears,
record it before considering a tested fix. AI review is not two-human sign-off.
