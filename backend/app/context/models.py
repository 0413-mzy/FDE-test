"""Closed immutable authorized context contracts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from app.integrations.models import CanonicalModel, Nonblank, UtcTimestamp

Operation = Literal["get_inquiry", "get_order", "get_parcels", "get_shipment", "get_notes"]
Outcome = Literal[
    "SUCCESS",
    "EMPTY",
    "NOT_FOUND",
    "NO_TRACKING",
    "TIMEOUT",
    "UNAVAILABLE",
    "INVALID_RESPONSE",
    "REJECTED",
    "CONFLICT",
]
EvidenceId = Annotated[str, Field(pattern=r"^ev-[0-9a-f]{64}$")]
PositiveSeconds = Annotated[int, Field(gt=0)]


class SourceAges(CanonicalModel):
    order: PositiveSeconds = 86400
    parcel: PositiveSeconds = 86400
    warehouse_note: PositiveSeconds = 86400
    shipment: PositiveSeconds = 21600
    shipment_event: PositiveSeconds = 21600


class FreshnessPolicy(CanonicalModel):
    version: Literal["freshness-v1"] = "freshness-v1"
    fetch_max_age_seconds: PositiveSeconds = 1800
    source_max_age_seconds: SourceAges = Field(default_factory=SourceAges)


class Evidence(CanonicalModel):
    id: EvidenceId
    kind: Literal["FACT", "SOURCE_TEXT"]
    source_system: Nonblank
    source_record_id: Nonblank
    snapshot_id: UUID
    snapshot_version: Annotated[int, Field(gt=0)]
    pointer: Annotated[str, Field(pattern=r"^/records/\d+/")]
    value: JsonValue
    source_updated_at: UtcTimestamp | None
    fetched_at: UtcTimestamp
    occurred_at: UtcTimestamp | None
    freshness_status: Literal["FRESH", "STALE", "UNKNOWN"]


class AuthorizationScope(CanonicalModel):
    inquiry_id: UUID
    external_order_id: Nonblank
    team_id: UUID
    assigned_agent_id: UUID


class Question(CanonicalModel):
    text: Nonblank
    source_system: Nonblank
    source_record_id: Nonblank
    created_at: UtcTimestamp


class ContextOrder(CanonicalModel):
    external_order_id: Nonblank
    status_evidence_id: EvidenceId


class ContextParcel(CanonicalModel):
    parcel_id: Nonblank
    tracking_number_evidence_id: EvidenceId | None
    shipment_status_evidence_id: EvidenceId | None
    event_evidence_ids: list[EvidenceId]


class SourceOutcome(CanonicalModel):
    fetch_id: UUID
    operation: Operation
    target_id: Nonblank
    outcome: Outcome
    error_code: str | None
    fetched_at: UtcTimestamp | None


class Unknown(CanonicalModel):
    code: Literal["UNKNOWN_SOURCE_TIME", "UNKNOWN_STATUS", "CLOCK_ANOMALY", "OLD_FETCH"]
    evidence_ids: list[EvidenceId]


class MissingInformation(CanonicalModel):
    code: Literal[
        "NO_PARCELS",
        "NO_EVENTS",
        "NO_WAREHOUSE_NOTES",
        "NO_TRACKING",
        "SOURCE_NOT_FOUND",
        "SOURCE_TIMEOUT",
        "SOURCE_UNAVAILABLE",
        "SOURCE_INVALID_RESPONSE",
        "SOURCE_REJECTED",
        "SOURCE_CONFLICT",
    ]
    scope: Nonblank
    evidence_ids: list[EvidenceId]


class Conflict(CanonicalModel):
    id: Nonblank
    code: Literal["INCOMPATIBLE_EVENT_STATUS", "POSSIBLE_HANDOVER_CONFLICT"]
    evidence_ids: list[EvidenceId]
    explanation: Nonblank


class CaseContext(CanonicalModel):
    schema_version: Literal["core-mvp-v1"] = "core-mvp-v1"
    context_id: UUID
    inquiry_id: UUID
    run_id: UUID
    context_version: Annotated[int, Field(gt=0)]
    created_at: UtcTimestamp
    policy_version: Literal["core-policy-v1"] = "core-policy-v1"
    freshness_policy: FreshnessPolicy
    authorization_scope: AuthorizationScope
    question: Question
    order: ContextOrder
    parcels: list[ContextParcel]
    source_outcomes: list[SourceOutcome]
    evidence: list[Evidence]
    facts: list[EvidenceId]
    source_texts: list[EvidenceId]
    unknowns: list[Unknown]
    missing_information: list[MissingInformation]
    conflicts: list[Conflict]
    quality: Literal["COMPLETE", "DEGRADED"]
    risk_flags: list[
        Literal[
            "STALE_DATA",
            "UNKNOWN_FRESHNESS",
            "PARTIAL_SOURCE_FAILURE",
            "MISSING_INFORMATION",
            "CONFLICTING_SOURCES",
            "UNKNOWN_STATUS",
            "CLOCK_ANOMALY",
        ]
    ]

    @model_validator(mode="after")
    def references_are_local(self):
        evidence = {e.id: e for e in self.evidence}
        if len(evidence) != len(self.evidence):
            raise ValueError("Duplicate evidence identity")
        if (
            self.inquiry_id != self.authorization_scope.inquiry_id
            or self.order.external_order_id != self.authorization_scope.external_order_id
        ):
            raise ValueError("Context authorization mismatch")
        if (
            len(self.facts + self.source_texts) != len(self.evidence)
            or len(set(self.facts + self.source_texts)) != len(self.evidence)
            or set(self.facts + self.source_texts) != set(evidence)
        ):
            raise ValueError("Evidence partition must cover each evidence exactly once")
        if any(evidence[k].kind != "FACT" for k in self.facts) or any(
            evidence[k].kind != "SOURCE_TEXT" for k in self.source_texts
        ):
            raise ValueError("Invalid evidence partition")
        refs = [self.order.status_evidence_id]
        for p in self.parcels:
            refs += [
                r for r in (p.tracking_number_evidence_id, p.shipment_status_evidence_id) if r
            ] + p.event_evidence_ids
        for item in [*self.unknowns, *self.missing_information, *self.conflicts]:
            refs += item.evidence_ids
        if not set(refs) <= set(evidence):
            raise ValueError("Cross-context evidence reference")
        fetches = {f.fetch_id for f in self.source_outcomes if f.outcome == "SUCCESS"}
        if any(
            e.snapshot_id not in fetches or e.snapshot_version != self.context_version
            for e in self.evidence
        ):
            raise ValueError("Evidence snapshot/version mismatch")
        if any(len(set(c.evidence_ids)) < 2 for c in self.conflicts):
            raise ValueError("Conflict requires distinct evidence")
        return self
