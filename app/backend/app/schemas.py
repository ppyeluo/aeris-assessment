"""Request/response schemas.

Money is always in minor units (``*_cents``); the client formats it with the
product's currency.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OptionDimensionOut(BaseModel):
    name: str
    values: list[str]


class SkuOut(BaseModel):
    id: str
    option_values: dict[str, str]
    price_cents: int
    stock: int
    available: int = Field(description="Stock minus units currently held in carts")
    image: str


class ProductOut(BaseModel):
    id: str
    name: str
    description: str
    currency: str
    image: str
    options: list[OptionDimensionOut]
    skus: list[SkuOut]


class AddCartItemRequest(BaseModel):
    sku_id: str = Field(min_length=1)
    quantity: int = Field(ge=1, le=100)


class CartItemOut(BaseModel):
    sku_id: str
    product_id: str
    name: str
    option_values: dict[str, str]
    quantity: int
    price_cents: int
    line_total_cents: int
    image: str


class CartOut(BaseModel):
    items: list[CartItemOut]
    item_count: int
    total_cents: int
    currency: str


class AddCartItemResponse(BaseModel):
    sku_id: str
    quantity: int
    cart_item_count: int
    cart_total_cents: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
