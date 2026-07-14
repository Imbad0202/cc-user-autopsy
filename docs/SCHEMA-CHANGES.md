# Schema changes

Tracks deprecations and removals in `analysis-data.json` and related JSON artifacts so external consumers (cross-machine merge scripts, historical archives, third-party readers) can plan around them.

## Policy

- **Additive changes** (new fields) are released without warning.
- **Deprecations** are announced here, retained for **2 releases**, then removed.
- **Breaking changes** without deprecation period are avoided. When unavoidable, they are called out in the commit message with `BREAKING:` prefix.

## Deprecated fields

### `scores[dim].explanation` (string)

**Deprecated:** 2026-04-20 (with `feat/i18n-explanations` PR)
**Removal target:** 2 releases after deprecation announcement
**Why:** Explanation text is now authored per-locale in `scripts/narrative_en.py` / `scripts/narrative_zh.py`. The aggregator layer no longer generates prose. Render layer reads narrative modules directly; the JSON field is retained only for external consumers.
**Migration:** If you need explanation text from `analysis-data.json`, switch to the narrative modules. For a locale-appropriate rendering without going through `build_html.py`:

```python
from scripts import narrative_en  # or narrative_zh
scores = analysis_data["scores"]
for dim, metrics in scores.items():
    if metrics.get("score") is not None:
        print(narrative_en.d1_explanation(metrics))  # etc.
```

### `scores[dim].pattern` (string or None)

**Deprecated:** 2026-04-20 (same PR)
**Removal target:** 2 releases after deprecation announcement
**Why:** Same as above — pattern text is now narrative-layer concern, not aggregator concern. The accompanying `scores[dim].pattern_emit: bool` is the new canonical signal for whether a pattern sentence should render.
**Migration:** Call `narrative_<locale>.dX_pattern(metrics)` when `metrics["pattern_emit"]` is True. Do not assume `pattern` string in JSON matches what the current report renders.

## Additive fields (informational)

### `scores[dim].pattern_emit` (bool)

**Added:** 2026-04-20
**Purpose:** Canonical signal for "should the pattern sentence be rendered for this dimension." Replaces the legacy convention of `pattern == None` meaning "don't emit."
**Semantics:** `True` iff both subgroups needed for the pattern comparison met `_PATTERN_MIN_SAMPLE` (and any other per-dim preconditions). Older JSON from before this PR lacks the field; consumers should treat missing as `False` and skip rendering.

### `cross_llm.sources[].parse_errors` (int)

**Added:** 2026-07-14
**Purpose:** Count of malformed/incomplete lines skipped from a given `--cross-llm-rows` input (missing `source` or `start_time`, or invalid JSON — bucketed under `"(unknown)"` when the source can't be guessed). 0 for `claude` (always internally derived, never file-loaded) and for any source with no parse failures.

## 2026-07-14 — additive: `cross_llm` and `ledger` top-level blocks (V5 Phase 1)

- `cross_llm`: cross-tool sources / common_window / weekly_share / parallel /
  project_matrix / head_to_head. Present even with no external sources
  (sources then lists only `claude`). Fields inside rows may be null —
  unknown is never imputed.
- `ledger`: schema_version 1; window / output counters / sources_detected.
- No existing fields changed or removed.

## 2026-07-14 — additive: `cross_llm.sources[].detected` (bool) + adapter `_meta` line (codex-fix-wave)

- `cross_llm.sources[]` now always contains one card per known source
  (`claude`, `codex`, `grok`, `antigravity`), even when a source produced
  no rows for this run. Undetected cards carry `"detected": false` and null
  out every measured field (`coverage`, `session_count: 0`, `first_date`,
  `last_date`, `total_input_tokens`, `total_output_tokens`); detected cards
  gain `"detected": true`. Undetected sources never appear inside
  `weekly_share`, `parallel`, `project_matrix`, or `head_to_head` — those
  structures are unchanged.
- Consumers reading `cross_llm.sources` before this change treated a
  missing source as "not run" implicitly (source absent from the list).
  After this change, absence is impossible — check `detected` instead.
- `scan_codex.py` and `scan_grok.py` now append one trailing
  `{"_meta": true, "source": "<codex|grok>", "parse_errors": N}` line to
  their output jsonl, carrying the scanner's own malformed-line skip count
  (previously only printed to stderr). `aggregate.load_cross_llm_rows()`
  consumes `_meta` lines into its `parse_errors_by_source` return value
  instead of treating them as session rows, so
  `cross_llm.sources[].parse_errors` now reflects adapter-side parse
  failures, not just aggregate-side ones. `scan_antigravity.py` is
  unaffected (it lists protobuf files by mtime; no JSON-line parsing to
  fail).

## 2026-07-14 — additive: `cross_llm.unattributed_parse_errors` (int) (codex-fix-wave round 3)

**Added:** 2026-07-14
**Purpose:** Count of malformed `--cross-llm-rows` lines that `load_cross_llm_rows` bucketed under `"(unknown)"` because no `source` could be guessed from the line (invalid JSON, or a row missing both `source` and `start_time`). Previously these errors were silently invisible — they never attached to any per-source card, since `cross_llm.sources[].parse_errors` only carries errors attributed to a known source. 0 default when no unattributed errors occurred.

## 2026-07-14 — semantics tightened: `ledger.sources_detected` (codex-fix-wave round 2)

- `compute_ledger` now filters `cross_llm.sources` to entries with
  `detected: true` (or `session_count > 0` for JSON predating the
  `detected` field) before listing them in `ledger.sources_detected`.
  Previously every known source (`claude`, `codex`, `grok`, `antigravity`)
  was copied verbatim, so an undetected source (one that produced zero
  rows this run) falsely appeared "detected" in the ledger. No field was
  added or removed — this is a correctness fix to which sources
  `sources_detected` includes.

## 2026-07-14 — additive: `blind_spots` top-level block (V5 Phase 2)

- `blind_spots`: schema_version 1; seven heuristic entries keyed
  `repeated_instructions`, `sunk_cost`, `switch_tax`, `graveyard`,
  `habit_drift`, `ask_vs_ship`, `interrupt_win_rate` (spec §5). Each entry
  has the shape `{id, gate_passed, suppressed_by_guard, n, metrics, reason}`:
  `gate_passed` is `False` whenever the heuristic's sample floor isn't met
  *or* its counterexample guard tripped (`suppressed_by_guard: true`
  distinguishes the two — `reason` explains either case in prose); `metrics`
  is heuristic-specific and may be `{}` when gated off; `n` is the
  heuristic's own qualifying-sample count (patterns / pairs / items /
  eligible weeks / scored sessions, depending on the heuristic).
