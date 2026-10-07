"""Persistent conversation and after-sales domain operations under Commerce write mutex."""

from datetime import timedelta

from sqlalchemy import select

from app.commerce import inputs as inp
from app.commerce import views
from app.commerce.errors import fail
from app.commerce.models import (
    AfterSaleCase,
    AfterSaleLine,
    Conversation,
    Inventory,
    Message,
    Order,
    OrderLine,
    PaymentAttempt,
    RefundAttempt,
    ReturnShipment,
    Shipment,
    ShipmentLine,
    Shop,
)

TERMINAL = {"REJECTED", "CANCELLED", "COMPLETED"}


def active(db, order, kind=None):
    return [
        c
        for c in views.rows(db, AfterSaleCase, order_id=order.id)
        if c.state not in TERMINAL and (kind is None or c.type == kind)
    ]


def conversation_create(svc, body):
    inp.fields(body, ["shop_id", "order_id"])
    shop = svc.get(Shop, inp.identifier(body["shop_id"]))
    oid = None if body["order_id"] is None else inp.identifier(body["order_id"])
    if oid:
        order = svc.own_order(oid)
        if order.shop_id != shop.id:
            fail("NOT_FOUND", 404)
    old = svc.db.scalar(
        select(Conversation).filter_by(customer_id=svc.actor.id, shop_id=shop.id, order_id=oid)
    )
    if old is None and oid is None and shop.status != "ACTIVE":
        fail("INVALID_STATE")
    row = old or svc.new(Conversation, customer_id=svc.actor.id, shop_id=shop.id, order_id=oid)
    return views.conversation(row), 200 if old else 201


def message_create(svc, row, body, merchant):
    inp.fields(body, ["body"])
    message = svc.new(
        Message,
        conversation_id=row.id,
        sender_account_id=svc.actor.id,
        sender_side="MERCHANT" if merchant else "CUSTOMER",
        body=inp.string(body["body"], 1, 2000),
    )
    return views.message(message), 201


def create_case(svc, order, body):
    from app.commerce.platform_service import ensure_unfrozen

    ensure_unfrozen(svc, order.id)
    inp.fields(body, ["expected_version", "type", "reason", "lines"])
    svc.version(order, body)
    kind = body["type"]
    if not isinstance(kind, str) or kind not in {"UNSHIPPED_REFUND", "RETURN_REFUND"}:
        fail("INVALID_REQUEST", 400)
    reason = inp.string(body["reason"], 1, 500)
    selected = inp.selection(body["lines"])
    if active(svc.db, order):
        fail("ACTIVE_CASE_EXISTS")
    if order.financial_status not in {"PAID", "PARTIALLY_REFUNDED"}:
        fail("INVALID_STATE")
    lines = {line.id: line for line in views.rows(svc.db, OrderLine, order_id=order.id)}
    amount = 0
    for lid, qty in selected:
        if lid not in lines:
            fail("NOT_FOUND", 404)
        line = lines[lid]
        available = (
            line.quantity - line.shipped_qty - line.refunded_unshipped_qty
            if kind == "UNSHIPPED_REFUND"
            else line.shipped_qty - line.refunded_shipped_qty
        )
        if qty > available:
            fail("QUANTITY_CONFLICT")
        if kind == "RETURN_REFUND":
            shipments = [
                svc.get(Shipment, sl.shipment_id)
                for sl in views.rows(svc.db, ShipmentLine, order_line_id=lid)
            ]
            if not shipments or any(s.status != "DELIVERED" for s in shipments):
                fail("INVALID_STATE")
            if svc.now > max(s.delivered_at for s in shipments) + timedelta(days=14):
                fail("RETURN_WINDOW_EXPIRED")
        amount += qty * line.unit_price_minor
    case = svc.new(
        AfterSaleCase,
        order_id=order.id,
        type=kind,
        state="REQUESTED",
        reason=reason,
        requested_amount_minor=amount,
        currency="CNY",
    )
    for lid, qty in selected:
        svc.new(
            AfterSaleLine,
            case_id=case.id,
            order_id=order.id,
            order_line_id=lid,
            quantity=qty,
            unit_price_minor_snapshot=lines[lid].unit_price_minor,
        )
    svc.bump(order)
    return views.case(svc.db, case), 201


