# Auto-Scoring Rubric (8 Dimensions)

Each dimension scored 1-10. Rules are applied in `aggregate.py`. Scores may
differ from LLM-written peer review because rules are coarse — treat both views
as complementary.

## D1 — Delegation (Task agent usage)

Rationale: using `Task` subagents is the main mechanism for parallelizing work
and protecting the main context. Usage rate and outcome quality both matter.

| Score | Threshold |
|-------|-----------|
| 10 | task-agent rate ≥ 70% AND good-rate with TA ≥ 75% |
| 9 | task-agent rate ≥ 60% AND good-rate ≥ 70% |
| 8 | task-agent rate ≥ 45% AND good-rate ≥ 65% |
| 7 | task-agent rate ≥ 30% |
| 6 | task-agent rate ≥ 15% |
| 5 | task-agent rate ≥ 5% |
| 3 | task-agent rate > 0% but < 5% |
| 1 | no task-agent usage at all |

## D2 — Root-cause debugging

Rationale: iterative bug-fix sessions ("v11 → v12 → v13") signal symptom-level
patching. Measured via iterative_refinement sessions with buggy_code friction.

Let `R = (iterative_refinement sessions with buggy_code friction) / (all sessions with facets)`.

| Score | Threshold |
|-------|-----------|
| 10 | R ≤ 2% |
| 9 | R ≤ 4% |
| 8 | R ≤ 7% |
| 7 | R ≤ 10% |
| 6 | R ≤ 15% |
| 5 | R ≤ 20% |
| 4 | R ≤ 25% |
| 3 | R > 25% |

If facets coverage < 30%, return "insufficient data" instead of a score.

## D3 — Prompt quality

Rationale: the median tokens-per-commit for 150-400 char prompts vs <50 char
prompts tells us whether long prompts pay off AND whether the user uses them.

| Score | Threshold |
|-------|-----------|
| 10 | ≥ 60% of sessions have prompts ≥ 100 chars AND 150-400 bucket is the most efficient |
| 8 | ≥ 40% of sessions have prompts ≥ 100 chars |
| 7 | ≥ 25% of sessions have prompts ≥ 100 chars |
| 5 | < 25% of sessions use prompts ≥ 100 chars (heavy reliance on short prompts) |
| 3 | > 50% of sessions use prompts < 20 chars |

## D4 — Context management

Rationale: sessions > 60 min with higher friction, output-token-limit hits, and
"effort-no-commit" sessions indicate poor context hygiene.

Composite: penalize each of the following.

Start at 10, subtract:
- 1 if output-token-limit sessions > 2
- 1 if output-token-limit sessions > 5
- 1 if long-session (>60min) interrupt rate > 25%
- 1 if > 15% of sessions > 20 min had 0 commits (effort-no-commit)
- 1 if > 30% of sessions > 20 min had 0 commits
- 1 if any single project has > 5 output-token-limit sessions

Floor at 3.

## D5 — Interrupt judgment

Rationale: interrupts that correlate with recovered outcomes indicate good
intervention timing, not noise.

Let `P = fraction of interrupted sessions that reach good outcome (full+mostly)`.

| Score | Threshold |
|-------|-----------|
| 10 | P ≥ 60% |
| 9 | P ≥ 50% |
| 8 | P ≥ 40% |
| 7 | P ≥ 30% |
| 5 | P ≥ 20% |
| 3 | P < 20% |

If interrupt count < 5, return "insufficient data".

## D6 — Tool breadth

Rationale: over-reliance on Bash/Read/Edit compared to MCP tools and dedicated
tools (Glob, Grep, Skill, Task) signals narrow tool knowledge. MCP adoption rate
is a secondary check.

Composite metric `T`:
- `mcp_rate` = fraction of sessions using any MCP tool
- `top3_share` = share of Bash + Read + Edit calls out of total tool calls

| Score | Thresholds |
|-------|-----------|
| 10 | mcp_rate ≥ 30% AND top3_share ≤ 40% |
| 8 | mcp_rate ≥ 15% AND top3_share ≤ 55% |
| 7 | mcp_rate ≥ 10% |
| 6 | mcp_rate ≥ 5% |
| 5 | mcp_rate ≥ 2% |
| 4 | mcp_rate < 2% |

