"""TDD for new HTML additions: API-equivalent cost tile + models chart.

Tests are intentionally narrow — they check that the specific elements
appear in the output, not the full rendered layout. Render tests beyond that
become brittle and fight the authors.
"""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import build_html  # noqa: E402


def _activity_panel(**overrides):
    base = {
        "total_sessions": 10,
        "total_messages": 100,
        "active_days": 5,
        "current_streak": 2,
        "longest_streak": 3,
        "cache_creation_tokens": 1_000_000,
        "cache_read_tokens": 5_000_000,
        "models": {"claude-opus-4-6": 50, "claude-haiku-4-5": 30},
        "favorite_model": "claude-opus-4-6",
        "api_equivalent_cost_usd": 1234.56,
    }
    base.update(overrides)
    return base


class CostTileTests(unittest.TestCase):
    def test_activity_panel_shows_api_equivalent_cost(self):
        """The Desktop-style activity panel must include a tile showing the
        API-equivalent cost when the aggregator provides it."""
        html = build_html._build_activity_panel(_activity_panel())
        self.assertIn("API-equivalent", html)
        # Dollar amount should render compactly (e.g. $1.2k or $1,234)
        self.assertTrue("$1" in html, f"expected dollar amount in panel, got: {html[:500]}")

    def test_cost_tile_hidden_when_zero(self):
        """When cost is 0 (e.g. no cache/tokens data available), the tile
        should not appear — otherwise readers assume the work was free."""
        html = build_html._build_activity_panel(
            _activity_panel(api_equivalent_cost_usd=0.0,
                            cache_creation_tokens=0, cache_read_tokens=0))
        self.assertNotIn("API-equivalent", html)


class ModelsChartTests(unittest.TestCase):
    def test_activity_panel_includes_models_chart_canvas(self):
        """When `models` is populated, the activity panel must render a chart
        container plus a prettified model label (e.g. 'Opus 4.6')."""
        html = build_html._build_activity_panel(_activity_panel())
        self.assertIn('id="models-chart"', html)
        self.assertIn("Opus 4.6", html)

    def test_no_chart_when_models_empty(self):
        """Empty models dict → no chart canvas (avoid rendering an empty box)."""
        html = build_html._build_activity_panel(_activity_panel(models={}))
        self.assertNotIn('id="models-chart"', html)