def case_action(svc, order, case, action, body):
    from app.commerce.platform_service import ensure_unfrozen

    ensure_unfrozen(svc, order.id)
    required = {
        "decision": ["decision", "reason"],
        "return": ["tracking_number"],
        "receive-return": ["restock"],
    }.get(action, [])
    inp.fields(body, ["expected_version", *required])
    svc.version(case, body)
    if action == "withdraw":
        if case.state not in {"REQUESTED", "AWAITING_RETURN"}:
            fail("INVALID_STATE")
        case.state = "CANCELLED"
    elif action == "decision":
        decision = body["decision"]
        if not isinstance(decision, str) or decision not in {"APPROVE", "REJECT"}:
            fail("INVALID_REQUEST", 400)
        reason = inp.string(body["reason"], 1, 500)
        if case.state != "REQUESTED":
            fail("INVALID_STATE")
        case.decision_reason = reason
        case.state = (
            "REJECTED"
            if decision == "REJECT"
            else "REFUND_PENDING"
            if case.type == "UNSHIPPED_REFUND"
            else "AWAITING_RETURN"
        )
    elif action == "return":
        tracking = inp.string(body["tracking_number"], 1, 100)
        if case.type != "RETURN_REFUND" or case.state != "AWAITING_RETURN":
            fail("INVALID_STATE")
        svc.new(
            ReturnShipment,
            case_id=case.id,
            tracking_number=tracking,
            state="IN_TRANSIT",
            registered_at=svc.now,
        )
        case.state = "RETURN_IN_TRANSIT"
    elif action == "receive-return":
        restock = inp.boolean(body["restock"])
        if case.type != "RETURN_REFUND" or case.state != "RETURN_IN_TRANSIT":
            fail("INVALID_STATE")
        ret = views.rows(svc.db, ReturnShipment, case_id=case.id)[0]
        ret.state, ret.restock, ret.received_at = "RECEIVED", restock, svc.now
        svc.bump(ret)
        if restock:
            restock_lines(svc, case, "RETURN_RESTOCK")
        case.state = "REFUND_PENDING"
    elif action == "refunds":
        if case.state != "REFUND_PENDING" or any(
            a.state in {"PENDING", "SUCCEEDED"}
            for a in views.rows(svc.db, RefundAttempt, after_sale_id=case.id)
        ):
            fail("INVALID_STATE")
        attempt = svc.new(
            RefundAttempt,
            after_sale_id=case.id,
            amount_minor=case.requested_amount_minor,
            currency="CNY",
            state="PENDING",
            simulation=True,
        )
        svc.bump(case)
        svc.bump(order)
        return views.attempt(attempt), 201
    else:
        fail("NOT_FOUND", 404)
    svc.bump(case)
    svc.bump(order)
    return views.case(svc.db, case), 200


def restock_lines(svc, case, reason):
    rows = [
        (svc.get(OrderLine, line.order_line_id), line.quantity)
        for line in views.rows(svc.db, AfterSaleLine, case_id=case.id)
    ]
    for line, qty in sorted(rows, key=lambda pair: pair[0].sku_id):
        inv = views.rows(svc.db, Inventory, sku_id=line.sku_id)[0]
        svc.db.refresh(inv, with_for_update=True)
        svc.movement(inv, qty, 0, reason, case.id)


def refund_result(svc, attempt, body):
    inp.fields(body, ["expected_version", "result", "event_id"])
    inp.integer(body["expected_version"])
    eid = inp.string(body["event_id"], 1, 100)
    result = body["result"]
    if not isinstance(result, str) or result not in {"SUCCEEDED", "FAILED"}:
        fail("INVALID_REQUEST", 400)

    def apply():
        case = svc.get(AfterSaleCase, attempt.after_sale_id, True)
        order = svc.get(Order, case.order_id, True)
        from app.commerce.platform_service import ensure_unfrozen

        ensure_unfrozen(svc, order.id)
        svc.version(attempt, body)
        if (
            attempt.state != "PENDING"
            or case.state != "REFUND_PENDING"
            or attempt.amount_minor != case.requested_amount_minor
        ):
            fail("INVALID_STATE")
        if result == "SUCCEEDED":
            cases = views.rows(svc.db, AfterSaleCase, order_id=order.id)
            total = (
                sum(
                    a.amount_minor
                    for c in cases
                    for a in views.rows(svc.db, RefundAttempt, after_sale_id=c.id)
                    if a.state == "SUCCEEDED"
                )
                + attempt.amount_minor
            )
            paid = sum(
                a.amount_minor
                for a in views.rows(svc.db, PaymentAttempt, order_id=order.id)
                if a.state == "SUCCEEDED"
            )
            if total > paid:
                fail("QUANTITY_CONFLICT")
            for selected in views.rows(svc.db, AfterSaleLine, case_id=case.id):
                line = svc.get(OrderLine, selected.order_line_id)
                if case.type == "UNSHIPPED_REFUND":
                    if (
                        selected.quantity
                        > line.quantity - line.shipped_qty - line.refunded_unshipped_qty
                    ):
                        fail("QUANTITY_CONFLICT")
                    line.refunded_unshipped_qty += selected.quantity
                else:
                    if selected.quantity > line.shipped_qty - line.refunded_shipped_qty:
                        fail("QUANTITY_CONFLICT")
                    line.refunded_shipped_qty += selected.quantity
                svc.bump(line)
            if case.type == "UNSHIPPED_REFUND":
                restock_lines(svc, case, "UNSHIPPED_REFUND_RESTOCK")
                lines = views.rows(svc.db, OrderLine, order_id=order.id)
                if all(line.quantity == line.refunded_unshipped_qty for line in lines):
                    order.status = "CANCELLED"
                    order.cancelled_at = svc.now
                    order.cancel_reason_code = "ALL_UNSHIPPED_REFUNDED"
                elif (
                    all(
                        line.shipped_qty == line.quantity - line.refunded_unshipped_qty
                        for line in lines
                    )
                    and order.status != "COMPLETED"
                ):
                    order.status = "SHIPPED"
            order.financial_status = "REFUNDED" if total == paid else "PARTIALLY_REFUNDED"
            case.state = "COMPLETED"
        attempt.state = result
        attempt.finished_at = svc.now
        attempt.provider_reference = eid
        attempt.failure_code = "SIMULATED_REFUND_FAILURE" if result == "FAILED" else None
        svc.bump(attempt)
        svc.bump(case)
        svc.bump(order)
        return {
            "id": str(attempt.id),
            "state": result,
            "version": attempt.version,
            "simulation": True,
        }, 200

    return svc.event_result("SIMULATED_REFUND", attempt, eid, {"result": result}, apply)
