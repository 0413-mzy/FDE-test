"""Explicit operator recovery of one interrupted resolution; never an automatic sweep."""

import argparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.core.clock import SystemClock
from app.core.config import Settings
from app.db.connection import product_engine
from app.db.models import AuditLog, ContextVersion, Inquiry, ResolutionRun, User


def recover(session, clock, *, inquiry_id, run_id, expected_lock_version, operator_id):
    operator = session.scalar(select(User).where(User.id == operator_id).with_for_update(read=True))
    if operator is None or not operator.is_active or operator.role != "ADMIN":
        raise ApiError(403, "FORBIDDEN")
    inquiry = session.scalar(select(Inquiry).where(Inquiry.id == inquiry_id).with_for_update())
    run = session.scalar(
        select(ResolutionRun)
        .where(ResolutionRun.id == run_id, ResolutionRun.inquiry_id == inquiry_id)
        .with_for_update()
    )
    if inquiry is None or run is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND")
    if (
        type(expected_lock_version) is not int
        or expected_lock_version < 1
        or inquiry.lock_version != expected_lock_version
    ):
        raise ApiError(409, "VERSION_CONFLICT")
    if (
        run.state != "RUNNING"
        or inquiry.latest_run_id != run.id
        or inquiry.current_context_id is not None
        or session.scalar(select(ContextVersion.id).where(ContextVersion.run_id == run.id))
        is not None
    ):
        raise ApiError(409, "STATE_CONFLICT")
    run.state = "FAILED"
    run.error_code = "OPERATION_INTERRUPTED"
    run.finished_at = clock.now()
    inquiry.lock_version += 1
    inquiry.updated_at = clock.now()
    session.add(
        AuditLog(
            inquiry_id=inquiry.id,
            actor_id=operator.id,
            event_type="OPERATION_RECOVERED",
            record_id=run.id,
            request_id="manual-recovery",
            occurred_at=clock.now(),
            safe_metadata={"error_code": "OPERATION_INTERRUPTED"},
        )
    )
    session.flush()
    return {"run_id": str(run.id), "state": run.state, "lock_version": inquiry.lock_version}


def main():
    parser = argparse.ArgumentParser(
        description="Recover an explicitly confirmed stopped resolution worker"
    )
    parser.add_argument("--inquiry-id", type=UUID, required=True)
    parser.add_argument("--run-id", type=UUID, required=True)
    parser.add_argument("--expected-lock-version", type=int, required=True)
    parser.add_argument("--operator-id", type=UUID, required=True)
    args = parser.parse_args()
    settings = Settings()
    if settings.database_url is None:
        parser.error("DATABASE_URL is required")
    engine = product_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as session, session.begin():
            result = recover(
                session,
                SystemClock(),
                inquiry_id=args.inquiry_id,
                run_id=args.run_id,
                expected_lock_version=args.expected_lock_version,
                operator_id=args.operator_id,
            )
        print(result)
    except ApiError as error:
        parser.exit(1, error.code + "\n")
    except Exception:
        parser.exit(1, "INTERNAL_ERROR\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
