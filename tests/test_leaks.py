import unittest
from datetime import datetime, timedelta, timezone

from scripts.aggregate import (
    bs_repeated_instructions, compute_blind_spots, compute_leaks)

BASE = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
WINDOW = {"start": "2026-06-01", "end": "2026-07-11", "days": 40}


def _sess(sid, days, outcome, tokens=40000, prompt="tune the ingestion retry logic"):
    return {"sid": sid, "start": (BASE + timedelta(days=days)).isoformat(),
            "outcome": outcome, "first_prompt": prompt,
            "first_prompt_len": len(prompt), "token_accel": None,
            "duration_min": 60, "total_tokens": tokens,
            "input_tokens": tokens - 4000, "output_tokens": 4000,
            "cache_create_tokens": 0, "cache_read_tokens": 0,
            "model_counts": {"claude-opus-4-6": 10}, "goal_cats": {},
            "git_commits": 0, "interrupts": 0, "friction_counts": {}}


class LeakCatalogTests(unittest.TestCase):
    def test_failed_burn_leak(self):
        rated = ([_sess(f"f{i}", i, "not_achieved") for i in range(6)]
                 + [_sess(f"g{i}", 10 + i, "fully_achieved") for i in range(6)])
        bs = compute_blind_spots(rated, rated, [], [], BASE + timedelta(days=40))
        leaks = compute_leaks(bs, rated, WINDOW)
        types = [i["type"] for i in leaks["items"]]
        self.assertIn("failed_session_burn", types)
        item = next(i for i in leaks["items"] if i["type"] == "failed_session_burn")
        self.assertGreater(item["weekly_cost_usd"], 0)
        self.assertEqual(item["occurrences"], 6)
        self.assertLessEqual(len(item["evidence"]), 3)

    def test_below_floor_no_failed_burn(self):
        rated = ([_sess(f"f{i}", i, "not_achieved") for i in range(4)]
                 + [_sess(f"g{i}", 10 + i, "fully_achieved") for i in range(20)])
        bs = compute_blind_spots(rated, rated, [], [], BASE + timedelta(days=40))
        leaks = compute_leaks(bs, rated, WINDOW)
        self.assertNotIn("failed_session_burn",
                         [i["type"] for i in leaks["items"]])

    def test_ranked_desc_and_max_three(self):
        rated = ([_sess(f"f{i}", i, "not_achieved") for i in range(6)]
                 + [_sess(f"g{i}", 10 + i, "fully_achieved") for i in range(6)])
        bs = compute_blind_spots(rated, rated, [], [], BASE + timedelta(days=40))
        leaks = compute_leaks(bs, rated, WINDOW)
        costs = [i["weekly_cost_usd"] for i in leaks["items"]]
        self.assertEqual(costs, sorted(costs, reverse=True))
        self.assertLessEqual(len(leaks["items"]), 3)

    def test_window_weeks_floor(self):
        leaks = compute_leaks(
            compute_blind_spots([], [], [], [], BASE), [],
            {"start": None, "end": None, "days": 3})
        self.assertEqual(leaks["window_weeks"], 1.0)
        self.assertEqual(leaks["items"], [])

    def test_failed_sessions_before_window_start_excluded_from_weekly_cost(self):
        # 5 not_achieved sessions inside the window, 5 not_achieved 200 days
        # earlier (well before window start) — occurrences/weekly_cost must
        # reflect only the in-window 5.
        rated = ([_sess(f"old{i}", -200 + i, "not_achieved") for i in range(5)]
                 + [_sess(f"f{i}", i, "not_achieved") for i in range(5)]
                 + [_sess(f"g{i}", 10 + i, "fully_achieved") for i in range(6)])
        bs = compute_blind_spots(rated, rated, [], [], BASE + timedelta(days=40))
        leaks = compute_leaks(bs, rated, WINDOW)
        item = next(i for i in leaks["items"] if i["type"] == "failed_session_burn")
        self.assertEqual(item["occurrences"], 5)

    def test_repeated_instructions_usd_prices_claude_share_only(self):
        # A pattern dominated by Codex occurrences with only a few Claude
        # ones: pricing all occurrences at the Claude rate vs. pricing only
        # the Claude share must produce a distinguishable ($0.01+) gap.
        INSTR = ("Always reply in zh-TW, run the full pytest suite before "
                 "you claim done, never skip hooks, and keep commit messages "
                 "in the conventional-commit format we agreed on earlier") * 3

        def _row(sid, days, source=None, coverage=None):
            row = {"session_id": sid,
                  "start_time": (BASE + timedelta(days=days)).isoformat(),
                  "first_prompt": INSTR}
            if source:
                row["source"], row["coverage"] = source, coverage
            return row

        claude_rows = [_row(f"c{i}", i % 50) for i in range(10)]
        codex_rows = [_row(f"x{i}", i % 50, source="codex", coverage="full")
                      for i in range(2000)]
        bs1 = bs_repeated_instructions(claude_rows, codex_rows)
        self.assertTrue(bs1["gate_passed"])
        p = bs1["metrics"]["patterns"][0]
        self.assertEqual(p["occurrences"], 2010)
        self.assertEqual(p["claude_wasted_tokens"], 9 * (len(p["exemplar"]) // 4))
        self.assertEqual(p["est_wasted_tokens"], 2009 * (len(p["exemplar"]) // 4))
        self.assertGreater(p["claude_wasted_tokens"], 0)
        self.assertLess(p["claude_wasted_tokens"], p["est_wasted_tokens"])

        bs = {"repeated_instructions": bs1, "sunk_cost": {}}
        leaks = compute_leaks(bs, [], WINDOW)
        item = next(i for i in leaks["items"] if i["type"] == "repeated_instructions")
        weeks = round(max(WINDOW["days"] / 7.0, 1.0), 1)
        # weekly_tokens uses the all-source est_wasted_tokens (bigger numerator)
        self.assertEqual(item["weekly_tokens"], int(p["est_wasted_tokens"] / weeks))
        # weekly_cost_usd is derived from claude_wasted_tokens only, which
        # is strictly smaller than pricing all occurrences would give.
        all_source_cost = round(
            (p["est_wasted_tokens"] / weeks) / 1e6 * 15.0, 2)
        self.assertLess(item["weekly_cost_usd"], all_source_cost)


if __name__ == "__main__":
    unittest.main()
