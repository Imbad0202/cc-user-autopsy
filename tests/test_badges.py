"""compute_badges(): threshold-based badge layer (spec §4, bars v1.1).

Every badge: one earn case, one miss case, one below-sample case.
Fixture dicts mirror the exact metric field names the D-scorers emit.
"""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from aggregate import compute_badges  # noqa: E402


def _scores(**over):
    base = {
        "D1_delegation": {"score": 8, "metric_ta_rate_pct": 45.0,
                          "metric_good_rate_with_ta_pct": 75.0},
        "D2_root_cause": {"score": 9, "metric_iter_buggy_pct": 3.0},
        "D6_tool_breadth": {"score": 8, "metric_mcp_rate_pct": 20.0,
                            "metric_top3_share_pct": 50.0},
        "D9_token_efficiency": {"score": 8, "metric_ratio": 1.0,
                                "metric_cache_hit_pct": 90.0},
    }
    base.update(over)
    return base


def _ledger(days=28, commits=40, with_commits=12):
    return {"window": {"start": "2026-06-01", "end": "2026-06-29", "days": days},
            "output": {"git_commits": commits, "git_pushes": 10,
                       "sessions_with_commits": with_commits}}


def _cross(full_sources=("claude", "codex"), win_days=28, degraded=False,
           multi_hours=15):
    return {
        "sources": [{"source": s, "coverage": "full", "detected": True}
                    for s in full_sources] +
                   [{"source": "grok", "coverage": "partial", "detected": True}],
        "common_window": {"start": "2026-06-01", "end": "2026-06-29",
                          "days": win_days, "degraded": degraded},
        "parallel": {"hours_multi_source": multi_hours,
                     "hours_single_source": 100},
    }


def _sessions(n):
    return [{"uses_task_agent": i % 2 == 0, "outcome": "fully_achieved"}
            for i in range(n)]


class BadgeShapeTests(unittest.TestCase):
    def test_six_items_fixed_order_and_shape(self):
        out = compute_badges(_scores(), _ledger(), _cross(),
                             _sessions(60), _sessions(40))
        self.assertEqual(out["schema_version"], 1)
        self.assertEqual(out["standard_version"], "v1.1")
        self.assertEqual(
            [b["id"] for b in out["items"]],
            ["delegation", "root_cause", "tool_breadth", "token_efficiency",
             "shipping_cadence", "cross_tool_orchestration"])
        for b in out["items"]:
            self.assertIn("earned", b)
            self.assertIn("n", b)
            self.assertIn("metrics", b)
            self.assertIn("thresholds", b)

    def test_all_earned_on_strong_fixture(self):
        out = compute_badges(_scores(), _ledger(), _cross(),
                             _sessions(60), _sessions(40))
        self.assertTrue(all(b["earned"] for b in out["items"]))


def _delegation_pools(total, ta, ta_good, ta_bad, non_ta_rated=10):
    """Session/rated pools with exact delegation rates encoded: `ta`/`total`
    Task-agent adoption in sessions; a rated pool whose Task-agent rows
    split `ta_good` good / `ta_bad` not-good. The earned gate recomputes
    raw rates from these pools (not from the rounded D1 display metrics),
    so boundary cases must be expressed here."""
    sessions = [{"uses_task_agent": i < ta, "outcome": "fully_achieved"}
                for i in range(total)]
    rated = ([{"uses_task_agent": True, "outcome": "fully_achieved"}] * ta_good
             + [{"uses_task_agent": True, "outcome": "not_achieved"}] * ta_bad
             + [{"uses_task_agent": False, "outcome": "fully_achieved"}]
             * non_ta_rated)
    return sessions, rated


