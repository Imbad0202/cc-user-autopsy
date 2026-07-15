"""TDD for direction-C rendering foundation: Exhibit frame, ledger narration
parser, and locale keys. See docs/superpowers/sdd/task-7-brief.md.

These are foundation-only tests — the section builders that call these
helpers land in a later task. Here we only verify the frame/parser
primitives and locale parity.
"""
import re
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import locales  # noqa: E402
from report_render import (  # noqa: E402
    _exhibit, _parse_ledger_narration,
    _build_opening_band, _build_output_ledger, _build_team_ledger,
    _build_leak_ledger)


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
        self.assertEqual(d, {"opening": "", "output-ledger": "", "team-ledger": "",
                             "leak-ledger": ""})

    def test_parses_leak_ledger_book(self):
        md = ("# opening\nOne sentence.\n"
              "# leak-ledger\nLeak claim.\n\nMore leak prose.\n")
        d = _parse_ledger_narration(md)
        self.assertTrue(d["leak-ledger"].startswith("Leak claim."))


class LedgerLocaleKeyTests(unittest.TestCase):
    REQUIRED = [
        "ledger_exhibit_label", "ledger_source_prefix", "ledger_opening_kicker",
        "ledger_output_title", "ledger_team_title", "ledger_source_card_full",
        "ledger_source_card_partial", "ledger_source_card_presence",
        "ledger_not_detected", "ledger_degraded_note",
        "ledger_common_window_note_template", "ledger_weekly_share_title",
        "ledger_parallel_title", "ledger_matrix_title", "ledger_h2h_title",
        "ledger_parse_errors_template",
        # --- Phase 2: leak ledger + blind spots ---
        "ledger_leaks_title", "ledger_leaks_kicker", "ledger_blindspot_label",
        "blindspot_repeated_title", "blindspot_repeated_template",
        "blindspot_sunk_title", "blindspot_sunk_template",
        "blindspot_switch_title", "blindspot_switch_template",
        "blindspot_graveyard_title", "blindspot_graveyard_template",
        "blindspot_askship_title", "blindspot_askship_template",
        "blindspot_interrupt_title", "blindspot_interrupt_template",
        "ledger_leak_weekly_cost_template", "ledger_leak_tokens_template",
        "ledger_leak_occurrences_template", "ledger_leak_fix_label",
        "leak_type_repeated_instructions", "leak_type_sunk_cost",
        "leak_type_failed_session_burn",
        "leak_fix_repeated_instructions", "leak_fix_repeated_instructions_cross",
        "leak_fix_sunk_cost", "leak_fix_failed_session_burn",
        "ledger_graveyard_exhibit_title", "ledger_graveyard_untouched_template",
        "ledger_graveyard_writes_template", "ledger_leaks_exhibit_title",
        "ledger_secondary_findings", "ledger_source_graveyard",
        "ledger_source_leaks",
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
    "parallel": {"heatmap": [[3 if (wd, hr) == (2, 14) else 0 for hr in range(24)]
                             for wd in range(7)],
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
        "team-ledger": "Codex took the long jobs.\n\nMore prose.",
        "leak-ledger": "The repeated-instruction tax is your biggest leak.\n\nDetail."}

# --- Phase 2 fixtures: blind spots + leak ledger ---

BS_ALL_PASSED = {
    "schema_version": 1,
    "repeated_instructions": {
        "id": "repeated_instructions", "gate_passed": True,
        "suppressed_by_guard": False, "n": 1,
        "metrics": {"patterns": [{
            "exemplar": "run the tests <script>alert(1)</script>",
            "occurrences": 7, "weeks": 4, "sources": ["claude", "codex"],
            "est_wasted_tokens": 900,
            "evidence": ["sid-1", "sid-2", "sid-3"]}]},
        "reason": None},
    "sunk_cost": {
        "id": "sunk_cost", "gate_passed": True, "suppressed_by_guard": False,
        "n": 3, "metrics": {"pairs": [], "accel_rate_not_achieved": 0.5,
                            "accel_rate_fully_achieved": 0.1}, "reason": None},
    "switch_tax": {
        "id": "switch_tax", "gate_passed": True, "suppressed_by_guard": False,
        "n": 60,
        "metrics": {"multi": {"n": 25, "good_rate": 55.0,
                              "friction_per_session": 1.2,
                              "interrupts_per_session": 0.3},
                    "single": {"n": 35, "good_rate": 78.0,
                              "friction_per_session": 0.4,
                              "interrupts_per_session": 0.1}},
        "reason": None},
    "graveyard": {
        "id": "graveyard", "gate_passed": True, "suppressed_by_guard": False,
        "n": 2,
        "metrics": {"items": [
            {"project_key": "old-webapp", "last_active_date": "2026-05-01",
             "days_untouched": 40, "writes": 12, "evidence": ["sid-9"]},
            {"project_key": "side-project", "last_active_date": "2026-05-15",
             "days_untouched": 26, "writes": 6, "evidence": ["sid-10"]},
        ]},
        "reason": None},
    "habit_drift": {"id": "habit_drift", "gate_passed": False,
                    "suppressed_by_guard": False, "n": 0, "metrics": {},
                    "reason": "fewer than 8 weeks"},
    "ask_vs_ship": {
        "id": "ask_vs_ship", "gate_passed": True, "suppressed_by_guard": False,
        "n": 40,
        "metrics": {"top_gap": {"category": "refactoring", "ask_share_pct": 30.0,
                                "ship_share_pct": 8.0, "gap_pp": 22.0},
                    "shipped_sessions": 14},
        "reason": None},
    "interrupt_win_rate": {
        "id": "interrupt_win_rate", "gate_passed": True,
        "suppressed_by_guard": False, "n": 12,
        "metrics": {"interrupted": {"n": 12, "good_rate": 40.0},
                    "baseline": {"n": 30, "good_rate": 70.0},
                    "delta_pp": -30.0},
        "reason": None},
}

BS_ALL_FAILED = {
    "schema_version": 1,
    "repeated_instructions": {"id": "repeated_instructions", "gate_passed": False,
                              "suppressed_by_guard": False, "n": 0, "metrics": {},
                              "reason": "no pattern"},
    "sunk_cost": {"id": "sunk_cost", "gate_passed": False,
                 "suppressed_by_guard": False, "n": 0, "metrics": {},
                 "reason": "fewer than 3 confirmed pairs"},
    "switch_tax": {"id": "switch_tax", "gate_passed": False,
                  "suppressed_by_guard": False, "n": 0, "metrics": {},
                  "reason": "no multi-source windows"},
    "graveyard": {"id": "graveyard", "gate_passed": False,
                 "suppressed_by_guard": False, "n": 0, "metrics": {},
                 "reason": "fewer than 2 qualifying items"},
    "habit_drift": {"id": "habit_drift", "gate_passed": False,
                    "suppressed_by_guard": False, "n": 0, "metrics": {},
                    "reason": "fewer than 8 weeks"},
    "ask_vs_ship": {"id": "ask_vs_ship", "gate_passed": False,
                    "suppressed_by_guard": False, "n": 0, "metrics": {},
                    "reason": "fewer than 20 scored sessions"},
    "interrupt_win_rate": {"id": "interrupt_win_rate", "gate_passed": False,
                           "suppressed_by_guard": False, "n": 0, "metrics": {},
                           "reason": "fewer than 5 sessions in a bucket"},
}

LEDGER_LEAKS = dict(LEDGER, leaks={
    "window_weeks": 7.1,
    "items": [
        {"type": "repeated_instructions", "weekly_cost_usd": 4.32,
         "weekly_tokens": 12000, "occurrences": 7, "evidence": ["sid-1"],
         "sources": ["claude"]},
        {"type": "sunk_cost", "weekly_cost_usd": 2.10,
         "weekly_tokens": 5000, "occurrences": 3, "evidence": ["sid-4"]},
        {"type": "failed_session_burn", "weekly_cost_usd": 1.05,
         "weekly_tokens": 3000, "occurrences": 5, "evidence": ["sid-7"]},
    ],
})

LEDGER_LEAKS_CROSS_SOURCE = dict(LEDGER, leaks={
    "window_weeks": 7.1,
    "items": [
        {"type": "repeated_instructions", "weekly_cost_usd": 4.32,
         "weekly_tokens": 12000, "occurrences": 7, "evidence": ["sid-1"],
         "sources": ["claude", "codex"]},
    ],
})

LEDGER_NO_LEAKS = dict(LEDGER, leaks={"window_weeks": 7.1, "items": []})


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

    def test_healthy_window_renders_heatmap_and_matrix_exhibits(self):
        # CROSS has a non-degraded common_window plus non-empty parallel
        # heatmap and project_matrix data — both exhibits must render.
        html = _build_team_ledger(CROSS, NARR, "en")
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["ledger_parallel_title"], html)
        self.assertIn(STRINGS["en"]["ledger_matrix_title"], html)

    def test_degraded_window_drops_comparisons(self):
        degraded = dict(CROSS, common_window={"start": "2026-06-10",
                                              "end": "2026-06-18",
                                              "days": 8, "degraded": True})
        html = _build_team_ledger(degraded, NARR, "en")
        self.assertNotIn("2026-W20", html)   # no weekly comparison exhibit
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["ledger_degraded_note"], html)
        # Per-source fallback only: heatmap and project x tool matrix
        # exhibits must NOT render when the window is degraded — those are
        # cross-source comparisons the source cards + degraded note already
        # cover per-source.
        self.assertNotIn(STRINGS["en"]["ledger_parallel_title"], html)
        self.assertNotIn(STRINGS["en"]["ledger_matrix_title"], html)

    def test_absent_window_drops_comparisons(self):
        no_window = dict(CROSS, common_window=None)
        html = _build_team_ledger(no_window, NARR, "en")
        from scripts.locales import STRINGS
        self.assertNotIn(STRINGS["en"]["ledger_parallel_title"], html)
        self.assertNotIn(STRINGS["en"]["ledger_matrix_title"], html)

    def test_never_prints_prompt_text(self):
        cross = dict(CROSS)
        cross["sources"] = CROSS["sources"] + [
            {"source": "grok", "coverage": "partial", "session_count": 3,
             "first_date": "2026-06-01", "last_date": "2026-06-05",
             "total_input_tokens": None, "total_output_tokens": None,
             "parse_errors": 0}]
        html = _build_team_ledger(cross, NARR, "en")
        self.assertNotIn("GROK_PRIVATE_MARKER", html)

    def test_source_card_shows_parse_errors_when_present(self):
        cross = dict(CROSS)
        cross["sources"] = [
            dict(CROSS["sources"][0], detected=True),
            dict(CROSS["sources"][1], detected=True, parse_errors=2),
        ]
        html = _build_team_ledger(cross, NARR, "en")
        from scripts.locales import STRINGS
        expected = STRINGS["en"]["ledger_parse_errors_template"].format(n=2)
        self.assertIn(expected, html)

    def test_source_card_hides_parse_errors_when_zero(self):
        cross = dict(CROSS)
        cross["sources"] = [
            dict(CROSS["sources"][0], detected=True, parse_errors=0),
            dict(CROSS["sources"][1], detected=True, parse_errors=0),
        ]
        html = _build_team_ledger(cross, NARR, "en")
        from scripts.locales import STRINGS
        # Template with n=0 must not appear anywhere in the rendered output.
        unexpected = STRINGS["en"]["ledger_parse_errors_template"].format(n=0)
        self.assertNotIn(unexpected, html)

    def test_not_detected_source_card_shows_label_not_counts(self):
        cross = dict(CROSS)
        undetected = {"source": "grok", "coverage": None, "session_count": 0,
                     "first_date": None, "last_date": None,
                     "total_input_tokens": None, "total_output_tokens": None,
                     "parse_errors": 0, "detected": False}
        cross["sources"] = [
            dict(s, detected=True) for s in CROSS["sources"]
        ] + [undetected]
        html = _build_team_ledger(cross, NARR, "en")
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["ledger_not_detected"], html)
        self.assertIn("grok", html.lower())

    def test_not_detected_source_card_with_parse_errors_shows_error_line(self):
        # A source whose EVERY line was malformed shows "not detected"
        # (session_count 0) but parse_errors > 0 — the reader needs a hint
        # that something WAS there but failed to parse, not just silence.
        cross = dict(CROSS)
        undetected_with_errors = {
            "source": "grok", "coverage": None, "session_count": 0,
            "first_date": None, "last_date": None,
            "total_input_tokens": None, "total_output_tokens": None,
            "parse_errors": 5, "detected": False,
        }
        cross["sources"] = [
            dict(s, detected=True) for s in CROSS["sources"]
        ] + [undetected_with_errors]
        html = _build_team_ledger(cross, NARR, "en")
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["ledger_not_detected"], html)
        expected = STRINGS["en"]["ledger_parse_errors_template"].format(n=5)
        self.assertIn(expected, html)

    def test_unattributed_parse_errors_note_renders_when_set(self):
        cross = dict(CROSS, unattributed_parse_errors=3)
        html = _build_team_ledger(cross, NARR, "en")
        from scripts.locales import STRINGS
        expected = STRINGS["en"]["ledger_unknown_parse_errors_template"].format(n=3)
        self.assertIn(expected, html)

    def test_unattributed_parse_errors_note_absent_when_zero(self):
        cross = dict(CROSS, unattributed_parse_errors=0)
        html = _build_team_ledger(cross, NARR, "en")
        from scripts.locales import STRINGS
        unexpected = STRINGS["en"]["ledger_unknown_parse_errors_template"].format(n=0)
        self.assertNotIn(unexpected, html)

    def test_unattributed_parse_errors_note_absent_when_missing_key(self):
        # cross_llm blocks from before this field existed lack the key
        # entirely — must not raise and must not render the note.
        cross = dict(CROSS)
        cross.pop("unattributed_parse_errors", None)
        html = _build_team_ledger(cross, NARR, "en")
        from scripts.locales import STRINGS
        unexpected_zero = STRINGS["en"]["ledger_unknown_parse_errors_template"].format(n=0)
        self.assertNotIn(unexpected_zero, html)


