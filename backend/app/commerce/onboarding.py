"""Atomic onboarding writes under the existing schema-local commerce mutex."""

import re
from datetime import timedelta

from sqlalchemy import select, update

from app.commerce import inputs as inp
from app.commerce import views
from app.commerce.errors import fail
from app.commerce.models import Cart, CommerceAccount, CommerceSession, Shop, ShopMembership
from app.commerce.onboarding_models import (
    AccountProfile,
    AddressBook,
    EmailChallenge,
    MerchantApplication,
)
from app.core.security import PASSWORD_HASHER, new_token, password_matches, token_digest

ACCEPTED = {"accepted": True, "simulation": True}


def email(value):
    value = inp.string(value, 3, 254)
    if not value.isascii() or not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",
        value,
    ):
        fail("INVALID_REQUEST", 400)
    return value.lower()


def password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        fail("INVALID_REQUEST", 400)
    return value


def profile(svc, create=False):
    statement = select(AccountProfile).where(AccountProfile.account_id == svc.actor.id)
    if svc.write:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = svc.db.scalar(statement)
    if row is None and create:
        row = svc.new(AccountProfile, account_id=svc.actor.id)
    return row


def profile_view(svc):
    row = profile(svc)
    return dict(
        account_id=str(svc.actor.id),
        username=svc.actor.username,
        version=row.version if row else 0,
        display_name=row.display_name if row else "",
        phone=row.phone if row else "",
        email=row.email if row else None,
        email_verified=row.email_verified if row else False,
        review_enabled=row.review_enabled if row else False,
    )


def address_view(row):
    return dict(
        id=str(row.id),
        version=row.version,
        address=row.address,
        is_default=row.is_default,
        created_at=views.iso(row.created_at),
        updated_at=views.iso(row.updated_at),
    )


def application_view(row):
    return dict(
        id=str(row.id),
        version=row.version,
        state=row.state,
        shop_name=row.shop_name,
        business_scope=row.business_scope,
        contact_name=row.contact_name,
        contact_phone=row.contact_phone,
        description=row.description,
        created_at=views.iso(row.created_at),
        updated_at=views.iso(row.updated_at),
        decision_reason=row.decision_reason,
        shop_id=str(row.shop_id) if row.shop_id else None,
    )


def challenge(svc, account, target, purpose):
    # New challenge supersedes all older challenges for this account/purpose.
    svc.db.execute(
        update(EmailChallenge)
        .where(
            EmailChallenge.account_id == account.id,
            EmailChallenge.purpose == purpose,
            EmailChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=svc.now)
    )
    code = new_token()
    svc.new(
        EmailChallenge,
        account_id=account.id,
        email=target,
        purpose=purpose,
        token_digest=token_digest(code),
        expires_at=svc.now + timedelta(minutes=15),
    )
    svc.letters.append(
        dict(
            email=target,
            purpose=purpose,
            code=code,
            expires_at=views.iso(svc.now + timedelta(minutes=15)),
        )
    )


def revoke(svc, account):
    svc.db.execute(
        update(CommerceSession)
        .where(CommerceSession.account_id == account.id, CommerceSession.revoked_at.is_(None))
        .values(revoked_at=svc.now)
    )


