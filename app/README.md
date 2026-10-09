# App — Variant Product Detail Page

A small but production-minded PDP: a FastAPI service that owns price and stock, and a
React + TypeScript client that renders variant state honestly.

```text
app/
  backend/    FastAPI 0.143 + Pydantic 2 (in-memory storage, seeded catalogue)
  frontend/   React 18 + TypeScript + Vite, tested with Vitest + Testing Library
```

## Run

> **Requires Python 3.11+** (`fastapi==0.143.0` has no 3.9 wheel). Create the virtualenv
> with `python3.11 -m venv`; see the repository
> [root README](../README.md#python-version-read-this-first) for why.

```bash
# backend  (terminal 1)
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000      # interactive docs at /docs
pytest                                         # 21 tests

# frontend (terminal 2)
cd frontend
npm install
npm run dev                                    # http://127.0.0.1:5173
npm test                                       # 23 tests
npm run typecheck
```

Start the backend first: the Vite dev server proxies `/api` to
`http://127.0.0.1:8000` (override with `VITE_API_TARGET`). Product images are served
from the frontend's `public/images/`, so they work without the backend.

## Domain model and seed data

One product (`aeris-everyday-tee`) with two option dimensions, `Colour` (Black, White,
Sand) × `Size` (S, M, L), and eight SKUs:

| SKU | Colour / Size | Price | Stock | Purpose |
| --- | --- | --- | --- | --- |
| `tee-black-s` | Black / S | $39.00 | 5 | normal |
| `tee-black-m` | Black / M | $39.00 | 4 | normal |
| — | **Black / L** | — | — | **impossible combination** (no SKU) |
| `tee-white-s` | White / S | $39.00 | 0 | **out of stock** |
| `tee-white-m` | White / M | $39.00 | 6 | normal |
| `tee-white-l` | White / L | $39.00 | 3 | normal |
| `tee-sand-s` | Sand / S | $42.00 | 2 | different price, low stock |
| `tee-sand-m` | Sand / M | $42.00 | 5 | normal |
| `tee-sand-l` | Sand / L | $42.00 | 1 | the "last unit" used in the race test |

Every SKU carries its own price, available quantity, image and option values. Money is
integer cents everywhere; the client formats it with the product's currency.

## API contract

### `GET /api/products/{id}` → `200`

```json
{
  "id": "aeris-everyday-tee",
  "name": "Aeris Everyday Tee",
  "description": "A midweight organic cotton tee…",
  "currency": "AUD",
  "image": "/images/tee-black.svg",
  "options": [
    { "name": "Colour", "values": ["Black", "White", "Sand"] },
    { "name": "Size", "values": ["S", "M", "L"] }
  ],
  "skus": [
    {
      "id": "tee-black-s",
      "option_values": { "Colour": "Black", "Size": "S" },
      "price_cents": 3900,
      "stock": 5,
      "available": 5,
      "image": "/images/tee-black.svg"
    }
  ]
}
```

`available` is `stock` minus everything currently held in carts — the number the UI
must respect. Unknown product → `404` `{"error": {"code": "unknown_product", …}}`.

### `POST /api/cart/items` → `201`

Request (the `Idempotency-Key` header is required):

```http
POST /api/cart/items
Content-Type: application/json
Idempotency-Key: 6f1c2a3e-…

{"sku_id": "tee-black-s", "quantity": 2}
```

```json
{
  "sku_id": "tee-black-s",
  "quantity": 2,
  "cart_item_count": 2,
  "cart_total_cents": 7800
}
```

| Status | Code | When |
| --- | --- | --- |
| `201` | — | reserved; `cart_item_count` / `cart_total_cents` reflect the whole cart |
| `400` | `missing_idempotency_key` / `invalid_idempotency_key` | header absent, blank, or longer than 128 chars |
| `404` | `unknown_sku` | no such SKU |
| `409` | `insufficient_stock` | `details` carries `requested` and `available` |
| `422` | `validation_error` | body failed validation (quantity < 1 or > 100, missing field) |

Any price or stock sent by the client is ignored: the server resolves both from the
catalogue.

Replaying the same `Idempotency-Key` returns the **first** response unchanged —
including a `409` — and never reserves twice.

### `GET /api/cart` → `200`

```json
{
  "items": [
    {
      "sku_id": "tee-black-s",
      "product_id": "aeris-everyday-tee",
      "name": "Aeris Everyday Tee",
      "option_values": { "Colour": "Black", "Size": "S" },
      "quantity": 2,
      "price_cents": 3900,
      "line_total_cents": 7800,
      "image": "/images/tee-black.svg"
    }
  ],
  "item_count": 2,
  "total_cents": 7800,
  "currency": "AUD"
}
```

Error envelope for every failure: `{"error": {"code", "message", "details"}}`, where
`details` is `null` when the failure carries nothing extra (for example a missing
`Idempotency-Key`) and an object otherwise (`{"available": 0, "requested": 1, ...}` for
`insufficient_stock`, `{"problems": [...]}` for a validation error). The key is always
present, so a client can read it unconditionally. The generated OpenAPI page at `/docs`
documents the same contract, including the `404` returned for an unknown `sku_id`.

## Concurrency: preventing oversell

Adding to the cart is a check-then-act over shared state, so the check and the
reservation happen inside **one critical section**:

* `CartStore.add_item` holds a single `threading.Lock` for lookup → validation →
  reservation → response caching. The invariant is that reserved units never exceed
  stock, so two requests for the last unit cannot both succeed.
* Endpoints that touch the store are declared with `def`, not `async def`. Starlette
  runs them in its worker thread pool, so the blocking lock serialises callers; inside
  an async endpoint it would block the event loop instead.
* The critical section is a few dictionary operations, so a single lock is more than
  fast enough here. If contention mattered, the natural next step is per-SKU locks plus
  an atomic decrement — the important part is that the decision and the mutation are
  not separated.

`test_store_serialises_concurrent_reservations` lines up eight threads on a barrier and
asserts exactly one succeeds; `test_api_rejects_the_loser_of_the_race` does the same
through HTTP.

## Idempotency

* The header is mandatory; without it a retry could duplicate a reservation silently.
* The response — success or refusal — is cached against the key **inside** the critical
  section, so concurrent replays of one key reserve exactly once and all receive the
  original answer (`test_concurrent_replays_of_one_key_reserve_once`).
* The client reuses one key per user intent: a failed add retries with the same key,
  while changing the variant or the quantity starts a new intent with a fresh key.

## Frontend structure

* `src/domain/variants.ts` — pure functions: `candidatesFor`, `resolveSku`, `optionState`
  (`available` / `out_of_stock` / `impossible`), `maxQuantity`, `clampQuantity`,
  `formatPrice`, `stockLabel`. Unit tested without rendering anything.
* `src/api/client.ts` — one `ApiError` type for transport failures, HTTP errors and
  server envelopes; components never see a raw response object.
* `src/App.tsx` — page states (`loading` / `ready` / `error` with retry) and the
  submit state machine (`idle` → `submitting` → `success` / `error`). The API client is
  injected, so tests drive the real component tree with a fake. After the add itself
  succeeds, the follow-up product/cart refresh is best-effort: a failure there leaves the
  previous numbers on screen rather than reporting a successful add as an error.
* `src/components/` — `OptionPicker` (radio groups; impossible and sold-out values are
  genuinely `disabled` and the reason is linked via `aria-describedby`),
  `QuantityStepper`, `CartSummary`, `ProductImage`.

Accessibility and resilience: semantic `fieldset`/`legend`, visible focus rings,
keyboard-operable controls, `role="status"` with `aria-live="polite"` for add-to-cart
feedback, and a retry path when the product fails to load. Layout is a single column at
375 px and two columns at 1280 px.

## Tests

* **Backend (21)** — the error envelope and the documented 404 contract, catalogue
  shape (two dimensions, impossible combination,
  sold-out SKU), success path, server-side pricing, missing/invalid idempotency key,
  unknown SKU, validation envelope, insufficient stock, `available` decreasing,
  idempotent replay (success and error), different keys accumulating, concurrent
  replays, the stock race at both the store and HTTP layers, the always-present
  `details` key, and the `404` in the generated OpenAPI schema.
* **Frontend (23)** — 14 unit tests for variant resolution/quantity/formatting and 9
  component tests covering load + incomplete selection, disabled sold-out and
  impossible options, price/stock updates on selection, single submission while in
  flight (double-click), structured server errors, quantity clamping, retry after a
  failed load, and a post-add refresh failure that must not be reported as a failed add.

## Trade-offs and what would change at scale

* In-memory storage keeps the exercise self-contained; production would need a real
  database and a transactional reservation (`UPDATE … WHERE available >= qty`) or a
  distributed lock, plus an idempotency table with a TTL.
* The idempotency cache is unbounded — fine for a demo, needs eviction in production.
* There is no delete/update cart endpoint because the brief specifies only add and
  list; adding one would also need to release reservations.
* The frontend refetches the product after each add so stock is never stale. With a
  slower API, optimistic updates (with rollback) would be the next step; the design
  keeps `available` as the single source of truth so that change is local to the page.