class LeakLedgerRenderTests(unittest.TestCase):
    def test_gate_passing_renders_section_with_exemplar_cost_fix_and_secondary(self):
        from itertools import count
        html = _build_leak_ledger(LEDGER_LEAKS, BS_ALL_PASSED, NARR, "en", count(1))
        self.assertIn('id="ledger-leaks"', html)
        # XSS marker in the repeated-instruction exemplar must be escaped.
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("c-leak-cost", html)
        self.assertIn("4.32", html)  # formatted weekly cost
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["ledger_leak_fix_label"], html)
        self.assertIn(STRINGS["en"]["leak_fix_repeated_instructions"], html)
        # secondary findings (#6 ask-vs-ship, #7 interrupt win-rate)
        self.assertIn(STRINGS["en"]["ledger_secondary_findings"], html)
        self.assertIn("refactoring", html)

    def test_cross_source_repeated_instructions_uses_cross_fix_text(self):
        # Fix 5: when the repeated_instructions leak item's sources include
        # a non-Claude tool, CLAUDE.md-only advice is wrong (Codex/Grok
        # don't read it) — the cross-tool fix key must render instead, and
        # the CLAUDE.md-only text must NOT appear.
        from itertools import count
        html = _build_leak_ledger(LEDGER_LEAKS_CROSS_SOURCE, BS_ALL_PASSED,
                                  NARR, "en", count(1))
        from scripts.locales import STRINGS
        from scripts.report_render import esc
        self.assertIn(esc(STRINGS["en"]["leak_fix_repeated_instructions_cross"]), html)
        self.assertNotIn(esc(STRINGS["en"]["leak_fix_repeated_instructions"]), html)

    def test_claude_only_repeated_instructions_uses_claude_md_fix_text(self):
        from itertools import count
        html = _build_leak_ledger(LEDGER_LEAKS, BS_ALL_PASSED, NARR, "en", count(1))
        from scripts.locales import STRINGS
        from scripts.report_render import esc
        self.assertIn(esc(STRINGS["en"]["leak_fix_repeated_instructions"]), html)
        self.assertNotIn(esc(STRINGS["en"]["leak_fix_repeated_instructions_cross"]), html)

    def test_all_gates_failed_and_no_leak_items_suppresses_whole_section(self):
        from itertools import count
        html = _build_leak_ledger(LEDGER_NO_LEAKS, BS_ALL_FAILED, NARR, "en", count(1))
        self.assertEqual(html, "")
        self.assertNotIn('id="ledger-leaks"', html)

    def test_leak_items_alone_render_even_without_opener_gates(self):
        # Uses a leaks fixture with NO sunk_cost item (only
        # repeated_instructions + failed_session_burn) so the sunk-cost
        # opener — which since Fix 2 renders off leaks.items rather than
        # bs2.gate_passed — stays legitimately silent here; this isolates
        # "leak cards render independent of the repeated_instructions (bs1)
        # opener gate" from the sunk-cost item-presence behavior covered by
        # test_sunk_cost_item_present_renders_section_and_opener_with_item_occurrences.
        from itertools import count
        ledger_no_sunk_item = dict(LEDGER, leaks={
            "window_weeks": 7.1,
            "items": [it for it in LEDGER_LEAKS["leaks"]["items"]
                      if it["type"] != "sunk_cost"],
        })
        bs = dict(BS_ALL_FAILED)
        html = _build_leak_ledger(ledger_no_sunk_item, bs, NARR, "en", count(1))
        self.assertIn('id="ledger-leaks"', html)
        self.assertNotIn("c-blindspot", html)

    def test_opener_gate_alone_renders_even_without_leak_items(self):
        from itertools import count
        bs = dict(BS_ALL_FAILED, repeated_instructions=BS_ALL_PASSED["repeated_instructions"])
        html = _build_leak_ledger(LEDGER_NO_LEAKS, bs, NARR, "en", count(1))
        self.assertIn('id="ledger-leaks"', html)
        self.assertIn("c-blindspot", html)

    def test_only_secondary_finding_gate_still_renders_section(self):
        # Neither leaks items, bs1 (repeated_instructions), nor bs2
        # (sunk_cost) pass — only ask_vs_ship (#6, a secondary finding)
        # does. The section must still render (secondary findings live
        # inside the leak ledger body per spec) with the secondary-findings
        # block but no leak cards exhibit and no opener callouts.
        from itertools import count
        bs = dict(BS_ALL_FAILED, ask_vs_ship=BS_ALL_PASSED["ask_vs_ship"])
        html = _build_leak_ledger(LEDGER_NO_LEAKS, bs, NARR, "en", count(1))
        self.assertIn('id="ledger-leaks"', html)
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["ledger_secondary_findings"], html)
        self.assertIn("refactoring", html)
        self.assertNotIn("c-blindspot", html)
        self.assertNotIn("c-leak-cards", html)

    def test_only_interrupt_win_rate_gate_still_renders_section(self):
        from itertools import count
        bs = dict(BS_ALL_FAILED, interrupt_win_rate=BS_ALL_PASSED["interrupt_win_rate"])
        html = _build_leak_ledger(LEDGER_NO_LEAKS, bs, NARR, "en", count(1))
        self.assertIn('id="ledger-leaks"', html)
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["ledger_secondary_findings"], html)
        self.assertNotIn("c-blindspot", html)
        self.assertNotIn("c-leak-cards", html)

    def test_ask_ship_known_category_localizes_in_zh_tw(self):
        # Codex round 16: raw facet keys (snake_case identifiers) must not
        # leak into the report — known categories map to locale labels.
        from itertools import count
        bs = dict(BS_ALL_FAILED, ask_vs_ship=dict(
            BS_ALL_PASSED["ask_vs_ship"],
            metrics={"top_gap": {"category": "feature_implementation",
                                 "ask_share_pct": 30.0, "ship_share_pct": 8.0,
                                 "gap_pp": 22.0},
                     "shipped_sessions": 14}))
        html = _build_leak_ledger(LEDGER_NO_LEAKS, bs, NARR, "zh_TW", count(1))
        self.assertIn("功能實作", html)
        self.assertNotIn("feature_implementation", html)

    def test_ask_ship_unknown_category_falls_back_de_underscored(self):
        from itertools import count
        bs = dict(BS_ALL_FAILED, ask_vs_ship=dict(
            BS_ALL_PASSED["ask_vs_ship"],
            metrics={"top_gap": {"category": "schema_wrangling",
                                 "ask_share_pct": 30.0, "ship_share_pct": 8.0,
                                 "gap_pp": 22.0},
                     "shipped_sessions": 14}))
        html = _build_leak_ledger(LEDGER_NO_LEAKS, bs, NARR, "en", count(1))
        self.assertIn("schema wrangling", html)
        self.assertNotIn("schema_wrangling", html)

    def test_all_gates_failed_still_suppresses_with_ask_ship_and_interrupt_off(self):
        # Regression guard: BS_ALL_FAILED (nothing passes anything, leaks
        # empty) must still yield no section — existing suppression case.
        from itertools import count
        html = _build_leak_ledger(LEDGER_NO_LEAKS, BS_ALL_FAILED, NARR, "en", count(1))
        self.assertEqual(html, "")

    def test_sunk_cost_gate_passed_but_no_in_window_item_suppresses_section(self):
        # Codex round 8 Fix 2: bs2 (sunk_cost) may pass its gate entirely on
        # pairs OUTSIDE the ledger window — compute_leaks then emits no
        # sunk_cost item. gate_passed=True must NOT be enough on its own:
        # with leaks.items empty and bs1/bs6/bs7 all failed too, there is no
        # in-window support for anything, so the whole section must be
        # suppressed (no ledger-leaks section at all).
        from itertools import count
        bs = dict(BS_ALL_FAILED, sunk_cost=BS_ALL_PASSED["sunk_cost"])
        html = _build_leak_ledger(LEDGER_NO_LEAKS, bs, NARR, "en", count(1))
        self.assertEqual(html, "")
        self.assertNotIn('id="ledger-leaks"', html)

    def test_sunk_cost_item_present_renders_section_and_opener_with_item_occurrences(self):
        # Codex round 8 Fix 2: when a sunk_cost item DOES exist in
        # leaks.items (in-window support confirmed), the section renders
        # and the sunk-cost opener shows the ITEM's occurrence count (the
        # in-window failed-session count), not bs2["n"] (the all-time
        # confirmed-pair count) — LEDGER_LEAKS' sunk_cost item has
        # occurrences=3 while BS_ALL_PASSED's sunk_cost.n is also 3, so use
        # a deliberately different n to prove the item count wins.
        from itertools import count
        bs = dict(BS_ALL_PASSED,
                  sunk_cost=dict(BS_ALL_PASSED["sunk_cost"], n=99))
        html = _build_leak_ledger(LEDGER_LEAKS, bs, NARR, "en", count(1))
        self.assertIn('id="ledger-leaks"', html)
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["blindspot_sunk_title"], html)
        expected = STRINGS["en"]["blindspot_sunk_template"].format(n=3)
        self.assertIn(expected, html)
        not_expected = STRINGS["en"]["blindspot_sunk_template"].format(n=99)
        self.assertNotIn(not_expected, html)


