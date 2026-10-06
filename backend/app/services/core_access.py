"""Stage 3 transactions: current identity and Inquiry ownership before disclosure."""

import json
from datetime import timedelta
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.api.contracts import (
    InquiryList,
    InquirySummary,
    InquiryView,
    LoginInput,
    LoginView,
    Pagination,
    UserView,
)
from app.api.errors import ApiError
from app.core.clock import Clock
from app.core.security import bearer_token, new_token, password_matches, token_digest
from app.db.models import AuditLog, AuthSession, Inquiry, User


def inquiry_scope(user: User):
    if user.role == "SUPERVISOR" and user.team_id is not None:
        return Inquiry.team_id == user.team_id
    if user.role == "AGENT" and user.team_id is not None:
        return (Inquiry.team_id == user.team_id) & (Inquiry.assigned_agent_id == user.id)
    return false()


def closed_query(pairs: list[tuple[str, str]], allowed: set[str]) -> dict:
    result = {}
    for key, value in pairs:
        if key not in allowed or key in result:
            raise ApiError(422, "INVALID_REQUEST")
        result[key] = value
    return result


def no_input(body: bytes, query: list[tuple[str, str]]) -> None:
    if body or query:
        raise ApiError(422, "INVALID_REQUEST")


def validated(model, values):
    try:
        return model.model_validate(values)
    except ValidationError as exc:
        # Do not forward Pydantic's input, ctx, URLs, or caller-supplied key names.
        fields = {
            str(error["loc"][0])
            if error["loc"] and error["loc"][0] in model.model_fields
            else "request"
            for error in exc.errors(include_input=False, include_context=False, include_url=False)
        }
        raise ApiError(422, "INVALID_REQUEST", {"field_errors": sorted(fields)}) from None


def login_body(body: bytes, content_type: str) -> LoginInput:
    def unique_object(pairs):
        return closed_query(pairs, {"username", "password"})

    if content_type.split(";", 1)[0].strip().lower() != "application/json" or len(body) > 4096:
        raise ApiError(422, "INVALID_REQUEST")
    try:
        value = json.loads(body, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError, RecursionError):
        raise ApiError(422, "INVALID_REQUEST") from None
    return validated(LoginInput, value)


class CoreAccess:
    def __init__(self, session: Session, clock: Clock, request_id: str):
        self.session = session
        self.clock = clock
        self.request_id = request_id

    def audit(self, event: str, actor_id: UUID | None = None, **metadata) -> None:
        self.session.add(
            AuditLog(
                actor_id=actor_id,
                event_type=event,
                request_id=self.request_id,
                occurred_at=self.clock.now(),
                safe_metadata=metadata,
            )
        )

    def authenticate(self, header: str | None, *, logout: bool = False) -> tuple[User, AuthSession]:
        token = bearer_token(header)
        if token is None:
            raise ApiError(401, "UNAUTHENTICATED")
        digest = token_digest(token)
        user_id = self.session.scalar(
            select(AuthSession.user_id).where(AuthSession.token_digest == digest)
        )
        if user_id is None:
            raise ApiError(401, "UNAUTHENTICATED")
        # User -> session -> Inquiry is the shared lock order for future services.
        user = self.session.scalar(
            select(User).where(User.id == user_id).with_for_update(read=True)
        )
        auth = self.session.scalar(
            select(AuthSession)
            .where(AuthSession.token_digest == digest, AuthSession.user_id == user_id)
            .with_for_update(read=not logout)
        )
        if (
            user is None
            or not user.is_active
            or auth is None
            or auth.revoked_at is not None
            or self.clock.now() >= auth.expires_at
        ):
            raise ApiError(401, "UNAUTHENTICATED")
        return user, auth

    def login(self, body: bytes, content_type: str, query: list[tuple[str, str]]) -> LoginView:
        closed_query(query, set())
        data = login_body(body, content_type)
        user = self.session.scalar(
            select(User).where(User.username == data.username).with_for_update(read=True)
        )
        matches = password_matches(user.password_hash if user else None, data.password)
        if not matches or user is None or not user.is_active:
            self.audit("LOGIN_FAILED", error_code="AUTHENTICATION_FAILED")
            raise ApiError(401, "AUTHENTICATION_FAILED")
        now = self.clock.now()
        token = new_token()
        auth = AuthSession(
            user_id=user.id,
            token_digest=token_digest(token),
            created_at=now,
            expires_at=now + timedelta(hours=8),
        )
        self.session.add(auth)
        self.audit("LOGIN_SUCCESS", user.id)
        return LoginView(
            token=token, expires_at=auth.expires_at, user=UserView.model_validate(user)
        )

    def me(self, header, body, query) -> UserView:
        user, _ = self.authenticate(header)
        no_input(body, query)
        return UserView.model_validate(user)

    def logout(self, header, body, query) -> None:
        user, auth = self.authenticate(header, logout=True)
        no_input(body, query)
        auth.revoked_at = self.clock.now()
        self.audit("LOGOUT", user.id)

    def list_inquiries(self, header, body, query) -> InquiryList:
        user, _ = self.authenticate(header)
        if body:
            raise ApiError(422, "INVALID_REQUEST")
        pagination = validated(Pagination, closed_query(query, {"limit", "offset"}))
        scope = inquiry_scope(user)
        total = self.session.scalar(select(func.count()).select_from(Inquiry).where(scope))
        records = self.session.scalars(
            select(Inquiry)
            .where(scope)
            .order_by(Inquiry.created_at.desc(), Inquiry.id.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
            .with_for_update(read=True)
        ).all()
        return InquiryList(
            items=[InquirySummary.model_validate(record) for record in records],
            limit=pagination.limit,
            offset=pagination.offset,
            total=total,
        )

    def read_inquiry(self, header, inquiry_id, body, query, *, order: bool = False) -> InquiryView:
        user, _ = self.authenticate(header)
        try:
            identity = UUID(inquiry_id)
        except ValueError:
            raise ApiError(422, "INVALID_REQUEST", {"field_errors": ["id"]}) from None
        inquiry = self.session.scalar(
            select(Inquiry)
            .where(Inquiry.id == identity, inquiry_scope(user))
            .with_for_update(read=True)
        )
        if inquiry is None:
            self.audit("ACCESS_DENIED", user.id, error_code="FORBIDDEN")
            raise ApiError(403, "FORBIDDEN")
        no_input(body, query)
        if order:
            if inquiry.external_order_id is None:
                raise ApiError(422, "ORDER_REFERENCE_MISSING")
            raise ApiError(409, "CONTEXT_REQUIRED")
        return InquiryView.model_validate(inquiry)
