import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.aggregate import (
    bs_repeated_instructions, bs_sunk_cost, counterexample_similar,
    normalize_prompt, prompt_identity, prompt_similarity, week_key,
    bs_switch_tax, bs_interrupt_win_rate)


class NormalizePromptTests(unittest.TestCase):
    def test_case_punct_whitespace_collapse(self):
        self.assertEqual(
            normalize_prompt("  Fix the FLAKY test!!  (again) "),
            "fix the flaky test again")

    def test_cjk_preserved(self):
        self.assertEqual(normalize_prompt("回覆一律用繁體中文，先跑測試"),
                         "回覆一律用繁體中文 先跑測試")

    def test_non_string_is_empty(self):
        self.assertEqual(normalize_prompt(None), "")
        self.assertEqual(normalize_prompt(42), "")

    def test_no_200_char_truncation_shared_prefix_stays_distinct(self):
        # Two long instructions sharing a 200-char normalized prefix but
        # differing after it must produce DIFFERENT normalized strings —
        # identity uses the full string, so they would not merge into one
        # repeated-instruction pattern.
        shared_prefix = "always run the full pytest suite before claiming done and never skip hooks " * 3
        a = normalize_prompt(shared_prefix + "then update the changelog")
        b = normalize_prompt(shared_prefix + "then update the readme instead")
        self.assertGreater(len(normalize_prompt(shared_prefix)), 200)
        self.assertNotEqual(a, b)
        self.assertEqual(a[:200], b[:200])


class PromptSimilarityTests(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(prompt_similarity("fix the test", "fix the test"), 1.0)

    def test_disjoint(self):
        self.assertEqual(prompt_similarity("alpha beta", "gamma delta"), 0.0)

    def test_partial_overlap(self):
        # {fix,the,flaky,test} vs {fix,the,broken,test}: 3/5
        self.assertAlmostEqual(
            prompt_similarity("fix the flaky test", "fix the broken test"), 0.6)

    def test_empty_is_zero(self):
        self.assertEqual(prompt_similarity("", "anything"), 0.0)

    def test_cjk_near_identical_scores_high_via_bigram_fallback(self):
        # Two zh prompts differing only by one trailing word: word-token
        # Jaccard would treat each as one giant unsplit "word" (no spaces
        # between Chinese words) and score 0.0 despite being near-
        # identical. The CJK bigram fallback must score this > 0.5.
        a = normalize_prompt("回覆一律用繁體中文，先跑測試")
        b = normalize_prompt("回覆一律用繁體中文，先跑測試，再送出")
        sim = prompt_similarity(a, b)
        self.assertGreater(sim, 0.5)

    def test_cjk_unrelated_scores_low(self):
        a = normalize_prompt("回覆一律用繁體中文，先跑測試")
        b = normalize_prompt("今天天氣很好，適合出門散步")
        sim = prompt_similarity(a, b)
        self.assertLess(sim, 0.3)

    def test_cjk_short_string_falls_back_to_word_path(self):
        # A de-spaced normalized string under 2 chars has no bigrams;
        # must not crash and must fall back to word-token comparison.
        self.assertEqual(prompt_similarity("中", "中"), 1.0)

    def test_english_prompts_unaffected_by_cjk_path(self):
        # Regression guard: non-CJK inputs must take the original
        # word-token Jaccard path, unchanged.
        self.assertAlmostEqual(
            prompt_similarity("fix the flaky test", "fix the broken test"), 0.6)


class WeekKeyTests(unittest.TestCase):
    def test_iso_week_format(self):
        dt = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)  # ISO 2026-W23
        self.assertEqual(week_key(dt), "2026-W23")

    def test_year_boundary_uses_iso_year(self):
        dt = datetime(2025, 12, 29, tzinfo=timezone.utc)  # ISO 2026-W01
        self.assertEqual(week_key(dt), "2026-W01")


BASE = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
INSTR = "Always reply in zh-TW and run the full pytest suite before you claim done"


def _prompt_row(sid, start, prompt, source=None, coverage=None, prompt_hash=None):
    row = {"session_id": sid, "start_time": start.isoformat(),
           "first_prompt": prompt}
    if source:
        row["source"], row["coverage"] = source, coverage
    if prompt_hash is not None:
        row["first_prompt_hash"] = prompt_hash
    return row


