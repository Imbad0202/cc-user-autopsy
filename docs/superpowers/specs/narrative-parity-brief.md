# Narrative Parity Brief

This brief captures which metrics and content each narrative function must convey. It is the human-readable companion to the automated `test_narrative_parity.py` AST check — the automated test asserts both locales reference the same metric keys; this brief asserts both locales actually *say* the relevant facts in natural prose.

Filled during implementation of `feat/i18n-explanations` (2026-04-20).

## Style rules (apply to all functions)

**English narrative:**
- Evidence voice. State what the data shows.
- No advice: forbidden "should", "recommend", "try", "consider".
- No value judgments: forbidden "good idea", "bad idea", "best practice".
- Mirror existing D1-D8 house style from PR #12 (contrastive pattern sentences, descriptive explanations).

**Chinese narrative:**
- Evidence voice. 敘述數據呈現什麼。
- 不給建議：禁用「建議」「應該」「可以考慮」「嘗試」「不妨」。
- 不做價值判斷：禁用「好習慣」「壞習慣」「最佳實踐」。
- 沿用 D1-D8 在 `locales.py` 已固定的 zh_TW 術語（Task Agent / session / prompt / Token / rated）。
- 禁 em-dash（repo 有 `test_zh_tw_strings_have_no_em_dash` rule enforcing this）。
- 句式可以獨立於英文，但**必須引用相同的 metric 欄位**（由 AST parity test 強制）。

---

## D1 delegation

### d1_explanation (always emit)

Must reference:
- `metric_ta_rate_pct` — Task Agent adoption rate
- `metric_good_rate_with_ta_pct` — good-outcome rate when Task Agent is used

Both values must appear as formatted numbers in the final sentence.

### d1_pattern (emit when `pattern_emit=True`)

Must convey:
- Task Agent group good-outcome rate (from `metric_good_rate_with_ta_pct`)
- Overall baseline good-outcome rate (from `metric_overall_good_rate_pct` — aggregator must supply this)
- Directional contrast (higher / lower / comparable)

Style: contrastive, mirrors D2-D9 pattern family.

---

## D2 root cause

### d2_explanation (always emit)

Must reference:
- `metric_iter_buggy_count` — number of iterative_refinement sessions with buggy_code friction
- `metric_iter_buggy_pct` — as % of rated sessions

### d2_pattern (emit when `pattern_emit=True`)

Must convey:
- Good-outcome rate for sessions WITHOUT iterative_refinement friction
- Good-outcome rate for sessions WITH iterative_refinement
- Which group did better, by how much

---

## D3 prompt quality

### d3_explanation

Must reference:
- `metric_rate_ge_100_pct` — % of sessions with prompts ≥100 chars
- `metric_best_bucket` — most efficient prompt-length bucket for tokens/commit

### d3_pattern

Must convey:
- Average tokens/commit for long prompts (≥100 chars)
- Average tokens/commit for short prompts (<20 chars)
- Contrast relationship

---

## D4 context management

### d4_explanation

Must reference:
- `metric_output_token_limit_count` — sessions that hit output-token-limit
- `metric_long_session_no_commit_pct` — % of >20min sessions with 0 commits
- `metric_long_session_interrupt_pct` — long-session interrupt rate

### d4_pattern (likely None — no established pattern句; confirm during implementation)

---

## D5 interrupt judgment

### d5_explanation

Must reference:
- `metric_interrupted_good_pct` — % of interrupted sessions that reached good outcome
- `metric_interrupted_count` and `metric_interrupted_good_count` — raw counts

### d5_pattern

Must convey:
- Interrupted group good-outcome rate
- Non-interrupted group good-outcome rate
- Which is higher

---

## D6 tool breadth

### d6_explanation

Must reference:
- `metric_mcp_rate_pct` — % of sessions using MCP tools
- `metric_top3_share_pct` — share of calls from top-3 tools (Bash/Read/Edit)

### d6_pattern

Must convey:
- Diverse-tool group good-outcome rate
- Narrow-tool group good-outcome rate
- Contrast

---

## D7 writing consistency

### d7_explanation

Must reference:
- `metric_writing_sessions_count` — count of writing-related sessions
- `metric_avg_misunderstood` — avg misunderstood_request per session

### d7_pattern (may be None — confirm during implementation)

---

## D8 time-of-day management

### d8_explanation

Must reference:
- `metric_worst_hour` — hour with highest friction rate
- `metric_best_hour` — hour with lowest friction rate
- `metric_worst_best_ratio` — ratio between them

### d8_pattern

Must convey:
- Good-outcome rate before/after some time cutoff
- Direction of contrast

---

## D9 token efficiency

### d9_explanation (always emit)

Must reference:
- `metric_tokens_per_good` — mean total_tokens for good-outcome sessions
- `metric_tokens_per_not_good` — mean for other rated sessions
- `metric_ratio` — ratio of the two
- Conditionally: per-turn numbers if both `tokens_per_turn_*` computed (check via `metrics.get("metric_tokens_per_turn_good")` nullability)
- Conditionally: cache hit ratio if `metric_cache_hit_pct is not None`

### d9_pattern (emit when `pattern_emit=True`)

Must convey:
- Good-outcome group avg tokens
- Not-good group avg tokens
- Ratio (same number as explanation)

Keep pattern shorter than explanation — it's a summary, not a recap.

---

## Methodology block

### methodology_subtitle

**en:** one-line dek under "Methodology" section header. Previously "What this report is, and what it is not." → revised to match zh direct-tone.
**zh:** 直譯味過重的原版已在 PR #16 改為「報告限制。」。narrative_zh 保留這個句。

### methodology_sampling_body

Must convey:
- How many sessions are sampled for evidence library (currently 24)
- The seven buckets and counts per bucket
- Fallback rule when facets data is missing

### methodology_caveats_body

Must convey:
- Facet labels come from LLM, may misclassify
- Facet coverage threshold for reliability (50% ok, <30% n/a)
- Scoring thresholds are heuristics, not exact science
- Peer review requires enough data; thin data → short feedback, not padded

Style reminder: zh version should NOT read like a translation. Authored directly in Chinese. "硬湊滿版" / "站得住" style from PR #16 revision is the voice target.

---

## outcome_label

Map keys → display labels:

| outcome key | en | zh |
|---|---|---|
| `fully_achieved` | Fully achieved | 完全達成 |
| `mostly_achieved` | Mostly achieved | 大致達成 |
| `partially_achieved` | Partially achieved | 部分達成 |
| `not_achieved` | Not achieved | 未達成 |
| `unclear_from_transcript` | Unclear from transcript | 逐字稿難判斷 |
| (unknown / fallback) | (raw value unchanged) | (raw value unchanged) |

---

## evidence_badge

Map tags → badge labels:

| tag | en | zh |
|---|---|---|
| `high_friction` | High friction | 摩擦最高 |
| `top_token` | Top token | Token 用量最多 |
| `top_interrupt` | Top interrupt | 中斷次數最多 |
| `not_achieved` | Not achieved | 未達成 |
| `partial` | Partial | 部分達成 |
| `control_good` | Control good | 對照組 |
| `user_rejected` | User rejected | 你否決動作 |
| `long_duration` | Long duration | 持續最久 |

---

## no_facet_label

**en:** `(no facet)`
**zh:** `（無 facet）`

Used when a sample's outcome field is missing. Aggregator hands the raw string; narrative turns it into this label.