class DelegationBadgeTests(unittest.TestCase):
    def test_miss_when_adoption_below_bar(self):
        # 20/60 = 33.3% adoption cleared the v1 bar (30) but not v1.1 (45).
        sessions, rated = _delegation_pools(60, 20, ta_good=20, ta_bad=0)
        sc = _scores(D1_delegation={"score": 7, "metric_ta_rate_pct": 33.3,
                                    "metric_good_rate_with_ta_pct": 100.0})
        out = compute_badges(sc, _ledger(), _cross(), sessions, rated)
        self.assertFalse(out["items"][0]["earned"])

    def test_rounding_does_not_award_below_raw_bar(self):
        # 58/129 = 44.961% raw adoption; D1's display metric rounds it to
        # 45.0, which would wrongly clear the >=45 bar if the ROUNDED
        # value were gated on instead of the raw rate.
        sessions, rated = _delegation_pools(129, 58, ta_good=20, ta_bad=0)
        sc = _scores(D1_delegation={"score": 7, "metric_ta_rate_pct": 45.0,
                                    "metric_good_rate_with_ta_pct": 100.0})
        out = compute_badges(sc, _ledger(), _cross(), sessions, rated)
        self.assertFalse(out["items"][0]["earned"])

    def test_miss_when_good_rate_below_bar(self):
        # 12/20 = 60% good rate on Task-agent rated sessions, below 65.
        sessions, rated = _delegation_pools(60, 30, ta_good=12, ta_bad=8)
        sc = _scores(D1_delegation={"score": 7, "metric_ta_rate_pct": 50.0,
                                    "metric_good_rate_with_ta_pct": 60.0})
        out = compute_badges(sc, _ledger(), _cross(), sessions, rated)
        self.assertFalse(out["items"][0]["earned"])

    def test_earned_at_recalibrated_bars(self):
        # Exactly on both v1.1 bars: 27/60 = 45.0% adoption, 13/20 = 65.0%
        # good rate. The good rate would MISS the old v1 bar (70), so this
        # pins the lowered threshold; the assertions on the emitted
        # thresholds pin the published constants themselves.
        sessions, rated = _delegation_pools(60, 27, ta_good=13, ta_bad=7)
        sc = _scores(D1_delegation={"score": 8, "metric_ta_rate_pct": 45.0,
                                    "metric_good_rate_with_ta_pct": 65.0})
        out = compute_badges(sc, _ledger(), _cross(), sessions, rated)
        b = out["items"][0]
        self.assertTrue(b["earned"])
        self.assertEqual(b["thresholds"]["ta_rate_pct"], 45.0)
        self.assertEqual(b["thresholds"]["good_rate_with_ta_pct"], 65.0)
        self.assertEqual(b["thresholds"]["min_ta_rated"], 15)

    def test_below_sample_not_earned_with_reason(self):
        # only 10 rated TA sessions < 15 floor
        rated = [{"uses_task_agent": i < 10, "outcome": "fully_achieved"}
                 for i in range(40)]
        out = compute_badges(_scores(), _ledger(), _cross(), _sessions(60), rated)
        b = out["items"][0]
        self.assertFalse(b["earned"])
        self.assertEqual(b["n"], 10)
        self.assertIn("reason", b)


class RootCauseBadgeTests(unittest.TestCase):
    def test_miss_when_iter_buggy_above_bar(self):
        sc = _scores(D2_root_cause={"score": 7, "metric_iter_buggy_pct": 9.0})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        self.assertFalse(out["items"][1]["earned"])

    def test_unscored_d2_not_earned(self):
        sc = _scores(D2_root_cause={"score": None,
                                    "reason": "insufficient facet coverage"})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        b = out["items"][1]
        self.assertFalse(b["earned"])
        self.assertIn("reason", b)

    def test_below_sample(self):
        out = compute_badges(_scores(), _ledger(), _cross(),
                             _sessions(60), _sessions(20))
        self.assertFalse(out["items"][1]["earned"])


class ToolBreadthBadgeTests(unittest.TestCase):
    def test_miss_when_top3_share_too_high(self):
        sc = _scores(D6_tool_breadth={"score": 7, "metric_mcp_rate_pct": 20.0,
                                      "metric_top3_share_pct": 70.0})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        self.assertFalse(out["items"][2]["earned"])

    def test_below_sample(self):
        out = compute_badges(_scores(), _ledger(), _cross(),
                             _sessions(20), _sessions(40))
        self.assertFalse(out["items"][2]["earned"])


