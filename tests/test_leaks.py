import unittest
from datetime import datetime, timedelta, timezone

from scripts.aggregate import (
    bs_repeated_instructions, bs_sunk_cost, compute_api_equivalent_cost,
    compute_blind_spots, compute_leaks, PRICING, _CHEAPEST_INPUT_RATE,
    _leak_cost_usd)

BASE = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
WINDOW = {"start": "2026-06-01", "end": "2026-07-11", "days": 40}


def _sess(sid, days, outcome, tokens=40000, prompt="tune the ingestion retry logic",
         start=None):
    return {"sid": sid, "start": (start or BASE + timedelta(days=days)).isoformat(),
            "outcome": outcome, "first_prompt": prompt,
            "first_prompt_len": len(prompt), "token_accel": None,
            "duration_min": 60, "total_tokens": tokens,
            "input_tokens": tokens - 4000, "output_tokens": 4000,
            "cache_create_tokens": 0, "cache_read_tokens": 0,
            "model_counts": {"claude-opus-4-6": 10}, "goal_cats": {},
            "git_commits": 0, "interrupts": 0, "friction_counts": {}}


_SUNK_FAIL_PROMPT = "refactor the payment reconciliation pipeline to stream batches"
_SUNK_RETRY_PROMPT = ("refactor the payment reconciliation pipeline to stream "
                      "batches cleanly")


def _sunk_sess(sid, days, outcome, prompt=_SUNK_FAIL_PROMPT, accel=None,
               dur=120, tokens=50000):
    return {"sid": sid, "start": (BASE + timedelta(days=days)).isoformat(),
            "outcome": outcome, "first_prompt": prompt, "token_accel": accel,
            "duration_min": dur, "total_tokens": tokens,
            "input_tokens": tokens - 5000, "output_tokens": 5000,
            "cache_create_tokens": 0, "cache_read_tokens": 0,
            "model_counts": {"claude-opus-4-6": 10}}


def _sunk_pair(i, base_days):
    failed = _sunk_sess(f"f{i}", base_days + 2 * i, "not_achieved", accel=2.0)
    retry = _sunk_sess(f"r{i}", base_days + 2 * i + 1, "fully_achieved",
                       prompt=_SUNK_RETRY_PROMPT, accel=1.0, dur=30, tokens=8000)
    return [failed, retry]


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

    def test_sunk_cost_pairs_before_window_produce_no_card(self):
        # 3 confirmed sunk-cost pairs, all 200 days before WINDOW's start —
        # the gate passes on these out-of-window pairs, but the windowed
        # failed list compute_leaks builds is then empty. No sunk_cost item
        # should be emitted (no $0.00 / 0 occurrences / no-evidence card).
        base_days = -200
        rated = [s for i in range(3) for s in _sunk_pair(i, base_days)]
        # guard needs a fully_achieved population without acceleration,
        # also placed well before the window so it doesn't interfere.
        rated += [_sunk_sess(f"g{i}", base_days + 40 + i, "fully_achieved",
                             prompt=f"unrelated task {i} entirely", accel=1.0)
                  for i in range(6)]
        bs = compute_blind_spots(rated, rated, [], [], BASE + timedelta(days=40))
        self.assertTrue(bs["sunk_cost"]["gate_passed"])
        leaks = compute_leaks(bs, rated, WINDOW)
        types = [i["type"] for i in leaks["items"]]
        self.assertNotIn("sunk_cost", types)

    def test_window_end_date_is_tz_independent(self):
        # Fix 1: window bounds are calendar dates parsed with
        # date.fromisoformat(), not _parse_dt(...).date() (which assumes
        # UTC then converts to local — west of UTC "2026-07-11" would
        # shift to 2026-07-10 local and wrongly exclude a session whose
        # local wall-clock start is still on the inclusive end date). The
        # session's own start is built from the local system tz (via
        # astimezone(), matching how _parse_dt normalizes real timestamps)
        # so its calendar date is unambiguously 2026-07-11 local no matter
        # what timezone runs this test — isolating the assertion to the
        # window-bound parsing fix, not session-timestamp normalization.
        window = {"start": "2026-06-01", "end": "2026-07-11", "days": 40}
        late_on_end_date = datetime(2026, 7, 11, 23, 30).astimezone()
        rated = [_sess("late", None, "not_achieved", start=late_on_end_date)]
        rated += [_sess(f"f{i}", i, "not_achieved") for i in range(5)]
        bs = compute_blind_spots(rated, rated, [], [], BASE + timedelta(days=40))
        leaks = compute_leaks(bs, rated, window)
        item = next(i for i in leaks["items"] if i["type"] == "failed_session_burn")
        self.assertEqual(item["occurrences"], 6)


