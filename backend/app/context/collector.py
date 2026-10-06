"""One attempt per source operation; no fallback or hidden source reads."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from app.core.clock import Clock
from app.integrations.errors import (
    ExternalConflict,
    ExternalError,
    ExternalInvalidResponse,
    ExternalNotFound,
    ExternalRejected,
    ExternalTimeout,
    ExternalUnavailable,
)
from app.integrations.models import (
    OrderSnapshot,
    ParcelSnapshot,
    ShipmentSnapshot,
    SupportInquiry,
    WarehouseNoteSnapshot,
)
from app.integrations.providers import (
    LogisticsProvider,
    MessageProvider,
    OrderProvider,
    WarehouseProvider,
)


@dataclass(frozen=True)
class ProviderBundle:
    order: OrderProvider
    logistics: LogisticsProvider
    warehouse: WarehouseProvider
    message: MessageProvider
    support_source_system: str = "demo_support"


@dataclass(frozen=True)
class FetchRecord:
    id: UUID
    operation: str
    target_id: str
    source_system: str
    outcome: str
    started_at: datetime
    completed_at: datetime
    fetched_at: datetime | None
    error_code: str | None
    payload: dict | None


@dataclass(frozen=True)
class Collection:
    fetches: list[FetchRecord]
    error_code: str | None

    @property
    def run_state(self) -> str:
        if self.error_code:
            return "FAILED"
        return (
            "PARTIAL"
            if any(f.outcome not in ("SUCCESS", "EMPTY") for f in self.fetches)
            else "SUCCEEDED"
        )


ERROR_OUTCOMES = {
    ExternalNotFound: "NOT_FOUND",
    ExternalTimeout: "TIMEOUT",
    ExternalUnavailable: "UNAVAILABLE",
    ExternalInvalidResponse: "INVALID_RESPONSE",
    ExternalRejected: "REJECTED",
    ExternalConflict: "CONFLICT",
}


class BindingMismatch(ValueError):
    pass


def validate_records(operation: str, records: list, target_id: str, external_order_id: str) -> None:
    """Canonical shape and ownership are required before saving any payload."""
    expected = {
        "get_inquiry": SupportInquiry,
        "get_order": OrderSnapshot,
        "get_parcels": ParcelSnapshot,
        "get_shipment": ShipmentSnapshot,
        "get_notes": WarehouseNoteSnapshot,
    }[operation]
    if operation in ("get_inquiry", "get_order", "get_shipment") and len(records) != 1:
        raise ValueError("Single record required")
    seen = set()
    for record in records:
        if not isinstance(record, expected):
            raise ValueError("Canonical result required")
        expected.model_validate_json(record.model_dump_json(warnings="error"))
        if hasattr(record, "external_order_id") and record.external_order_id != external_order_id:
            raise BindingMismatch("Order binding mismatch")
        if operation == "get_inquiry" and record.inquiry_id != target_id:
            raise BindingMismatch("Inquiry binding mismatch")
        if operation == "get_shipment":
            if record.parcel_id != target_id:
                raise ValueError("Parcel binding mismatch")
            event_ids = set()
            for event in record.events:
                identity = (event.source_system, event.source_record_id)
                if event.parcel_id != target_id or identity in event_ids:
                    raise ValueError("Event binding or identity mismatch")
                event_ids.add(identity)
        identity = (
            record.parcel_id
            if operation == "get_parcels"
            else record.note_id
            if operation == "get_notes"
            else getattr(record, "source_record_id", target_id)
        )
        source_identity = (
            getattr(record, "source_system", "support"),
            getattr(record, "source_record_id", identity),
        )
        if identity in seen or source_identity in seen:
            raise ValueError("Duplicate canonical identity")
        seen.update((identity, source_identity))


async def collect(
    providers: ProviderBundle,
    external_inquiry_id: str,
    external_order_id: str,
    clock: Clock,
    request_id: str,
) -> Collection:
    fetches = []
    binding_mismatch = False
    if not external_order_id or not external_order_id.strip():
        return Collection(fetches, "ORDER_REFERENCE_MISSING")

    async def read(
        operation: str, target_id: str, service: str, call: Callable[[], Awaitable]
    ) -> list | None:
        nonlocal binding_mismatch
        started = clock.now()
        try:
            result = await call()
            if operation in ("get_parcels", "get_notes") and not isinstance(result, list):
                raise ValueError("Array operation requires an array")
            records = result if isinstance(result, list) else [result]
            validate_records(operation, records, target_id, external_order_id)
            completed = clock.now()
            source = (
                records[0].source_system
                if records and hasattr(records[0], "source_system")
                else service
            )
            fetches.append(
                FetchRecord(
                    uuid4(),
                    operation,
                    target_id,
                    source,
                    "SUCCESS" if records else "EMPTY",
                    started,
                    completed,
                    records[0].fetched_at
                    if records and hasattr(records[0], "fetched_at")
                    else completed,
                    None,
                    {"records": [r.model_dump(mode="json") for r in records]},
                )
            )
            return records
        except (
            ExternalError,
            ValidationError,
            ValueError,
            TypeError,
            AttributeError,
            PydanticSerializationError,
        ) as exc:
            binding_mismatch = operation == "get_inquiry" and isinstance(exc, BindingMismatch)
            outcome = next(
                (value for cls, value in ERROR_OUTCOMES.items() if isinstance(exc, cls)),
                "INVALID_RESPONSE",
            )
            fetches.append(
                FetchRecord(
                    uuid4(),
                    operation,
                    target_id,
                    service,
                    outcome,
                    started,
                    clock.now(),
                    None,
                    outcome,
                    None,
                )
            )
            return None

    inquiry = await read(
        "get_inquiry",
        external_inquiry_id,
        providers.support_source_system,
        lambda: providers.message.get_inquiry(external_inquiry_id, request_id=request_id),
    )
    if inquiry is None:
        return Collection(
            fetches,
            "SOURCE_BINDING_MISMATCH" if binding_mismatch else "SOURCE_" + fetches[-1].outcome,
        )
    order = await read(
        "get_order",
        external_order_id,
        "order",
        lambda: providers.order.get_order(external_order_id, request_id=request_id),
    )
    if order is None:
        return Collection(fetches, "SOURCE_" + fetches[-1].outcome)
    parcels = await read(
        "get_parcels",
        external_order_id,
        "order",
        lambda: providers.order.get_parcels(external_order_id, request_id=request_id),
    )
    if parcels is None:
        return Collection(fetches, "SOURCE_" + fetches[-1].outcome)
    for parcel in parcels:
        if parcel.tracking_number is None:
            stamp = clock.now()
            fetches.append(
                FetchRecord(
                    uuid4(),
                    "get_shipment",
                    parcel.parcel_id,
                    "logistics",
                    "NO_TRACKING",
                    stamp,
                    stamp,
                    None,
                    "NO_TRACKING",
                    None,
                )
            )
        else:
            await read(
                "get_shipment",
                parcel.parcel_id,
                "logistics",
                lambda parcel=parcel: providers.logistics.get_shipment(
                    parcel, request_id=request_id
                ),
            )
    await read(
        "get_notes",
        external_order_id,
        "warehouse",
        lambda: providers.warehouse.get_notes(external_order_id, request_id=request_id),
    )
    return Collection(fetches, None)
