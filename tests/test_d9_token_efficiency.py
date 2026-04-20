"""Tests for D9 token efficiency rubric dimension.

Spec: docs/superpowers/specs/2026-04-20-d9-token-efficiency-design.md
"""
from __future__ import annotations

import re
import pytest

from scripts.aggregate import score_d9_token_efficiency, _PATTERN_MIN_SAMPLE


def _sess(outcome: str, total_tokens: int, user_msgs: int = 5,
          cache_read: int = 0, cache_create: int = 0):
    """Minimal session dict covering the fields D9 reads."""
    return {
        "outcome": outcome,
        "total_tokens": total_tokens,
        "user_msgs": user_msgs,
        "cache_read_tokens": cache_read,
        "cache_create_tokens": cache_create,
    }


def _pool(good_count: int, good_tokens: int, not_good_count: int,
          not_good_tokens: int, **kw):
    """Build a rated pool with `good_count` good-outcome sessions and
    `not_good_count` not-good sessions, each with the given token avg."""
    good = [_sess("fully_achieved", good_tokens, **kw) for _ in range(good_count)]
    ng = [_sess("abandoned", not_good_tokens, **kw) for _ in range(not_good_count)]
    return good + ng


@pytest.mark.parametrize(
    "ratio_target, expected_score",
    [
        (0.5, 10),
        (1.0, 8),
        (1.3, 6),
        (1.8, 4),
        (3.0, 2),
    ],
)
def test_ratio_bands(ratio_target, expected_score):
    good_tok = 10_000
    ng_tok = int(good_tok * ratio_target)
    rated = _pool(6, good_tok, 6, ng_tok)
    result = score_d9_token_efficiency(rated, rated)
    assert result["score"] == expected_score


@pytest.mark.parametrize(
    "cache_read, cache_create, expected_adj",
    [
        (15, 85, -1),   # 15% → below 20%, −1
        (40, 60, 0),    # 40% → mid, no adj
        (70, 30, +1),   # 70% → ≥60%, +1
    ],
)
def test_cache_hit_adjustment(cache_read, cache_create, expected_adj):
    rated = _pool(6, 10_000, 6, 11_000,  # ratio 1.10 → base 8
                  cache_read=cache_read, cache_create=cache_create)
    result = score_d9_token_efficiency(rated, rated)
    assert result["score"] == 8 + expected_adj


def test_cache_adjustment_clamps_high():
    # base 10 + adj +1 should clamp at 10
    rated = _pool(6, 10_000, 6, 4_000,  # ratio 0.4 → base 10
                  cache_read=70, cache_create=30)
    result = score_d9_token_efficiency(rated, rated)
    assert result["score"] == 10


def test_cache_adjustment_clamps_low():
    # base 2 + adj -1 should clamp at 1
    rated = _pool(6, 10_000, 6, 40_000,  # ratio 4.0 → base 2
                  cache_read=15, cache_create=85)
    result = score_d9_token_efficiency(rated, rated)
    assert result["score"] == 1


def test_insufficient_good_sample_returns_none():
    good = [_sess("fully_achieved", 10_000) for _ in range(_PATTERN_MIN_SAMPLE - 1)]
    ng = [_sess("abandoned", 20_000) for _ in range(_PATTERN_MIN_SAMPLE + 5)]
    rated = good + ng
    result = score_d9_token_efficiency(rated, rated)
    assert result["score"] is None
    assert result["pattern"] is None
    assert "insufficient" in result["reason"]


def test_insufficient_not_good_sample_returns_none():
    good = [_sess("fully_achieved", 10_000) for _ in range(_PATTERN_MIN_SAMPLE + 5)]
    ng = [_sess("abandoned", 20_000) for _ in range(_PATTERN_MIN_SAMPLE - 1)]
    rated = good + ng
    result = score_d9_token_efficiency(rated, rated)
    assert result["score"] is None
    assert result["pattern"] is None


def test_zero_token_good_sessions_returns_none():
    good = [_sess("fully_achieved", 0) for _ in range(6)]
    ng = [_sess("abandoned", 10_000) for _ in range(6)]
    rated = good + ng
    result = score_d9_token_efficiency(rated, rated)
    assert result["score"] is None
    assert "zero-token" in result["reason"]


def test_per_turn_fragment_omitted_when_zero_turns():
    rated = _pool(6, 10_000, 6, 11_000, user_msgs=0)
    result = score_d9_token_efficiency(rated, rated)
    assert "per-turn" not in result["explanation"]


def test_cache_fragment_omitted_when_no_cache_activity():
    rated = _pool(6, 10_000, 6, 11_000,
                  cache_read=0, cache_create=0)
    result = score_d9_token_efficiency(rated, rated)
    assert "Cache hit ratio" not in result["explanation"]


def test_pattern_sentence_format():
    rated = _pool(6, 10_000, 6, 13_000)  # ratio ~1.30
    result = score_d9_token_efficiency(rated, rated)
    pat = result["pattern"]
    assert re.match(
        r"Good-outcome sessions averaged [\d,]+ tokens; "
        r"other rated sessions averaged [\d,]+ \(\d+\.\d{2}× more\)\.",
        pat,
    ), f"pattern did not match: {pat!r}"