## D7 — Writing/consistency friction

Rationale: repeated misunderstood_request or wrong_approach in writing-related
goal categories (writing_refinement, content_writing, documentation_update)
hints at drifting prose without upfront style framing.

Let `W = sum of misunderstood_request across writing-related sessions /
writing-related session count`.

| Score | Threshold |
|-------|-----------|
| 10 | W ≤ 0.1 |
| 8 | W ≤ 0.3 |
| 7 | W ≤ 0.6 |
| 5 | W ≤ 1.0 |
| 3 | W > 1.0 |

If writing-related sessions < 5, skip this dimension (display "n/a").

## D8 — Time-of-day management

Rationale: if certain hour buckets have 2x+ the friction rate of the best hour,
the user isn't self-managing well.

Compute friction_per_session for each hour (TPE timezone if user has Asia
locale; otherwise UTC).
Let `ratio = max_friction_rate / min_friction_rate` across hours with ≥ 5
sessions.

| Score | Threshold |
|-------|-----------|
| 10 | ratio ≤ 1.5 |
| 8 | ratio ≤ 2.0 |
| 7 | ratio ≤ 2.5 |
| 5 | ratio ≤ 3.5 |
| 3 | ratio > 3.5 |

If fewer than 3 hours have ≥ 5 sessions, skip.

---

## Notes

- Every score is accompanied by the raw metric that drove it, so the user can
  decide if the threshold is fair for their context.
- Rules assume > 20 rated sessions. Below that, the aggregate script flags the
  report as "preliminary" and dials down confidence language in the HTML.
- When a dimension is skipped due to insufficient data, it's shown as "n/a"
  in the report and does not factor into the 9-dimension average.

---

## Blind-spot heuristics (v1, provisional)

Seven pattern detectors computed by `compute_blind_spots()` in `aggregate.py`
(spec §5), stored in the additive `blind_spots` top-level block. Unlike the
9-dimension scores above, these are not scored 1-10 — each is a binary
gate (`gate_passed`) with a sample floor and, where applicable, a
counterexample guard that suppresses the finding even when the sample floor
is met. All constants on this page are **provisional v1**: chosen at plan
time without a real-data tuning pass; expect them to move once the engine
has run against actual usage.

Shared building blocks: `normalize_prompt()` (lowercase, punctuation folded
to spaces, whitespace collapsed — the full normalized string is kept for
identity, no truncation; only the displayed exemplar is truncated, to 120
chars), `prompt_similarity()`
(token-set Jaccard — with a CJK-aware fallback, see below), `week_key()`
(ISO `YYYY-Www`), and the counterexample
guard `counterexample_similar(rate_flagged, rate_good)` — trips (returns
`True`, suppressing the finding) when the flagged behavior occurs in
`fully_achieved` sessions at a rate within **provisional v1** `_BS_GUARD_FACTOR
= 1.5`× the flagged rate, i.e. the behavior isn't actually predictive of
failure for this user.

