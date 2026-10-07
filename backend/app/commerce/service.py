"""Short atomic commerce transactions. A bounded schema-local PG mutex serializes MVP writes.

The mutex avoids reverse aggregate acquisition during whole-order expiry. Authority
rows are checked under locks after mutex acquisition. No network runs under locks.
"""

import hashlib
import json
import re
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, text

from app.commerce import after_sales, views
from app.commerce import inputs as inp
from app.commerce.errors import CommerceError, fail
from app.commerce.models import (
    SKU,
    AddressRevision,
    BusinessAudit,
    Cart,
    CartLine,
    Checkout,
    CommerceAccount,
    CommerceSession,
    IdempotencyRecord,
    Inventory,
    Order,
    OrderLine,
    PaymentAttempt,
    Product,
    Shipment,
    ShipmentLine,
    Shop,
    ShopMembership,
    SimulationEvent,
    StockMovement,
    StockReservation,
    TrackingEvent,
)
from app.core.security import bearer_token, new_token, password_matches, token_digest

ORDER_STATES = {
    "PENDING_PAYMENT",
    "READY_TO_SHIP",
    "PARTIALLY_SHIPPED",
    "SHIPPED",
    "COMPLETED",
    "CANCELLED",
}


def digest(body):
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def normalize(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    return value


class Commerce:
    def __init__(self, db, clock, request, write=False):
        self.db = db
        self.clock = clock
        self.request = request
        self.write = write
        self.actor = None
        self.shop = None
        self.now = clock.now()
        self.request_id = request.state.request_id
        if write:
            self.acquire_write()

    def acquire_write(self):
        self.db.execute(text("SET LOCAL lock_timeout='2000ms'"))
        self.db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(current_schema() || '-commerce-v1',0))"
            )
        )
        self.write = True
        self.now = self.clock.now()

    def new(self, cls, **values):
        obj = cls(id=uuid4(), version=1, created_at=self.now, updated_at=self.now, **values)
        self.db.add(obj)
        self.db.flush()
        return obj

    def bump(self, row):
        row.version += 1
        row.updated_at = self.now

    def get(self, cls, identifier, lock=False):
        row = self.db.scalar(
            select(cls)
            .where(cls.id == identifier)
            .with_for_update()
            .execution_options(populate_existing=True)
            if lock
            else select(cls).where(cls.id == identifier)
        )
        if row is None:
            fail("NOT_FOUND", 404)
        return row

    def auth(self, capability=None, shop_id=None, owner=False):
        token = bearer_token(self.request.headers.get("authorization"))
        if not token:
            fail("UNAUTHENTICATED", 401)
        query = select(CommerceSession).where(CommerceSession.token_digest == token_digest(token))
        if self.write:
            query = query.with_for_update().execution_options(populate_existing=True)
        session = self.db.scalar(query)
        if session is None or session.revoked_at or session.expires_at <= self.clock.now():
            fail("UNAUTHENTICATED", 401)
        actor = self.get(CommerceAccount, session.account_id, self.write)
        if not actor.active:
            fail("UNAUTHENTICATED", 401)
        self.actor = actor
        self.session = session
        if (
            capability == "customer"
            and not actor.customer_enabled
            or capability == "demo"
            and not actor.demo_enabled
        ):
            fail("CAPABILITY_REQUIRED", 403)
        if capability == "merchant":
            members = views.rows(self.db, ShopMembership, account_id=actor.id, active=True)
            if not members or owner and not any(m.role == "OWNER" for m in members):
                fail("CAPABILITY_REQUIRED", 403)
            if shop_id is not None:
                member = next((m for m in members if m.shop_id == shop_id), None)
                if member is None:
                    fail("NOT_FOUND", 404)
                if self.write:
                    self.db.refresh(member, with_for_update=True)
                    if not member.active:
                        fail("NOT_FOUND", 404)
                if owner and member.role != "OWNER":
                    fail("CAPABILITY_REQUIRED", 403)
                self.shop = self.get(Shop, shop_id, self.write)
        return actor

    def own_order(self, identifier, merchant=False):
        row = self.get(Order, identifier, self.write)
        if (
            merchant
            and row.shop_id != self.shop.id
            or not merchant
            and row.customer_id != self.actor.id
        ):
            fail("NOT_FOUND", 404)
        return row

    def own_product(self, identifier):
        row = self.get(Product, identifier, self.write)
        if row.shop_id != self.shop.id:
            fail("NOT_FOUND", 404)
        return row

    def own_sku(self, identifier, product=None):
        row = self.get(SKU, identifier, self.write)
        if row.shop_id != self.shop.id or product is not None and row.product_id != product.id:
            fail("NOT_FOUND", 404)
        return row

    def my_cart(self):
        row = self.db.scalar(
            select(Cart)
            .where(Cart.customer_id == self.actor.id)
            .with_for_update()
            .execution_options(populate_existing=True)
            if self.write
            else select(Cart).where(Cart.customer_id == self.actor.id)
        )
        if row is None:
            fail("NOT_FOUND", 404)
        return row

    def version(self, row, body):
        if inp.integer(body["expected_version"]) != row.version:
            fail("VERSION_CONFLICT")

    def audit(self, action, target=None, **metadata):
        self.new(
            BusinessAudit,
            actor_id=self.actor.id if self.actor else None,
            action=action,
            target_id=target,
            request_id=self.request_id,
            safe_metadata=metadata,
        )

    def write_result(self, operation, body, action):
        keys = self.request.headers.getlist("idempotency-key")
        if len(keys) != 1 or not re.fullmatch(r"[!-~]{1,200}", keys[0]):
            fail("IDEMPOTENCY_KEY_REQUIRED" if not keys else "INVALID_REQUEST", 400)
        key = keys[0]
        body = body if operation.startswith("onboarding:") else normalize(body)
        request_hash = (
            self.onboarding_fingerprint(body)
            if operation.startswith("onboarding:")
            else digest(body)
        )
        old = self.db.scalar(
            select(IdempotencyRecord).filter_by(
                actor_id=self.actor.id, operation=operation, key=key
            )
        )
        if old:
            if old.request_hash != request_hash:
                fail("IDEMPOTENCY_CONFLICT")
            return (
                old.response_payload,
                old.response_status
                if operation.startswith("onboarding:")
                else (
                    204
                    if old.response_status == 204
                    else 410
                    if old.response_status == 410
                    else 200
                ),
                True,
            )
        payload, status = action()
        self.db.flush()
        resource_ids = []
        if isinstance(payload, dict):
            resource_ids = payload.get("order_ids", []) or (
                [payload["id"]] if "id" in payload else []
            )
        self.new(
            IdempotencyRecord,
            actor_id=self.actor.id,
            operation=operation,
            key=key,
            request_hash=request_hash,
            resource_ids=resource_ids,
            response_status=status,
            response_payload=payload,
        )
        self.audit(
            operation,
            UUID_or_none(resource_ids[0]) if resource_ids else None,
            outcome="ORDER_EXPIRED" if status == 410 else "ALLOWED",
        )
        return payload, status, getattr(self, "event_replay", False)

    def movement(self, inv, on_hand, reserved, reason, related):
        if (
            inv.on_hand + on_hand < inv.reserved + reserved
            or inv.on_hand + on_hand < 0
            or inv.reserved + reserved < 0
        ):
            fail("STOCK_UNAVAILABLE", sku_id=str(inv.sku_id), available=inv.on_hand - inv.reserved)
        inv.on_hand += on_hand
        inv.reserved += reserved
        self.bump(inv)
        self.new(
            StockMovement,
            sku_id=inv.sku_id,
            actor_id=self.actor.id,
            on_hand_delta=on_hand,
            reserved_delta=reserved,
            reason=reason,
            related_record_id=related,
        )

    def settle(self, order, reason="ORDER_EXPIRED"):
        for line in sorted(
            views.rows(self.db, OrderLine, order_id=order.id), key=lambda line: line.sku_id
        ):
            reservation = views.rows(self.db, StockReservation, order_line_id=line.id)[0]
            if reservation.state != "HELD":
                fail("INVALID_STATE")
            inv = views.rows(self.db, Inventory, sku_id=line.sku_id)[0]
            self.db.refresh(inv, with_for_update=True)
            self.movement(inv, 0, -reservation.quantity, reason, order.id)
            reservation.state = "RELEASED"
            self.bump(reservation)
        for attempt in views.rows(self.db, PaymentAttempt, order_id=order.id):
            if attempt.state == "PENDING":
                attempt.state = "FAILED"
                attempt.failure_code = reason
                attempt.finished_at = self.now
                self.bump(attempt)
        order.status = "CANCELLED"
        order.cancel_reason_code = reason
        order.cancelled_at = self.now
        self.bump(order)
        self.audit("ORDER_SETTLED", order.id, reason=reason)

    def expire_result(self, order):
        if views.expired(order, self.now):
            self.settle(order)
            return CommerceError(410, "ORDER_EXPIRED").payload(self.request_id), 410
        return None

    def login(self, body):
        inp.fields(body, ["username", "password"])
        username = inp.string(body["username"], 1, 80)
        password = body["password"]
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            fail("INVALID_REQUEST", 400)
        if not re.fullmatch(r"[a-z0-9_.-]{1,80}", username):
            fail("INVALID_REQUEST", 400)
        actor = self.db.scalar(
            select(CommerceAccount).where(CommerceAccount.username == username).with_for_update()
        )
        if (
            not password_matches(actor.password_hash if actor else None, password)
            or actor is None
            or not actor.active
        ):
            fail("INVALID_CREDENTIALS", 401)
        self.actor = actor
        token = new_token()
        session = self.new(
            CommerceSession,
            account_id=actor.id,
            token_digest=token_digest(token),
            expires_at=self.now + timedelta(hours=8),
        )
        self.audit("LOGIN", actor.id, outcome="ALLOWED")
        return {
            "token": token,
            "expires_at": views.iso(session.expires_at),
            "account": views.account(self.db, actor),
        }, 200

    def new_sku(self, product, body):
        code = inp.string(body["sku_code"], 1, 80)
        opts = inp.options(body["options"])
        price = inp.integer(body["unit_price_minor"], 1, 100000000)
        stock = inp.integer(body["initial_stock"], 0, 1000000)
        skus = views.rows(self.db, SKU, product_id=product.id)
        if (
            len(skus) >= 50
            or any(s.options == opts for s in skus)
            or self.db.scalar(select(SKU).filter_by(shop_id=product.shop_id, sku_code=code))
        ):
            fail("INVALID_STATE")
        sku = self.new(
            SKU,
            product_id=product.id,
            shop_id=product.shop_id,
            sku_code=code,
            options=opts,
            unit_price_minor=price,
            price_version=1,
            active=True,
        )
        inv = self.new(Inventory, sku_id=sku.id, on_hand=stock, reserved=0)
        if stock:
            self.new(
                StockMovement,
                sku_id=sku.id,
                actor_id=self.actor.id,
                on_hand_delta=stock,
                reserved_delta=0,
                reason="INITIAL_STOCK",
                related_record_id=product.id,
            )
        return sku, inv

    def product_action(self, product, action, body):
        if action == "create":
            inp.fields(body, ["title", "description", "sku"])
            title = inp.string(body["title"], 1, 200)
            description = inp.string(body["description"], 0, 5000)
            inp.fields(body["sku"], ["sku_code", "options", "unit_price_minor", "initial_stock"])
            product = self.new(
                Product, shop_id=self.shop.id, title=title, description=description, status="DRAFT"
            )
            self.new_sku(product, body["sku"])
            return views.product(self.db, product, True), 201
        if action == "edit":
            inp.fields(body, ["expected_version", "title", "description"])
            self.version(product, body)
            product.title = inp.string(body["title"], 1, 200)
            product.description = inp.string(body["description"], 0, 5000)
        elif action == "skus":
            inp.fields(
                body,
                ["expected_version", "sku_code", "options", "unit_price_minor", "initial_stock"],
            )
            self.version(product, body)
            self.new_sku(product, body)
        else:
            inp.fields(body, ["expected_version"])
            self.version(product, body)
            if action == "publish":
                if self.shop.status != "ACTIVE" or not any(
                    s.active for s in views.rows(self.db, SKU, product_id=product.id)
                ):
                    fail("NOT_PURCHASABLE")
                if product.status == "PUBLISHED":
                    fail("INVALID_STATE")
                product.status = "PUBLISHED"
            elif action == "archive":
                if product.status != "PUBLISHED":
                    fail("INVALID_STATE")
                product.status = "ARCHIVED"
            else:
                fail("NOT_FOUND", 404)
        self.bump(product)
        self.db.flush()
        return views.product(self.db, product, True), 201 if action == "skus" else 200

    def sku_edit(self, sku, body):
        inp.fields(body, ["expected_version", "unit_price_minor", "active"])
        self.version(sku, body)
        price = inp.integer(body["unit_price_minor"], 1, 100000000)
        active = inp.boolean(body["active"])
        if price != sku.unit_price_minor:
            sku.price_version += 1
        sku.unit_price_minor = price
        sku.active = active
        self.bump(sku)
        return views.sku(self.db, sku, True), 200

    def adjust(self, inv, body):
        inp.fields(body, ["expected_version", "delta", "reason"])
        self.version(inv, body)
        delta = inp.integer(body["delta"], -1000000, 1000000)
        if delta == 0:
            fail("INVALID_REQUEST", 400)
        reason = inp.string(body["reason"], 1, 200)
        self.movement(inv, delta, 0, reason, inv.id)
        return views.inventory(inv), 200

    def cart_line(self, cart, body, remove=None):
        if remove is not None:
            inp.fields(body, ["expected_version"])
            self.version(cart, body)
            line = self.db.scalar(select(CartLine).filter_by(cart_id=cart.id, sku_id=remove))
            if line is None:
                fail("NOT_FOUND", 404)
            self.db.delete(line)
            self.bump(cart)
            return None, 204
        inp.fields(body, ["expected_version", "sku_id", "quantity", "seen_price_version"])
        self.version(cart, body)
        sku = self.get(SKU, inp.identifier(body["sku_id"]), True)
        quantity = inp.integer(body["quantity"], 1, 99)
        seen = inp.integer(body["seen_price_version"])
        if not views.purchasable(self.db, sku):
            fail("NOT_PURCHASABLE")
        if seen != sku.price_version:
            fail(
                "PRICE_CHANGED",
                sku_id=str(sku.id),
                current_price_version=sku.price_version,
                current_price_minor=sku.unit_price_minor,
            )
        line = self.db.scalar(select(CartLine).filter_by(cart_id=cart.id, sku_id=sku.id))
        status = 200 if line else 201
        if line is None:
            if len(views.rows(self.db, CartLine, cart_id=cart.id)) >= 50:
                fail("INVALID_STATE")
            line = self.new(
                CartLine,
                cart_id=cart.id,
                sku_id=sku.id,
                quantity=quantity,
                seen_price_version=seen,
                seen_price_minor=sku.unit_price_minor,
            )
        else:
            line.quantity = quantity
            line.seen_price_version = seen
            line.seen_price_minor = sku.unit_price_minor
            self.bump(line)
        self.bump(cart)
        self.db.flush()
        return views.cart(self.db, cart), status

    def checkout(self, cart, body):
        inp.fields(body, ["expected_version", "address"])
        self.version(cart, body)
        address = inp.address(body["address"])
        cart_lines = views.rows(self.db, CartLine, cart_id=cart.id)
        if not cart_lines:
            fail("INVALID_STATE")
        sku_ids = {line.sku_id for line in cart_lines}
        # Collect and settle whole expired orders BEFORE inventory acquisition.
        expired_orders = list(
            self.db.scalars(
                select(Order)
                .join(OrderLine, OrderLine.order_id == Order.id)
                .where(
                    OrderLine.sku_id.in_(sku_ids),
                    Order.status == "PENDING_PAYMENT",
                    Order.payment_deadline <= self.now,
                )
                .distinct()
                .order_by(Order.id)
            )
        )
        for old in expired_orders:
            self.db.refresh(old, with_for_update=True)
            if views.expired(old, self.now):
                self.settle(old)
        grouped = {}
        for line in sorted(cart_lines, key=lambda line: line.sku_id):
            sku = self.get(SKU, line.sku_id, True)
            if not views.purchasable(self.db, sku):
                fail("NOT_PURCHASABLE")
            if sku.price_version != line.seen_price_version:
                fail(
                    "PRICE_CHANGED",
                    sku_id=str(sku.id),
                    current_price_version=sku.price_version,
                    current_price_minor=sku.unit_price_minor,
                )
            inv = views.rows(self.db, Inventory, sku_id=sku.id)[0]
            self.db.refresh(inv, with_for_update=True)
            if inv.on_hand - inv.reserved < line.quantity:
                fail("STOCK_UNAVAILABLE", sku_id=str(sku.id), available=inv.on_hand - inv.reserved)
            grouped.setdefault(sku.shop_id, []).append((line, sku, inv))
        checkout = self.new(
            Checkout,
            customer_id=self.actor.id,
            cart_id=cart.id,
            source_cart_version=cart.version,
            result_cart_version=cart.version + 1,
            address_snapshot=address,
        )
        for shop_id, entries in sorted(grouped.items()):
            total = sum(s.unit_price_minor * line.quantity for line, s, _ in entries)
            order = self.new(
                Order,
                checkout_id=checkout.id,
                customer_id=self.actor.id,
                shop_id=shop_id,
                total_minor=total,
                payment_deadline=self.now + timedelta(minutes=15),
                address_snapshot=address,
                address_revision=1,
                status="PENDING_PAYMENT",
                financial_status="UNPAID",
            )
            self.new(AddressRevision, order_id=order.id, revision=1, address_snapshot=address)
            for line, sku, inv in entries:
                product = self.get(Product, sku.product_id)
                order_line = self.new(
                    OrderLine,
                    order_id=order.id,
                    shop_id=shop_id,
                    sku_id=sku.id,
                    product_title_snapshot=product.title,
                    options_snapshot=sku.options,
                    unit_price_minor=sku.unit_price_minor,
                    quantity=line.quantity,
                    shipped_qty=0,
                    refunded_unshipped_qty=0,
                    refunded_shipped_qty=0,
                )
                self.new(
                    StockReservation,
                    order_line_id=order_line.id,
                    quantity=line.quantity,
                    state="HELD",
                )
                self.movement(inv, 0, line.quantity, "CHECKOUT_RESERVED", order.id)
                self.db.delete(line)
        self.bump(cart)
        self.db.flush()
        return views.checkout(self.db, checkout, self.now), 201

    def order_action(self, order, action, body):
        inp.fields(
            body,
            ["expected_version", "address"]
            if action == "address"
            else ["expected_version", "reason"]
            if action == "cancel"
            else ["expected_version"],
        )
        # Expiry precedes version for payment/cancel, commits explicit 410 snapshot.
        if action in {"payments", "cancel"}:
            result = self.expire_result(order)
            if result:
                return result
        self.version(order, body)
        if action in {"address", "confirm-receipt"} and after_sales.active(self.db, order):
            fail("ACTIVE_CASE_EXISTS")
        if action == "address":
            address = inp.address(body["address"])
            if (
                order.status not in {"PENDING_PAYMENT", "READY_TO_SHIP"}
                or views.expired(order, self.now)
                or views.rows(self.db, Shipment, order_id=order.id)
            ):
                fail("INVALID_STATE")
            order.address_snapshot = address
            order.address_revision += 1
            self.new(
                AddressRevision,
                order_id=order.id,
                revision=order.address_revision,
                address_snapshot=address,
            )
        elif action == "cancel":
            inp.string(body["reason"], 1, 500)
            if order.status != "PENDING_PAYMENT":
                fail("INVALID_STATE")
            self.settle(order, "CUSTOMER_CANCELLED")
            return views.order(self.db, order, self.now), 200
        elif action == "payments":
            if order.status != "PENDING_PAYMENT" or any(
                a.state in {"PENDING", "SUCCEEDED"}
                for a in views.rows(self.db, PaymentAttempt, order_id=order.id)
            ):
                fail("INVALID_STATE")
            attempt = self.new(
                PaymentAttempt,
                order_id=order.id,
                amount_minor=order.total_minor,
                currency="CNY",
                state="PENDING",
                simulation=True,
            )
            self.bump(order)
            return views.attempt(attempt), 201
        elif action == "confirm-receipt":
            shipments = views.rows(self.db, Shipment, order_id=order.id)
            if (
                order.status != "SHIPPED"
                or not shipments
                or any(s.status != "DELIVERED" for s in shipments)
            ):
                fail("INVALID_STATE")
            order.status = "COMPLETED"
            order.completed_at = self.now
        else:
            fail("NOT_FOUND", 404)
        self.bump(order)
        return views.order(self.db, order, self.now), 200

    def ship(self, order, body):
        inp.fields(body, ["expected_version", "lines"])
        self.version(order, body)
        selected = inp.selection(body["lines"])
        if after_sales.active(self.db, order, "UNSHIPPED_REFUND"):
            fail("ACTIVE_CASE_EXISTS")
        if order.financial_status not in {"PAID", "PARTIALLY_REFUNDED"} or order.status not in {
            "READY_TO_SHIP",
            "PARTIALLY_SHIPPED",
        }:
            fail("INVALID_STATE")
        lines = {line.id: line for line in views.rows(self.db, OrderLine, order_id=order.id)}
        for identifier, quantity in selected:
            if identifier not in lines:
                fail("NOT_FOUND", 404)
            line = lines[identifier]
            if quantity > line.quantity - line.shipped_qty - line.refunded_unshipped_qty:
                fail("QUANTITY_CONFLICT")
        shipment_id = uuid4()
        shipment = self.new(
            Shipment,
            order_id=order.id,
            tracking_number="SIM-" + shipment_id.hex,
            status="SHIPPED",
            simulation=True,
            shipped_at=self.now,
        )
        for identifier, quantity in selected:
            self.new(
                ShipmentLine,
                shipment_id=shipment.id,
                order_id=order.id,
                order_line_id=identifier,
                quantity=quantity,
            )
            lines[identifier].shipped_qty += quantity
            self.bump(lines[identifier])
        self.new(
            TrackingEvent,
            shipment_id=shipment.id,
            event_id="shipped-" + str(shipment.id),
            kind="SHIPPED",
            description="Simulated merchant dispatch",
            occurred_at=self.now,
            sequence=1,
            source="SIMULATED_CARRIER",
        )
        order.status = (
            "SHIPPED"
            if all(
                line.shipped_qty == line.quantity - line.refunded_unshipped_qty
                for line in lines.values()
            )
            else "PARTIALLY_SHIPPED"
        )
        self.bump(order)
        return views.shipment(self.db, shipment), 201

    def event_result(self, source, target, event_id, payload, action):
        request_hash = digest({"target_id": str(target.id)} | payload)
        old = self.db.scalar(select(SimulationEvent).filter_by(source=source, event_id=event_id))
        if old:
            if old.request_hash != request_hash:
                fail("IDEMPOTENCY_CONFLICT")
            self.event_replay = True
            return old.response_payload, old.response_status
        if (
            source == "SIMULATED_CARRIER"
            and self.db.scalar(select(TrackingEvent).filter_by(event_id=event_id)) is not None
        ):
            fail("IDEMPOTENCY_CONFLICT")
        result, status = action()
        self.new(
            SimulationEvent,
            source=source,
            event_id=event_id,
            target_id=target.id,
            request_hash=request_hash,
            response_payload=result,
            response_status=status,
        )
        return result, status

    def payment_result(self, attempt, body):
        inp.fields(body, ["expected_version", "result", "event_id"])
        inp.integer(body["expected_version"])
        event_id = inp.string(body["event_id"], 1, 100)
        result = body["result"]
        if not isinstance(result, str) or result not in {"SUCCEEDED", "FAILED"}:
            fail("INVALID_REQUEST", 400)

        def apply():
            order = self.get(Order, attempt.order_id, True)
            expiry = self.expire_result(order)
            if expiry:
                return expiry
            self.version(attempt, body)
            if (
                attempt.state != "PENDING"
                or order.status != "PENDING_PAYMENT"
                or attempt.amount_minor != order.total_minor
            ):
                fail("INVALID_STATE")
            attempt.state = result
            attempt.finished_at = self.now
            attempt.failure_code = "SIMULATED_DECLINE" if result == "FAILED" else None
            attempt.provider_reference = event_id
            self.bump(attempt)
            if result == "SUCCEEDED":
                for line in sorted(
                    views.rows(self.db, OrderLine, order_id=order.id), key=lambda line: line.sku_id
                ):
                    reservation = views.rows(self.db, StockReservation, order_line_id=line.id)[0]
                    if reservation.state != "HELD":
                        fail("INVALID_STATE")
                    inv = views.rows(self.db, Inventory, sku_id=line.sku_id)[0]
                    self.db.refresh(inv, with_for_update=True)
                    self.movement(inv, -line.quantity, -line.quantity, "PAYMENT_CONSUMED", order.id)
                    reservation.state = "CONSUMED"
                    self.bump(reservation)
                order.financial_status = "PAID"
                order.status = "READY_TO_SHIP"
            self.bump(order)
            return {
                "id": str(attempt.id),
                "state": attempt.state,
                "version": attempt.version,
                "simulation": True,
            }, 200

        return self.event_result("SIMULATED_PAYMENT", attempt, event_id, {"result": result}, apply)

    def tracking(self, shipment, body):
        inp.fields(body, ["expected_version", "event_id", "kind", "description", "occurred_at"])
        inp.integer(body["expected_version"])
        event_id = inp.string(body["event_id"], 1, 100)
        kind = body["kind"]
        if not isinstance(kind, str) or kind not in {"IN_TRANSIT", "DELIVERED", "EXCEPTION"}:
            fail("INVALID_REQUEST", 400)
        description = inp.string(body["description"], 1, 500)
        occurred = inp.timestamp(body["occurred_at"])

        def apply():
            self.version(shipment, body)
            events = views.rows(self.db, TrackingEvent, shipment_id=shipment.id)
            latest = max(e.occurred_at for e in events)
            if occurred < latest or occurred > self.now:
                fail("INVALID_EVENT_ORDER")
            if shipment.status == "DELIVERED" or shipment.status == kind:
                fail("INVALID_STATE")
            self.new(
                TrackingEvent,
                shipment_id=shipment.id,
                event_id=event_id,
                kind=kind,
                description=description,
                occurred_at=occurred,
                sequence=max(e.sequence for e in events) + 1,
                source="SIMULATED_CARRIER",
            )
            shipment.status = kind
            if kind == "DELIVERED":
                shipment.delivered_at = occurred
            self.bump(shipment)
            order = self.get(Order, shipment.order_id, True)
            self.bump(order)
            return {
                "id": str(shipment.id),
                "status": shipment.status,
                "version": shipment.version,
                "simulation": True,
            }, 200

        return self.event_result(
            "SIMULATED_CARRIER",
            shipment,
            event_id,
            {"kind": kind, "description": description, "occurred_at": views.iso(occurred)},
            apply,
        )

    def expire_orders(self, body):
        inp.fields(body, ["order_ids"])
        ids = body["order_ids"]
        if not isinstance(ids, list) or not 1 <= len(ids) <= 100:
            fail("INVALID_REQUEST", 400)
        ids = [inp.identifier(i) for i in ids]
        if len(set(ids)) != len(ids):
            fail("INVALID_REQUEST", 400)
        expired = []
        unchanged = []
        for identifier in sorted(ids):
            order = self.db.get(Order, identifier, with_for_update=True)
            if order and views.expired(order, self.now):
                self.settle(order)
                expired.append(str(identifier))
            else:
                unchanged.append(str(identifier))
        return {"expired_ids": expired, "unchanged_ids": unchanged}, 200


def UUID_or_none(value):
    from uuid import UUID

    try:
        return UUID(value)
    except (ValueError, TypeError):
        return None
