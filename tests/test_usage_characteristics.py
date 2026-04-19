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
        """Mixed session_type values, both groups >= 5 (after floor raise) →
        pattern contrasts good-outcome rates between the two groups.
        Non-iterative floor must also be >= _PATTERN_MIN_SAMPLE."""
        # 6 iterative + 6 non-iterative, alternating outcomes → 50% good rate each
        sessions = [_session(f"s{i}",
                             session_type="iterative_refinement" if i < 6 else "fresh_work",
                             outcome="fully_achieved" if i % 2 else "failed")
                    for i in range(12)]
        rated = sessions
        result = aggregate.score_d2_rootcause(sessions, rated, facets_coverage=80)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        # Both groups should produce 50% good-outcome rate under alternating outcomes
        self.assertIn("50%", result["pattern"])
        self.assertIn("iterative_refinement", result["pattern"])
        # Confirm the sentence structure: "without ... X% ... versus Y% for iterative"
        self.assertIn("without iterative_refinement", result["pattern"])
        self.assertIn("versus", result["pattern"])

    def test_pattern_none_when_iterative_group_too_small(self):
        """Iterative sub-group < _PATTERN_MIN_SAMPLE → pattern is None even
        if non-iterative group is large. Symmetric floor prevents noise."""
        sessions = [_session(f"s{i}",
                             session_type="iterative_refinement" if i < 3 else "fresh_work",
                             outcome="fully_achieved" if i % 2 else "failed")
                    for i in range(12)]
        rated = sessions
        result = aggregate.score_d2_rootcause(sessions, rated, facets_coverage=80)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])

    def test_pattern_none_when_facets_coverage_insufficient(self):
        """Low facet coverage → score is None AND pattern is None (key still present)."""
        sessions = [_session(f"s{i}") for i in range(12)]
        rated = sessions
        result = aggregate.score_d2_rootcause(sessions, rated, facets_coverage=10)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])


class ScoreD3PatternTests(unittest.TestCase):
    def _d3_session(self, sid, first_prompt_len, total_tokens, git_commits):
        """Minimal session dict for score_d3_prompt_quality."""
        return {
            "session_id": sid,
            "first_prompt_len": first_prompt_len,
            "total_tokens": total_tokens,
            "git_commits": git_commits,
        }

    def test_pattern_contrasts_prompt_length_buckets(self):
        """6 long-prompt + 6 short-prompt sessions with git_commits > 0 →
        pattern string contrasts avg tokens/commit between the two groups.
        long: 6 sessions each 2000 tokens / 2 commits = 1000 t/commit avg
        short: 6 sessions each 600 tokens / 2 commits = 300 t/commit avg."""
        sessions = (
            [self._d3_session(f"L{i}", first_prompt_len=150, total_tokens=2000, git_commits=2)
             for i in range(6)]
            + [self._d3_session(f"S{i}", first_prompt_len=30, total_tokens=600, git_commits=2)
               for i in range(6)]
        )
        result = aggregate.score_d3_prompt_quality(sessions)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("≥100 chars", result["pattern"])
        self.assertIn("≤50", result["pattern"])
        # avg_long = 2000/2 = 1000, avg_short = 600/2 = 300
        self.assertIn("1000", result["pattern"])
        self.assertIn("300", result["pattern"])

    def test_pattern_none_when_long_group_too_small(self):
        """Fewer than _PATTERN_MIN_SAMPLE long-prompt sessions → pattern is None."""
        sessions = (
            # only 4 long-prompt sessions (below floor)
            [self._d3_session(f"L{i}", first_prompt_len=150, total_tokens=2000, git_commits=2)
             for i in range(4)]
            # 6 short-prompt sessions (above floor)
            + [self._d3_session(f"S{i}", first_prompt_len=30, total_tokens=600, git_commits=2)
               for i in range(6)]
        )
        result = aggregate.score_d3_prompt_quality(sessions)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])

    def test_pattern_none_when_short_group_too_small(self):
        """Fewer than _PATTERN_MIN_SAMPLE short-prompt sessions → pattern is None.
        Symmetric floor: long group being large doesn't compensate."""
        sessions = (
            # 6 long-prompt sessions (above floor)
            [self._d3_session(f"L{i}", first_prompt_len=150, total_tokens=2000, git_commits=2)
             for i in range(6)]
            # only 4 short-prompt sessions (below floor)
            + [self._d3_session(f"S{i}", first_prompt_len=30, total_tokens=600, git_commits=2)
               for i in range(4)]
        )
        result = aggregate.score_d3_prompt_quality(sessions)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])

    def test_pattern_key_present_when_no_sessions(self):
        """Empty input: early-return path must still carry 'pattern' key = None."""
        result = aggregate.score_d3_prompt_quality([])
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])