**CJK normalization note (Fix 3)**: `prompt_similarity()` is word-token
Jaccard by default, which assumes whitespace-delimited words. Chinese (and
other CJK scripts) have no spaces between words, so a whole zh sentence
normalizes to a single unsplit "token" — two near-identical zh prompts
would score 0.0 instead of something graded, breaking sunk-cost pair
matching (#2 below) for zh users. When either normalized string contains a
CJK character (`一-鿿`), `prompt_similarity()` instead computes Jaccard over
character BIGRAMS of the de-spaced string; strings shorter than 2 characters
after de-spacing fall back to the word-token path (no bigrams possible).
Non-CJK (English etc.) inputs are unaffected.

### #1 — Repeated-instruction tax

Rationale: an instruction the user has to retype every session (a style
rule, a "run tests before claiming done" reminder) is a tax on every
session it appears in, win or lose. **Not outcome-guarded by design** — see
counterexample-guard applicability below.

Let `X = normalize_prompt(first_prompt)` grouped into exact-match patterns
across Claude rows and full/partial-coverage cross-LLM rows (`coverage ==
"presence_only"` rows excluded — no prompt text available).

| Threshold | Value (provisional v1) |
|-----------|-------------------------|
| Minimum pattern length | `_BS_MIN_PATTERN_CHARS = 20` normalized chars |
| Minimum occurrences | `_BS_REPEAT_MIN_OCC = 5` |
| Minimum distinct weeks | `_BS_REPEAT_MIN_WEEKS = 3` |

`metrics.patterns` reports the top 5 patterns by occurrence count; each
carries the most-common raw exemplar (≤120 chars, display only, chosen
among CLAUDE hits only — spec §4 forbids cross-LLM prompt text in any
output, so a pattern with no Claude occurrence stores an empty exemplar
and the renderer omits its detail line), a
lower-bound `est_wasted_tokens` (each occurrence charged at its own
NORMALIZED length in tokens, `len(normalized) // 4`, summed with the
single largest occurrence dropped as the free "first typing" — only the
retyped text, thinking/re-reading time not counted), and up to 3 evidence
session IDs. Charging per-occurrence rather than at the exemplar's length
matters because raw prompts of different lengths can share one folded
identity.

If no pattern reaches 5 occurrences across ≥3 distinct weeks, `gate_passed`
is `False` and `reason` explains which floor wasn't met. The heuristic is
also gated off entirely (reason: no valid ledger window) when no
transcript-derived window exists to scope occurrences against — otherwise
cross-tool history of unbounded length would be scanned unwindowed while
the weekly leak items are suppressed for the same invalid window.

Pricing rule: `compute_leaks` prices the repeated-instruction leak's dollar
figure from `claude_wasted_usd`, which prices each Claude occurrence at its
own row's verified input-rate floor (the cheapest input rate among the
row's observed models) times that occurrence's own normalized-length
tokens. An occurrence with no verified rate — missing model attribution, or
any model absent from the pricing table (a cheaper historical model may
have processed it) — contributes $0, and the one free "first typing" is
discounted at the largest single-occurrence dollar value, so the total
stays a floor. `claude_wasted_tokens` (the same per-occurrence sum
restricted to Claude hits, largest hit dropped) remains as the Claude-share
token count, and `weekly_tokens` in the leak-catalog item still reports the
all-source `est_wasted_tokens` total, so cross-tool (Codex/Grok) repetition
is visible in the token count without being priced at a Claude rate it was
never billed at.

### #2 — Sunk-cost sessions

Rationale: a failed session that accelerated its output pace late (grinding
harder without changing approach), followed by a fast, similar-prompt
success, is the signature of "should have restarted sooner."

A confirmed pair = a `not_achieved` session with `token_accel >=
_BS_ACCEL_FLAG` (**provisional v1** `1.5`), followed by a later session
whose outcome is good (`is_good()`, i.e. `fully_achieved` OR
`mostly_achieved`) and whose normalized prompt has Jaccard similarity
`>= _BS_SIMILARITY_MIN` (**provisional v1** `0.5`) to the failed session's,
finishing in `<= _BS_RETRY_MAX_DURATION_SHARE` (**provisional v1** `0.5`,
i.e. half) of the failed session's minutes. Note the counterexample guard
below uses a narrower baseline than the retry qualification: it measures
the acceleration rate in `fully_achieved` sessions only (not
`mostly_achieved`), so a pair's retry can qualify on `mostly_achieved`
while the guard's baseline rate is computed strictly from `fully_achieved`
sessions.

| Threshold | Value (provisional v1) |
|-----------|-------------------------|
| Minimum confirmed pairs | `_BS_SUNK_MIN_PAIRS = 3` |

**Counterexample guard applies**: if `token_accel >= 1.5` occurs about as
often in `fully_achieved` sessions as in `not_achieved` ones
(`counterexample_similar` trips), acceleration isn't actually a failure
signal for this user — the whole finding is suppressed
(`suppressed_by_guard: true`) regardless of pair count.

If fewer than 3 confirmed pairs and the guard didn't trip, `gate_passed` is
`False` with `reason = "fewer than 3 confirmed pairs"`.

### #3 — Switch tax

Rationale: sessions that overlap another tool's active window (multi-tool
mornings, say) may carry a context-switching cost visible as lower
good-rate or higher friction/interrupts compared to single-tool sessions.
Symmetric comparison — **no counterexample guard** (both buckets are
reported; there's no "guard direction" for a comparison that reports both
sides).