class GraveyardOpenerTests(unittest.TestCase):
    def test_gate_passing_shows_callout_and_exhibit_rows(self):
        from itertools import count
        html = _build_output_ledger(LEDGER, NARR, "en", count(1), BS_ALL_PASSED)
        self.assertIn("c-blindspot", html)
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["blindspot_graveyard_title"], html)
        self.assertIn("old-webapp", html)
        self.assertIn("side-project", html)

    def test_gate_failed_no_callout(self):
        from itertools import count
        html = _build_output_ledger(LEDGER, NARR, "en", count(1), BS_ALL_FAILED)
        self.assertNotIn("c-blindspot", html)
        from scripts.locales import STRINGS
        self.assertNotIn(STRINGS["en"]["blindspot_graveyard_title"], html)

    def test_graveyard_opens_before_output_metrics_exhibit(self):
        # Fix 5: every book opens with its blind spot — the graveyard
        # callout must render BEFORE the output-metrics exhibit, so its
        # exhibit takes the earlier position/number.
        from itertools import count
        from scripts.locales import STRINGS
        html = _build_output_ledger(LEDGER, NARR, "en", count(1), BS_ALL_PASSED)
        callout_pos = html.index(STRINGS["en"]["blindspot_graveyard_title"])
        metrics_pos = html.index(STRINGS["en"]["ledger_output_commits"])
        self.assertLess(callout_pos, metrics_pos)