class ScoreD4PatternTests(unittest.TestCase):
    def _d4_session(self, sid, duration_min=10, git_commits=1,
                    friction_counts=None, interrupts=0, project_key="proj-a"):
        """Minimal session dict for score_d4_context_mgmt.

        score_d4 accesses friction_counts, duration_min, interrupts,
        project_key, and git_commits without .get() — all must be present.
        The "hit output limit" signal is read from friction_counts (same source
        as the score and explanation), not from the top-level hit_output_limit
        field populated by a different scanner code path.
        """
        return _session(
            sid,
            duration_min=duration_min,
            git_commits=git_commits,
            interrupts=interrupts,
            project_key=project_key,
            friction_counts=friction_counts if friction_counts is not None else {},
        )

    def test_pattern_contrasts_long_no_commit_vs_other(self):
        """6 long-no-commit (>20min, 0 commits) + 6 other sessions.
        3 of the long-no-commit sessions hit output limit → 50%.
        1 of the other sessions hits output limit → ~17%.
        Pattern must contain '50%' AND '17%'.

        The "hit output limit" signal must come from friction_counts
        (key 'output_token_limit_exceeded'), the same source used by the
        score and explanation — not from hit_output_limit, which is a
        separate scanner field that can diverge.
        """
        long_no_commit = [
            self._d4_session(
                f"lnc{i}", duration_min=25, git_commits=0,
                friction_counts={"output_token_limit_exceeded": 1} if i < 3 else {},
            )
            for i in range(6)
        ]
        other = [
            self._d4_session(
                f"oth{i}", duration_min=10, git_commits=2,
                friction_counts={"output_token_limit_exceeded": 1} if i == 0 else {},
            )
            for i in range(6)
        ]
        sessions = long_no_commit + other
        result = aggregate.score_d4_context_mgmt(sessions)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("50%", result["pattern"])
        self.assertIn("17%", result["pattern"])

    def test_pattern_none_when_long_no_commit_group_too_small(self):
        """Fewer than _PATTERN_MIN_SAMPLE long-no-commit sessions → pattern None."""
        long_no_commit = [
            self._d4_session(f"lnc{i}", duration_min=25, git_commits=0)
            for i in range(4)   # only 4 — below floor
        ]
        other = [
            self._d4_session(f"oth{i}", duration_min=10, git_commits=2)
            for i in range(6)
        ]
        result = aggregate.score_d4_context_mgmt(long_no_commit + other)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])

    def test_pattern_none_when_other_group_too_small(self):
        """Fewer than _PATTERN_MIN_SAMPLE 'other' sessions → pattern None.
        Symmetric floor: large long-no-commit group doesn't compensate.
        """
        long_no_commit = [
            self._d4_session(f"lnc{i}", duration_min=25, git_commits=0)
            for i in range(6)
        ]
        other = [
            self._d4_session(f"oth{i}", duration_min=10, git_commits=2)
            for i in range(4)   # only 4 — below floor
        ]
        result = aggregate.score_d4_context_mgmt(long_no_commit + other)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])

    def test_pattern_key_present_when_no_sessions(self):
        """Empty input: early-return path must still carry 'pattern' key = None."""
        result = aggregate.score_d4_context_mgmt([])
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])