class RepeatedInstructionsCheapestRateTests(unittest.TestCase):
    # Fix 4: repeated-instruction dollars price at the single cheapest known
    # input rate — no per-session/dominant-model attribution, since a
    # repeated prompt isn't tracked back to which session/model retyped it.
    def test_leak_usd_uses_cheapest_input_rate_formula(self):
        INSTR = ("Always reply in zh-TW, run the full pytest suite before "
                 "you claim done, never skip hooks") * 3
        rows = [{"session_id": f"c{i}",
                 "start_time": (BASE + timedelta(weeks=i % 3, days=i)).isoformat(),
                 "first_prompt": INSTR} for i in range(5)]
        bs1 = bs_repeated_instructions(rows, [])
        self.assertTrue(bs1["gate_passed"])
        p = bs1["metrics"]["patterns"][0]
        bs = {"repeated_instructions": bs1, "sunk_cost": {}}
        leaks = compute_leaks(bs, [], WINDOW)
        item = next(i for i in leaks["items"] if i["type"] == "repeated_instructions")
        weeks = round(max(WINDOW["days"] / 7.0, 1.0), 1)
        claude_tokens_week = p["claude_wasted_tokens"] / weeks
        expected = round(claude_tokens_week / 1e6 * _CHEAPEST_INPUT_RATE, 2)
        self.assertEqual(item["weekly_cost_usd"], expected)

    def test_cheapest_rate_is_the_min_across_pricing_table(self):
        self.assertEqual(_CHEAPEST_INPUT_RATE, min(p["input"] for p in PRICING.values()))

    def test_repeated_instructions_cost_independent_of_rated_models(self):
        # An all-Opus rated pool must NOT push the repeated-instructions
        # price above the cheapest known rate — there is no dominant-model
        # lookup anymore; the pool argument to compute_leaks doesn't affect
        # this item's pricing at all.
        INSTR = "tune the ingestion retry pipeline please and keep it tidy" * 3
        rows = [{"session_id": f"c{i}",
                 "start_time": (BASE + timedelta(weeks=i % 3, days=i)).isoformat(),
                 "first_prompt": INSTR} for i in range(5)]
        bs1 = bs_repeated_instructions(rows, [])
        bs = {"repeated_instructions": bs1, "sunk_cost": {}}
        opus_rated = [_sess(f"o{i}", i, "fully_achieved") for i in range(10)]
        leaks_opus = compute_leaks(bs, opus_rated, WINDOW)
        leaks_empty = compute_leaks(bs, [], WINDOW)
        item_opus = next(i for i in leaks_opus["items"] if i["type"] == "repeated_instructions")
        item_empty = next(i for i in leaks_empty["items"] if i["type"] == "repeated_instructions")
        self.assertEqual(item_opus["weekly_cost_usd"], item_empty["weekly_cost_usd"])


