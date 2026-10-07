"""Closed shopping DTOs."""

from pydantic import StrictBool, StrictInt

from app.commerce.schemas import DTO, MerchantProductView, ProductView


class ImageView(DTO):
    id: str
    url: str
    alt: str
    position: StrictInt


class ProductCardView(ProductView):
    category_id: str | None
    category_name: str | None
    images: list[ImageView]
    rating: float | None
    review_count: StrictInt


class MerchantProductCardView(MerchantProductView):
    category_id: str | None
    category_name: str | None
    images: list[ImageView]
    rating: float | None
    review_count: StrictInt


class CategoryView(DTO):
    id: str
    name: str
    active: StrictBool
    version: StrictInt


class ShopView(DTO):
    id: str
    name: str
    status: str
    version: StrictInt


class FavoriteView(DTO):
    id: str
    product_id: str
    active: StrictBool
    version: StrictInt
    purchasable: StrictBool
    product: ProductCardView | None


class ReviewView(DTO):
    id: str
    product_id: str
    shop_id: str
    order_id: str
    order_line_id: str
    rating: StrictInt
    body: str
    reply: str | None
    visible: StrictBool
    version: StrictInt
    created_at: str
    updated_at: str
    financial_status: str
