"""Closed Stage 3 wire models; secret inputs are never used in error details."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)


class LoginInput(ClosedModel):
    username: str = Field(pattern=r"^[A-Za-z0-9._-]{3,64}$", min_length=3, max_length=64)
    password: str = Field(
        min_length=1, max_length=128, repr=False, json_schema_extra={"writeOnly": True}
    )


class Pagination(ClosedModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("limit", "offset", mode="before")
    @classmethod
    def query_integer(cls, value):
        if isinstance(value, str):
            if not re.fullmatch(r"[0-9]{1,10}", value):
                raise ValueError("Expected a nonnegative integer")
            return int(value)
        return value


class UserView(ClosedModel):
    id: UUID
    username: str
    role: Literal["AGENT", "SUPERVISOR", "ADMIN"]
    team_id: UUID | None


class LoginView(ClosedModel):
    token: str = Field(repr=False)
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: datetime
    user: UserView


class InquirySummary(ClosedModel):
    id: UUID
    external_inquiry_id: str
    external_order_id: str | None
    state: Literal["OPEN", "CONTEXT_READY", "DRAFTED", "APPROVED", "ESCALATED"]
    lock_version: int
    current_context_id: UUID | None
    current_draft_id: UUID | None
    latest_run_id: UUID | None
    created_at: datetime
    updated_at: datetime


class InquiryView(InquirySummary):
    escalation_reason: str | None


class InquiryList(ClosedModel):
    items: list[InquirySummary]
    limit: int
    offset: int
    total: int


class ResolveInput(ClosedModel):
    expected_lock_version: int = Field(gt=0)


class ResolveView(ClosedModel):
    run_id: UUID
    state: Literal["RUNNING", "SUCCEEDED", "PARTIAL", "FAILED"]
    context_id: UUID | None
    context_version: int | None
    quality: Literal["COMPLETE", "DEGRADED"] | None
    lock_version: int