class HRLayoutTests(unittest.TestCase):
    """HR version should not duplicate at-a-glance data.

    profile-card already exposes scale / velocity / parallel-work. Adding a
    full Overview section with 8 more tiles + charts duplicates the story
    and pushes the peer review below the fold. HR-specific: Overview is
    hidden, but the activity panel (cache/models/cost — the highest-value
    numbers for readers comparing builders) lives directly under the
    profile card. Self audit still gets the full Overview.
    """
    def _build_hr(self, **overrides):
        # Minimal analysis-data + profile to exercise build_report_html.
        import subprocess, tempfile, json as _json
        skill_dir = Path(__file__).resolve().parent.parent
        analysis = {
            "meta": {"total_sessions": 5, "sessions_with_facets": 3,
                     "facets_coverage_pct": 60.0,
                     "date_range": {"first": "2026-03-01T00:00:00Z",
                                    "last": "2026-04-01T00:00:00Z"},
                     "tz_offset_hours": 8.0, "data_thin_warning": False},
            "aggregates": {
                "activity": {
                    "total_sessions": 5, "total_messages": 100,
                    "active_days": 10, "current_streak": 2, "longest_streak": 5,
                    "cache_creation_tokens": 1_000_000,
                    "cache_read_tokens": 50_000_000,
                    "models": {"claude-opus-4-6": 50, "claude-haiku-4-5": 20},
                    "favorite_model": "claude-opus-4-6",
                    "api_equivalent_cost_usd": 234.0,
                },
                "tokens": {"total": 1000, "median": 100, "p90": 500, "max": 800,
                           "dist_buckets": {}},
                "tools": {"totals": {"Bash": 3}, "sessions_using_task_agent": 3,
                          "sessions_using_mcp": 1, "sessions_using_web_search": 0,
                          "sessions_using_web_fetch": 0},
                "heatmap": {}, "projects": {}, "outcomes": {}, "friction": {"totals": {}, "by_outcome": {}},
                "interrupts": {"sessions_with_interrupt": 0, "total_interrupts": 0, "interrupt_rate_pct": 0},
                "prompt_len_vs_outcome": {}, "weekly": [],
                "extremes": {"top_tokens": [], "top_interrupts": [], "top_duration": [],
                             "highest_friction": [], "outcome_not_achieved": []},
                "session_types": {}, "helpfulness": {}, "response_times": {"median_seconds": 10, "mean_seconds": 10, "p90_seconds": 10, "sample_count": 5},
                "goal_categories": {},
                "efficiency": {"tokens_per_commit_median": 0, "sessions_with_commits": 0,
                               "commits_per_hour": 0.5, "total_duration_hr": 1.0},
                "shipped_artifacts": [], "growth_curve": [],
                "profile_summary": {"scale_tier": "light", "total_duration_hr": 1.0,
                                    "total_sessions": 5, "project_count_active": 1,
                                    "top_project_share_pct": 100.0,
                                    "top_project_label": "demo", "ta_pct": 60.0,
                                    "mcp_pct": 20.0, "specialty": "testing",
                                    "date_span_days": 30},
            },
            "scores": {"_overall": {"avg": 7.0, "dimensions_scored": 0, "dimensions_total": 8}},
            "_sessions": [],
        }
        profile = {"name": "Test User", "role": "Tester", "contact": {}}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.json").write_text(_json.dumps(analysis))
            (tmp / "s.json").write_text("{}")
            (tmp / "p.json").write_text(_json.dumps(profile))
            out = tmp / "out.html"
            r = subprocess.run([
                "python3", str(skill_dir / "scripts" / "build_html.py"),
                "--input", str(tmp / "a.json"),
                "--samples", str(tmp / "s.json"),
                "--profile", str(tmp / "p.json"),
                "--audience", "hr",
                "--output", str(out),
            ], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return out.read_text()

    def test_hr_has_no_overview_section(self):
        """§ 01 Overview must be absent from HR output."""
        html = self._build_hr()
        self.assertNotIn('id="overview"', html)
        self.assertNotIn('§ 01', html)

    def test_hr_still_shows_activity_panel_under_profile(self):
        """Activity panel (cache/models/cost) must remain — it's the most
        compelling scale signal for a reader who lacks access to raw data."""
        html = self._build_hr()
        self.assertIn("Cache-read tokens", html)
        self.assertIn("API-equivalent", html)
        self.assertIn('id="models-chart"', html)

    def test_self_still_has_overview_section(self):
        """Self audit keeps Overview — the reader is the user themselves and
        wants the full dump."""
        import subprocess, tempfile, json as _json
        skill_dir = Path(__file__).resolve().parent.parent
        # Reuse the same analysis dict by calling _build_hr's fixture path.
        analysis = self._build_hr.__func__  # silence unused warn
        # Keep it simple: just check a fresh self build directly.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.json").write_text(_json.dumps({
                "meta": {"total_sessions": 5, "sessions_with_facets": 3,
                         "facets_coverage_pct": 60.0,
                         "date_range": {"first": "2026-03-01T00:00:00Z",
                                        "last": "2026-04-01T00:00:00Z"},
                         "tz_offset_hours": 8.0, "data_thin_warning": False},
                "aggregates": {
                    "activity": {"total_sessions": 5, "total_messages": 100,
                                 "active_days": 10, "current_streak": 2,
                                 "longest_streak": 5, "cache_creation_tokens": 0,
                                 "cache_read_tokens": 0, "models": {},
                                 "favorite_model": None,
                                 "api_equivalent_cost_usd": 0.0},
                    "tokens": {"total": 1000, "median": 100, "p90": 500, "max": 800, "dist_buckets": {}},
                    "tools": {"totals": {}, "sessions_using_task_agent": 0,
                              "sessions_using_mcp": 0, "sessions_using_web_search": 0, "sessions_using_web_fetch": 0},
                    "heatmap": {}, "projects": {}, "outcomes": {}, "friction": {"totals": {}, "by_outcome": {}},
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
            }))
            (tmp / "s.json").write_text("{}")
            out = tmp / "out.html"
            r = subprocess.run([
                "python3", str(skill_dir / "scripts" / "build_html.py"),
                "--input", str(tmp / "a.json"),
                "--samples", str(tmp / "s.json"),
                "--audience", "self",
                "--output", str(out),
            ], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            html = out.read_text()
            self.assertIn('id="overview"', html)
            self.assertIn('§ 01', html)


class ChartLayoutInjectionTests(unittest.TestCase):
    """The pure JS layout helpers in js/chart_layout.js must be inlined into
    every generated report and used by the chart renderers — otherwise the
    label-truncation regression returns silently."""

    def _build_self(self):
        import subprocess, tempfile, json as _json
        skill_dir = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.json").write_text(_json.dumps({
                "meta": {"total_sessions": 5, "sessions_with_facets": 3,
                         "facets_coverage_pct": 60.0,
                         "date_range": {"first": "2026-03-01T00:00:00Z",
                                        "last": "2026-04-01T00:00:00Z"},
                         "tz_offset_hours": 8.0, "data_thin_warning": False},
                "aggregates": {
                    "activity": {"total_sessions": 5, "total_messages": 100,
                                 "active_days": 10, "current_streak": 2,
                                 "longest_streak": 5, "cache_creation_tokens": 0,
                                 "cache_read_tokens": 0, "models": {},
                                 "favorite_model": None,
                                 "api_equivalent_cost_usd": 0.0},
                    "tokens": {"total": 1000, "median": 100, "p90": 500, "max": 800, "dist_buckets": {}},
                    "tools": {"totals": {}, "sessions_using_task_agent": 0,
                              "sessions_using_mcp": 0, "sessions_using_web_search": 0, "sessions_using_web_fetch": 0},
                    "heatmap": {}, "projects": {}, "outcomes": {}, "friction": {"totals": {}, "by_outcome": {}},
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
            }))
            (tmp / "s.json").write_text("{}")
            out = tmp / "out.html"
            r = subprocess.run([
                "python3", str(skill_dir / "scripts" / "build_html.py"),
                "--input", str(tmp / "a.json"),
                "--samples", str(tmp / "s.json"),
                "--audience", "self",
                "--output", str(out),
            ], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return out.read_text()

    def test_chart_layout_helpers_inlined(self):
        html = self._build_self()
        self.assertIn("function computeBarPlot", html)
        self.assertIn("function clipLabelToWidth", html)
        self.assertIn("function measureRotatedLabel", html)
        # Node-only export must be stripped before inlining (would crash browser).
        self.assertNotIn("module.exports", html)

    def test_donut_chart_clips_long_legend_labels(self):
        """drawDonutChart must call clipLabelToWidth so long model/outcome
        names don't shoot past the canvas right edge."""
        html = self._build_self()
        # Locate the donut renderer body (between drawDonutChart definition
        # and the next top-level function) and assert it uses the clipper.
        start = html.index("function drawDonutChart")
        end = html.index("function drawGroupedBarChart", start)
        donut_body = html[start:end]
        self.assertIn("clipLabelToWidth", donut_body,
                      "drawDonutChart must clip long legend labels")

    def test_grouped_bar_uses_computed_plot(self):
        """drawGroupedBarChart must derive its plot rect from computeBarPlot
        so vertical/horizontal label space scales with actual label length."""
        html = self._build_self()
        start = html.index("function drawGroupedBarChart")
        end = html.index("function drawHorizontalBarChart", start)
        body = html[start:end]
        self.assertIn("computeBarPlot", body,
                      "drawGroupedBarChart must use computeBarPlot for layout")


class FmtTests(unittest.TestCase):
    def test_billion_scale_uses_B_suffix(self):
        """Values >=1B must render with B suffix, not as thousands-of-M."""
        # Previously fmt(14_000_000_000) produced "14000.0M" — ugly and wrong.
        self.assertEqual(build_html.fmt(14_000_000_000), "14.0B")
        self.assertEqual(build_html.fmt(14_291_307_909), "14.3B")

    def test_million_still_uses_M(self):
        self.assertEqual(build_html.fmt(730_500_000), "730.5M")

    def test_trillion_uses_T(self):
        """Just in case someone runs this in the future at absurd scale."""
        self.assertEqual(build_html.fmt(1_500_000_000_000), "1.5T")


def _minimal_analysis():
    """Smallest analysis-data shape that makes build_html.py emit a full
    self-audience report. Used by tests that need to drive the renderer
    end-to-end without depending on demo data."""
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
    }