class ScoreD5PatternTests(unittest.TestCase):
    def _d5_session(self, sid, interrupts=0, outcome=""):
        """Minimal session dict for score_d5_interrupt.

        score_d5_interrupt accesses s["interrupts"] and s["outcome"] without
        .get(), so both keys must be present. The base _session() does not
        include 'interrupts', so we set it explicitly here.
        """
        return _session(sid, interrupts=interrupts, outcome=outcome)

    def test_pattern_contrasts_interrupted_vs_non(self):
        """6 interrupted (3 good → 50%) + 6 non-interrupted (5 good → 83%).
        Pattern must contain '50%' AND '83%'.
        """
        interrupted = [
            self._d5_session(f"intr{i}", interrupts=1,
                             outcome="fully_achieved" if i % 2 == 0 else "partial")
            for i in range(6)
        ]
        non_interrupted = [
            self._d5_session(f"non{i}", interrupts=0,
                             outcome="fully_achieved" if i < 5 else "failed")
            for i in range(6)
        ]
        rated = interrupted + non_interrupted
        result = aggregate.score_d5_interrupt(rated)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("50%", result["pattern"])
        self.assertIn("83%", result["pattern"])

    def test_pattern_none_when_interrupted_group_too_small(self):
        """3 interrupted + 9 non-interrupted → early return fires (< 5 interrupted).
        Early-return dict must still carry 'pattern' key = None.
        """
        interrupted = [
            self._d5_session(f"intr{i}", interrupts=1, outcome="fully_achieved")
            for i in range(3)
        ]
        non_interrupted = [
            self._d5_session(f"non{i}", interrupts=0, outcome="fully_achieved")
            for i in range(9)
        ]
        rated = interrupted + non_interrupted
        result = aggregate.score_d5_interrupt(rated)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])
        self.assertIsNone(result["score"])

    def test_pattern_none_when_non_interrupted_group_too_small(self):
        """9 interrupted + 3 non-interrupted → score is set, but symmetric floor
        on non-interrupted group means pattern is None.
        """
        interrupted = [
            self._d5_session(f"intr{i}", interrupts=1, outcome="fully_achieved")
            for i in range(9)
        ]
        non_interrupted = [
            self._d5_session(f"non{i}", interrupts=0, outcome="fully_achieved")
            for i in range(3)
        ]
        rated = interrupted + non_interrupted
        result = aggregate.score_d5_interrupt(rated)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])
        self.assertIsNotNone(result["score"])