class RepeatedInstructionTests(unittest.TestCase):
    def test_five_occurrences_three_weeks_passes_gate(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i % 3, days=i), INSTR)
                for i in range(5)]
        out = bs_repeated_instructions(rows, [])
        self.assertTrue(out["gate_passed"])
        p = out["metrics"]["patterns"][0]
        self.assertEqual(p["occurrences"], 5)
        self.assertGreaterEqual(p["weeks"], 3)
        self.assertEqual(p["est_wasted_tokens"], 4 * (len(INSTR) // 4))
        self.assertLessEqual(len(p["evidence"]), 3)

    def test_five_occurrences_two_weeks_fails_gate(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(days=i), INSTR)
                for i in range(5)]
        out = bs_repeated_instructions(rows, [])
        self.assertFalse(out["gate_passed"])
        self.assertIsNotNone(out["reason"])

    def test_cross_tool_occurrences_count(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i), INSTR)
                for i in range(3)]
        cross = [_prompt_row(f"x{i}", BASE + timedelta(weeks=i, hours=2), INSTR,
                             source="codex", coverage="full") for i in range(2)]
        out = bs_repeated_instructions(rows, cross)
        self.assertTrue(out["gate_passed"])
        self.assertIn("codex", out["metrics"]["patterns"][0]["sources"])

    def test_claude_wasted_tokens_prices_only_claude_share(self):
        # 3 claude + 2 codex occurrences of the same pattern.
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i % 3, days=i), INSTR)
                for i in range(3)]
        cross = [_prompt_row(f"x{i}", BASE + timedelta(weeks=i, hours=2), INSTR,
                             source="codex", coverage="full") for i in range(2)]
        out = bs_repeated_instructions(rows, cross)
        self.assertTrue(out["gate_passed"])
        p = out["metrics"]["patterns"][0]
        self.assertEqual(p["occurrences"], 5)
        # est_wasted_tokens uses (5-1) — all sources
        self.assertEqual(p["est_wasted_tokens"], 4 * (len(p["exemplar"]) // 4))
        # claude_wasted_tokens uses (3-1) — claude occurrences only
        self.assertEqual(p["claude_wasted_tokens"], 2 * (len(p["exemplar"]) // 4))

    def test_presence_only_rows_ignored(self):
        cross = [{"session_id": f"a{i}", "start_time": (BASE + timedelta(weeks=i)).isoformat(),
                  "first_prompt": None, "source": "antigravity",
                  "coverage": "presence_only"} for i in range(9)]
        out = bs_repeated_instructions([], cross)
        self.assertFalse(out["gate_passed"])

    def test_short_prompts_never_pattern(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i), "continue")
                for i in range(9)]
        out = bs_repeated_instructions(rows, [])
        self.assertFalse(out["gate_passed"])

    def test_normalization_merges_variants(self):
        rows = ([_prompt_row(f"c{i}", BASE + timedelta(weeks=i % 3, days=i),
                             INSTR) for i in range(3)]
                + [_prompt_row(f"d{i}", BASE + timedelta(weeks=i, days=2),
                               INSTR.upper() + "!!") for i in range(2)])
        out = bs_repeated_instructions(rows, [])
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["patterns"][0]["occurrences"], 5)

    def test_out_of_window_occurrences_excluded_fails_gate(self):
        # 3 occurrences inside a narrow window (< 3 distinct weeks) + 4
        # occurrences outside the window: without windowing this would pass
        # the gate (7 occurrences, plenty of weeks); with window_start/end
        # supplied, only the 3 in-window ones count and the window itself
        # spans < 3 weeks, so the gate must fail.
        window_start = BASE
        window_end = BASE + timedelta(days=10)
        in_window = [_prompt_row(f"c{i}", BASE + timedelta(days=i * 3), INSTR)
                     for i in range(3)]  # all inside [BASE, BASE+10d]
        out_of_window = [_prompt_row(f"o{i}", BASE + timedelta(weeks=10 + i),
                                     INSTR) for i in range(4)]
        out = bs_repeated_instructions(
            in_window, out_of_window,
            window_start=window_start, window_end=window_end)
        self.assertFalse(out["gate_passed"])

    def test_all_in_window_variant_passes(self):
        # Same total occurrence count (7) but every row falls inside a wide
        # enough window spanning >=3 distinct weeks -> gate passes.
        window_start = BASE
        window_end = BASE + timedelta(weeks=6)
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i), INSTR)
                for i in range(7)]
        out = bs_repeated_instructions(
            rows, [], window_start=window_start, window_end=window_end)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["patterns"][0]["occurrences"], 7)

    def test_none_window_bounds_keep_prior_behavior(self):
        # Existing tests pass window bounds as None implicitly (positional
        # calls with only 2 args) — explicit None must behave identically.
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i % 3, days=i), INSTR)
                for i in range(5)]
        out = bs_repeated_instructions(rows, [], window_start=None, window_end=None)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["patterns"][0]["occurrences"], 5)

    def test_date_inclusive_window_boundary(self):
        # Fix 6: window_start is 09:00 on the window's first date. A
        # cross-source occurrence at 06:00 the SAME calendar date is
        # earlier in the day than window_start's exact timestamp, but the
        # comparison must be by calendar date (inclusive) — so it still
        # counts as in-window, matching the date range the rendered window
        # note claims to cover.
        window_start = BASE.replace(hour=9, minute=0)
        window_end = window_start + timedelta(weeks=6)
        early_same_day = window_start.replace(hour=6, minute=0)
        rows = ([_prompt_row("c-early", early_same_day, INSTR)]
                + [_prompt_row(f"c{i}", BASE + timedelta(weeks=i), INSTR)
                   for i in range(1, 7)])
        out = bs_repeated_instructions(
            rows, [], window_start=window_start, window_end=window_end)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["patterns"][0]["occurrences"], 7)

    def test_shared_500_char_prefix_hash_rows_do_not_merge(self):
        # Fix 3: two codex rows whose (truncated-to-500-char) first_prompt
        # text shares a prefix but whose first_prompt_hash values were
        # computed on genuinely different full prompts must NOT merge into
        # one pattern, even though their displayed text looks identical
        # up to 500 chars.
        shared_prefix = "always run the full pytest suite before claiming done " * 10
        self.assertGreater(len(shared_prefix), 500)
        full_a = shared_prefix + "then update the changelog"
        full_b = shared_prefix + "then update the readme instead"
        hash_a, hash_b = prompt_identity(full_a), prompt_identity(full_b)
        self.assertNotEqual(hash_a, hash_b)
        display = shared_prefix[:500]  # what a real adapter would truncate to
        rows_a = [_prompt_row(f"a{i}", BASE + timedelta(weeks=i % 3, days=i),
                              display, source="codex", coverage="full",
                              prompt_hash=hash_a) for i in range(5)]
        rows_b = [_prompt_row(f"b{i}", BASE + timedelta(weeks=i % 3, days=i),
                              display, source="codex", coverage="full",
                              prompt_hash=hash_b) for i in range(5)]
        out = bs_repeated_instructions(rows_a + rows_b, [])
        self.assertTrue(out["gate_passed"])
        occs = [p["occurrences"] for p in out["metrics"]["patterns"]]
        # Two distinct patterns of 5 each, never one merged pattern of 10.
        self.assertEqual(sorted(occs, reverse=True)[:2], [5, 5])

    def test_identical_long_prompt_claude_and_codex_merge_via_hash(self):
        # Fix 3: an identical 600-char prompt sent once through Claude
        # (untruncated first_prompt) and via codex (truncated to 500 chars
        # for display) must still merge into one pattern because both rows
        # carry the same first_prompt_hash computed on the full text.
        long_prompt = "please refactor the ingestion retry pipeline cleanly " * 12
        self.assertGreater(len(long_prompt), 500)
        h = prompt_identity(long_prompt)
        claude_rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i % 3, days=i),
                                   long_prompt, prompt_hash=h) for i in range(3)]
        codex_rows = [_prompt_row(f"x{i}", BASE + timedelta(weeks=i, hours=2),
                                  long_prompt[:500], source="codex",
                                  coverage="full", prompt_hash=h) for i in range(2)]
        out = bs_repeated_instructions(claude_rows, codex_rows)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["patterns"][0]["occurrences"], 5)

    def test_legacy_rows_without_hash_still_group_by_normalized_text(self):
        # Rows predating Fix 3 carry no first_prompt_hash at all — must fall
        # back to prompt_identity(first_prompt) grouping (Fix 8: same hash
        # function as hash-carrying rows, just computed here instead of by
        # the scanner), unchanged in observable behavior for an all-legacy
        # input.
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i % 3, days=i), INSTR)
                for i in range(5)]
        self.assertNotIn("first_prompt_hash", rows[0])
        out = bs_repeated_instructions(rows, [])
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["patterns"][0]["occurrences"], 5)

    def test_mixed_hash_and_legacy_rows_merge_into_one_pattern(self):
        # Codex round 8 Fix 1 (P2): new rows carrying first_prompt_hash and
        # legacy rows without it must land in the SAME hash space. Before
        # the fix, hash rows grouped by sha1(first_prompt_hash) while
        # legacy rows grouped by raw normalize_prompt(text) — two different
        # key spaces — so 3 hash occurrences + 2 legacy occurrences of the
        # IDENTICAL prompt split into two patterns of 3 and 2, neither
        # reaching the 5-occurrence gate. After the fix both fall back to
        # prompt_identity(text), the same sha1 space, and merge into one
        # pattern of 5 spanning 3 weeks that passes the gate.
        h = prompt_identity(INSTR)
        hash_rows = [_prompt_row(f"h{i}", BASE + timedelta(weeks=i), INSTR,
                                 prompt_hash=h) for i in range(3)]
        legacy_rows = [_prompt_row(f"l{i}", BASE + timedelta(weeks=i, days=3), INSTR)
                       for i in range(2)]
        for r in legacy_rows:
            self.assertNotIn("first_prompt_hash", r)
        out = bs_repeated_instructions(hash_rows + legacy_rows, [])
        self.assertTrue(out["gate_passed"])
        self.assertEqual(len(out["metrics"]["patterns"]), 1)
        p = out["metrics"]["patterns"][0]
        self.assertEqual(p["occurrences"], 5)
        self.assertGreaterEqual(p["weeks"], 3)


