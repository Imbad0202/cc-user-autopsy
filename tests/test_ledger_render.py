"""TDD for direction-C rendering foundation: Exhibit frame, ledger narration
parser, and locale keys. See docs/superpowers/sdd/task-7-brief.md.

These are foundation-only tests — the section builders that call these
helpers land in a later task. Here we only verify the frame/parser
primitives and locale parity.
"""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import locales  # noqa: E402
from report_render import (  # noqa: E402
    _exhibit, _parse_ledger_narration,
    _build_opening_band, _build_output_ledger, _build_team_ledger)


class ExhibitTests(unittest.TestCase):
    def test_exhibit_frame(self):
        html = _exhibit(3, "Weekly share", "<p>body</p>",
                        "aggregate.py, transcript pool", locale="en")
        self.assertIn("EXHIBIT", html)
        self.assertIn("3", html)
        self.assertIn("<p>body</p>", html)
        self.assertIn("aggregate.py, transcript pool", html)

    def test_exhibit_escapes_source_line(self):
        html = _exhibit(1, "t", "<p>b</p>", "<script>x</script>", locale="en")
        self.assertNotIn("<script>x</script>", html)


class NarrationParseTests(unittest.TestCase):
    def test_parses_three_books(self):
        md = ("# opening\nOne sentence.\n"
              "# output-ledger\nClaim A.\n\nMore.\n"
              "# team-ledger\nClaim B.\n")
        d = _parse_ledger_narration(md)
        self.assertEqual(d["opening"], "One sentence.")
        self.assertTrue(d["output-ledger"].startswith("Claim A."))
        self.assertEqual(d["team-ledger"], "Claim B.")

    def test_missing_sections_empty(self):
        d = _parse_ledger_narration("")
        self.assertEqual(d, {"opening": "", "output-ledger": "", "team-ledger": ""})


class LedgerLocaleKeyTests(unittest.TestCase):
    REQUIRED = [
        "ledger_exhibit_label", "ledger_source_prefix", "ledger_opening_kicker",
        "ledger_output_title", "ledger_team_title", "ledger_source_card_full",
        "ledger_source_card_partial", "ledger_source_card_presence",
        "ledger_not_detected", "ledger_degraded_note",
        "ledger_common_window_note_template", "ledger_weekly_share_title",
        "ledger_parallel_title", "ledger_matrix_title", "ledger_h2h_title",
    ]

    def test_keys_in_both_locales(self):
        for loc in ("en", "zh_TW"):
            for key in self.REQUIRED:
                self.assertIn(key, locales.STRINGS[loc], f"{loc}:{key}")


CROSS = {
    "sources": [
        {"source": "claude", "coverage": "full", "session_count": 40,
         "first_date": "2026-05-01", "last_date": "2026-06-20",
         "total_input_tokens": 1000, "total_output_tokens": 200, "parse_errors": 0},
        {"source": "codex", "coverage": "full", "session_count": 12,
         "first_date": "2026-05-10", "last_date": "2026-06-18",
         "total_input_tokens": 500, "total_output_tokens": 90, "parse_errors": 0},
    ],
    "common_window": {"start": "2026-05-10", "end": "2026-06-18",
                      "days": 39, "degraded": False},
    "weekly_share": [{"week": "2026-W20", "minutes": {"claude": 300, "codex": 120}}],
    "parallel": {"heatmap": [[0] * 24 for _ in range(7)],
                 "daily_max": [], "hours_multi_source": 3,
                 "hours_single_source": 50},
    "project_matrix": {"projects": ["webapp"], "sources": ["claude", "codex"],
                       "counts": [[30, 10]]},
    "head_to_head": {"window_days": 39,
                     "claude": {"sessions": 35, "active_days": 30,
                                "total_tokens": 1200, "median_duration_minutes": 40},
                     "codex": {"sessions": 12, "active_days": 10,
                               "total_tokens": 590, "median_duration_minutes": 25}},
}
LEDGER = {"schema_version": 1,
          "window": {"start": "2026-05-01", "end": "2026-06-20", "days": 50},
          "output": {"git_commits": 21, "git_pushes": 9,
                     "sessions_with_commits": 14},
          "sources_detected": ["claude", "codex"]}
NARR = {"opening": "Your AI team shipped 21 commits for about $80.",
        "output-ledger": "21 commits landed in 50 days.\n\nDetail prose.",
        "team-ledger": "Codex took the long jobs.\n\nMore prose."}


class OpeningBandTests(unittest.TestCase):
    def test_contains_opening_sentence(self):
        html = _build_opening_band(LEDGER, NARR, "en")
        self.assertIn("Your AI team shipped 21 commits", html)

    def test_empty_narration_renders_without_fabricated_prose(self):
        html = _build_opening_band(LEDGER,
                                   {"opening": "", "output-ledger": "",
                                    "team-ledger": ""}, "en")
        self.assertNotIn("None", html)


class OutputLedgerTests(unittest.TestCase):
    def test_metrics_and_source_line(self):
        html = _build_output_ledger(LEDGER, NARR, "en")
        self.assertIn("21", html)
        self.assertIn("EXHIBIT", html)
        self.assertIn("ledger.output", html)