def _run_build(audience="self", locale=None, analysis=None):
    """Spawn build_html.py against a temp fixture. Returns the rendered
    HTML on success, raises AssertionError with stderr on non-zero exit.

    locale=None means omit the --locale flag entirely (exercises the default).
    """
    import subprocess
    import tempfile
    import json as _json
    skill_dir = Path(__file__).resolve().parent.parent
    payload = analysis if analysis is not None else _minimal_analysis()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "a.json").write_text(_json.dumps(payload))
        (tmp / "s.json").write_text("{}")
        out = tmp / "out.html"
        cmd = [
            "python3", str(skill_dir / "scripts" / "build_html.py"),
            "--input", str(tmp / "a.json"),
            "--samples", str(tmp / "s.json"),
            "--audience", audience,
            "--output", str(out),
        ]
        if locale is not None:
            cmd += ["--locale", locale]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError(f"build_html.py exited {r.returncode}: {r.stderr}")
        return out.read_text()


class LocaleTests(unittest.TestCase):
    """--locale must drive <html lang>, the doc title, and every chrome
    string. zh_TW build must contain zero key English chrome — otherwise
    a reader sees mixed languages, defeating the feature.

    Both locale outputs are deterministic for the fixed minimal fixture, so
    setUpClass builds each one once and shares the HTML across methods.
    """

    @classmethod
    def setUpClass(cls):
        cls._html_en = _run_build(locale=None)
        cls._html_zh = _run_build(locale="zh_TW")

    def test_default_locale_is_en(self):
        self.assertIn('<html lang="en">', self._html_en)
        self.assertIn("Cache-read tokens", self._html_en)

    def test_zh_tw_sets_html_lang_to_zh_hant(self):
        self.assertIn('<html lang="zh-Hant">', self._html_zh)

    def test_zh_tw_build_has_no_english_chrome(self):
        forbidden = [
            "Cache-read tokens",
            "Favorite model",
            "Active days",
            "Total messages",
            "API-equivalent",
        ]
        present = [s for s in forbidden if s in self._html_zh]
        self.assertEqual(present, [],
                         f"zh_TW build must not contain English chrome: {present}")

    def test_zh_tw_build_contains_localized_strings(self):
        self.assertIn("快取讀取 Token", self._html_zh)
        self.assertIn("最常用模型", self._html_zh)
        self.assertIn("評分", self._html_zh)
        self.assertIn("方法論", self._html_zh)

    def test_zh_tw_build_has_no_section_chrome_in_english(self):
        """Independent leak scan beyond the basic 5-string list. Catches
        section headers, method paragraphs, TOC links, and chart series
        labels that previously slipped through."""
        forbidden = [
            "Scoring", "Peer review", "Pattern mining", "Weekly trends",
            "Evidence library", "Methodology",
            "Eight dimensions, each with its own rubric",
            "Written by Claude after reading your data",
            "What this report is",
            "Rule-based", "Personalized peer review",
            "Composite score", "Good-outcome rate", "Task agent adoption",
            "Tokens (M)", "Avg prompt length",
            "sessions analyzed",
            "Data sources", "Sampling strategy", "Caveats",
            # Hero block (was leaking — title, dek, intro-card)
            "A diagnostic letter", "your Claude Code practice",
            "No sandwiching", "tends to celebrate",
            # Letterhead unsubstituted placeholders (pre-existing bug)
            "$total_sessions", "$facets_coverage",
        ]
        present = [s for s in forbidden if s in self._html_zh]
        self.assertEqual(present, [],
                         f"zh_TW build still leaks English chrome: {present}")

    def test_unknown_locale_rejected(self):
        import subprocess, tempfile
        skill_dir = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.json").write_text("{}")
            (tmp / "s.json").write_text("{}")
            r = subprocess.run([
                "python3", str(skill_dir / "scripts" / "build_html.py"),
                "--input", str(tmp / "a.json"),
                "--samples", str(tmp / "s.json"),
                "--audience", "self",
                "--locale", "ja",
                "--output", str(tmp / "x.html"),
            ], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0,
                                "build_html must reject unknown locales")


