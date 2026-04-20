"""Tests for the (unknown)-project bias fix.

Background
----------
Sessions whose transcript does not expose a project path land in
``project_path == "(unknown)"``. The scanner cannot run ``git log`` for those
sessions, so ``git_commits`` is structurally 0 regardless of whether the user
actually committed work. Three places in the aggregator conflated this with
genuine "no-commit" behaviour:

1. ``score_d4_context_mgmt`` — the 79% "long sessions with zero commits" red
   flag counted unknown-project sessions, inflating the metric.
2. ``shipped_artifacts`` — the (unknown) bucket could appear as a shipped
   artefact even though it has 0 project commits, 0 pushes, and no repo.
3. ``profile_summary.top_project_label`` — "(unknown)" won by session count
   over real projects, making the "your top project" line meaningless.

These tests fail on main and pass after the fix.
"""
from __future__ import annotations

from scripts.aggregate import score_d4_context_mgmt


def _sess(**overrides):
    """Minimal session dict covering fields aggregate paths read."""
    base = {
        "sid": "dead" + "0" * 28,
        "sid8": "dead0000",
        "project": "my-repo",
        "project_key": "/Users/u/Projects/my-repo",
        "project_path": "/Users/u/Projects/my-repo",
        "start": "2026-04-01T10:00:00+00:00",
        "week": "2026-W14",
        "duration_min": 30,
        "total_tokens": 50000,
        "input_tokens": 10000,
        "output_tokens": 2000,
        "cache_read_tokens": 100000,
        "cache_create_tokens": 5000,
        "cache_read": 100000,
        "cache_create": 5000,
        "interrupts": 0,
        "git_commits": 0,
        "git_pushes": 0,
        "friction_counts": {},
        "friction_detail": "",
        "tool_counts": {},
        "uses_task_agent": False,
        "uses_subagent": False,
        "uses_mcp": False,
        "uses_web_search": False,
        "uses_web_fetch": False,
        "first_prompt": "",
        "first_prompt_len": 0,
        "hour_of_day": 10,
        "weekday": 2,
        "outcome": "fully_achieved",
        "helpfulness": "essential",
        "session_type": "multi_task",
        "goal_categories": {},
        "goal_cats": {},
        "primary_success": "",
        "brief_summary": "built the thing",
        "user_msgs": 5,
        "tool_errors": 0,
        "hit_output_limit": False,
        "lines_added": 0,
        "lines_removed": 0,
        "files_modified": 0,
        "model_counts": {},
        "response_times": [],
        "message_hours": [10],
        "source_machine": "local",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# D4 — "no commits after 20 min" should exclude (unknown)-project sessions
# ---------------------------------------------------------------------------
class TestD4ExcludesUnknownProject:
    def test_unknown_sessions_do_not_inflate_enc_pct(self):
        """50 unknown+0commits sessions + 10 known+0commits (out of 10 known)
        should produce enc_pct based on the 10 known, not the 60 combined."""
        sessions = [
            _sess(project_path="(unknown)", project_key="(unknown)",
                  git_commits=0, duration_min=30)
            for _ in range(50)
        ] + [
            _sess(project_path="/Users/u/Projects/real-repo",
                  project_key="/Users/u/Projects/real-repo",
                  git_commits=1, duration_min=30)  # this one committed
            for _ in range(5)
        ] + [
            _sess(project_path="/Users/u/Projects/real-repo",
                  project_key="/Users/u/Projects/real-repo",
                  git_commits=0, duration_min=30)  # this one didn't
            for _ in range(5)
        ]

        result = score_d4_context_mgmt(sessions)

        # The real "no commit" rate is 5/10 = 50%. Buggy version would report
        # 55/60 = 91.7%. Assert we are on the correct side.
        assert result["metric_effort_no_commit_pct"] == 50.0, (
            f"enc_pct should reflect the real-project pool only; "
            f"got {result['metric_effort_no_commit_pct']}"
        )

    def test_all_unknown_produces_null_enc_pct(self):
        """If every session is (unknown), we can't measure commit behaviour —
        enc_pct should be 0 (no eligible sessions), not 100%."""
        sessions = [
            _sess(project_path="(unknown)", project_key="(unknown)",
                  git_commits=0, duration_min=30)
            for _ in range(20)
        ]
        result = score_d4_context_mgmt(sessions)
        # With zero eligible sessions, enc_pct is 0 by definition of the
        # "if over20 else 0" guard — but we also expect the score to not
        # trigger the penalty paths that require >15% / >30%.
        assert result["metric_effort_no_commit_pct"] == 0.0

    def test_metric_exposes_eligible_sample_size(self):
        """Consumers (peer review, HTML) need to know how many sessions went
        into enc_pct so they don't over-interpret a 3/4 ratio as a trend."""
        sessions = [
            _sess(project_path="(unknown)", project_key="(unknown)",
                  git_commits=0, duration_min=30)
            for _ in range(30)
        ] + [
            _sess(project_path="/r/p", project_key="/r/p",
                  git_commits=0, duration_min=30)
            for _ in range(8)
        ]
        result = score_d4_context_mgmt(sessions)
        # 8 eligible known-project long sessions, 30 unknown excluded.
        assert result.get("metric_effort_no_commit_sample") == 8, (
            f"expected 8 eligible, got {result.get('metric_effort_no_commit_sample')}"
        )


# ---------------------------------------------------------------------------
# shipped_artifacts — (unknown) must not appear
# ---------------------------------------------------------------------------
class TestShippedExcludesUnknown:
    def test_unknown_project_not_in_shipped(self):
        """A (unknown) session with a good summary must not be listed as a
        shipped artefact, because we cannot attribute it to a repo."""
        sessions_meta = [
            {
                "session_id": "aaaa" + "0" * 28,
                "project_path": "(unknown)",
                "start_time": "2026-04-01T10:00:00+00:00",
                "duration_minutes": 30,
                "user_message_count": 5,
                "assistant_message_count": 10,
                "tool_counts": {},
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_creation_input_tokens": 100,
                "cache_read_input_tokens": 1000,
                "model_counts": {},
                "git_commits": 0,
                "git_pushes": 0,
                "user_interruptions": 0,
                "tool_errors": 0,
                "hit_output_limit": False,
                "uses_task_agent": False,
                "uses_subagent": False,
                "uses_mcp": False,
                "uses_web_search": False,
                "uses_web_fetch": False,
                "first_prompt": "",
                "user_response_times": [],
                "message_hours": [10],
                "lines_added": 0,
                "lines_removed": 0,
                "files_modified": 0,
            },
        ]
        # We cannot easily call aggregate() here with full fixtures; instead
        # test the filter predicate directly by asserting downstream
        # consumers never see (unknown) in shipped. The unit test for the
        # dict-building code path is in test_build_html_additions.py; here
        # we just assert the guard exists via the helper.
        from scripts.aggregate import is_shippable_project_key
        assert is_shippable_project_key("(unknown)") is False
        assert is_shippable_project_key("/Users/u/Projects/real") is True


# ---------------------------------------------------------------------------
# profile_summary.top_project_label — skip (unknown)
# ---------------------------------------------------------------------------
class TestTopProjectSkipsUnknown:
    def test_top_project_picks_largest_known_project(self):
        """When (unknown) has the most sessions, top_project_label should
        still be the largest *real* project."""
        from scripts.aggregate import pick_top_project
        proj_detail = {
            "(unknown)": {"label": "(unknown)", "sessions": 218, "path": "(unknown)"},
            "/r/real-big": {"label": "real-big", "sessions": 50, "path": "/r/real-big"},
            "/r/real-small": {"label": "real-small", "sessions": 5, "path": "/r/real-small"},
        }
        top = pick_top_project(proj_detail)
        assert top is not None
        key, data = top
        assert data["label"] == "real-big", f"expected real-big, got {data['label']}"

    def test_top_project_returns_none_when_only_unknown(self):
        from scripts.aggregate import pick_top_project
        proj_detail = {
            "(unknown)": {"label": "(unknown)", "sessions": 50, "path": "(unknown)"},
        }
        assert pick_top_project(proj_detail) is None
