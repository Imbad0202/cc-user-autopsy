"""Origin classification: was a session driven by hand, launched by
another tool, or impossible to tell (scripts/origin.py)."""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts.cross_llm_common import cli_launch_targets  # noqa: E402
from scripts.origin import (  # noqa: E402
    COVERAGE_GAP_DAYS, LAUNCH_WINDOW_SECONDS, classify_all, count_by_source,
    launcher_coverage)

BOTH = {"claude", "codex"}  # both launcher tools were scanned
DAY = 86400


def row(source, sid, start, *, end=None, multi_turn=False, launches=(),
        scanned=True, until=None, **extra):
    r = {"source": source, "session_id": sid, "start_time": start,
         "segments": [[start, end or start]], "multi_turn": multi_turn,
         "coverage": "partial" if source == "grok" else "full", **extra}
    if scanned:
        r["cli_launches"] = [{"target": t, "ts": ts, "until": until}
                             for t, ts in launches]
    return r


T0 = "2026-04-01T10:00:00+00:00"


def at(seconds):
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(T0) + timedelta(seconds=seconds)).isoformat()


# A long hand-driven Claude session whose transcript spans every test
# timestamp, so "a launch would have been visible" holds unless a test
# removes it.
CLAUDE_SPAN = row("claude", "span", at(-3600), end=at(7200), multi_turn=True)


class LaunchCommandTests(unittest.TestCase):
    def test_any_wrapper_around_the_cli_is_caught(self):
        # Recall over precision: a missed launch would make the session it
        # started read as hand-driven. origin.py's time window is what
        # keeps a stray mention from mattering.
        for cmd in ('codex exec "x"',
                    "cd /a && FOO=1 timeout 600 codex review",
                    "nohup codex exec x &", "time codex review",
                    "/opt/homebrew/bin/codex exec x", "npx codex exec x",
                    "env FOO=1 codex exec x", "timeout -k 5 600 codex review",
                    "bash -lc 'codex exec x'", "if codex review; then :; fi",
                    "{ codex exec x; }", "xargs codex exec",
                    'FOO="a b" codex exec x', "echo `codex exec x`"):
            self.assertEqual(cli_launch_targets(cmd), ["codex"], cmd)
        self.assertEqual(
            cli_launch_targets("~/.local/bin/claude -p hi"), ["claude"])
        self.assertEqual(cli_launch_targets("codex.exe exec x"), ["codex"])

    def test_names_inside_a_longer_word_or_path_do_not_match(self):
        for cmd in ("cat ./codex-notes.md", "ls ~/.codex/sessions",
                    "cat ~/.claude/settings.json", "pip install codex_tools",
                    "open https://claude.ai/x", "cd codex/src && ls",
                    "echo Codex", "vim grok.md"):
            self.assertEqual(cli_launch_targets(cmd), [], cmd)

    def test_every_cli_named_is_reported_once_in_order(self):
        self.assertEqual(cli_launch_targets("claude -p x; grok -p y; claude -p z"),
                         ["claude", "grok"])

    def test_non_string_command(self):
        self.assertEqual(cli_launch_targets(None), [])
        self.assertEqual(cli_launch_targets(["codex"]), [])


def classify_all_both(rows):
    return classify_all(rows, BOTH)


