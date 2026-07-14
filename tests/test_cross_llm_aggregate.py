# tests/test_cross_llm_aggregate.py
import unittest
from datetime import datetime, timedelta, timezone

from scripts.aggregate import compute_cross_llm, compute_ledger


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

    def test_midnight_spanning_session_splits_by_day(self):
        late = datetime(2026, 6, 1, 23, 30, tzinfo=timezone.utc)
        claude = [_claude_row("c0", late, dur=120)]  # crosses midnight
        codex = [_codex_row("x0", late + timedelta(minutes=5), dur=120)]
        block = compute_cross_llm(claude, codex)
        days = {d["date"] for d in block["parallel"]["daily_max"]}
        self.assertIn("2026-06-01", days)
        self.assertIn("2026-06-02", days)


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
