# tests/test_cross_llm_aggregate.py
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scripts.aggregate import (
    compute_cross_llm, compute_ledger, load_cross_llm_rows, _row_windows)


def _iso(dt):
    return dt.isoformat()


def _claude_row(sid, start, dur=60, project="/home/user/projects/webapp",
                commits=0):
    return {"session_id": sid, "project_path": project,
            "start_time": _iso(start), "duration_minutes": dur,
            "input_tokens": 1000, "output_tokens": 200,
            "git_commits": commits, "git_pushes": 0}


def _codex_row(sid, start, dur=60, project="/home/user/projects/webapp"):
    return {"session_id": sid, "project_path": project,
            "start_time": _iso(start), "duration_minutes": dur,
            "segments": [[_iso(start), _iso(start + timedelta(minutes=dur))]],
            "input_tokens": 500, "output_tokens": 100,
            "source": "codex", "coverage": "full"}


BASE = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


class CrossLlmTests(unittest.TestCase):
    def _twenty_days_both(self):
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i)) for i in range(20)]
        codex = [_codex_row(f"x{i}", BASE + timedelta(days=i, minutes=30))
                 for i in range(20)]
        return claude, codex

    def test_sources_cards_include_claude(self):
        claude, codex = self._twenty_days_both()
        block = compute_cross_llm(claude, codex)
        srcs = {s["source"]: s for s in block["sources"]}
        self.assertIn("claude", srcs)
        self.assertIn("codex", srcs)
        self.assertEqual(srcs["codex"]["session_count"], 20)

    def test_common_window_not_degraded_at_20_days(self):
        claude, codex = self._twenty_days_both()
        block = compute_cross_llm(claude, codex)
        self.assertFalse(block["common_window"]["degraded"])
        self.assertGreaterEqual(block["common_window"]["days"], 14)

    def test_common_window_degraded_below_14_days(self):
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i)) for i in range(30)]
        codex = [_codex_row("x0", BASE + timedelta(days=25))]  # 5-day overlap tail
        block = compute_cross_llm(claude, codex)
        self.assertTrue(block["common_window"]["degraded"])

    def test_parallel_overlap_detected(self):
        claude = [_claude_row("c0", BASE, dur=120)]
        codex = [_codex_row("x0", BASE + timedelta(minutes=10), dur=60)]
        block = compute_cross_llm(claude, codex)
        self.assertGreaterEqual(block["parallel"]["hours_multi_source"], 1)

    def test_parallel_same_hour_non_overlapping_not_counted(self):
        # Both sessions touch the 09:00 hour bucket but never run at the same
        # instant (09:05-09:10 vs 09:55-09:58) — true-overlap detection must
        # NOT mark this hour as multi-source, even though the old hour-bucket
        # heuristic would.
        claude = [_claude_row("c0", BASE.replace(hour=9, minute=5), dur=5)]
        codex = [_codex_row("x0", BASE.replace(hour=9, minute=55), dur=3)]
        block = compute_cross_llm(claude, codex)
        self.assertEqual(block["parallel"]["hours_multi_source"], 0)

    def test_presence_only_excluded_from_comparisons(self):
        claude, codex = self._twenty_days_both()
        anti = [{"session_id": "a0", "project_path": "",
                 "start_time": _iso(BASE), "duration_minutes": None,
                 "segments": None, "input_tokens": None, "output_tokens": None,
                 "source": "antigravity", "coverage": "presence_only"}]
        block = compute_cross_llm(claude, codex + anti)
        srcs = {s["source"] for s in block["sources"]}
        self.assertIn("antigravity", srcs)
        for wk in block["weekly_share"]:
            self.assertNotIn("antigravity", wk["minutes"])
        self.assertNotIn("antigravity", block["project_matrix"]["sources"])

    def test_head_to_head_present_with_both_sources(self):
        claude, codex = self._twenty_days_both()
        h2h = compute_cross_llm(claude, codex)["head_to_head"]
        self.assertIsNotNone(h2h)
        self.assertEqual(h2h["claude"]["sessions"], 20)
        self.assertEqual(h2h["codex"]["sessions"], 20)

    def test_head_to_head_uses_statistics_median(self):
        # 4 claude sessions with durations 10, 20, 30, 1000 — statistics.median
        # gives (20+30)/2 = 25, NOT durs[len//2] == durs[2] == 30 (the old
        # lower-biased index pick for even-length lists).
        claude = [
            _claude_row("c0", BASE, dur=10),
            _claude_row("c1", BASE + timedelta(days=1), dur=20),
            _claude_row("c2", BASE + timedelta(days=2), dur=30),
            _claude_row("c3", BASE + timedelta(days=3), dur=1000),
        ]
        codex = [_codex_row(f"x{i}", BASE + timedelta(days=i, minutes=30))
                 for i in range(20)]
        h2h = compute_cross_llm(claude, codex)["head_to_head"]
        self.assertEqual(h2h["claude"]["median_duration_minutes"], 25)

    def test_head_to_head_total_tokens_skips_rows_with_no_token_data(self):
        # One codex row in the window has both token fields None (e.g. a
        # grok-like partial-coverage source or a codex row with no usage
        # info yet) — total_tokens must sum only rows that DO have data,
        # not impute 0 for the missing one silently mixed into the total
        # (imputing 0 vs skipping only differs when ALL rows lack data,
        # which the "if NO row has token data, emit None" rule covers).
        claude, codex = self._twenty_days_both()
        no_token_codex = dict(codex[0])
        no_token_codex["input_tokens"] = None
        no_token_codex["output_tokens"] = None
        codex_with_gap = [no_token_codex] + codex[1:]
        h2h = compute_cross_llm(claude, codex_with_gap)["head_to_head"]
        expected = sum(
            (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0)
            for r in codex[1:]
        )
        self.assertEqual(h2h["codex"]["total_tokens"], expected)

    def test_head_to_head_total_tokens_none_when_no_row_has_token_data(self):
        claude, codex = self._twenty_days_both()
        for r in codex:
            r["input_tokens"] = None
            r["output_tokens"] = None
        h2h = compute_cross_llm(claude, codex)["head_to_head"]
        self.assertIsNone(h2h["codex"]["total_tokens"])

    def test_mixed_naive_and_aware_timestamps_does_not_raise(self):
        # One claude row has a timezone-naive start_time (no UTC offset),
        # mixed with aware codex rows. Regression for TypeError: can't
        # compare offset-naive and offset-aware datetimes, which used to
        # abort compute_cross_llm (and therefore the whole aggregate run)
        # before _parse_dt normalized naive datetimes to aware UTC.
        naive_claude = _claude_row("c_naive", BASE)
        naive_claude["start_time"] = "2026-06-05T10:00:00"  # no offset
        claude = [naive_claude] + [
            _claude_row(f"c{i}", BASE + timedelta(days=i)) for i in range(1, 20)
        ]
        codex = [_codex_row(f"x{i}", BASE + timedelta(days=i, minutes=30))
                 for i in range(20)]
        block = compute_cross_llm(claude, codex)
        self.assertIsInstance(block, dict)
        self.assertIsNotNone(block["common_window"])

    def test_weekly_share_clipped_to_common_window(self):
        # Claude has 30 days of history; codex only shows up in the last 20
        # days. weekly_share must not include any week that predates the
        # common_window start (the renderer's note claims the comparison is
        # scoped to the common window — the data must match that claim).
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i)) for i in range(30)]
        codex = [_codex_row(f"x{i}", BASE + timedelta(days=10 + i, minutes=30))
                 for i in range(20)]
        block = compute_cross_llm(claude, codex)
        win = block["common_window"]
        self.assertIsNotNone(win)
        win_start = datetime.fromisoformat(win["start"]).date()
        for wk in block["weekly_share"]:
            # ISO week string "YYYY-Www" — recover the Monday of that week
            # and confirm no week's Monday falls entirely before the window,
            # i.e. every week represented has at least one day >= win_start.
            year, week_num = wk["week"].split("-W")
            monday = date.fromisocalendar(int(year), int(week_num), 1)
            sunday = monday + timedelta(days=6)
            self.assertGreaterEqual(sunday, win_start,
                                     f"week {wk['week']} entirely predates common window")

    def test_midnight_spanning_session_splits_by_day(self):
        late = datetime(2026, 6, 1, 23, 30, tzinfo=timezone.utc)
        claude = [_claude_row("c0", late, dur=120)]  # crosses midnight
        codex = [_codex_row("x0", late + timedelta(minutes=5), dur=120)]
        block = compute_cross_llm(claude, codex)
        days = {d["date"] for d in block["parallel"]["daily_max"]}
        self.assertIn("2026-06-01", days)
        self.assertIn("2026-06-02", days)


