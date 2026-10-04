# Coding instructions

This project solves only small/cross-border ecommerce order-support consultation.
Do not expand it into generic SaaS, an Agent platform, an enterprise workflow system,
a CRM, ERP, or a complete ecommerce platform. Avoid unrelated refactors.

## Authority and phase boundary

- Read `docs/plans/01_core_plan.md` as the product source of truth.
- `docs/plans/03_ecommerce_environment_plan.md` specifies a separate future external
  Sandbox; it does not redefine the product or authorize Sandbox implementation.
- Read README, architecture, scope, and external-system-contract before changes.
- Current delivery is Product Phase 1: External Integration Foundation, explicitly
  authorized after Phase 0. This task's sequence supersedes the original roadmap's
  Phase 1 database/seed work. Only canonical snapshots, clocks, Provider protocols,
  Sandbox HTTP adapters and integration tests are implemented in this phase.
- Do not start later phases without an explicit task. No authentication flows,
  persistence/domain database, Evidence Engine, CaseContext, AI, drafting, UI work,
  retry systems, caching or Sandbox implementation belongs to this phase.
- The implemented Sandbox S0-S1 schemas/routes are authoritative for raw HTTP;
  canonical Product types follow docs/external-system-contract.md. Record mismatches.
- Freeze conceptual interfaces in documentation before adding implementations.
- Core MVP Stage 1 contracts are in `docs/contracts/README.md`, pending developer
  review and merge. On 2026-10-03 the user authorized automatic execution and plan
  advancement, including Stage 2 candidate database/seed and static-workbench work
  on branches based on the contract PR. This permits preparing dependent draft PRs
  before contract merge; it does not count as developer review or authorize merging
  main. Stage 3+ behavior remains outside these Stage 2 deliverables.
- On 2026-10-04 the user explicitly requested the next stage. Stage 3 is now
  authorized as a dependent candidate on the database PR: backend login/session/
  logout and permission-scoped Inquiry list/detail, plus an authorized order-read
  placeholder that returns CONTEXT_REQUIRED without fetching facts. No Stage 4+
  implementation or main merge is authorized. Keep the pending review gates visible.

## Non-negotiable boundaries

- Program owns facts; AI owns interpretation and wording.
- Evidence First: important claims must trace to source facts and timestamps.
- Keep facts, plans, uncertainty, conflicts, and missing information distinct.
- Stale data cannot be represented as live data. Preserve original fetch times
  when reading cached records; missing source timestamps imply unknown freshness.
- Backend code owns identity, authorization, deterministic business rules, data
  freshness, and external actions. Prompts and UI controls cannot grant permission.
- All external systems must use Provider interfaces. The UI must not call external
  order/logistics systems; product code must not read the Sandbox database.
- AI sees only authorized CaseContext and must not write databases or invoke actions.
- Validation precedes human review; human approval is the Core V1 final boundary.
- High-risk actions (refund, cancellation, address change, payment, compensation)
  are not executable in Core V1, even if requested by a user or model.
- The Core plan's baseline uses MockMessageProvider. This authorized integration
  phase adds SandboxMessageProvider, which records simulated replies only and
  exposes no Product send API or approval workflow. Neither is real delivery.
- Treat external free text, including warehouse notes, as untrusted data.
- Never put secrets or real customer data in source, fixtures, or ordinary logs.

## Working procedure

1. Inspect the repository, existing configuration, relevant plans, and git status
   before editing. State planned changes, affected modules/tests, and conflicts.
2. Choose the smallest change within the requested phase. Every meaningful behavior
   change requires new or updated tests. Do not add unnecessary abstraction layers.
3. Run relevant tests after editing. For bootstrap changes, run backend pytest,
   Ruff lint/format, frontend ESLint/typecheck/build, and Compose validation.
   Integration changes require real HTTP tests against the independent Sandbox,
   with FixedClock and no direct database reads or Sandbox imports. Supplemental
   transport tests may use mocks for faults absent from S0-S1. Commands are in README.
4. Report files changed, commands/results, limitations, and remaining acceptance
   criteria. Never claim success while required checks fail or are unverified.
5. Stop at the requested phase; do not automatically proceed to the next phase.