class TeamLedgerTests(unittest.TestCase):
    def test_source_cards_and_h2h(self):
        html = _build_team_ledger(CROSS, NARR, "en")
        self.assertIn("codex", html.lower())
        self.assertIn("39", html)          # window days
        self.assertIn("EXHIBIT", html)

    def test_degraded_window_drops_comparisons(self):
        degraded = dict(CROSS, common_window={"start": "2026-06-10",
                                              "end": "2026-06-18",
                                              "days": 8, "degraded": True})
        html = _build_team_ledger(degraded, NARR, "en")
        self.assertNotIn("2026-W20", html)   # no weekly comparison exhibit
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["ledger_degraded_note"], html)

    def test_never_prints_prompt_text(self):
        cross = dict(CROSS)
        cross["sources"] = CROSS["sources"] + [
            {"source": "grok", "coverage": "partial", "session_count": 3,
             "first_date": "2026-06-01", "last_date": "2026-06-05",
             "total_input_tokens": None, "total_output_tokens": None,
             "parse_errors": 0}]
        html = _build_team_ledger(cross, NARR, "en")
        self.assertNotIn("GROK_PRIVATE_MARKER", html)


def _minimal_ledger_analysis():
    """Smallest analysis-data shape (same skeleton as
    test_build_html_additions._minimal_analysis) plus ledger/cross_llm blocks,
    so we can drive build_html.py end-to-end for the HR/SELF gating test."""
    return {
        "meta": {"total_sessions": 5, "sessions_with_facets": 3,
                 "facets_coverage_pct": 60.0,
                 "date_range": {"first": "2026-03-01T00:00:00Z",
                                "last": "2026-04-01T00:00:00Z"},
                 "tz_offset_hours": 8.0, "data_thin_warning": False},
        "aggregates": {
            "activity": {"total_sessions": 5, "total_messages": 100,
                         "active_days": 10, "current_streak": 2,
                         "longest_streak": 5,
                         "cache_creation_tokens": 1_000_000,
                         "cache_read_tokens": 50_000_000,
                         "models": {"claude-opus-4-7": 50},
                         "favorite_model": "claude-opus-4-7",
                         "api_equivalent_cost_usd": 234.0},
            "tokens": {"total": 1000, "median": 100, "p90": 500, "max": 800, "dist_buckets": {}},
            "tools": {"totals": {}, "sessions_using_task_agent": 0,
                      "sessions_using_mcp": 0, "sessions_using_web_search": 0,
                      "sessions_using_web_fetch": 0},
            "heatmap": {}, "projects": {}, "outcomes": {},
            "friction": {"totals": {}, "by_outcome": {}},
            "interrupts": {"sessions_with_interrupt": 0, "total_interrupts": 0, "interrupt_rate_pct": 0},
            "prompt_len_vs_outcome": {}, "weekly": [],
            "extremes": {"top_tokens": [], "top_interrupts": [], "top_duration": [],
                         "highest_friction": [], "outcome_not_achieved": []},
            "session_types": {}, "helpfulness": {},
            "response_times": {"median_seconds": 10, "mean_seconds": 10, "p90_seconds": 10, "sample_count": 5},
            "goal_categories": {},
            "efficiency": {"tokens_per_commit_median": 0, "sessions_with_commits": 0,
                           "commits_per_hour": 0, "total_duration_hr": 1.0},
            "shipped_artifacts": [], "growth_curve": [],
            "profile_summary": {"scale_tier": "light", "total_duration_hr": 1.0,
                                "total_sessions": 5, "project_count_active": 1,
                                "top_project_share_pct": 100.0,
                                "top_project_label": "demo", "ta_pct": 0,
                                "mcp_pct": 0, "specialty": "x", "date_span_days": 30},
        },
        "scores": {"_overall": {"avg": 0, "dimensions_scored": 0, "dimensions_total": 8}},
        "_sessions": [],
        "ledger": LEDGER,
        "cross_llm": CROSS,
    }


def _run_build_with_ledger(audience, tmp_path):
    """Drive build_html.py as a subprocess (same pattern as
    test_build_html_additions._run_build) with --ledger-narration wired in."""
    import subprocess
    import json as _json
    (tmp_path / "a.json").write_text(_json.dumps(_minimal_ledger_analysis()))
    (tmp_path / "s.json").write_text("{}")
    narr_md = (
        "# opening\n" + NARR["opening"] + "\n"
        "# output-ledger\n" + NARR["output-ledger"] + "\n"
        "# team-ledger\n" + NARR["team-ledger"] + "\n"
    )
    (tmp_path / "narr.md").write_text(narr_md)
    out = tmp_path / "out.html"
    skill_dir = SKILL_DIR
    cmd = [
        "python3", str(skill_dir / "scripts" / "build_html.py"),
        "--input", str(tmp_path / "a.json"),
        "--samples", str(tmp_path / "s.json"),
        "--audience", audience,
        "--ledger-narration", str(tmp_path / "narr.md"),
        "--output", str(out),
        # Always isolate the snapshot hook — without this, every SELF test
        # build appends junk to the user's REAL autopsy-history.jsonl.
        "--history-file", str(tmp_path / "history.jsonl"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"build_html.py exited {r.returncode}: {r.stderr}")
    return out.read_text()


class LedgerAudienceGateTests(unittest.TestCase):
    def test_hr_excludes_ledger_sections_self_includes_them(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html_hr = _run_build_with_ledger("hr", tmp_path)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html_self = _run_build_with_ledger("self", tmp_path)
        # Static CSS rules for .c-exhibit are always present in the
        # stylesheet, so check for the rendered element (class="c-exhibit")
        # rather than the bare class-name substring.
        self.assertNotIn('class="c-exhibit"', html_hr)
        self.assertIn('class="c-exhibit"', html_self)
        # Belt-and-suspenders: none of the three ledger section ids render in HR.
        for sec_id in ("ledger-opening", "ledger-output", "ledger-team"):
            self.assertNotIn(f'id="{sec_id}"', html_hr)
            self.assertIn(f'id="{sec_id}"', html_self)


if __name__ == "__main__":
    unittest.main()