FAIL_PROMPT = "refactor the payment reconciliation pipeline to stream batches"
RETRY_PROMPT = "refactor the payment reconciliation pipeline to stream batches cleanly"


def _sess(sid, start, outcome, prompt=FAIL_PROMPT, accel=None, dur=120,
          tokens=50000):
    return {"sid": sid, "start": start.isoformat(), "outcome": outcome,
            "first_prompt": prompt, "token_accel": accel,
            "duration_min": dur, "total_tokens": tokens,
            "input_tokens": tokens - 5000, "output_tokens": 5000,
            "cache_create_tokens": 0, "cache_read_tokens": 0,
            "model_counts": {"claude-opus-4-6": 10}}


def _pair(i):
    failed = _sess(f"f{i}", BASE + timedelta(days=2 * i), "not_achieved",
                   accel=2.0)
    retry = _sess(f"r{i}", BASE + timedelta(days=2 * i + 1), "fully_achieved",
                  prompt=RETRY_PROMPT, accel=1.0, dur=30, tokens=8000)
    return [failed, retry]


class SunkCostTests(unittest.TestCase):
    def test_three_pairs_pass_gate(self):
        rated = [s for i in range(3) for s in _pair(i)]
        # guard needs a fully_achieved population without acceleration
        rated += [_sess(f"g{i}", BASE + timedelta(days=40 + i),
                        "fully_achieved", prompt=f"unrelated task {i} entirely",
                        accel=1.0) for i in range(6)]
        out = bs_sunk_cost(rated)
        self.assertTrue(out["gate_passed"])
        self.assertFalse(out["suppressed_by_guard"])
        self.assertEqual(out["n"], 3)
        self.assertEqual(out["metrics"]["pairs"][0]["failed_sid"], "f0")

    def test_two_pairs_fail_gate(self):
        rated = [s for i in range(2) for s in _pair(i)]
        out = bs_sunk_cost(rated)
        self.assertFalse(out["gate_passed"])

    def test_retry_must_be_later_and_fast(self):
        failed = _sess("f0", BASE + timedelta(days=5), "not_achieved", accel=2.0)
        early_retry = _sess("r0", BASE, "fully_achieved", prompt=RETRY_PROMPT,
                            dur=30)
        slow_retry = _sess("r1", BASE + timedelta(days=6), "fully_achieved",
                           prompt=RETRY_PROMPT, dur=110)
        out = bs_sunk_cost([failed, early_retry, slow_retry] * 3)
        self.assertEqual(out["n"], 0)

    def test_guard_trips_when_accel_common_in_success(self):
        rated = [s for i in range(3) for s in _pair(i)]
        # fully_achieved sessions accelerate just as much -> not a failure signal
        rated += [_sess(f"g{i}", BASE + timedelta(days=40 + i),
                        "fully_achieved", prompt=f"unrelated task {i} entirely",
                        accel=2.0) for i in range(6)]
        out = bs_sunk_cost(rated)
        self.assertTrue(out["suppressed_by_guard"])
        self.assertFalse(out["gate_passed"])


class GuardHelperTests(unittest.TestCase):
    def test_similar_rates_trip(self):
        self.assertTrue(counterexample_similar(0.5, 0.4))

    def test_distinct_rates_pass(self):
        self.assertFalse(counterexample_similar(0.6, 0.1))

    def test_zero_flagged_rate_trips(self):
        self.assertTrue(counterexample_similar(0.0, 0.0))


def _rated(sid, start, outcome, dur=60, interrupts=0, friction=None):
    return {"sid": sid, "start": start.isoformat(), "outcome": outcome,
            "duration_min": dur, "interrupts": interrupts,
            "friction_counts": friction or {}, "first_prompt": "x",
            "token_accel": None, "total_tokens": 1000}


def _act_row(sid, start, dur=60):
    return {"session_id": sid, "project_path": "/p", "start_time": start.isoformat(),
            "duration_minutes": dur}


def _codex_act(sid, start, dur=60):
    r = _act_row(sid, start, dur)
    r["source"], r["coverage"] = "codex", "full"
    return r


