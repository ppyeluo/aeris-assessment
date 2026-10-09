#!/usr/bin/env python3
"""Task B - Fulfilment Split Optimiser.

An order of ``Q`` units is fulfilled from a set of warehouses.  A solution
chooses, for every used warehouse, how many units it ships, such that the
allocated total is exactly ``Q``.  Valid solutions are compared in this order:

1. fewest warehouses used;
2. lowest total shipping cost, where a used warehouse contributes
   ``fixed_cost + allocated_qty * unit_cost``;
3. lexicographically smallest allocation list when sorted by ``warehouse_id``.

Design decisions
----------------
* **DP over (used warehouses, allocated units).**  ``g[i][k][q]`` is the cheapest
  way to allocate exactly ``q`` units using exactly ``k`` of the warehouses from
  index ``i`` onward (ids sorted ascending).  Enumerating subsets is exponential
  (``W = 30``), so a DP is required -- see the complexity note below.
* **Sliding-window minimum.**  Using warehouse ``i`` for ``x`` units costs
  ``g[i+1][k-1][q-x] + fixed_i + x*unit_i``.  Rewriting the candidate value as
  ``(g[i+1][k-1][q-x] - (q-x)*unit_i) + fixed_i + q*unit_i`` shows the inner
  minimum is taken over a sliding window of width ``stock_i``, so a monotonic
  deque removes the ``x`` loop.
* **Lexicographic tie-break by greedy reconstruction.**  Because the target list
  is sorted by ``warehouse_id``, the comparison order matches the processing
  order.  Walking the warehouses by ascending id and always *using* the current
  one when that still admits an optimal solution (with the smallest feasible
  quantity) yields the lexicographically smallest list: a list whose first
  element has a smaller id wins, and for equal ids the smaller quantity wins.

Complexity
----------
Let ``K = min(W, Q)`` be the maximum number of warehouses that can be used.

* Time  **O(W * K * Q)**: one pass over ``q`` per (warehouse, k) pair, each
  transition O(1) amortised thanks to the deque; reconstruction is O(W * stock).
* Space **O(W * K * Q)** because every suffix layer is kept for reconstruction
  (about 1.9M integers at the maximum constraints, comfortably in memory).

Usage
-----
    python3.11 solution.py < input.txt
    python3.11 solution.py input.txt
"""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

INF = 10**30  # far above the largest reachable cost (30 * (10^6 + 2000 * 10^6))


@dataclass(frozen=True, slots=True)
class Warehouse:
    warehouse_id: str
    stock: int
    fixed_cost: int
    unit_cost: int


