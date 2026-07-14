import unittest
from datetime import datetime, timedelta, timezone

from scripts.aggregate import (
    bs_repeated_instructions, bs_sunk_cost, counterexample_similar,
    normalize_prompt, prompt_similarity, week_key)


class NormalizePromptTests(unittest.TestCase):
    def test_case_punct_whitespace_collapse(self):
        self.assertEqual(
            normalize_prompt("  Fix the FLAKY test!!  (again) "),
            "fix the flaky test again")

    def test_cjk_preserved(self):
        self.assertEqual(normalize_prompt("回覆一律用繁體中文，先跑測試"),
                         "回覆一律用繁體中文 先跑測試")

    def test_non_string_is_empty(self):
        self.assertEqual(normalize_prompt(None), "")
        self.assertEqual(normalize_prompt(42), "")

    def test_truncated_to_200_chars(self):
        self.assertEqual(len(normalize_prompt("a b " * 200)), 200)


class PromptSimilarityTests(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(prompt_similarity("fix the test", "fix the test"), 1.0)

    def test_disjoint(self):
        self.assertEqual(prompt_similarity("alpha beta", "gamma delta"), 0.0)

    def test_partial_overlap(self):
        # {fix,the,flaky,test} vs {fix,the,broken,test}: 3/5
        self.assertAlmostEqual(
            prompt_similarity("fix the flaky test", "fix the broken test"), 0.6)

    def test_empty_is_zero(self):
        self.assertEqual(prompt_similarity("", "anything"), 0.0)


class WeekKeyTests(unittest.TestCase):
    def test_iso_week_format(self):
        dt = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)  # ISO 2026-W23
        self.assertEqual(week_key(dt), "2026-W23")

    def test_year_boundary_uses_iso_year(self):
        dt = datetime(2025, 12, 29, tzinfo=timezone.utc)  # ISO 2026-W01
        self.assertEqual(week_key(dt), "2026-W01")


BASE = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
INSTR = "Always reply in zh-TW and run the full pytest suite before you claim done"


def _prompt_row(sid, start, prompt, source=None, coverage=None):
    row = {"session_id": sid, "start_time": start.isoformat(),
           "first_prompt": prompt}
    if source:
        row["source"], row["coverage"] = source, coverage
    return row


class RepeatedInstructionTests(unittest.TestCase):
    def test_five_occurrences_three_weeks_passes_gate(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i % 3, days=i), INSTR)
                for i in range(5)]
        out = bs_repeated_instructions(rows, [])
        self.assertTrue(out["gate_passed"])
        p = out["metrics"]["patterns"][0]
        self.assertEqual(p["occurrences"], 5)
        self.assertGreaterEqual(p["weeks"], 3)
        self.assertEqual(p["est_wasted_tokens"], 4 * (len(INSTR) // 4))
        self.assertLessEqual(len(p["evidence"]), 3)

    def test_five_occurrences_two_weeks_fails_gate(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(days=i), INSTR)
                for i in range(5)]
        out = bs_repeated_instructions(rows, [])
        self.assertFalse(out["gate_passed"])
        self.assertIsNotNone(out["reason"])

    def test_cross_tool_occurrences_count(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i), INSTR)
                for i in range(3)]
        cross = [_prompt_row(f"x{i}", BASE + timedelta(weeks=i, hours=2), INSTR,
                             source="codex", coverage="full") for i in range(2)]
        out = bs_repeated_instructions(rows, cross)
        self.assertTrue(out["gate_passed"])
        self.assertIn("codex", out["metrics"]["patterns"][0]["sources"])

    def test_presence_only_rows_ignored(self):
        cross = [{"session_id": f"a{i}", "start_time": (BASE + timedelta(weeks=i)).isoformat(),
                  "first_prompt": None, "source": "antigravity",
                  "coverage": "presence_only"} for i in range(9)]
        out = bs_repeated_instructions([], cross)
        self.assertFalse(out["gate_passed"])

    def test_short_prompts_never_pattern(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i), "continue")
                for i in range(9)]
        out = bs_repeated_instructions(rows, [])
        self.assertFalse(out["gate_passed"])

    def test_normalization_merges_variants(self):
        rows = ([_prompt_row(f"c{i}", BASE + timedelta(weeks=i % 3, days=i),
                             INSTR) for i in range(3)]
                + [_prompt_row(f"d{i}", BASE + timedelta(weeks=i, days=2),
                               INSTR.upper() + "!!") for i in range(2)])
        out = bs_repeated_instructions(rows, [])
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["patterns"][0]["occurrences"], 5)