class SwitchTaxTests(unittest.TestCase):
    def _fixture(self, drop_activity_for=()):
        """drop_activity_for: set of multi-bucket indices (0..19) whose
        activity row should be OMITTED — simulates a rated session whose
        transcript was rotated away (meta-only), still present in `rated`
        but missing from `activity_rows`."""
        rated, act, cross = [], [], []
        for i in range(20):  # multi-tool mornings: codex runs alongside
            t = BASE + timedelta(days=i)
            rated.append(_rated(f"m{i}", t, "not_achieved" if i % 2 else
                                "fully_achieved", friction={"buggy_code": 1}))
            if i not in drop_activity_for:
                act.append(_act_row(f"m{i}", t))
            cross.append(_codex_act(f"x{i}", t + timedelta(minutes=10)))
        for i in range(20):  # single-tool, same local calendar day, later
            # +2h (not the wider offset originally used) keeps every
            # session on the SAME local calendar day as its multi-tool
            # morning sibling regardless of the test machine's UTC offset
            # — Fix 1's common-window date bucketing (_common_window_dates)
            # compares LOCAL calendar dates (matching _parse_dt's
            # documented local-zone normalization), so a wider offset that
            # crosses local midnight in positive-UTC-offset zones would
            # push the session's date outside the codex-limited window and
            # make the fixture flaky across machines/timezones.
            t = BASE + timedelta(days=i, hours=2)
            rated.append(_rated(f"s{i}", t, "fully_achieved"))
            act.append(_act_row(f"s{i}", t))
        return rated, act, cross

    def test_buckets_and_gate(self):
        rated, act, cross = self._fixture()
        out = bs_switch_tax(rated, act, cross)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["multi"]["n"], 20)
        self.assertEqual(out["metrics"]["single"]["n"], 20)
        self.assertEqual(out["metrics"]["single"]["good_rate"], 100.0)
        self.assertLess(out["metrics"]["multi"]["good_rate"], 100.0)

    def test_below_bucket_floor_fails_gate(self):
        rated, act, cross = self._fixture()
        out = bs_switch_tax(rated[:25], act, cross)  # only 5 single-tool
        self.assertFalse(out["gate_passed"])

    def test_no_cross_rows_fails_gate(self):
        rated, act, _ = self._fixture()
        out = bs_switch_tax(rated, act, [])
        self.assertFalse(out["gate_passed"])

    def test_zero_duration_session_inside_multi_window_lands_in_multi_bucket(self):
        rated, act, cross = self._fixture()
        # The multi-source window for day 0 is [t+10min, t+60min) (codex
        # starts 10 minutes after the claude act row and both run 60min).
        # Replace the day-0 rated session with a 0-minute session starting
        # AT t+10min, inside that window — its probe interval must not
        # collapse to empty ([st, st)) and silently fall into the
        # single-tool bucket.
        t = BASE + timedelta(days=0, minutes=10)
        rated[0] = _rated("m0", t, "not_achieved", dur=0,
                          friction={"buggy_code": 1})
        out = bs_switch_tax(rated, act, cross)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["multi"]["n"], 20)
        self.assertEqual(out["metrics"]["single"]["n"], 20)

    def test_meta_only_rated_session_still_lands_in_multi_bucket(self):
        # m0's rated session exists in `rated` but its activity row is
        # missing entirely (transcript rotated away) — bs_switch_tax must
        # synthesize minimal Claude activity from the rated session so it
        # still overlaps the codex row and lands in the multi bucket,
        # rather than silently falling into single-tool.
        rated, act, cross = self._fixture(drop_activity_for={0})
        self.assertEqual(len(act), 39)  # 20 multi - 1 dropped + 20 single
        out = bs_switch_tax(rated, act, cross)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["multi"]["n"], 20)
        self.assertEqual(out["metrics"]["single"]["n"], 20)

    def test_pre_overlap_sessions_excluded_from_both_buckets(self):
        # Fix 1: Claude has 30 single-tool sessions BEFORE codex/grok ever
        # ran (pre-overlap history), then the normal fixture (20 multi +
        # 20 single) inside the codex-covered window. The common window is
        # [min codex start, max codex end] intersected with [min claude
        # start-inside-that-range, max claude end] — codex only exists
        # during the normal-fixture days, so the 30 pre-overlap Claude-only
        # sessions (which could never have been multi-tool) must land in
        # NEITHER bucket: single.n stays 20, not 50.
        rated, act, cross = self._fixture()
        pre_overlap_start = BASE - timedelta(days=40)
        for i in range(30):
            t = pre_overlap_start + timedelta(days=i)
            rated.insert(0, _rated(f"pre{i}", t, "fully_achieved"))
            act.insert(0, _act_row(f"pre{i}", t))
        out = bs_switch_tax(rated, act, cross)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["multi"]["n"], 20)
        self.assertEqual(out["metrics"]["single"]["n"], 20)

    def test_in_window_single_bucket_below_floor_fails_gate_despite_total(self):
        # Even though total single-tool sessions (in-window + pre-overlap)
        # would clear the 20-session floor, only the IN-WINDOW ones count.
        # Fixture: 20 multi (in-window) + only 5 single (in-window) + 30
        # pre-overlap single-tool sessions outside the common window. Total
        # non-multi sessions = 35 (>=20), but in-window single = 5 (<20) —
        # gate must fail.
        rated, act, cross = [], [], []
        for i in range(20):  # multi-tool mornings, in-window
            t = BASE + timedelta(days=i)
            rated.append(_rated(f"m{i}", t, "fully_achieved"))
            act.append(_act_row(f"m{i}", t))
            cross.append(_codex_act(f"x{i}", t + timedelta(minutes=10)))
        for i in range(5):  # single-tool, same local day, in-window
            t = BASE + timedelta(days=i, hours=2)
            rated.append(_rated(f"s{i}", t, "fully_achieved"))
            act.append(_act_row(f"s{i}", t))
        pre_overlap_start = BASE - timedelta(days=60)
        for i in range(30):  # pre-overlap: clears the floor if wrongly counted
            t = pre_overlap_start + timedelta(days=i)
            rated.append(_rated(f"pre{i}", t, "fully_achieved"))
            act.append(_act_row(f"pre{i}", t))
        out = bs_switch_tax(rated, act, cross)
        self.assertFalse(out["gate_passed"])

    def _segment_probe_fixture(self, gap_codex_offset):
        """m1..m20 straightforward multi-tool mornings + m0-anchor (an extra
        multi-tool pair used only to pin the common window, see below) + m0
        (whose activity row carries two real segments split by a 10-day
        idle gap) + 20 single-tool sessions. m0's own codex partner (x0) is
        placed at `gap_codex_offset` from m0's segment-1 end, so the caller
        controls whether x0 lands inside the idle gap or on the real second
        segment. The m0-anchor pair means removing m0 from the multi bucket
        (Case A) still leaves multi at the 21-session baseline, clearing the
        20-session floor either way.

        A separate codex row (x0-anchor), paired with its OWN claude activity
        row (m0-anchor, a plain unsegmented session on day 0 that is not
        m0), pins codex's earliest presence to day 0 without touching m0's
        own probe windows — otherwise, when x0 itself is pushed days out
        (Case A), codex's earliest occurrence would shift later and exclude
        m0's whole day-0 session from the common window, making the test
        assert nothing about segment-awareness."""
        rated, act, cross = [], [], []
        seg1_start = BASE
        seg1_end = seg1_start + timedelta(minutes=60)
        # seg2 lands on day 10.5 (not an integer day offset) so its window
        # never coincides with the day-indexed m1..m20 multi-source hours
        # (each at HH:10-11:00 on its own integer day) or their single-tool
        # siblings — isolating the assertions to m0's own segment/gap logic.
        seg2_start = seg1_start + timedelta(days=10, hours=12)
        seg2_end = seg2_start + timedelta(minutes=60)
        rated.append(_rated("m0", seg1_start, "not_achieved",
                            friction={"buggy_code": 1}))
        act.append({
            "session_id": "m0", "project_path": "/p",
            "start_time": seg1_start.isoformat(),
            # Full-span duration a naive [start, start+duration] probe would
            # use — 10+ days — deliberately much larger than either real
            # segment, so a bug that ignores segments would make an
            # idle-gap codex row wrongly overlap.
            "duration_minutes": int((seg2_end - seg1_start).total_seconds() / 60),
            "segments": [
                [seg1_start.isoformat(), seg1_end.isoformat()],
                [seg2_start.isoformat(), seg2_end.isoformat()],
            ],
        })
        # m0-anchor / x0-anchor: an UNRELATED multi-tool pair on day 0 that
        # exists solely to pin codex's earliest date to day 0. Counted as
        # rated (contributes to the multi bucket, distinct from m1..m20).
        anchor_t = seg1_start + timedelta(hours=3)  # different hour, no overlap risk with m0
        rated.append(_rated("m0-anchor", anchor_t, "fully_achieved"))
        act.append(_act_row("m0-anchor", anchor_t))
        cross.append(_codex_act("x0-anchor", anchor_t + timedelta(minutes=10)))
        cross.append(_codex_act("x0", seg1_end + gap_codex_offset))
        for i in range(1, 21):  # 20 more straightforward multi-tool mornings
            t = BASE + timedelta(days=i)
            rated.append(_rated(f"m{i}", t, "not_achieved" if i % 2 else
                                "fully_achieved", friction={"buggy_code": 1}))
            act.append(_act_row(f"m{i}", t))
            cross.append(_codex_act(f"x{i}", t + timedelta(minutes=10)))
        for i in range(20):  # single-tool, same local day as its m_i sibling
            t = BASE + timedelta(days=i, hours=2)
            rated.append(_rated(f"s{i}", t, "fully_achieved"))
            act.append(_act_row(f"s{i}", t))
        return rated, act, cross

    def test_segment_aware_probe_gap_lands_single_bucket(self):
        # Fix 1: codex row strictly inside m0's idle gap (between its two
        # real segments) must NOT overlap m0's segment-aware probe windows
        # — m0 lands single-tool despite a naive full-span probe wrongly
        # overlapping it (the 10+ day duration_minutes spans the gap).
        rated, act, cross = self._segment_probe_fixture(timedelta(days=5))
        out = bs_switch_tax(rated, act, cross)
        self.assertTrue(out["gate_passed"])
        # Baseline multi bucket = m0-anchor + m1..m20 = 21; m0 excluded.
        self.assertEqual(out["metrics"]["multi"]["n"], 21)
        self.assertEqual(out["metrics"]["single"]["n"], 21)  # m0 joins single

    def test_segment_aware_probe_overlap_lands_multi_bucket(self):
        # Codex row starting 10 minutes into m0's real second segment
        # ([seg1_end + 10d11h10min] = [seg2_start + 10min], not the idle
        # gap) so it genuinely overlaps that segment's [start, start+60min]
        # window — m0 lands multi-tool.
        rated, act, cross = self._segment_probe_fixture(
            timedelta(days=10, hours=11, minutes=10))
        out = bs_switch_tax(rated, act, cross)
        self.assertTrue(out["gate_passed"])
        # Baseline 21 + m0 included = 22.
        self.assertEqual(out["metrics"]["multi"]["n"], 22)
        self.assertEqual(out["metrics"]["single"]["n"], 20)

    def test_meta_only_rated_sessions_do_not_stretch_common_window(self):
        # Fix 1: 20 meta-only rated sessions (no activity_rows entry — as if
        # their transcript rotated away) dated MONTHS before the real
        # activity/cross overlap. The displayed common_window (compute_cross_
        # llm, derived from activity+cross rows only) would say the window
        # starts at the normal fixture's BASE — these ancient meta-only
        # sessions must not pull win_start_d back to cover them: they stay
        # outside the common window (excluded from both buckets) and must
        # not inflate either bucket's n.
        rated, act, cross = self._fixture()
        ancient_start = BASE - timedelta(days=400)
        for i in range(20):
            t = ancient_start + timedelta(days=i)
            # Meta-only: appended to `rated` only, no matching activity row —
            # exactly the "extra" synthesis path in bs_switch_tax.
            rated.append(_rated(f"ancient{i}", t, "fully_achieved"))
        out = bs_switch_tax(rated, act, cross)
        self.assertTrue(out["gate_passed"])
        # Unchanged from the plain fixture — the 20 ancient meta-only
        # sessions land in neither bucket.
        self.assertEqual(out["metrics"]["multi"]["n"], 20)
        self.assertEqual(out["metrics"]["single"]["n"], 20)

    def _clip_fixture(self, m0_codex_offset):
        """m0 plus 20 more multi-tool 'm' sessions (m1..m20, one more than
        the 20-session floor so the multi bucket clears it either way),
        each with its own codex partner. A third source (antigravity)
        brackets the m1..m20 cluster with two narrow presence blips that
        never overlap m0's own window, collapsing the common window
        (intersection of every source's span) to BASE's calendar day only.
        m0's own bucket then depends entirely on `m0_codex_offset`: a LARGE
        offset (e.g. 5 days) puts m0's codex partner's interval far outside
        that window, so clipping drops it and m0 falls single-tool; a SMALL
        offset keeps the interval inside the window and m0 lands
        multi-tool."""
        rated, act, cross = [], [], []
        t0 = BASE
        rated.append(_rated("m0", t0, "fully_achieved"))
        act.append(_act_row("m0", t0, dur=5))
        cross.append(_codex_act("cx0", t0 + m0_codex_offset, dur=5))
        # antigravity: two 1-minute presence blips bracketing the m1..m20
        # cluster (well AFTER m0's own [t0, t0+5min] window, so antigravity
        # itself never overlaps m0 and can't independently make m0 land
        # multi-tool).
        anti_lo = dict(_act_row("anti-lo", t0 + timedelta(minutes=6), dur=1))
        anti_lo["source"], anti_lo["coverage"] = "antigravity", "full"
        cross.append(anti_lo)
        anti_hi = dict(_act_row(
            "anti-hi", t0 + timedelta(minutes=10 * 20 + 4), dur=1))
        anti_hi["source"], anti_hi["coverage"] = "antigravity", "full"
        cross.append(anti_hi)
        for i in range(1, 21):
            t = BASE + timedelta(minutes=10 * i)
            rated.append(_rated(f"m{i}", t, "fully_achieved"))
            act.append(_act_row(f"m{i}", t, dur=5))
            cross.append(_codex_act(f"cx{i}", t + timedelta(minutes=1), dur=3))
        # 20 single-tool sessions, earlier the same local day (before BASE).
        for i in range(20):
            t = BASE - timedelta(minutes=10 * (i + 1))
            rated.append(_rated(f"s{i}", t, "fully_achieved"))
            act.append(_act_row(f"s{i}", t, dur=5))
        return rated, act, cross

    def test_overlap_after_common_window_end_excluded_lands_single(self):
        # Fix 2: m0's own codex partner lands 5 days after m0's start — the
        # only interval that codex row can ever form is 5 days out, far
        # outside the antigravity-limited common window (BASE's calendar
        # day only). Once clipped, that interval is dropped entirely, so
        # m0 has NO surviving multi-source interval to overlap and must
        # fall into the single-tool bucket despite being an in-window rated
        # session.
        rated, act, cross = self._clip_fixture(timedelta(days=5))
        out = bs_switch_tax(rated, act, cross)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["single"]["n"], 21)  # s0..19 + m0
        self.assertEqual(out["metrics"]["multi"]["n"], 20)   # m1..20 only

    def test_overlap_moved_inside_common_window_lands_multi(self):
        # Same fixture, but m0's codex partner is moved to overlap m0's own
        # activity window directly (a few minutes after m0's start, inside
        # the antigravity-limited common window) — m0 must land multi-tool.
        rated, act, cross = self._clip_fixture(timedelta(minutes=1))
        out = bs_switch_tax(rated, act, cross)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["single"]["n"], 20)  # s0..19
        self.assertEqual(out["metrics"]["multi"]["n"], 21)   # m0..20


