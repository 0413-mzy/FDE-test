"""Authorized, bounded logistics facts. No customer or payment projection."""

import hashlib
import json
import re

from sqlalchemy import func, select

from app.commerce.ai_provider import redact
from app.commerce.errors import fail
from app.commerce.models import Order, Shipment, TrackingEvent

MAX_SHIPMENTS = 5
MAX_EVENTS = 8


def sanitize_known(value, secrets=()):
    if value is None:
        return None
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            value = value.replace(secret, "[私人资料]")
    value = redact(value)
    value = re.sub(
        r"(?<![A-Za-z0-9])[A-Za-z0-9_-]{8,}(?![A-Za-z0-9])",
        lambda match: "[标识已省略]" if any(char.isdigit() for char in match[0]) else match[0],
        value,
    )
    value = re.sub(r"(?:地址|住址|姓名|收件人|联系人)\s*[:：]\s*[^，,;；\n]+", "[私人资料]", value)
    return "".join(c for c in value if c.isprintable())


def safe_text(value, secrets=()):
    safe = sanitize_known(value, secrets)
    return safe[:200] if safe is not None else None


def stamp(value):
    return value.isoformat() if value else None


def _logistics_snapshot(db, conversation):
    if conversation.order_id is None:
        context = {"state": "NO_LINKED_ORDER", "order": None, "shipments": [], "source_ids": []}
        return context, fingerprint(context)
    order = db.scalar(
        select(Order).where(
            Order.id == conversation.order_id,
            Order.customer_id == conversation.customer_id,
            Order.shop_id == conversation.shop_id,
        )
    )
    if order is None:
        fail("NOT_FOUND", 404)
    query = select(Shipment).where(Shipment.order_id == order.id)
    shipments = db.scalars(
        query.order_by(Shipment.shipped_at, Shipment.id).limit(MAX_SHIPMENTS)
    ).all()
    count = db.scalar(
        select(func.count()).select_from(Shipment).where(Shipment.order_id == order.id)
    )
    # PostgreSQL aggregates every dependency, including facts outside the visible bounds.
    dependency = db.execute(
        select(func.count(), func.max(Shipment.updated_at), func.sum(Shipment.version)).where(
            Shipment.order_id == order.id
        )
    ).one()
    events_dependency = db.execute(
        select(func.count(), func.max(TrackingEvent.updated_at), func.sum(TrackingEvent.version))
        .join(Shipment, Shipment.id == TrackingEvent.shipment_id)
        .where(Shipment.order_id == order.id)
    ).one()
    secrets = [v for v in (order.address_snapshot or {}).values() if isinstance(v, str)]
    secrets.extend(
        db.scalars(select(Shipment.tracking_number).where(Shipment.order_id == order.id)).all()
    )
    sources = ["order:" + str(order.id)]
    parcels = []
    for shipment in shipments:
        events = db.scalars(
            select(TrackingEvent)
            .where(TrackingEvent.shipment_id == shipment.id)
            .order_by(TrackingEvent.sequence.desc(), TrackingEvent.id.desc())
            .limit(MAX_EVENTS)
        ).all()
        event_count = db.scalar(
            select(func.count())
            .select_from(TrackingEvent)
            .where(TrackingEvent.shipment_id == shipment.id)
        )
        source = "shipment:" + str(shipment.id)
        sources.append(source)
        timeline = []
        for event in reversed(events):
            ref = "tracking:" + str(event.id)
            sources.append(ref)
            timeline.append(
                dict(
                    source_id=ref,
                    kind=event.kind,
                    description=safe_text(event.description, secrets),
                    location=safe_text(event.location, secrets),
                    reason=event.reason,
                    source=event.source,
                    occurred_at=stamp(event.occurred_at),
                    received_at=stamp(event.created_at),
                    status_applied=event.status_applied,
                    version=event.version,
                )
            )
        parcels.append(
            dict(
                source_id=source,
                id=str(shipment.id),
                status=shipment.status,
                version=shipment.version,
                simulation=shipment.simulation,
                source="SIMULATED_CARRIER" if shipment.simulation else None,
                shipped_at=stamp(shipment.shipped_at),
                delivered_at=stamp(shipment.delivered_at),
                exception_reason=shipment.exception_reason,
                exception_from_status=shipment.exception_from_status,
                events=timeline,
                event_count=event_count,
                events_truncated=event_count > MAX_EVENTS,
            )
        )
    context = dict(
        state="LINKED_ORDER" if count else "NO_SHIPMENTS",
        order=dict(
            source_id=sources[0], id=str(order.id), status=order.status, version=order.version
        ),
        shipments=parcels,
        shipment_count=count,
        shipments_truncated=count > MAX_SHIPMENTS,
        source_ids=sources,
        limits=dict(shipments=MAX_SHIPMENTS, events_per_shipment=MAX_EVENTS),
        eta=None,
    )
    dependencies = [list(dependency), list(events_dependency)]
    return context, fingerprint([context, dependencies])


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def dependency_fence(db, conversation):
    order = db.execute(
        select(Order.version, Order.status).where(
            Order.id == conversation.order_id,
            Order.customer_id == conversation.customer_id,
            Order.shop_id == conversation.shop_id,
        )
    ).one_or_none()
    shipments = db.execute(
        select(func.count(), func.max(Shipment.updated_at), func.sum(Shipment.version)).where(
            Shipment.order_id == conversation.order_id
        )
    ).one()
    events = db.execute(
        select(func.count(), func.max(TrackingEvent.updated_at), func.sum(TrackingEvent.version))
        .join(Shipment, Shipment.id == TrackingEvent.shipment_id)
        .where(Shipment.order_id == conversation.order_id)
    ).one()
    return [list(order) if order else None, list(shipments), list(events)]


def logistics_snapshot(db, conversation):
    if conversation.order_id is None:
        return _logistics_snapshot(db, conversation)
    # A version fence retries mixed READ COMMITTED observations without business locks.
    for _ in range(3):
        before = dependency_fence(db, conversation)
        context, digest = _logistics_snapshot(db, conversation)
        if before == dependency_fence(db, conversation):
            return context, digest
        db.expire_all()
    fail("AI_BUSY", 409)


def input_secrets(db, conversation):
    if conversation.order_id is None:
        return []
    order = db.scalar(
        select(Order).where(
            Order.id == conversation.order_id,
            Order.customer_id == conversation.customer_id,
            Order.shop_id == conversation.shop_id,
        )
    )
    if order is None:
        fail("NOT_FOUND", 404)
    return [
        value for value in (order.address_snapshot or {}).values() if isinstance(value, str)
    ] + db.scalars(select(Shipment.tracking_number).where(Shipment.order_id == order.id)).all()
