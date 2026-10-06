# Recover one interrupted Stage 4 resolution

Recovery is an explicit operational action, not an HTTP endpoint, automatic retry,
or permission grant. Use it only after confirming the originating Product worker
has stopped and will not continue its network operation. The CLI cannot cancel a
live worker. Never use it simply because a normal request is slow.

## Diagnose first

1. An authorized Inquiry read shows its latest_run_id and current lock_version.
   Read that exact run at GET `/api/v1/inquiries/{id}/runs/{run_id}`.
2. Confirm the run remains RUNNING and the Inquiry has no valid current Context.
   Check the owning worker/process using the safe request_id; do not paste tokens,
   passwords, source payloads or customer questions into logs/issues.
3. Stop the originating worker before recovery. If it is still running or its
   state is uncertain, keep the operation BUSY and investigate. There is no age-based
   automatic timeout, takeover, retry, or batch cleanup in this MVP.

## Execute on the Product database

The operator must already have privileged access to the Product PostgreSQL database.
The explicit active ADMIN UUID is checked and recorded for Audit attribution; passing
someone's UUID is not an authentication method or a grant of database privileges.
Supply DATABASE_URL securely in the environment. Never put it in shell history or
command arguments. Do not point this tool at the Sandbox database.

From backend, substitute the exact verified identities and version:

```sh
python -m app.context.recovery \
  --inquiry-id "$stage4_inquiry_id" \
  --run-id "$stage4_run_id" \
  --expected-lock-version "$stage4_lock_version" \
  --operator-id "$stage4_admin_id"
```

The CLI targets only the named Inquiry's latest RUNNING resolution, verifies its
ownership and optimistic version, and writes a single transaction:

- run becomes FAILED with error_code OPERATION_INTERRUPTED and finished_at;
- Inquiry remains OPEN with no current Context/Draft, lock_version advances;
- OPERATION_RECOVERED Audit records the operator and exact run, with safe metadata.

History is preserved. It never deletes snapshots, restores old pointers, calls a
Provider, resumes HTTP, or produces a draft/send/approval. A stale version, already
finished run, wrong Inquiry/run association or inactive/non-Admin operator is rejected.
If the transaction fails, no partial recovery is committed.

## Verify and resume manually

Re-read the run and Inquiry with current business authorization. The run should be
FAILED, the Inquiry OPEN, and BUSY released. Replaying the interrupted operation's
original idempotency key must not call a Provider again. A deliberate fresh resolve
needs a new key and the server's latest lock_version. Late completion of the old
worker must be rejected and must not replace the newer run or restore old facts.

Do not edit historical rows directly, disable append-only triggers, truncate tables,
reset seed data or downgrade migrations to bypass a failed recovery.
