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

    def test_source_card_last_date_uses_resumed_segment_end(self):
        # A codex rollout file can be resumed days after its first segment
        # (spec: vendor rollout files get appended to when a session
        # resumes). The row's start_time is the FIRST segment's start
        # (Apr 20), but a later resumed segment ends Apr 30. The source
        # card's last_date must reflect the true last activity (Apr 30),
        # not just start_time.
        claude, _ = self._twenty_days_both()
        resumed = {
            "session_id": "x_resumed", "project_path": "/home/user/projects/webapp",
            "start_time": "2026-04-20T09:00:00Z", "duration_minutes": 30,
            "segments": [
                ["2026-04-20T09:00:00Z", "2026-04-20T09:30:00Z"],
                ["2026-04-30T14:00:00Z", "2026-04-30T14:45:00Z"],
            ],
            "input_tokens": 500, "output_tokens": 100,
            "source": "codex", "coverage": "full",
        }
        block = compute_cross_llm(claude, [resumed])
        codex_card = next(s for s in block["sources"] if s["source"] == "codex")
        self.assertEqual(codex_card["first_date"], "2026-04-20")
        self.assertEqual(codex_card["last_date"], "2026-04-30")

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

    def test_parallel_overlap_across_mixed_timezone_offsets(self):
        # Claude rows are always UTC ('Z'); adapter (codex/grok/antigravity)
        # rows may carry a local UTC offset instead. One claude row at
        # 2026-06-01T02:00:00Z (60min, so 02:00-03:00 UTC) and one codex row
        # at 2026-06-01T10:10:00+08:00 (== 02:10 UTC, 30min so 02:10-02:40
        # UTC) REALLY overlap 02:10-02:40 UTC. Before the tz-consistency fix,
        # comparing/bucketing each row in its own original offset instead of
        # a common zone could miss this true overlap.
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i)) for i in range(14)]
        overlap_claude = dict(claude[0])
        overlap_claude["session_id"] = "c_overlap"
        overlap_claude["start_time"] = "2026-06-01T02:00:00Z"
        overlap_claude["duration_minutes"] = 60
        claude.append(overlap_claude)

        codex = [_codex_row(f"x{i}", BASE + timedelta(days=i, minutes=30))
                 for i in range(14)]
        overlap_codex = {
            "session_id": "x_overlap", "project_path": "/home/user/projects/webapp",
            "start_time": "2026-06-01T10:10:00+08:00", "duration_minutes": 30,
            "segments": [["2026-06-01T10:10:00+08:00", "2026-06-01T10:40:00+08:00"]],
            "input_tokens": 500, "output_tokens": 100,
            "source": "codex", "coverage": "full",
        }
        codex.append(overlap_codex)

        block = compute_cross_llm(claude, codex)
        self.assertGreaterEqual(block["parallel"]["hours_multi_source"], 1)

    def test_parallel_overlap_straddling_utc_midnight_with_local_offset(self):
        # Sharper regression than the mixed-offset test above: the claude
        # row's window is stored in UTC and straddles the UTC calendar-day
        # boundary (23:50 -> 00:50), while the truly-overlapping codex row
        # is stored in +08:00 and falls entirely within a SINGLE +08:00
        # calendar day. Before the fix, day-splitting
        # (_split_at_midnight/_hours_touched) reads each row's own stored
        # offset, so the two sides' calendar-day/hour buckets for the same
        # real-world overlap window don't line up and the multi-source hour
        # can be missed or double-split. After normalizing every _parse_dt
        # result to one consistent zone, both rows bucket consistently and
        # the true overlap (07:55-08:15 local == 23:55-00:15 UTC) is counted
        # under exactly one calendar day.
        #
        # Baseline days are widely spaced (non-overlapping claude/codex
        # windows) so only the injected midnight pair produces any
        # concurrency>=2 bucket — isolates the assertion from unrelated
        # daily overlaps that a tighter fixture would introduce.
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i), dur=10)
                  for i in range(20)]
        overlap_claude = dict(claude[0])
        overlap_claude["session_id"] = "c_midnight"
        overlap_claude["start_time"] = "2026-06-05T23:50:00Z"
        overlap_claude["duration_minutes"] = 60  # 23:50 -> 00:50 UTC (Jun5->Jun6)
        claude.append(overlap_claude)

        codex = [_codex_row(f"x{i}", BASE + timedelta(days=i, hours=5), dur=10)
                 for i in range(20)]
        codex.append({
            "session_id": "x_midnight", "project_path": "/home/user/projects/webapp",
            "start_time": "2026-06-06T07:55:00+08:00", "duration_minutes": 20,
            "segments": [["2026-06-06T07:55:00+08:00", "2026-06-06T08:15:00+08:00"]],
            "input_tokens": 500, "output_tokens": 100,
            "source": "codex", "coverage": "full",
        })

        block = compute_cross_llm(claude, codex)
        self.assertGreaterEqual(block["parallel"]["hours_multi_source"], 1)
        daily_by_date = {d["date"]: d["max_parallel"] for d in block["parallel"]["daily_max"]}
        # The true overlap instant is 2026-06-06 07:55-08:15 in a single
        # consistent local zone — exactly one calendar day should show
        # max_parallel >= 2 for it, not a phantom split across two days.
        multi_days = [d for d, m in daily_by_date.items() if m >= 2]
        self.assertEqual(len(multi_days), 1)

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

    def test_head_to_head_includes_session_via_resumed_segment_in_window(self):
        # A codex session that STARTED before the common window (its
        # start_time is outside the window) but was resumed with a second
        # segment INSIDE the window is counted by parallel/project_matrix
        # (which are window-clipped, via `windows`/`_clip`) but was
        # previously excluded from head_to_head (which filtered by
        # start_time alone). head_to_head must include it too — the two
        # exhibits describe the same window and must agree on membership.
        claude, codex = self._twenty_days_both()
        window_start = date.fromisoformat(
            compute_cross_llm(claude, codex)["common_window"]["start"])
        # Resumed row: first segment well before the window, second segment
        # squarely inside it (2 days after window start).
        resumed_start = BASE - timedelta(days=10)
        resumed_inside = datetime.combine(
            window_start + timedelta(days=2), resumed_start.time(),
            tzinfo=resumed_start.tzinfo)
        resumed = {
            "session_id": "x_resumed_h2h",
            "project_path": "/home/user/projects/webapp",
            "start_time": _iso(resumed_start), "duration_minutes": 30,
            "segments": [
                [_iso(resumed_start), _iso(resumed_start + timedelta(minutes=30))],
                [_iso(resumed_inside), _iso(resumed_inside + timedelta(minutes=45))],
            ],
            "input_tokens": 500, "output_tokens": 100,
            "source": "codex", "coverage": "full",
        }
        block = compute_cross_llm(claude, codex + [resumed])
        h2h = block["head_to_head"]
        self.assertIsNotNone(h2h)
        # The resumed session's in-window segment must be counted: codex
        # session count grows by 1 versus the baseline (20) fixture.
        self.assertEqual(h2h["codex"]["sessions"], 21)

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

    def test_weekly_share_full_first_day_when_local_offset_nonzero(self):
        # Regression for the UTC-midnight clip bug: clip_start/clip_end used
        # to be built as UTC midnights even though _parse_dt returns
        # local-zone-aware datetimes. In a positive-UTC-offset zone (e.g.
        # +08:00), the window's first LOCAL day starts before UTC midnight
        # arrives, so activity between local midnight and the (wrongly UTC)
        # clip boundary was silently dropped from weekly_share.
        #
        # Construct rows at a fixed local offset (independent of the actual
        # machine running the test) so the fixture is deterministic: 20 days,
        # 60 minutes each, starting at 07:00 local on day 0 — local offsets
        # of +1h or more reproduce the bug (07:00 local < 08:00 = start of
        # local day in UTC when offset is +8; more generally any offset > 0
        # pushes local midnight before the UTC clip_start computed from the
        # same calendar date). Use +08:00 explicitly, matching the finding.
        tz8 = timezone(timedelta(hours=8))
        base_local = datetime(2026, 6, 1, 7, 0, tzinfo=tz8)
        claude = [_claude_row(f"c{i}", base_local + timedelta(days=i), dur=60)
                  for i in range(20)]
        codex = [_codex_row(f"x{i}", base_local + timedelta(days=i, minutes=30), dur=60)
                 for i in range(20)]
        block = compute_cross_llm(claude, codex)
        win = block["common_window"]
        self.assertIsNotNone(win)
        total_minutes = sum(
            mins for wk in block["weekly_share"] for mins in wk["minutes"].values()
        )
        # 20 days * (60 claude + 60 codex) = 2400 minutes total, if no
        # activity is clipped away. The UTC-midnight bug drops the first
        # local day's full hour of activity for both sources (120 minutes),
        # yielding 2280 (or, in the finding's single-source phrasing,
        # 19/20 days worth instead of 20/20).
        self.assertEqual(total_minutes, 2400)

    def test_parallel_and_matrix_clipped_to_common_window_when_healthy(self):
        # Claude has 30 days of history; codex only shows up in the last 20
        # days, in a DIFFERENT project ("legacy-tool") than the overlapping
        # window's project ("webapp"). Spec §13: cross-source comparison
        # charts (parallel heatmap, project x tool matrix) are scoped to the
        # common window when one exists and isn't degraded — activity
        # outside that window (here, claude's early solo days in
        # "old-project") must not leak into parallel/matrix.
        claude_early = [_claude_row(f"ce{i}", BASE + timedelta(days=i),
                                    project="/home/user/projects/old-project")
                        for i in range(10)]
        claude_common = [_claude_row(f"cc{i}", BASE + timedelta(days=10 + i))
                         for i in range(20)]
        codex = [_codex_row(f"x{i}", BASE + timedelta(days=10 + i, minutes=30))
                 for i in range(20)]
        block = compute_cross_llm(claude_early + claude_common, codex)
        win = block["common_window"]
        self.assertIsNotNone(win)
        self.assertFalse(win["degraded"])
        self.assertNotIn("old-project", block["project_matrix"]["projects"])
        pre_window_date = BASE.date().isoformat()  # day 0, before the window
        for d in block["parallel"]["daily_max"]:
            self.assertNotEqual(d["date"], pre_window_date)

    def test_parallel_and_matrix_full_history_when_degraded(self):
        # A degraded (< 14 day) or absent common_window must NOT drop rows
        # from parallel/project_matrix — schema stability: the blocks are
        # always emitted over full history in that case, and it's
        # report_render.py's job to suppress the exhibit, not aggregate.py's
        # job to hide the data.
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i),
                              project="/home/user/projects/old-project")
                  for i in range(30)]
        codex = [_codex_row("x0", BASE + timedelta(days=25))]  # 5-day overlap tail
        block = compute_cross_llm(claude, codex)
        self.assertTrue(block["common_window"]["degraded"])
        self.assertIn("old-project", block["project_matrix"]["projects"])

    def test_midnight_spanning_session_splits_by_day(self):
        # aggregate.py now buckets calendar days in the SYSTEM'S local zone
        # (via _parse_dt's astimezone() normalization — see P1 fix), not
        # UTC. Construct "23:30 local, crossing midnight" from the actual
        # system local offset rather than hardcoding UTC, so this test
        # passes regardless of which machine/CI timezone it runs under.
        local_offset = datetime.now().astimezone().utcoffset()
        local_tz = timezone(local_offset)
        late = datetime(2026, 6, 1, 23, 30, tzinfo=local_tz)
        claude = [_claude_row("c0", late, dur=120)]  # crosses local midnight
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

    def test_sources_detected_excludes_undetected_sources(self):
        # cross_llm.sources now always has one card per known source
        # (claude/codex/grok/antigravity), including undetected ones with
        # "detected": false and session_count 0. compute_ledger must filter
        # sources_detected to only actually-detected sources — copying every
        # card verbatim would make grok/antigravity falsely appear "detected"
        # in every report even when the user never ran them.
        metas = {f"c{i}": _claude_row(f"c{i}", BASE + timedelta(days=i))
                 for i in range(10)}
        codex = [_codex_row(f"x{i}", BASE + timedelta(days=i, minutes=30))
                 for i in range(10)]
        cross = compute_cross_llm(list(metas.values()), codex)
        ledger = compute_ledger(metas, cross)
        self.assertIn("claude", ledger["sources_detected"])
        self.assertIn("codex", ledger["sources_detected"])
        self.assertNotIn("grok", ledger["sources_detected"])
        self.assertNotIn("antigravity", ledger["sources_detected"])


