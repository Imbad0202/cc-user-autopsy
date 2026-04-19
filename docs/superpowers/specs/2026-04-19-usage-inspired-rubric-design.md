# Usage-inspired rubric: per-dim patterns, usage characteristics, disclaimers

**Status:** Draft — pending user review (2026-04-19)
**Scope:** `feat/usage-inspired-rubric` branch, targeting PR #12 candidate
**Base:** `main@37563e0` (post PR #10), branch currently zero commits ahead
**Related:** PR #11 `feat/design-tokens` (open, independent — no conflict)

## Problem

Anthropic's official `/usage` dashboard (2026-04-19 release) introduces a short section labelled "What's contributing to your limits usage?" — five percent-based characteristics, each with a concise tip. The pattern is compelling because it frames diagnostics as *independent slices* rather than a breakdown, makes the numbers actionable, and builds trust by being explicit about what the scores do and do not mean.

`cc-user-autopsy` currently presents scoring as eight dimensions × one explanatory sentence each, plus an activity panel with raw counters. Three gaps surface against the `/usage` model:

1. **No descriptive evidence** backing each dimension score — a reader sees "7/10" and a short explanation but no number that grounds *why*.
2. **No %-based narrative anywhere** — the activity panel is pure totals; there is no "of your sessions, X%…" storytelling that makes the aggregate legible.
3. **No disclaimer** that the eight dimensions do not sum. A naïve reader may add the scores and reach meaningless totals.

The official product is a plan-cost diagnostic (how your account is being billed); `cc-user-autopsy` is a skill-use diagnostic (how you collaborate with Claude Code). The two are complementary, not overlapping. But the three UX mechanics above transfer cleanly.

## Goals

- Every dimension that has enough supporting data shows one *pattern* sentence — a descriptive contrast grounded in the aggregate (no LLM-generated text, no advice).
- The Activity panel grows a new "Usage characteristics" block: five percent-based items with a brief tip line each. Fixed order, rule-computed from the aggregate.
- A one-line disclaimer above the score table and a new "HOW SCORES RELATE" entry inside the existing how-to-read expandable explain that dimensions are independent.
- All new prose is locale-gated through `locales.py` (en only in this PR; zh_TW deferred to a follow-up).

## Non-goals

- LLM-generated tips or patterns. The pattern/tip strings are templated from aggregate counters — deterministic, testable, and privacy-neutral.
- Translating this feature to zh_TW in the same PR. The follow-up PR will add zh_TW strings and any rewrite-step integration.
- Changing the eight-dimension scoring algorithm. This PR is surface-level (data-passing + render) only; `score_dX_*` internals retain existing behaviour, with `pattern` added as a new returned field.
- Reworking the activity panel's existing tiles. The new "Usage characteristics" block appends; nothing above it is touched.
- Chart changes. No canvas rendering, no new SVG. This is text-only.

## Decisions (from 2026-04-19 brainstorm)

| # | Decision | Choice | Reasoning |
|---|---|---|---|
| Q1 | How tips are generated | **B. Rule-computed by scoring function** | Deterministic, testable, no runtime LLM dependency. Already own the aggregate. |
| Q2 | Tip voice | **C. Descriptive contrasts for rubric patterns; advice-style for activity tips** | Rubric patterns are evidence, not advice. Activity tips already tonally permit suggestion-style copy. Mixed register is fine because they live in different sections. |
| Q3 | Placement of %-narrative | **A. Inside the Activity panel** | Activity already holds counters; promoting a narrative block there makes it the natural home. Avoids a new top-level section. |
| Q4 | Number of %-items | **5** | Matches `/usage`, survives screen scan, enough to feel plural without diluting. |
| Q5 | Disclaimer placement | **C. Above score table *and* inside how-to-read** | Above-table catches scanners; how-to-read catches readers who drill in. Belt and braces for a point that is easy to miss and easy to misread. |
| Q6 | Locale scope | **en only, zh_TW deferred** | Ship the mechanic first; translate in a dedicated follow-up so the English copy can settle before being frozen. |
| Q7 | Activity dict time window | **Carry `since` / `until` / `n_sessions`** | A characteristic without a window is a claim without a base rate. The "across 280 sessions from 2026-03-20 to 2026-04-19" footer grounds it. |

### Design decisions (this spec, post-brainstorm)

| # | Decision | Choice | Reasoning |
|---|---|---|---|
| D-A | `.pattern` typography | **italic, `--ink-muted`, sans 13.5px** | One visual step below `.exp` (sans, `--ink-soft`, 14.5px). Italic + colour do the "secondary evidence" job without adding a new font. |
| D-B | `.score-disclaimer` alignment | **left-align** | The report is editorial left-aligned throughout; `overall-strip` is left; a right-aligned uppercase mono line punches above its caveat-level weight. |
| D-C | `.uc-row` percent column | **72px, internal `text-align: right`** | Serif 24px `100%` lands at the 60px threshold in Iowan Old Style; 72px guarantees headroom and aligns with the `.dim` column (80px) rhythm. Right-aligning inside the column keeps the `%` symbol vertically aligned across rows (42% / 100%). |

## Architecture

```
scripts/aggregate.py                        # 8 score_dX_* fns grow `pattern` in return dict
                                            # build_activity() gains usage_characteristics block
scripts/locales.py                          # new keys; en only this PR
scripts/build_html.py                       # render pattern; render disclaimer; render UC block
tests/test_build_html_additions.py          # extend existing additions tests
tests/test_usage_characteristics.py         # NEW — pattern math + UC rendering + XSS
```

## Section 1 — Data model (`aggregate.py`)

### 1a. Each `score_dX_*` returns `pattern`

All eight scoring functions return a dict that already contains `score`, `band`, `explanation`, etc. Add one field:

```python
return {
    "score": ...,
    "band": ...,
    "explanation": ...,
    "pattern": pattern_str_or_none,   # NEW
    # ... existing fields
}
```

**Computation rules (shared across all eight):**

- If the supporting sample size is `< 5`, `pattern = None`.
- If the computed contrast would duplicate or near-duplicate `explanation`, `pattern = None` (avoids redundancy).
- Otherwise format the dimension-specific template below.

**Per-dimension templates:**

| Dim | Pattern template |
|---|---|
| D1 delegation | `Sessions that used Task agent had a {X}% good-outcome rate, versus {Y}% overall.` |
| D2 root-cause | `Sessions without iterative_refinement friction reached good outcomes {X}% of the time, versus {Y}% for iterative_refinement sessions.` |
| D3 prompt quality | `Sessions with prompts ≥100 chars averaged {X} tokens per commit; ≤50-char prompts averaged {Y}.` |
| D4 context mgmt | `Sessions over 20 minutes without a commit hit output-token-limit {X}% of the time.` |
| D5 interrupt | `Of interrupted sessions, {X}% still reached good outcomes — a resilience signal.` |
| D6 tool breadth | `Your top tool consumes {X}% of calls — sessions diversifying tools had {Y}% higher outcome quality.` |
| D7 writing | `Writing-related sessions averaged {X} misunderstood_request events per session.` |
| D8 time-of-day | `Sessions started before 10am had a {X}% good-outcome rate, versus {Y}% for after-10pm sessions.` |

All numbers rounded: percentages to whole integers; per-session averages to one decimal.

### 1a-bis. Scanner gains `hit_output_limit`

Item 1 of `usage_characteristics` needs a signal that doesn't currently exist in the pipeline. Real transcripts contain a `message.stop_reason` field on assistant rows; the value `"max_tokens"` means the response was truncated by the output-token cap — the exact event the `/usage`-inspired narrative wants to surface.

`scripts/scan_transcripts.py` adds one boolean-ish field to each emitted row:

```python
# Per row in scan_transcripts output
"hit_output_limit": bool,   # True if any assistant message in the session had stop_reason == "max_tokens"
```

Implementation: when walking a jsonl session, track a local flag; set `True` on first sight of an assistant row whose `message.stop_reason == "max_tokens"`; emit the flag with the row.

**Data reality check (2026-04-19 local sample):** 50 recent transcripts contain 2 sessions with `max_tokens` stop-reasons. Rare event — which is what makes it a useful percent narrative. Guard against zero-match: when no sessions in the aggregate hit the limit, the item renders as `0%` — still valuable information.

`scripts/aggregate.py` passes `hit_output_limit` through from transcript rows into the session dict (join on `session_id`). Sessions from `session-meta` only (no transcript row) default to `False`, matching their absence in the activity scoring pool.

### 1b. Activity dict gains `usage_characteristics`

`build_activity()` appends one block to the returned dict:

```python
activity["usage_characteristics"] = {
    "since": "YYYY-MM-DD",          # earliest session date in scoring pool
    "until": "YYYY-MM-DD",          # latest session date in scoring pool
    "n_sessions": int,              # total sessions in scoring pool
    "items": [                      # exactly 5 entries, fixed order
        {"pct": int, "label": str, "tip": str},
        ...
    ],
}
```

**Five fixed items (rule-computed):**

| Order | Label template | Computation |
|---|---|---|
| 1 | `of your sessions hit output-token-limit` | sessions with `hit_output_limit=True` / total |
| 2 | `of your high-friction sessions were long (>20min)` | (duration>20min ∧ friction_count≥N) / friction sessions |
| 3 | `of your good-outcome sessions delegated to Task agent` | (outcome="good" ∧ uses_task_agent=True) / good sessions |
| 4 | `of your sessions used only 1-2 distinct tools` | sessions with `distinct_tools ≤ 2` / total |
| 5 | `of your sessions were after 10pm` | sessions with `start_hour ≥ 22` / total |

**Tips (advice-voice, static copy, rule-computed by thresholds; may vary based on the computed pct):**

| Order | Tip (default) | Variant if pct < threshold |
|---|---|---|
| 1 | `Sessions that /compact mid-task rarely hit the wall.` | (same) |
| 2 | `Long sessions concentrate friction; consider /clear between subtasks.` | (same) |
| 3 | `Task-agent delegation correlates with ship-level outcomes.` | (same) |
| 4 | `Narrow tool use is fine for focused work but misses MCP leverage.` | (same) |
| 5 | `Evening sessions produce more tokens per friction event.` | (same) |

Tips are static for v1 — we will iterate on variants if patterns emerge. Keep the dict structure ready to accept variants later.

**Guard condition:** If `n_sessions < 10` **or** any of the five items cannot be computed (missing prerequisite fields), omit `usage_characteristics` entirely. Render-side checks for presence before drawing the block.

### 1c. New `locales.py` keys (en only)

```python
"score_disclaimer": "These are independent characteristics, not a breakdown — scores do not sum.",
"score_disclaimer_long": "Each dimension is scored from the sessions that apply to it. A session can contribute to multiple dimensions, so the eight scores describe independent slices, not shares of a whole.",
"how_to_read_key_relate": "HOW SCORES RELATE",
"how_to_read_val_relate": "Each dimension scores a different aspect of sessions. A session can score high on Delegation but low on Time-of-day; they are independent characteristics, not shares of a total.",
"usage_char_header": "Usage characteristics",
"usage_char_note_template": "Across {n_sessions} sessions from {since} to {until}, local only.",
```

zh_TW entries use `"[TODO zh_TW] <english fallback>"` placeholders this PR. `tests/test_locales.py` enforces:

- `test_locale_keysets_match` — must stay green (add every new key to both locales).
- `test_no_empty_values` — must stay green (`""` would fail; `[TODO zh_TW] …` passes because it's non-whitespace).
- `test_zh_tw_strings_have_no_em_dash` — placeholder strings contain no em-dash, so stays green.

A new test `test_no_zh_tw_todo_markers_in_release` is added but marked `@unittest.skip("zh_TW rewrite scheduled for follow-up PR")` with a dated TODO comment pointing at the follow-up PR. The follow-up PR deletes the `@skip` and fills in native-tone strings. This preserves the spirit of PR #10's parity gate (keys can never be missing) while explicitly staging the translation work.

## Section 2 — Rendering (`build_html.py`)

### 2a. `.pattern` row on each `.score-row`

Append one `<p class="pattern">…</p>` inside `.score-row .body`, after `.exp`, only if `pattern` is non-None. Render with `esc()`.

```css
.score-row .body .pattern {
  font-family: var(--sans);
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--ink-muted);
  font-style: italic;
  margin: 6px 0 0 0;
}
```

### 2b. `.score-disclaimer` above score table

Insert directly above `<div class="score-table">` inside `<section id="scores">`:

```html
<p class="score-disclaimer">$score_disclaimer</p>
<div class="score-table">...</div>
```

```css
.score-disclaimer {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--ink-muted);
  text-transform: uppercase;
  margin: 0 0 14px 0;
  text-align: left;          /* Decision D-B */
}
```

### 2c. HOW SCORES RELATE inside `details.how-to-read`

Append one `<dt>/<dd>` pair at the end of the existing `dl`:

```html
<dt>$how_to_read_key_relate</dt>
<dd>$how_to_read_val_relate</dd>
```

No new CSS — reuses existing `details.how-to-read dt/dd` styles.

### 2d. `usage-characteristics` block in activity panel

`_build_activity_panel` appends (inside the existing panel wrapper, after the current stats tiles/list):

```html
<div class="usage-characteristics">
  <h4 class="uc-header">$usage_char_header</h4>
  <p class="uc-note">$usage_char_note</p>
  <div class="uc-list">
    <div class="uc-row">
      <span class="pct">42%</span>
      <div class="uc-body">
        <p class="label">of your sessions hit output-token-limit</p>
        <p class="tip">Sessions that /compact mid-task rarely hit the wall.</p>
      </div>
    </div>
    <!-- ×5 -->
  </div>
</div>
```

Render only when `activity.get("usage_characteristics")` is present. All fields of each item pass through `esc()`.

```css
.usage-characteristics {
  margin: 28px 0 0 0;
  padding: 20px 0 0 0;
  border-top: 1px solid var(--rule);
}
.uc-header {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--ink-muted);
  text-transform: uppercase;
  margin: 0 0 4px 0;
}
.uc-note {
  font-family: var(--sans);
  font-size: 12.5px;
  color: var(--ink-muted);
  margin: 0 0 14px 0;
}
.uc-list { display: flex; flex-direction: column; gap: 10px; }
.uc-row {
  display: grid;
  grid-template-columns: 72px 1fr;    /* Decision D-C */
  gap: 16px;
  padding: 8px 0;
  border-bottom: 1px dotted var(--rule);
  align-items: baseline;
}
.uc-row:last-child { border-bottom: none; }
.uc-row .pct {
  font-family: var(--serif);
  font-variation-settings: "opsz" 24, "wght" 400;
  font-size: 24px;
  line-height: 1;
  color: var(--ink);
  text-align: right;                  /* Decision D-C, keeps % vertically aligned */
  letter-spacing: -0.01em;
}
.uc-body .label {
  font-family: var(--sans);
  font-size: 14.5px;
  line-height: 1.45;
  color: var(--ink);
  margin: 0 0 2px 0;
}
.uc-body .tip {
  font-family: var(--sans);
  font-size: 13px;
  line-height: 1.5;
  color: var(--ink-muted);
  font-style: italic;
  margin: 0;
}
```

## Section 3 — Locales

en is canonical this PR. `STRINGS["zh_TW"]` gets `"[TODO zh_TW] <english fallback>"` entries for every new key (non-empty — passes `test_no_empty_values`; no em-dash — passes the em-dash gate). A new `@unittest.skip`-marked test `test_no_zh_tw_todo_markers_in_release` documents the debt; follow-up PR deletes the skip and writes native-tone zh_TW copy. PR #10's `test_locale_keysets_match` stays green throughout.

## Section 4 — Tests

### 4a. Extend `tests/test_build_html_additions.py`

- `class="pattern"` block appears when `scores[dim]` dict contains non-None `pattern`.
- `class="pattern"` block is **absent** when `pattern` is None (explicitly checked — not just "not present by accident").
- `.score-disclaimer` string is present and ordered **before** the score table div in the emitted HTML.
- New `dt`/`dd` pair for HOW SCORES RELATE appears inside `details.how-to-read` when rendered.
- `usage-characteristics` section contains exactly 5 `uc-row` children when activity dict is fully populated.
- `usage-characteristics` section is **absent** when `activity["usage_characteristics"]` is missing.

### 4b. New `tests/test_usage_characteristics.py`

Unit-test aggregate math on synthetic input:

- 0 sessions → `usage_characteristics` omitted.
- <10 sessions → `usage_characteristics` omitted (guard threshold).
- 100 sessions all `hit_output_limit=True` → item 1 pct = 100, item 1 tip rendered.
- Missing prerequisite field on an item (e.g., no `distinct_tools` in any row) → block omitted entirely.
- XSS: inject `<script>alert(1)</script>` into a derived label/tip path (where synthetic data could leak through) → escaped on render.

### 4c. XSS regression tests in `test_build_html_additions.py`

- pattern containing `<script>` escapes to `&lt;script&gt;`.
- uc-row label containing `<img onerror=…>` escapes.
- uc-row tip containing `"><script>` escapes.

## Acceptance criteria

1. `python scripts/build_html.py` on demo data (`/tmp/cc-autopsy-demo`) produces HTML containing:
   - At least 4 `.pattern` blocks (dimensions with ≥5 supporting sessions in demo).
   - One `.score-disclaimer` line directly above `.score-table`.
   - New HOW SCORES RELATE entry visible when `details.how-to-read` is expanded.
   - `.usage-characteristics` block with 5 `.uc-row` children inside the activity panel.
2. All existing tests pass. New tests pass. Offline smoke test passes.
3. Render on Safari + Chrome shows italic `.pattern` below each scored dimension; `.uc-row` percents vertically aligned for mixed 2-digit / 3-digit values.
4. No layout shift in existing sections (score-row grid, identity header, overview tiles).
5. HR-mode rendering unaffected — `.pattern` and `.usage-characteristics` appear regardless of mode (they contain no PII, only aggregate stats).

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Pattern text redundant with explanation | Computation rule: `pattern = None` when near-duplicate. Eyeball check on all 8 dims during review. |
| `/tmp/cc-autopsy-demo` doesn't cover thresholds | `generate_demo_data.py` may need a small tweak to ensure at least 4 dims have ≥5 supporting sessions — out-of-spec adjustment, fold into implementation plan if needed. |
| locale-parity test breaks on zh_TW placeholder | Use `@skip` with dated TODO pointing to follow-up PR; don't relax the gate globally. |
| 72px column too wide at mobile breakpoint | Add `@media (max-width: 640px)` rule collapsing to 56px if visual review flags it. Defer until render check. |
| Activity panel dict shape drift between PR #5 (`--extra-redacted`) and this feature | `usage_characteristics` is additive — redacted dump will not contain it; aggregate re-computes locally per build. |
| `hit_output_limit` pct is 0% for most users | Still valid narrative ("0% of your sessions hit the wall — nice headroom"); don't suppress the item for aesthetic reasons. Tip copy acknowledges both directions. |
| Redacted cross-machine dump schema needs `hit_output_limit` too | Add `hit_output_limit` to `_REDACTED_META_KEYS` in `aggregate.py` so dumps round-trip; tests in `test_scan_transcripts.py` already validate redacted schema. |

## Out of scope / follow-ups

- zh_TW locale for all new keys (follow-up PR).
- Dynamic tip variants per pct threshold — infrastructure ready, content deferred.
- LLM-generated pattern text — intentionally not pursued; determinism > nuance here.
- A/B variation on rubric pattern placement (e.g., inline vs below). Current design commits to below-`.exp`; revisit only if user feedback indicates hierarchy confusion.
