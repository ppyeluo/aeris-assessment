#!/usr/bin/env python3
"""Task B - automated tests.

Runs with either runner::

    python3.11 -m unittest discover -s B -t B
    python3.11 -m pytest B -q

Besides the worked examples, ``RandomisedCrossCheck`` compares the DP against a
brute-force reference over random small instances, which is what pins down the
three-level comparison order (fewest warehouses -> cheapest -> lexicographic).
"""

from __future__ import annotations

import itertools
import random
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import solution  # noqa: E402  (path tweak must happen first)
from solution import Warehouse  # noqa: E402  (import follows the path tweak)

SOLUTION = Path(__file__).resolve().parent / "solution.py"
SAMPLES = Path(__file__).resolve().parent / "samples"


def wh(name: str, stock: int, fixed: int, unit: int) -> Warehouse:
    return Warehouse(name, stock, fixed, unit)


def brute_force(
    warehouses: list[Warehouse], quantity: int
) -> tuple[int, int, tuple[tuple[str, int], ...]] | None:
    """Reference implementation: exhaustive over subsets and allocations."""
    best = None
    n = len(warehouses)
    for r in range(1, n + 1):
        for combo in itertools.combinations(range(n), r):
            def walk(pos: int, remaining: int, acc: list, cost: int) -> None:
                nonlocal best
                if pos == len(combo):
                    if remaining == 0:
                        candidate = (r, cost, tuple(sorted(acc)))
                        if best is None or candidate < best:
                            best = candidate
                    return
                item = warehouses[combo[pos]]
                for x in range(1, min(item.stock, remaining) + 1):
                    acc.append((item.warehouse_id, x))
                    walk(pos + 1, remaining - x, acc, cost + item.fixed_cost + x * item.unit_cost)
                    acc.pop()

            walk(0, quantity, [], 0)
    return best


class OfficialSample(unittest.TestCase):
    INPUT = "3 7\nAU 5 8 2\nCN 7 20 1\nUS 4 3 4\n"

    def test_sample_matches_the_statement(self) -> None:
        self.assertEqual(solution.process(self.INPUT), ["1 27", "CN 7"])

    def test_sample_files(self) -> None:
        expected = (SAMPLES / "sample1.out").read_text(encoding="utf-8").splitlines()
        self.assertEqual(solution.process((SAMPLES / "sample1.in").read_text(encoding="utf-8")), expected)


class ObjectiveOrdering(unittest.TestCase):
    def test_fewest_warehouses_beats_cheaper_split(self) -> None:
        """k=1 with an expensive single warehouse wins over a cheap pair."""
        warehouses = [wh("A", 6, 1, 1), wh("B", 6, 1, 1), wh("C", 10, 1000, 1000)]
        self.assertEqual(
            solution.optimise(warehouses, 10),
            (1, 11000, [("C", 10)]),
        )

    def test_cheapest_wins_among_equal_warehouse_counts(self) -> None:
        warehouses = [wh("A", 10, 1000, 0), wh("B", 10, 0, 1), wh("C", 10, 0, 1)]
        self.assertEqual(solution.optimise(warehouses, 10), (1, 10, [("B", 10)]))

    def test_fixed_cost_is_charged_once_per_used_warehouse(self) -> None:
        warehouses = [wh("A", 5, 100, 0), wh("B", 5, 100, 0)]
        # Two warehouses: 200 fixed, no unit cost. One warehouse cannot cover 6.
        self.assertEqual(solution.optimise(warehouses, 6), (2, 200, [("A", 1), ("B", 5)]))

    def test_lexicographic_tie_break_prefers_smaller_id_and_smaller_quantity(self) -> None:
        # k=1 impossible; every pair costs 0, so lexicographic order decides:
        # {A,B} starts with A and can give A only 2 units (B ships 3).
        warehouses = [wh("A", 3, 0, 0), wh("B", 3, 0, 0), wh("C", 2, 0, 0)]
        self.assertEqual(solution.optimise(warehouses, 5), (2, 0, [("A", 2), ("B", 3)]))

    def test_zero_stock_warehouse_is_never_used(self) -> None:
        warehouses = [wh("A", 0, 0, 0), wh("B", 3, 5, 1)]
        self.assertEqual(solution.optimise(warehouses, 3), (1, 8, [("B", 3)]))

    def test_split_across_three_warehouses(self) -> None:
        warehouses = [wh("A", 2, 1, 1), wh("B", 2, 1, 1), wh("C", 2, 1, 1)]
        self.assertEqual(solution.optimise(warehouses, 5), (3, 8, [("A", 1), ("B", 2), ("C", 2)]))

    def test_uses_only_part_of_a_large_stock(self) -> None:
        self.assertEqual(solution.optimise([wh("A", 10, 3, 2)], 4), (1, 11, [("A", 4)]))

    def test_order_is_sorted_by_warehouse_id_in_the_output(self) -> None:
        warehouses = [wh("ZZ", 5, 0, 0), wh("AA", 5, 0, 0)]
        result = solution.optimise(warehouses, 8)
        self.assertIsNotNone(result)
        _, _, allocation = result
        self.assertEqual([name for name, _ in allocation], sorted(name for name, _ in allocation))


