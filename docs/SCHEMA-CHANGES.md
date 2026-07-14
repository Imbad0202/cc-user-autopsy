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

## 2026-07-14 — semantics tightened: `ledger.sources_detected` (codex-fix-wave round 2)

- `compute_ledger` now filters `cross_llm.sources` to entries with
  `detected: true` (or `session_count > 0` for JSON predating the
  `detected` field) before listing them in `ledger.sources_detected`.
  Previously every known source (`claude`, `codex`, `grok`, `antigravity`)
  was copied verbatim, so an undetected source (one that produced zero
  rows this run) falsely appeared "detected" in the ledger. No field was
  added or removed — this is a correctness fix to which sources
  `sources_detected` includes.

---

*Maintained alongside `scripts/aggregate.py`. When adding, deprecating, or removing fields, update this file in the same commit.*
