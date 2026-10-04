# Phase 1 Basic Validation Record — 2026-09-23

## Status

**Basic code validation reported as passed. Full Phase 1 integration validation remains incomplete.**

The developer reported running the prescribed local backend and frontend checks on
2026-09-23 with no errors. This record preserves that result without treating it as
independent verification or as proof of the real Sandbox HTTP integration.

## Code baseline

- Phase 1 code commit: `2bfab022f0f7796aabfaa1eaf51978130419d575`
- Working branch during validation: `docs/core-mvp-contracts`
- The working branch adds documentation on top of the Phase 1 code commit; it does
  not change backend or frontend implementation files.

## Reported checks

### Backend

Run from `backend/` in an activated Python 3.12 environment:

```sh
ruff check .
ruff format --check .
APP_ENV=test pytest -m "not integration"
```

Reported result: all commands completed without errors.

### Frontend

Run from `frontend/` after `npm ci`:

```sh
npm run lint
npm run typecheck
npm run build
```

Reported result: all commands completed without errors.

## Evidence boundary

This record is based on the developer's report in the working session. Raw terminal
logs, command exit codes and test counts were not committed to the repository, and
the checks were not independently rerun when this document was written.

Therefore this result supports the statement:

> Phase 1 basic lint, format, non-integration test, type-check and frontend build
> checks were reported as passing locally.

It does not support the statement that full Phase 1 integration is verified.

## Outstanding validation

- [ ] Docker Compose configuration validation
- [ ] Container build and startup
- [ ] Runtime `GET /health` response check
- [ ] GitHub Actions backend, frontend and Compose jobs
- [ ] Real HTTP integration suite against an independent DemoCommerce S0-S1 service
- [ ] Confirmation that the integration suite ran without skips

Until the real HTTP suite passes, use this status:

```text
Phase 1 basic validation complete; real Sandbox HTTP integration unverified.
```
