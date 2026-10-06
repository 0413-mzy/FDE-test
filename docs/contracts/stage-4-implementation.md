# Stage 4 executable slice

Date: 2026-10-06. User-authorized next-stage implementation. Frozen core-mvp-v1
Evidence, API and lifecycle contracts remain the source of truth.

## Interfaces and response envelopes

- POST `/api/v1/inquiries/{id}/resolve-context`: closed JSON
  `{expected_lock_version: positive integer}`, one nonblank 1–200 character
  `Idempotency-Key`. New completed operation returns 201, completed replay 200;
  RUNNING replay returns 202 and `Location` pointing to the run resource.
  Required source failure returns the contract's safe error status/code with `run_id`.
- GET `/api/v1/inquiries/{id}/runs/{run_id}`: id, state, version, context_id,
  error_code and current Inquiry lock_version; include `busy` derived from active
  resolution/generation records. Reauthorize before looking up the historical ID.
- GET `/api/v1/inquiries/{id}/contexts/{context_id}`: outer `{context, is_current}`;
  context is the frozen CaseContext. Historical payload/timestamps are not rewritten.
- GET `/api/v1/inquiries/{id}/order`: outer `{context_id, context_version, order,
  freshness}`. Only read the successful order envelope from the valid current
  Context/run of the same Inquiry. Freshness is reevaluated using its stored policy
  and original canonical times at the read Clock. Never call a Provider on reads.

## Transactions and failures

The start transaction locks identity/session then Inquiry, checks permission before
body/version/state, checks idempotency before optimistic version, reserves a RUNNING
run, clears current Context/Draft and increments lock_version. Commit before HTTP.
Required order binding cannot be changed by the request or by source output.
The completion transaction repeats identity/ownership checks and verifies the exact
run, version and reserved binding. All snapshots, Context, terminal run and Audit
commit atomically. Optional failures remain individual outcomes; required failures
save FAILED with no Context. Invalid model/Provider output is never a usable snapshot.

If session/ownership/binding changes during HTTP, discard newly fetched facts,
mark only the owned run FAILED with AUTHORIZATION_CHANGED/BINDING_CHANGED, clear
reservation, and respond with the current safe authorization/conflict error.
Unexpected errors roll back the completion transaction and leave RUNNING/BUSY for
explicit recovery. No return value can expose facts without final authorization.

After successful identity/Inquiry authorization, a rejected resolve request appends
the existing RESOLVE_FAILED Audit event with inquiry_id, actor_id, request_id,
record_id null and safe_metadata `{error_code, rejected: true}`. This records a
request rejection, not a newly created FAILED run; no key/body/customer text is
copied. Unknown/forbidden Inquiry keeps the existing nondisclosing ACCESS_DENIED
event. Missing/invalid bearer is rejected before database access. Exact operation
replay relies on the original operation Audit rather than fabricating another attempt.

The Provider bundle contains existing order/logistics/warehouse/message protocols.
MessageProvider is used only for get_inquiry, never send_reply. Warehouse notes
are fetched once per order. Success SourceFetch.fetched_at is the canonical parent
timestamp when present, completion Clock for SupportInquiry/empty arrays; canonical
SupportInquiry is not extended with a fabricated timestamp.

## Manual recovery

Provide a CLI requiring explicit Inquiry UUID, Run UUID, expected_lock_version and
active ADMIN operator identity. It takes locks, targets only that Inquiry's current
RUNNING resolution, changes it to FAILED / OPERATION_INTERRUPTED, increments the
Inquiry lock_version and appends OPERATION_RECOVERED. No remote calls, resume,
automatic sweep, Context restoration or deletion. Operators must first establish
that the originating worker stopped; recovery cannot cancel live HTTP.

## Boundaries

No migrations, AI, drafting, approval, escalation API, sending, cache, retry or
frontend behavior. CORS allows Idempotency-Key and exposes the run Location header
for the existing trusted origins.
The Stage 3 route inventory test will recognize Stage 4 routes and continue rejecting
later-stage endpoints. Existing Stage 3 zero-Provider-call regression remains valid.