def optimise(
    warehouses: list[Warehouse], quantity: int
) -> tuple[int, int, list[tuple[str, int]]] | None:
    """Return ``(warehouse_count, total_cost, [(id, qty), ...])`` or None."""
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if sum(w.stock for w in warehouses) < quantity:
        return None  # cannot be fulfilled at all

    # Id ascending: this is the order the output must be sorted in, and the
    # order the lexicographic tie-break is defined over.
    ordered = sorted(warehouses, key=lambda w: w.warehouse_id)
    w_count = len(ordered)
    k_max = min(w_count, quantity)  # every used warehouse ships >= 1 unit

    # layers[i][k][q] = cheapest allocation of exactly q units using exactly k
    # warehouses drawn from ordered[i:].  layers[w_count] is the empty suffix.
    layers: list[list[list[int]]] = [None] * (w_count + 1)  # type: ignore[list-item]
    base = [[INF] * (quantity + 1) for _ in range(k_max + 1)]
    base[0][0] = 0
    layers[w_count] = base

    for i in range(w_count - 1, -1, -1):
        wid, stock, fixed, unit = (
            ordered[i].warehouse_id,
            ordered[i].stock,
            ordered[i].fixed_cost,
            ordered[i].unit_cost,
        )
        current = [row[:] for row in layers[i + 1]]  # option: skip warehouse i

        if stock > 0:
            # A suffix of ``k`` warehouses cannot exceed the number left from i.
            for k in range(1, min(k_max, w_count - i) + 1):
                source, target = layers[i + 1][k - 1], current[k]
                window: deque[tuple[int, int]] = deque()  # (q, value - q*unit)
                for q in range(1, quantity + 1):
                    q_in = q - 1
                    value = source[q_in]
                    if value < INF:
                        key = value - q_in * unit
                        while window and window[-1][1] >= key:
                            window.pop()
                        window.append((q_in, key))
                    # x = q - q_in must satisfy 1 <= x <= stock
                    left = q - stock
                    while window and window[0][0] < left:
                        window.popleft()
                    if window:
                        candidate = window[0][1] + fixed + q * unit
                        if candidate < target[q]:
                            target[q] = candidate

        layers[i] = current

    best_k = next(
        (k for k in range(1, k_max + 1) if layers[0][k][quantity] < INF), None
    )
    if best_k is None:
        return None
    best_cost = layers[0][best_k][quantity]

    # Greedy reconstruction: ascending id, use the warehouse if the optimum is
    # still reachable, with the smallest feasible quantity.
    remaining_qty, remaining_k, remaining_cost = quantity, best_k, best_cost
    allocation: list[tuple[str, int]] = []
    for i in range(w_count):
        warehouse = ordered[i]
        if remaining_k == 0:
            break
        pick: int | None = None
        for x in range(1, min(warehouse.stock, remaining_qty) + 1):
            rest = layers[i + 1][remaining_k - 1][remaining_qty - x]
            if rest < INF and rest + warehouse.fixed_cost + x * warehouse.unit_cost == remaining_cost:
                pick = x
                break
        if pick is not None:
            allocation.append((warehouse.warehouse_id, pick))
            remaining_qty -= pick
            remaining_k -= 1
            remaining_cost -= warehouse.fixed_cost + pick * warehouse.unit_cost
        if remaining_qty == 0 and remaining_k == 0:
            break

    if remaining_qty != 0 or remaining_k != 0:  # defensive: reconstruction must land
        raise AssertionError("reconstruction failed to reproduce the optimum")
    return best_k, best_cost, allocation


def parse(text: str) -> tuple[list[Warehouse], int]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("empty input")
    header = lines[0].split()
    if len(header) != 2:
        raise ValueError("first line must be '<warehouse count> <quantity>'")
    try:
        w_count, quantity = int(header[0]), int(header[1])
    except ValueError as exc:
        raise ValueError("first line must contain two integers") from exc
    if w_count < 1 or quantity < 1:
        raise ValueError("warehouse count and quantity must both be >= 1")

    rows = lines[1 : w_count + 1]
    if len(rows) != w_count:
        raise ValueError(f"expected {w_count} warehouse rows, found {len(rows)}")

    warehouses: list[Warehouse] = []
    for index, row in enumerate(rows, start=1):
        parts = row.split()
        if len(parts) != 4:
            raise ValueError(f"row {index}: expected '<id> <stock> <fixed> <unit>'")
        name = parts[0]
        try:
            stock, fixed, unit = int(parts[1]), int(parts[2]), int(parts[3])
        except ValueError as exc:
            raise ValueError(f"row {index}: stock/fixed/unit must be integers") from exc
        if not name:
            raise ValueError(f"row {index}: warehouse_id must not be empty")
        if stock < 0 or fixed < 0 or unit < 0:
            raise ValueError(f"row {index}: stock, fixed and unit cost must be >= 0")
        warehouses.append(Warehouse(name, stock, fixed, unit))
    return warehouses, quantity


def render(result: tuple[int, int, list[tuple[str, int]]] | None) -> list[str]:
    if result is None:
        return ["-1"]
    count, cost, allocation = result
    return [f"{count} {cost}", *(f"{name} {qty}" for name, qty in allocation)]


def process(text: str) -> list[str]:
    warehouses, quantity = parse(text)
    return render(optimise(warehouses, quantity))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: solution.py [input-file]", file=sys.stderr)
        return 2
    text = Path(args[0]).read_text(encoding="utf-8") if args else sys.stdin.read()
    try:
        output = process(text)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write("\n".join(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
