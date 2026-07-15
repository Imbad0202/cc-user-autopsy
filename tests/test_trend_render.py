"""Trend ledger (spec §3 book 4): locked below 3 snapshots, comparison
table + sparklines when unlocked, habit-drift opener, narration book."""
import re
import sys
import unittest
from itertools import count
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from report_render import (  # noqa: E402
    _build_opening_band, _build_trend_ledger, _parse_ledger_narration,
    _sparkline_svg)


def _entry(d, commits=5, sessions=50, overall=6.0, badges=("delegation",),
           leaks=None):
    return {"date": d, "schema_version": 1,
            "scores": {"D1_delegation": 7},
            "overall_avg": overall,
            "badges": list(badges),
            "ledger": {"git_commits": commits, "sessions": sessions,
                       "sources_detected": ["claude"],
                       "leaks": leaks if leaks is not None else [
                           {"type": "repeated_instructions",
                            "weekly_cost_usd": 1.5, "weekly_tokens": 40000,
                            "occurrences": 6}]}}


ANALYSIS = {
    "meta": {"total_sessions": 61},
    "scores": {"_overall": {"avg": 6.4, "dimensions_scored": 9,
                            "dimensions_total": 9}},
    "ledger": {"window": {"start": "2026-06-01", "end": "2026-07-10",
                          "days": 39},
               "output": {"git_commits": 44, "git_pushes": 12,
                          "sessions_with_commits": 18},
               "leaks": {"window_weeks": 5.6, "items": [
                   {"type": "sunk_cost", "weekly_cost_usd": 2.25,
                    "weekly_tokens": 60000, "occurrences": 3,
                    "evidence": ["sid-secret-1"]}]}},
    "badges": {"schema_version": 1, "standard_version": "v1", "items": [
        {"id": "delegation", "earned": True, "n": 20, "metrics": {},
         "thresholds": {}},
        {"id": "root_cause", "earned": False, "n": 40, "metrics": {},
         "thresholds": {}}]},
}

DRIFT_PASSED = {"habit_drift": {
    "id": "habit_drift", "gate_passed": True, "suppressed_by_guard": False,
    "n": 10, "metrics": {"weeks": 10, "early_median_len": 180,
                         "late_median_len": 90, "early_good_rate": 68.0,
                         "late_good_rate": 61.0}, "reason": None}}
DRIFT_GATED = {"habit_drift": {
    "id": "habit_drift", "gate_passed": False, "suppressed_by_guard": False,
    "n": 3, "metrics": {}, "reason": "fewer than 8 weeks"}}

ENTRIES_3 = [_entry("2026-04-05", commits=20, overall=5.5),
             _entry("2026-05-20", commits=30, overall=5.9),
             _entry("2026-07-01", commits=38, overall=6.2)]


def build(entries, blind_spots=DRIFT_GATED, narration="", locale="en"):
    return _build_trend_ledger(ANALYSIS, entries,
                               _parse_ledger_narration(narration),
                               locale, count(7), blind_spots)


class LockedStateTests(unittest.TestCase):
    def test_locked_below_three_snapshots(self):
        html = build(ENTRIES_3[:2])
        self.assertIn('id="ledger-trend"', html)
        # "unlocks after 1 more run" — no table, no exhibit
        self.assertIn("1", html)
        self.assertNotIn("c-exhibit", html)
        self.assertNotIn("<table", html)

    def test_locked_message_counts_remaining_runs(self):
        html = build([])
        self.assertIn("3", html)


class UnlockedTests(unittest.TestCase):
    def test_three_snapshots_render_table_and_sparklines(self):
        html = build(ENTRIES_3)
        self.assertIn("c-exhibit", html)
        self.assertIn("<svg", html)
        # this-run values from live analysis
        self.assertIn("44", html)     # commits this run
        self.assertIn("6.4", html)    # overall this run
        # last-run column from newest snapshot
        self.assertIn("2026-07-01", html)

    def test_reference_column_picks_entry_closest_to_90_days(self):
        html = build(ENTRIES_3)
        # newest 2026-07-01 − 90d = 2026-04-02 → 2026-04-05 wins over 2026-05-20
        self.assertIn("2026-04-05", html)

    def test_history_leak_cost_read_from_compact_list_shape(self):
        html = build(ENTRIES_3)
        self.assertIn("1.50", html)   # history compact-list sum
        self.assertIn("2.25", html)   # this-run dict-shape sum

    def test_no_session_ids_leak(self):
        self.assertNotIn("sid-secret-1", build(ENTRIES_3))

    def test_drift_opener_when_gate_passed(self):
        html = build(ENTRIES_3, blind_spots=DRIFT_PASSED)
        self.assertIn("c-blindspot", html)
        self.assertIn("180", html)
        self.assertIn("90", html)

    def test_no_drift_opener_when_gated(self):
        self.assertNotIn("c-blindspot", build(ENTRIES_3, blind_spots=DRIFT_GATED))

    def test_narration_title_and_prose(self):
        md = "# trend-ledger\nCommits per run rose 2.2x over three months.\n\nBody prose."
        html = build(ENTRIES_3, narration=md)
        self.assertIn("Commits per run rose 2.2x over three months.", html)
        self.assertIn("Body prose.", html)

    def test_zh_locale_renders(self):
        html = build(ENTRIES_3, locale="zh_TW")
        self.assertIn('id="ledger-trend"', html)
        self.assertNotIn("—", html)


class NarrationBookTests(unittest.TestCase):
    def test_trend_book_parsed(self):
        d = _parse_ledger_narration("# trend-ledger\nClaim T.\n")
        self.assertEqual(d["trend-ledger"], "Claim T.")


class OpeningBandTrendTests(unittest.TestCase):
    LEDGER = {"window": {"start": "2026-06-01", "end": "2026-07-10",
                         "days": 39},
              "output": {"git_commits": 44, "git_pushes": 12,
                         "sessions_with_commits": 18}}
    NARR = _parse_ledger_narration(
        "# output-ledger\nO claim.\n# trend-ledger\nT claim.\n")

    def test_trend_claim_included_when_flag_true(self):
        html = _build_opening_band(self.LEDGER, self.NARR, "en",
                                   include_trend_finding=True)
        self.assertIn("T claim.", html)

    def test_trend_claim_suppressed_by_default(self):
        html = _build_opening_band(self.LEDGER, self.NARR, "en")
        self.assertNotIn("T claim.", html)


class SparklineTests(unittest.TestCase):
    def test_polyline_with_points(self):
        svg = _sparkline_svg([1, 2, 3])
        self.assertIn("<svg", svg)
        self.assertIn("polyline", svg)

    def test_fewer_than_two_numbers_empty(self):
        self.assertEqual(_sparkline_svg([5]), "")
        self.assertEqual(_sparkline_svg([None, None]), "")

    def test_none_values_skipped_not_crash(self):
        svg = _sparkline_svg([1, None, 3])
        self.assertIn("polyline", svg)

    def test_flat_series_no_zero_division(self):
        self.assertIn("polyline", _sparkline_svg([2, 2, 2]))


if __name__ == "__main__":
    unittest.main()
