"""Behavioral tests for scripts/narrative_zh.py. Mirrors test_narrative_en.py
but also enforces the no-em-dash rule on runtime output (narrative modules
produce prose strings that flow into the HTML report)."""
from __future__ import annotations

import pytest

from scripts import narrative_zh as N
from tests._narrative_fixtures import ALL_DIM_FIXTURES, d9_fixture_no_cache


@pytest.mark.parametrize("dim", sorted(ALL_DIM_FIXTURES.keys()))
def test_explanation_returns_non_empty_string(dim):
    fn = getattr(N, f"{dim}_explanation")
    out = fn(ALL_DIM_FIXTURES[dim]())
    assert isinstance(out, str) and out.strip(), f"{dim}_explanation returned empty"
    assert "—" not in out, f"{dim}_explanation contains em-dash"


@pytest.mark.parametrize("dim", sorted(ALL_DIM_FIXTURES.keys()))
def test_pattern_returns_non_empty_string(dim):
    fn = getattr(N, f"{dim}_pattern")
    out = fn(ALL_DIM_FIXTURES[dim]())
    assert isinstance(out, str) and out.strip(), f"{dim}_pattern returned empty"
    assert "—" not in out, f"{dim}_pattern contains em-dash"


def test_d1_explanation_cites_both_numbers():
    out = N.d1_explanation(ALL_DIM_FIXTURES["d1"]())
    assert "97%" in out
    assert "70%" in out


def test_d9_explanation_omits_cache_when_none():
    out = N.d9_explanation(d9_fixture_no_cache())
    assert "Cache" not in out


def test_d9_explanation_includes_cache_when_present():
    out = N.d9_explanation(ALL_DIM_FIXTURES["d9"]())
    assert "Cache 命中率" in out
    assert "96%" in out


def test_outcome_label_known_values():
    assert N.outcome_label("fully_achieved") == "完全達成"
    assert N.outcome_label("partially_achieved") == "部分達成"


def test_outcome_label_unknown_falls_through():
    assert N.outcome_label("some_new_category") == "some_new_category"


def test_evidence_badge_known_values():
    assert N.evidence_badge("high_friction") == "摩擦最高"
    assert N.evidence_badge("top_token") == "Token 用量最多"


def test_evidence_badge_unknown_falls_through():
    assert N.evidence_badge("mystery_tag") == "mystery_tag"


def test_no_facet_label():
    assert N.no_facet_label() == "（無 facet）"


def test_methodology_functions_return_non_empty():
    assert N.methodology_subtitle().strip()
    assert N.methodology_sampling_body().strip()
    assert N.methodology_caveats_body().strip()


def test_zh_narrative_contains_no_em_dash_in_static_methodology():
    for fn in (N.methodology_subtitle, N.methodology_sampling_body, N.methodology_caveats_body):
        assert "—" not in fn(), f"{fn.__name__} contains em-dash"