class ScoreD6PatternTests(unittest.TestCase):
    def _d6_session(self, sid, tool_counts=None, outcome="", uses_mcp=False):
        """Minimal session dict for score_d6_tool_breadth.

        score_d6_tool_breadth accesses s["uses_mcp"] and s["tool_counts"]
        without .get(), so both keys must be present. The base _session()
        does not include 'uses_mcp', so we set it explicitly here.
        """
        return _session(
            sid,
            tool_counts=tool_counts if tool_counts is not None else {},
            outcome=outcome,
            uses_mcp=uses_mcp,
        )

    def test_pattern_contrasts_diverse_vs_narrow(self):
        """6 diverse sessions (≥4 distinct tools, 3 good → 50%) +
        6 narrow sessions (1-2 distinct tools, 5 good → ~83%).
        Pattern must contain '50%' AND '83%' AND '≥4' AND '1–2' (EN-DASH).
        """
        diverse_tools = {"Bash": 5, "Read": 3, "Edit": 2, "Grep": 1}  # 4 distinct tools
        narrow_tools = {"Bash": 5, "Read": 3}  # 2 distinct tools

        diverse = [
            self._d6_session(
                f"div{i}",
                tool_counts=diverse_tools,
                outcome="fully_achieved" if i < 3 else "failed",
            )
            for i in range(6)
        ]
        narrow = [
            self._d6_session(
                f"nar{i}",
                tool_counts=narrow_tools,
                outcome="fully_achieved" if i < 5 else "failed",
            )
            for i in range(6)
        ]
        result = aggregate.score_d6_tool_breadth(diverse + narrow)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("50%", result["pattern"])
        self.assertIn("83%", result["pattern"])
        self.assertIn("≥4", result["pattern"])
        self.assertIn("1\u20132", result["pattern"])  # EN-DASH U+2013

    def test_pattern_none_when_diverse_group_too_small(self):
        """Fewer than _PATTERN_MIN_SAMPLE diverse sessions → pattern is None."""
        diverse_tools = {"Bash": 5, "Read": 3, "Edit": 2, "Grep": 1}
        narrow_tools = {"Bash": 5, "Read": 3}

        diverse = [
            self._d6_session(f"div{i}", tool_counts=diverse_tools, outcome="fully_achieved")
            for i in range(4)  # only 4 — below floor
        ]
        narrow = [
            self._d6_session(f"nar{i}", tool_counts=narrow_tools, outcome="fully_achieved")
            for i in range(6)
        ]
        result = aggregate.score_d6_tool_breadth(diverse + narrow)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])

    def test_pattern_none_when_narrow_group_too_small(self):
        """Fewer than _PATTERN_MIN_SAMPLE narrow sessions → pattern is None.
        Symmetric floor: large diverse group doesn't compensate.
        """
        diverse_tools = {"Bash": 5, "Read": 3, "Edit": 2, "Grep": 1}
        narrow_tools = {"Bash": 5, "Read": 3}

        diverse = [
            self._d6_session(f"div{i}", tool_counts=diverse_tools, outcome="fully_achieved")
            for i in range(6)
        ]
        narrow = [
            self._d6_session(f"nar{i}", tool_counts=narrow_tools, outcome="fully_achieved")
            for i in range(4)  # only 4 — below floor
        ]
        result = aggregate.score_d6_tool_breadth(diverse + narrow)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])

    def test_pattern_key_present_when_no_sessions(self):
        """Empty input: early return must carry 'pattern' key = None."""
        result = aggregate.score_d6_tool_breadth([])
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])

    def test_pattern_excludes_unrated_sessions(self):
        """Unrated sessions (outcome == '') must not bias the diversity rates.
        Proves the fix: 6 rated diverse (3 good → 50%) + 4 unrated diverse (would drag
        rate to 30% if included) + 6 rated narrow (5 good → 83%). Pattern should show
        50%/83%, not 30%/83%."""
        sessions = []
        # 6 rated diverse: 3 good, 3 failed
        for i in range(6):
            sessions.append(self._d6_session(f"rd{i}",
                                             tool_counts={"Bash": 2, "Read": 2, "Edit": 2, "Grep": 2},
                                             outcome="fully_achieved" if i < 3 else "failed"))
        # 4 unrated diverse (would skew if included) — outcome=""
        for i in range(4):
            sessions.append(self._d6_session(f"ud{i}",
                                             tool_counts={"Bash": 2, "Read": 2, "Edit": 2, "Grep": 2},
                                             outcome=""))
        # 6 rated narrow: 5 good, 1 failed
        for i in range(6):
            sessions.append(self._d6_session(f"rn{i}",
                                             tool_counts={"Bash": 3, "Read": 2},
                                             outcome="fully_achieved" if i < 5 else "failed"))
        result = aggregate.score_d6_tool_breadth(sessions)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("50%", result["pattern"])
        self.assertIn("83%", result["pattern"])
        # If the bug were present, diverse_good would be 30% (3/10), not 50% (3/6)
        self.assertNotIn("30%", result["pattern"])


