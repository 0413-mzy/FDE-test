"""Closed platform operations; all writes share the commerce transaction mutex."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.commerce import after_sales, views
from app.commerce import inputs as inp
from app.commerce.catalog_models import Category, ProductExperience, ProductReview
from app.commerce.errors import fail
from app.commerce.models import (
    AfterSaleCase,
    AfterSaleLine,
    CommerceAccount,
    Order,
    OrderLine,
    PaymentAttempt,
    Product,
    RefundAttempt,
    Shipment,
    ShipmentLine,
    Shop,
    ShopMembership,
)
from app.commerce.platform_models import Dispute, ModerationAction, ModerationReport, PlatformRole

SAFE = {
    CommerceAccount: ("username", "active", "customer_enabled", "demo_enabled"),
    Shop: ("name", "status"),
    Product: ("shop_id", "title", "description", "status"),
    ProductReview: ("product_id", "shop_id", "rating", "body", "reply", "visible"),
    Category: ("name", "active"),
    ModerationReport: (
        "reporter_id",
        "target_type",
        "target_id",
        "reason",
        "state",
        "decision_reason",
    ),
    ModerationAction: ("actor_id", "target_type", "target_id", "action", "reason", "report_id"),
    Dispute: (
        "customer_id",
        "order_id",
        "case_id",
        "shop_id",
        "reason",
        "state",
        "customer_evidence",
        "merchant_evidence",
        "decision_reason",
        "decided_by",
    ),
}


def dto(row, svc=None):
    from uuid import UUID

    def val(v):
        return str(v) if isinstance(v, UUID) else v.isoformat() if isinstance(v, datetime) else v

    result = {
        k: val(getattr(row, k))
        for k in ("id", "version", "created_at", "updated_at", *SAFE[type(row)])
    }
    if isinstance(row, Product):
        exp = svc.db.scalar(select(ProductExperience).where(ProductExperience.product_id == row.id))
        result["moderation_hidden"] = bool(exp and exp.moderation_hidden)
    if isinstance(row, Dispute):
        case = svc.get(AfterSaleCase, row.case_id)
        result["case_state"] = case.state
        result["can_refund"] = (
            row.state == "OVERTURNED"
            and case.state == "REFUND_PENDING"
            and not any(
                a.state in {"PENDING", "SUCCEEDED"}
                for a in views.rows(svc.db, RefundAttempt, after_sale_id=case.id)
            )
        )
    return result


def enabled(svc):
    return bool(
        svc.db.scalar(
            select(PlatformRole).where(
                PlatformRole.account_id == svc.actor.id, PlatformRole.active.is_(True)
            )
        )
    )


def authorize(svc):
    svc.auth()
    if not enabled(svc):
        fail("CAPABILITY_REQUIRED", 403)


def ensure_unfrozen(svc, order_id):
    if svc.db.scalar(
        select(Dispute.id).where(Dispute.order_id == order_id, Dispute.state == "OPEN")
    ):
        fail("DISPUTE_OPEN")


def listing(svc, cls, filters=()):
    params = svc.request.query_params
    if len(params.multi_items()) != len(params):
        fail("INVALID_REQUEST", 400)
    if set(params) - {"offset", "limit"}:
        fail("INVALID_REQUEST", 400)
    try:
        offset = int(params.get("offset", "0"))
        limit = int(params.get("limit", "30"))
    except ValueError:
        fail("INVALID_REQUEST", 400)
    if offset < 0 or not 1 <= limit <= 100:
        fail("INVALID_REQUEST", 400)
    q = select(cls).where(*filters)
    total = svc.db.scalar(select(func.count()).select_from(q.subquery()))
    rows = svc.db.scalars(
        q.order_by(cls.created_at.desc(), cls.id).offset(offset).limit(limit)
    ).all()
    return dict(
        items=[dto(r, svc) for r in rows],
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + limit < total,
    )


def target(svc, kind, identifier, public=False):
    if not isinstance(kind, str):
        fail("INVALID_REQUEST", 400)
    cls = {
        "PRODUCT": Product,
        "SHOP": Shop,
        "REVIEW": ProductReview,
        "ACCOUNT": CommerceAccount,
    }.get(kind)
    if cls is None or public and kind == "ACCOUNT":
        fail("INVALID_REQUEST", 400)
    row = svc.get(cls, identifier, svc.write)
    if public:
        if kind == "SHOP":
            visible = row.status == "ACTIVE"
        else:
            product = row if kind == "PRODUCT" else svc.get(Product, row.product_id)
            exp = svc.db.scalar(
                select(ProductExperience).where(ProductExperience.product_id == product.id)
            )
            visible = (
                product.status == "PUBLISHED"
                and svc.get(Shop, product.shop_id).status == "ACTIVE"
                and not (exp and exp.moderation_hidden)
                and (kind != "REVIEW" or row.visible)
            )
        if not visible:
            fail("NOT_FOUND", 404)
    return row


def moderation(svc, payload, report=None):
    inp.fields(payload, ["target_type", "target_id", "expected_version", "action", "reason"])
    row = target(svc, payload["target_type"], inp.identifier(payload["target_id"]))
    svc.version(row, payload)
    reason = inp.string(payload["reason"], 1, 1000)
    action = payload["action"]
    kind = payload["target_type"]
    allowed = {
        "PRODUCT": {"WARN", "HIDE_PRODUCT", "RESTORE_PRODUCT"},
        "REVIEW": {"WARN", "HIDE_REVIEW", "RESTORE_REVIEW"},
        "SHOP": {"WARN", "SUSPEND_SHOP", "RESTORE_SHOP"},
        "ACCOUNT": {"WARN", "SUSPEND_ACCOUNT", "RESTORE_ACCOUNT"},
    }
    if not isinstance(action, str) or action not in allowed[kind]:
        fail("INVALID_REQUEST", 400)
    if kind == "ACCOUNT" and svc.db.scalar(
        select(PlatformRole.id).where(PlatformRole.account_id == row.id)
    ):
        fail("PLATFORM_ACCOUNT_PROTECTED", 403)
    if action in {"HIDE_PRODUCT", "RESTORE_PRODUCT"}:
        exp = svc.db.scalar(select(ProductExperience).where(ProductExperience.product_id == row.id))
        if exp is None:
            exp = svc.new(
                ProductExperience, product_id=row.id, category_id=None, moderation_hidden=False
            )
        exp.moderation_hidden = action == "HIDE_PRODUCT"
        svc.bump(exp)
    elif action in {"HIDE_REVIEW", "RESTORE_REVIEW"}:
        row.visible = action == "RESTORE_REVIEW"
    elif action in {"SUSPEND_SHOP", "RESTORE_SHOP"}:
        row.status = "SUSPENDED" if action == "SUSPEND_SHOP" else "ACTIVE"
    elif action in {"SUSPEND_ACCOUNT", "RESTORE_ACCOUNT"}:
        row.active = action == "RESTORE_ACCOUNT"
    svc.bump(row)
    return dto(
        svc.new(
            ModerationAction,
            actor_id=svc.actor.id,
            target_type=kind,
            target_id=row.id,
            action=action,
            reason=reason,
            report_id=report.id if report else None,
        )
    ), 201


def report_create(svc, payload):
    inp.fields(payload, ["target_type", "target_id", "reason"])
    row = target(svc, payload["target_type"], inp.identifier(payload["target_id"]), True)
    if svc.db.scalar(
        select(ModerationReport.id).where(
            ModerationReport.reporter_id == svc.actor.id,
            ModerationReport.target_type == payload["target_type"],
            ModerationReport.target_id == row.id,
            ModerationReport.state == "OPEN",
        )
    ):
        fail("ACTIVE_REPORT_EXISTS")
    return dto(
        svc.new(
            ModerationReport,
            reporter_id=svc.actor.id,
            target_type=payload["target_type"],
            target_id=row.id,
            reason=inp.string(payload["reason"], 1, 1000),
            state="OPEN",
        )
    ), 201


def dispute_create(svc, order, case, payload):
    inp.fields(payload, ["expected_version", "reason"])
    svc.version(case, payload)
    ensure_unfrozen(svc, order.id)
    if case.state != "REJECTED" and not (
        case.state == "REQUESTED" and svc.now >= case.created_at + timedelta(hours=48)
    ):
        fail("DISPUTE_NOT_ELIGIBLE")
    if any(c.id != case.id for c in after_sales.active(svc.db, order)):
        fail("ACTIVE_CASE_EXISTS")
    return dto(
        svc.new(
            Dispute,
            customer_id=svc.actor.id,
            order_id=order.id,
            case_id=case.id,
            shop_id=order.shop_id,
            reason=inp.string(payload["reason"], 1, 2000),
            state="OPEN",
            customer_evidence="",
            merchant_evidence="",
        ),
        svc,
    ), 201


def approval_checks(svc, order, case):
    if any(c.id != case.id for c in after_sales.active(svc.db, order)):
        fail("ACTIVE_CASE_EXISTS")
    if order.financial_status not in {"PAID", "PARTIALLY_REFUNDED"}:
        fail("INVALID_STATE")
    paid = sum(
        a.amount_minor
        for a in views.rows(svc.db, PaymentAttempt, order_id=order.id)
        if a.state == "SUCCEEDED"
    )
    cases = views.rows(svc.db, AfterSaleCase, order_id=order.id)
    refunded = sum(
        a.amount_minor
        for c in cases
        for a in views.rows(svc.db, RefundAttempt, after_sale_id=c.id)
        if a.state in {"PENDING", "SUCCEEDED"}
    )
    selected = views.rows(svc.db, AfterSaleLine, case_id=case.id)
    if not selected or refunded + case.requested_amount_minor > paid:
        fail("QUANTITY_CONFLICT")
    amount = 0
    for sl in selected:
        line = svc.get(OrderLine, sl.order_line_id, True)
        available = (
            line.quantity - line.shipped_qty - line.refunded_unshipped_qty
            if case.type == "UNSHIPPED_REFUND"
            else line.shipped_qty - line.refunded_shipped_qty
        )
        if sl.quantity > available or sl.unit_price_minor_snapshot != line.unit_price_minor:
            fail("QUANTITY_CONFLICT")
        if case.type == "RETURN_REFUND":
            shipments = [
                svc.get(Shipment, s.shipment_id)
                for s in views.rows(svc.db, ShipmentLine, order_line_id=line.id)
            ]
            if not shipments or any(
                s.status != "DELIVERED" or not s.delivered_at for s in shipments
            ):
                fail("INVALID_STATE")
            if case.created_at > max(s.delivered_at for s in shipments) + timedelta(days=14):
                fail("RETURN_WINDOW_EXPIRED")
        amount += sl.quantity * line.unit_price_minor
    if amount != case.requested_amount_minor:
        fail("QUANTITY_CONFLICT")


def dispute_action(svc, row, op, payload, merchant=False):
    required = ["expected_version"] + (
        ["body"] if op == "evidence" else ["decision", "reason"] if op == "decision" else []
    )
    inp.fields(payload, required)
    svc.version(row, payload)
    order = svc.get(Order, row.order_id, True)
    case = svc.get(AfterSaleCase, row.case_id, True)
    if op == "refunds":
        if order.customer_id == svc.actor.id or svc.db.scalar(
            select(ShopMembership.id).where(
                ShopMembership.account_id == svc.actor.id, ShopMembership.shop_id == order.shop_id
            )
        ):
            fail("SELF_ARBITRATION_FORBIDDEN", 403)
        if row.state != "OVERTURNED":
            fail("INVALID_STATE")
        ensure_unfrozen(svc, order.id)
        result = after_sales.case_action(
            svc, order, case, "refunds", {"expected_version": case.version}
        )
        svc.bump(row)
        return result
    if row.state != "OPEN":
        fail("INVALID_STATE")
    if op == "evidence":
        text = inp.string(payload["body"], 1, 2000)
        field = "merchant_evidence" if merchant else "customer_evidence"
        previous = getattr(row, field)
        if len(previous) + len(text) > 10000:
            fail("EVIDENCE_LIMIT", 400)
        setattr(row, field, previous + "\n" + text if previous else text)
    elif op == "withdraw":
        row.state = "WITHDRAWN"
    elif op == "decision":
        if order.customer_id == svc.actor.id or svc.db.scalar(
            select(ShopMembership.id).where(
                ShopMembership.account_id == svc.actor.id, ShopMembership.shop_id == order.shop_id
            )
        ):
            fail("SELF_ARBITRATION_FORBIDDEN", 403)
        decision = payload["decision"]
        reason = inp.string(payload["reason"], 1, 2000)
        if not isinstance(decision, str) or decision not in {"UPHOLD", "APPROVE"}:
            fail("INVALID_REQUEST", 400)
        if case.state not in {"REJECTED", "REQUESTED"}:
            fail("INVALID_STATE")
        if decision == "APPROVE":
            approval_checks(svc, order, case)
            case.state = "REFUND_PENDING" if case.type == "UNSHIPPED_REFUND" else "AWAITING_RETURN"
        else:
            case.state = "REJECTED"
        case.decision_reason = reason
        row.state = "OVERTURNED" if decision == "APPROVE" else "UPHELD"
        row.decision_reason = reason
        row.decided_by = svc.actor.id
        svc.bump(case)
        svc.bump(order)
    svc.bump(row)
    return dto(row, svc), 200


assert_no_open_dispute = ensure_unfrozen


def analytics(svc, shop_id=None):
    params = svc.request.query_params
    if len(params.multi_items()) != len(params) or set(params) - {
        "start",
        "end",
        "shop_id",
        "offset",
        "limit",
    }:
        fail("INVALID_REQUEST", 400)
    try:
        start = datetime.fromisoformat(params["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(params["end"].replace("Z", "+00:00"))
        offset = int(params.get("offset", "0"))
        limit = int(params.get("limit", "30"))
    except (KeyError, ValueError):
        fail("INVALID_REQUEST", 400)
    if (
        not start.tzinfo
        or not end.tzinfo
        or not start < end
        or end - start > timedelta(days=366)
        or offset < 0
        or not 1 <= limit <= 100
    ):
        fail("INVALID_REQUEST", 400)
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if shop_id and "shop_id" in params and inp.identifier(params["shop_id"]) != shop_id:
        fail("NOT_FOUND", 404)
    if not shop_id and params.get("shop_id"):
        shop_id = inp.identifier(params["shop_id"])
        svc.get(Shop, shop_id)

    def scoped(sid):
        return [Order.shop_id == sid] if sid else []

    payment_base = (
        select(PaymentAttempt)
        .join(Order, Order.id == PaymentAttempt.order_id)
        .where(
            PaymentAttempt.state == "SUCCEEDED",
            PaymentAttempt.finished_at >= start,
            PaymentAttempt.finished_at < end,
        )
    )
    refund_base = (
        select(RefundAttempt)
        .join(AfterSaleCase, AfterSaleCase.id == RefundAttempt.after_sale_id)
        .join(Order, Order.id == AfterSaleCase.order_id)
        .where(
            RefundAttempt.state == "SUCCEEDED",
            RefundAttempt.finished_at >= start,
            RefundAttempt.finished_at < end,
        )
    )

    def amount(base, model, sid):
        sub = base.where(*scoped(sid)).with_only_columns(model.amount_minor).subquery()
        return svc.db.scalar(select(func.coalesce(func.sum(sub.c.amount_minor), 0)))

    def metrics(sid):
        paid = amount(payment_base, PaymentAttempt, sid)
        refunded = amount(refund_base, RefundAttempt, sid)
        created = svc.db.scalar(
            select(func.count())
            .select_from(Order)
            .where(*scoped(sid), Order.created_at >= start, Order.created_at < end)
        )
        completed = svc.db.scalar(
            select(func.count())
            .select_from(Order)
            .where(*scoped(sid), Order.completed_at >= start, Order.completed_at < end)
        )
        return dict(
            payment_total_minor=paid,
            refund_total_minor=refunded,
            net_total_minor=paid - refunded,
            orders_created=created,
            orders_completed=completed,
        )

    daily = {}
    for base, model, field in [
        (payment_base, PaymentAttempt, "payment_total_minor"),
        (refund_base, RefundAttempt, "refund_total_minor"),
    ]:
        day = func.date(func.timezone("UTC", model.finished_at))
        rows = svc.db.execute(
            base.where(*scoped(shop_id))
            .with_only_columns(day.label("day"), func.sum(model.amount_minor).label("amount"))
            .group_by(day)
            .order_by(day)
        ).all()
        for date, amount_minor in rows:
            key = date.isoformat()
            row = daily.setdefault(
                key, dict(date=key, payment_total_minor=0, refund_total_minor=0, net_total_minor=0)
            )
            row[field] = amount_minor
    for row in daily.values():
        row["net_total_minor"] = row["payment_total_minor"] - row["refund_total_minor"]

    def backlog(states):
        return svc.db.scalar(
            select(func.count())
            .select_from(Order)
            .where(*scoped(shop_id), Order.status.in_(states))
        )

    active_cases = svc.db.scalar(
        select(func.count())
        .select_from(AfterSaleCase)
        .join(Order, Order.id == AfterSaleCase.order_id)
        .where(*scoped(shop_id), AfterSaleCase.state.not_in(after_sales.TERMINAL))
    )
    selected_shops = (
        select(Shop.id)
        .where(*([Shop.id == shop_id] if shop_id else []))
        .order_by(Shop.id)
        .offset(offset)
        .limit(limit + 1)
    )
    shop_ids = svc.db.scalars(selected_shops).all()
    shops_more = len(shop_ids) > limit
    shops = [dict(shop_id=str(sid), **metrics(sid)) for sid in shop_ids[:limit]]
    payment_exists = (
        select(PaymentAttempt.id)
        .where(PaymentAttempt.order_id == Order.id, PaymentAttempt.state == "SUCCEEDED")
        .exists()
    )
    sales_query = (
        select(
            Order.shop_id,
            OrderLine.sku_id,
            func.sum(OrderLine.quantity),
            func.sum(OrderLine.refunded_unshipped_qty),
            func.sum(OrderLine.refunded_shipped_qty),
        )
        .join(Order, Order.id == OrderLine.order_id)
        .where(*scoped(shop_id), Order.created_at >= start, Order.created_at < end, payment_exists)
        .group_by(Order.shop_id, OrderLine.sku_id)
        .order_by(Order.shop_id, OrderLine.sku_id)
        .offset(offset)
        .limit(limit + 1)
    )
    sale_rows = svc.db.execute(sales_query).all()
    sales_more = len(sale_rows) > limit
    sales = [
        dict(
            shop_id=str(sid),
            sku_id=str(sku),
            purchased_quantity=qty,
            refunded_unshipped_quantity=unshipped,
            refunded_shipped_quantity=shipped,
        )
        for sid, sku, qty, unshipped, shipped in sale_rows[:limit]
    ]
    return dict(
        simulation=True,
        currency="CNY",
        start=start.isoformat(),
        end=end.isoformat(),
        shop_id=str(shop_id) if shop_id else None,
        **metrics(shop_id),
        backlog=dict(
            unpaid=backlog(["PENDING_PAYMENT"]),
            awaiting_shipment=backlog(["READY_TO_SHIP", "PARTIALLY_SHIPPED"]),
            in_transit=backlog(["SHIPPED", "PARTIALLY_SHIPPED"]),
            after_sales=active_cases,
        ),
        daily=sorted(daily.values(), key=lambda d: d["date"]),
        shops=shops,
        sales=sales,
        offset=offset,
        limit=limit,
        shops_has_more=shops_more,
        sales_has_more=sales_more,
        sales_basis=(
            "Orders created in interval with successful payment; "
            "refund quantities are current cumulative totals"
        ),
        backlog_basis="Current state at query time",
    )


def eligibility(svc, order, case):
    opened = bool(
        svc.db.scalar(
            select(Dispute.id).where(Dispute.order_id == order.id, Dispute.state == "OPEN")
        )
    )
    eligible = case.state == "REJECTED" or (
        case.state == "REQUESTED" and svc.now >= case.created_at + timedelta(hours=48)
    )
    conflict = any(c.id != case.id for c in after_sales.active(svc.db, order))
    reason = (
        "DISPUTE_OPEN"
        if opened
        else "ACTIVE_CASE_EXISTS"
        if conflict
        else "DISPUTE_NOT_ELIGIBLE"
        if not eligible
        else None
    )
    return dict(can_dispute=reason is None, dispute_open=opened, reason=reason)


def dispute_context(svc, row):
    case = svc.get(AfterSaleCase, row.case_id)
    order = svc.get(Order, row.order_id)
    cases = views.rows(svc.db, AfterSaleCase, order_id=order.id)
    paid = sum(
        a.amount_minor
        for a in views.rows(svc.db, PaymentAttempt, order_id=order.id)
        if a.state == "SUCCEEDED"
    )
    refunded = sum(
        a.amount_minor
        for c in cases
        for a in views.rows(svc.db, RefundAttempt, after_sale_id=c.id)
        if a.state == "SUCCEEDED"
    )
    lines = []
    for selected in views.rows(svc.db, AfterSaleLine, case_id=case.id):
        line = svc.get(OrderLine, selected.order_line_id)
        lines.append(
            dict(
                title=line.product_title_snapshot,
                quantity=selected.quantity,
                unit_price_minor=selected.unit_price_minor_snapshot,
                shipped_qty=line.shipped_qty,
                refunded_unshipped_qty=line.refunded_unshipped_qty,
                refunded_shipped_qty=line.refunded_shipped_qty,
            )
        )
    returns = views.rows(svc.db, after_sales.ReturnShipment, case_id=case.id)
    return dict(
        case_type=case.type,
        state=case.state,
        reason=case.reason,
        merchant_decision_reason=case.decision_reason,
        requested_amount_minor=case.requested_amount_minor,
        currency=case.currency,
        financial_status=order.financial_status,
        paid_minor=paid,
        refunded_minor=refunded,
        lines=lines,
        return_state=returns[0].state if returns else None,
    )