class ZeroLengthSegmentTests(unittest.TestCase):
    def test_row_windows_expands_zero_length_segment_to_one_minute(self):
        # A single-event session (e.g. one grok prompt) has a [t, t] segment
        # — zero duration. _row_windows must expand it to a minimum 1-minute
        # window so it contributes real minutes/parallel presence instead of
        # silently vanishing from weekly_share and the parallel heatmap.
        t = _iso(BASE)
        row = {"start_time": t, "segments": [[t, t]]}
        windows = _row_windows(row)
        self.assertEqual(len(windows), 1)
        s, e = windows[0]
        self.assertGreaterEqual((e - s).total_seconds(), 60)

    def test_grok_single_prompt_session_contributes_to_weekly_share(self):
        claude, codex = self._twenty_days_both_helper()
        t = _iso(BASE + timedelta(days=1))
        grok_single = [{"session_id": "g0", "project_path": "/home/user/x",
                        "start_time": t, "duration_minutes": 0,
                        "segments": [[t, t]], "input_tokens": None,
                        "output_tokens": None, "source": "grok",
                        "coverage": "partial"}]
        block = compute_cross_llm(claude, codex + grok_single)
        total_grok_minutes = sum(
            wk["minutes"].get("grok", 0) for wk in block["weekly_share"])
        self.assertGreaterEqual(total_grok_minutes, 1)

    def _twenty_days_both_helper(self):
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i)) for i in range(20)]
        codex = [_codex_row(f"x{i}", BASE + timedelta(days=i, minutes=30))
                 for i in range(20)]
        return claude, codex