class LeakCostUsdTests(unittest.TestCase):
    # Fix 2: _leak_cost_usd is the lower-bound pricing helper used by
    # sunk_cost / failed_session_burn leak items — same blended-by-model
    # shape as compute_api_equivalent_cost, but unknown models price at the
    # CHEAPEST known rates (not the Opus fallback) and cache_creation tokens
    # price at base input rate (not the 2x cache_write upper bound).
    def test_unknown_model_prices_at_cheapest_rates_not_opus(self):
        sessions = [{"model_counts": {"unknown-model-x": 1},
                     "input_tokens": 100_000, "output_tokens": 10_000,
                     "cache_create_tokens": 0, "cache_read_tokens": 0}]
        leak_cost = _leak_cost_usd(sessions)
        api_equiv_cost = compute_api_equivalent_cost(sessions)
        # compute_api_equivalent_cost falls back to Opus pricing for unknown
        # models — strictly more expensive than the cheapest-rate floor.
        self.assertLess(leak_cost, api_equiv_cost)
        cheapest_in = min(p["input"] for p in PRICING.values())
        cheapest_out = min(p["output"] for p in PRICING.values())
        expected = round(100_000 / 1e6 * cheapest_in + 10_000 / 1e6 * cheapest_out, 2)
        self.assertEqual(leak_cost, expected)

    def test_known_model_cache_write_priced_at_base_input_rate(self):
        # A known model (opus): cache_creation tokens must price at the
        # model's base INPUT rate, not the 2x cache_write upper-bound rate
        # compute_api_equivalent_cost uses.
        sessions = [{"model_counts": {"claude-opus-4-6": 1},
                     "input_tokens": 0, "output_tokens": 0,
                     "cache_create_tokens": 100_000, "cache_read_tokens": 0}]
        leak_cost = _leak_cost_usd(sessions)
        opus = PRICING["claude-opus-4-6"]
        expected = round(100_000 / 1e6 * opus["input"], 2)
        self.assertEqual(leak_cost, expected)
        # Sanity: strictly cheaper than pricing the same tokens at the
        # cache_write (2x input) rate compute_api_equivalent_cost would use.
        cache_write_priced = round(100_000 / 1e6 * opus["cache_write"], 2)
        self.assertLess(leak_cost, cache_write_priced)

    def test_known_model_cache_read_priced_normally(self):
        sessions = [{"model_counts": {"claude-sonnet-4-6": 1},
                     "input_tokens": 0, "output_tokens": 0,
                     "cache_create_tokens": 0, "cache_read_tokens": 200_000}]
        leak_cost = _leak_cost_usd(sessions)
        sonnet = PRICING["claude-sonnet-4-6"]
        expected = round(200_000 / 1e6 * sonnet["cache_read"], 2)
        self.assertEqual(leak_cost, expected)

    def test_empty_sessions_is_zero(self):
        self.assertEqual(_leak_cost_usd([]), 0.0)

    def test_sunk_cost_and_failed_burn_use_leak_cost_usd(self):
        # End-to-end: sunk_cost / failed_session_burn weekly_cost_usd must
        # come from _leak_cost_usd, not compute_api_equivalent_cost — verify
        # by using an unknown model where the two functions diverge.
        rated = ([_sess(f"f{i}", i, "not_achieved") for i in range(6)]
                 + [_sess(f"g{i}", 10 + i, "fully_achieved") for i in range(6)])
        for s in rated:
            s["model_counts"] = {"unknown-model-y": 10}
        bs = compute_blind_spots(rated, rated, [], [], BASE + timedelta(days=40))
        leaks = compute_leaks(bs, rated, WINDOW)
        item = next(i for i in leaks["items"] if i["type"] == "failed_session_burn")
        burn = [s for s in rated if s["outcome"] == "not_achieved"]
        weeks = round(max(WINDOW["days"] / 7.0, 1.0), 1)
        expected = round(_leak_cost_usd(burn) / weeks, 2)
        self.assertEqual(item["weekly_cost_usd"], expected)
        # And it must differ from (be less than) what compute_api_equivalent_cost
        # would have produced for the same sessions.
        api_equiv_weekly = round(compute_api_equivalent_cost(burn) / weeks, 2)
        self.assertLess(item["weekly_cost_usd"], api_equiv_weekly)


if __name__ == "__main__":
    unittest.main()
