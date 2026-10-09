# Task A — Inventory Reservation Ledger

Deterministic command processor for a single SKU: tracks `on_hand`, the units
reserved per order, and the event ids already handled.

## Run

```bash
python3.11 solution.py samples/sample1.in          # file argument
python3.11 solution.py < samples/sample1.in        # stdin
python3.11 test_solution.py                        # 24 tests
# from the repository root:
python3.11 -m unittest discover -s A -t A
```

Standard library only — no installation step.

**Requires Python 3.11+** — see the repository
[root README](../README.md#python-version-read-this-first) for why.

## Output contract

One line per command, then a trailer:

```text
<OK|REJECTED|DUPLICATE> <on_hand> <reserved_total>
...
OPEN <count> [order_id ...]
```

## Semantics

| Command | Succeeds when | Effect |
| --- | --- | --- |
| `RESERVE eid oid qty` | `on_hand - reserved_total >= qty` | reserves `qty` for `oid` |
| `RELEASE eid oid qty` | the order holds at least `qty` | releases it (order leaves the OPEN list at zero) |
| `SHIP eid oid qty` | the order holds at least `qty` | `on_hand -= qty` **and** releases the reservation (no availability check needed) |
| `RESTOCK eid qty` | always (given a valid line) | `on_hand += qty` |

An `event_id` is idempotent. A replay returns `DUPLICATE` and never changes state —
**including replays of operations that were refused by a business rule**. Every
constraint is checked before anything is mutated, so a `REJECTED` line can never
leave a partial change behind.

## Complexity

* **Time O(N)** — each command performs a constant number of dictionary operations;
  `reserved_total` is maintained incrementally so printing a status line is O(1).
* **Space O(E + O)** — `E` remembered event ids and `O` orders with an open
  reservation.

## Assumptions

1. **`OPEN` format.** The statement only says "print open reservations ordered by
   `order_id`", while the worked example ends with `OPEN 0` for a run that closes
   everything. Implemented as `OPEN <count> [order_id ...]` with ids ascending, so the
   empty case is literally `OPEN 0`.
2. **Refusals are recorded.** The sample is explicit: `RESERVE e2 o200 7` is rejected
   for insufficient stock, and the later `RESERVE e2 o999 1` answers `DUPLICATE`.
3. **Malformed lines are not events.** An unparseable line (unknown command, wrong
   field count, non-integer or non-positive quantity, empty/non-ASCII token) has no
   trustworthy event id, so it is answered `REJECTED` and not recorded; the same id may
   still be processed later by a well-formed line.
4. **Blank lines are ignored.** If the input contains fewer command lines than the
   header declares, the available lines are processed and the `OPEN` trailer is still
   printed; lines beyond the declared count are ignored.
5. **Invalid header** (non-numeric, negative stock, zero commands) is a hard failure:
   a message on stderr and exit status 2.

## Test coverage

The suite pins the official sample byte-for-byte and covers: replay of successful and
refused events, atomicity of refusals, RELEASE/SHIP bounds, reservation accumulation
per order, partial release, zero-availability boundaries, `10^12` quantities, the
sorted `OPEN` trailer, malformed lines (unknown command, missing field, zero/negative/
non-numeric quantity), extra and truncated input, invalid headers, and the CLI.
