# D9 Token Efficiency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add D9 Token efficiency — a ninth rubric dimension comparing average `total_tokens` per good-outcome session versus other rated sessions, with overall cache hit ratio as a ±1 score adjustment.

**Architecture:** New `score_d9_token_efficiency(sessions, rated)` in `scripts/aggregate.py` returns the same dict shape as D1-D8 (`score`, `explanation`, `pattern`, metrics). Wired into `compute_scores()` and the `dim_titles` dict in `build_html.py`. Locale keys added in `scripts/locales.py` (en only; zh_TW keys added as placeholders with `[TODO zh_TW]` marker for the parallel `fix/zh-tw-locale` branch). All strings rule-computed from aggregate counters — no LLM.

**Tech Stack:** Python 3, pytest, Node test runner (for chart tests that must stay green). Branch: `feat/d9-token-efficiency` (already checked out, spec committed at `7c1b949`).

**Spec:** `docs/superpowers/specs/2026-04-20-d9-token-efficiency-design.md`

**Key naming convention (verified in codebase):**
- Score dict key: `D9_token_efficiency` (matches `D1_delegation` … `D8_time_mgmt` style)
- Scoring function: `score_d9_token_efficiency`
- Locale key: `score_d9`
- Band labels: `d9_band_10`, `d9_band_8`, `d9_band_6`, `d9_band_4`, `d9_band_2`
- How-it-works: `d9_how_it_works`
- Insufficient message: `d9_insufficient`

---

## Task 1: Write failing unit tests for `score_d9_token_efficiency`

**Files:**
- Create: `tests/test_d9_token_efficiency.py`

- [ ] **Step 1: Inspect existing test helper patterns**

Run: `grep -n "def _make_session\|def make_session\|def session_fixture" tests/*.py | head -10`

Expected: find any shared session-builder helpers. If `tests/conftest.py` or `tests/test_aggregate.py` has a `_make_session` helper, reuse it; otherwise the test file creates its own inline helper (shown in Step 2).

- [ ] **Step 2: Write the test file**

Create `tests/test_d9_token_efficiency.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd ~/Projects/cc-user-autopsy && python -m pytest tests/test_d9_token_efficiency.py -v 2>&1 | tail -30`

Expected: ALL tests fail (or collection fails) with `ImportError: cannot import name 'score_d9_token_efficiency'`.

- [ ] **Step 4: Commit the failing tests**

Run:
```bash
cd ~/Projects/cc-user-autopsy
git add tests/test_d9_token_efficiency.py
git commit -m "test(d9): failing unit tests for token efficiency rubric"
```

---

## Task 2: Implement `score_d9_token_efficiency`

**Files:**
- Modify: `scripts/aggregate.py` (add function after `score_d8_time_mgmt` which ends around line 708)

- [ ] **Step 1: Confirm the insertion point**

Run: `grep -n "^def score_d8_time_mgmt\|^def compute_scores" scripts/aggregate.py`

Expected output:
```
656:def score_d8_time_mgmt(sessions, rated):
711:def compute_scores(sessions, rated, facets_coverage):
```

Insert the new function between `score_d8_time_mgmt` (ends ~line 708) and `compute_scores` (line 711).

- [ ] **Step 2: Add the function**

Insert this block immediately before the `def compute_scores(...)` line:

