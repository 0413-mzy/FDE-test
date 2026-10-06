# Stage 4 Evidence / CaseContext design

User authorization: take responsibility for the next stage and report the completed work.
Baseline: origin/main 8469971. Frozen core-mvp-v1 contracts remain authoritative.

Implement the existing contract rather than redesign it. A pure Context builder creates
closed Pydantic output, stable evidence pointers, freshness, unknowns, missing data and
the two conservative conflict rules. A Provider collector validates canonical identities
and records individual outcomes. An application service uses two short PostgreSQL
transactions around HTTP: authorize/reserve/clear old pointers, then reauthorize/save/release.
Idempotency precedes optimistic version checks. No transaction remains open during HTTP.

Expose resolve-context, run, historical Context and current order reads. Never retrieve
facts for unauthorized callers; never restore an old Context after a failed new run.
Preserve RUNNING after interrupted or failed final transactions. Provide an explicit
targeted recovery CLI/runbook; no automatic recovery, retry, cache, AI or sending.

Use the existing 12-table schema without rewriting frozen migrations. Test pure rules,
canonical association, real PostgreSQL version/concurrency/rollback/authorization,
and independent Sandbox HTTP using FixedClock. Update only Stage 4 documentation.

Alternative approaches considered: in-memory-only resolver omits durable history;
one long database transaction across HTTP prevents proper busy/recovery behavior.
The two-transaction persisted design follows the approved lifecycle contract.