FAIL_PROMPT = "refactor the payment reconciliation pipeline to stream batches"
RETRY_PROMPT = "refactor the payment reconciliation pipeline to stream batches cleanly"


def _sess(sid, start, outcome, prompt=FAIL_PROMPT, accel=None, dur=120,
          tokens=50000):
    return {"sid": sid, "start": start.isoformat(), "outcome": outcome,
            "first_prompt": prompt, "token_accel": accel,
            "duration_min": dur, "total_tokens": tokens,
            "input_tokens": tokens - 5000, "output_tokens": 5000,
            "cache_create_tokens": 0, "cache_read_tokens": 0,
            "model_counts": {"claude-opus-4-6": 10}}


def _pair(i):
    failed = _sess(f"f{i}", BASE + timedelta(days=2 * i), "not_achieved",
                   accel=2.0)
    retry = _sess(f"r{i}", BASE + timedelta(days=2 * i + 1), "fully_achieved",
                  prompt=RETRY_PROMPT, accel=1.0, dur=30, tokens=8000)
    return [failed, retry]


class SunkCostTests(unittest.TestCase):
    def test_three_pairs_pass_gate(self):
        rated = [s for i in range(3) for s in _pair(i)]
        # guard needs a fully_achieved population without acceleration
        rated += [_sess(f"g{i}", BASE + timedelta(days=40 + i),
                        "fully_achieved", prompt=f"unrelated task {i} entirely",
                        accel=1.0) for i in range(6)]
        out = bs_sunk_cost(rated)
        self.assertTrue(out["gate_passed"])
        self.assertFalse(out["suppressed_by_guard"])
        self.assertEqual(out["n"], 3)
        self.assertEqual(out["metrics"]["pairs"][0]["failed_sid"], "f0")

    def test_two_pairs_fail_gate(self):
        rated = [s for i in range(2) for s in _pair(i)]
        out = bs_sunk_cost(rated)
        self.assertFalse(out["gate_passed"])

    def test_retry_must_be_later_and_fast(self):
        failed = _sess("f0", BASE + timedelta(days=5), "not_achieved", accel=2.0)
        early_retry = _sess("r0", BASE, "fully_achieved", prompt=RETRY_PROMPT,
                            dur=30)
        slow_retry = _sess("r1", BASE + timedelta(days=6), "fully_achieved",
                           prompt=RETRY_PROMPT, dur=110)
        out = bs_sunk_cost([failed, early_retry, slow_retry] * 3)
        self.assertEqual(out["n"], 0)

    def test_guard_trips_when_accel_common_in_success(self):
        rated = [s for i in range(3) for s in _pair(i)]
        # fully_achieved sessions accelerate just as much -> not a failure signal
        rated += [_sess(f"g{i}", BASE + timedelta(days=40 + i),
                        "fully_achieved", prompt=f"unrelated task {i} entirely",
                        accel=2.0) for i in range(6)]
        out = bs_sunk_cost(rated)
        self.assertTrue(out["suppressed_by_guard"])
        self.assertFalse(out["gate_passed"])


class GuardHelperTests(unittest.TestCase):
    def test_similar_rates_trip(self):
        self.assertTrue(counterexample_similar(0.5, 0.4))

    def test_distinct_rates_pass(self):
        self.assertFalse(counterexample_similar(0.6, 0.1))

    def test_zero_flagged_rate_trips(self):
        self.assertTrue(counterexample_similar(0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