class TokenEfficiencyBadgeTests(unittest.TestCase):
    def test_miss_when_cache_below_bar(self):
        sc = _scores(D9_token_efficiency={"score": 6, "metric_ratio": 1.0,
                                          "metric_cache_hit_pct": 50.0})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        self.assertFalse(out["items"][3]["earned"])

    def test_none_cache_not_earned(self):
        sc = _scores(D9_token_efficiency={"score": 8, "metric_ratio": 1.0,
                                          "metric_cache_hit_pct": None})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        self.assertFalse(out["items"][3]["earned"])


class ShippingCadenceBadgeTests(unittest.TestCase):
    def test_miss_when_commits_per_week_below_bar(self):
        out = compute_badges(_scores(), _ledger(commits=10), _cross(),
                             _sessions(60), _sessions(40))
        self.assertFalse(out["items"][4]["earned"])

    def test_window_too_short_not_earned(self):
        out = compute_badges(_scores(), _ledger(days=7), _cross(),
                             _sessions(60), _sessions(40))
        b = out["items"][4]
        self.assertFalse(b["earned"])
        self.assertIn("reason", b)

    def test_metrics_carry_commits_per_week(self):
        out = compute_badges(_scores(), _ledger(days=28, commits=40), _cross(),
                             _sessions(60), _sessions(40))
        self.assertAlmostEqual(out["items"][4]["metrics"]["commits_per_week"],
                               10.0, places=1)

    def test_rounding_does_not_award_below_raw_bar(self):
        # 71 commits / (100/7 weeks) = 4.9699.. -> rounds to 5.0, which
        # would wrongly clear a >=5.0 bar if the ROUNDED value were
        # compared instead of the raw rate. sessions_with_commits=12 clears
        # the >=10 floor so this exercises only the rate comparison.
        out = compute_badges(_scores(), _ledger(days=100, commits=71,
                                                 with_commits=12),
                             _cross(), _sessions(60), _sessions(40))
        b = out["items"][4]
        self.assertEqual(b["metrics"]["commits_per_week"], 5.0)
        self.assertFalse(b["earned"])

    def test_earned_when_raw_rate_clears_bar(self):
        # 72 commits / (100/7 weeks) = 5.04 -> clears >=5.0 on the raw rate.
        out = compute_badges(_scores(), _ledger(days=100, commits=72,
                                                 with_commits=12),
                             _cross(), _sessions(60), _sessions(40))
        b = out["items"][4]
        self.assertTrue(b["earned"])


class OrchestrationBadgeTests(unittest.TestCase):
    def test_miss_with_one_full_source(self):
        out = compute_badges(_scores(), _ledger(), _cross(full_sources=("claude",)),
                             _sessions(60), _sessions(40))
        b = out["items"][5]
        self.assertFalse(b["earned"])
        self.assertIn("reason", b)

    def test_miss_when_window_degraded(self):
        out = compute_badges(_scores(), _ledger(), _cross(degraded=True),
                             _sessions(60), _sessions(40))
        self.assertFalse(out["items"][5]["earned"])

    def test_miss_when_hours_below_bar(self):
        out = compute_badges(_scores(), _ledger(), _cross(multi_hours=4),
                             _sessions(60), _sessions(40))
        self.assertFalse(out["items"][5]["earned"])

    def test_no_common_window_not_earned(self):
        cross = _cross()
        cross["common_window"] = None
        out = compute_badges(_scores(), _ledger(), cross,
                             _sessions(60), _sessions(40))
        self.assertFalse(out["items"][5]["earned"])


class RubricSyncTests(unittest.TestCase):
    """Cheap table-integrity check in the spirit of test_cost_estimate:
    every badge id must appear in the rubric's Badges section."""
    def test_rubric_mentions_every_badge_id(self):
        rubric = (SKILL_DIR / "references" / "scoring-rubric.md").read_text()
        self.assertIn("## Badges", rubric)
        for bid in ("delegation", "root_cause", "tool_breadth",
                    "token_efficiency", "shipping_cadence",
                    "cross_tool_orchestration"):
            self.assertIn(f"`{bid}`", rubric)


if __name__ == "__main__":
    unittest.main()
