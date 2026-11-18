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
    LAUNCH_WINDOW_SECONDS, classify_all, count_by_source)


def row(source, sid, start, *, end=None, multi_turn=False, launches=(),
        until=None, **extra):
    """A scanner row. `interactive` (True / False) is passed through
    **extra; leaving it out means the transcript does not say."""
    return {"source": source, "session_id": sid, "start_time": start,
            "segments": [[start, end or start]], "multi_turn": multi_turn,
            "coverage": "partial" if source == "grok" else "full",
            "cli_launches": [{"target": t, "ts": ts, "until": until}
                             for t, ts in launches], **extra}


T0 = "2026-04-01T10:00:00+00:00"


def at(seconds):
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(T0) + timedelta(seconds=seconds)).isoformat()


# A long hand-driven Claude session spanning every test timestamp and
# launching nothing. Its presence must never make another session direct.
CLAUDE_SPAN = row("claude", "span", at(-3600), end=at(7200), interactive=True)


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


def launcher(source="claude", target="codex", until=None, sid="a"):
    return row(source, sid, at(-600), end=at(900), interactive=True,
               launches=[(target, at(0))], until=until)


class ClassifyTests(unittest.TestCase):
    def origin(self, rows, key):
        return classify_all(rows)[key]

    # -- direct needs positive evidence ---------------------------------

    def test_recorded_interactive_session_is_direct_on_its_own(self):
        got = classify_all([row("claude", "a", at(0), interactive=True),
                            row("codex", "c", at(0), interactive=True)])
        self.assertEqual(got, {"claude:a": "direct", "codex:c": "direct"})

    def test_nothing_recorded_and_one_prompt_is_unknown(self):
        # Other tools' transcripts span the moment and show no launch.
        # That absence proves nothing: a script, a scheduler or a rotated
        # transcript could have started it.
        rows = [CLAUDE_SPAN, row("codex", "c1", at(0)),
                row("claude", "old", at(0)), row("grok", "g1", at(0))]
        got = classify_all(rows)
        self.assertEqual(
            [got["codex:c1"], got["claude:old"], got["grok:g1"]],
            ["unknown"] * 3)

    def test_nothing_recorded_but_a_real_back_and_forth_is_direct(self):
        rows = [row("grok", "g1", at(0), multi_turn=True),
                row("codex", "c1", at(0), multi_turn=True)]
        self.assertEqual(set(classify_all(rows).values()), {"direct"})

    def test_recorded_non_interactive_is_never_direct(self):
        # Not even with several turns: a script can feed a run more than
        # one prompt.
        rows = [CLAUDE_SPAN,
                row("codex", "c1", at(0), interactive=False),
                row("codex", "c2", at(0), interactive=False, multi_turn=True),
                row("claude", "s", at(0), interactive=False, multi_turn=True)]
        got = classify_all(rows)
        self.assertEqual(
            [got["codex:c1"], got["codex:c2"], got["claude:s"]],
            ["unknown"] * 3)

    def test_only_true_and_false_count_as_a_record(self):
        for junk in ("yes", 1, 0, "", [], {}):
            r = row("codex", "c", at(0), interactive=junk)
            self.assertEqual(self.origin([r], "codex:c"), "unknown", junk)
        r = row("codex", "c", at(0), multi_turn="yes")
        self.assertEqual(self.origin([r], "codex:c"), "unknown")
        # A malformed record is not "no record": the back-and-forth rule
        # is for rows that say nothing at all.
        for junk in ("false", "true", 0, 1, [], {}):
            r = row("codex", "c", at(0), interactive=junk, multi_turn=True)
            self.assertEqual(self.origin([r], "codex:c"), "unknown", junk)

    # -- launched -------------------------------------------------------

    def test_spawned_header_marks_launched_over_everything(self):
        rows = [row("codex", "c1", at(0), multi_turn=True, interactive=True,
                    launch_source="subagent"),
                row("codex", "c2", at(0), launch_source="SubAgent")]
        self.assertEqual(set(classify_all(rows).values()), {"launched"})

    def test_non_interactive_run_with_a_matching_call_is_launched(self):
        rows = [launcher(), row("codex", "c1", at(5), interactive=False)]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_time_match_beats_multi_turn_when_nothing_is_recorded(self):
        rows = [launcher(), row("codex", "c1", at(5), multi_turn=True)]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_the_transcripts_own_record_beats_a_time_match(self):
        # The user opened the terminal UI while an unrelated call that
        # mentions the tool happened to be running.
        rows = [launcher(), row("codex", "c1", at(5), interactive=True)]
        self.assertEqual(self.origin(rows, "codex:c1"), "direct")

    def test_window_runs_until_the_call_result_came_back(self):
        # The call sat behind a permission prompt for five minutes.
        got = classify_all([launcher(until=at(300)),
                            row("codex", "in", at(299)),
                            row("codex", "edge", at(300)),
                            row("codex", "out", at(301))])
        self.assertEqual(
            [got["codex:in"], got["codex:edge"], got["codex:out"]],
            ["launched", "launched", "unknown"])

    def test_result_sooner_than_the_minimum_window_keeps_the_minimum(self):
        # A backgrounded call returns at once; the run still starts later.
        rows = [launcher(until=at(1)), row("codex", "c1", at(30))]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_window_boundary(self):
        got = classify_all([
            launcher(),
            row("codex", "in", at(LAUNCH_WINDOW_SECONDS)),
            row("codex", "out", at(LAUNCH_WINDOW_SECONDS + 1)),
            row("codex", "same", at(0)),
            row("codex", "pre", at(-1))])
        self.assertEqual(got["codex:in"], "launched")
        # A session cannot be started by a call made at or after its own
        # first record.
        for sid in ("out", "same", "pre"):
            self.assertEqual(got[f"codex:{sid}"], "unknown", sid)

    def test_an_earlier_long_call_still_covers_after_a_later_short_one(self):
        long_call = row("claude", "a", at(-600), end=at(900), interactive=True,
                        launches=[("codex", at(0))], until=at(500))
        short_call = row("claude", "b", at(-600), end=at(900), interactive=True,
                         launches=[("codex", at(100))], until=at(101))
        rows = [long_call, short_call, row("codex", "c1", at(400)),
                row("codex", "c2", at(501))]
        got = classify_all(rows)
        self.assertEqual((got["codex:c1"], got["codex:c2"]),
                         ("launched", "unknown"))

    def test_launch_of_a_different_tool_does_not_match(self):
        rows = [launcher(target="grok"), row("codex", "c1", at(5))]
        self.assertEqual(self.origin(rows, "codex:c1"), "unknown")

    def test_reverse_direction_codex_launches_claude(self):
        rows = [launcher(source="codex", target="claude", sid="d"),
                row("claude", "e", at(4), interactive=False)]
        self.assertEqual(self.origin(rows, "claude:e"), "launched")

    def test_same_tool_launch_marks_the_child_not_the_parent(self):
        # The parent's first record and its own call share a timestamp:
        # the parent must not match itself.
        parent = row("claude", "p", at(0), end=at(600), interactive=True,
                     launches=[("claude", at(0))], until=at(20))
        headless_parent = row("claude", "hp", at(0), end=at(600),
                              interactive=False,
                              launches=[("claude", at(0))], until=at(20))
        rows = [parent, row("claude", "child", at(3), interactive=False)]
        got = classify_all(rows)
        self.assertEqual(got, {"claude:p": "direct", "claude:child": "launched"})
        self.assertEqual(
            classify_all([headless_parent])["claude:hp"], "unknown")

    # -- robustness -----------------------------------------------------

    def test_malformed_launch_events_are_skipped_not_fatal(self):
        bad = row("claude", "a", at(-600), end=at(600), interactive=True)
        bad["cli_launches"] = [
            None, "x", {"target": "codex"}, {"target": ["codex"], "ts": at(0)},
            {"target": {"a": 1}, "ts": at(0)}, {"target": "emacs", "ts": at(0)},
            {"target": "codex", "ts": "junk"},
            {"target": "codex", "ts": at(0), "until": "junk"}]
        worse = row("claude", "b", at(-600), interactive=True)
        worse["cli_launches"] = "codex"
        rows = [bad, worse, row("codex", "c1", at(5)),
                row("codex", "c2", at(LAUNCH_WINDOW_SECONDS + 5))]
        got = classify_all(rows)
        self.assertEqual((got["codex:c1"], got["codex:c2"]),
                         ("launched", "unknown"))

    def test_no_usable_start_cannot_be_time_matched(self):
        r = row("codex", "c1", "not a time", interactive=False)
        r["segments"] = None
        self.assertEqual(self.origin([launcher(), r], "codex:c1"), "unknown")

    def test_malformed_segments_fall_back_to_start_time(self):
        # The reversed pair starts outside the window: were it used, the
        # verdict would be unknown.
        r = row("codex", "c1", at(5))
        r["segments"] = [["garbage"], [at(5000), at(10)], "x"]
        self.assertEqual(self.origin([launcher(), r], "codex:c1"), "launched")

    def test_segments_of_the_wrong_type_fall_back_to_start_time(self):
        for junk in (7, "x", {"a": 1}, None):
            r = row("codex", "c1", at(5))
            r["segments"] = junk
            self.assertEqual(self.origin([launcher(), r], "codex:c1"),
                             "launched", junk)

    def test_earliest_segment_is_the_start(self):
        # start_time says later than the first segment (a resumed file).
        r = row("codex", "c1", at(4000))
        r["segments"] = [[at(3000), at(3100)], [at(5), at(40)]]
        self.assertEqual(self.origin([launcher(), r], "codex:c1"), "launched")

    def test_naive_timestamps_do_not_raise(self):
        a = row("claude", "a", "2026-04-01T09:00:00",
                end="2026-04-01T11:00:00", interactive=True,
                launches=[("codex", "2026-04-01T10:00:00")])
        rows = [a, row("codex", "c1", "2026-04-01T10:00:05")]
        self.assertEqual(self.origin(rows, "codex:c1"), "launched")

    def test_rows_without_source_are_claude(self):
        r = row("claude", "a", at(0), interactive=True)
        del r["source"]
        self.assertEqual(classify_all([r]), {"claude:a": "direct"})

    def test_duplicate_session_keys_keep_the_more_cautious_verdict(self):
        direct = row("codex", "dup", at(5000), interactive=True)
        unknown = row("codex", "dup", at(5000))
        launched = row("codex", "dup", at(5), interactive=False)
        for rows, want in (([direct, unknown], "unknown"),
                           ([unknown, direct], "unknown"),
                           ([direct, launched, unknown], "launched"),
                           ([unknown, launched], "launched"),
                           ([launched, direct], "launched")):
            self.assertEqual(
                classify_all([launcher()] + rows)["codex:dup"], want)

    def test_orphan_fragment_launch_still_counts(self):
        orphan = row("claude", "o", at(-10), end=at(7200),
                     launches=[("codex", at(0))], orphan_subagent_only=True)
        got = classify_all([orphan, row("codex", "c1", at(5)),
                            row("codex", "c2", at(600))])
        self.assertEqual(got, {"codex:c1": "launched", "codex:c2": "unknown"})

    def test_presence_only_orphan_and_idless_rows_are_skipped(self):
        anti = {"source": "antigravity", "session_id": "x",
                "start_time": at(0), "coverage": "presence_only"}
        orphan = row("claude", "o", at(0), orphan_subagent_only=True)
        noid = row("codex", None, at(0), interactive=True)
        self.assertEqual(classify_all([anti, orphan, noid]), {})


class CountTests(unittest.TestCase):
    def test_counts_per_source(self):
        rows = [launcher(), row("codex", "c1", at(5)),
                row("codex", "c2", at(300), multi_turn=True),
                row("codex", "c3", at(300))]
        counts = count_by_source(classify_all(rows))
        self.assertEqual(counts["codex"],
                         {"direct": 1, "launched": 1, "unknown": 1})
        self.assertEqual(counts["claude"],
                         {"direct": 1, "launched": 0, "unknown": 0})


if __name__ == "__main__":
    unittest.main()
