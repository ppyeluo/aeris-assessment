#!/usr/bin/env python3
"""Task A - automated tests.

Written with the standard library ``unittest`` so they run with either::

    python3.11 -m unittest discover -s A -t A
    python3.11 -m pytest A -q

Coverage: the official sample, idempotency (including events that were
*business-rejected*), atomic rejection, RELEASE/SHIP bounds, large values,
malformed input, and the OPEN trailer.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import solution  # noqa: E402  (path tweak must happen first)

SOLUTION = Path(__file__).resolve().parent / "solution.py"


def run(*lines: str) -> list[str]:
    return solution.process("\n".join(lines))


class OfficialSample(unittest.TestCase):
    """The example printed in the assessment must reproduce exactly."""

    INPUT = """10 6
RESERVE e1 o100 4
RESERVE e2 o200 7
SHIP    e3 o100 2
RELEASE e4 o100 2
RESTOCK e5 3
RESERVE e2 o999 1"""

    EXPECTED = [
        "OK 10 4",
        "REJECTED 10 4",
        "OK 8 2",
        "OK 8 0",
        "OK 11 0",
        "DUPLICATE 11 0",
        "OPEN 0",
    ]

    def test_sample_output_is_reproduced_line_by_line(self) -> None:
        self.assertEqual(solution.process(self.INPUT), self.EXPECTED)


class Idempotency(unittest.TestCase):
    def test_replayed_successful_event_is_duplicate(self) -> None:
        out = run("5 2", "RESERVE e1 o1 2", "RESERVE e1 o1 2")
        self.assertEqual(out, ["OK 5 2", "DUPLICATE 5 2", "OPEN 1 o1"])

    def test_rejected_event_is_still_processed(self) -> None:
        """The trap in the sample: a refused event is remembered."""
        out = run("1 3", "RESERVE e1 o1 5", "RESERVE e1 o1 1", "RESERVE e2 o1 1")
        self.assertEqual(
            out,
            [
                "REJECTED 1 0",  # insufficient stock
                "DUPLICATE 1 0",  # same event id -> duplicate, not a retry
                "OK 1 1",         # a fresh event id does succeed
                "OPEN 1 o1",
            ],
        )

    def test_duplicate_never_changes_state(self) -> None:
        lines = ["9 4", "RESERVE e1 o1 3", "RESTOCK e1 100", "SHIP e2 o1 1", "SHIP e2 o1 1"]
        out = run(*lines)
        # e1 replay is refused for RESTOCK, e2 replay is refused for SHIP
        self.assertEqual(out[:4], ["OK 9 3", "DUPLICATE 9 3", "OK 8 2", "DUPLICATE 8 2"])
        self.assertEqual(out[4], "OPEN 1 o1")


class RejectionIsAtomic(unittest.TestCase):
    def test_reject_leaves_state_untouched(self) -> None:
        out = run("5 2", "RESERVE e1 o1 4", "RESERVE e2 o1 2")
        self.assertEqual(out, ["OK 5 4", "REJECTED 5 4", "OPEN 1 o1"])

    def test_release_beyond_reservation_rejected(self) -> None:
        out = run("10 3", "RESERVE e1 o1 3", "RELEASE e2 o1 4", "SHIP e3 o1 4")
        self.assertEqual(out, ["OK 10 3", "REJECTED 10 3", "REJECTED 10 3", "OPEN 1 o1"])

    def test_malformed_lines_are_rejected_without_side_effects(self) -> None:
        out = run(
            "5 6",
            "RESERVE e1 o1 2",   # OK
            "BOGUS e2 o1 1",     # unknown command
            "RESERVE e3 o1",     # missing field
            "RESERVE e4 o1 0",   # qty must be positive
            "RESERVE e5 o1 -1",  # qty must be positive
            "RESERVE e6 o1 two", # qty must be an integer
        )
        self.assertEqual(
            out,
            ["OK 5 2"] + ["REJECTED 5 2"] * 5 + ["OPEN 1 o1"],
        )

    def test_malformed_line_does_not_consume_the_event_id(self) -> None:
        """A malformed line has no reliable event id, so it must not poison it."""
        out = run("5 2", "RESERVE e1 o1 x", "RESERVE e1 o1 2")
        self.assertEqual(out, ["REJECTED 5 0", "OK 5 2", "OPEN 1 o1"])


class CommandRules(unittest.TestCase):
    def test_reserve_may_use_exactly_the_available_units(self) -> None:
        out = run("5 2", "RESERVE e1 o1 5", "RESERVE e2 o2 1")
        self.assertEqual(out, ["OK 5 5", "REJECTED 5 5", "OPEN 1 o1"])

    def test_ship_consumes_on_hand_and_the_reservation(self) -> None:
        # SHIP lowers on_hand *and* clears the reservation, so those units are
        # gone for good: only 4 remain, and asking for 5 must be refused.
        out = run("10 3", "RESERVE e1 o1 6", "SHIP e2 o1 6", "RESERVE e3 o2 5")
        self.assertEqual(out, ["OK 10 6", "OK 4 0", "REJECTED 4 0", "OPEN 0"])

    def test_shipped_units_are_no_longer_available(self) -> None:
        out = run("10 3", "RESERVE e1 o1 6", "SHIP e2 o1 6", "RESERVE e3 o2 4")
        self.assertEqual(out, ["OK 10 6", "OK 4 0", "OK 4 4", "OPEN 1 o2"])

    def test_restock_frees_capacity(self) -> None:
        out = run("0 3", "RESERVE e1 o1 1", "RESTOCK e2 2", "RESERVE e3 o1 1")
        self.assertEqual(out, ["REJECTED 0 0", "OK 2 0", "OK 2 1", "OPEN 1 o1"])

    def test_reservations_accumulate_per_order(self) -> None:
        out = run("10 2", "RESERVE e1 o1 3", "RESERVE e2 o1 4")
        self.assertEqual(out, ["OK 10 3", "OK 10 7", "OPEN 1 o1"])

    def test_release_partial_keeps_the_order_open(self) -> None:
        out = run("10 2", "RESERVE e1 o1 5", "RELEASE e2 o1 2")
        self.assertEqual(out, ["OK 10 5", "OK 10 3", "OPEN 1 o1"])

    def test_large_quantities_fit(self) -> None:
        big = str(10**12)
        out = run(f"{big} 3", f"RESERVE e1 o1 {big}", f"RESERVE e2 o2 {big}", f"RESTOCK e3 {big}")
        self.assertEqual(out, [f"OK {big} {big}", f"REJECTED {big} {big}", f"OK {2 * 10**12} {big}", "OPEN 1 o1"])


class OutputFormat(unittest.TestCase):
    def test_open_lists_orders_sorted_with_a_count(self) -> None:
        out = run("20 3", "RESERVE e1 ob 1", "RESERVE e2 oa 1", "RESERVE e3 oc 1")
        self.assertEqual(out[-1], "OPEN 3 oa ob oc")

    def test_open_is_zero_when_everything_is_closed(self) -> None:
        out = run("5 2", "RESERVE e1 o1 2", "SHIP e2 o1 2")
        self.assertEqual(out[-1], "OPEN 0")

    def test_extra_lines_beyond_the_declared_count_are_ignored(self) -> None:
        out = solution.process("5 1\nRESERVE e1 o1 1\nRESERVE e2 o1 4\n")
        self.assertEqual(out, ["OK 5 1", "OPEN 1 o1"])

    def test_blank_lines_are_skipped(self) -> None:
        out = solution.process("5 1\n\nRESERVE e1 o1 1\n\n")
        self.assertEqual(out, ["OK 5 1", "OPEN 1 o1"])

    def test_missing_command_lines_are_tolerated(self) -> None:
        """Truncated input still produces the OPEN trailer."""
        out = solution.process("5 3\nRESERVE e1 o1 1")
        self.assertEqual(out, ["OK 5 1", "OPEN 1 o1"])

    def test_invalid_header_raises(self) -> None:
        for bad in ["", "5", "5 0", "-1 2", "5 x"]:
            with self.assertRaises(ValueError):
                solution.process(bad)


class CommandLineInterface(unittest.TestCase):
    def test_reads_stdin_and_writes_stdout(self) -> None:
        sample = "10 2\nRESERVE e1 o1 4\nSHIP e2 o1 1\n"
        proc = subprocess.run(
            [sys.executable, str(SOLUTION)],
            input=sample,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.splitlines(), ["OK 10 4", "OK 9 3", "OPEN 1 o1"])

    def test_reads_a_file_argument(self) -> None:
        sample = Path(__file__).resolve().parent / "samples" / "sample1.in"
        expected = (Path(__file__).resolve().parent / "samples" / "sample1.out").read_text(
            encoding="utf-8"
        ).splitlines()
        proc = subprocess.run(
            [sys.executable, str(SOLUTION), str(sample)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.splitlines(), expected)

    def test_invalid_header_exits_non_zero_with_a_message(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SOLUTION)],
            input="oops\n",
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error:", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