class ScoreD7PatternTests(unittest.TestCase):
    def _d7_session(self, sid, goal_cats=None, friction_counts=None):
        """Minimal session dict for score_d7_writing.

        score_d7_writing accesses s.get("goal_cats", {}) and
        s["friction_counts"].get("misunderstood_request", 0).
        The base _session() provides friction_counts={}, but not goal_cats,
        so we set both explicitly here.
        """
        return _session(
            sid,
            goal_cats=goal_cats if goal_cats is not None else {},
            friction_counts=friction_counts if friction_counts is not None else {},
        )

    def test_pattern_contrasts_writing_vs_non_writing(self):
        """6 writing sessions (avg 2.0 misunderstood_request) +
        6 non-writing sessions (avg 1.0 misunderstood_request) →
        pattern mentions '2.0', '1.0', and 'Writing'.
        """
        writing = [
            self._d7_session(f"w{i}",
                             goal_cats={"writing": 1},
                             friction_counts={"misunderstood_request": 2})
            for i in range(6)
        ]
        non_writing = [
            self._d7_session(f"nw{i}",
                             goal_cats={"code_development": 1},
                             friction_counts={"misunderstood_request": 1})
            for i in range(6)
        ]
        rated = writing + non_writing
        result = aggregate.score_d7_writing(rated)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("2.0", result["pattern"])
        self.assertIn("1.0", result["pattern"])
        self.assertIn("Writing", result["pattern"])

    def test_pattern_none_when_writing_group_too_small(self):
        """<5 writing sessions → early return fires (score is None), pattern key present = None."""
        writing = [
            self._d7_session(f"w{i}", goal_cats={"writing": 1},
                             friction_counts={"misunderstood_request": 2})
            for i in range(4)
        ]
        non_writing = [
            self._d7_session(f"nw{i}", goal_cats={"code_development": 1},
                             friction_counts={"misunderstood_request": 1})
            for i in range(6)
        ]
        result = aggregate.score_d7_writing(writing + non_writing)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])
        self.assertIsNone(result["score"])

    def test_pattern_none_when_non_writing_group_too_small(self):
        """≥5 writing + <5 non-writing → score is set, but symmetric floor means pattern is None."""
        writing = [
            self._d7_session(f"w{i}", goal_cats={"writing": 1},
                             friction_counts={"misunderstood_request": 2})
            for i in range(6)
        ]
        non_writing = [
            self._d7_session(f"nw{i}", goal_cats={"code_development": 1},
                             friction_counts={"misunderstood_request": 1})
            for i in range(4)
        ]
        result = aggregate.score_d7_writing(writing + non_writing)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])
        self.assertIsNotNone(result["score"])


