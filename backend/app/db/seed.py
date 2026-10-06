"""Idempotent demo identities/bindings only; no external facts or API behavior."""

import os
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.security import PASSWORD_HASHER
from app.db.connection import product_engine
from app.db.models import Inquiry, Team, User

DEMO_NAMESPACE = UUID("6fc0832a-1175-4cc5-8f5a-f83b7724d397")


def validate_seed_config(app_env: str, password: str | None) -> str:
    if app_env not in {"development", "test"}:
        raise ValueError("Demo seed is restricted to development/test")
    if password is None or not 12 <= len(password) <= 128 or not password.strip():
        raise ValueError("DEMO_SEED_PASSWORD must be explicitly set to 12-128 nonblank characters")
    return password


def seed_demo(session: Session, clock: Clock, *, app_env: str, password: str | None) -> dict:
    """Caller owns the transaction; existing passwords/ownership/workflow are never reset."""
    secret = validate_seed_config(app_env, password)
    now = clock.now()
    teams = {}
    for n in (1, 2):
        code = f"DEMO-TEAM-{n}"
        team = session.scalar(select(Team).where(Team.code == code))
        if team is None:
            team = Team(
                id=uuid5(DEMO_NAMESPACE, code),
                code=code,
                display_name=f"Demo support group {n}",
                created_at=now,
            )
            session.add(team)
        teams[n] = team
    session.flush()
    users = {}
    for username, role, team_number in (
        ("agent.a", "AGENT", 1),
        ("agent.b", "AGENT", 1),
        ("agent.c", "AGENT", 2),
        ("supervisor", "SUPERVISOR", 1),
        ("admin", "ADMIN", None),
    ):
        team_id = teams[team_number].id if team_number else None
        user = session.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                id=uuid5(DEMO_NAMESPACE, username),
                username=username,
                password_hash=PASSWORD_HASHER.hash(secret),
                role=role,
                team_id=team_id,
                is_active=True,
                created_at=now,
                lock_version=1,
            )
            session.add(user)
        elif user.role != role or user.team_id != team_id or not user.is_active:
            raise ValueError("Existing demo identity differs from the required active role/team")
        users[username] = user
    session.flush()
    for n in range(1, 13):
        external_id = f"INQ-DEMO-{n:03}"
        existing = session.scalar(
            select(Inquiry).where(
                Inquiry.source_system == "demo_support", Inquiry.external_inquiry_id == external_id
            )
        )
        if existing is not None:
            continue
        agent = users["agent.b" if n == 11 else "agent.c" if n == 12 else "agent.a"]
        session.add(
            Inquiry(
                id=uuid5(DEMO_NAMESPACE, external_id),
                source_system="demo_support",
                external_inquiry_id=external_id,
                external_order_id=f"ORD-DEMO-{n:03}",
                team_id=agent.team_id,
                assigned_agent_id=agent.id,
                state="OPEN",
                lock_version=1,
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()
    return {"teams": 2, "users": 5, "demo_inquiry_bindings": 12}


def main() -> None:
    settings = Settings()
    password = validate_seed_config(settings.app_env, os.environ.get("DEMO_SEED_PASSWORD"))
    if settings.database_url is None:
        raise ValueError("DATABASE_URL is required for Product demo seed")
    engine = product_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as session, session.begin():
            seed_demo(session, SystemClock(), app_env=settings.app_env, password=password)
    finally:
        engine.dispose()
    print("Product demo identities and Inquiry bindings are ready; no workflow state was reset.")


if __name__ == "__main__":
    main()
