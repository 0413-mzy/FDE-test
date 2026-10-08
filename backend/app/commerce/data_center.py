"""Private, bounded, read-only business inspection with an explicit field policy."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select

from app.commerce.ai_models import AIAttempt  # noqa: F401
from app.commerce.catalog_models import Category  # noqa: F401
from app.commerce.errors import fail
from app.commerce.history import RecordHistory
from app.commerce.models import Base, ShopMembership
from app.commerce.onboarding_models import AccountProfile  # noqa: F401
from app.commerce.platform_models import PlatformRole  # noqa: F401
from app.commerce.platform_service import authorize

# Fixed reviewed names and fields: never expose all columns or reflect a client table.
FIELDS = {
    "commerce_account_profiles": (
        "account_id",
        "display_name",
        "phone",
        "email",
        "email_verified",
        "review_enabled",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_accounts": (
        "username",
        "active",
        "customer_enabled",
        "demo_enabled",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_address_book": (
        "customer_id",
        "address",
        "is_default",
        "active",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_address_revisions": (
        "order_id",
        "revision",
        "address_snapshot",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_after_sale_cases": (
        "order_id",
        "type",
        "state",
        "reason",
        "requested_amount_minor",
        "currency",
        "decision_reason",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_after_sale_lines": (
        "case_id",
        "order_id",
        "order_line_id",
        "quantity",
        "unit_price_minor_snapshot",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_cart_lines": (
        "cart_id",
        "sku_id",
        "quantity",
        "seen_price_version",
        "seen_price_minor",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_carts": ("customer_id", "id", "version", "created_at", "updated_at"),
    "commerce_checkouts": (
        "customer_id",
        "cart_id",
        "source_cart_version",
        "result_cart_version",
        "address_snapshot",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_conversations": (
        "customer_id",
        "shop_id",
        "order_id",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_inventory": (
        "sku_id",
        "on_hand",
        "reserved",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_merchant_applications": (
        "customer_id",
        "state",
        "shop_name",
        "business_scope",
        "contact_name",
        "contact_phone",
        "description",
        "decision_reason",
        "shop_id",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_messages": (
        "conversation_id",
        "sender_account_id",
        "sender_side",
        "body",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_order_lines": (
        "shop_id",
        "order_id",
        "sku_id",
        "product_title_snapshot",
        "options_snapshot",
        "unit_price_minor",
        "quantity",
        "shipped_qty",
        "refunded_unshipped_qty",
        "refunded_shipped_qty",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_orders": (
        "checkout_id",
        "customer_id",
        "shop_id",
        "status",
        "financial_status",
        "total_minor",
        "currency",
        "payment_deadline",
        "address_snapshot",
        "address_revision",
        "completed_at",
        "cancelled_at",
        "cancel_reason_code",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_payment_attempts": (
        "order_id",
        "amount_minor",
        "currency",
        "state",
        "simulation",
        "provider_reference",
        "finished_at",
        "failure_code",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_products": (
        "shop_id",
        "title",
        "description",
        "status",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_refund_attempts": (
        "after_sale_id",
        "amount_minor",
        "currency",
        "state",
        "simulation",
        "provider_reference",
        "finished_at",
        "failure_code",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_return_shipments": (
        "case_id",
        "tracking_number",
        "state",
        "restock",
        "registered_at",
        "received_at",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_shipment_lines": (
        "order_id",
        "shipment_id",
        "order_line_id",
        "quantity",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_shipments": (
        "order_id",
        "tracking_number",
        "exception_reason",
        "exception_from_status",
        "status",
        "simulation",
        "shipped_at",
        "delivered_at",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_shop_memberships": (
        "account_id",
        "shop_id",
        "role",
        "active",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_shops": ("name", "status", "id", "version", "created_at", "updated_at"),
    "commerce_skus": (
        "product_id",
        "shop_id",
        "sku_code",
        "options",
        "unit_price_minor",
        "currency",
        "price_version",
        "active",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_stock_movements": (
        "sku_id",
        "actor_id",
        "on_hand_delta",
        "reserved_delta",
        "reason",
        "related_record_id",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_stock_reservations": (
        "order_line_id",
        "quantity",
        "state",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_tracking_events": (
        "shipment_id",
        "event_id",
        "location",
        "reason",
        "actor_id",
        "status_applied",
        "request_version",
        "kind",
        "description",
        "occurred_at",
        "sequence",
        "source",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_categories": ("name", "active", "id", "version", "created_at", "updated_at"),
    "commerce_product_experiences": (
        "product_id",
        "category_id",
        "moderation_hidden",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_product_images": (
        "product_id",
        "position",
        "alt",
        "mime",
        "width",
        "height",
        "digest",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_favorites": (
        "customer_id",
        "product_id",
        "active",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_product_reviews": (
        "customer_id",
        "order_id",
        "order_line_id",
        "product_id",
        "shop_id",
        "rating",
        "body",
        "reply",
        "visible",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_platform_roles": (
        "account_id",
        "active",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_moderation_reports": (
        "reporter_id",
        "target_type",
        "target_id",
        "reason",
        "state",
        "decision_reason",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_moderation_actions": (
        "actor_id",
        "target_type",
        "target_id",
        "action",
        "reason",
        "report_id",
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_disputes": (
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
        "id",
        "version",
        "created_at",
        "updated_at",
    ),
    "commerce_ai_attempts": (
        "id",
        "cached_from",
        "conversation_id",
        "actor_id",
        "source_ids",
        "message_count",
        "model",
        "prompt_version",
        "state",
        "created_at",
        "finished_at",
        "result",
        "error_code",
        "usage",
    ),
}

LABELS = {
    "commerce_account_profiles": "账户资料",
    "commerce_accounts": "账户",
    "commerce_address_book": "地址簿",
    "commerce_address_revisions": "订单地址版本",
    "commerce_after_sale_cases": "售后申请",
    "commerce_after_sale_lines": "售后明细",
    "commerce_cart_lines": "购物袋明细",
    "commerce_carts": "购物袋",
    "commerce_checkouts": "结算",
    "commerce_conversations": "会话",
    "commerce_inventory": "库存",
    "commerce_merchant_applications": "商家入驻申请",
    "commerce_messages": "消息",
    "commerce_order_lines": "订单明细",
    "commerce_orders": "订单",
    "commerce_payment_attempts": "模拟支付",
    "commerce_products": "商品",
    "commerce_refund_attempts": "模拟退款",
    "commerce_return_shipments": "退货物流",
    "commerce_shipment_lines": "发货明细",
    "commerce_shipments": "发货",
    "commerce_shop_memberships": "店铺成员",
    "commerce_shops": "店铺",
    "commerce_skus": "商品规格",
    "commerce_stock_movements": "库存变动",
    "commerce_stock_reservations": "库存预留",
    "commerce_tracking_events": "物流事件",
    "commerce_categories": "商品分类",
    "commerce_product_experiences": "商品体验",
    "commerce_product_images": "商品图片元数据",
    "commerce_favorites": "收藏",
    "commerce_product_reviews": "商品评价",
    "commerce_platform_roles": "平台资格",
    "commerce_moderation_reports": "举报",
    "commerce_moderation_actions": "审核操作",
    "commerce_disputes": "争议",
    "commerce_ai_attempts": "AI生成尝试",
}


def private_authorize(svc):
    authorize(svc)
    if (
        svc.actor.customer_enabled
        or svc.actor.demo_enabled
        or svc.db.scalar(
            select(ShopMembership.id)
            .where(ShopMembership.account_id == svc.actor.id, ShopMembership.active.is_(True))
            .limit(1)
        )
    ):
        fail("CAPABILITY_REQUIRED", 403)


def resource(name):
    if name not in FIELDS:
        fail("NOT_FOUND", 404)
    return Base.metadata.tables[name]


def project(name, row):
    return {key: row[key] for key in FIELDS[name] if key in row} if row is not None else None


def bounds(params, allowed):
    if set(params) - allowed:
        fail("INVALID_REQUEST", 400)
    try:
        limit, offset = int(params.get("limit", "50")), int(params.get("offset", "0"))
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError
        return limit, offset
    except ValueError:
        fail("INVALID_REQUEST", 400)


def date_value(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    except ValueError:
        fail("INVALID_REQUEST", 400)


def identifier(value):
    try:
        return UUID(value)
    except ValueError:
        fail("INVALID_REQUEST", 400)


def directory(db):
    return {
        "items": [
            {
                "resource": name,
                "label": LABELS[name],
                "count": db.scalar(select(func.count()).select_from(resource(name))),
                "fields": list(fields),
                "history_mode": "attempt_lifecycle"
                if name == "commerce_ai_attempts"
                else "record_history",
            }
            for name, fields in FIELDS.items()
        ]
    }


def listing(db, name, params):
    table = resource(name)
    limit, offset = bounds(
        params, {"limit", "offset", "q", "id", "status", "from", "to", "field", "value"}
    )
    clauses = []
    if params.get("field") or params.get("value"):
        field = params.get("field")
        allowed = {
            fk.parent.name
            for fk in table.foreign_keys
            if fk.parent.name in FIELDS[name] and fk.column.table.name in FIELDS
        }
        if field not in allowed or not params.get("value"):
            fail("INVALID_REQUEST", 400)
        clauses.append(table.c[field] == identifier(params["value"]))
    if params.get("id"):
        clauses.append(table.c.id == identifier(params["id"]))
    if params.get("q"):
        value = params["q"]
        if len(value) > 200:
            fail("INVALID_REQUEST", 400)
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append(
            or_(
                *(
                    cast(table.c[k], String).ilike("%" + escaped + "%", escape="\\")
                    for k in FIELDS[name]
                )
            )
        )
    if params.get("status"):
        cols = [table.c[k] for k in ("status", "state", "financial_status") if k in FIELDS[name]]
        if not cols or len(params["status"]) > 80:
            fail("INVALID_REQUEST", 400)
        clauses.append(or_(*(col == params["status"] for col in cols)))
    for key, compare in [("from", lambda c, v: c >= v), ("to", lambda c, v: c <= v)]:
        if params.get(key):
            clauses.append(compare(table.c.created_at, date_value(params[key])))
    query = select(*(table.c[k] for k in FIELDS[name])).where(*clauses)
    items = (
        db.execute(
            query.order_by(table.c.created_at.desc(), table.c.id).limit(limit).offset(offset)
        )
        .mappings()
        .all()
    )
    total = db.scalar(select(func.count()).select_from(table).where(*clauses))
    return {"items": [dict(row) for row in items], "total": total, "limit": limit, "offset": offset}


def history(db, params, name=None, rid=None):
    limit, offset = bounds(
        params, {"limit", "offset", "resource", "id", "actor", "operation", "from", "to"}
    )
    table = RecordHistory.__table__
    clauses = [table.c.entity_table.in_(tuple(FIELDS))]
    name = name or params.get("resource")
    if name:
        resource(name)
        clauses.append(table.c.entity_table == name)
    if rid or params.get("id"):
        clauses.append(table.c.entity_id == identifier(rid or params["id"]))
    if params.get("actor"):
        if len(params["actor"]) > 80:
            fail("INVALID_REQUEST", 400)
        clauses.append(
            or_(
                table.c.actor_username == params["actor"],
                cast(table.c.actor_id, String) == params["actor"],
            )
        )
    if params.get("operation"):
        if params["operation"] not in ("BASELINE", "INSERT", "UPDATE", "DELETE"):
            fail("INVALID_REQUEST", 400)
        clauses.append(table.c.operation == params["operation"])
    for key, compare in [("from", lambda c, v: c >= v), ("to", lambda c, v: c <= v)]:
        if params.get(key):
            clauses.append(compare(table.c.recorded_at, date_value(params[key])))
    columns = (
        "id",
        "entity_table",
        "entity_id",
        "operation",
        "before_data",
        "after_data",
        "changed_fields",
        "actor_id",
        "actor_username",
        "request_id",
        "action",
        "reason",
        "recorded_at",
    )
    rows = (
        db.execute(
            select(*(table.c[k] for k in columns))
            .where(*clauses)
            .order_by(table.c.recorded_at.desc(), table.c.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    items = []
    for row in rows:
        item = dict(row)
        entity = row["entity_table"]
        item["before_data"] = project(entity, row["before_data"])
        item["after_data"] = project(entity, row["after_data"])
        item["changed_fields"] = [k for k in row["changed_fields"] if k in FIELDS[entity]]
        items.append(item)
    return {
        "items": items,
        "total": db.scalar(select(func.count()).select_from(table).where(*clauses)),
        "limit": limit,
        "offset": offset,
    }


def detail(db, name, rid, params):
    table = resource(name)
    uid = identifier(rid)
    bounds(params, {"limit", "offset"})
    row = (
        db.execute(select(*(table.c[k] for k in FIELDS[name])).where(table.c.id == uid))
        .mappings()
        .first()
    )
    entries = history(db, params, name, rid)
    if row is None and not entries["total"]:
        fail("NOT_FOUND", 404)
    related = {}
    # Composite constraints may include tenant/shop scope components. Only the
    # component referencing the target primary ID is a navigable record link.
    if row:
        for constraint in table.foreign_key_constraints:
            for fk in constraint.elements:
                target = fk.column.table.name
                field = fk.parent.name
                if (
                    fk.column.name == "id"
                    and target in FIELDS
                    and field in row
                    and row[field] is not None
                ):
                    key = ("parent", target, field)
                    related[key] = {
                        "resource": target,
                        "id": str(row[field]),
                        "field": field,
                        "direction": "parent",
                    }
        for target in FIELDS:
            for constraint in resource(target).foreign_key_constraints:
                for fk in constraint.elements:
                    field = fk.parent.name
                    if (
                        fk.column.table.name == name
                        and fk.column.name == "id"
                        and field in FIELDS[target]
                    ):
                        key = ("children", target, field)
                        related[key] = {
                            "resource": target,
                            "filter": {"field": field, "value": str(uid)},
                            "field": field,
                            "direction": "children",
                        }
    return {
        "resource": name,
        "record": dict(row) if row else None,
        "deleted": row is None,
        "fields": list(FIELDS[name]),
        "related": [related[key] for key in sorted(related)],
        "history": entries,
        "history_mode": "attempt_lifecycle" if name == "commerce_ai_attempts" else "record_history",
    }