class ImpossibleOrders(unittest.TestCase):
    def test_total_stock_below_quantity(self) -> None:
        warehouses = [wh("A", 3, 1, 1), wh("B", 3, 1, 1)]
        self.assertIsNone(solution.optimise(warehouses, 10))
        self.assertEqual(solution.process("2 10\nA 3 1 1\nB 3 1 1\n"), ["-1"])

    def test_all_warehouses_empty(self) -> None:
        warehouses = [wh("A", 0, 0, 0), wh("B", 0, 0, 0)]
        self.assertIsNone(solution.optimise(warehouses, 1))


class RandomisedCrossCheck(unittest.TestCase):
    """DP vs exhaustive search on small instances (fixed seed for reproducibility)."""

    def test_matches_brute_force(self) -> None:
        rng = random.Random(20261009)
        ids = ["AU", "CN", "DE", "JP", "SG", "US"]
        checked = 0
        for _ in range(400):
            warehouse_count = rng.randint(1, 5)
            quantity = rng.randint(1, 14)
            warehouses = [
                wh(ids[i], rng.randint(0, 7), rng.randint(0, 9), rng.randint(0, 5))
                for i in range(warehouse_count)
            ]
            expected = brute_force(warehouses, quantity)
            actual = solution.optimise(warehouses, quantity)
            if expected is None:
                self.assertIsNone(actual, f"{warehouses} Q={quantity}")
            else:
                self.assertIsNotNone(actual, f"{warehouses} Q={quantity}")
                used_count, cost, allocation = actual
                self.assertEqual(
                    (used_count, cost, tuple(allocation)),
                    expected,
                    f"{warehouses} Q={quantity}",
                )
            checked += 1
        self.assertEqual(checked, 400)


class Scale(unittest.TestCase):
    def test_maximum_constraints_finish_quickly(self) -> None:
        rng = random.Random(11)
        warehouses = [
            wh(f"WH{i:02d}", rng.randint(0, 2000), rng.randint(0, 10**6), rng.randint(0, 10**6))
            for i in range(30)
        ]
        started = time.perf_counter()
        result = solution.optimise(warehouses, 2000)
        elapsed = time.perf_counter() - started
        self.assertIsNotNone(result)
        self.assertLess(elapsed, 5.0, f"DP took {elapsed:.2f}s on the largest case")

    def test_impossible_boundary_is_immediate(self) -> None:
        warehouses = [wh("A", 1, 1, 1)]
        self.assertIsNone(solution.optimise(warehouses, 2000))


class InputHandling(unittest.TestCase):
    def test_extra_rows_beyond_w_are_ignored(self) -> None:
        text = "1 3\nA 3 0 0\nB 99 99 99\n"
        self.assertEqual(solution.process(text), ["1 0", "A 3"])

    def test_blank_lines_are_skipped(self) -> None:
        self.assertEqual(solution.process("1 2\n\nA 2 0 0\n"), ["1 0", "A 2"])

    def test_invalid_inputs_raise(self) -> None:
        for bad in ["", "3\n", "0 5\n", "3 0\n", "2 5\nA 1 1 1\n", "1 2\nA 1 1\n"]:
            with self.assertRaises(ValueError):
                solution.process(bad)

    def test_unknown_extra_columns_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            solution.process("1 2\nA 1 1 1 1\n")


class CommandLineInterface(unittest.TestCase):
    def test_stdin_to_stdout(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SOLUTION)],
            input="3 7\nAU 5 8 2\nCN 7 20 1\nUS 4 3 4\n",
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.splitlines(), ["1 27", "CN 7"])

    def test_file_argument(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SOLUTION), str(SAMPLES / "sample1.in")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(
            proc.stdout.splitlines(),
            (SAMPLES / "sample1.out").read_text(encoding="utf-8").splitlines(),
        )

    def test_impossible_order_prints_minus_one(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SOLUTION)],
            input="1 10\nA 1 1 1\n",
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "-1")

    def test_bad_input_exits_non_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SOLUTION)], input="oops\n", capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error:", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
