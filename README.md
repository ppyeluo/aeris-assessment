# Coding Interview Assessment — Full Stack

Submission for the Aeris Health Full-Stack Developer take-home exercise.

| Section | Focus | Points | Location |
| --- | --- | --- | --- |
| **A** | State, validation, idempotency | 20 | [`A/`](A/) |
| **B** | Optimisation and complexity | 20 | [`B/`](B/) |
| **C** | API reliability and reasoning | 20 | [`C/answers.md`](C/answers.md) |
| **App** | End-to-end product engineering | 40 | [`app/`](app/) |

Everything here was written and executed locally; the commands below are the exact
ones that were run to verify the repository.

---

## Quick start

### Python version (read this first)

**Everything here needs Python 3.11 or newer.** The commands below call
`python3.11` explicitly rather than `python3`. That is deliberate: on macOS the
`python3` on `PATH` is frequently Apple's 3.9 build, and on 3.9 two things fail —

* `B/solution.py` uses `@dataclass(slots=True)`, which needs 3.10+;
* `fastapi==0.143.0` has no wheel for 3.9, so `pip install -r requirements.txt`
  stops with `No matching distribution found`.

Check your interpreter before anything else:

```bash
python3.11 -c "import sys; assert sys.version_info >= (3, 11), sys.version; print(sys.version)"
```

If that prints `3.11.x` you are ready. Otherwise install 3.11 (`brew install python@3.11`)
and either keep using `python3.11`, or point `python3` at it for the session:

```bash
alias python3=python3.11      # current shell only
```

### A and B — standard library only

```bash
# Run the tests
python3.11 -m unittest discover -s A -t A
python3.11 -m unittest discover -s B -t B

# Run the programs
python3.11 A/solution.py A/samples/sample1.in     # inventory reservation ledger
python3.11 B/solution.py B/samples/sample1.in     # fulfilment split optimiser

# …or pipe input on stdin
printf '10 2\nRESERVE e1 o1 4\nSHIP e2 o1 1\n' | python3.11 A/solution.py
```

No third-party packages are required. `unittest` is the runner that was used to verify
this repository; `pytest A -q` also collects the same tests if it happens to be
installed, but that path was not exercised here. Each directory has its own README with
the complexity analysis and the assumptions the implementation makes.

### App — FastAPI backend

```bash
cd app/backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                                        # 21 tests
uvicorn app.main:app --reload --port 8000     # http://127.0.0.1:8000/docs
```

### App — React + TypeScript frontend

```bash
cd app/frontend
npm install
npm test                                      # 23 tests (vitest)
npm run typecheck
npm run dev                                   # http://127.0.0.1:5173
```

The frontend talks to `/api` on its own origin; Vite proxies that to FastAPI on
`http://127.0.0.1:8000`, so **start the backend first**, then open
<http://127.0.0.1:5173>.

To point the proxy somewhere else:

```bash
VITE_API_TARGET=http://127.0.0.1:9000 npm run dev
```

---

## Repository layout

```text
A/                     Task A: solution.py, tests, sample input/output, README
B/                     Task B: solution.py, tests, sample input/output, README
C/answers.md           Task C: written answers (C1–C6) with official references
app/
  backend/             FastAPI service
    app/domain.py        catalogue + seed data (8 SKUs, impossible + sold-out cases)
    app/store.py         thread-safe cart with stock reservation (the concurrency story)
    app/schemas.py       request/response contracts
    app/errors.py        one error envelope for every failure
    app/main.py          routes and app factory
    tests/test_api.py    21 tests: validation, idempotency, the stock race, contracts
  frontend/            React 18 + TypeScript (Vite)
    src/api/             HTTP client + wire types
    src/domain/          pure variant-resolution logic (unit tested on its own)
    src/components/      presentational components
    src/App.tsx          page orchestration and submit state machine
```

Everything above is the content of this repository, rooted at the directory holding
this README.

---

## Architecture notes (App)

* **Layering.** `api/` knows about HTTP, `domain/` is pure logic (variant resolution,
  quantity clamping, formatting) and `components/` only render. The page receives its
  HTTP client through a prop, so component tests drive the real component tree with a
  fake API instead of mocking `fetch`.
* **Server is the authority.** The client never sends a price or a stock level; both
  come from the catalogue on every response, and the page refreshes the product and the
  cart after each successful add so stale UI cannot persist.