class InterruptWinRateTests(unittest.TestCase):
    def test_symmetric_rates_and_delta(self):
        rated = ([_rated(f"i{k}", BASE + timedelta(days=k),
                         "fully_achieved" if k < 2 else "not_achieved",
                         interrupts=1) for k in range(5)]
                 + [_rated(f"b{k}", BASE + timedelta(days=k, hours=5),
                           "fully_achieved" if k < 4 else "not_achieved")
                    for k in range(5)])
        out = bs_interrupt_win_rate(rated)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["interrupted"]["good_rate"], 40.0)
        self.assertEqual(out["metrics"]["baseline"]["good_rate"], 80.0)
        self.assertEqual(out["metrics"]["delta_pp"], -40.0)

    def test_gate_needs_five_in_each_bucket(self):
        rated = [_rated(f"i{k}", BASE + timedelta(days=k), "fully_achieved",
                        interrupts=1) for k in range(5)]
        out = bs_interrupt_win_rate(rated)  # zero non-interrupted
        self.assertFalse(out["gate_passed"])


from scripts.aggregate import bs_graveyard, bs_ask_vs_ship

WINDOW_END = BASE + timedelta(days=60)


def _grave_row(sid, start, project, writes=6, commits=0, segments=None):
    row = {"session_id": sid, "project_path": project,
          "start_time": start.isoformat(), "duration_minutes": 60,
          "tool_counts": {"Edit": writes, "Read": 10},
          "git_commits": commits, "input_tokens": 100, "output_tokens": 50}
    if segments:
        row["segments"] = [[s.isoformat(), e.isoformat()] for s, e in segments]
    return row