class SwitchTaxOpenerTests(unittest.TestCase):
    def test_gate_passing_shows_callout_with_negative_class_on_worse_rate(self):
        from itertools import count
        html = _build_team_ledger(CROSS, NARR, "en", count(2), BS_ALL_PASSED)
        self.assertIn("c-blindspot", html)
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["blindspot_switch_title"], html)
        # multi (55.0) < single (78.0) => multi rate wrapped in negative class
        self.assertIn("c-neg-num", html)
        self.assertIn("55.0", html)
        self.assertIn("78.0", html)

    def test_gate_failed_no_callout(self):
        from itertools import count
        html = _build_team_ledger(CROSS, NARR, "en", count(2), BS_ALL_FAILED)
        self.assertNotIn("c-blindspot", html)

    def test_degraded_window_suppresses_callout_even_when_gate_passed(self):
        # Fix 2: switch_tax gate passing is not enough — the callout is
        # itself a cross-source comparison, so it must not render next to
        # the degraded note that tells the reader cross-source comparisons
        # were suppressed.
        from itertools import count
        degraded = dict(CROSS, common_window={"start": "2026-06-10",
                                              "end": "2026-06-18",
                                              "days": 8, "degraded": True})
        html = _build_team_ledger(degraded, NARR, "en", count(2), BS_ALL_PASSED)
        self.assertNotIn("c-blindspot", html)
        from scripts.locales import STRINGS
        self.assertNotIn(STRINGS["en"]["blindspot_switch_title"], html)
        self.assertIn(STRINGS["en"]["ledger_degraded_note"], html)

    def test_healthy_window_still_shows_callout(self):
        # Existing behavior preserved: CROSS's common_window is healthy, so
        # a gate-passing switch_tax still renders the callout.
        from itertools import count
        html = _build_team_ledger(CROSS, NARR, "en", count(2), BS_ALL_PASSED)
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["blindspot_switch_title"], html)


