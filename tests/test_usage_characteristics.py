"""TDD for per-dimension patterns and the usage_characteristics block.
See docs/superpowers/specs/2026-04-19-usage-inspired-rubric-design.md."""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import aggregate  # noqa: E402


def _session(sid, **overrides):
    base = {
        "session_id": sid,
        "uses_task_agent": False,
        "outcome": "",
        "session_type": "",
        "friction_counts": {},
        "duration_min": 10,
        "hour": 14,
        "prompt_chars": 60,
        "tool_counts": {},
        "hit_output_limit": False,
        "start": "2026-04-19T10:00:00Z",
        "user_msgs": 5,
        "assistant_msgs": 5,
    }
    base.update(overrides)
    return base


class ScoreD1PatternTests(unittest.TestCase):
    def test_pattern_present_when_sample_size_sufficient(self):
        """≥5 task-agent sessions with mixed outcomes → pattern string
        compares TA good-rate to overall."""
        sessions = [_session(f"s{i}", uses_task_agent=(i < 6),
                             outcome="fully_achieved" if i % 2 == 0 else "partial")
                    for i in range(12)]
        rated = sessions  # all have outcome set
        result = aggregate.score_d1_delegation(sessions, rated)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("%", result["pattern"])
        self.assertIn("Task agent", result["pattern"])

    def test_pattern_none_when_sample_too_small(self):
        """<5 task-agent sessions → pattern is None (key still present)."""
        sessions = [_session(f"s{i}", uses_task_agent=(i < 2),
                             outcome="fully_achieved")
                    for i in range(8)]
        rated = sessions
        result = aggregate.score_d1_delegation(sessions, rated)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])


class ScoreD2PatternTests(unittest.TestCase):
    def test_pattern_contrasts_non_iterative_vs_iterative(self):
        """Mixed session_type values with >= 5 non-iterative rated →
        pattern contrasts good-outcome rates between the two groups."""
        sessions = [_session(f"s{i}",
                             session_type="iterative_refinement" if i < 5 else "fresh_work",
                             outcome="fully_achieved" if i % 2 else "failed",
                             friction_counts={"buggy_code": 1} if i < 3 else {})
                    for i in range(12)]
        rated = sessions
        result = aggregate.score_d2_rootcause(sessions, rated, facets_coverage=80)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("iterative_refinement", result["pattern"])

    def test_pattern_none_when_facets_coverage_insufficient(self):
        """Low facet coverage → score is None AND pattern is None (key still present)."""
        sessions = [_session(f"s{i}") for i in range(12)]
        rated = sessions
        result = aggregate.score_d2_rootcause(sessions, rated, facets_coverage=10)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])


if __name__ == "__main__":
    unittest.main()
