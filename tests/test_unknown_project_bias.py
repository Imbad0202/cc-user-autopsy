"""Tests for the (unknown)-project bias fixes.

Background
----------
Sessions whose transcript does not expose a project path land in
``project_path == "(unknown)"``. The scanner cannot run ``git log`` for those
sessions, so ``git_commits`` is structurally 0 regardless of whether the user
actually committed work. Multiple aggregator paths conflated this with
genuine no-commit behaviour:

1. ``score_d4_context_mgmt`` — "long sessions with zero commits" red flag.
2. ``shipped_artifacts`` — (unknown) appeared as a shipped artefact.
3. ``profile_summary.top_project_label`` — (unknown) won by session count.
4. ``efficiency.commits_per_hour`` — denominator included unknown duration,
   deflating the velocity metric (exposed as HR "Velocity").
5. ``profile_summary.project_count_active`` — (unknown) counted as real.
6. ``d4_explanation`` narrative — rendered "50%" without "n=<sample>".

Plus edge cases for ``is_shippable_project_key``: whitespace-only keys,
mixed-case "(Unknown)", and keys that are just empty strings.

These tests fail on main and pass after the corresponding fix.
"""
from __future__ import annotations

from scripts.aggregate import (
    is_shippable_project_key,
    pick_top_project,
    score_d4_context_mgmt,
)


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
# D4 — "no commits after 20 min" excludes (unknown)-project sessions
# ---------------------------------------------------------------------------
class TestD4ExcludesUnknownProject:
    def test_unknown_sessions_do_not_inflate_enc_pct(self):
        """50 unknown+0commits sessions + 10 known (5 committed, 5 not)
        should produce 50% enc_pct, not 91.7%."""
        sessions = [
            _sess(project_path="(unknown)", project_key="(unknown)",
                  git_commits=0, duration_min=30)
            for _ in range(50)
        ] + [
            _sess(project_path="/Users/u/Projects/real-repo",
                  project_key="/Users/u/Projects/real-repo",
                  git_commits=1, duration_min=30)
            for _ in range(5)
        ] + [
            _sess(project_path="/Users/u/Projects/real-repo",
                  project_key="/Users/u/Projects/real-repo",
                  git_commits=0, duration_min=30)
            for _ in range(5)
        ]
        result = score_d4_context_mgmt(sessions)
        assert result["metric_effort_no_commit_pct"] == 50.0

    def test_all_unknown_produces_zero_enc_pct(self):
        sessions = [
            _sess(project_path="(unknown)", project_key="(unknown)",
                  git_commits=0, duration_min=30)
            for _ in range(20)
        ]
        result = score_d4_context_mgmt(sessions)
        assert result["metric_effort_no_commit_pct"] == 0.0

    def test_metric_exposes_eligible_sample_size(self):
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
        assert result.get("metric_effort_no_commit_sample") == 8


# ---------------------------------------------------------------------------
# is_shippable_project_key edge cases
# ---------------------------------------------------------------------------
class TestIsShippableProjectKey:
    def test_plain_unknown_rejected(self):
        assert is_shippable_project_key("(unknown)") is False

    def test_empty_string_rejected(self):
        assert is_shippable_project_key("") is False

    def test_real_path_accepted(self):
        assert is_shippable_project_key("/Users/u/Projects/real") is True

    def test_whitespace_only_rejected(self):
        """A project_key that is only spaces/tabs/newlines is not a real
        project — don't count it in shipped/top-project/D4."""
        assert is_shippable_project_key("   ") is False
        assert is_shippable_project_key("\t\n") is False

    def test_mixed_case_unknown_rejected(self):
        """External/merged data sources may produce variants like '(Unknown)'
        or '(UNKNOWN)' — normalize when comparing."""
        assert is_shippable_project_key("(Unknown)") is False
        assert is_shippable_project_key("(UNKNOWN)") is False

    def test_padded_unknown_rejected(self):
        """If the key arrives with surrounding whitespace, still treat as
        unresolved."""
        assert is_shippable_project_key("  (unknown)  ") is False


