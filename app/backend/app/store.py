"""Thread-safe in-memory cart with stock reservation.

Concurrency approach
--------------------
Adding to the cart is a read-modify-write over shared state (is there enough
stock? then reserve it), so the check and the reservation must happen in one
critical section or two simultaneous requests can both pass the check and
oversell the last unit.

The store therefore guards every mutation with a single ``threading.Lock``, and
the FastAPI endpoints that touch it are declared with ``def`` (not ``async def``)
so Starlette runs them in its worker thread pool.  A blocking lock inside an
``async def`` endpoint would stall the event loop instead of serialising callers.

The critical section is tiny (a dict lookup and two integer updates), so a single
lock is well within budget for this exercise; it is also the clearest statement of
the invariant "reserved units never exceed stock".
"""

from __future__ import annotations

import threading

from .domain import Product, Sku


class CartStore:
    """In-memory cart plus the stock it has reserved."""

    def __init__(self, product: Product) -> None:
        self._product = product
        self._lock = threading.Lock()
        self._reserved: dict[str, int] = {}          # sku_id -> units held in carts
        self._responses: dict[str, tuple[int, dict]] = {}  # idempotency key -> reply

    # ------------------------------------------------------------------ reads
    @property
    def product(self) -> Product:
        return self._product

    def find_sku(self, sku_id: str) -> Sku | None:
        return self._product.by_id(sku_id)

    def reserved_units(self, sku_id: str) -> int:
        with self._lock:
            return self._reserved.get(sku_id, 0)

    def available_units(self, sku: Sku) -> int:
        """Stock not yet promised to a cart. Read under the lock."""
        with self._lock:
            return max(sku.stock - self._reserved.get(sku.id, 0), 0)

    def cart(self) -> dict:
        with self._lock:
            items = []
            for sku in self._product.skus:
                quantity = self._reserved.get(sku.id, 0)
                if not quantity:
                    continue
                items.append(
                    {
                        "sku_id": sku.id,
                        "product_id": self._product.id,
                        "name": self._product.name,
                        "option_values": dict(sku.option_values),
                        "quantity": quantity,
                        "price_cents": sku.price_cents,
                        "line_total_cents": sku.price_cents * quantity,
                        "image": sku.image,
                    }
                )
            return {
                "items": items,
                "item_count": sum(item["quantity"] for item in items),
                "total_cents": sum(item["line_total_cents"] for item in items),
                "currency": self._product.currency,
            }

    # ------------------------------------------------------------------ write
    def add_item(self, sku_id: str, quantity: int, idempotency_key: str) -> tuple[int, dict]:
        """Reserve ``quantity`` units of ``sku_id``.

        Returns ``(status_code, body)``.  Every outcome is recorded against the
        idempotency key *inside* the critical section, so a retry of the same key
        replays the original answer verbatim and can never reserve twice -- even
        when the retry arrives concurrently with the first attempt.
        """
        with self._lock:
            replayed = self._responses.get(idempotency_key)
            if replayed is not None:
                return replayed

            sku = self._product.by_id(sku_id)
            if sku is None:
                reply = (
                    404,
                    {
                        "error": {
                            "code": "unknown_sku",
                            "message": f"No SKU with id '{sku_id}'",
                            "details": {"sku_id": sku_id},
                        }
                    },
                )
            else:
                available = max(sku.stock - self._reserved.get(sku.id, 0), 0)
                if quantity > available:
                    reply = (
                        409,
                        {
                            "error": {
                                "code": "insufficient_stock",
                                "message": (
                                    f"Only {available} unit(s) of '{sku_id}' are available"
                                ),
                                "details": {
                                    "sku_id": sku_id,
                                    "requested": quantity,
                                    "available": available,
                                },
                            }
                        },
                    )
                else:
                    new_quantity = self._reserved.get(sku.id, 0) + quantity
                    self._reserved[sku.id] = new_quantity
                    reply = (
                        201,
                        {
                            "sku_id": sku_id,
                            "quantity": quantity,
                            "cart_item_count": sum(self._reserved.values()),
                            "cart_total_cents": sum(
                                s.price_cents * self._reserved.get(s.id, 0) for s in self._product.skus
                            ),
                        },
                    )

            self._responses[idempotency_key] = reply
            return reply