class ClassifyTests(unittest.TestCase):
    def origin(self, rows, key, scanned=BOTH):
        return classify_all(rows, scanned)[key]

    def test_spawned_header_marks_launched(self):
        rows = [CLAUDE_SPAN,
                row("codex", "c1", at(0), multi_turn=True,
                    launch_source="subagent")]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_non_interactive_header_alone_is_unknown_never_direct(self):
        # A one-shot exec run with no launching call in sight: nobody sat
        # in it, but who started it cannot be told — even though Claude's
        # transcripts span the moment and it would otherwise be "direct".
        rows = [CLAUDE_SPAN,
                row("codex", "c1", at(0), launch_source="Exec"),
                row("codex", "c2", at(0), launch_source="exec", multi_turn=True),
                row("codex", "c3", at(0), launch_source="mcp")]
        got = classify_all(rows, BOTH)
        self.assertEqual(
            [got[f"codex:c{i}"] for i in (1, 2, 3)], ["unknown"] * 3)

    def test_non_interactive_header_with_a_matching_call_is_launched(self):
        launcher = row("claude", "a", at(-600), end=at(600), multi_turn=True,
                       launches=[("codex", at(0))])
        rows = [launcher, row("codex", "c1", at(5), launch_source="exec")]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_interactive_header_values_do_not_block_direct(self):
        rows = [CLAUDE_SPAN,
                row("codex", "c1", at(0), launch_source="cli"),
                row("codex", "c2", at(0), launch_source="vscode")]
        got = classify_all(rows, BOTH)
        self.assertEqual((got["codex:c1"], got["codex:c2"]),
                         ("direct", "direct"))

    def test_window_runs_until_the_call_result_came_back(self):
        # The call sat behind a permission prompt for five minutes.
        launcher = row("claude", "a", at(-600), end=at(900), multi_turn=True,
                       launches=[("codex", at(0))], until=at(300))
        got = classify_all_both([launcher, row("codex", "in", at(299)),
                            row("codex", "out", at(301))])
        self.assertEqual(got["codex:in"], "launched")
        self.assertEqual(got["codex:out"], "direct")

    def test_result_sooner_than_the_minimum_window_keeps_the_minimum(self):
        # A backgrounded call returns at once; the run still starts later.
        launcher = row("claude", "a", at(-600), end=at(600), multi_turn=True,
                       launches=[("codex", at(0))], until=at(1))
        rows = [launcher, row("codex", "c1", at(30))]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_time_match_marks_launched_even_when_multi_turn(self):
        launcher = row("claude", "a", at(-600), end=at(600), multi_turn=True,
                       launches=[("codex", at(0))])
        rows = [launcher, row("codex", "c1", at(5), multi_turn=True)]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_window_boundary(self):
        launcher = row("claude", "a", at(-600), end=at(600), multi_turn=True,
                       launches=[("codex", at(0))])
        inside = row("codex", "in", at(LAUNCH_WINDOW_SECONDS))
        outside = row("codex", "out", at(LAUNCH_WINDOW_SECONDS + 1))
        before = row("codex", "pre", at(-1))
        got = classify_all_both([launcher, inside, outside, before])
        self.assertEqual(got["codex:in"], "launched")
        self.assertEqual(got["codex:out"], "direct")
        self.assertEqual(got["codex:pre"], "direct")

    def test_launch_of_a_different_tool_does_not_match(self):
        launcher = row("claude", "a", at(-600), end=at(600), multi_turn=True,
                       launches=[("grok", at(0))])
        rows = [launcher, row("codex", "c1", at(5))]
        self.assertEqual(self.origin(rows, "codex:c1"), "direct")

    def test_reverse_direction_codex_launches_claude(self):
        launcher = row("codex", "d", at(-600), end=at(600), multi_turn=True,
                       launches=[("claude", at(0))])
        rows = [launcher, row("claude", "e", at(4))]
        self.assertEqual(self.origin(rows, "claude:e"), "launched")

    def test_multi_turn_is_what_makes_an_uncovered_session_direct(self):
        # No launcher tool was scanned at all, so coverage can vouch for
        # nothing: the verdict rests on multi_turn alone.
        for multi, want in ((True, "direct"), (False, "unknown")):
            rows = [row("grok", "g1", at(0), multi_turn=multi)]
            self.assertEqual(self.origin(rows, "grok:g1", scanned=set()), want)

    def test_single_turn_outside_launcher_coverage_is_unknown(self):
        # Claude transcripts exist, but none span this moment (rotated).
        late_claude = row("claude", "a", at(86400), end=at(90000), multi_turn=True)
        rows = [late_claude, row("codex", "c1", at(0))]
        self.assertEqual(self.origin(rows, "codex:c1"), "unknown")

    def test_single_turn_inside_launcher_coverage_is_direct(self):
        rows = [CLAUDE_SPAN, row("codex", "c1", at(0))]
        self.assertEqual(self.origin(rows, "codex:c1"), "direct")

    def test_launcher_rows_without_scanned_shell_calls_give_no_coverage(self):
        # Session-meta rows carry no cli_launches list: they cannot show
        # that nothing was launched.
        unscanned = row("claude", "a", at(-3600), end=at(7200),
                        multi_turn=True, scanned=False)
        rows = [unscanned, row("codex", "c1", at(0))]
        self.assertEqual(self.origin(rows, "codex:c1"), "unknown")

    def test_scanned_launcher_with_no_sessions_does_not_block(self):
        # The Codex adapter ran and found nothing: only Claude could launch.
        rows = [CLAUDE_SPAN, row("grok", "g1", at(0))]
        self.assertEqual(self.origin(rows, "grok:g1"), "direct")

    def test_launcher_that_was_not_scanned_blocks(self):
        # Same rows, but the Codex adapter never ran: "no Codex rows" is
        # then "not looked", and a Codex launch cannot be ruled out.
        rows = [CLAUDE_SPAN, row("grok", "g1", at(0))]
        self.assertEqual(self.origin(rows, "grok:g1", scanned={"claude"}),
                         "unknown")
        # Default (scanned_sources not given): only tools with scanned
        # rows count, so the answer is the same.
        self.assertEqual(classify_all(rows)["grok:g1"], "unknown")

    def test_lone_session_meta_row_is_not_direct(self):
        # One Claude row with a time and nothing else, cross-tool adapters
        # not run: nothing shows who started it.
        r = row("claude", "a", at(0), scanned=False)
        self.assertEqual(classify_all([r], set())["claude:a"], "unknown")
        self.assertEqual(classify_all([r])["claude:a"], "unknown")

    def test_old_straggler_does_not_vouch_for_the_gap_after_it(self):
        # Rotation left one old Claude transcript and the recent run. A
        # single-prompt Codex session in the weeks between is not covered.
        gap = (COVERAGE_GAP_DAYS + 3) * DAY
        old = row("claude", "old", at(-gap - 3600), end=at(-gap), multi_turn=True)
        recent = row("claude", "new", at(0), end=at(3600), multi_turn=True)
        rows = [old, recent,
                row("codex", "mid", at(-gap // 2)),
                row("codex", "now", at(60))]
        got = classify_all(rows, BOTH)
        self.assertEqual(got["codex:mid"], "unknown")
        self.assertEqual(got["codex:now"], "direct")

    def test_sessions_closer_than_the_gap_form_one_retained_run(self):
        near = (COVERAGE_GAP_DAYS - 1) * DAY
        rows = [row("claude", "a", at(-near - 60), end=at(-near), multi_turn=True),
                row("claude", "b", at(0), end=at(3600), multi_turn=True),
                row("codex", "mid", at(-near // 2))]
        self.assertEqual(self.origin(rows, "codex:mid"), "direct")

    def test_unscanned_session_at_that_moment_hides_a_launch(self):
        # Claude's retained run spans the moment, but one Claude session
        # active right then is known only from session-meta.
        blind = row("claude", "meta", at(-120), scanned=False,
                    duration_minutes=10)
        blind["segments"] = None
        rows = [CLAUDE_SPAN, blind, row("codex", "c1", at(0)),
                row("codex", "c2", at(3000))]
        got = classify_all(rows, BOTH)
        self.assertEqual(got["codex:c1"], "unknown")
        self.assertEqual(got["codex:c2"], "direct")

    def test_same_tool_launch_marks_the_child_not_the_parent(self):
        parent = row("claude", "p", at(-600), end=at(600), multi_turn=True,
                     launches=[("claude", at(0))], until=at(20))
        rows = [parent, row("claude", "child", at(3)),
                row("claude", "later", at(45), multi_turn=True)]
        got = classify_all(rows, {"claude"})
        self.assertEqual(got["claude:p"], "direct")
        self.assertEqual(got["claude:child"], "launched")
        # Same-tool calls keep their real duration (no 60 s padding), so a
        # session opened by hand 25 s after the call ended is not swept in.
        self.assertEqual(got["claude:later"], "direct")

    def test_malformed_launch_events_are_skipped_not_fatal(self):
        bad = row("claude", "a", at(-600), end=at(600), multi_turn=True)
        bad["cli_launches"] = [None, "x", {"target": "codex"},
                               {"target": "codex", "ts": at(0), "until": None}]
        rows = [bad, row("codex", "c1", at(5))]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_no_usable_start_is_unknown(self):
        r = row("codex", "c1", "not a time")
        r["segments"] = None
        self.assertEqual(self.origin([CLAUDE_SPAN, r], "codex:c1"), "unknown")

    def test_malformed_segments_fall_back_to_start_time(self):
        r = row("codex", "c1", at(0))
        r["segments"] = [["garbage"], [at(50), at(10)], "x"]
        self.assertEqual(self.origin([CLAUDE_SPAN, r], "codex:c1"), "direct")

    def test_grok_rows_never_count_as_launcher_coverage(self):
        g = row("grok", "g", at(-3600), end=at(7200), multi_turn=True)
        self.assertEqual(launcher_coverage([g], BOTH), {})

    def test_naive_timestamps_do_not_raise(self):
        launcher = row("claude", "a", "2026-04-01T09:00:00",
                       end="2026-04-01T11:00:00", multi_turn=True,
                       launches=[("codex", "2026-04-01T10:00:00")])
        rows = [launcher, row("codex", "c1", "2026-04-01T10:00:05")]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_rows_without_source_are_claude(self):
        r = row("claude", "a", at(0), multi_turn=True)
        del r["source"]
        self.assertEqual(classify_all_both([r]), {"claude:a": "direct"})

    def test_orphan_fragment_launch_still_counts_but_gives_no_coverage(self):
        # The fragment's own activity spans c2's start: were fragments ever
        # counted as coverage, c2 would wrongly come out "direct".
        orphan = row("claude", "o", at(-10), end=at(7200),
                     launches=[("codex", at(0))], orphan_subagent_only=True)
        got = classify_all_both([orphan, row("codex", "c1", at(5)),
                            row("codex", "c2", at(600))])
        self.assertEqual(got["codex:c1"], "launched")
        # No Claude transcript proper spans c2, so nothing shows it was
        # NOT launched.
        self.assertEqual(got["codex:c2"], "unknown")
        self.assertNotIn("claude:o", got)

    def test_presence_only_and_orphan_rows_are_skipped(self):
        anti = {"source": "antigravity", "session_id": "x",
                "start_time": at(0), "coverage": "presence_only"}
        orphan = row("claude", "o", at(0), orphan_subagent_only=True)
        self.assertEqual(classify_all_both([anti, orphan]), {})


class CountTests(unittest.TestCase):
    def test_counts_per_source(self):
        launcher = row("claude", "a", at(-600), end=at(600), multi_turn=True,
                       launches=[("codex", at(0))])
        rows = [launcher, row("codex", "c1", at(5)),
                row("codex", "c2", at(300), multi_turn=True)]
        counts = count_by_source(classify_all(rows, BOTH))
        self.assertEqual(counts["codex"],
                         {"direct": 1, "launched": 1, "unknown": 0})
        self.assertEqual(counts["claude"],
                         {"direct": 1, "launched": 0, "unknown": 0})


if __name__ == "__main__":
    unittest.main()
