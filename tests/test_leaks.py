import unittest
from datetime import datetime, timedelta, timezone

from scripts.aggregate import compute_blind_spots, compute_leaks

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


if __name__ == "__main__":
    unittest.main()
