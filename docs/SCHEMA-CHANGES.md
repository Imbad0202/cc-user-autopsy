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

---

*Maintained alongside `scripts/aggregate.py`. When adding, deprecating, or removing fields, update this file in the same commit.*