- Present on every run, including empty-input runs — the whole block ships
  even when all seven entries are gated off, so downstream consumers (the
  Phase 2 leak ledger, Phase 3 trend rendering) can distinguish "engine ran,
  nothing qualified" from "engine did not run." Consumers reading JSON from
  before this change should treat a missing `blind_spots` key as "engine not
  run" (not as "nothing found").
- `habit_drift` is computed and stored by this change but intentionally not
  yet rendered anywhere in the HTML report — the trend-ledger UI consuming
  it is Phase 3 scope (decision #3 in the Phase 2 plan header).
- No existing fields changed or removed.
- `ledger.leaks`: additive field on the existing `ledger` block (schema_version
  1, unchanged). Shape:
  `{window_weeks: float, items: [{type, weekly_cost_usd, weekly_tokens,
  occurrences, evidence: [sid, ...]}]}`. `window_weeks` is
  `max(ledger.window.days / 7, 1)` rounded to 1 decimal. `items` holds up to
  3 entries, sorted by `weekly_cost_usd` descending — every leak type that
  independently clears its own gate, not just the top-scoring one. `type` is
  one of `repeated_instructions` (from `blind_spots.repeated_instructions`),
  `sunk_cost` (from `blind_spots.sunk_cost`'s confirmed pairs), or
  `failed_session_burn` (all other `not_achieved` rated sessions not already
  counted under `sunk_cost`, gated at >=5 sessions to avoid double-counting
  and small-sample noise). All costs are lower-bound estimates: every dollar
  traces to tokens the evidence actually shows. Absent `ledger.leaks` means
  the leak-catalog engine did not run (older JSON, or a run predating this
  change) — do not infer "no leaks found" from its absence, only from an
  empty `items` list on a present block.
- No existing `ledger` fields changed or removed.
- **`autopsy-history.jsonl` snapshot shape differs from `analysis-data.json`'s
  `ledger.leaks`.** SELF builds append one line to `autopsy-history.jsonl`
  (`build_html.append_history_snapshot`) whose `ledger.leaks` field is a
  **compact list** — each item is `{type, weekly_cost_usd, weekly_tokens,
  occurrences}` with no `evidence` sids — derived from but not identical to
  `analysis-data.json`'s `ledger.leaks`, which is a **dict**
  (`{window_weeks, items: [...]}`) whose `items` entries additionally carry
  an `evidence: [sid, ...]` list. Phase 3's trend-ledger implementer should
  read shapes per source: list-of-leak-dicts from the history file, the
  `{window_weeks, items}` dict from `analysis-data.json`.

---

*Maintained alongside `scripts/aggregate.py`. When adding, deprecating, or removing fields, update this file in the same commit.*