def public(svc, op, body):
    if op == "register":
        inp.fields(body, ["username", "email", "password"])
        username = inp.string(body["username"], 1, 80)
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", username):
            fail("INVALID_REQUEST", 400)
        target = email(body["email"])
        secret = password(body["password"])
        occupied = svc.db.scalar(
            select(CommerceAccount).where(CommerceAccount.username == username)
        )
        bound = svc.db.scalar(select(AccountProfile).where(AccountProfile.email == target))
        pending = svc.db.scalar(
            select(EmailChallenge).where(
                EmailChallenge.email == target,
                EmailChallenge.purpose.in_(["REGISTER", "BIND"]),
                EmailChallenge.consumed_at.is_(None),
                EmailChallenge.expires_at > svc.now,
            )
        )
        if not occupied and not bound and not pending:
            account = svc.new(
                CommerceAccount,
                username=username,
                password_hash=PASSWORD_HASHER.hash(secret),
                active=False,
                customer_enabled=False,
                demo_enabled=False,
            )
            svc.new(AccountProfile, account_id=account.id, email=target, email_verified=False)
            challenge(svc, account, target, "REGISTER")
        return ACCEPTED, 202
    if op in {"verification-request", "password-reset/request"}:
        inp.fields(body, ["email"])
        target = email(body["email"])
        row = svc.db.scalar(select(AccountProfile).where(AccountProfile.email == target))
        if row and (
            (op == "password-reset/request" and row.email_verified)
            or (op == "verification-request" and not row.email_verified)
        ):
            account = svc.get(CommerceAccount, row.account_id, True)
            challenge(svc, account, target, "RESET" if row.email_verified else "REGISTER")
        elif op == "verification-request":
            pending = svc.db.scalar(
                select(EmailChallenge)
                .where(
                    EmailChallenge.email == target,
                    EmailChallenge.purpose == "BIND",
                    EmailChallenge.consumed_at.is_(None),
                )
                .order_by(EmailChallenge.created_at.desc())
                .limit(1)
            )
            if pending:
                account = svc.get(CommerceAccount, pending.account_id, True)
                if account.active:
                    challenge(svc, account, target, "BIND")
        return ACCEPTED, 202
    reset = op == "password-reset/confirm"
    inp.fields(body, ["email", "code", "new_password"] if reset else ["email", "code"])
    target = email(body["email"])
    code = inp.string(body["code"], 43, 43)
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", code):
        fail("INVALID_CHALLENGE", 400)
    row = svc.db.scalar(
        select(EmailChallenge)
        .where(
            EmailChallenge.email == target,
            EmailChallenge.token_digest == token_digest(code),
            EmailChallenge.purpose.in_(["RESET"] if reset else ["REGISTER", "BIND"]),
        )
        .with_for_update()
    )
    if row is None or row.consumed_at or row.expires_at <= svc.now:
        fail("INVALID_CHALLENGE", 400)
    account = svc.get(CommerceAccount, row.account_id, True)
    info = svc.db.scalar(
        select(AccountProfile).where(AccountProfile.account_id == account.id).with_for_update()
    )
    if reset:
        if not account.active or not info.email_verified or info.email != target:
            fail("INVALID_CHALLENGE", 400)
        account.password_hash = PASSWORD_HASHER.hash(password(body["new_password"]))
        svc.bump(account)
        revoke(svc, account)
    else:
        conflict = svc.db.scalar(
            select(AccountProfile).where(
                AccountProfile.email == target, AccountProfile.account_id != account.id
            )
        )
        if conflict:
            fail("INVALID_CHALLENGE", 400)
        info.email = target
        info.email_verified = True
        svc.bump(info)
        if row.purpose == "REGISTER":
            account.active = True
            account.customer_enabled = True
            svc.bump(account)
            svc.new(Cart, customer_id=account.id)
    row.consumed_at = svc.now
    svc.bump(row)
    return {"changed": True} if reset else {"verified": True}, 200


