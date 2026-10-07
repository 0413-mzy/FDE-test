"""Persistent shopping metadata, bounded images, private favorites and verified reviews."""

from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.commerce.models import Base, Record


class Category(Record, Base):
    __tablename__ = "commerce_categories"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 100"),
        CheckConstraint("version > 0"),
    )


class ProductExperience(Record, Base):
    __tablename__ = "commerce_product_experiences"
    product_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_products.id"), unique=True)
    category_id: Mapped[UUID | None] = mapped_column(ForeignKey("commerce_categories.id"))
    moderation_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    __table_args__ = (CheckConstraint("version > 0"),)


class ProductImage(Record, Base):
    __tablename__ = "commerce_product_images"
    product_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_products.id"))
    position: Mapped[int] = mapped_column(Integer)
    alt: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(20))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    __table_args__ = (
        UniqueConstraint("product_id", "position"),
        CheckConstraint("version > 0"),
        CheckConstraint("position BETWEEN 0 AND 7"),
        CheckConstraint("width > 0 AND height > 0 AND width::bigint * height <= 16000000"),
        CheckConstraint("mime IN ('image/png','image/jpeg','image/webp')"),
        CheckConstraint("octet_length(content) BETWEEN 1 AND 8388608"),
    )


class Favorite(Record, Base):
    __tablename__ = "commerce_favorites"
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    product_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_products.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("customer_id", "product_id"), CheckConstraint("version > 0"))


class ProductReview(Record, Base):
    __tablename__ = "commerce_product_reviews"
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_accounts.id"))
    order_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_orders.id"))
    order_line_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_order_lines.id"), unique=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_products.id"))
    shop_id: Mapped[UUID] = mapped_column(ForeignKey("commerce_shops.id"))
    rating: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    reply: Mapped[str | None] = mapped_column(Text)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "customer_id", "shop_id"],
            ["commerce_orders.id", "commerce_orders.customer_id", "commerce_orders.shop_id"],
        ),
        ForeignKeyConstraint(
            ["order_line_id", "order_id"],
            ["commerce_order_lines.id", "commerce_order_lines.order_id"],
        ),
        ForeignKeyConstraint(
            ["product_id", "shop_id"], ["commerce_products.id", "commerce_products.shop_id"]
        ),
        CheckConstraint("rating BETWEEN 1 AND 5"),
        CheckConstraint("version > 0"),
        CheckConstraint("length(trim(body)) BETWEEN 1 AND 2000"),
        CheckConstraint("reply IS NULL OR length(trim(reply)) BETWEEN 1 AND 2000"),
    )