def test_explanation_uses_other_rated_wording():
    # Spec: explanation should use "Other rated sessions" not "Not-good sessions"
    rated = _pool(6, 10_000, 6, 13_000)
    result = score_d9_token_efficiency(rated, rated)
    assert "Other rated sessions" in result["explanation"]
    assert "Not-good sessions" not in result["explanation"]


def test_per_turn_and_cache_fragments_present_when_data_available():
    rated = _pool(6, 10_000, 6, 13_000,
                  user_msgs=5, cache_read=60, cache_create=40)
    result = score_d9_token_efficiency(rated, rated)
    assert "per-turn" in result["explanation"]
    assert "Cache hit ratio" in result["explanation"]


def test_metrics_present_in_return_dict():
    rated = _pool(6, 10_000, 6, 13_000,
                  cache_read=60, cache_create=40)
    result = score_d9_token_efficiency(rated, rated)
    assert result["metric_tokens_per_good"] == 10_000
    assert result["metric_tokens_per_not_good"] == 13_000
    assert result["metric_ratio"] == 1.30
    assert result["metric_cache_hit_pct"] == 60.0


def test_explanation_ends_with_period_when_no_auxiliary_fragments():
    """Grammar bug guard: when both per-turn and cache fragments are empty,
    explanation should end with '.' not with bare ';'."""
    rated = _pool(6, 10_000, 6, 11_000, user_msgs=0,
                  cache_read=0, cache_create=0)
    result = score_d9_token_efficiency(rated, rated)
    # Must end with a period, not a semicolon
    assert result["explanation"].endswith(".")
    assert "more);" not in result["explanation"]
    # Sanity: no trailing fragments
    assert "per-turn" not in result["explanation"]
    assert "Cache hit ratio" not in result["explanation"]


def test_cache_hit_uses_sessions_arg_not_rated():
    """When sessions and rated are different pools, cache hit must be
    computed from sessions (all), not rated (subset)."""
    # rated pool: 6 good + 6 not-good with ratio 1.10 → base=8, no cache data
    rated = _pool(6, 10_000, 6, 11_000, cache_read=0, cache_create=0)
    # sessions: larger pool including extra sessions with heavy cache activity.
    # Cache hit ratio over sessions = 70% → adj=+1 → expected score 9.
    extra_cache_sessions = [
        _sess("fully_achieved", 5000, user_msgs=3,
              cache_read=70, cache_create=30)
        for _ in range(10)
    ]
    sessions = rated + extra_cache_sessions
    result = score_d9_token_efficiency(sessions, rated)
    # Base from rated ratio = 8; cache from sessions adds +1 → 9.
    assert result["score"] == 9
    assert result["metric_cache_hit_pct"] == 70.0


def test_d9_wired_into_compute_scores():
    from unittest.mock import patch
    from scripts.aggregate import compute_scores

    rated = _pool(6, 10_000, 6, 13_000, cache_read=60, cache_create=40)
    sessions = rated

    _stub = {"score": None, "reason": "stub", "pattern": None, "explanation": ""}

    with (
        patch("scripts.aggregate.score_d1_delegation", return_value=_stub),
        patch("scripts.aggregate.score_d2_rootcause", return_value=_stub),
        patch("scripts.aggregate.score_d3_prompt_quality", return_value=_stub),
        patch("scripts.aggregate.score_d4_context_mgmt", return_value=_stub),
        patch("scripts.aggregate.score_d5_interrupt", return_value=_stub),
        patch("scripts.aggregate.score_d6_tool_breadth", return_value=_stub),
        patch("scripts.aggregate.score_d7_writing", return_value=_stub),
        patch("scripts.aggregate.score_d8_time_mgmt", return_value=_stub),
    ):
        scores = compute_scores(sessions, rated, facets_coverage=100)

    assert "D9_token_efficiency" in scores
    assert scores["D9_token_efficiency"]["score"] is not None


def test_d9_en_locale_keys_present():
    from scripts.locales import t
    assert t("en", "score_d9") == "Token efficiency"
    for band in (10, 8, 6, 4, 2):
        key = f"d9_band_{band}"
        assert t("en", key).strip() != ""
        assert not t("en", key).startswith("[TODO")
    assert t("en", "d9_insufficient").strip() != ""
    assert t("en", "d9_how_it_works").strip() != ""


def test_d9_zh_tw_keys_have_todo_marker():
    """Ensure every D9 zh_TW key carries the TODO marker until
    fix/zh-tw-locale fills native translations."""
    from scripts.locales import t
    todo_keys = [
        "score_d9",
        "d9_how_it_works",
        "d9_band_10",
        "d9_band_8",
        "d9_band_6",
        "d9_band_4",
        "d9_band_2",
        "d9_insufficient",
    ]
    for key in todo_keys:
        assert "[TODO zh_TW]" in t("zh_TW", key), f"{key} missing TODO marker"