class ExhibitNumberingTests(unittest.TestCase):
    def test_exhibits_are_strictly_consecutive_from_one_in_document_order(self):
        from itertools import count
        exhibit_no = count(1)
        html = (_build_output_ledger(LEDGER, NARR, "en", exhibit_no, BS_ALL_PASSED)
                + _build_team_ledger(CROSS, NARR, "en", exhibit_no, BS_ALL_PASSED)
                + _build_leak_ledger(LEDGER_LEAKS, BS_ALL_PASSED, NARR, "en", exhibit_no))
        nums = [int(n) for n in re.findall(r"EXHIBIT\s+(\d+)", html)]
        self.assertEqual(nums, list(range(1, len(nums) + 1)))
        self.assertGreaterEqual(len(nums), 4)  # output(1) + team(>=2) + leak(1)


class NarrationLeakBookTests(unittest.TestCase):
    def test_first_line_becomes_h2_and_opening_band_finding(self):
        from itertools import count
        leak_html = _build_leak_ledger(LEDGER_LEAKS, BS_ALL_PASSED, NARR, "en", count(1))
        self.assertIn("The repeated-instruction tax is your biggest leak", leak_html)
        band_html = _build_opening_band(LEDGER, NARR, "en")
        self.assertIn("The repeated-instruction tax is your biggest leak", band_html)
        # third finding number
        self.assertIn('<div class="c-finding-no">3</div>', band_html)

    def test_missing_book_falls_back_to_locale_title_no_fabricated_prose(self):
        from itertools import count
        narr = dict(NARR, **{"leak-ledger": ""})
        html = _build_leak_ledger(LEDGER_LEAKS, BS_ALL_PASSED, narr, "en", count(1))
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["ledger_leaks_title"], html)
        self.assertNotIn("None", html)
        band_html = _build_opening_band(LEDGER, narr, "en")
        # no third finding when the leak-ledger book is empty
        self.assertNotIn('<div class="c-finding-no">3</div>', band_html)


