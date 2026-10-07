"""Closed public DTOs; credential and private customer fields cannot leak."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.commerce.schemas import AttemptView


class RecordDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class AccessDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform_enabled: bool


class AccountDTO(RecordDTO):
    username: str
    active: bool
    customer_enabled: bool
    demo_enabled: bool


class ShopDTO(RecordDTO):
    name: str
    status: str


class ProductDTO(RecordDTO):
    moderation_hidden: bool
    shop_id: UUID
    title: str
    description: str
    status: str


class ReviewDTO(RecordDTO):
    product_id: UUID
    shop_id: UUID
    rating: int
    body: str
    reply: str | None
    visible: bool


class CategoryDTO(RecordDTO):
    name: str
    active: bool


class ReportDTO(RecordDTO):
    reporter_id: UUID
    target_type: str
    target_id: UUID
    reason: str
    state: str
    decision_reason: str | None


class ActionDTO(RecordDTO):
    actor_id: UUID
    target_type: str
    target_id: UUID
    action: str
    reason: str
    report_id: UUID | None


class DisputeDTO(RecordDTO):
    case_state: str
    can_refund: bool
    customer_id: UUID
    order_id: UUID
    case_id: UUID
    shop_id: UUID
    reason: str
    state: str
    customer_evidence: str
    merchant_evidence: str
    decision_reason: str | None
    decided_by: UUID | None


class PageDTO[T](BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[T]
    total: int
    offset: int
    limit: int
    has_more: bool


class EligibilityDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    can_dispute: bool
    dispute_open: bool
    reason: str | None


class FinancialDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_total_minor: int
    refund_total_minor: int
    net_total_minor: int


class MetricsDTO(FinancialDTO):
    orders_created: int
    orders_completed: int


class DailyDTO(FinancialDTO):
    date: str


class ShopMetricsDTO(MetricsDTO):
    shop_id: UUID


class BacklogDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unpaid: int
    awaiting_shipment: int
    in_transit: int
    after_sales: int


class SalesDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shop_id: UUID
    sku_id: UUID
    purchased_quantity: int
    refunded_unshipped_quantity: int
    refunded_shipped_quantity: int


class AnalyticsDTO(MetricsDTO):
    offset: int
    limit: int
    shops_has_more: bool
    sales_has_more: bool
    simulation: bool
    currency: str
    start: datetime
    end: datetime
    shop_id: UUID | None
    backlog: BacklogDTO
    daily: list[DailyDTO]
    shops: list[ShopMetricsDTO]
    sales: list[SalesDTO]
    sales_basis: str
    backlog_basis: str


class DisputeLineDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    quantity: int
    unit_price_minor: int
    shipped_qty: int
    refunded_unshipped_qty: int
    refunded_shipped_qty: int


class DisputeContextDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_type: str
    state: str
    reason: str
    merchant_decision_reason: str | None
    requested_amount_minor: int
    currency: str
    financial_status: str
    paid_minor: int
    refunded_minor: int
    lines: list[DisputeLineDTO]
    return_state: str | None


RESPONSES = {
    "list.actions": PageDTO[ActionDTO],
    "dispute.context": DisputeContextDTO,
    "access": AccessDTO,
    "list.accounts": PageDTO[AccountDTO],
    "list.shops": PageDTO[ShopDTO],
    "list.products": PageDTO[ProductDTO],
    "list.reviews": PageDTO[ReviewDTO],
    "list.reports": PageDTO[ReportDTO],
    "list.disputes": PageDTO[DisputeDTO],
    "list.categories": PageDTO[CategoryDTO],
    "customer.reports": PageDTO[ReportDTO],
    "customer.disputes": PageDTO[DisputeDTO],
    "merchant.disputes": PageDTO[DisputeDTO],
    "report.create": ReportDTO,
    "report.decision": ReportDTO,
    "moderation": ActionDTO,
    "dispute.create": DisputeDTO,
    "dispute.decision": DisputeDTO,
    "customer.evidence": DisputeDTO,
    "customer.withdraw": DisputeDTO,
    "merchant.evidence": DisputeDTO,
    "dispute.refunds": AttemptView,
    "category.create": CategoryDTO,
    "category.edit": CategoryDTO,
    "customer.eligibility": EligibilityDTO,
    "analytics": AnalyticsDTO,
    "merchant.analytics": AnalyticsDTO,
}
