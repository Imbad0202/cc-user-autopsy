# D9 Token efficiency: good-vs-not-good token ratio with cache hit adjustment

**Status:** Draft — pending user review (2026-04-20)
**Scope:** `feat/d9-token-efficiency` branch, targeting a follow-up PR after #12/#13/#14
**Base:** `main@229c382` (post PR #14 chart-rendering merge)
**Related:** PR #12 `feat/usage-inspired-rubric` (merged — provides pattern/explanation house style); `fix/zh-tw-locale` (parallel follow-up, will fill D9 zh_TW keys)

## Problem

The user's original prompt that triggered this branch: *"token 量多不等於有效，應該要能呈現使用者是否有效地使用 token 而不是亂燒。"*

`cc-user-autopsy` already reports token totals in tiles and a weekly chart, but nothing connects token spend to outcome quality. A session that burned 400k tokens and ended in `abandoned` looks identical in the current report to a session that burned 400k tokens and ended in `fully_achieved`. The rubric scores D1-D8 cover delegation, root-cause, prompt quality, context, interruptions, tool breadth, writing, and time-of-day — none of them read cost.

Three gaps:

1. No dimension grounds "efficient use" in outcome data. Token tiles and the weekly token chart are descriptive, not diagnostic.
2. Cache hit ratio is visible only as a raw number in cost estimation; the rubric doesn't say whether the user's cache reuse is healthy or wasted.
3. The user cannot answer the question "am I spending tokens where they land results, or am I burning them on sessions that don't?"

## Goals

- Add a ninth rubric dimension — D9 Token efficiency — that compares average `total_tokens` per good-outcome session against per other rated session, as a ratio.
- Emit one pattern sentence contrasting the two group averages, in the same house style as D1-D8.
- Adjust the score by ±1 based on overall cache hit ratio, so healthy cache reuse shows up as a signal distinct from the outcome-linked ratio.
- Preserve symmetric sample floor (`_PATTERN_MIN_SAMPLE = 5` on each side) for both score and pattern; insufficient samples return `None` and render as `—`.

## Non-goals

- LLM-generated explanations or patterns. Every string is rule-computed from aggregate counters — consistent with PR #12 house style.
- Activity-panel changes. The five `uc_*` Usage-characteristics items from PR #12 stay as-is. D9 lives entirely in the score table.
- Chart rendering. D9 is text-only. No new canvas, no new SVG.
- Changes to D1-D8 algorithms, thresholds, or pattern sentences.
- zh_TW translations. D9 keys land with `[TODO zh_TW]` markers and are filled in the parallel `fix/zh-tw-locale` follow-up branch.
- Cost estimation (USD) changes. The existing cost tile stays untouched.

## Decisions (from 2026-04-20 brainstorm)

| # | Decision | Choice | Reasoning |
|---|---|---|---|
| Q1 | Score band structure | **A. Symmetric ratio ladder + cache hit ±1** | Matches frozen memory design. Direct, interpretable. Cache hit as adjustment (not primary) keeps the ratio as the headline. |
| Q2 | Sample guard | **A. Symmetric `_PATTERN_MIN_SAMPLE` for both score and pattern** | Identical to D2 guard pattern. Returns `None` for both when either side is short. |
| Q3 | Good/bad definition | **D. Good vs not-good binary using existing `is_good()`** | No `is_bad()` helper exists in codebase. D1-D8 already contrast via language-neutral splits (`non_iter`, `non_interrupted`) — never invoking a "bad" category. Wording says "other rated sessions". |
| Q4 | Unit | **C. Per-session primary + per-turn secondary** | Per-session is the headline ratio (memory-frozen). Per-turn numbers land in `explanation` as a secondary grounding, which controls for session length without changing the score. |
| Q5 | Cache hit scope | **A. All sessions** | Cache reuse is a habit signal (stable prompt prefix, long-running projects), not an outcome signal. Computed once across all sessions, applied as score adjustment. |
| Q6 | Pattern wording | **A. Averaged X; other rated sessions averaged Y (Z× more)** | Most directly answers the user's original question. Mirrors D1-D8 contrast grammar. |

## Wording convention

Two phrasings coexist intentionally:

- **Band table labels** use `"Not-good sessions cost X× of good ones"` — short, scannable, suitable for a one-line band description.
- **Pattern and explanation sentences** use `"other rated sessions"` — precise complement of `is_good()`, avoids the "bad" framing that the codebase never commits to (no `is_bad()` helper exists; D1-D8 pattern sentences always use language-neutral splits).

Tests assert both phrasings separately so drift in either direction is caught.

## Architecture

```
scripts/aggregate.py         # + score_d9_token_efficiency(sessions, rated)
                             # aggregate_sessions() wires d9 into scores dict
scripts/locales.py           # + 7 en keys; zh_TW placeholders with [TODO zh_TW]
scripts/build_html.py        # rubric band table grows D9 row; score render loop grows d9 entry
tests/test_d9_token_efficiency.py       # NEW — 7 unit tests
tests/test_build_html_additions.py      # extend with 3 D9 render tests
```

## Section 1 — Data model (`aggregate.py`)

### 1a. Function signature and sample guard

```python
def score_d9_token_efficiency(sessions, rated):
    rated_good = [s for s in rated if is_good(s["outcome"])]
    rated_not_good = [s for s in rated if not is_good(s["outcome"])]
    if len(rated_good) < _PATTERN_MIN_SAMPLE or len(rated_not_good) < _PATTERN_MIN_SAMPLE:
        return {"score": None, "reason": "insufficient good/not-good sample", "pattern": None}
```

`sessions` is all sessions (used for overall cache hit). `rated` is the subset with non-empty outcome, passed in by `aggregate_sessions()` the same way D1, D5, D7, D8 receive it.

### 1b. Primary ratio and per-turn auxiliary

```python
tokens_per_good = sum(s["total_tokens"] for s in rated_good) / len(rated_good)
tokens_per_not_good = sum(s["total_tokens"] for s in rated_not_good) / len(rated_not_good)
ratio = tokens_per_not_good / tokens_per_good if tokens_per_good > 0 else None
```

If `tokens_per_good == 0` (all good sessions had zero billable tokens — degenerate), return `{"score": None, "reason": "zero-token good sessions", "pattern": None}`.

Per-turn secondary:

```python
turns_good = sum(s["user_msgs"] for s in rated_good)
turns_not_good = sum(s["user_msgs"] for s in rated_not_good)
tokens_per_turn_good = (
    sum(s["total_tokens"] for s in rated_good) / turns_good if turns_good > 0 else None
)
tokens_per_turn_not_good = (
    sum(s["total_tokens"] for s in rated_not_good) / turns_not_good if turns_not_good > 0 else None
)
```

Note: `total_tokens` in the session object is `input + output` only (aggregate.py line 288) — cache tokens are NOT included. This is intentional for D9: the ratio measures billable non-cache spend; cache is reflected via hit ratio.

### 1c. Cache hit (overall, not grouped)

```python
cache_read_all = sum(s.get("cache_read_tokens", 0) or 0 for s in sessions)
cache_create_all = sum(s.get("cache_create_tokens", 0) or 0 for s in sessions)
cache_total = cache_read_all + cache_create_all
cache_hit = cache_read_all / cache_total if cache_total > 0 else None
```

`or 0` guards against `None` values, matching the pattern at aggregate.py line 94.

### 1d. Score band with cache adjustment

```python
if ratio <= 0.9:   base = 10
elif ratio <= 1.1: base = 8
elif ratio <= 1.5: base = 6
elif ratio <= 2.0: base = 4
else:              base = 2

adj = 0
if cache_hit is not None:
    if cache_hit < 0.20:  adj = -1
    elif cache_hit >= 0.60: adj = +1

score = max(1, min(10, base + adj))
```

### 1e. Return dict

```python
per_turn_frag = ""
if tokens_per_turn_good is not None and tokens_per_turn_not_good is not None:
    per_turn_frag = f" per-turn: {tokens_per_turn_not_good:,.0f} vs {tokens_per_turn_good:,.0f};"

cache_frag = f" Cache hit ratio {cache_hit*100:.0f}%." if cache_hit is not None else ""

explanation = (
    f"Other rated sessions averaged {tokens_per_not_good:,.0f} tokens "
    f"versus {tokens_per_good:,.0f} for good outcomes ({ratio:.2f}× more);"
    f"{per_turn_frag}{cache_frag}"
)

pattern = (
    f"Good-outcome sessions averaged {tokens_per_good:,.0f} tokens; "
    f"other rated sessions averaged {tokens_per_not_good:,.0f} ({ratio:.2f}× more)."
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

### 1f. Wiring in `aggregate_sessions()`

Find the block where scores are assembled (`scores["d1"] = score_d1_delegation(...)` etc.). Append:

```python
scores["d9"] = score_d9_token_efficiency(all_sessions, rated)
```

## Section 2 — Rendering (`build_html.py`, `locales.py`)

### 2a. Locale keys (en)

Add to `scripts/locales.py`:

```python
"d9_name": "Token efficiency",
"d9_short": "Efficiency",
"d9_how_it_works": (
    "Compares average tokens spent on good-outcome sessions versus other "
    "rated sessions. Heavy spending on sessions that didn't reach a good "
    "outcome suggests tokens are being burned without landing results. "
    "Cache hit ratio adjusts the score by ±1 to reflect prompt reuse."
),
"d9_band_10": "Not-good sessions cost ≤0.9× of good ones — very efficient",
"d9_band_8":  "Not-good sessions cost 0.9–1.1× of good ones",
"d9_band_6":  "Not-good sessions cost 1.1–1.5× of good ones",
"d9_band_4":  "Not-good sessions cost 1.5–2.0× of good ones",
"d9_band_2":  "Not-good sessions cost >2.0× of good ones — tokens burning without results",
"d9_insufficient": "Not enough rated good/not-good sessions to compare (need ≥5 of each).",
```

zh_TW keys mirror the en keys with `[TODO zh_TW]` prefix, deferred to `fix/zh-tw-locale`.

### 2b. Rubric band table

Extend the existing band table in `build_html.py` with a D9 row. Row renders the five band labels from `d9_band_10/8/6/4/2` plus a footnote line noting `±1 cache hit adjustment (<20% / ≥60%)`.

### 2c. Score table integration

`build_html.py` iterates scores. Likely a hard-coded list `["d1", "d2", ..., "d8"]` somewhere. Implementation task: `grep -n '"d8"' scripts/ tests/` to locate every such list and extend to `d9`. No new DOM structure — D9 slots into existing score-tile + explanation + pattern layout.

### 2d. Activity panel

Unchanged. The five `uc_*` items from PR #12 are the Usage-characteristics block; D9 does not touch them.

## Section 3 — Tests

### 3a. `tests/test_d9_token_efficiency.py` (new)

1. `test_ratio_bands` — parametrized 5 cases: ratio=0.5 → score=10, 1.0 → 8, 1.3 → 6, 1.8 → 4, 3.0 → 2 (all with cache_hit=None so no adjustment)
2. `test_cache_hit_adjustment` — parametrized: low cache (15%) → −1, mid (40%) → 0, high (70%) → +1; verify clamp when base=10 + adj=+1 stays at 10 and base=2 + adj=−1 stays at 1
3. `test_insufficient_sample_returns_none` — good=4, not-good=10 → `score is None, pattern is None, reason == "insufficient good/not-good sample"`
4. `test_zero_token_good_sessions_returns_none` — all rated_good have total_tokens=0 → `score is None, reason == "zero-token good sessions"`
5. `test_per_turn_fragment_omitted_when_zero_turns` — user_msgs all 0 → `explanation` doesn't contain `"per-turn"`
6. `test_cache_fragment_omitted_when_no_cache_activity` — no cache tokens → `explanation` doesn't contain `"Cache hit ratio"`
7. `test_pattern_sentence_format` — assert pattern matches `r"Good-outcome sessions averaged .+ tokens; other rated sessions averaged .+ \(\d+\.\d{2}× more\)\."`
8. `test_d9_in_scores_dict` — call `aggregate_sessions()` on a minimal fixture and verify `result["scores"]["d9"]` exists with expected keys

### 3b. `tests/test_build_html_additions.py` (extend)

9. `test_d9_band_table_row_rendered` — HTML contains the 5 band label strings from `d9_band_10/8/6/4/2`
10. `test_d9_explanation_and_pattern_rendered` — when D9 score is numeric, report HTML contains the explanation and the italic pattern line
11. `test_d9_insufficient_shows_dash` — when D9 score is `None`, score tile renders `—` and no pattern line appears

## Section 4 — Risks and mitigations

| Risk | Mitigation |
|---|---|
| `total_tokens` has `None` or negative values | `s.get("total_tokens", 0) or 0` — pattern from aggregate.py line 94 |
| Demo fixture has too few rated sessions → D9 displays `—` permanently | Test 11 covers; real-user autopsy will have sample; documented as expected demo behavior in session notes |
| `user_msgs` field name drift | Spec pins to `s["user_msgs"]` (session-object field), not `user_message_count` (meta-layer field) |
| Divide-by-zero in cache hit | Section 1c guards `cache_total > 0` |
| Hard-coded `d1..d8` lists in build_html or tests | Implementation task: `grep -n '"d8"' scripts/ tests/` and extend every occurrence |

## Section 5 — Implementation order (for writing-plans)

1. TDD: write `tests/test_d9_token_efficiency.py` — all 8 tests, expect red
2. Implement `score_d9_token_efficiency` in `aggregate.py` → tests 1-7 green
3. Wire `scores["d9"] = ...` in `aggregate_sessions()` → test 8 green
4. Add en locale keys to `locales.py`; add zh_TW `[TODO zh_TW]` placeholders
5. Add D9 row to rubric band table in `build_html.py`
6. Grep for `"d8"` lists in `scripts/` and `tests/`; extend to `d9`
7. Add tests 9-11 to `tests/test_build_html_additions.py` → green
8. Regenerate `/tmp/cc-autopsy-demo/report.html`; visual check of D9 row
9. Full test suite: `pytest` + `node --test tests/chart_layout.test.mjs`
10. Commit, push, open PR

## Appendix: sample size diagnostics

For reference when analyzing demo vs. real data:

- `_PATTERN_MIN_SAMPLE = 5` — defined at `aggregate.py:42`
- D9 requires 5 good + 5 not-good, so 10 rated minimum
- Demo fixture (generate_demo_data.py) should be audited during step 8 to confirm it satisfies D9's sample floor; if not, either extend the fixture or accept demo-level `—` (documented)