```python
def score_d9_token_efficiency(sessions, rated):
    """Compare tokens per good-outcome session vs per other rated session.

    Primary signal: ratio = mean(total_tokens | not-good) / mean(total_tokens | good).
    Secondary: cache hit ratio over all sessions adjusts score by ±1.
    total_tokens is billable non-cache (input + output); cache tokens counted
    separately via cache hit ratio. Returns score=None when either rated
    subgroup is below _PATTERN_MIN_SAMPLE.
    """
    rated_good = [s for s in rated if is_good(s["outcome"])]
    rated_not_good = [s for s in rated if not is_good(s["outcome"])]
    if len(rated_good) < _PATTERN_MIN_SAMPLE or len(rated_not_good) < _PATTERN_MIN_SAMPLE:
        return {
            "score": None,
            "reason": "insufficient good/not-good sample",
            "pattern": None,
        }

    tokens_per_good = sum(s["total_tokens"] for s in rated_good) / len(rated_good)
    tokens_per_not_good = sum(s["total_tokens"] for s in rated_not_good) / len(rated_not_good)
    if tokens_per_good <= 0:
        return {
            "score": None,
            "reason": "zero-token good sessions",
            "pattern": None,
        }
    ratio = tokens_per_not_good / tokens_per_good

    turns_good = sum(s["user_msgs"] for s in rated_good)
    turns_not_good = sum(s["user_msgs"] for s in rated_not_good)
    tokens_per_turn_good = (
        sum(s["total_tokens"] for s in rated_good) / turns_good
        if turns_good > 0 else None
    )
    tokens_per_turn_not_good = (
        sum(s["total_tokens"] for s in rated_not_good) / turns_not_good
        if turns_not_good > 0 else None
    )

    cache_read_all = sum(s.get("cache_read_tokens", 0) or 0 for s in sessions)
    cache_create_all = sum(s.get("cache_create_tokens", 0) or 0 for s in sessions)
    cache_total = cache_read_all + cache_create_all
    cache_hit = cache_read_all / cache_total if cache_total > 0 else None

    if ratio <= 0.9:
        base = 10
    elif ratio <= 1.1:
        base = 8
    elif ratio <= 1.5:
        base = 6
    elif ratio <= 2.0:
        base = 4
    else:
        base = 2

    adj = 0
    if cache_hit is not None:
        if cache_hit < 0.20:
            adj = -1
        elif cache_hit >= 0.60:
            adj = +1
    score = max(1, min(10, base + adj))

    per_turn_frag = ""
    if tokens_per_turn_good is not None and tokens_per_turn_not_good is not None:
        per_turn_frag = (
            f" per-turn: {tokens_per_turn_not_good:,.0f} "
            f"vs {tokens_per_turn_good:,.0f};"
        )
    cache_frag = (
        f" Cache hit ratio {cache_hit*100:.0f}%." if cache_hit is not None else ""
    )
    explanation = (
        f"Other rated sessions averaged {tokens_per_not_good:,.0f} tokens "
        f"versus {tokens_per_good:,.0f} for good outcomes "
        f"({ratio:.2f}× more);"
        f"{per_turn_frag}{cache_frag}"
    )
    pattern = (
        f"Good-outcome sessions averaged {tokens_per_good:,.0f} tokens; "
        f"other rated sessions averaged {tokens_per_not_good:,.0f} "
        f"({ratio:.2f}× more)."
    )

    return {
        "score": score,
        "metric_tokens_per_good": round(tokens_per_good),
        "metric_tokens_per_not_good": round(tokens_per_not_good),
        "metric_ratio": round(ratio, 2),
        "metric_cache_hit_pct": round(cache_hit * 100, 1) if cache_hit is not None else None,
        "explanation": explanation,
        "pattern": pattern,
    }


```

- [ ] **Step 3: Run D9 unit tests**

Run: `cd ~/Projects/cc-user-autopsy && python -m pytest tests/test_d9_token_efficiency.py -v 2>&1 | tail -40`

Expected: all tests PASS.

- [ ] **Step 4: Run full Python test suite to catch regressions**

Run: `cd ~/Projects/cc-user-autopsy && python -m pytest 2>&1 | tail -20`

Expected: pre-existing skip count (7, per memory) unchanged; no new failures.

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/cc-user-autopsy
git add scripts/aggregate.py
git commit -m "feat(d9): add score_d9_token_efficiency