class OpeningBandLeakGateEndToEndTests(unittest.TestCase):
    """Fix 5: narration containing all four books (opening/output/team/leak)
    must not let the opening band claim a leak finding when the leak
    section itself doesn't render (no leak data passed a blind-spot gate)."""

    def test_no_leak_data_yields_two_findings_and_no_leak_section(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html = _run_build_with_ledger(
                "self", tmp_path, ledger=LEDGER, blind_spots={})
        self.assertNotIn('id="ledger-leaks"', html)
        self.assertIn('<div class="c-finding-no">1</div>', html)
        self.assertIn('<div class="c-finding-no">2</div>', html)
        self.assertNotIn('<div class="c-finding-no">3</div>', html)
        self.assertNotIn(NARR["leak-ledger"].splitlines()[0], html)

    def test_leak_data_present_yields_three_findings_and_leak_section(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html = _run_build_with_ledger(
                "self", tmp_path, ledger=LEDGER_LEAKS, blind_spots=BS_ALL_PASSED)
        self.assertIn('id="ledger-leaks"', html)
        self.assertIn('<div class="c-finding-no">1</div>', html)
        self.assertIn('<div class="c-finding-no">2</div>', html)
        self.assertIn('<div class="c-finding-no">3</div>', html)
        self.assertIn(NARR["leak-ledger"].splitlines()[0], html)


class HRAbsenceTests(unittest.TestCase):
    def test_hr_render_has_no_leak_or_blindspot_or_graveyard_markers(self):
        # Static CSS rules for .c-blindspot etc. are always present in the
        # stylesheet (same as LedgerAudienceGateTests' .c-exhibit check), so
        # assert on the rendered element (class="c-blindspot") rather than
        # the bare class-name substring, and on locale prose that only a
        # rendered callout/exhibit would introduce.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html_hr = _run_build_with_ledger(
                "hr", tmp_path, ledger=LEDGER_LEAKS, blind_spots=BS_ALL_PASSED)
        self.assertNotIn('id="ledger-leaks"', html_hr)
        self.assertNotIn('class="c-blindspot"', html_hr)
        from scripts.locales import STRINGS
        self.assertNotIn(STRINGS["en"]["blindspot_graveyard_title"], html_hr)
        self.assertNotIn("old-webapp", html_hr)

    def test_self_render_has_leak_and_blindspot_markers(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            html_self = _run_build_with_ledger(
                "self", tmp_path, ledger=LEDGER_LEAKS, blind_spots=BS_ALL_PASSED)
        self.assertIn('id="ledger-leaks"', html_self)
        self.assertIn('class="c-blindspot"', html_self)


def _minimal_ledger_analysis(ledger=None, blind_spots=None):
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
        "ledger": ledger if ledger is not None else LEDGER,
        "cross_llm": CROSS,
        "blind_spots": blind_spots if blind_spots is not None else {},
    }


def _run_build_with_ledger(audience, tmp_path, ledger=None, blind_spots=None):
    """Drive build_html.py as a subprocess (same pattern as
    test_build_html_additions._run_build) with --ledger-narration wired in."""
    import subprocess
    import json as _json
    (tmp_path / "a.json").write_text(
        _json.dumps(_minimal_ledger_analysis(ledger=ledger, blind_spots=blind_spots)))
    (tmp_path / "s.json").write_text("{}")
    narr_md = (
        "# opening\n" + NARR["opening"] + "\n"
        "# output-ledger\n" + NARR["output-ledger"] + "\n"
        "# team-ledger\n" + NARR["team-ledger"] + "\n"
        "# leak-ledger\n" + NARR["leak-ledger"] + "\n"
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