class ScoreD8PatternTests(unittest.TestCase):
    """TDD for the morning-vs-after-10am pattern in score_d8_time_mgmt.

    score_d8_time_mgmt(sessions, rated) requires:
    - len(rated) >= 20  (first early-return guard)
    - >= 3 distinct hours each with >= 5 sessions  (second early-return guard)

    The pattern uses rated sessions only (not sessions), contrasting
    good-outcome rate before-10am vs after-10am. This is a DIFFERENT metric
    from the score (which uses friction-per-hour ratio) — complementary angle.

    _session() defaults: hour=14, friction_counts={}, outcome="".
    We pass rated twice for tests where sessions == rated.
    """

    def _d8_session(self, sid, hour=14, outcome="fully_achieved"):
        """Minimal session for D8: hour, outcome, friction_counts (empty → ratio 0)."""
        return _session(sid, hour=hour, outcome=outcome, friction_counts={})

    def test_pattern_contrasts_morning_vs_after_10am(self):
        """Happy path: 10 morning (hour=8) + 10 afternoon (hour=14) + 5 late (hour=16).
        Morning: 5 fully_achieved, 5 failed → 50%.
        After-10am total: 10 afternoon (8 good, 2 bad) + 5 late (4 good, 1 bad)
          = 12 good out of 15 → 80%.
        Total 25 rated sessions → both guards pass. Pattern must mention '50%',
        '80%', and '10am'.
        """
        morning = (
            [self._d8_session(f"m_good{i}", hour=8, outcome="fully_achieved") for i in range(5)]
            + [self._d8_session(f"m_bad{i}", hour=8, outcome="failed") for i in range(5)]
        )
        afternoon = (
            [self._d8_session(f"a_good{i}", hour=14, outcome="fully_achieved") for i in range(8)]
            + [self._d8_session(f"a_bad{i}", hour=14, outcome="failed") for i in range(2)]
        )
        # 4 good + 1 bad at hour=16 → combined after-10am: 12/15 = 80%
        late = (
            [self._d8_session(f"l_good{i}", hour=16, outcome="fully_achieved") for i in range(4)]
            + [self._d8_session("l_bad0", hour=16, outcome="failed")]
        )
        rated = morning + afternoon + late
        result = aggregate.score_d8_time_mgmt(rated, rated)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("50%", result["pattern"])
        self.assertIn("80%", result["pattern"])
        self.assertIn("10am", result["pattern"])

    def test_pattern_none_when_before_group_too_small(self):
        """>=20 sessions but < 5 before-10am → score computed, pattern is None.
        3 morning (hour=8) + 22 afternoon spread over 3 hours.
        """
        morning = [self._d8_session(f"m{i}", hour=8, outcome="fully_achieved") for i in range(3)]
        # Need >= 3 hours with >= 5 sessions each, and total >= 20.
        # Use hours 14, 15, 16 with 7 sessions each = 21, plus 3 morning = 24 total.
        afternoon = (
            [self._d8_session(f"h14_{i}", hour=14, outcome="fully_achieved") for i in range(7)]
            + [self._d8_session(f"h15_{i}", hour=15, outcome="fully_achieved") for i in range(7)]
            + [self._d8_session(f"h16_{i}", hour=16, outcome="fully_achieved") for i in range(7)]
        )
        rated = morning + afternoon
        result = aggregate.score_d8_time_mgmt(rated, rated)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])
        self.assertIsNotNone(result["score"])

    def test_pattern_none_when_rated_insufficient(self):
        """< 20 rated sessions → first early return fires; pattern key present and None."""
        rated = [self._d8_session(f"s{i}", hour=8) for i in range(15)]
        result = aggregate.score_d8_time_mgmt(rated, rated)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])
        self.assertIsNone(result["score"])

    def test_pattern_none_when_too_few_hours(self):
        """>=20 rated but < 3 hours with >= 5 sessions → second early return fires;
        pattern key present and None.
        20 sessions all at hour=14 → only 1 qualifying hour.
        """
        rated = [self._d8_session(f"s{i}", hour=14) for i in range(20)]
        result = aggregate.score_d8_time_mgmt(rated, rated)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])
        self.assertIsNone(result["score"])


