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
    LAUNCH_WINDOW_SECONDS, classify_all, count_by_source, launcher_spans)


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
            self.assertEqual(cli_launch_targets(cmd, "claude"), ["codex"], cmd)
        self.assertEqual(
            cli_launch_targets("~/.local/bin/claude -p hi", "codex"), ["claude"])

    def test_names_inside_a_longer_word_or_path_do_not_match(self):
        for cmd in ("cat ./codex-notes.md", "ls ~/.codex/sessions",
                    "cat ~/.claude/settings.json", "pip install codex_tools",
                    "open https://claude.ai/x", "cd codex/src && ls",
                    "echo Codex", "vim grok.md"):
            self.assertEqual(cli_launch_targets(cmd, "none"), [], cmd)

    def test_own_cli_is_not_a_cross_tool_launch(self):
        self.assertEqual(cli_launch_targets("claude -p x", "claude"), [])
        self.assertEqual(cli_launch_targets("claude -p x; grok -p y", "claude"),
                         ["grok"])

    def test_non_string_command(self):
        self.assertEqual(cli_launch_targets(None, "claude"), [])
        self.assertEqual(cli_launch_targets(["codex"], "claude"), [])


class ClassifyTests(unittest.TestCase):
    def origin(self, rows, key):
        return classify_all(rows)[key]

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
        got = classify_all(rows)
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
        got = classify_all(rows)
        self.assertEqual((got["codex:c1"], got["codex:c2"]),
                         ("direct", "direct"))

    def test_window_runs_until_the_call_result_came_back(self):
        # The call sat behind a permission prompt for five minutes.
        launcher = row("claude", "a", at(-600), end=at(900), multi_turn=True,
                       launches=[("codex", at(0))], until=at(300))
        got = classify_all([launcher, row("codex", "in", at(299)),
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
        got = classify_all([launcher, inside, outside, before])
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

    def test_multi_turn_is_direct_without_any_coverage(self):
        rows = [row("grok", "g1", at(0), multi_turn=True)]
        self.assertEqual(self.origin(rows, "grok:g1"), "direct")

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

    def test_absent_launcher_tool_does_not_block(self):
        # The user has no Codex sessions at all: only Claude could launch.
        rows = [CLAUDE_SPAN, row("grok", "g1", at(0))]
        self.assertEqual(self.origin(rows, "grok:g1"), "direct")

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
        self.assertEqual(launcher_spans([g]), {})

    def test_naive_timestamps_do_not_raise(self):
        launcher = row("claude", "a", "2026-04-01T09:00:00",
                       end="2026-04-01T11:00:00", multi_turn=True,
                       launches=[("codex", "2026-04-01T10:00:00")])
        rows = [launcher, row("codex", "c1", "2026-04-01T10:00:05")]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_rows_without_source_are_claude(self):
        r = row("claude", "a", at(0), multi_turn=True)
        del r["source"]
        self.assertEqual(classify_all([r]), {"claude:a": "direct"})

    def test_orphan_fragment_launch_still_counts_but_gives_no_coverage(self):
        orphan = row("claude", "o", at(-10), launches=[("codex", at(0))],
                     orphan_subagent_only=True)
        got = classify_all([orphan, row("codex", "c1", at(5)),
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
        self.assertEqual(classify_all([anti, orphan]), {})


class CountTests(unittest.TestCase):
    def test_counts_per_source(self):
        launcher = row("claude", "a", at(-600), end=at(600), multi_turn=True,
                       launches=[("codex", at(0))])
        rows = [launcher, row("codex", "c1", at(5)),
                row("codex", "c2", at(300), multi_turn=True)]
        counts = count_by_source(classify_all(rows))
        self.assertEqual(counts["codex"],
                         {"direct": 1, "launched": 1, "unknown": 0})
        self.assertEqual(counts["claude"],
                         {"direct": 1, "launched": 0, "unknown": 0})


if __name__ == "__main__":
    unittest.main()