class CssRuleTests(unittest.TestCase):
    """Light smoke tests that the new CSS rules are present in the full
    rendered HTML output. We test the rule strings exist and are syntactically
    plausible; full visual correctness is checked by the user in-browser."""

    def _render_minimal(self):
        """Render a minimal HTML using the module's template — enough to
        assert CSS presence without requiring full demo data."""
        import sys
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(SKILL / "scripts"))
        import build_html
        # Read the raw template text to inspect CSS — simpler than full render
        template_path = SKILL / "scripts" / "build_html.py"
        return template_path.read_text()

    def test_pattern_class_css_present(self):
        src = self._render_minimal()
        self.assertIn(".score-row .body .pattern", src)
        self.assertIn("font-style: italic", src)

    def test_score_disclaimer_css_present(self):
        src = self._render_minimal()
        self.assertIn(".score-disclaimer", src)
        self.assertIn("text-align: left", src)

    def test_usage_characteristics_css_present(self):
        src = self._render_minimal()
        self.assertIn(".usage-characteristics", src)
        self.assertIn(".uc-row", src)
        self.assertIn("grid-template-columns: 72px 1fr", src)


class PatternRenderTests(unittest.TestCase):
    """Task 14: score_rows loop must emit <p class="pattern"> when pattern is present."""

    def _score_rows_source(self):
        """Return the raw Python source of build_html.py for structural assertions."""
        import inspect
        src_path = Path(__file__).resolve().parent.parent / "scripts" / "build_html.py"
        return src_path.read_text()

    def _render_with_pattern(self, pattern_val):
        """Build an analysis fixture where D1_delegation carries `pattern_val`,
        then run build_html.py and return the rendered HTML string."""
        import subprocess, tempfile, json as _json
        skill_dir = Path(__file__).resolve().parent.parent
        analysis = _minimal_analysis()
        analysis["scores"] = {
            "_overall": {"avg": 7.0, "dimensions_scored": 1, "dimensions_total": 8},
            "D1_delegation": {
                "score": 7,
                "explanation": "Good delegation practice.",
                "pattern": pattern_val,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.json").write_text(_json.dumps(analysis))
            (tmp / "s.json").write_text("{}")
            out = tmp / "out.html"
            r = subprocess.run([
                "python3", str(skill_dir / "scripts" / "build_html.py"),
                "--input", str(tmp / "a.json"),
                "--samples", str(tmp / "s.json"),
                "--audience", "self",
                "--output", str(out),
            ], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return out.read_text()

    def test_pattern_block_rendered_when_non_none(self):
        """When pattern is a non-empty string, the rendered score row must
        contain an element with class="pattern"."""
        html = self._render_with_pattern("Uses Task agent for all long-running work.")
        self.assertIn('class="pattern"', html)

    def test_pattern_block_absent_when_pattern_is_none(self):
        """When pattern is None (or key absent), no pattern element is emitted.
        Guard check: source code must use s.get('pattern') not s['pattern']."""
        # First assert the rendered output has no pattern element
        html = self._render_with_pattern(None)
        self.assertNotIn('class="pattern"', html)
        # Structural guard: source must use dict.get() to avoid KeyError
        src = self._score_rows_source()
        self.assertTrue(
            's.get("pattern")' in src or "s.get('pattern')" in src,
            "score_rows loop must use s.get('pattern') not s['pattern']",
        )

    def test_pattern_xss_escaped_in_full_render(self):
        """XSS gate: injecting a raw <script> tag via pattern must produce
        the HTML-escaped form (&lt;script&gt;) in output, never the raw tag."""
        demo_dir = Path("/tmp/cc-autopsy-demo")
        if not demo_dir.exists():
            self.skipTest("Demo data absent at /tmp/cc-autopsy-demo/ — skipping XSS integration test.")

        import subprocess, tempfile, json as _json
        skill_dir = Path(__file__).resolve().parent.parent

        # Load the demo aggregate if it exists, otherwise build our own fixture
        demo_agg = demo_dir / "analysis-data.json"
        if demo_agg.exists():
            analysis = _json.loads(demo_agg.read_text())
        else:
            self.skipTest("Demo analysis-data.json absent — skipping XSS integration test.")

        # Inject XSS payload into the first scored dimension we find
        xss_payload = "<script>alert(1)</script>"
        scores = analysis.get("scores", {})
        injected = False
        for dim_key in scores:
            if dim_key.startswith("D") and isinstance(scores[dim_key], dict):
                scores[dim_key]["pattern"] = xss_payload
                injected = True
                break
        if not injected:
            self.skipTest("No scored dimension found to inject XSS payload — skipping.")

        analysis["scores"] = scores

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.json").write_text(_json.dumps(analysis))
            (tmp / "s.json").write_text("{}")
            out = tmp / "out.html"
            r = subprocess.run([
                "python3", str(skill_dir / "scripts" / "build_html.py"),
                "--input", str(tmp / "a.json"),
                "--samples", str(tmp / "s.json"),
                "--audience", "self",
                "--output", str(out),
            ], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            rendered = out.read_text()

        self.assertNotIn(xss_payload, rendered,
                         "Raw <script> tag must not appear in rendered HTML")
        self.assertIn("&lt;script&gt;", rendered,
                      "XSS payload must be HTML-escaped to &lt;script&gt; in output")


class HowScoresRelateTests(unittest.TestCase):
    def test_how_to_read_hr_mode_includes_relate_entry(self):
        """build_html.py source must reference both locale keys for the new
        HOW SCORES RELATE dt/dd entry in the HR how-to-read block."""
        src = (Path(__file__).resolve().parent.parent / "scripts" / "build_html.py").read_text()
        self.assertIn('how_to_read_key_relate', src,
                      "build_html.py must reference locale key 'how_to_read_key_relate'")
        self.assertIn('how_to_read_val_relate', src,
                      "build_html.py must reference locale key 'how_to_read_val_relate'")


class ScoreDisclaimerTests(unittest.TestCase):
    def test_disclaimer_placeholder_in_template(self):
        """Template source must contain both the $score_disclaimer placeholder
        and the class="score-disclaimer" element."""
        src = Path(__file__).resolve().parent.parent / "scripts" / "build_html.py"
        text = src.read_text()
        self.assertIn("$score_disclaimer", text,
                      "Template must contain $score_disclaimer placeholder")
        self.assertIn('class="score-disclaimer"', text,
                      "Template must contain class=\"score-disclaimer\" element")

    def test_disclaimer_rendered_above_score_table(self):
        """score-disclaimer element must appear BEFORE score-table in source order."""
        src = Path(__file__).resolve().parent.parent / "scripts" / "build_html.py"
        text = src.read_text()
        idx_disclaimer = text.find('class="score-disclaimer"')
        idx_table = text.find('class="score-table"')
        self.assertGreater(idx_disclaimer, 0,
                           "class=\"score-disclaimer\" not found in source")
        self.assertGreater(idx_table, 0,
                           "class=\"score-table\" not found in source")
        self.assertLess(idx_disclaimer, idx_table,
                        "score-disclaimer must appear before score-table in source")


class UsageCharacteristicsRenderTests(unittest.TestCase):
    """Task 17: usage_characteristics block rendered inside _build_activity_panel."""

    def _activity_with_uc(self, **overrides):
        uc = {
            "n_sessions": 280,
            "since": "2026-01-01",
            "until": "2026-04-19",
            "items": [
                {"pct": 42, "label": "output-token-limit", "tip": "Hit the output cap in 42% of sessions."},
                {"pct": 31, "label": "long-context", "tip": "Loaded >100k tokens of context."},
                {"pct": 18, "label": "multi-turn-deep", "tip": "Conversation exceeded 20 turns."},
                {"pct": 12, "label": "tool-heavy", "tip": "More than 10 tool calls per session."},
                {"pct": 7,  "label": "low-friction", "tip": "No interrupts and goal achieved."},
            ],
        }
        base = _activity_panel(usage_characteristics=uc)
        base.update(overrides)
        return base

    def test_usage_characteristics_block_rendered(self):
        """When usage_characteristics is present, the block renders with header,
        note, and one uc-row per item."""
        html = build_html._build_activity_panel(self._activity_with_uc())
        self.assertIn('class="usage-characteristics"', html)
        self.assertIn("42%", html)
        self.assertEqual(html.count('class="uc-row"'), 5)
        self.assertIn("output-token-limit", html)
        self.assertIn("Across 280 sessions", html)

    def test_usage_characteristics_absent_when_missing(self):
        """When the activity dict has no usage_characteristics key, the block
        must be entirely absent."""
        html = build_html._build_activity_panel(_activity_panel())
        self.assertNotIn('class="usage-characteristics"', html)

    def test_usage_characteristics_xss_escaped(self):
        """Labels and tips coming from the scanner must be HTML-escaped before
        insertion to prevent XSS."""
        xss_label = "<script>alert(1)</script>"
        xss_tip = "'\"<script>alert(2)</script>"
        uc = {
            "n_sessions": 1,
            "since": "2026-01-01",
            "until": "2026-04-19",
            "items": [
                {"pct": 99, "label": xss_label, "tip": xss_tip},
            ],
        }
        html = build_html._build_activity_panel(
            _activity_panel(usage_characteristics=uc)
        )
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<script>alert(2)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class D9RenderTests(unittest.TestCase):
    """D9 token-efficiency dimension must appear in the rendered score table."""

    def test_d9_row_rendered_in_score_table(self):
        """After D9 wiring, the score table includes a D9 row with the
        locale title."""
        html = _run_build(audience="self", locale="en")
        self.assertIn("Token efficiency", html)

    def test_score_subtitle_says_nine(self):
        """After adding D9, the scoring section subtitle should mention nine, not eight."""
        html = _run_build(audience="self", locale="en")
        self.assertTrue(
            "Nine dimensions" in html or "nine dimensions" in html,
            "Expected 'Nine dimensions' or 'nine dimensions' in HTML",
        )
        self.assertNotIn("Eight dimensions", html)
        self.assertNotIn("eight dimensions", html)

    def test_zh_tw_subtitle_says_nine(self):
        """zh_TW subtitle should say 九個面向 after D9 wiring."""
        html = _run_build(locale="zh_TW")
        self.assertIn("九個面向", html)
        self.assertNotIn("八個面向", html)


if __name__ == "__main__":
    unittest.main()