class UsageCharacteristicsTests(unittest.TestCase):
    def test_block_emitted_when_10_plus_sessions(self):
        """20 sessions with varied inputs → specific pct values verify each item.

        Session layout (20 total):
        - Item 1 (hit_output_limit rate): 4 True / 20 → 20%
        - Item 3 (good+TA / good):
            6 fully_achieved (4 with TA) + 4 mostly_achieved (1 with TA) = 10 good, 5 TA
            → correct: 5/10 = 50%
            → bug (missing mostly_achieved): 4/6 = 67% (rounds to 67) ≠ 50 → RED
        - Item 4 (narrow-tool rate): sessions with exactly 1 distinct tool = 10/20 = 50%

        Session index → attributes:
          s0-s5  (6): fully_achieved, first 4 have TA, narrow (1 tool {"Read":5})
          s6-s9  (4): mostly_achieved, first 1 has TA, wide (3 tools)
          s10-s13(4): failed, no TA, hit_output_limit=True, narrow (1 tool)
          s14-s19(6): outcome="", no TA, no limit, wide (3 tools)

        Item 1: hit_output_limit True = s10-s13 = 4/20 = 20
        Item 3: good = s0-s9 = 10; TA in good = s0,s1,s2,s3 + s6 = 5 → 5/10 = 50
                bug path: good = s0-s5 = 6; TA in good = 4 → round(400/6) = 67 (≠ 50)
        Item 4: narrow (len(tool_counts)==1) = s0-s5 (6) + s10-s13 (4) = 10/20 = 50
        """
        sessions = []
        # s0-s5: fully_achieved, first 4 have TA, narrow (1 tool)
        for i in range(6):
            sessions.append(_session(
                f"s{i}",
                outcome="fully_achieved",
                uses_task_agent=(i < 4),
                hit_output_limit=False,
                tool_counts={"Read": 5},
            ))
        # s6-s9: mostly_achieved, only s6 has TA, wide (3 tools)
        for i in range(4):
            sessions.append(_session(
                f"s{i + 6}",
                outcome="mostly_achieved",
                uses_task_agent=(i == 0),
                hit_output_limit=False,
                tool_counts={"Read": 2, "Bash": 1, "Edit": 1},
            ))
        # s10-s13: failed, no TA, hit_output_limit=True, narrow (1 tool)
        for i in range(4):
            sessions.append(_session(
                f"s{i + 10}",
                outcome="failed",
                uses_task_agent=False,
                hit_output_limit=True,
                tool_counts={"Read": 3},
            ))
        # s14-s19: unrated (outcome=""), no TA, no limit, wide (3 tools)
        for i in range(6):
            sessions.append(_session(
                f"s{i + 14}",
                outcome="",
                uses_task_agent=False,
                hit_output_limit=False,
                tool_counts={"Read": 2, "Bash": 1, "Edit": 1},
            ))

        activity = aggregate.compute_activity(sessions)
        self.assertIn("usage_characteristics", activity)
        uc = activity["usage_characteristics"]
        self.assertEqual(uc["n_sessions"], 20)
        self.assertIn("since", uc)
        self.assertIn("until", uc)
        items = uc["items"]
        self.assertEqual(len(items), 5)
        for item in items:
            self.assertIn("pct", item)
            self.assertIn("label", item)
            self.assertIn("tip", item)
            self.assertIsInstance(item["pct"], int)

        # Item 1: hit_output_limit rate = 4/20 = 20%
        self.assertEqual(uc["items"][0]["pct"], 20,
                         "Item 1 (hit_output_limit rate) should be 20% (4/20)")
        # Item 3: good+TA / good = 5/10 = 50%
        # If 'mostly_achieved' were excluded (the bug), denominator = 6 (fully_achieved only),
        # TA count = 4 → round(100*4/6) = 67, NOT 50. This assertion catches the regression.
        self.assertEqual(uc["items"][2]["pct"], 50,
                         "Item 3 (good+TA / good) should be 50% (5/10); "
                         "bug would give 67% (4/6) by missing mostly_achieved")
        # Item 4: narrow-tool (1 distinct tool) rate = 10/20 = 50%
        self.assertEqual(uc["items"][3]["pct"], 50,
                         "Item 4 (narrow-tool rate) should be 50% (10/20)")

    def test_block_omitted_below_10_sessions(self):
        """8 sessions → usage_characteristics NOT in activity."""
        sessions = [_session(f"s{i}") for i in range(8)]
        activity = aggregate.compute_activity(sessions)
        self.assertNotIn("usage_characteristics", activity)

    def test_block_omitted_when_no_sessions(self):
        """compute_activity([]) early return → usage_characteristics NOT in activity."""
        activity = aggregate.compute_activity([])
        self.assertNotIn("usage_characteristics", activity)

    def test_since_until_span_session_dates(self):
        """15 sessions with explicit start dates 2026-03-01 through 2026-03-15 →
        since == '2026-03-01' and until == '2026-03-15'."""
        sessions = [
            _session(f"s{i}", start=f"2026-03-{i + 1:02d}T10:00:00Z")
            for i in range(15)
        ]
        activity = aggregate.compute_activity(sessions)
        self.assertIn("usage_characteristics", activity)
        uc = activity["usage_characteristics"]
        self.assertEqual(uc["since"], "2026-03-01")
        self.assertEqual(uc["until"], "2026-03-15")


if __name__ == "__main__":
    unittest.main()
