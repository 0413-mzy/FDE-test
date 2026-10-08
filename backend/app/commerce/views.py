"""Explicit DTO projections; never serialize ORM/private identity data."""

from sqlalchemy import select

from app.commerce.models import (
    SKU,
    AfterSaleCase,
    AfterSaleLine,
    CartLine,
    Inventory,
    Order,
    OrderLine,
    PaymentAttempt,
    Product,
    RefundAttempt,
    ReturnShipment,
    Shipment,
    ShipmentLine,
    Shop,
    ShopMembership,
    TrackingEvent,
)


def rows(db, cls, **filters):
    query = select(cls).filter_by(**filters).order_by(cls.created_at, cls.id)
    return list(db.scalars(query))


def iso(value):
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def membership(db, member):
    shop = db.get(Shop, member.shop_id)
    return {
        "shop_id": str(shop.id),
        "shop_name": shop.name,
        "role": member.role,
        "shop_status": shop.status,
    }


def account(db, actor):
    return {
        "id": str(actor.id),
        "username": actor.username,
        "customer_enabled": actor.customer_enabled,
        "demo_enabled": actor.demo_enabled,
        "shops": [
            membership(db, m) for m in rows(db, ShopMembership, account_id=actor.id, active=True)
        ],
    }


def inventory(row):
    return {
        "sku_id": str(row.sku_id),
        "on_hand": row.on_hand,
        "reserved": row.reserved,
        "available": row.on_hand - row.reserved,
        "version": row.version,
    }


def sku(db, row, merchant=False):
    inv = rows(db, Inventory, sku_id=row.id)[0]
    result = {
        "id": str(row.id),
        "sku_code": row.sku_code,
        "options": row.options,
        "unit_price_minor": row.unit_price_minor,
        "currency": row.currency,
        "price_version": row.price_version,
        "active": row.active,
        "available": inv.on_hand - inv.reserved,
    }
    if merchant:
        result["version"] = row.version
    return result


def product(db, row, merchant=False):
    shop = db.get(Shop, row.shop_id)
    return {
        "id": str(row.id),
        "shop_id": str(shop.id),
        "shop_name": shop.name,
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "version": row.version,
        "skus": [
            sku(db, s, merchant) for s in rows(db, SKU, product_id=row.id) if merchant or s.active
        ],
    }


def purchasable(db, s):
    p = db.get(Product, s.product_id)
    from app.commerce.catalog_models import ProductExperience

    info = db.scalar(select(ProductExperience).where(ProductExperience.product_id == p.id))
    return (
        s.active
        and p.status == "PUBLISHED"
        and db.get(Shop, p.shop_id).status == "ACTIVE"
        and not (info and info.moderation_hidden)
    )


def cart(db, row):
    lines = []
    for line in rows(db, CartLine, cart_id=row.id):
        s = db.get(SKU, line.sku_id)
        inv = rows(db, Inventory, sku_id=s.id)[0]
        lines.append(
            {
                "sku_id": str(s.id),
                "product_title": db.get(Product, s.product_id).title,
                "shop_name": db.get(Shop, s.shop_id).name,
                "options": s.options,
                "shop_id": str(s.shop_id),
                "quantity": line.quantity,
                "seen_price_version": line.seen_price_version,
                "seen_price_minor": line.seen_price_minor,
                "current_price_version": s.price_version,
                "current_price_minor": s.unit_price_minor,
                "currency": s.currency,
                "available": inv.on_hand - inv.reserved,
                "purchasable": purchasable(db, s),
            }
        )
    return {"id": str(row.id), "version": row.version, "lines": lines}


def expired(order, now):
    return order.status == "PENDING_PAYMENT" and now >= order.payment_deadline


def summary(row, now, db=None):
    return {
        "id": str(row.id),
        "shop_id": str(row.shop_id),
        "shop_name": db.get(Shop, row.shop_id).name if db else None,
        "status": row.status,
        "financial_status": row.financial_status,
        "total_minor": row.total_minor,
        "currency": row.currency,
        "version": row.version,
        "created_at": iso(row.created_at),
        "payment_deadline": iso(row.payment_deadline),
        "payment_expired": expired(row, now),
    }


def attempt(row):
    return {
        "id": str(row.id),
        "state": row.state,
        "version": row.version,
        "amount_minor": row.amount_minor,
        "currency": row.currency,
        "simulation": True,
        "created_at": iso(row.created_at),
        "finished_at": iso(row.finished_at),
        "failure_code": row.failure_code,
    }


