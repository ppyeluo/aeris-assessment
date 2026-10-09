# Task B — Fulfilment Split Optimiser

Chooses how many units each warehouse ships so that an order of `Q` units is
fulfilled exactly, optimising three levels in order.

## Run

```bash
python3.11 solution.py samples/sample1.in
python3.11 solution.py < samples/sample1.in
python3.11 test_solution.py                        # 23 tests, incl. 400 randomised cross-checks
# from the repository root:
python3.11 -m unittest discover -s B -t B
```

Standard library only.

**Requires Python 3.11+** — this file uses `@dataclass(slots=True)`, which needs 3.10+,
so a bare `python3` fails with `TypeError: dataclass() got an unexpected keyword
argument 'slots'`. See the repository
[root README](../README.md#python-version-read-this-first) for the full explanation.

## Objective order

1. Fewest warehouses used.
2. Lowest total cost, where a used warehouse costs `fixed_cost + allocated_qty * unit_cost`.
3. Lexicographically smallest allocation list when sorted by `warehouse_id`.

Output is either a single `-1` (impossible) or `<count> <cost>` followed by
`<warehouse_id> <allocated_qty>` lines in ascending id order.

## Algorithm

* **Suffix DP.** `g[i][k][q]` = cheapest way to allocate exactly `q` units using
  exactly `k` warehouses taken from index `i` onward, with the warehouses sorted by id
  (that sort is also what the tie-break is defined over).
* **Sliding-window minimum.** Using warehouse `i` for `x` units costs
  `g[i+1][k-1][q-x] + fixed_i + x*unit_i`. Rewriting the term as
  `(g[i+1][k-1][q-x] - (q-x)*unit_i) + fixed_i + q*unit_i` makes the inner minimum a
  sliding-window minimum of width `stock_i`, so a monotonic deque removes the loop over
  `x` entirely.
* **Fewest warehouses** is then the smallest `k` with a finite `g[0][k][Q]`.
* **Lexicographic tie-break** is reconstructed greedily: walk the warehouses in
  ascending id and always *use* the current one when that still admits the optimal
  `(k, cost)`, choosing the smallest feasible quantity. Because the compared list is
  itself sorted by id, processing order equals comparison order — so a list that starts
  with a smaller id wins, and for an equal id the smaller quantity wins. That is exactly
  rule 3.

## Complexity

Let `K = min(W, Q)` (a used warehouse ships at least one unit).

* **Time O(W·K·Q)** — one pass over `q` per `(warehouse, k)` pair with O(1) amortised
  transitions, plus an O(W·stock) greedy reconstruction.
* **Space O(W·K·Q)** — every suffix layer is retained because the tie-break is
  reconstructed front-to-back.

Measured on the stated maximum (`W=30, Q=2000`): **0.21 s**. Exhaustive subset search
would be `2^30` and is not viable, which is why the DP exists.

## Assumptions

1. **Lexicographic order** is read as: sort each candidate's `(warehouse_id, qty)`
   pairs by id, then compare the sequences with standard lexicographic ordering (id
   first, then quantity, shorter strict prefix is smaller). A useful consequence is that
   when both `k` and cost tie, a solution whose first used warehouse has the smaller id
   wins, and for the same id the smaller allocation wins.
2. **`fixed_cost` is charged once per used warehouse** — i.e. only when the allocated
   quantity is greater than zero. A warehouse shipping nothing is not "used" and is
   absent from the output.
3. **Impossible orders** (including `sum(stock) < Q`) print a single line `-1`.
4. Input is validated: a malformed header or warehouse row is a hard error (stderr
   message, exit status 2) rather than a wrong answer.

## Test coverage

Official sample; impossible orders; all-empty stock; fewest-warehouses beating a
cheaper split; cheapest-wins among equal counts; fixed cost charged once; the
lexicographic tie-break (smaller id *and* smaller quantity); zero-stock warehouses
never used; three-way splits; partial use of a large stock; output sorted by id;
`W=30, Q=2000` finishing well under the time budget; input handling (extra rows, blank
lines, malformed rows, invalid header); and CLI behaviour including `-1`.

`RandomisedCrossCheck` additionally compares the DP against an exhaustive
subset-and-allocation reference on **400 fixed-seed random instances**, which is what
actually pins the three-level comparison order down.