class LoadCrossLlmRowsTests(unittest.TestCase):
    def test_malformed_scalar_json_line_counted_not_fatal(self):
        # A syntactically valid JSON line that isn't an object (bare array)
        # must not raise when the loader does row.get(...); it should be
        # counted as a parse error under "(unknown)" and skipped.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "codex.jsonl"
            good = _codex_row("x0", BASE)
            p.write_text(
                json.dumps(good) + "\n" + json.dumps([1, 2, 3]) + "\n",
                encoding="utf-8")
            rows, errors = load_cross_llm_rows([str(p)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(sum(errors.values()), 1)

    def test_meta_line_consumed_into_parse_errors_not_treated_as_session(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "codex.jsonl"
            good = _codex_row("x0", BASE)
            meta = {"_meta": True, "source": "codex", "parse_errors": 3}
            p.write_text(json.dumps(good) + "\n" + json.dumps(meta) + "\n",
                          encoding="utf-8")
            rows, errors = load_cross_llm_rows([str(p)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(errors.get("codex"), 3)


class DetectedSourcesTests(unittest.TestCase):
    def test_sources_always_has_four_entries_and_undetected_flag(self):
        claude, codex = self._twenty_days_both_helper()
        block = compute_cross_llm(claude, codex)
        srcs = {s["source"]: s for s in block["sources"]}
        self.assertEqual(set(srcs), {"claude", "codex", "grok", "antigravity"})
        self.assertTrue(srcs["claude"]["detected"])
        self.assertTrue(srcs["codex"]["detected"])
        self.assertFalse(srcs["grok"]["detected"])
        self.assertFalse(srcs["antigravity"]["detected"])
        self.assertIsNone(srcs["grok"]["coverage"])
        self.assertEqual(srcs["grok"]["session_count"], 0)
        # undetected sources must never leak into comparison structures
        for wk in block["weekly_share"]:
            self.assertNotIn("grok", wk["minutes"])
            self.assertNotIn("antigravity", wk["minutes"])
        self.assertNotIn("grok", block["project_matrix"]["sources"])
        self.assertNotIn("antigravity", block["project_matrix"]["sources"])

    def _twenty_days_both_helper(self):
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i)) for i in range(20)]
        codex = [_codex_row(f"x{i}", BASE + timedelta(days=i, minutes=30))
                 for i in range(20)]
        return claude, codex


class LedgerTests(unittest.TestCase):
    def test_ledger_output_counts(self):
        metas = {f"c{i}": _claude_row(f"c{i}", BASE + timedelta(days=i),
                                      commits=(1 if i % 2 else 0))
                 for i in range(10)}
        cross = compute_cross_llm(list(metas.values()), [])
        ledger = compute_ledger(metas, cross)
        self.assertEqual(ledger["schema_version"], 1)
        self.assertEqual(ledger["output"]["git_commits"], 5)
        self.assertEqual(ledger["output"]["sessions_with_commits"], 5)
        self.assertIn("claude", ledger["sources_detected"])


if __name__ == "__main__":
    unittest.main()
