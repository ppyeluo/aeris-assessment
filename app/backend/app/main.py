"""FastAPI application for the Variant PDP exercise.

Endpoints
---------
``GET  /api/products/{id}``  product, option dimensions and every SKU
``POST /api/cart/items``     add a SKU (requires an ``Idempotency-Key`` header)
``GET  /api/cart``           current cart with totals

Server-side rules: the client never sends a price or a stock level; both are
resolved from the catalogue.  Adding to the cart *reserves* stock immediately,
which is what makes the concurrent-oversell case real.
"""

from __future__ import annotations

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .domain import build_seed_product
from .errors import ApiError, register_error_handlers
from .schemas import (
    AddCartItemRequest,
    AddCartItemResponse,
    CartOut,
    ErrorResponse,
    OptionDimensionOut,
    ProductOut,
    SkuOut,
)
from .store import CartStore

IDEMPOTENCY_KEY_MAX = 128  # matches the limit documented by Xero, a familiar convention

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Missing or malformed request header"},
    404: {"model": ErrorResponse, "description": "Unknown product or SKU"},
    409: {"model": ErrorResponse, "description": "Not enough stock available"},
    422: {"model": ErrorResponse, "description": "Request body failed validation"},
}


def create_app(store: CartStore | None = None) -> FastAPI:
    """Build the app. Tests call this directly to get pristine stock."""
    app = FastAPI(
        title="Variant PDP API",
        version="1.0.0",
        description=(
            "Small product-detail-page backend: catalogue lookup, cart with "
            "server-side stock validation, idempotent add-to-cart."
        ),
    )
    app.state.store = store or CartStore(build_seed_product())

    # The Vite dev server runs on a different origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    @app.get("/health", include_in_schema=False)
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/products/{product_id}", response_model=ProductOut, responses={404: ERROR_RESPONSES[404]})
    def get_product(product_id: str, request: Request) -> ProductOut:
        store: CartStore = request.app.state.store
        product = store.product
        if product.id != product_id:
            raise ApiError(404, "unknown_product", f"No product with id '{product_id}'", {"product_id": product_id})
        return ProductOut(
            id=product.id,
            name=product.name,
            description=product.description,
            currency=product.currency,
            image=product.image,
            options=[OptionDimensionOut(name=dim.name, values=list(dim.values)) for dim in product.options],
            skus=[
                SkuOut(
                    id=sku.id,
                    option_values=dict(sku.option_values),
                    price_cents=sku.price_cents,
                    stock=sku.stock,
                    available=store.available_units(sku),
                    image=sku.image,
                )
                for sku in product.skus
            ],
        )

    @app.post(
        "/api/cart/items",
        response_model=AddCartItemResponse,
        status_code=201,
        responses=ERROR_RESPONSES,
    )
    def add_cart_item(
        payload: AddCartItemRequest,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> JSONResponse:
        if idempotency_key is None or not idempotency_key.strip():
            raise ApiError(
                400,
                "missing_idempotency_key",
                "The 'Idempotency-Key' header is required so retries cannot add the item twice.",
            )
        if len(idempotency_key) > IDEMPOTENCY_KEY_MAX:
            raise ApiError(
                400,
                "invalid_idempotency_key",
                f"'Idempotency-Key' must be at most {IDEMPOTENCY_KEY_MAX} characters.",
            )

        store: CartStore = request.app.state.store
        status_code, body = store.add_item(payload.sku_id, payload.quantity, idempotency_key)
        return JSONResponse(status_code=status_code, content=body)

    @app.get("/api/cart", response_model=CartOut)
    def get_cart(request: Request) -> CartOut:
        store: CartStore = request.app.state.store
        return CartOut(**store.cart())

    return app


app = create_app()