Compares mean total_tokens per good-outcome session against per
other rated session. Cache hit ratio adjusts score by ±1. Returns
None when either rated subgroup is below _PATTERN_MIN_SAMPLE."
```

---

## Task 3: Wire D9 into `compute_scores` and add locale keys

**Files:**
- Modify: `scripts/aggregate.py:720` (add `scores["D9_token_efficiency"] = ...`)
- Modify: `scripts/locales.py` (en block around line 182-189; zh_TW block around line 375-382)

- [ ] **Step 1: Add D9 to compute_scores**

Open `scripts/aggregate.py` and find:

```python
    scores["D8_time_mgmt"] = score_d8_time_mgmt(sessions, rated)
    # overall
```

Insert BEFORE the `# overall` comment:

```python
    scores["D9_token_efficiency"] = score_d9_token_efficiency(sessions, rated)
```

Resulting block:

```python
    scores["D8_time_mgmt"] = score_d8_time_mgmt(sessions, rated)
    scores["D9_token_efficiency"] = score_d9_token_efficiency(sessions, rated)
    # overall
```

- [ ] **Step 2: Add en locale keys**

Open `scripts/locales.py` and find the en block containing `"score_d8"` (around line 189). Add after `"score_d8"`:

```python
        "score_d9": "Token efficiency",
        "d9_how_it_works": (
            "Compares average tokens spent on good-outcome sessions versus "
            "other rated sessions. Heavy spending on sessions that didn't "
            "reach a good outcome suggests tokens are being burned without "
            "landing results. Cache hit ratio adjusts the score by ±1 to "
            "reflect prompt reuse."
        ),
        "d9_band_10": "Not-good sessions cost ≤0.9× of good ones — very efficient",
        "d9_band_8": "Not-good sessions cost 0.9–1.1× of good ones",
        "d9_band_6": "Not-good sessions cost 1.1–1.5× of good ones",
        "d9_band_4": "Not-good sessions cost 1.5–2.0× of good ones",
        "d9_band_2": "Not-good sessions cost >2.0× of good ones — tokens burning without results",
        "d9_insufficient": "Not enough rated good/not-good sessions to compare (need ≥5 of each).",
```

- [ ] **Step 3: Add zh_TW placeholder keys**

Find the zh_TW block containing `"score_d8"` (around line 382). Add after it:

```python
        "score_d9": "[TODO zh_TW] Token efficiency",
        "d9_how_it_works": "[TODO zh_TW] d9 how it works",
        "d9_band_10": "[TODO zh_TW] d9 band 10",
        "d9_band_8": "[TODO zh_TW] d9 band 8",
        "d9_band_6": "[TODO zh_TW] d9 band 6",
        "d9_band_4": "[TODO zh_TW] d9 band 4",
        "d9_band_2": "[TODO zh_TW] d9 band 2",
        "d9_insufficient": "[TODO zh_TW] d9 insufficient",
```

- [ ] **Step 4: Write a wiring smoke test**

Append to `tests/test_d9_token_efficiency.py`:

```python
def test_d9_wired_into_compute_scores():
    from scripts.aggregate import compute_scores
    rated = _pool(6, 10_000, 6, 13_000, cache_read=60, cache_create=40)
    sessions = rated  # compute_scores uses both args; here they're the same
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
    from scripts.locales import t
    # zh_TW placeholders are expected until fix/zh-tw-locale fills them
    assert "[TODO zh_TW]" in t("zh_TW", "score_d9")
    assert "[TODO zh_TW]" in t("zh_TW", "d9_band_10")
```

- [ ] **Step 5: Run the new tests**

Run: `cd ~/Projects/cc-user-autopsy && python -m pytest tests/test_d9_token_efficiency.py::test_d9_wired_into_compute_scores tests/test_d9_token_efficiency.py::test_d9_en_locale_keys_present tests/test_d9_token_efficiency.py::test_d9_zh_tw_keys_have_todo_marker -v 2>&1 | tail -20`

Expected: all three PASS.

- [ ] **Step 6: Run full Python suite**

