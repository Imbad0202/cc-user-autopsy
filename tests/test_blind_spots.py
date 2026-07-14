import unittest
from datetime import datetime, timezone

from scripts.aggregate import normalize_prompt, prompt_similarity, week_key


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


if __name__ == "__main__":
    unittest.main()
