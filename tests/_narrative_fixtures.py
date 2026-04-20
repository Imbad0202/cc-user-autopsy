"""Shared fixtures for narrative tests. Each fixture returns a complete
metrics dict for one dimension, with pattern_emit=True so pattern
functions can be tested too."""
from __future__ import annotations


def d1_fixture() -> dict:
    return {
        "score": 9,
        "metric_ta_rate_pct": 97.0,
        "metric_good_rate_with_ta_pct": 70.0,
        "pattern_emit": True,
    }


def d2_fixture() -> dict:
    return {
        "score": 6,
        "metric_iter_buggy_count": 9,
        "metric_iter_buggy_pct": 6.0,
        "pattern_emit": True,
    }


def d3_fixture() -> dict:
    return {
        "score": 5,
        "metric_pct_prompts_ge_100_chars": 20.0,
        "metric_pct_prompts_lt_20_chars": 15.0,
        "metric_bucket_median_tokens_per_commit": {"50-100": 8000},
        "metric_most_efficient_bucket": "50-100",
        "pattern_emit": True,
    }


def d4_fixture() -> dict:
    return {
        "score": 5,
        "metric_output_token_limit_sessions": 2,
        "metric_effort_no_commit_pct": 54.0,
        "metric_long_session_interrupt_rate_pct": 33.0,
        "metric_max_otl_in_one_project": 2,
        "pattern_emit": True,
    }


def d5_fixture() -> dict:
    return {
        "score": 8,
        "metric_interrupt_recovery_pct": 70.0,
        "metric_interrupted_sessions": 37,
        "pattern_emit": True,
    }


def d6_fixture() -> dict:
    return {
        "score": 7,
        "metric_mcp_rate_pct": 16.0,
        "metric_top3_share_pct": 63.0,
        "metric_top_tools": {"Bash": 100},
        "pattern_emit": True,
    }


def d7_fixture() -> dict:
    return {
        "score": 8,
        "metric_misunderstood_per_writing_session": 0.16,
        "metric_writing_sessions": 50,
        "pattern_emit": True,
    }


def d8_fixture() -> dict:
    return {
        "score": 3,
        "metric_friction_ratio_hi_lo": 39.0,
        "metric_worst_hour": {"hour": 0, "friction_per_session": 8.0},
        "metric_best_hour": {"hour": 19, "friction_per_session": 0.2},
        "pattern_emit": True,
    }


def d9_fixture() -> dict:
    return {
        "score": 10,
        "metric_tokens_per_good": 19331,
        "metric_tokens_per_not_good": 15019,
        "metric_ratio": 0.78,
        "metric_cache_hit_pct": 96.0,
        "pattern_emit": True,
    }


def d9_fixture_no_cache() -> dict:
    d = d9_fixture()
    d["metric_cache_hit_pct"] = None
    return d


ALL_DIM_FIXTURES = {
    "d1": d1_fixture,
    "d2": d2_fixture,
    "d3": d3_fixture,
    "d4": d4_fixture,
    "d5": d5_fixture,
    "d6": d6_fixture,
    "d7": d7_fixture,
    "d8": d8_fixture,
    "d9": d9_fixture,
}