Run: `cd ~/Projects/cc-user-autopsy && python -m pytest 2>&1 | tail -10`

Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
cd ~/Projects/cc-user-autopsy
git add scripts/aggregate.py scripts/locales.py tests/test_d9_token_efficiency.py
git commit -m "feat(d9): wire into compute_scores + en/zh_TW locale keys

zh_TW keys are [TODO zh_TW] placeholders; parallel fix/zh-tw-locale
branch will fill native translations."
```

---

## Task 4: Render D9 in the score table + rubric band table

**Files:**
- Modify: `scripts/build_html.py:2108-2116` (extend `dim_titles`)
- Modify: `scripts/build_html.py` (extend band table — location found in Step 2)

- [ ] **Step 1: Extend `dim_titles`**

Open `scripts/build_html.py` and find the `dim_titles = {...}` block (around line 2107). Add a new entry after `"D8_time_mgmt"`:

```python
    dim_titles = {
        "D1_delegation": t(args.locale, "score_d1"),
        "D2_root_cause": t(args.locale, "score_d2"),
        "D3_prompt_quality": t(args.locale, "score_d3"),
        "D4_context_mgmt": t(args.locale, "score_d4"),
        "D5_interrupt_judgment": t(args.locale, "score_d5"),
        "D6_tool_breadth": t(args.locale, "score_d6"),
        "D7_writing_consistency": t(args.locale, "score_d7"),
        "D8_time_mgmt": t(args.locale, "score_d8"),
        "D9_token_efficiency": t(args.locale, "score_d9"),
    }
```

- [ ] **Step 2: Locate the rubric band table**

Run: `grep -n "d8_band\|d1_band\|d8_how_it_works\|rubric" scripts/build_html.py | head -20`

Read the surrounding context to identify the band-table rendering block. There should be a loop or sequence that emits one row per dimension using the `d{N}_band_*` keys.

- [ ] **Step 3: Extend the rubric band table**

In the band-table block found in Step 2, add a D9 row using the same structure as the D8 row. The D9 row uses:
- Title: `t(locale, "score_d9")`
- How-it-works: `t(locale, "d9_how_it_works")`
- Band labels: `d9_band_10`, `d9_band_8`, `d9_band_6`, `d9_band_4`, `d9_band_2`

If the band table is a loop over a dimension list, append `"d9"` or `"D9_token_efficiency"` to that list (match whatever naming convention the loop already uses). If it's hand-unrolled per dimension, copy the D8 block and adapt keys.

Also add a footnote/caveat line under D9 mentioning cache-hit adjustment. Exact wording, in English:

```
(Score adjusts by ±1 based on overall cache hit ratio: <20% −1, ≥60% +1.)
```

Surface this either as appended text to `d9_how_it_works` (already contains the adjustment mention) or as a separate locale key `d9_cache_note`. If `d9_how_it_works` is already used verbatim, reuse it. No new locale key needed.

- [ ] **Step 4: Write render tests**

Open `tests/test_build_html_additions.py` and append:

```python
def test_d9_row_rendered_in_score_table(tmp_path, monkeypatch):
    """After D9 wiring, the score table includes a D9 row with explanation and pattern."""
    from scripts import build_html
    # Reuse the existing fixture builder in this test file (check top of file
    # for _run_build or similar helper). If none exists, generate the demo
    # report using the CLI-equivalent path the other tests in this file use.
    # Pattern-match on a known D9 locale string to confirm presence.
    html = _render_demo_html_en()  # existing helper in this test file
    assert "Token efficiency" in html
    # When D9 has sufficient sample the pattern line should render as italic prose.
    # When insufficient, the row should still render the title but show "n/a" or "—".
    # This test accepts either state; assertions are presence-based only.


def test_d9_band_labels_present_in_rubric(tmp_path):
    """Band table contains all five D9 band label strings."""
    html = _render_demo_html_en()
    assert "Not-good sessions cost ≤0.9× of good ones" in html
    assert "Not-good sessions cost >2.0× of good ones" in html