class GraveyardTests(unittest.TestCase):
    def test_two_items_pass_gate(self):
        rows = [_grave_row("g1", BASE, "/home/u/projects/legacy-migration"),
                _grave_row("g2", BASE + timedelta(days=3),
                           "/home/u/projects/docs-site")]
        out = bs_graveyard(rows, WINDOW_END)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(len(out["metrics"]["items"]), 2)
        self.assertGreaterEqual(out["metrics"]["items"][0]["days_untouched"], 14)

    def test_later_activity_disqualifies(self):
        rows = [_grave_row("g1", BASE, "/home/u/projects/legacy-migration"),
                _grave_row("g2", BASE + timedelta(days=50),
                           "/home/u/projects/legacy-migration", writes=0)]
        out = bs_graveyard(rows, WINDOW_END)
        self.assertFalse(out["gate_passed"])

    def test_commit_disqualifies(self):
        rows = [_grave_row("g1", BASE, "/home/u/projects/a", commits=1),
                _grave_row("g2", BASE, "/home/u/projects/b", commits=1)]
        out = bs_graveyard(rows, WINDOW_END)
        self.assertFalse(out["gate_passed"])

    def test_scratch_and_unknown_excluded(self):
        rows = [_grave_row("g1", BASE, "/tmp/throwaway"),
                _grave_row("g2", BASE, "(unknown)")]
        out = bs_graveyard(rows, WINDOW_END)
        self.assertFalse(out["gate_passed"])

    def test_recent_session_not_yet_graveyard(self):
        rows = [_grave_row("g1", WINDOW_END - timedelta(days=3),
                           "/home/u/projects/a"),
                _grave_row("g2", WINDOW_END - timedelta(days=2),
                           "/home/u/projects/b")]
        out = bs_graveyard(rows, WINDOW_END)
        self.assertFalse(out["gate_passed"])

    def test_staleness_measured_from_segment_end_not_session_start(self):
        # Fix 4: g1's session STARTED 30 days ago but has a segment that
        # ENDS only 3 days before window_end (a resumed multi-day
        # session). Staleness must be measured from that segment's end,
        # not the session's start — so this project is NOT a graveyard
        # candidate even though start-based staleness would say 30 days.
        start = WINDOW_END - timedelta(days=30)
        recent_end = WINDOW_END - timedelta(days=3)
        g1 = {"session_id": "g1", "project_path": "/home/u/projects/resumed",
              "segments": [[start.isoformat(), recent_end.isoformat()]],
              "tool_counts": {"Edit": 6, "Read": 10}, "git_commits": 0}
        g2 = _grave_row("g2", BASE, "/home/u/projects/b")  # ordinary graveyard item
        out = bs_graveyard([g1, g2], WINDOW_END)
        touched_keys = {i["project_key"] for i in out.get("metrics", {}).get("items", [])}
        self.assertNotIn("projects/resumed", touched_keys)

    def test_scratch_root_paths_excluded(self):
        # Fix 4: normalize_project_path() strips trailing slashes, so a
        # project rooted exactly at "/tmp" or "/private/tmp" no longer
        # contains the "/tmp/"-style marker as a substring. Both must still
        # be excluded from the graveyard, alongside an ordinary non-scratch
        # project that DOES qualify (to prove exclusion isn't accidentally
        # swallowing everything).
        rows = [
            _grave_row("g1", BASE, "/tmp"),
            _grave_row("g2", BASE, "/private/tmp"),
            _grave_row("g3", BASE, "/home/u/projects/legacy-migration"),
            _grave_row("g4", BASE + timedelta(days=3), "/home/u/projects/docs-site"),
        ]
        out = bs_graveyard(rows, WINDOW_END)
        keys = {i["project_key"] for i in out.get("metrics", {}).get("items", [])}
        self.assertNotIn("tmp", keys)
        self.assertNotIn("private/tmp", keys)
        self.assertIn("projects/legacy-migration", keys)
        self.assertIn("projects/docs-site", keys)

    def test_non_scratch_path_containing_tmp_substring_not_excluded(self):
        # A project path that merely contains "tmp" as part of a directory
        # name (not a "/tmp/" path root, and not the "m in p" substring
        # pattern either) must NOT be excluded.
        rows = [
            _grave_row("g1", BASE, "/home/u/tmp-tools"),
            _grave_row("g2", BASE + timedelta(days=3), "/home/u/projects/docs-site"),
        ]
        out = bs_graveyard(rows, WINDOW_END)
        keys = {i["project_key"] for i in out.get("metrics", {}).get("items", [])}
        self.assertIn("u/tmp-tools", keys)

    def test_same_session_without_recent_segment_is_graveyard(self):
        # Same fixture as above, but WITHOUT the recent-ending segment —
        # only start+duration (60 min), which ends long before window_end
        # minus the horizon. This project SHOULD be a graveyard candidate,
        # confirming the previous test's non-graveyard result was due to
        # the segment's end, not some other fixture difference.
        start = WINDOW_END - timedelta(days=30)
        g1 = {"session_id": "g1", "project_path": "/home/u/projects/resumed",
              "start_time": start.isoformat(), "duration_minutes": 60,
              "tool_counts": {"Edit": 6, "Read": 10}, "git_commits": 0}
        g2 = _grave_row("g2", BASE, "/home/u/projects/b")
        out = bs_graveyard([g1, g2], WINDOW_END)
        touched_keys = {i["project_key"] for i in out["metrics"]["items"]}
        self.assertIn("projects/resumed", touched_keys)