* **One error shape.** FastAPI validation errors, business rejections and unexpected
  failures are all returned as `{"error": {"code", "message", "details"}}`, with `details`
  always present and `null` when there is nothing extra to report, and the client
  normalises transport failures into the same `ApiError` type.
* **Concurrency.** Adding to the cart is a check-then-act over shared state, so the
  whole operation runs inside one `threading.Lock`, and those endpoints are declared
  with `def` (not `async def`) so Starlette executes them in its worker thread pool —
  a blocking lock inside an async endpoint would stall the event loop instead of
  serialising callers. `CartStore` documents the invariant: reserved units never
  exceed stock.
* **Idempotency.** Every add request must carry an `Idempotency-Key`; the outcome
  (success *or* refusal) is cached against that key inside the same critical section,
  so concurrent retries of one key reserve exactly once and replays return the original
  response verbatim.
* **Quantity bound.** The quantity input is clamped to the resolved SKU's availability
  and re-clamped whenever the selection changes, so a shrinking stock level can never
  leave an invalid quantity on screen.

---

## Assumptions

The exercise leaves a few behaviours open. These are the readings this submission
implements; each is also stated in the relevant section README or `answers.md`.

**Task A — inventory ledger**

1. `OPEN` format. The statement says only "print open reservations ordered by
   `order_id`", but the worked example ends with `OPEN 0` for a run with no open
   reservation. Format therefore implemented as `OPEN <count> [order_id ...]`, ids in
   ascending order.
2. A business-rejected operation still counts as processed — the sample proves it
   (`e2` is refused, then replaying `e2` yields `DUPLICATE`, not a retry).
3. A malformed line is *not* recorded, because a line that cannot be parsed has no
   trustworthy `event_id`. If that id later arrives in a well-formed line it is
   processed normally.
4. Blank lines are ignored. If fewer command lines are supplied than the header
   declares, the available lines are processed and the `OPEN` line is still printed;
   extra lines beyond the declared count are ignored.
5. Malformed headers are a hard error: a message on stderr and exit code 2, rather
   than a silently wrong answer.

**Task B — split optimiser**

1. "Lexicographically smallest allocation list when sorted by `warehouse_id`" is read
   as: sort each candidate's `(warehouse_id, allocated_qty)` pairs by `warehouse_id`,
   then compare the resulting sequences with standard lexicographic ordering (id first,
   then quantity; a strict prefix is smaller). Note the consequence — with equal
   warehouse count and cost, a list that *starts* with a smaller id wins.
2. `fixed_cost` is charged once per used warehouse (i.e. allocated quantity > 0); a
   warehouse allocated zero units is not "used" and appears nowhere in the output.
3. An unfulfillable order prints a single line `-1`.

**App — variant PDP**

1. Adding to the cart reserves stock immediately; `available` returned by the API is
   stock minus units currently held in carts.
2. `Idempotency-Key` is required. Repeating a key returns the first response unchanged
   (including error responses) and never reserves twice. Reusing a key with a different
   payload returns the original response — the key identifies one intent.
3. Quantity is capped at 100 per request (server-side validation) and the UI clamps to
   the SKU's availability.
4. Storage is in memory: restarting the API resets the catalogue and the cart.
5. Authentication, checkout, payments and production deployment are explicitly out of
   scope per the brief, so they are not implemented.

---

## Known limitations

* **A / B** keep everything in memory and process a single input stream; they are
  deterministic single-pass programs, not services.
* **B** keeps every DP suffix layer (`O(W·K·Q)` space) because the lexicographic
  tie-break is reconstructed greedily front-to-back. At the stated maximum
  (`W=30, Q=2000`) that is ~1.9M integers (measured 0.21 s, well within budget); a
  larger `W` would want the tie-break expressed inside the DP instead.
* **App** is single-process: the idempotency cache and reserved quantities live in
  memory, so multiple uvicorn workers or a restart would need a shared store
  (Postgres/Redis) plus a cross-process lock. The idempotency cache never expires,
  which is fine for a demo but would need a TTL in production. There is no endpoint to
  update or remove cart lines, because the brief only specifies add/list.
* **C** is a design review answered from the official documentation and the published
  OpenAPI specification; no live Xero sandbox call was made, so the answer discusses
  behaviour rather than reporting production telemetry.

---

## AI tool usage

See [`AI_USAGE.md`](AI_USAGE.md) for the full disclosure. In short: AI assistance was
used for design discussion, first-draft code and tests, and for locating the official
Xero documentation that Task C cites. Every command in this README was executed, all
test suites pass locally, and both worked examples were reproduced byte-for-byte.