def test_d9_missing_when_demo_sample_too_small():
    """Demo fixture may not satisfy D9's 5+5 floor; the row should render
    a dash rather than crash."""
    html = _render_demo_html_en()
    # Either the D9 pattern renders, OR the insufficient-sample fallback shows.
    # Do not assert on which branch — just that render completes without error.
    assert "D9" in html or "Token efficiency" in html
```

Before running: confirm the helper `_render_demo_html_en` (or equivalent) exists in `tests/test_build_html_additions.py`. If the actual helper has a different name, rename the three test calls to match. Run:

```bash
grep -n "^def _\|^def test_" tests/test_build_html_additions.py | head -20
```

- [ ] **Step 5: Run render tests**

Run: `cd ~/Projects/cc-user-autopsy && python -m pytest tests/test_build_html_additions.py -v 2>&1 | tail -20`

Expected: all tests PASS (including the three new D9 tests).

- [ ] **Step 6: Run full Python suite**

Run: `cd ~/Projects/cc-user-autopsy && python -m pytest 2>&1 | tail -10`

Expected: no regressions.

- [ ] **Step 7: Run Node chart tests (defensive)**

Run: `cd ~/Projects/cc-user-autopsy && node --test tests/chart_layout.test.mjs 2>&1 | tail -10`

Expected: 23/23 pass (chart code is untouched by D9 but this guards against collateral damage).

- [ ] **Step 8: Commit**

```bash
cd ~/Projects/cc-user-autopsy
git add scripts/build_html.py tests/test_build_html_additions.py
git commit -m "feat(d9): render score row + rubric band table"
```

---

## Task 5: Regenerate demo report and visually verify

**Files:**
- Regenerate: `/tmp/cc-autopsy-demo/report.html`

- [ ] **Step 1: Run the demo generator**

Run: `cd ~/Projects/cc-user-autopsy && bash scripts/run_demo.sh 2>&1 | tail -20`

If `run_demo.sh` does not exist, run the equivalent CLI the README specifies. Check `README.md` section "Quick demo" for the exact invocation.

Expected: `/tmp/cc-autopsy-demo/report.html` regenerates without errors.

- [ ] **Step 2: Visually verify the D9 row**

Open `/tmp/cc-autopsy-demo/report.html` in a browser. Confirm:

1. Score table contains a row labelled `D9 · token efficiency`
2. Either a numeric score (2/4/6/8/10) with explanation + italic pattern line, OR `n/a` with insufficient-sample message — both are valid outcomes depending on demo fixture sample size
3. Rubric band table shows five D9 band descriptions
4. No layout regression to D1-D8 rows, charts, or Usage-characteristics block
5. No visible `[TODO zh_TW]` markers when viewing `?locale=en` or default

- [ ] **Step 3: If demo fixture produces `n/a`, document in commit note**

This is expected per spec appendix. Do NOT extend the demo fixture unless the user explicitly asks — the spec declared this an accepted demo limitation.

- [ ] **Step 4: Commit (if run_demo.sh or similar produced any artifact changes)**

If the demo run produced no tracked file changes, skip. Otherwise:

```bash
cd ~/Projects/cc-user-autopsy
git add -A
git status  # review what changed before committing
git commit -m "chore(d9): regenerate demo report with D9 row"
```

---

## Task 6: Self-review, push, and open PR

- [ ] **Step 1: Re-read the spec against the diff**

Run:
```bash
cd ~/Projects/cc-user-autopsy
git log --oneline main..HEAD
git diff main..HEAD --stat
```

Walk through each section of `docs/superpowers/specs/2026-04-20-d9-token-efficiency-design.md` and confirm implementation covers it. Specifically:

- Section 1a-1f: scoring function fully implemented in Task 2 ✓
- Section 2a-2d: locale + render in Tasks 3-4 ✓
- Section 3a-3b: tests in Tasks 1, 3, 4 ✓
- Non-goals: confirm no changes to D1-D8 algorithms, UC block, or charts (run `git diff main..HEAD -- scripts/aggregate.py | grep "score_d[1-8]"` — should be empty except the one-line `scores["D9_..."] =` addition near D8 wiring)

- [ ] **Step 2: Run the full test matrix one more time**

```bash
cd ~/Projects/cc-user-autopsy
python -m pytest 2>&1 | tail -10
node --test tests/chart_layout.test.mjs 2>&1 | tail -5
```

Expected: Python — all pass, pre-existing skip count unchanged. Node — 23/23 pass.

- [ ] **Step 3: Push the branch**

```bash
cd ~/Projects/cc-user-autopsy
git push -u origin feat/d9-token-efficiency
```

- [ ] **Step 4: Open the PR**

Run:
```bash
cd ~/Projects/cc-user-autopsy
gh pr create --title "feat(d9): token efficiency rubric dimension" --body "$(cat <<'EOF'
## Summary