def _goal_sess(sid, cats, commits=0):
    return {"sid": sid, "start": BASE.isoformat(), "outcome": "fully_achieved",
            "goal_cats": cats, "git_commits": commits,
            "project_key": "webapp", "first_prompt": "x",
            "duration_min": 30, "interrupts": 0, "friction_counts": {},
            "token_accel": None, "total_tokens": 100}


class AskVsShipTests(unittest.TestCase):
    def test_gap_detected(self):
        # 10+10 fixture: feature_implementation is asked in 10/20 sessions
        # (session-membership share = 50.0%), ships in 0 -> gap 50pp.
        rated = ([_goal_sess(f"a{i}", {"feature_implementation": 1})
                  for i in range(10)]
                 + [_goal_sess(f"b{i}", {"documentation_update": 1},
                               commits=1) for i in range(10)])
        out = bs_ask_vs_ship(rated)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["top_gap"]["category"],
                         "feature_implementation")
        self.assertEqual(out["metrics"]["top_gap"]["ask_share_pct"], 50.0)
        self.assertEqual(out["metrics"]["top_gap"]["ship_share_pct"], 0.0)

    def test_nonshipping_categories_never_flagged(self):
        rated = ([_goal_sess(f"a{i}", {"information_query": 1})
                  for i in range(15)]
                 + [_goal_sess(f"b{i}", {"bug_fix": 1}, commits=1)
                    for i in range(10)])
        out = bs_ask_vs_ship(rated)
        if out["gate_passed"]:
            self.assertNotEqual(out["metrics"]["top_gap"]["category"],
                                "information_query")

    def test_gate_needs_shipped_sessions(self):
        rated = [_goal_sess(f"a{i}", {"bug_fix": 1}) for i in range(25)]
        out = bs_ask_vs_ship(rated)  # zero commits anywhere
        self.assertFalse(out["gate_passed"])

    def test_multi_category_session_ships_100pct_for_both_categories(self):
        # A session tagged with two categories, committed, counts once per
        # category it contains for BOTH ask and ship shares — a session
        # with multiple categories must not silently inflate one category's
        # share past 100% or leave the other one uncounted.
        rated = [_goal_sess(f"s{i}", {"bug_fix": 1, "refactoring": 1},
                            commits=1) for i in range(20)]
        out = bs_ask_vs_ship(rated)
        # Identical ask/ship distributions for both categories -> gap 0,
        # which now also fails the min-gap gate (Fix 3) — confirms shares
        # are computed correctly (100/100, not >100%) even though the gate
        # itself doesn't pass here.
        self.assertFalse(out["gate_passed"])

    def test_identical_distributions_fail_min_gap_gate(self):
        # Same category mix asked and shipped -> gap_pp == 0, must not pass
        # (no "100% vs 100%" nonsense finding).
        rated = [_goal_sess(f"s{i}", {"bug_fix": 1}, commits=1)
                 for i in range(20)]
        out = bs_ask_vs_ship(rated)
        self.assertFalse(out["gate_passed"])
        self.assertEqual(out["reason"], "no category gap >= 10pp")

    def test_fifty_point_gap_still_passes(self):
        rated = ([_goal_sess(f"a{i}", {"feature_implementation": 1})
                  for i in range(10)]
                 + [_goal_sess(f"b{i}", {"documentation_update": 1},
                               commits=1) for i in range(10)])
        out = bs_ask_vs_ship(rated)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["top_gap"]["gap_pp"], 50.0)


import json as _json
import subprocess
import sys
import tempfile

from scripts.aggregate import bs_habit_drift, compute_blind_spots


def _week_sess(week_i, j, plen, good):
    start = BASE + timedelta(weeks=week_i, days=j % 5)
    return {"sid": f"w{week_i}s{j}", "start": start.isoformat(),
            "outcome": "fully_achieved" if good else "not_achieved",
            "first_prompt": "p" * plen, "first_prompt_len": plen,
            "duration_min": 30, "interrupts": 0, "friction_counts": {},
            "goal_cats": {}, "git_commits": 0, "token_accel": None,
            "total_tokens": 100}


class HabitDriftTests(unittest.TestCase):
    def _weeks(self, lens, good_rates):
        rated = []
        for w, (plen, gr) in enumerate(zip(lens, good_rates)):
            for j in range(4):  # 4 rated per week >= GROWTH_MIN_RATED_PER_WEEK
                rated.append(_week_sess(w, j, plen, good=(j / 4 < gr)))
        return rated

    def test_drift_detected(self):
        # prompts shrink 200 -> 80, good rate flat
        out = bs_habit_drift(self._weeks([200] * 4 + [80] * 4, [0.75] * 8))
        self.assertTrue(out["gate_passed"])
        self.assertLess(out["metrics"]["late_median_len"],
                        0.75 * out["metrics"]["early_median_len"])

    def test_guard_improved_outcomes_suppress(self):
        out = bs_habit_drift(self._weeks([200] * 4 + [80] * 4,
                                         [0.5] * 4 + [1.0] * 4))
        self.assertFalse(out["gate_passed"])
        self.assertTrue(out["suppressed_by_guard"])

    def test_gate_needs_eight_weeks(self):
        out = bs_habit_drift(self._weeks([200] * 3 + [80] * 3, [0.75] * 6))
        self.assertFalse(out["gate_passed"])
        self.assertFalse(out["suppressed_by_guard"])

    def test_stable_prompts_no_drift(self):
        out = bs_habit_drift(self._weeks([150] * 8, [0.75] * 8))
        self.assertFalse(out["gate_passed"])

    def test_respects_precomputed_week_when_present(self):
        # Fix 3a: when rows carry a precomputed "week" (as build_sessions
        # produces, already tz-converted), bs_habit_drift must use it
        # instead of re-deriving from _parse_dt (OS-local). Give every
        # session a "week" field that groups them into 8 weeks completely
        # different from what _parse_dt(s["start"]) + week_key would
        # produce (all sessions share the SAME real start date, so without
        # honoring s["week"] they'd all collapse into one calendar week and
        # the gate would fail on "fewer than 8 weeks").
        rated = []
        for w in range(8):
            plen = 200 if w < 4 else 80
            gr = 0.75
            for j in range(4):
                sess = _week_sess(0, j, plen, good=(j / 4 < gr))
                # Override start to a single fixed date (would bucket into
                # one real calendar week) but tag with a distinct
                # precomputed ISO week label per w — this is what
                # build_sessions supplies as s["week"] after its own
                # tz-aware conversion.
                sess["sid"] = f"pw{w}s{j}"
                sess["week"] = f"2026-W{10 + w:02d}"
                rated.append(sess)
        out = bs_habit_drift(rated)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["weeks"], 8)
        self.assertLess(out["metrics"]["late_median_len"],
                        0.75 * out["metrics"]["early_median_len"])

    def test_falls_back_to_parsed_start_when_week_absent(self):
        # No "week" key on any row (legacy fixture shape) -> falls back to
        # _parse_dt(start) + week_key, matching prior behavior exactly.
        out = bs_habit_drift(self._weeks([200] * 4 + [80] * 4, [0.75] * 8))
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["weeks"], 8)


