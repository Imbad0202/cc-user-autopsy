"""Recruiter version v1 (spec §4): identity -> earned badges -> output
ledger (allowlist-filtered) -> case study -> scope disclosure. The V4 HR
blocks (profile card, memo peer review, 4-signal scores, trends, zone map,
self-awareness caveat) must be gone. Privacy: earned-only badges, no sids,
no non-allowlisted project names."""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import narrative_en  # noqa: E402
from report_render import render, _build_badges_section  # noqa: E402


def _analysis(badges_items):
    return {
        "meta": {"total_sessions": 61, "facets_coverage_pct": 80.0,
                 "date_range": {"first": "2026-06-01T00:00:00Z",
                                "last": "2026-07-10T00:00:00Z"}},
        "aggregates": {
            "tokens": {"total": 1_000_000},
            "projects": {"public-repo": {"sessions": 30, "friction": 2,
                                         "commits": 25, "duration_min": 900,
                                         "label": "public-repo"},
                         "secret-client": {"sessions": 31, "friction": 3,
                                           "commits": 19, "duration_min": 800,
                                           "label": "secret-client"}},
            "weekly": [], "heatmap": {}, "outcomes": {}, "session_types": {},
            "friction": {"totals": {}}, "tools": {"totals": {}},
            "prompt_len_vs_outcome": {}, "helpfulness": {},
            "growth_curve": [], "activity": {},
            "profile_summary": {"scale_tier": "heavy", "total_sessions": 61,
                                "total_duration_hr": 28.0,
                                "project_count_active": 2,
                                "date_span_days": 40, "ta_pct": 40.0,
                                "mcp_pct": 20.0, "specialty": "",
                                "top_project_share_pct": 50.0},
            "shipped_artifacts": [
                {"project": "public-repo", "summary": "Shipped a CLI tool",
                 "project_sessions": 30, "project_duration_min": 900,
                 "project_commits": 25, "total_tokens": 500_000},
                {"project": "secret-client", "summary": "SECRET-WORK-SUMMARY",
                 "project_sessions": 31, "project_duration_min": 800,
                 "project_commits": 19, "total_tokens": 400_000},
            ],
            "efficiency": {"commits_per_hour": 1.5},
        },
        "scores": {"_overall": {"avg": 6.4, "dimensions_scored": 9,
                                "dimensions_total": 9}},
        "ledger": {"window": {"start": "2026-06-01", "end": "2026-07-10",
                              "days": 39},
                   "output": {"git_commits": 44, "git_pushes": 12,
                              "sessions_with_commits": 18}},
        "badges": {"schema_version": 1, "standard_version": "v1",
                   "items": badges_items},
    }


EARNED = {"id": "delegation", "earned": True, "n": 20,
          "metrics": {"ta_rate_pct": 45.0, "good_rate_with_ta_pct": 75.0},
          "thresholds": {"min_ta_rated": 15, "ta_rate_pct": 30.0,
                         "good_rate_with_ta_pct": 70.0}}
UNEARNED = {"id": "root_cause", "earned": False, "n": 40,
            "metrics": {"iter_buggy_pct": 12.0},
            "thresholds": {"min_rated": 30, "max_iter_buggy_pct": 7.0}}


def _render_hr(badges_items, **kw):
    return render(
        analysis=_analysis(badges_items), samples_data={},
        peer_review_md="MEMO-BODY-MUST-NOT-RENDER", locale="en",
        audience="hr", narrative=narrative_en,
        profile_info={"name": "Jane Doe", "role": "QA lead"},
        public_set={"public-repo"}, category_map={},
        case_study_md="## Case\nA redacted case study.", **kw)


class HrLayoutTests(unittest.TestCase):
    def test_five_block_layout_present(self):
        html = _render_hr([EARNED, UNEARNED])
        self.assertIn('id="badges"', html)
        self.assertIn('id="hr-output"', html)
        self.assertIn('id="case-study"', html)
        self.assertIn('id="method"', html)
        self.assertIn("Jane Doe", html)

    def test_v4_blocks_demolished(self):
        html = _render_hr([EARNED])
        self.assertNotIn('id="scores"', html)
        self.assertNotIn('id="peer-review-section"', html)
        self.assertNotIn('id="trends"', html)
        self.assertNotIn("profile-card", html)
        self.assertNotIn("zone-map", html)
        self.assertNotIn("MEMO-BODY-MUST-NOT-RENDER", html)

    def test_no_ledger_sections_in_hr(self):
        self.assertNotIn('id="ledger-', _render_hr([EARNED]))


class BadgeRenderTests(unittest.TestCase):
    def test_earned_only(self):
        html = _render_hr([EARNED, UNEARNED])
        self.assertIn("Delegation", html)
        self.assertNotIn("Root-cause", html)
        # never render "failed"/unearned wording
        self.assertNotIn("not earned", html.lower())

    def test_zero_earned_suppresses_section(self):
        html = _render_hr([UNEARNED])
        self.assertNotIn('id="badges"', html)

    def test_criteria_line_carries_numbers(self):
        html = _render_hr([EARNED])
        self.assertIn("45", html)   # metric
        self.assertIn("30", html)   # bar
        self.assertIn("20", html)   # n

    def test_builder_empty_on_no_badges_block(self):
        self.assertEqual(_build_badges_section({}, {}, "en"), "")


class HrOutputLedgerTests(unittest.TestCase):
    def test_allowlist_filtering(self):
        html = _render_hr([EARNED])
        self.assertIn("public-repo", html)
        self.assertNotIn("secret-client", html)
        self.assertNotIn("SECRET-WORK-SUMMARY", html)

    def test_output_counters_render(self):
        html = _render_hr([EARNED])
        self.assertIn("44", html)


class ScopeDisclosureTests(unittest.TestCase):
    def test_scope_disclosure_names_standard_and_repro(self):
        html = _render_hr([EARNED, UNEARNED])
        self.assertIn("v1", html)
        self.assertIn("scoring-rubric.md", html)

    def test_self_awareness_caveat_gone(self):
        from locales import STRINGS
        self.assertNotIn("hr_self_awareness_caveat", STRINGS["en"])


class SelfUnaffectedTests(unittest.TestCase):
    def test_self_never_renders_badge_section(self):
        html = render(
            analysis=_analysis([EARNED]), samples_data={},
            peer_review_md="", locale="en", audience="self",
            narrative=narrative_en)
        self.assertNotIn('id="badges"', html)


if __name__ == "__main__":
    unittest.main()
