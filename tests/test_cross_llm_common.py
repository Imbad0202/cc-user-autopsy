# tests/test_cross_llm_common.py
import unittest
from datetime import datetime, timedelta, timezone

from scripts.cross_llm_common import parse_ts, split_segments, to_local_iso


class ParseTsTests(unittest.TestCase):
    def test_z_suffix_parses_as_utc(self):
        dt = parse_ts("2026-04-20T02:44:00.313Z")
        self.assertEqual(dt.tzinfo.utcoffset(dt), timedelta(0))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_ts("not-a-date"))
        self.assertIsNone(parse_ts(None))


class ToLocalIsoTests(unittest.TestCase):
    def test_output_carries_utc_offset(self):
        dt = datetime(2026, 4, 20, 2, 44, tzinfo=timezone.utc)
        s = to_local_iso(dt)
        # aware ISO string: ends with +HH:MM / -HH:MM offset (never bare, never Z)
        self.assertRegex(s, r"[+-]\d{2}:\d{2}$")


class SplitSegmentsTests(unittest.TestCase):
    def _ts(self, *minutes):
        base = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
        return [base + timedelta(minutes=m) for m in minutes]

    def test_single_cluster_is_one_segment(self):
        ts = self._ts(0, 5, 12, 20)
        segs = split_segments(ts)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0], [ts[0], ts[-1]])

    def test_resumed_session_splits_at_gap(self):
        # models the observed real case: rollout file resumed 10 days later
        ts = self._ts(0, 10) + self._ts(14400, 14405)  # +10 days
        segs = split_segments(ts)
        self.assertEqual(len(segs), 2)
        active = sum((e - s).total_seconds() for s, e in segs) / 60
        self.assertEqual(active, 15)  # 10 + 5, not 14405

    def test_empty_input(self):
        self.assertEqual(split_segments([]), [])


if __name__ == "__main__":
    unittest.main()