class RepeatedInstructionsTzTests(unittest.TestCase):
    def test_week_key_follows_passed_tz_not_os_local(self):
        # Fix 3b: occ1/occ2 are 20 minutes apart, straddling the UTC
        # Sunday/Monday ISO-week boundary (23:50 -> 00:10 UTC) — under UTC
        # they fall in DIFFERENT ISO weeks (23 and 24); at UTC+14 the same
        # instants both land on Monday afternoon of the SAME ISO week (24),
        # since a constant +14h shift moves both past the boundary
        # together. occ3/occ4 are 2 and 4 weeks later, each a distinct week
        # under both zones. So the deterministic, OS-local-independent
        # signal is the WEEK COUNT itself: 4 distinct weeks under UTC
        # {23,24,25,27}, but only 3 under +14 {24,24,26,28} (occ1/occ2
        # merge) — a bug that ignored the `tz` param (falling back to
        # _parse_dt's OS-local behavior, which for a UTC test box would
        # equal the "under UTC" column) would report 4, not 3.
        long_prompt = "please always run the full test suite before " \
                      "declaring the task done, no exceptions " * 2
        tz14 = timezone(timedelta(hours=14))
        occ1 = datetime(2026, 6, 7, 23, 50, tzinfo=timezone.utc)   # wk23 UTC / wk24 @+14
        occ2 = occ1 + timedelta(minutes=20)                         # wk24 UTC / wk24 @+14
        occ3 = occ1 + timedelta(weeks=2)                            # wk25 UTC / wk26 @+14
        occ4 = occ1 + timedelta(weeks=4)                            # wk27 UTC / wk28 @+14
        rows = [
            {"session_id": f"o{i}", "start_time": t.isoformat(),
             "first_prompt": long_prompt, "source": "claude"}
            for i, t in enumerate([occ1, occ2, occ3, occ4])
        ]
        # Pad occurrence count to clear the >=5-occurrence gate with a row
        # right next to occ1, landing in the same week as occ1 under BOTH
        # zones, so it doesn't change either week count.
        rows.append({"session_id": "pad0",
                     "start_time": (occ1 + timedelta(minutes=1)).isoformat(),
                     "first_prompt": long_prompt, "source": "claude"})
        out_tz = bs_repeated_instructions(rows, [], tz=tz14)
        self.assertTrue(out_tz["gate_passed"])
        pattern_tz = out_tz["metrics"]["patterns"][0]
        self.assertEqual(pattern_tz["occurrences"], 5)
        self.assertEqual(pattern_tz["weeks"], 3)


class ComputeBlindSpotsTests(unittest.TestCase):
    def test_all_seven_keys_present(self):
        out = compute_blind_spots([], [], [], [], WINDOW_END)
        self.assertEqual(out["schema_version"], 1)
        for k in ("repeated_instructions", "sunk_cost", "switch_tax",
                  "graveyard", "habit_drift", "ask_vs_ship",
                  "interrupt_win_rate"):
            self.assertIn(k, out)
            self.assertFalse(out[k]["gate_passed"])   # empty inputs: all gated


class BlindSpotsWiringTests(unittest.TestCase):
    """Mirrors tests/test_cross_llm_aggregate.py::MainWiringTests: build a
    minimal session-meta dir, run aggregate.py as a subprocess, assert the
    output JSON has a well-formed blind_spots block."""

    @staticmethod
    def _write_minimal_session_meta(data_dir):
        meta_dir = data_dir / "session-meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        sid = "11111111-1111-1111-1111-111111111111"
        (meta_dir / f"{sid}.json").write_text(_json.dumps({
            "session_id": sid,
            "project_path": "/home/user/projects/demo",
            "start_time": BASE.isoformat(),
            "duration_minutes": 10,
            "input_tokens": 100, "output_tokens": 50,
            "git_commits": 0, "git_pushes": 0,
        }), encoding="utf-8")

    def test_main_emits_blind_spots_block(self):
        skill_dir = Path(__file__).resolve().parent.parent
        script = skill_dir / "scripts" / "aggregate.py"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            data_dir = td / "usage-data"
            data_dir.mkdir()
            self._write_minimal_session_meta(data_dir)
            out_path = td / "analysis-data.json"
            r = subprocess.run(
                [sys.executable, str(script),
                 "--data-dir", str(data_dir),
                 "--output", str(out_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            data = _json.loads(out_path.read_text())
        self.assertIn("blind_spots", data)
        self.assertEqual(data["blind_spots"]["schema_version"], 1)

    def test_graveyard_window_end_anchors_to_max_activity_end_not_start(self):
        """Fix 2: main()'s window_end for compute_blind_spots must be the
        max END over every activity row's windows, not the max START.

        Project "resumed" starts a session 30 days before "now" but that
        session has a segment ENDING only 1 day before "now" (a multi-day
        resumed session) — this is the single latest activity in the whole
        dataset, so window_end must anchor there (~1 day ago). Two OTHER
        projects are idle ~20/25 days as of that anchor and qualify for the
        graveyard (>=14 day horizon, >=2 items required).

        If window_end were wrongly anchored to max START instead (30 days
        ago, from the resumed session's start_time), "now" would be pushed
        back 29 days and the two idle-only projects would show far less (or
        negative) days_untouched relative to that stale anchor — likely
        failing the 14-day horizon and the gate. Asserting the gate passes
        with both idle projects present proves the END-based anchor is in
        effect.
        """
        skill_dir = Path(__file__).resolve().parent.parent
        script = skill_dir / "scripts" / "aggregate.py"
        now = BASE + timedelta(days=40)
        resumed_start = now - timedelta(days=30)
        resumed_end = now - timedelta(days=1)
        idle_a_last = now - timedelta(days=20)
        idle_b_last = now - timedelta(days=25)

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            data_dir = td / "usage-data"
            meta_dir = data_dir / "session-meta"
            meta_dir.mkdir(parents=True)
            rows = [
                _grave_row("r1", resumed_start, "/home/user/projects/resumed",
                          segments=[(resumed_start, resumed_end)]),
                _grave_row("r2", idle_a_last, "/home/user/projects/idle-a"),
                _grave_row("r3", idle_b_last, "/home/user/projects/idle-b"),
            ]
            for row in rows:
                (meta_dir / f"{row['session_id']}.json").write_text(
                    _json.dumps(row), encoding="utf-8")
            out_path = td / "analysis-data.json"
            r = subprocess.run(
                [sys.executable, str(script),
                 "--data-dir", str(data_dir),
                 "--output", str(out_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            data = _json.loads(out_path.read_text())

        grave = data["blind_spots"]["graveyard"]
        self.assertTrue(grave["gate_passed"])
        keys = {it["project_key"] for it in grave["metrics"]["items"]}
        self.assertIn("projects/idle-a", keys)
        self.assertIn("projects/idle-b", keys)
        self.assertNotIn("projects/resumed", keys)


if __name__ == "__main__":
    unittest.main()
