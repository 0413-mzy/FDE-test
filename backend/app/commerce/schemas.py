"""Closed commerce-v1 response types, validated before the transaction commits."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MembershipView(DTO):
    shop_id: str
    shop_name: str
    role: Literal["OWNER", "STAFF"]
    shop_status: Literal["ACTIVE", "SUSPENDED"]


class AccountView(DTO):
    id: str
    username: str
    customer_enabled: StrictBool
    demo_enabled: StrictBool
    shops: list[MembershipView]


class SessionView(DTO):
    token: str
    expires_at: str
    account: AccountView


class SKUView(DTO):
    id: str
    sku_code: str
    options: dict[str, str]
    unit_price_minor: StrictInt
    currency: Literal["CNY"]
    price_version: StrictInt
    active: StrictBool
    available: StrictInt


class MerchantSKUView(SKUView):
    version: StrictInt


class ProductView(DTO):
    id: str
    shop_id: str
    shop_name: str
    title: str
    description: str
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
    version: StrictInt
    skus: list[SKUView]


class MerchantProductView(ProductView):
    skus: list[MerchantSKUView]


class InventoryView(DTO):
    sku_id: str
    on_hand: StrictInt
    reserved: StrictInt
    available: StrictInt
    version: StrictInt


class CartLineView(DTO):
    sku_id: str
    shop_id: str
    product_title: str
    shop_name: str
    options: dict[str, str]
    quantity: StrictInt
    seen_price_version: StrictInt
    seen_price_minor: StrictInt
    current_price_version: StrictInt
    current_price_minor: StrictInt
    currency: Literal["CNY"]
    available: StrictInt
    purchasable: StrictBool


class CartView(DTO):
    id: str
    version: StrictInt
    lines: list[CartLineView]


class AddressView(DTO):
    recipient_name: str
    phone: str
    country_code: Literal["CN"]
    region: str
    city: str
    postal_code: str
    address_line: str


class OrderSummary(DTO):
    id: str
    shop_id: str
    status: Literal[
        "PENDING_PAYMENT", "READY_TO_SHIP", "PARTIALLY_SHIPPED", "SHIPPED", "COMPLETED", "CANCELLED"
    ]
    financial_status: Literal["UNPAID", "PAID", "PARTIALLY_REFUNDED", "REFUNDED"]
    total_minor: StrictInt
    currency: Literal["CNY"]
    version: StrictInt
    created_at: str
    payment_deadline: str
    payment_expired: StrictBool


class OrderLineView(DTO):
    id: str
    sku_id: str
    title: str
    options: dict[str, str]
    unit_price_minor: StrictInt
    quantity: StrictInt
    shipped_qty: StrictInt
    refunded_unshipped_qty: StrictInt
    refunded_shipped_qty: StrictInt


class AttemptView(DTO):
    id: str
    state: Literal["PENDING", "SUCCEEDED", "FAILED"]
    version: StrictInt
    amount_minor: StrictInt
    currency: Literal["CNY"]
    simulation: Literal[True]
    created_at: str
    finished_at: str | None
    failure_code: str | None


class ShipmentLineView(DTO):
    order_line_id: str
    quantity: StrictInt


class EventView(DTO):
    id: str
    event_id: str
    kind: Literal["SHIPPED", "IN_TRANSIT", "DELIVERED", "EXCEPTION"]
    description: str
    occurred_at: str
    sequence: StrictInt
    source: Literal["SIMULATED_CARRIER"]


class ShipmentView(DTO):
    id: str
    order_id: str
    tracking_number: str
    status: Literal["SHIPPED", "IN_TRANSIT", "DELIVERED", "EXCEPTION"]
    version: StrictInt
    simulation: Literal[True]
    shipped_at: str
    delivered_at: str | None
    lines: list[ShipmentLineView]
    events: list[EventView]


class OrderView(OrderSummary):
    checkout_id: str | None
    lines: list[OrderLineView]
    address: AddressView
    address_revision: StrictInt
    shipments: list[ShipmentView]
    payment_attempts: list[AttemptView]
    after_sale_cases: list[dict] = Field(max_length=0)
    completed_at: str | None
    cancel_reason_code: str | None
    cancelled_at: str | None


class CheckoutView(DTO):
    id: str
    order_ids: list[str]
    orders: list[OrderSummary]
    cart_version: StrictInt


class Page[T](DTO):
    items: list[T]
    limit: StrictInt
    offset: StrictInt
    has_more: StrictBool


class DemoItem(DTO):
    id: str
    kind: Literal["PAYMENT", "SHIPMENT"]
    state: str
    version: StrictInt
    simulation: Literal[True]
    created_at: str


class PaymentResult(DTO):
    id: str
    state: Literal["SUCCEEDED", "FAILED"]
    version: StrictInt
    simulation: Literal[True]


class TrackingResult(DTO):
    id: str
    status: Literal["IN_TRANSIT", "DELIVERED", "EXCEPTION"]
    version: StrictInt
    simulation: Literal[True]


class ExpireResult(DTO):
    expired_ids: list[str]
    unchanged_ids: list[str]


RESPONSES = {
    "login": SessionView,
    "me": AccountView,
    "logout": None,
    "catalog.list": Page[ProductView],
    "catalog.detail": ProductView,
    "merchant.shops": Page[MembershipView],
    "merchant.products": Page[MerchantProductView],
    "merchant.product.detail": MerchantProductView,
    "merchant.product.create": MerchantProductView,
    "merchant.product.edit": MerchantProductView,
    "merchant.product.publish": MerchantProductView,
    "merchant.product.archive": MerchantProductView,
    "merchant.product.skus": MerchantProductView,
    "merchant.sku.edit": MerchantSKUView,
    "merchant.inventory": InventoryView,
    "merchant.inventory.adjust": InventoryView,
    "customer.cart": CartView,
    "customer.cart.set": CartView,
    "customer.cart.delete": None,
    "customer.checkout.create": CheckoutView,
    "customer.checkout.detail": CheckoutView,
    "customer.orders": Page[OrderSummary],
    "customer.order.detail": OrderView,
    "customer.order.address": OrderView,
    "customer.order.cancel": OrderView,
    "customer.order.payments": AttemptView,
    "customer.order.confirm-receipt": OrderView,
    "merchant.orders": Page[OrderSummary],
    "merchant.order.detail": OrderView,
    "merchant.ship": ShipmentView,
    "merchant.shipment": ShipmentView,
    "customer.shipment": ShipmentView,
    "demo.pending": Page[DemoItem],
    "demo.payment": PaymentResult,
    "demo.tracking": TrackingResult,
    "demo.expire": ExpireResult,
}
