"""Human controlled simulated carrier facts and bounded state transitions."""

from sqlalchemy import select

from app.commerce import inputs as inp
from app.commerce import views
from app.commerce.errors import fail
from app.commerce.models import Order, TrackingEvent

STAGES = ("SHIPPED", "COLLECTED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED")
REASONS = {"TRANSPORT_DELAY", "DELIVERY_FAILED"}


def transition(shipment, kind, reason):
    """Validate before writing; delivery and customer receipt remain independent."""
    current = shipment.status
    if current == "DELIVERED":
        fail("INVALID_STATE")
    if kind == "EXCEPTION":
        allowed = (
            reason == "TRANSPORT_DELAY"
            and current in {"COLLECTED", "IN_TRANSIT"}
            or reason == "DELIVERY_FAILED"
            and current == "OUT_FOR_DELIVERY"
        )
        if not allowed:
            fail("INVALID_STATE")
        shipment.exception_reason = reason
        shipment.exception_from_status = current
    elif current == "EXCEPTION":
        restore = (
            "OUT_FOR_DELIVERY"
            if shipment.exception_reason == "DELIVERY_FAILED"
            else shipment.exception_from_status or "IN_TRANSIT"
        )
        if kind != restore:
            fail("INVALID_STATE")
        shipment.exception_reason = None
        shipment.exception_from_status = None
    elif not (
        current == "IN_TRANSIT"
        and kind == "IN_TRANSIT"
        or current in STAGES[:-1]
        and kind == STAGES[STAGES.index(current) + 1]
    ):
        fail("INVALID_STATE")
    shipment.status = kind


def record(svc, shipment, body):
    required = {"expected_version", "event_id", "kind", "description", "occurred_at"}
    if (
        not isinstance(body, dict)
        or not required <= set(body)
        or set(body) - required - {"location", "reason"}
    ):
        fail("INVALID_REQUEST", 400)
    expected = inp.integer(body["expected_version"])
    event_id = inp.string(body["event_id"], 1, 100)
    kind = body["kind"]
    if not isinstance(kind, str) or kind not in set(STAGES[1:]) | {"EXCEPTION"}:
        fail("INVALID_REQUEST", 400)
    description = inp.string(body["description"], 1, 500)
    location = inp.string(body["location"], 1, 200) if body.get("location") is not None else None
    reason = body.get("reason")
    if reason is not None and (not isinstance(reason, str) or reason not in REASONS):
        fail("INVALID_REQUEST", 400)
    if (kind == "EXCEPTION") != (reason is not None):
        fail("INVALID_REQUEST", 400)
    occurred = inp.timestamp(body["occurred_at"])

    def apply():
        svc.version(shipment, body)
        events = views.rows(svc.db, TrackingEvent, shipment_id=shipment.id)
        latest = max(e.occurred_at for e in events)
        if occurred < shipment.shipped_at or occurred > svc.now:
            fail("INVALID_EVENT_ORDER")
        applied = occurred >= latest
        if not applied:
            # Late facts only supplement stages honestly present in recorded history.
            # Exception/recovery facts must pass current-state validation instead.
            if kind == "EXCEPTION" or kind not in {
                e.kind for e in events if e.status_applied is not False
            }:
                fail("INVALID_STATE")
        else:
            transition(shipment, kind, reason)
            if kind == "DELIVERED":
                shipment.delivered_at = occurred
        svc.bump(shipment)
        svc.new(
            TrackingEvent,
            shipment_id=shipment.id,
            event_id=event_id,
            kind=kind,
            description=description,
            occurred_at=occurred,
            sequence=max(e.sequence for e in events) + 1,
            source="SIMULATED_CARRIER",
            actor_id=svc.actor.id,
            location=location,
            reason=reason,
            status_applied=applied,
            request_version=expected,
        )
        # An appended fact changes the customer/merchant order representation too.
        order = svc.get(Order, shipment.order_id, True)
        svc.bump(order)
        return {
            "id": str(shipment.id),
            "status": shipment.status,
            "version": shipment.version,
            "simulation": True,
            "status_applied": applied,
        }, 200

    payload = {
        "kind": kind,
        "description": description,
        "occurred_at": views.iso(occurred),
        "location": location,
        "reason": reason,
    }
    old = svc.db.scalar(select(TrackingEvent).filter_by(event_id=event_id))
    if old is not None and old.request_version is None and not {"location", "reason"} & set(body):
        # Historical callbacks hashed only the three original fact fields.
        payload.pop("location")
        payload.pop("reason")
    return svc.event_result("SIMULATED_CARRIER", shipment, event_id, payload, apply)
