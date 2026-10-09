#!/usr/bin/env python3
"""API tests: success paths, validation, idempotency and the stock race."""

from __future__ import annotations

import concurrent.futures
import threading

import pytest
from fastapi.testclient import TestClient

from app.domain import build_seed_product
from app.main import create_app
from app.store import CartStore

PRODUCT_ID = "aeris-everyday-tee"
IN_STOCK_SKU = "tee-black-s"      # stock 5
LAST_UNIT_SKU = "tee-sand-l"      # stock 1
OUT_OF_STOCK_SKU = "tee-white-s"  # stock 0


@pytest.fixture()
def client() -> TestClient:
    """A fresh app (pristine stock) for every test."""
    with TestClient(create_app()) as test_client:
        yield test_client


def add_item(client: TestClient, sku_id: str, quantity: int = 1, key: str = "key-1"):
    return client.post(
        "/api/cart/items",
        json={"sku_id": sku_id, "quantity": quantity},
        headers={"Idempotency-Key": key},
    )


# --------------------------------------------------------------------- catalogue
def test_product_exposes_two_option_dimensions_and_the_seed_skus(client: TestClient) -> None:
    body = client.get(f"/api/products/{PRODUCT_ID}").json()
    assert body["id"] == PRODUCT_ID
    assert [dimension["name"] for dimension in body["options"]] == ["Colour", "Size"]
    assert len(body["skus"]) == 8
    assert body["currency"] == "AUD"


def test_seed_contains_an_unavailable_combination_and_an_out_of_stock_sku(client: TestClient) -> None:
    skus = client.get(f"/api/products/{PRODUCT_ID}").json()["skus"]
    combinations = {(sku["option_values"]["Colour"], sku["option_values"]["Size"]) for sku in skus}
    assert ("Black", "L") not in combinations, "Black/L must stay an impossible combination"
    assert any(sku["available"] == 0 for sku in skus), "one SKU must be out of stock"


