#!/usr/bin/env python3
"""Task A - Inventory Reservation Ledger.

Deterministic command processor for a single SKU.

Model
-----
The ledger keeps three pieces of state:

* ``on_hand``          - units physically on the books;
* ``reserved``         - ``order_id -> units`` currently held for that order;
* ``processed_events`` - every ``event_id`` already handled.

``available`` is always ``on_hand - reserved_total``.

Design decisions
----------------
1. **A rejected business operation still counts as processed.**  The sample
   output proves it: ``RESERVE e2 o200 7`` is refused for insufficient stock and
   the later ``RESERVE e2 o999 1`` answers ``DUPLICATE`` instead of retrying.
   So an ``event_id`` is remembered as soon as the command is *understood*,
   whether it succeeds or is refused by a business rule.
2. **Rejections are atomic.**  Every constraint is checked before any state is
   mutated, so a REJECTED line can never leave a partial change behind.
3. **Malformed lines are not events.**  If a line cannot be parsed (unknown
   command, wrong field count, non-positive or non-integer quantity, empty or
   non-ASCII token) there is no trustworthy ``event_id`` to remember: the line
   is answered with REJECTED and is *not* recorded.
4. **``OPEN <count> [order_id ...]``.**  The statement only says "print open
   reservations ordered by order_id"; the sample prints ``OPEN 0`` for a run
   that ends with no open reservation, which fixes the format as a count
   followed by the order ids in ascending order.

Complexity
----------
Time  O(N) - each command touches a constant number of dict entries.
Space O(E + O) - E remembered event ids, O orders with an open reservation.

Usage
-----
    python3.11 solution.py < input.txt
    python3.11 solution.py input.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

# Command name -> exact number of whitespace separated fields.
COMMANDS = {
    "RESERVE": 4,  # RESERVE event_id order_id qty
    "RELEASE": 4,  # RELEASE event_id order_id qty
    "SHIP": 4,     # SHIP    event_id order_id qty
    "RESTOCK": 3,  # RESTOCK event_id qty
}


def _is_token(value: str) -> bool:
    """event_id / order_id must be non-empty ASCII tokens."""
    return bool(value) and value.isascii()


def _parse_positive_int(value: str) -> int | None:
    """Return a positive int, or None when the token is not a positive integer.

    ``int()`` accepts underscores ("1_0") and leading/trailing whitespace, so the
    token is validated against its digits explicitly to keep the input contract
    strict.
    """
    if not value.isascii() or not value.isdigit():
        return None
    number = int(value)
    return number if number > 0 else None


def _parse_non_negative_int(value: str) -> int | None:
    if not value.isascii() or not value.isdigit():
        return None
    return int(value)


class Ledger:
    """Mutable ledger state plus the per-command rules."""

    __slots__ = ("on_hand", "reserved", "reserved_total", "processed_events")

    def __init__(self, on_hand: int) -> None:
        self.on_hand = on_hand
        self.reserved: dict[str, int] = {}
        self.reserved_total = 0  # kept incrementally so output stays O(1)
        self.processed_events: set[str] = set()

    # ------------------------------------------------------------------ helpers
    @property
    def available(self) -> int:
        return self.on_hand - self.reserved_total

    def status_line(self, status: str) -> str:
        """``<STATUS> <on_hand> <reserved_total>`` - current totals, always."""
        return f"{status} {self.on_hand} {self.reserved_total}"

    def open_reservations_line(self) -> str:
        ids = sorted(self.reserved)  # alphabetical order over order_id
        return "OPEN " + " ".join([str(len(ids)), *ids])

    # ------------------------------------------------------------------ commands
    def handle(self, line: str) -> str:
        """Process one command line and return the line to print."""
        fields = line.split()
        command = fields[0] if fields else ""
        expected = COMMANDS.get(command)

        # --- syntax gate: unknown command / wrong arity -----------------------
        if expected is None or len(fields) != expected:
            return self.status_line("REJECTED")

        event_id = fields[1]
        if expected == 3:  # RESTOCK carries no order_id
            order_id, qty_token = None, fields[2]
        else:
            order_id, qty_token = fields[2], fields[3]

        if not _is_token(event_id) or (
            order_id is not None and not _is_token(order_id)
        ):
            return self.status_line("REJECTED")

        qty = _parse_positive_int(qty_token)
        if qty is None:
            return self.status_line("REJECTED")

        # --- idempotency gate -------------------------------------------------
        # Checked after parsing (a malformed line has no reliable event id) and
        # before any business rule, so a replayed event can never change state.
        if event_id in self.processed_events:
            return self.status_line("DUPLICATE")

        # --- business rules ---------------------------------------------------
        if command == "RESTOCK":
            self.on_hand += qty
        elif command == "RESERVE":
            if self.available < qty:
                self.processed_events.add(event_id)  # refused, still processed
                return self.status_line("REJECTED")
            self.reserved[order_id] = self.reserved.get(order_id, 0) + qty
            self.reserved_total += qty
        else:  # RELEASE / SHIP both act on an existing reservation
            held = self.reserved.get(order_id, 0)
            if held < qty:
                self.processed_events.add(event_id)
                return self.status_line("REJECTED")
            remaining = held - qty
            if remaining:
                self.reserved[order_id] = remaining
            else:
                del self.reserved[order_id]  # closed orders leave the OPEN list
            self.reserved_total -= qty
            if command == "SHIP":
                # SHIP consumes reserved stock; it needs no ``available`` check.
                self.on_hand -= qty

        self.processed_events.add(event_id)
        return self.status_line("OK")


def process(text: str) -> list[str]:
    """Run the whole input and return every output line, in order."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("empty input")

    header = lines[0].split()
    if len(header) != 2:
        raise ValueError("first line must be '<initial stock> <command count>'")

    stock = _parse_non_negative_int(header[0])
    count = _parse_positive_int(header[1])
    if stock is None or count is None:
        raise ValueError("initial stock must be >= 0 and command count >= 1")

    ledger = Ledger(stock)
    # Only the first ``count`` command lines are commands; anything after is ignored.
    output = [ledger.handle(line) for line in lines[1 : count + 1]]
    output.append(ledger.open_reservations_line())
    return output


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: solution.py [input-file]", file=sys.stderr)
        return 2
    text = Path(args[0]).read_text(encoding="utf-8") if args else sys.stdin.read()
    try:
        output = process(text)
    except ValueError as exc:  # explicit failure instead of a silent wrong answer
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write("\n".join(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