class MainWiringTests(unittest.TestCase):
    """Drives aggregate.py's CLI entry point end-to-end to verify the
    "(unknown)"-bucket errors from load_cross_llm_rows reach
    cross_llm.unattributed_parse_errors in the written analysis-data.json —
    the aggregation logic itself (load_cross_llm_rows bucketing under
    "(unknown)") is already covered by LoadCrossLlmRowsTests; this covers
    only the main()-level wiring of that bucket into the output JSON."""

    @staticmethod
    def _write_minimal_session_meta(data_dir: Path):
        """aggregate.py's session-meta mode refuses to run with zero
        sessions ("Use Claude Code first"). Write one minimal real
        session-meta file so main() proceeds far enough to reach the
        cross_llm wiring under test."""
        meta_dir = data_dir / "session-meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        sid = "11111111-1111-1111-1111-111111111111"
        (meta_dir / f"{sid}.json").write_text(json.dumps({
            "session_id": sid,
            "project_path": "/home/user/projects/demo",
            "start_time": _iso(BASE),
            "duration_minutes": 10,
            "input_tokens": 100, "output_tokens": 50,
            "git_commits": 0, "git_pushes": 0,
        }), encoding="utf-8")

    def test_unattributed_errors_reach_output_json(self):
        import subprocess
        import sys
        import tempfile

        skill_dir = Path(__file__).resolve().parent.parent
        script = skill_dir / "scripts" / "aggregate.py"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            empty_data_dir = td / "usage-data"
            empty_data_dir.mkdir()
            self._write_minimal_session_meta(empty_data_dir)
            cross_rows_path = td / "cross.jsonl"
            # One line that is valid JSON but not an object (bare scalar) —
            # load_cross_llm_rows buckets this under "(unknown)" since no
            # source can be guessed from it.
            cross_rows_path.write_text(json.dumps("not-an-object") + "\n",
                                       encoding="utf-8")
            out_path = td / "analysis-data.json"
            r = subprocess.run(
                [sys.executable, str(script),
                 "--data-dir", str(empty_data_dir),
                 "--cross-llm-rows", str(cross_rows_path),
                 "--output", str(out_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(out_path.read_text())
        self.assertEqual(data["cross_llm"].get("unattributed_parse_errors"), 1)

    def test_unattributed_errors_zero_by_default(self):
        import subprocess
        import sys
        import tempfile

        skill_dir = Path(__file__).resolve().parent.parent
        script = skill_dir / "scripts" / "aggregate.py"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            empty_data_dir = td / "usage-data"
            empty_data_dir.mkdir()
            self._write_minimal_session_meta(empty_data_dir)
            out_path = td / "analysis-data.json"
            r = subprocess.run(
                [sys.executable, str(script),
                 "--data-dir", str(empty_data_dir),
                 "--output", str(out_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(out_path.read_text())
        self.assertEqual(data["cross_llm"].get("unattributed_parse_errors"), 0)


class MidnightBoundaryTests(unittest.TestCase):
    def test_window_ending_at_midnight_counts_one_day(self):
        from scripts.aggregate import _split_at_midnight
        from datetime import datetime, timezone
        s = datetime(2026, 6, 1, 23, 0, tzinfo=timezone.utc)
        e = datetime(2026, 6, 2, 0, 0, tzinfo=timezone.utc)
        pieces = list(_split_at_midnight(s, e))
        self.assertEqual([d for d, _, _ in pieces], [s.date()])

    def test_single_point_window_still_yielded(self):
        from scripts.aggregate import _split_at_midnight
        from datetime import datetime, timezone
        t = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        pieces = list(_split_at_midnight(t, t))
        self.assertEqual(len(pieces), 1)


class HeadToHeadClippedDurationTests(unittest.TestCase):
    def test_resumed_session_contributes_only_in_window_minutes(self):
        # 20-day claude history; codex has exactly TWO sessions so the
        # median discriminates clipped vs whole-session durations.
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i))
                  for i in range(20)]
        # Plain codex session late in the window, 60 in-window minutes.
        plain = _codex_row("x-plain", BASE + timedelta(days=19, minutes=30))
        # Resumed session: STARTS 10 days before the window with 600
        # pre-window minutes, then resumes for 10 minutes inside it.
        early = BASE - timedelta(days=10)
        inside = BASE + timedelta(days=5)
        resumed = {"session_id": "xr", "project_path": "/home/user/projects/webapp",
                   "start_time": early.isoformat(), "duration_minutes": 610,
                   "segments": [[early.isoformat(),
                                 (early + timedelta(minutes=600)).isoformat()],
                                [inside.isoformat(),
                                 (inside + timedelta(minutes=10)).isoformat()]],
                   "input_tokens": 500, "output_tokens": 100,
                   "source": "codex", "coverage": "full"}
        block = compute_cross_llm(claude, [plain, resumed])
        h2h = block["head_to_head"]
        self.assertIsNotNone(h2h)
        # Clipped durations [60, 10] -> median 35. The pre-fix behavior
        # (whole-session [60, 610] -> median 335) fails this assertion,
        # so the test genuinely discriminates the fix.
        self.assertEqual(h2h["codex"]["median_duration_minutes"], 35)


if __name__ == "__main__":
    unittest.main()
