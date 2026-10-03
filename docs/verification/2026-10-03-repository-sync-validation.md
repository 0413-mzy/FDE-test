# Repository Sync and Observed Validation — 2026-10-03

Date uses Asia/Shanghai. This record supersedes the current-status conclusion of
the historical 2026-09-23 basic validation report; that report remains unchanged.

## Remote synchronization

- Product remote: `https://github.com/Mark-UM/FDE-test.git`.
- Starting branch `phase-1-external-integration` at `2bfab02` was clean and had no
  incoming commits after `git fetch origin --prune`.
- `main` is `33857e2ac42472c690d583fc50e670d994f6a436`, containing Phase 1 through
  [merged PR #1](https://github.com/Mark-UM/FDE-test/pull/1).
- `docs/core-mvp-contracts` has three documentation commits after Phase 1, ending at
  `0d04cfcdcf65c79b10e27e18866c10c6856b547b`. Checked it out as a local tracking branch
  and ran `git pull --ff-only origin docs/core-mvp-contracts` (already up to date).
- The planning branch's backend, frontend, CI, Compose and environment template
  are identical to fetched `origin/main`; its planning docs have not entered main.
- Sandbox remote: `https://github.com/Mark-UM/demo-commerce-sandbox.git`; local main
  and fetched origin/main both equal `4131f1c4be7af6a6981e15379214d238228e8fa2`.
  Its worktree is clean. The prior statement that S0-S1 files were uncommitted is historical.
- No merge, rebase, commit, push, PR creation or repository-policy change was performed.

## Observed checks

Local Python is 3.13.13; Node is 22.22.1. Commands were run on the tracked planning
branch with unchanged implementation files, not inferred from a previous report.

| Check | Command / observation | Result |
| --- | --- | --- |
| Backend lint | `python -m ruff check --no-cache .` | All checks passed |
| Backend format | `python -m ruff format --no-cache --check .` | 20 files already formatted |
| Full backend tests | `python -m pytest -q -p no:cacheprovider --sandbox-url http://127.0.0.1:19003` | **70 passed in 1.36s**, no skips/warnings; 13 real HTTP tests |
| Frontend lint | `npm run lint` | Exit 0 |
| Frontend TypeScript | `npm run typecheck` | Exit 0 |
| Frontend build | `npm run build` | Exit 0; Vite 7.3.6, 28 modules transformed |
| Product runtime | Uvicorn on loopback port 18003; actual `GET /health` | HTTP 200 with expected service/status |
| Local Compose | `docker compose --env-file .env.example config --quiet` attempted | Docker unavailable; no local result asserted |

Sandbox was launched as an independent Uvicorn process from its own checkout on
loopback port 19003, using a new temporary `SANDBOX_DB_PATH` and disabled bytecode
writes. Product tests only used HTTP; they did not import Sandbox or read its DB.
FixedClock used `2026-09-20T06:00:00Z`. Idempotency test writes were isolated from the
existing Sandbox database. Product startup used port 18003. Both processes were
stopped after validation.

Observed runtime response:

```json
{"status":"ok","service":"ecommerce-order-support-backend"}
```

## GitHub evidence

Read via `gh pr list`, `gh run list`, `gh run view 35831745007`, and repository APIs.
[Product checks run 35831745007](https://github.com/Mark-UM/FDE-test/actions/runs/35831745007)
completed successfully for main SHA `33857e2ac42472c690d583fc50e670d994f6a436`:

- `backend`: Python 3.12 install, Ruff lint/format and `pytest -m "not integration"` passed.
- `frontend`: npm ci, lint, typecheck and build passed.
- `compose`: `docker compose --env-file .env.example config --quiet` passed.

This remote run does not exercise real HTTP integration or build/start containers.
It validates the existing main baseline, not the newly edited local planning docs.
The new integration result above is local evidence against the identified Sandbox revision.

`gh api repos/Mark-UM/FDE-test/branches/main/protection` returned HTTP 404
(`Branch not protected`). `gh api repos/Mark-UM/FDE-test/rules/branches/main`
returned `[]`. No effective protection was observed, though the workflow requires it.

## Remaining gates

- Configure reviewed PRs and required backend/frontend/compose checks on main.
- Verify container build/startup in an environment with Docker.
- Merge the reviewed collaboration/contracts documentation through a PR.
- Freeze actual Core MVP contracts before database/API/Evidence/AI implementation.

Phase 1's existing code and real HTTP boundary passed the checks above; Core MVP
and production readiness remain future work. Remote CI availability does not turn
contract proposals or unavailable runtime checks into completed deliveries.
