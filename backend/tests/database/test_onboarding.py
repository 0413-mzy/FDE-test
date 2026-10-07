"""Real PostgreSQL onboarding acceptance; no public challenge disclosure."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_commerce import ADDRESS, PASSWORD, Clock

from app.commerce.models import CommerceAccount, Shop
from app.commerce.onboarding_models import (
    AccountProfile,
)
from app.commerce.onboarding_seed import seed_reviewer
from app.commerce.seed import seed_commerce
from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.database


def test_registration_verification(database, tmp_path):
    engine, _, _ = database
    app = create_app(
        Settings(app_env="test", commerce_mailbox_dir=tmp_path / "mail"),
        session_factory=lambda: Session(engine),
    )
    with TestClient(app) as client:
        result = client.post(
            "/api/commerce/v1/auth/register",
            headers={"Idempotency-Key": "reg"},
            json={
                "username": "new.user",
                "email": "USER@EXAMPLE.COM",
                "password": "new-password-123",
            },
        )
        assert result.status_code == 202, result.text
        assert result.json() == {"accepted": True, "simulation": True}
        letters = list((tmp_path / "mail").glob("*.json"))
        assert len(letters) == 1
        code = json.loads(letters[0].read_text())["code"]
        verified = client.post(
            "/api/commerce/v1/auth/verify-email",
            headers={"Idempotency-Key": "verify"},
            json={"email": "user@example.com", "code": code},
        )
        assert verified.status_code == 200, verified.text
        login = client.post(
            "/api/commerce/v1/auth/login",
            json={"username": "new.user", "password": "new-password-123"},
        )
        assert login.status_code == 200
        assert login.json()["account"]["customer_enabled"]


def setup(database, tmp_path):
    engine, _, _ = database
    clock = Clock()
    with Session(engine) as db:
        seed_commerce(db, PASSWORD, clock.now())
    with Session(engine) as db:
        seed_reviewer(db, PASSWORD)
    app = create_app(
        Settings(app_env="test", commerce_mailbox_dir=tmp_path / "mail"),
        session_factory=lambda: Session(engine),
        clock=clock,
    )
    return engine, clock, app


def post(client, path, value, token=None, key=None):
    from uuid import uuid4

    headers = {"Idempotency-Key": key or str(uuid4())}
    if token:
        headers["Authorization"] = "Bearer " + token
    return client.post("/api/commerce/v1/" + path, json=value, headers=headers)


def login(client, username="customer.a", password=PASSWORD):
    result = post(client, "auth/login", {"username": username, "password": password})
    assert result.status_code == 200, result.text
    return result.json()["token"]


def letter(tmp_path, purpose=None):
    values = [json.loads(path.read_text()) for path in (tmp_path / "mail").glob("*.json")]
    return next(
        value for value in reversed(values) if purpose is None or value["purpose"] == purpose
    )


def bind(client, token, tmp_path, email="customer@example.com"):
    profile = client.get(
        "/api/commerce/v1/account/profile", headers={"Authorization": "Bearer " + token}
    ).json()
    assert (
        post(
            client,
            "account/email",
            {"expected_version": profile["version"], "email": email, "current_password": PASSWORD},
            token,
        ).status_code
        == 202
    )
    mail = letter(tmp_path, "BIND")
    result = post(client, "auth/verify-email", {"email": email, "code": mail["code"]})
    assert result.status_code == 200, result.text


def test_profile_address_review_isolation(database, tmp_path):
    engine, clock, app = setup(database, tmp_path)
    with TestClient(app) as client:
        a = login(client)
        b = login(client, "customer.b")
        reviewer = login(client, "reviewer")
        auth = {"Authorization": "Bearer " + a}
        initial = client.get("/api/commerce/v1/account/profile", headers=auth)
        assert initial.json()["version"] == 0
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(AccountProfile)) == 1
        result = post(
            client,
            "account/profile",
            {"expected_version": 0, "display_name": " Test ", "phone": ""},
            a,
        )
        assert result.json()["version"] == 1
        assert result.json()["display_name"] == "Test"
        assert (
            post(
                client,
                "account/profile",
                {"expected_version": 0, "display_name": "X", "phone": ""},
                a,
            ).status_code
            == 409
        )
        first = post(
            client, "customer/addresses", {"address": ADDRESS, "is_default": False}, a
        ).json()
        second = post(
            client, "customer/addresses", {"address": ADDRESS, "is_default": True}, a
        ).json()
        assert first["is_default"] and second["is_default"]
        assert (
            post(
                client, "customer/addresses/" + first["id"] + "/edit", {"junk": True}, b
            ).status_code
            == 404
        )
        assert (
            post(client, "customer/addresses/" + first["id"] + "/edit", {"junk": True}).status_code
            == 401
        )
        assert (
            client.get(
                "/api/commerce/v1/customer/addresses",
                headers={"Authorization": "Bearer " + reviewer},
            ).status_code
            == 403
        )
        assert (
            client.get("/api/commerce/v1/review/merchant-applications", headers=auth).status_code
            == 403
        )
        bind(client, a, tmp_path)
        value = {
            "shop_name": "Independent shop",
            "business_scope": "Physical goods",
            "contact_name": "Applicant",
            "contact_phone": "123",
            "description": "Fictional application",
        }
        created = post(client, "customer/merchant-applications", value, a, "apply")
        assert created.status_code == 201, created.text
        application = created.json()
        assert (
            post(client, "customer/merchant-applications", value, a, "apply").json() == application
        )
        assert post(client, "customer/merchant-applications", value, a).status_code == 409
        assert (
            post(
                client,
                "customer/merchant-applications/" + application["id"] + "/withdraw",
                {"junk": True},
                b,
            ).status_code
            == 404
        )
        decision = {"expected_version": 1, "decision": "APPROVE", "reason": ""}
        approved = post(
            client,
            "review/merchant-applications/" + application["id"] + "/decision",
            decision,
            reviewer,
            "approve",
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["state"] == "APPROVED"
        assert (
            post(
                client,
                "review/merchant-applications/" + application["id"] + "/decision",
                decision,
                reviewer,
                "approve",
            ).json()
            == approved.json()
        )
        assert (
            post(
                client,
                "review/merchant-applications/" + application["id"] + "/decision",
                decision,
                reviewer,
            ).status_code
            == 409
        )
        me = client.get("/api/commerce/v1/auth/me", headers=auth).json()
        assert me["customer_enabled"] and len(me["shops"]) == 1
        rows = client.get("/api/commerce/v1/customer/addresses", headers=auth).json()["items"]
        assert sum(row["is_default"] for row in rows) == 1
        default = next(row for row in rows if row["is_default"])
        assert (
            post(
                client,
                "customer/addresses/" + default["id"] + "/delete",
                {"expected_version": default["version"]},
                a,
            ).status_code
            == 200
        )
        rows = client.get("/api/commerce/v1/customer/addresses", headers=auth).json()["items"]
        assert len(rows) == 1 and rows[0]["is_default"]


def test_reset_revokes_every_session_and_one_use(database, tmp_path):
    engine, clock, app = setup(database, tmp_path)
    with TestClient(app) as client:
        a = login(client)
        second = login(client)
        bind(client, a, tmp_path)
        unknown = post(client, "auth/password-reset/request", {"email": "unknown@example.com"})
        known = post(
            client,
            "auth/password-reset/request",
            {"email": "customer@example.com"},
            key="reset-request",
        )
        assert unknown.status_code == known.status_code == 202
        assert unknown.json() == known.json()
        reset = letter(tmp_path, "RESET")
        value = {
            "email": "customer@example.com",
            "code": reset["code"],
            "new_password": "replacement-password-123",
        }
        assert (
            post(client, "auth/password-reset/confirm", {**value, "code": "x" * 43}).status_code
            == 400
        )
        changed = post(client, "auth/password-reset/confirm", value, key="reset-confirm")
        assert changed.status_code == 200, changed.text
        assert post(client, "auth/password-reset/confirm", value, key="reset-confirm").json() == {
            "changed": True
        }
        assert post(client, "auth/password-reset/confirm", value).status_code == 400
        for token in [a, second]:
            assert (
                client.get(
                    "/api/commerce/v1/auth/me", headers={"Authorization": "Bearer " + token}
                ).status_code
                == 401
            )
        assert (
            post(client, "auth/login", {"username": "customer.a", "password": PASSWORD}).status_code
            == 401
        )
        new = login(client, password=value["new_password"])
        assert (
            post(
                client,
                "account/password",
                {"current_password": value["new_password"], "new_password": PASSWORD},
                new,
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/commerce/v1/auth/me", headers={"Authorization": "Bearer " + new}
            ).status_code
            == 401
        )


def test_challenge_expiry_limits_mailbox_permissions_and_replay(database, tmp_path):
    engine, clock, app = setup(database, tmp_path)
    with TestClient(app) as client:
        value = {"username": "pending", "email": "PENDING@example.com", "password": PASSWORD}
        first = post(client, "auth/register", value, key="pending")
        assert first.status_code == 202
        assert post(client, "auth/register", value, key="pending").status_code == 202
        assert len(list((tmp_path / "mail").glob("*.json"))) == 1
        assert (
            post(client, "auth/register", {**value, "username": "other"}, key="pending").status_code
            == 409
        )
        assert (
            post(client, "auth/login", {"username": "pending", "password": PASSWORD}).status_code
            == 401
        )
        for path in (tmp_path / "mail").glob("*.json"):
            assert path.stat().st_mode & 0o777 == 0o600
        assert (tmp_path / "mail").stat().st_mode & 0o777 == 0o700
        assert (tmp_path / "mail" / ".fingerprint-key").stat().st_mode & 0o777 == 0o600
        mail = letter(tmp_path, "REGISTER")
        clock.value += timedelta(minutes=16)
        assert (
            post(
                client, "auth/verify-email", {"email": value["email"], "code": mail["code"]}
            ).status_code
            == 400
        )
        for _ in range(5):
            assert (
                post(
                    client, "auth/verification-request", {"email": "missing@example.com"}
                ).status_code
                == 202
            )
        assert (
            post(client, "auth/verification-request", {"email": "missing@example.com"}).status_code
            == 429
        )
        assert not any("code" in first.json() for _ in [0])


def test_registration_and_decision_concurrency(database, tmp_path):
    engine, clock, app = setup(database, tmp_path)
    value = {"username": "racing", "email": "racing@example.com", "password": PASSWORD}

    def register(index):
        with TestClient(app) as client:
            return post(client, "auth/register", value, key="race-" + str(index)).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(register, range(2))) == [202, 202]
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(CommerceAccount)
                .where(CommerceAccount.username == "racing")
            )
            == 1
        )
    with TestClient(app) as client:
        mail = letter(tmp_path, "REGISTER")
        assert (
            post(
                client, "auth/verify-email", {"email": value["email"], "code": mail["code"]}
            ).status_code
            == 200
        )
        token = login(client, "racing")
        reviewer = login(client, "reviewer")
        created = post(
            client,
            "customer/merchant-applications",
            {
                "shop_name": "Race Shop",
                "business_scope": "Goods",
                "contact_name": "A",
                "contact_phone": "1",
                "description": "Goods",
            },
            token,
        ).json()

    def decide(index):
        with TestClient(app) as client:
            return post(
                client,
                "review/merchant-applications/" + created["id"] + "/decision",
                {"expected_version": 1, "decision": "APPROVE", "reason": ""},
                reviewer,
                key="decision-" + str(index),
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(decide, range(2))) == [200, 409]
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(Shop).where(Shop.name == "Race Shop")) == 1
        )


def test_delivery_failure_retry_restart_and_seed_preservation(database, tmp_path, monkeypatch):
    from app.commerce import mailbox

    engine, clock, app = setup(database, tmp_path)
    original = mailbox.deliver

    def broken(*args):
        raise OSError("Fictional local disk failure")

    monkeypatch.setattr(mailbox, "deliver", broken)
    value = {"username": "failed.delivery", "email": "failure@example.com", "password": PASSWORD}
    with TestClient(app) as client:
        assert post(client, "auth/register", value, key="failed-delivery").status_code == 503
        assert post(client, "auth/register", value, key="failed-delivery").status_code == 503
    with Session(engine) as db:
        account = db.scalar(
            select(CommerceAccount).where(CommerceAccount.username == "failed.delivery")
        )
        assert account is not None and not account.active
    monkeypatch.setattr(mailbox, "deliver", original)
    restarted = create_app(
        Settings(app_env="test", commerce_mailbox_dir=tmp_path / "mail"),
        session_factory=lambda: Session(engine),
        clock=clock,
    )
    with TestClient(restarted) as client:
        assert post(client, "auth/register", value, key="failed-delivery").status_code == 503
        assert (
            post(client, "auth/verification-request", {"email": value["email"]}).status_code == 202
        )
        mail = letter(tmp_path, "REGISTER")
        assert (
            post(
                client, "auth/verify-email", {"email": value["email"], "code": mail["code"]}
            ).status_code
            == 200
        )
        token = login(client, "failed.delivery")
        profile = client.get(
            "/api/commerce/v1/account/profile", headers={"Authorization": "Bearer " + token}
        ).json()
        assert profile["email_verified"]
    with Session(engine) as db:
        before = db.scalar(
            select(CommerceAccount).where(CommerceAccount.username == "reviewer")
        ).password_hash
    with Session(engine) as db:
        seed_reviewer(db, "a-different-password-123")
    with Session(engine) as db:
        assert (
            db.scalar(
                select(CommerceAccount).where(CommerceAccount.username == "reviewer")
            ).password_hash
            == before
        )


def test_address_limit_rejection_withdraw_and_unauthorized_replay(database, tmp_path):
    engine, clock, app = setup(database, tmp_path)
    with TestClient(app) as client:
        token = login(client)
        reviewer = login(client, "reviewer")
        bind(client, token, tmp_path)
        for _ in range(20):
            assert (
                post(
                    client, "customer/addresses", {"address": ADDRESS, "is_default": False}, token
                ).status_code
                == 201
            )
        assert (
            post(
                client, "customer/addresses", {"address": ADDRESS, "is_default": False}, token
            ).status_code
            == 409
        )
        application = {
            "shop_name": "Declined",
            "business_scope": "Goods",
            "contact_name": "A",
            "contact_phone": "1",
            "description": "Description",
        }
        row = post(client, "customer/merchant-applications", application, token).json()
        path = "review/merchant-applications/" + row["id"] + "/decision"
        assert (
            post(
                client, path, {"expected_version": 1, "decision": "REJECT", "reason": ""}, reviewer
            ).status_code
            == 400
        )
        rejected = post(
            client,
            path,
            {"expected_version": 1, "decision": "REJECT", "reason": "Missing details"},
            reviewer,
            "reject",
        )
        assert (
            rejected.status_code == 200 and rejected.json()["decision_reason"] == "Missing details"
        )
        with Session(engine) as db:
            with db.begin():
                info = db.scalar(
                    select(AccountProfile)
                    .join(CommerceAccount)
                    .where(CommerceAccount.username == "reviewer")
                )
                info.review_enabled = False
        assert (
            post(
                client,
                path,
                {"expected_version": 1, "decision": "REJECT", "reason": "Missing details"},
                reviewer,
                "reject",
            ).status_code
            == 403
        )
        row = post(client, "customer/merchant-applications", application, token).json()
        withdrawn = post(
            client,
            "customer/merchant-applications/" + row["id"] + "/withdraw",
            {"expected_version": 1},
            token,
        )
        assert withdrawn.status_code == 200 and withdrawn.json()["state"] == "WITHDRAWN"


def test_email_preserves_original_until_verified_and_raw_password(database, tmp_path):
    engine, clock, app = setup(database, tmp_path)
    secret = " " + PASSWORD + " "
    value = {"username": "spaced", "email": "original@example.com", "password": secret}
    with TestClient(app) as client:
        assert post(client, "auth/register", value).status_code == 202
        mail = letter(tmp_path, "REGISTER")
        assert (
            post(
                client, "auth/verify-email", {"email": value["email"], "code": mail["code"]}
            ).status_code
            == 200
        )
        token = login(client, "spaced", secret)
        change = {
            "expected_version": 2,
            "email": "replacement@example.com",
            "current_password": secret,
        }
        assert post(client, "account/email", change, token, "binding").status_code == 202
        assert post(client, "account/email", change, token, "binding").status_code == 202
        auth = {"Authorization": "Bearer " + token}
        assert (
            client.get("/api/commerce/v1/account/profile", headers=auth).json()["email"]
            == value["email"]
        )
        assert (
            post(
                client, "auth/verification-request", {"email": "replacement@example.com"}
            ).status_code
            == 202
        )
        letters = [json.loads(path.read_text()) for path in (tmp_path / "mail").glob("*.json")]
        # Select the active challenge digest, independent of filesystem ordering.
        from app.commerce.onboarding_models import EmailChallenge
        from app.core.security import token_digest

        with Session(engine) as db:
            active = db.scalar(
                select(EmailChallenge).where(
                    EmailChallenge.purpose == "BIND", EmailChallenge.consumed_at.is_(None)
                )
            )
            code = next(
                mail["code"]
                for mail in letters
                if token_digest(mail["code"]) == active.token_digest
            )
        assert (
            post(
                client, "auth/verify-email", {"email": "replacement@example.com", "code": code}
            ).status_code
            == 200
        )
        assert (
            client.get("/api/commerce/v1/account/profile", headers=auth).json()["email"]
            == "replacement@example.com"
        )


def test_reviewer_revoked_while_waiting_for_write_lock(database, tmp_path, monkeypatch):
    from threading import Event

    from sqlalchemy import text

    from app.commerce.service import Commerce

    engine, clock, app = setup(database, tmp_path)
    with TestClient(app) as client:
        token = login(client)
        reviewer = login(client, "reviewer")
        bind(client, token, tmp_path)
        application = post(
            client,
            "customer/merchant-applications",
            {
                "shop_name": "Must not create",
                "business_scope": "Goods",
                "contact_name": "A",
                "contact_phone": "1",
                "description": "Description",
            },
            token,
        ).json()
    waiting = Event()
    original = Commerce.acquire_write

    def acquire(svc):
        if svc.request.url.path.endswith("/decision"):
            waiting.set()
        return original(svc)

    monkeypatch.setattr(Commerce, "acquire_write", acquire)
    with Session(engine) as blocker:
        with blocker.begin():
            blocker.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtextextended(current_schema() || '-commerce-v1',0))"
                )
            )
            with ThreadPoolExecutor(max_workers=1) as pool:

                def decide():
                    with TestClient(app) as client:
                        return post(
                            client,
                            "review/merchant-applications/" + application["id"] + "/decision",
                            {"expected_version": 1, "decision": "APPROVE", "reason": ""},
                            reviewer,
                        )

                future = pool.submit(decide)
                assert waiting.wait(1)
                info = blocker.scalar(
                    select(AccountProfile)
                    .join(CommerceAccount)
                    .where(CommerceAccount.username == "reviewer")
                )
                info.review_enabled = False
                blocker.commit()
                result = future.result(timeout=5)
                assert result.status_code == 403, result.text
    with Session(engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(Shop).where(Shop.name == "Must not create"))
            == 0
        )


def test_concurrent_default_addresses_bump_replacement_version(database, tmp_path):
    engine, clock, app = setup(database, tmp_path)
    with TestClient(app) as client:
        token = login(client)

    def create(index):
        with TestClient(app) as client:
            return post(
                client,
                "customer/addresses",
                {
                    "address": {**ADDRESS, "address_line": "Street " + str(index)},
                    "is_default": True,
                },
                token,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(create, range(2))) == [201, 201]
    with TestClient(app) as client:
        auth = {"Authorization": "Bearer " + token}
        rows = client.get("/api/commerce/v1/customer/addresses", headers=auth).json()["items"]
        assert len(rows) == 2 and sum(row["is_default"] for row in rows) == 1
        old = next(row for row in rows if not row["is_default"])
        default = next(row for row in rows if row["is_default"])
        changed = post(
            client,
            "customer/addresses/" + default["id"] + "/edit",
            {"expected_version": default["version"], "address": ADDRESS, "is_default": False},
            token,
        )
        assert changed.status_code == 200
        replacement = next(
            row
            for row in client.get("/api/commerce/v1/customer/addresses", headers=auth).json()[
                "items"
            ]
            if row["id"] == old["id"]
        )
        assert replacement["is_default"] and replacement["version"] == old["version"] + 1
        assert (
            post(
                client,
                "customer/addresses/" + old["id"] + "/edit",
                {"expected_version": old["version"], "address": ADDRESS, "is_default": True},
                token,
            ).status_code
            == 409
        )
    key = tmp_path / "mail" / ".fingerprint-key"
    # This test only uses non-secret private address payloads, so no key creation is necessary.
    assert not key.exists()


def test_pending_delivery_exact_retry_is_busy_not_success(database, tmp_path, monkeypatch):
    from threading import Event

    from app.commerce import mailbox

    engine, clock, app = setup(database, tmp_path)
    started = Event()
    release = Event()
    original = mailbox.deliver

    def paused(settings, letter):
        started.set()
        assert release.wait(5)
        return original(settings, letter)

    monkeypatch.setattr(mailbox, "deliver", paused)
    value = {"username": "pending.mail", "email": "pendingmail@example.com", "password": PASSWORD}

    def register():
        with TestClient(app) as client:
            return post(client, "auth/register", value, key="pending-mail")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(register)
        assert started.wait(2)
        with TestClient(app) as client:
            busy = post(client, "auth/register", value, key="pending-mail")
            assert busy.status_code == 409 and busy.json()["error"]["code"] == "OPERATION_BUSY"
        release.set()
        assert future.result(timeout=5).status_code == 202
    with TestClient(app) as client:
        assert post(client, "auth/register", value, key="pending-mail").status_code == 202


def test_uniform_mailbox_preflight_unavailability(database, tmp_path, monkeypatch):
    from app.commerce import mailbox

    engine, clock, app = setup(database, tmp_path)
    with TestClient(app) as client:
        token = login(client)
        bind(client, token, tmp_path)

        def unavailable(settings):
            raise OSError("Unavailable local mailbox")

        monkeypatch.setattr(mailbox, "check_delivery", unavailable)
        for target in ["customer@example.com", "unknown@example.com"]:
            result = post(client, "auth/password-reset/request", {"email": target})
            assert (
                result.status_code == 503
                and result.json()["error"]["code"] == "MAILBOX_UNAVAILABLE"
            )