def mutate(svc, op, row, body):
    if op == "profile":
        inp.fields(body, ["expected_version", "display_name", "phone"])
        info = profile(svc)
        if inp.integer(body["expected_version"], 0) != (info.version if info else 0):
            fail("VERSION_CONFLICT")
        display = inp.string(body["display_name"], 0, 100)
        phone = inp.string(body["phone"], 0, 32)
        if info is None:
            info = profile(svc, True)
        else:
            svc.bump(info)
        info.display_name = display
        info.phone = phone
        return profile_view(svc), 200
    if op == "email":
        inp.fields(body, ["expected_version", "email", "current_password"])
        info = profile(svc)
        if inp.integer(body["expected_version"], 0) != (info.version if info else 0):
            fail("VERSION_CONFLICT")
        if not password_matches(svc.actor.password_hash, password(body["current_password"])):
            fail("INVALID_CREDENTIALS", 401)
        target = email(body["email"])
        occupied = svc.db.scalar(
            select(AccountProfile).where(
                AccountProfile.email == target, AccountProfile.account_id != svc.actor.id
            )
        )
        pending = svc.db.scalar(
            select(EmailChallenge).where(
                EmailChallenge.email == target,
                EmailChallenge.account_id != svc.actor.id,
                EmailChallenge.purpose.in_(["REGISTER", "BIND"]),
                EmailChallenge.consumed_at.is_(None),
                EmailChallenge.expires_at > svc.now,
            )
        )
        if not occupied and not pending:
            if info is None:
                profile(svc, True)
            challenge(svc, svc.actor, target, "BIND")
        return ACCEPTED, 202
    if op == "password":
        inp.fields(body, ["current_password", "new_password"])
        if not password_matches(svc.actor.password_hash, password(body["current_password"])):
            fail("INVALID_CREDENTIALS", 401)
        svc.actor.password_hash = PASSWORD_HASHER.hash(password(body["new_password"]))
        svc.bump(svc.actor)
        revoke(svc, svc.actor)
        return {"changed": True}, 200
    if op.startswith("address"):
        current = list(
            svc.db.scalars(
                select(AddressBook)
                .where(AddressBook.customer_id == svc.actor.id, AddressBook.active.is_(True))
                .order_by(AddressBook.created_at, AddressBook.id)
            )
        )
        if op == "address.delete":
            inp.fields(body, ["expected_version"])
            svc.version(row, body)
            was_default = row.is_default
            row.active = False
            row.is_default = False
            svc.bump(row)
            svc.db.flush()
            others = [item for item in current if item.id != row.id]
            if was_default and others:
                others[0].is_default = True
                svc.bump(others[0])
            return {"deleted": True}, 200
        inp.fields(body, ["address", "is_default"] + (["expected_version"] if row else []))
        value = inp.address(body["address"])
        default = inp.boolean(body["is_default"])
        if row:
            svc.version(row, body)
        elif len(current) >= 20:
            fail("ADDRESS_LIMIT")
        default = default or not current
        if row and row.is_default and not default and len(current) == 1:
            default = True
        if default:
            for item in current:
                if item.is_default and (row is None or item.id != row.id):
                    item.is_default = False
                    svc.bump(item)
            svc.db.flush()
        if row:
            old_default = row.is_default
            row.address = value
            row.is_default = default
            svc.bump(row)
            svc.db.flush()
            if old_default and not default:
                replacement = next(item for item in current if item.id != row.id)
                replacement.is_default = True
                svc.bump(replacement)
        else:
            row = svc.new(
                AddressBook,
                customer_id=svc.actor.id,
                address=value,
                is_default=default,
                active=True,
            )
        return address_view(row), 200 if op == "address.edit" else 201
    if op == "application.create":
        names = {
            "shop_name": 200,
            "business_scope": 500,
            "contact_name": 100,
            "contact_phone": 32,
            "description": 2000,
        }
        inp.fields(body, names)
        info = profile(svc)
        if not info or not info.email_verified:
            fail("EMAIL_VERIFICATION_REQUIRED", 403)
        if svc.db.scalar(
            select(ShopMembership).where(
                ShopMembership.account_id == svc.actor.id, ShopMembership.active.is_(True)
            )
        ) or svc.db.scalar(
            select(MerchantApplication).where(
                MerchantApplication.customer_id == svc.actor.id,
                MerchantApplication.state == "PENDING",
            )
        ):
            fail("APPLICATION_CONFLICT")
        row = svc.new(
            MerchantApplication,
            customer_id=svc.actor.id,
            state="PENDING",
            **{name: inp.string(body[name], 1, limit) for name, limit in names.items()},
        )
        return application_view(row), 201
    inp.fields(
        body,
        ["expected_version"]
        if op == "application.withdraw"
        else ["expected_version", "decision", "reason"],
    )
    svc.version(row, body)
    if row.state != "PENDING":
        fail("INVALID_STATE")
    if op == "application.withdraw":
        row.state = "WITHDRAWN"
    else:
        decision = body["decision"]
        if decision not in {"APPROVE", "REJECT"}:
            fail("INVALID_REQUEST", 400)
        reason = inp.string(body["reason"], 1 if decision == "REJECT" else 0, 500)
        row.decision_reason = reason or None
        if decision == "APPROVE":
            account = svc.get(CommerceAccount, row.customer_id, True)
            if (
                not account.active
                or not account.customer_enabled
                or svc.db.scalar(
                    select(ShopMembership).where(
                        ShopMembership.account_id == account.id, ShopMembership.active.is_(True)
                    )
                )
            ):
                fail("APPLICATION_CONFLICT")
            shop = svc.new(Shop, name=row.shop_name, status="ACTIVE")
            svc.new(
                ShopMembership, account_id=account.id, shop_id=shop.id, role="OWNER", active=True
            )
            row.shop_id = shop.id
            row.state = "APPROVED"
        else:
            row.state = "REJECTED"
    svc.bump(row)
    return application_view(row), 200
