# tests/test_cross_llm_common.py
import unittest
from datetime import datetime, timedelta, timezone

from scripts.cross_llm_common import (
    normalize_prompt, parse_ts, prompt_identity, split_segments, to_local_iso)


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


class NormalizePromptTests(unittest.TestCase):
    # Fix 3: normalize_prompt now lives here (moved from aggregate.py) so
    # the scan_*.py adapters can compute prompt_identity() at emission time.
    def test_case_punct_whitespace_collapse(self):
        self.assertEqual(
            normalize_prompt("  Fix the FLAKY test!!  (again) "),
            "fix the flaky test again")

    def test_non_string_is_empty(self):
        self.assertEqual(normalize_prompt(None), "")


class PromptIdentityTests(unittest.TestCase):
    def test_empty_input_is_none(self):
        self.assertIsNone(prompt_identity(""))
        self.assertIsNone(prompt_identity(None))

    def test_same_normalized_text_same_hash(self):
        a = prompt_identity("Fix the FLAKY test!!")
        b = prompt_identity("fix the flaky test")
        self.assertEqual(a, b)

    def test_shared_500_char_prefix_but_differing_after_is_distinct(self):
        # The scenario Fix 3 exists to prevent: two prompts sharing a
        # 500-char prefix (what adapters truncate first_prompt to) but
        # differing at char 600 must hash differently, since prompt_identity
        # is computed over the FULL text, not the truncated display copy.
        shared_prefix = "always run the full pytest suite before claiming done " * 10
        self.assertGreater(len(shared_prefix), 500)
        a = shared_prefix + "then update the changelog"
        b = shared_prefix + "then update the readme instead"
        self.assertEqual(a[:500], b[:500])
        self.assertNotEqual(prompt_identity(a), prompt_identity(b))

    def test_identical_long_prompt_same_hash_even_if_display_truncated(self):
        # An identical 600-char prompt: hashing the full text (before any
        # 500-char truncation applied for display) must match regardless of
        # how the caller later truncates first_prompt.
        long_prompt = "please refactor the ingestion retry pipeline " * 13
        self.assertGreater(len(long_prompt), 500)
        truncated_copy = long_prompt[:500]
        self.assertEqual(prompt_identity(long_prompt), prompt_identity(long_prompt))
        self.assertNotEqual(prompt_identity(long_prompt), prompt_identity(truncated_copy))


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