**Common-window clipping (Fix 1)**: both buckets are restricted to the
cross-source common window before comparison. Claude history predating
Codex/Grok adoption would otherwise flood the single-tool bucket — those
pre-overlap sessions could never have been multi-tool, biasing the
comparison — so per spec §13 ("cross-source comparisons render only over
the common time window"), `bs_switch_tax` computes each source's own
`[min start, max end]` (via `_row_windows`, same building block
`compute_cross_llm`'s `common_window` uses) over the comparable row pool
(Claude activity rows, meta-only rated sessions with synthesized minimal
activity, and full/partial cross-LLM rows — `presence_only` excluded), then
intersects across sources with ≥1 row (`start = max(mins)`, `end =
min(maxes)`). Fewer than 2 sources with a resolvable window → same "no
multi-source windows" failure path as before. Only rated sessions whose
start DATE falls inside `[start.date(), end.date()]` (inclusive at both
ends — see Fix 6 below) are bucketed at all; the 20/20 gate evaluates on
these clipped buckets, not the full history.

Buckets: `multi` = in-window rated Claude sessions whose
`[start, start+duration]` overlaps a merged interval where ≥2 sources were
concurrently active (computed from Claude activity rows plus full/partial
cross-LLM rows); `single` = the in-window rest.

| Threshold | Value (provisional v1) |
|-----------|-------------------------|
| Minimum sessions per bucket | `_BS_SWITCH_MIN_PER_BUCKET = 20` |

If no multi-source windows exist at all, or either IN-WINDOW bucket is
below 20 sessions (even if the bucket's all-time total would clear the
floor), `gate_passed` is `False`. `metrics.multi` / `metrics.single` each
report `n`, `good_rate`, `friction_per_session`, `interrupts_per_session`.

### #4 — The graveyard

Rationale: substantive work (real edits) with no commit, on a project that
then goes untouched for weeks, is effort that never shipped — a different
failure mode from a session that simply didn't finish. **Not
outcome-guarded** — achieved-but-never-shipped is precisely the finding, not
a counterexample to explain away; guarded instead by structural exclusions.

Per project (`normalize_project_path`), take the row owning the latest
activity **end** (Fix 4 — see below). It qualifies as a graveyard item when
all of:

| Threshold | Value (provisional v1) |
|-----------|-------------------------|
| Minimum substantive writes (Edit+Write+NotebookEdit) | `_BS_GRAVEYARD_MIN_WRITES = 5` |
| Staleness horizon | `_BS_GRAVEYARD_HORIZON_DAYS = 14` (spec §13) |
| Zero commits on that latest row | `git_commits == 0` |
| Not a scratch path | excludes scratch roots (`/tmp`, `/private/tmp` as the path or a path-root prefix) and any path containing a complete `scratchpad` component (`/home/u/scratchpad` yes, `/home/u/scratchpad-tools` no) |
| Project key resolvable | excludes `(unknown)` / non-shippable keys |
| Minimum qualifying items | `_BS_GRAVEYARD_MIN_ITEMS = 2` |

**Staleness from activity END, not session START (Fix 4)**: `window_end`
(the newest activity timestamp seen this run, or "now" if the activity pool
is empty) anchors "days untouched", but the per-project "last touched"
timestamp it's compared against is the max activity **end**, not the
session's start. A row's activity end = `max(e for _, e in
_row_windows(row))` — the same segment-aware helper `compute_cross_llm` uses
— so a resumed multi-day session that started 20 days ago but has a segment
active as recently as yesterday is correctly NOT stale, even though its
`start_time` is old. `days_untouched = (window_end - latest_end).days`; the
qualifying-session fields (`writes`, `git_commits`, `evidence`,
`last_active_date`) all come from the row that owns that latest end, and
`last_active_date = latest_end.date().isoformat()`. A project whose latest
activity end falls within the last 14 days of the window is not yet a
graveyard candidate, even with zero commits. `metrics.items` lists up to 8,
sorted by `days_untouched` descending.

### #5 — Habit drift

Rationale: shrinking prompt length over time can mean two very different
things — growing trust/skill (fine) or corner-cutting under fatigue (a
blind spot worth flagging). The heuristic can't tell those apart from
length alone, so it leans on the outcome trend to disambiguate.

Rated sessions are grouped into ISO weeks; only weeks with
`>= GROWTH_MIN_RATED_PER_WEEK` (existing constant, `= 3`) rated sessions
count as *eligible* — this mirrors the floor the growth panel already uses,
so "8 weeks" means 8 plottable weeks, not 8 calendar weeks. Eligible weeks
are split into an early half and a late half (sorted chronologically,
`ordered[:half]` vs `ordered[-half:]`).

Let `early_median_len` / `late_median_len` = median `first_prompt_len` (or
`len(first_prompt)` as fallback) over the early/late halves, and
`early_good_rate` / `late_good_rate` = percentage of `is_good()` outcomes
over the same halves.

| Threshold | Value (provisional v1) |
|-----------|-------------------------|
| Minimum eligible weeks | `_BS_DRIFT_MIN_WEEKS = 8` |
| Shortening threshold | `_BS_DRIFT_LEN_DROP = 0.75` (late median ≤ 75% of early median) |
| Good-rate tolerance | `_BS_DRIFT_GOOD_TOL_PP = 5` percentage points |

Decision logic, in order:

1. Fewer than 8 eligible weeks → `gate_passed = False`, not guarded
   (`reason = "fewer than 8 weeks with enough rated sessions"`).
2. No shortening trend (`late_median_len > 0.75 * early_median_len`, or
   `early_median_len` is 0) → `gate_passed = False`, not guarded
   (`reason = "no shortening trend"`).
3. Shortening, and `late_good_rate` improved by more than 5pp over
   `early_good_rate` → **counterexample guard trips**
   (`suppressed_by_guard = true`, `reason = "outcomes improved while
   prompts shortened"`): shorter prompts with better outcomes is skill
   gained, not drift.
4. Shortening, and `late_good_rate` is flat (within ±5pp) or worse →
   `gate_passed = True`. This is the drift finding.

**Phase 2 scope note**: `bs_habit_drift` is computed and stored in every
run starting this change, but is **not rendered** anywhere in the HTML
report yet. The trend-ledger UI that would visualize it needs multiple
snapshots to show a trend and is Phase 3 scope.

### #6 — Ask vs. ship

Rationale: if a goal category (e.g. `feature_implementation`) makes up a
large share of what's *asked* but a much smaller share of what actually
*ships* (sessions with `git_commits > 0`), that gap is a blind spot —
effort concentrated somewhere that rarely closes the loop.

Inherently non-shipping goal categories (`_BS_NONSHIP_GOALS =
{"information_query", "exploration", "quick_question"}`) are excluded from
gap-flagging by design — asking a question is not a leak. This is the
**structural** form of the counterexample guard for this heuristic (spec's
"guarded" reading, not the `counterexample_similar` numeric guard used by
#2/#5).

| Threshold | Value (provisional v1) |
|-----------|-------------------------|
| Minimum rated sessions | `_BS_ASKSHIP_MIN_RATED = 20` |
| Minimum shipped sessions | `_BS_ASKSHIP_MIN_SHIPPED = 5` |
| Minimum gap to flag | `_BS_ASKSHIP_MIN_GAP_PP = 10` percentage points |

`ask_share_pct` / `ship_share_pct` are **session-membership shares**: for
each category, the percent of rated (or shipped) sessions whose
`goal_cats` contains that category — a session with multiple categories
counts once per category it contains, not once per goal-tag occurrence.
`gap_pp = ask_share_pct - ship_share_pct` for each shippable category;
`metrics.top_gap` reports the largest gap. If there are zero shippable
categories present after exclusion, the rated/shipped floors aren't met,
or the largest gap is below `_BS_ASKSHIP_MIN_GAP_PP`, `gate_passed` is
`False`.

### #7 — Interrupt win-rate

Rationale: the D5 upgrade — instead of a single threshold score, report
both buckets symmetrically so the user can see the actual delta, not just
whether it cleared a bar. Symmetric comparison — **no counterexample
guard**.

Buckets: `interrupted` = rated sessions with `interrupts > 0`; `baseline` =
rated sessions with zero interrupts.

| Threshold | Value (provisional v1) |
|-----------|-------------------------|
| Minimum sessions per bucket | `5` (same floor as D5 above) |

`metrics.delta_pp = interrupted.good_rate - baseline.good_rate`. Negative
means interrupting correlates with worse outcomes for this user; positive
means interruptions tend to be well-timed rescues.

### Counterexample-guard applicability

Per spec §5 ("any pattern that occurs at a similar rate in `fully_achieved`
sessions drops below gate"), read per-heuristic:

- **#2 sunk-cost** — guarded: if `token_accel >= 1.5` is about as common in
  `fully_achieved` as in `not_achieved` sessions, acceleration is not a
  failure signal for this user; suppress.
- **#5 habit drift** — guarded: if prompts got shorter but the good rate
  *improved* beyond tolerance, that is skill, not drift; suppress.
- **#6 ask-vs-ship** — guarded structurally: inherently non-shipping goal
  categories (`information_query`, `exploration`, `quick_question`) are
  excluded from mismatch flagging (asking questions is not a leak).
- **#1 repeated-instruction tax** — **not** outcome-guarded by design: a
  repeated instruction is a tax regardless of outcome (successful sessions
  still paid it); an outcome guard would always suppress it. Guarded
  instead by the 20-char floor.
- **#3, #7** — not guarded: they *are* symmetric comparisons (both buckets
  reported), so there is no single "flagged rate" to compare against a
  "good rate."
- **#4 graveyard** — not outcome-guarded: an achieved-but-never-shipped
  artifact is precisely the finding; guarded instead by the structural
  exclusions (scratch paths, `(unknown)` project, 14-day horizon).

## Badges (v1, provisional)

The badge layer (spec §4) publishes absolute thresholds; claims that clear
them may be displayed affirmatively in external report versions. Badges are
threshold-based, never percentile-based; unearned badges are silently absent
in external versions (never shown as "failed"). Bars are **provisional v1**
(spec §13) — revisit after the first real runs. Where a 9-dim analogue
exists, each bar equals that dimension's "score ≥ 8" band. Badge wording in
reports is fixed template text in `scripts/locales.py`, not LLM prose.
Computed by `compute_badges()` in `scripts/aggregate.py`; the full item list
(earned and unearned, with metrics and thresholds) ships in
`analysis-data.json` under the top-level `badges` block.

| Badge | Earned when | Minimum sample |
|---|---|---|
| `delegation` | Task-agent adoption ≥ 30% of sessions AND good-outcome rate on Task-agent sessions ≥ 70% | ≥ 15 rated Task-agent sessions |
| `root_cause` | D2 scored AND iterative-refinement-with-buggy-code co-occurrence ≤ 7% of rated sessions | ≥ 30 rated sessions |
| `tool_breadth` | MCP used in ≥ 15% of sessions AND top-3 built-in tools (Bash/Read/Edit) ≤ 55% of all tool calls | ≥ 30 sessions |
| `token_efficiency` | not-good/good token ratio ≤ 1.1 AND cache hit ≥ 80% | ≥ 30 rated sessions |
| `shipping_cadence` | git commits per active week ≥ 5 (evidence-backed ledger count) AND ≥ 10 sessions with commits | ledger window ≥ 14 days |
| `cross_tool_orchestration` | ≥ 2 full-tier sources detected AND common window ≥ 14 days (not degraded) AND ≥ 10 hours of multi-source parallel work | n = multi-source hours |