Adds D9 Token efficiency — a ninth rubric dimension answering the question "am I burning tokens on sessions that don't reach results?"

- Primary: `ratio = mean(total_tokens | not-good) / mean(total_tokens | good)`, binned 2/4/6/8/10
- Adjustment: overall cache hit ratio adds ±1 (<20% / ≥60%)
- Sample floor: `_PATTERN_MIN_SAMPLE = 5` on each side; insufficient → `None` / `—`
- en locale only; zh_TW placeholders with `[TODO zh_TW]` marker, filled in parallel `fix/zh-tw-locale` branch

## Spec

`docs/superpowers/specs/2026-04-20-d9-token-efficiency-design.md`

## Test plan

- [ ] `pytest tests/test_d9_token_efficiency.py` — 14 new unit tests pass
- [ ] `pytest tests/test_build_html_additions.py` — 3 new D9 render tests pass, pre-existing tests unchanged
- [ ] `pytest` full suite — no regressions, pre-existing skip count preserved
- [ ] `node --test tests/chart_layout.test.mjs` — 23/23 pass (chart code untouched)
- [ ] `/tmp/cc-autopsy-demo/report.html` regenerates and renders D9 row cleanly

## Non-goals

- No changes to D1-D8 algorithms
- No Activity-panel / UC-block changes (PR #12 just merged)
- No chart changes (PR #14 just merged)
- No zh_TW translations (follow-up)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: Report the PR URL**

Capture the URL from `gh pr create` output and surface it to the user.

---

## Self-review (completed during plan drafting)

**1. Spec coverage:**

| Spec section | Covered in task |
|---|---|
| 1a sample guard | Task 2 Step 2 (explicit guard block) + Task 1 tests 6-7 |
| 1b primary ratio + per-turn | Task 2 Step 2 + Task 1 tests 1, 10 |
| 1c cache hit | Task 2 Step 2 + Task 1 tests 2-4 |
| 1d score band | Task 2 Step 2 + Task 1 tests 1-5 |
| 1e return dict | Task 2 Step 2 + Task 1 tests 7-9, 11-12 |
| 1f wiring | Task 3 Step 1 + Task 3 Step 4 test |
| 2a locale keys | Task 3 Steps 2-3 + Task 3 Step 4 tests |
| 2b rubric band table | Task 4 Steps 2-3 + Task 4 Step 4 test 2 |
| 2c score table | Task 4 Step 1 + Task 4 Step 4 test 1 |
| 2d activity panel unchanged | Task 6 Step 1 (self-check via git diff) |
| 3a unit tests | Task 1 + Task 3 Step 4 |
| 3b render tests | Task 4 Step 4 |
| Section 5 impl order | Tasks 1-6 follow the declared order |

**2. Placeholder scan:** No TBD/TODO in task bodies. All code blocks are complete. `[TODO zh_TW]` markers inside zh_TW locale strings are *intentional spec content*, not plan placeholders.

**3. Type consistency:** Score key `D9_token_efficiency` used consistently across Tasks 2/3/4/6. Function name `score_d9_token_efficiency` matches the import in Task 1 tests. Locale key `score_d9` used in Tasks 3 and 4. No naming drift.