def shipment(db, row):
    return {
        "id": str(row.id),
        "order_id": str(row.order_id),
        "tracking_number": row.tracking_number,
        "status": row.status,
        "version": row.version,
        "simulation": True,
        "shipped_at": iso(row.shipped_at),
        "delivered_at": iso(row.delivered_at),
        "exception_reason": row.exception_reason,
        "exception_from_status": row.exception_from_status,
        "lines": [
            {"order_line_id": str(line.order_line_id), "quantity": line.quantity}
            for line in rows(db, ShipmentLine, shipment_id=row.id)
        ],
        "events": [
            {
                "id": str(e.id),
                "event_id": e.event_id,
                "kind": e.kind,
                "description": e.description,
                "occurred_at": iso(e.occurred_at),
                "sequence": e.sequence,
                "source": e.source,
                "created_at": iso(e.created_at),
                "location": e.location,
                "reason": e.reason,
                "actor_id": str(e.actor_id) if e.actor_id else None,
                "status_applied": e.status_applied,
                "request_version": e.request_version,
            }
            for e in sorted(rows(db, TrackingEvent, shipment_id=row.id), key=lambda e: e.sequence)
        ],
    }


def order(db, row, now, merchant=False):
    return summary(row, now, db) | {
        "checkout_id": None if merchant else str(row.checkout_id),
        "lines": [
            {
                "id": str(line.id),
                "sku_id": str(line.sku_id),
                "title": line.product_title_snapshot,
                "options": line.options_snapshot,
                "unit_price_minor": line.unit_price_minor,
                "quantity": line.quantity,
                "shipped_qty": line.shipped_qty,
                "refunded_unshipped_qty": line.refunded_unshipped_qty,
                "refunded_shipped_qty": line.refunded_shipped_qty,
            }
            for line in rows(db, OrderLine, order_id=row.id)
        ],
        "address": row.address_snapshot,
        "address_revision": row.address_revision,
        "shipments": [shipment(db, s) for s in rows(db, Shipment, order_id=row.id)],
        "payment_attempts": [attempt(a) for a in rows(db, PaymentAttempt, order_id=row.id)],
        "after_sale_cases": [case(db, c) for c in rows(db, AfterSaleCase, order_id=row.id)],
        "completed_at": iso(row.completed_at),
        "cancel_reason_code": row.cancel_reason_code,
        "cancelled_at": iso(row.cancelled_at),
    }


def checkout(db, row, now):
    orders = rows(db, Order, checkout_id=row.id)
    return {
        "id": str(row.id),
        "order_ids": [str(o.id) for o in orders],
        "orders": [summary(o, now, db) for o in orders],
        "cart_version": row.result_cart_version,
    }


def conversation(row):
    return {
        "id": str(row.id),
        "shop_id": str(row.shop_id),
        "customer_id": str(row.customer_id),
        "order_id": str(row.order_id) if row.order_id else None,
        "version": row.version,
        "created_at": iso(row.created_at),
    }


def message(row):
    return {
        "id": str(row.id),
        "conversation_id": str(row.conversation_id),
        "sender_side": row.sender_side,
        "body": row.body,
        "created_at": iso(row.created_at),
    }


def case(db, row):
    returns = rows(db, ReturnShipment, case_id=row.id)
    ret = returns[0] if returns else None
    return {
        "id": str(row.id),
        "order_id": str(row.order_id),
        "type": row.type,
        "state": row.state,
        "version": row.version,
        "reason": row.reason,
        "requested_amount_minor": row.requested_amount_minor,
        "currency": row.currency,
        "created_at": iso(row.created_at),
        "decision_reason": row.decision_reason,
        "lines": [
            {"order_line_id": str(line.order_line_id), "quantity": line.quantity}
            for line in rows(db, AfterSaleLine, case_id=row.id)
        ],
        "return_shipment": {
            "tracking_number": ret.tracking_number,
            "state": ret.state,
            "restock": ret.restock,
            "registered_at": iso(ret.registered_at),
            "received_at": iso(ret.received_at),
        }
        if ret
        else None,
        "refund_attempts": [attempt(a) for a in rows(db, RefundAttempt, after_sale_id=row.id)],
    }


def demo_shipment(db, row):
    """Carrier console deliberately omits order/customer/address/line records."""
    result = shipment(db, row)
    return {key: value for key, value in result.items() if key not in {"order_id", "lines"}}
