"""TDD for the API-equivalent cost estimate in aggregate.py.

Context: Claude Code users on Max Plan pay a flat monthly rate regardless of
actual usage. The autopsy report adds a cost line showing what the same token
volume would cost on pay-per-use API pricing — purely informational, to give
readers a sense of scale. Pricing is pinned in a module-level PRICING dict
(with a dated comment) so users can update it when Anthropic's public rates
change.
"""
import sys
import unittest
from collections import Counter
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import aggregate  # noqa: E402


class PricingTableTests(unittest.TestCase):
    def test_pricing_table_has_current_models(self):
        """PRICING must cover every Claude model a Claude Code user could
        plausibly invoke in 2026. Missing entries silently drop cost."""
        expected = {
            "claude-opus-4-7", "claude-opus-4-6", "claude-opus-4-5",
            "claude-sonnet-4-6", "claude-sonnet-4-5",
            "claude-haiku-4-5",
        }
        self.assertTrue(expected.issubset(set(aggregate.PRICING.keys())),
                        f"missing models: {expected - set(aggregate.PRICING.keys())}")

    def test_pricing_entries_have_all_token_types(self):
        """Each entry must price input, output, cache_write, cache_read. Any
        missing key would fall through to 0 and silently undercount cost."""
        required = {"input", "output", "cache_write", "cache_read"}
        for model, p in aggregate.PRICING.items():
            self.assertTrue(required.issubset(set(p.keys())),
                            f"{model} missing keys: {required - set(p.keys())}")


class CostCalcTests(unittest.TestCase):
    def test_cost_matches_hand_calc_single_model(self):
        """compute_api_equivalent_cost with a single-model row must equal
        the hand-calculated cost: in*rate_in + out*rate_out + cc*rate_cw
        + cr*rate_cr, all in $/1M tokens."""
        sessions = [{
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cache_create_tokens": 1_000_000,
            "cache_read_tokens": 1_000_000,
            "model_counts": {"claude-opus-4-6": 1},
        }]
        cost = aggregate.compute_api_equivalent_cost(sessions)
        # All models share pricing within opus-4-6:
        p = aggregate.PRICING["claude-opus-4-6"]
        expected = p["input"] + p["output"] + p["cache_write"] + p["cache_read"]
        self.assertAlmostEqual(cost, expected, places=2)

    def test_cost_uses_model_weighted_mix(self):
        """When multiple models appear in model_counts across sessions, the
        implied billing-model mix is the assistant-message share of each
        model. Opus+haiku 50/50 should produce the mean of their rates."""
        # Two sessions, one opus-4-6 asst msg and one haiku-4-5 asst msg,
        # each contributing 1M input tokens. Total 2M input.
        # Rate = 0.5 * opus.input + 0.5 * haiku.input
        sessions = [
            {"input_tokens": 1_000_000, "output_tokens": 0,
             "cache_create_tokens": 0, "cache_read_tokens": 0,
             "model_counts": {"claude-opus-4-6": 1}},
            {"input_tokens": 1_000_000, "output_tokens": 0,
             "cache_create_tokens": 0, "cache_read_tokens": 0,
             "model_counts": {"claude-haiku-4-5": 1}},
        ]
        cost = aggregate.compute_api_equivalent_cost(sessions)
        blended = (aggregate.PRICING["claude-opus-4-6"]["input"] +
                   aggregate.PRICING["claude-haiku-4-5"]["input"]) / 2
        expected = 2 * blended  # 2M tokens
        self.assertAlmostEqual(cost, expected, places=2)

    def test_cost_is_zero_for_empty_sessions(self):
        self.assertEqual(aggregate.compute_api_equivalent_cost([]), 0.0)

    def test_cost_is_zero_when_no_tokens(self):
        sessions = [{
            "input_tokens": 0, "output_tokens": 0,
            "cache_create_tokens": 0, "cache_read_tokens": 0,
            "model_counts": {"claude-opus-4-6": 1},
        }]
        self.assertEqual(aggregate.compute_api_equivalent_cost(sessions), 0.0)

    def test_unknown_model_falls_back_to_opus(self):
        """If a session's model_counts contains a model not in PRICING (eg a
        new Opus variant we haven't updated), the cost must still be
        non-zero — fall back to the Opus pricing (conservative upper bound
        since Opus is the most expensive tier). Otherwise cost silently
        drops to 0 for that session, which is worse than over-reporting."""
        sessions = [{
            "input_tokens": 1_000_000,
            "output_tokens": 0,
            "cache_create_tokens": 0, "cache_read_tokens": 0,
            "model_counts": {"claude-unheard-of-9-9": 1},
        }]
        cost = aggregate.compute_api_equivalent_cost(sessions)
        # Should be close to the Opus input rate (conservative fallback).
        self.assertGreater(cost, 0)
        self.assertAlmostEqual(cost, aggregate.PRICING["claude-opus-4-6"]["input"],
                               places=2)


class ActivityPanelCostTests(unittest.TestCase):
    def test_compute_activity_includes_cost_field(self):
        """compute_activity must expose api_equivalent_cost_usd so the HTML
        builder can render it."""
        sessions = [{
            "start": "2026-04-18T00:00:00Z",
            "input_tokens": 1_000_000, "output_tokens": 1_000_000,
            "cache_create_tokens": 1_000_000, "cache_read_tokens": 1_000_000,
            "user_msgs": 1, "assistant_msgs": 1,
            "model_counts": {"claude-opus-4-6": 1},
        }]
        result = aggregate.compute_activity(sessions)
        self.assertIn("api_equivalent_cost_usd", result)
        self.assertGreater(result["api_equivalent_cost_usd"], 0)


if __name__ == "__main__":
    unittest.main()