def test_unknown_product_returns_the_error_envelope(client: TestClient) -> None:
    response = client.get("/api/products/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_product"


# -------------------------------------------------------------------- add to cart
def test_add_item_success_updates_the_cart(client: TestClient) -> None:
    response = add_item(client, IN_STOCK_SKU, quantity=2)
    assert response.status_code == 201
    assert response.json() == {
        "sku_id": IN_STOCK_SKU,
        "quantity": 2,
        "cart_item_count": 2,
        "cart_total_cents": 7800,
    }

    cart = client.get("/api/cart").json()
    assert cart["item_count"] == 2
    assert cart["total_cents"] == 7800
    assert cart["items"][0]["sku_id"] == IN_STOCK_SKU


def test_price_is_taken_from_the_server_not_the_request(client: TestClient) -> None:
    response = client.post(
        "/api/cart/items",
        json={"sku_id": IN_STOCK_SKU, "quantity": 1, "price_cents": 1},
        headers={"Idempotency-Key": "price-check"},
    )
    assert response.status_code == 201
    assert response.json()["cart_total_cents"] == 3900  # catalogue price, not 1


def test_missing_idempotency_key_is_rejected(client: TestClient) -> None:
    response = client.post("/api/cart/items", json={"sku_id": IN_STOCK_SKU, "quantity": 1})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_idempotency_key"


def test_error_envelope_always_carries_the_details_key(client: TestClient) -> None:
    """`details` is always present (null when empty) so clients can read it blindly."""
    missing_key = client.post("/api/cart/items", json={"sku_id": IN_STOCK_SKU, "quantity": 1})
    assert missing_key.status_code == 400
    body = missing_key.json()
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["details"] is None

    stock = add_item(client, OUT_OF_STOCK_SKU)
    assert stock.json()["error"]["details"] == {
        "sku_id": OUT_OF_STOCK_SKU,
        "requested": 1,
        "available": 0,
    }


def test_openapi_documents_the_404_for_an_unknown_sku(client: TestClient) -> None:
    """The documented contract and the generated schema must agree."""
    schema = client.get("/openapi.json").json()
    responses = schema["paths"]["/api/cart/items"]["post"]["responses"]
    assert "404" in responses, sorted(responses)
    assert set(responses) >= {"201", "400", "404", "409", "422"}


def test_unknown_sku_is_rejected(client: TestClient) -> None:
    response = add_item(client, "no-such-sku")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_sku"


@pytest.mark.parametrize("quantity", [0, -1, 101])
def test_invalid_quantity_uses_the_error_envelope(client: TestClient, quantity: int) -> None:
    response = add_item(client, IN_STOCK_SKU, quantity=quantity)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["problems"], "validation problems must be described"


def test_out_of_stock_sku_is_rejected(client: TestClient) -> None:
    response = add_item(client, OUT_OF_STOCK_SKU)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_stock"


def test_requesting_more_than_available_is_rejected(client: TestClient) -> None:
    assert add_item(client, IN_STOCK_SKU, quantity=5).status_code == 201
    response = add_item(client, IN_STOCK_SKU, quantity=1, key="key-2")
    assert response.status_code == 409
    assert response.json()["error"]["details"]["available"] == 0


def test_available_decreases_as_stock_is_reserved(client: TestClient) -> None:
    before = _available(client, IN_STOCK_SKU)
    add_item(client, IN_STOCK_SKU, quantity=2)
    assert _available(client, IN_STOCK_SKU) == before - 2


# --------------------------------------------------------------------- idempotency
def test_repeating_the_same_key_does_not_add_twice(client: TestClient) -> None:
    first = add_item(client, IN_STOCK_SKU, quantity=2, key="same-key")
    second = add_item(client, IN_STOCK_SKU, quantity=2, key="same-key")

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json(), "a replay must return the original answer"
    assert client.get("/api/cart").json()["item_count"] == 2


def test_different_keys_accumulate(client: TestClient) -> None:
    add_item(client, IN_STOCK_SKU, quantity=1, key="key-a")
    add_item(client, IN_STOCK_SKU, quantity=1, key="key-b")
    assert client.get("/api/cart").json()["item_count"] == 2


def test_replayed_error_is_also_replayed(client: TestClient) -> None:
    """A refused request that is retried with the same key stays refused."""
    first = add_item(client, OUT_OF_STOCK_SKU, key="err-key")
    second = add_item(client, OUT_OF_STOCK_SKU, key="err-key")
    assert first.status_code == second.status_code == 409
    assert first.json() == second.json()


def test_concurrent_replays_of_one_key_reserve_once(client: TestClient) -> None:
    barrier = threading.Barrier(6)

    def attempt(_: int) -> int:
        barrier.wait()
        return add_item(client, IN_STOCK_SKU, quantity=1, key="shared-key").status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(attempt, range(6)))

    assert codes == [201] * 6
    assert client.get("/api/cart").json()["item_count"] == 1


# ------------------------------------------------------------------ stock race
def test_store_serialises_concurrent_reservations() -> None:
    """Eight threads fight over the single remaining unit: exactly one wins.

    This exercises the critical section directly.  Without the lock in
    ``CartStore.add_item`` several threads observe ``available == 1`` and the
    final reserved quantity exceeds stock.
    """
    store = CartStore(build_seed_product())
    barrier = threading.Barrier(8)

    def attempt(index: int) -> int:
        barrier.wait()  # line every thread up before they all reserve
        return store.add_item(LAST_UNIT_SKU, 1, f"race-{index}")[0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(attempt, range(8)))

    assert codes.count(201) == 1, codes
    assert codes.count(409) == 7, codes

    sku = store.find_sku(LAST_UNIT_SKU)
    assert sku is not None
    assert store.reserved_units(LAST_UNIT_SKU) == 1
    assert store.reserved_units(LAST_UNIT_SKU) <= sku.stock


def test_api_rejects_the_loser_of_the_race(client: TestClient) -> None:
    barrier = threading.Barrier(4)

    def attempt(index: int) -> int:
        barrier.wait()
        return add_item(client, LAST_UNIT_SKU, 1, key=f"http-race-{index}").status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(attempt, range(4)))

    assert codes.count(201) == 1, codes
    assert all(code in (201, 409) for code in codes), codes
    assert client.get("/api/cart").json()["item_count"] == 1


# ------------------------------------------------------------------- helpers
def _available(client: TestClient, sku_id: str) -> int:
    skus = client.get(f"/api/products/{PRODUCT_ID}").json()["skus"]
    return next(sku["available"] for sku in skus if sku["id"] == sku_id)