# ---------------------------------------------------------------------------
# pick_top_project edge cases
# ---------------------------------------------------------------------------
class TestTopProjectSkipsUnknown:
    def test_top_project_picks_largest_known_project(self):
        proj_detail = {
            "(unknown)": {"label": "(unknown)", "sessions": 218, "path": "(unknown)"},
            "/r/real-big": {"label": "real-big", "sessions": 50, "path": "/r/real-big"},
            "/r/real-small": {"label": "real-small", "sessions": 5, "path": "/r/real-small"},
        }
        top = pick_top_project(proj_detail)
        assert top is not None
        key, data = top
        assert data["label"] == "real-big"

    def test_top_project_returns_none_when_only_unknown(self):
        proj_detail = {
            "(unknown)": {"label": "(unknown)", "sessions": 50, "path": "(unknown)"},
        }
        assert pick_top_project(proj_detail) is None


# ---------------------------------------------------------------------------
# D4 narrative — must surface n=<sample>
# ---------------------------------------------------------------------------
class TestD4NarrativeSurfacesSample:
    def test_en_narrative_includes_sample_size(self):
        """d4_explanation in English must include (n=<sample>) so the reader
        knows the denominator of the zero-commit percentage."""
        from scripts.narrative_en import d4_explanation
        metrics = {
            "metric_output_token_limit_sessions": 8,
            "metric_effort_no_commit_pct": 50.0,
            "metric_effort_no_commit_sample": 92,
            "metric_long_session_interrupt_rate_pct": 27.0,
        }
        text = d4_explanation(metrics)
        assert "92" in text, f"expected n=92 in narrative; got: {text}"

    def test_zh_narrative_includes_sample_size(self):
        from scripts.narrative_zh import d4_explanation
        metrics = {
            "metric_output_token_limit_sessions": 8,
            "metric_effort_no_commit_pct": 50.0,
            "metric_effort_no_commit_sample": 92,
            "metric_long_session_interrupt_rate_pct": 27.0,
        }
        text = d4_explanation(metrics)
        assert "92" in text, f"expected n=92 in zh narrative; got: {text}"


# ---------------------------------------------------------------------------
# commits_per_hour must exclude (unknown) duration
# ---------------------------------------------------------------------------
class TestCommitsPerHourExcludesUnknown:
    def test_commits_per_hour_excludes_unknown_duration(self):
        """10 unknown 30-min sessions + 10 known 30-min 1-commit sessions.
        Known-only: 10 commits / 5 hours = 2.0 commits/hr.
        Buggy version (includes unknown duration): 10 / 10 = 1.0 commits/hr."""
        from scripts.aggregate import compute_efficiency
        sessions = [
            _sess(project_path="(unknown)", project_key="(unknown)",
                  git_commits=0, duration_min=30)
            for _ in range(10)
        ] + [
            _sess(project_path="/r/p", project_key="/r/p",
                  git_commits=1, duration_min=30)
            for _ in range(10)
        ]
        eff = compute_efficiency(sessions)
        assert eff["commits_per_hour"] == 2.0, (
            f"expected 2.0 commits/hr from known-project only; got {eff['commits_per_hour']}"
        )


# ---------------------------------------------------------------------------
# profile_summary.project_count_active must exclude (unknown)
# ---------------------------------------------------------------------------
class TestProjectCountActiveExcludesUnknown:
    def test_project_count_active_excludes_unknown(self):
        """(unknown) with 218 sessions + 2 real projects each with ≥3 sessions
        should yield project_count_active = 2, not 3."""
        from scripts.aggregate import count_active_projects
        proj_detail = {
            "(unknown)": {"label": "(unknown)", "sessions": 218, "path": "(unknown)"},
            "/r/a": {"label": "a", "sessions": 10, "path": "/r/a"},
            "/r/b": {"label": "b", "sessions": 5, "path": "/r/b"},
            "/r/tiny": {"label": "tiny", "sessions": 2, "path": "/r/tiny"},  # below threshold
        }
        assert count_active_projects(proj_detail) == 2
