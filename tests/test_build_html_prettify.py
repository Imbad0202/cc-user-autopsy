"""TDD for prettify_model helper (Bug 1).

Rule:
- Strip 'claude-' prefix and any date suffix matching -\d{8}.
- Tokenize on '-': first token is family name, capitalize.
  Remaining tokens are version digits; join with '.' not '-'.
- Empty / None → empty string.
- Unknown models that don't follow the pattern: strip prefix/date, then
  title-case each token and join with spaces (safe fallback).
"""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import build_html  # noqa: E402


class PrettifyModelTests(unittest.TestCase):

    def test_full_form_opus(self):
        """claude-opus-4-7-20251101 → Opus 4.7"""
        self.assertEqual(build_html.prettify_model("claude-opus-4-7-20251101"), "Opus 4.7")

    def test_full_form_sonnet(self):
        """claude-sonnet-4-6-20251001 → Sonnet 4.6"""
        self.assertEqual(build_html.prettify_model("claude-sonnet-4-6-20251001"), "Sonnet 4.6")

    def test_full_form_haiku(self):
        """claude-haiku-4-5-20250929 → Haiku 4.5"""
        self.assertEqual(build_html.prettify_model("claude-haiku-4-5-20250929"), "Haiku 4.5")

    def test_no_prefix_already_stripped(self):
        """opus-4-7 (no claude- prefix) → Opus 4.7"""
        self.assertEqual(build_html.prettify_model("opus-4-7"), "Opus 4.7")

    def test_unknown_model_fallback(self):
        """unknown-model-x → title-cased tokens joined with spaces: 'Unknown Model X'"""
        result = build_html.prettify_model("unknown-model-x")
        # Must be non-empty and not crash
        self.assertTrue(len(result) > 0)
        # Must not have raw dashes (should be prettified in some way)
        self.assertNotIn("-", result)

    def test_empty_string_returns_empty(self):
        """Empty string → empty string."""
        self.assertEqual(build_html.prettify_model(""), "")

    def test_none_returns_empty(self):
        """None → empty string."""
        self.assertEqual(build_html.prettify_model(None), "")

    def test_date_suffix_stripped_generically(self):
        """Any 8-digit date suffix should be stripped (not just the 3 hardcoded ones)."""
        self.assertEqual(build_html.prettify_model("claude-opus-4-7-20261231"), "Opus 4.7")

    def test_single_token_family_only(self):
        """claude-opus → just 'Opus' (no version tokens)."""
        self.assertEqual(build_html.prettify_model("claude-opus"), "Opus")

    def test_activity_panel_uses_prettify(self):
        """_build_activity_panel must use prettified label (e.g. 'Opus 4.7') not raw short."""
        html = build_html._build_activity_panel({
            "total_sessions": 5,
            "total_messages": 50,
            "active_days": 3,
            "current_streak": 1,
            "longest_streak": 2,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "models": {},
            "favorite_model": "claude-opus-4-7-20251101",
            "api_equivalent_cost_usd": 0.0,
        })
        self.assertIn("Opus 4.7", html)
        self.assertNotIn("opus-4-7", html)

    def test_models_chart_uses_prettify(self):
        """_build_models_chart must use prettified labels."""
        html = build_html._build_models_chart(
            {"claude-sonnet-4-6-20251001": 80, "claude-haiku-4-5-20250929": 20}
        )
        self.assertIn("Sonnet 4.6", html)
        self.assertIn("Haiku 4.5", html)
        # Raw short forms must not appear
        self.assertNotIn("sonnet-4-6", html)
        self.assertNotIn("haiku-4-5", html)


if __name__ == "__main__":
    unittest.main()
