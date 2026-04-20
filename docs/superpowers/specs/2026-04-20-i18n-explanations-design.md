# i18n explanations + narrative module separation

**Status:** Draft — pending user review (2026-04-20)
**Scope:** `feat/i18n-explanations` branch, stacked on `fix/zh-tw-locale` (PR #16) which itself is stacked on `feat/d9-token-efficiency` (PR #15).
**Merge order:** PR #15 → PR #16 → this PR.
**Spec:** this file
**Parity brief:** `docs/superpowers/specs/narrative-parity-brief.md` (separate doc, committed alongside)
**Schema changes log:** `docs/SCHEMA-CHANGES.md` (separate doc, committed alongside)

## Problem

`cc-user-autopsy` currently generates a single report with locale chrome (section titles, tile labels, subtitles) translated via `scripts/locales.py`. But the **body** of every score dimension — the `explanation` sentence and `pattern` sentence — is hard-coded English inside `scripts/aggregate.py` as Python f-strings. The zh_TW report renders a mix: Chinese chrome plus English evidence paragraphs. The same applies to methodology caveats (already manually translated via `locales.py` during PR #16 review but showing translationese), evidence badges (`HIGH FRICTION` / `TOP TOKEN` — rendered from CSS class names via `replace('_', ' ')`, never reads locale), and outcome labels (`fully_achieved` / `partially_achieved` / `(no facet)` printed raw).

The previous approach was to add `[TODO zh_TW]` locale keys and translate them. The translations shipped in PR #16 but reading them side-by-side with the English made the deeper problem obvious: **a zh_TW report written as a word-for-word translation of the English report reads like translationese regardless of how carefully we translate**. Chinese technical writing has different rhythm, clause structure, and rhetorical stance than English editorial. Forcing one to mirror the other produces a report that feels hollow in both languages.

The decision (2026-04-20 session): stop treating zh_TW as an i18n of English. Treat it as a **parallel report authored in Chinese**, sharing all numeric data with the English version but free to choose its own sentence structure, clause order, and emphasis. The two narratives are siblings, not parent/child.

## Goals

- Every paragraph of evidence prose (`explanation`, `pattern`, methodology caveats, evidence badges, outcome labels) is authored per-locale in a dedicated narrative module, not templated from a shared string.
- The English report and zh_TW report cite **identical numbers** — same counts, same percentages, same metric values — even when the surrounding sentences differ.
- This invariant is enforced by an automated parity test that AST-scans both narrative modules and asserts each function pair reads the same set of `metrics[...]` keys.
- `scripts/aggregate.py` stops embedding locale-specific text. It becomes a pure data layer returning metric dicts + a `pattern_emit` boolean, with no locale awareness.
- `scripts/build_html.py` becomes a thin orchestrator: pick a narrative module by `--locale`, hand it metrics from `aggregate.py`, stitch the returned strings into the shared render layer.
- Existing chrome translations in `locales.py` (tile labels, section titles, chart legends) keep their current mechanism. The split is between **chrome** (locales.py) and **narrative** (narrative_*.py).

## Non-goals

- No changes to D1-D9 scoring algorithms or thresholds. Spec compliance here is surface-level only.
- No changes to CSS, design tokens, or chart rendering (all completed in PR #15 / PR #16).
- No new locales beyond en + zh_TW.
- No breaking changes to `analysis-data.json`. The existing `explanation` and `pattern` JSON fields remain populated (deprecated) for two releases so external consumers (cross-machine merge scripts, historical archives) don't silently break.
- No replacement of the AST parity test with a richer semantic check. Parity is "same metric keys cited", not "same semantic content."
- No extraction of the narrative brief into a runtime format. `narrative-parity-brief.md` is a human-readable writing aid, not machine-consumed.

## Decisions (from 2026-04-20 brainstorm)

| # | Decision | Choice | Reasoning |
|---|---|---|---|
| Q1 | Scope | **C. D1-D9 exp/pat + outcome labels + evidence badges + (no facet)** | Clear all English residue in one PR. Contract refactor is the expensive part; adding 10 more keys is cheap once the pipe is built. |
| Q2 | Architecture framing | **Two independent reports, not i18n** | User articulation: "中文版不應該是 i18n，而是出一份英文一份中文". Re-frames the whole effort. |
| Q3 | File split | **C. Shared render/CSS/chart + two narrative modules** | CSS and chart code must not diverge. Only prose does. Mirrors the existing `[lang="zh-Hant"]` scope-override pattern from PR #15. |
| Q4 | Narrative API | **A. Flat function per string** | Gives narrative authors maximum freedom (conditional sentences, clause reordering). `d9_explanation` already has 3-branch conditional assembly — template-dict approach would force re-implementing that logic inside each locale. |
| Q5 | Parity enforcement | **i + iii** | (i) AST-scan both narratives for `metrics[...]` key sets, assert equal. (iii) human-readable brief per dim listing which facts must be conveyed. Writing discipline + automated check. |
| Q6 | Entry point | **a. Keep `build_html.py --locale`** | Preserves CLI contract, README, SKILL.md docs. Locale flag becomes an import router. |
| Q7 | Numeric parity rule | **Same numbers, prose may differ** | Both narratives read the same `metrics` dict from the same `analysis-data.json`. Any divergence in reported figures is a bug. |
| Q8 | Parity test key extraction | **x. AST scan** | Zero author overhead. Static (no fixture needed). Catches both `metrics[k]` and `metrics.get(k)`. |
| Q9 | Schema back-compat | **Retain deprecated `explanation`/`pattern` fields in aggregate dict** | External consumers (cross-machine merge, archive) shouldn't silently break. Deprecation period: 2 releases. |
| Q10 | Deprecation comment location | **Separate `docs/SCHEMA-CHANGES.md`** | Keeps scoring functions clean. Single source of truth for "which fields are going away." |
| Q11 | Test migration | **b. Parallel test suites** | Existing `test_d9_token_efficiency.py` keeps its assertions on the deprecated JSON fields (guards back-compat). New `test_narrative_en.py` / `test_narrative_zh.py` test narrative functions directly. |
| Q12 | Branch strategy | **Stacked: main ← PR #15 ← PR #16 ← PR #17** | Each PR stays reviewable; stack rebases when parent merges. |

## Architecture

```
scripts/
  aggregate.py              # pure data. Returns metric dict + pattern_emit bool.
                            # Retains deprecated explanation/pattern fields (JSON back-compat).
  report_render.py  NEW     # HTML/CSS/chart/tile layout. No narrative strings.
  narrative_en.py   NEW     # English narrative. Flat functions.
  narrative_zh.py   NEW     # Chinese narrative. Same function signatures.
  build_html.py             # Thin orchestrator.
                            # import narrative_en or narrative_zh by --locale.
                            # Pass metric dicts to narrative, pass narrative output to render.
  locales.py                # Chrome only (tile labels, section titles, chart legends).
                            # method_* and ev_* (outcome-specific) keys migrate to narrative.
                            # Chrome keys that remain: section_*, tile_*, chart_*, score_d1..score_d9,
                            # header_*, footer_*, hero_* variants.

tests/
  test_narrative_parity.py        NEW   AST scan, metric-key set equality per function pair.
  test_narrative_en.py            NEW   Behavior tests for English narrative.
  test_narrative_zh.py            NEW   Behavior tests for Chinese narrative.
  test_d9_token_efficiency.py           Keeps assertions on deprecated JSON fields (back-compat).
  test_build_html_additions.py          May need small updates (orchestrator behavior).
  test_locales.py                       Keys migrating to narrative get removed from REQUIRED_KEYS.

docs/
  SCHEMA-CHANGES.md                   NEW   Deprecation schedule for JSON fields.
  superpowers/specs/
    2026-04-20-i18n-explanations-design.md  NEW   this spec
    narrative-parity-brief.md                NEW   per-dim writing checklist
```

## Wording convention

- **Chrome** = repeated interface strings (tile labels, section titles, "of 10", chart legends, footer). Lives in `locales.py`. Translated key-by-key. Style consistent across all reports.
- **Narrative** = evidence prose (explanation, pattern, methodology caveats, outcome labels, evidence badges). Lives in `narrative_*.py`. Authored per-locale. Style may differ between locales as long as numeric content matches.

The boundary test: if the same string appears ≥3 times across unrelated sections, it's chrome. If it's a sentence describing one specific metric or dimension, it's narrative.

## Section 1 — Narrative module API

Both `narrative_en.py` and `narrative_zh.py` export these functions:

```python
# Dimension explanations — always emitted
def d1_explanation(metrics: dict) -> str
def d2_explanation(metrics: dict) -> str
def d3_explanation(metrics: dict) -> str
def d4_explanation(metrics: dict) -> str
def d5_explanation(metrics: dict) -> str
def d6_explanation(metrics: dict) -> str
def d7_explanation(metrics: dict) -> str
def d8_explanation(metrics: dict) -> str
def d9_explanation(metrics: dict) -> str

# Dimension patterns — emitted only when metrics["pattern_emit"] is True
def d1_pattern(metrics: dict) -> str
def d2_pattern(metrics: dict) -> str
def d3_pattern(metrics: dict) -> str
def d4_pattern(metrics: dict) -> str
def d5_pattern(metrics: dict) -> str
def d6_pattern(metrics: dict) -> str
def d7_pattern(metrics: dict) -> str
def d8_pattern(metrics: dict) -> str
def d9_pattern(metrics: dict) -> str

# Single-value lookups — take a key string, return a label
def outcome_label(outcome: str) -> str
def evidence_badge(tag: str) -> str
def no_facet_label() -> str

# Methodology block — no metrics, static authored prose
def methodology_subtitle() -> str
def methodology_sampling_body() -> str
def methodology_caveats_body() -> str
```

All 24 functions must exist in both modules with identical signatures.

### Metric access constraints (for parity test to work)

1. Narrative functions read metric values via `metrics["<literal_key>"]` or `metrics.get("<literal_key>", default)` only.
2. **Banned**: dynamic key access (`metrics[some_var]`), `**metrics` unpacking, storing `metrics` as an attribute and accessing via `self.metrics[x]`.
3. These constraints are enforced by the parity test structure — violating them breaks parity detection, not the code. Document in the narrative module docstring.

### Pattern function contract

When `metrics["pattern_emit"]` is `False`, the caller (`build_html.py`) does not invoke the pattern function. The pattern function itself doesn't need to handle the "don't emit" case.

### outcome_label / evidence_badge lookup behavior

- `outcome_label("fully_achieved")` → en: `"Fully achieved"`, zh: `"完全達成"`
- Unknown outcome values: return the raw string unchanged (defensive; raw CC data may surface unexpected categories).
- Same pattern for `evidence_badge`.

## Section 2 — aggregate.py contract change

Before (all 9 `score_dX_*` functions):

```python
return {
    "score": score,
    "metric_foo": ...,
    "metric_bar": ...,
    "explanation": f"...hardcoded English...",
    "pattern": pattern_string_or_none,
}
```

After:

```python
return {
    "score": score,
    "metric_foo": ...,
    "metric_bar": ...,
    "pattern_emit": <bool>,   # NEW: was implicitly encoded by pattern=None vs pattern=string
    # --- DEPRECATED (JSON schema back-compat, see docs/SCHEMA-CHANGES.md) ---
    "explanation": f"...hardcoded English...",   # unchanged, kept for 2 releases
    "pattern": pattern_string_or_none,            # unchanged, kept for 2 releases
}
```

The deprecated fields carry identical content to what they emit today. Only the render layer stops reading them. External consumers (e.g. cross-machine merge, historical archive scripts) keep working until the 2-release deprecation period elapses.

`pattern_emit` is the new canonical signal. Render code reads `scores[dim].get("pattern_emit", False)`; older JSON (pre-this-PR) lacks the key, so `.get` defaults to `False` and the pattern line is skipped. That's correct behavior for old data — safer to under-emit than render mismatched pattern text against new-API metrics.

### Insufficient-sample case

When a scoring function currently returns `{"score": None, "reason": "insufficient ...", "pattern": None}`, the new shape is:

```python
{
    "score": None,
    "reason": "insufficient ...",
    "pattern_emit": False,
    "explanation": "...",   # deprecated; can be "" or the original string
    "pattern": None,         # deprecated
}
```

`explanation` in the deprecated field path keeps its current content unchanged (English fallback sentence or the existing "insufficient ..." string). Narrative modules produce their own insufficient-data sentence for display: `d1_explanation(metrics)` receives a metrics dict with `score = None` and returns a locale-appropriate "insufficient data" sentence. The exact wording is per-narrative (part of what the `narrative-parity-brief.md` captures). Render layer uses the narrative output; deprecated JSON field is for external consumers only.

## Section 3 — report_render.py extraction

Lift the HTML/CSS/chart-rendering code from current `build_html.py` into `scripts/report_render.py`. Keep `build_html.py` as a thin CLI entry that:

1. Parses `--locale`, `--input`, `--output`, `--samples`, `--peer-review`, `--audience` args (no change)
2. Loads `analysis-data.json`, `samples.json`, peer review
3. Imports the matching narrative module (`narrative_en` or `narrative_zh`)
4. Builds a `NarrativeBundle` dict by calling every narrative function once with the right metric dict
5. Hands the bundle + chrome (from `locales.py`) + raw data to `report_render.render(...)`
6. Writes the returned HTML string to `--output`

`report_render.render(...)` is pure-input-to-output: same inputs produce byte-identical output. No disk I/O, no CLI argparse, no stdout logging.

### NarrativeBundle shape (rough sketch)

```python
{
    "dims": {
        "D1_delegation": {"explanation": "...", "pattern": "..." or None, ...},
        ...
    },
    "methodology": {
        "subtitle": "...",
        "sampling_body": "...",
        "caveats_body": "...",
    },
    "outcome_labels": {
        "fully_achieved": "Fully achieved",
        ...
    },
    "evidence_badges": {
        "high_friction": "High friction",
        ...
    },
    "no_facet_label": "(no facet)",
}
```

This keeps narrative module access out of `report_render.py`. `report_render.py` only sees pre-computed strings.

## Section 4 — Parity test (AST scan)

File: `tests/test_narrative_parity.py` (new).

```python
import ast
import importlib.util
from pathlib import Path
import pytest

NARRATIVE_ROOT = Path(__file__).parent.parent / "scripts"

DIM_FUNCTION_NAMES = [
    f"d{d}_{kind}" for d in range(1, 10) for kind in ("explanation", "pattern")
]  # 18 functions

def _load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _extract_metrics_keys(module, func_name):
    """Walk the AST of module.<func_name> and collect every constant
    key accessed via metrics[<key>] or metrics.get(<key>, ...)."""
    src = Path(module.__file__).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            keys = set()
            for sub in ast.walk(node):
                # metrics["foo"] subscript
                if (
                    isinstance(sub, ast.Subscript)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "metrics"
                    and isinstance(sub.slice, ast.Constant)
                    and isinstance(sub.slice.value, str)
                ):
                    keys.add(sub.slice.value)
                # metrics.get("foo", default)
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "get"
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "metrics"
                    and sub.args
                    and isinstance(sub.args[0], ast.Constant)
                    and isinstance(sub.args[0].value, str)
                ):
                    keys.add(sub.args[0].value)
            return keys
    raise AssertionError(f"function {func_name} not found in {module.__file__}")

@pytest.fixture(scope="module")
def narrative_en():
    return _load_module(NARRATIVE_ROOT / "narrative_en.py")

@pytest.fixture(scope="module")
def narrative_zh():
    return _load_module(NARRATIVE_ROOT / "narrative_zh.py")

@pytest.mark.parametrize("func_name", DIM_FUNCTION_NAMES)
def test_metric_key_parity(func_name, narrative_en, narrative_zh):
    en_keys = _extract_metrics_keys(narrative_en, func_name)
    zh_keys = _extract_metrics_keys(narrative_zh, func_name)
    assert en_keys == zh_keys, (
        f"{func_name}: metric keys diverge.\n"
        f"  en-only: {en_keys - zh_keys}\n"
        f"  zh-only: {zh_keys - en_keys}"
    )
```

### Additional static checks

```python
def test_narrative_modules_expose_same_function_set(narrative_en, narrative_zh):
    """Signature parity, not just metric-key parity."""
    en_funcs = {name for name in dir(narrative_en) if callable(getattr(narrative_en, name)) and not name.startswith("_")}
    zh_funcs = {name for name in dir(narrative_zh) if callable(getattr(narrative_zh, name)) and not name.startswith("_")}
    assert en_funcs == zh_funcs

def test_narrative_modules_do_not_use_metrics_unpacking():
    """Enforce the 'no **metrics unpacking' rule so parity scan stays valid."""
    for module_path in ("narrative_en.py", "narrative_zh.py"):
        src = (NARRATIVE_ROOT / module_path).read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg is None:
                # ** unpacking — safe to skip unless the unpacked name is metrics
                pass  # keep benign — we only care about lookups, not calls
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "metrics"
                and not isinstance(node.slice, ast.Constant)
            ):
                raise AssertionError(
                    f"{module_path}: dynamic metrics[...] access detected at line {node.lineno}. "
                    "Narrative functions must use literal string keys so parity scan can read them."
                )
```

## Section 5 — Narrative brief (human-readable)

File: `docs/superpowers/specs/narrative-parity-brief.md` (new, committed with this spec).

Per dim, list:
- Which metrics MUST be mentioned in `dX_explanation`
- Which metrics MUST be mentioned in `dX_pattern`
- Style rules (e.g., "evidence voice, not advice", "mirror D2-D8 contrastive grammar")
- Forbidden constructs per language (en: no "should" / "recommend"; zh: no "建議" / "應該" / "可以考慮")

This is authored once by the spec owner, reviewed by user, then narrative authors follow it. It exists to catch parity violations that AST can't see — e.g., "narrative function references the right metric key in code but never actually prints the number in the sentence."

Rough outline (full content drafted during writing-plans / implementation):

```markdown
# Narrative Parity Brief

## D1 delegation

### d1_explanation (always emit)
Must mention:
- Task Agent adoption rate (metrics["metric_ta_rate_pct"])
- Good-outcome rate when Task Agent is used (metrics["metric_good_rate_with_ta_pct"])

Style: evidence-first. No advice.
Forbidden en: "should", "recommend", "try"
Forbidden zh: "建議", "應該", "可以考慮", "嘗試"

### d1_pattern (emit when pattern_emit=True)
Must mention:
- Task Agent group good-outcome rate
- Overall good-outcome rate
- Directional contrast (higher / lower / comparable)

Style: contrastive, mirrors D2-D9 pattern family.

## D2 root cause
... (8 more dim blocks)
```

## Section 6 — Files summary + tests

### New files

| File | Purpose |
|---|---|
| `scripts/report_render.py` | Lift HTML/CSS/chart from build_html.py. No behavior change. |
| `scripts/narrative_en.py` | English narrative, 24 functions. |
| `scripts/narrative_zh.py` | Chinese narrative, 24 functions. |
| `tests/test_narrative_parity.py` | AST parity test + signature parity + no-dynamic-access check. |
| `tests/test_narrative_en.py` | Behavior tests: each en narrative function against fixture metrics. |
| `tests/test_narrative_zh.py` | Behavior tests: each zh narrative function against fixture metrics. |
| `docs/SCHEMA-CHANGES.md` | Deprecation schedule for `analysis-data.json` fields. |
| `docs/superpowers/specs/narrative-parity-brief.md` | Per-dim writing brief. |

### Modified files

| File | Change |
|---|---|
| `scripts/aggregate.py` | Add `pattern_emit: bool`. Retain existing `explanation` / `pattern` (deprecated, unchanged content). 9 scoring functions touched. |
| `scripts/build_html.py` | Shrink to thin orchestrator. Import narrative by locale. Delegate render. |
| `scripts/locales.py` | Remove `method_*` keys, `ev_*` keys (outcome-specific), and `outcome_*` keys (if any). Chrome keys stay. |
| `tests/test_locales.py` | `REQUIRED_KEYS` set shrinks; any removed key's test dies with the key. |
| `tests/test_d9_token_efficiency.py` | Assertions on `result["explanation"]` / `result["pattern"]` keep validating **deprecated** fields. Add new counterparts in `tests/test_narrative_en.py`. |
| `tests/test_build_html_additions.py` | Update render tests if orchestrator output shape shifts. Expect minor edits, not rewrites. |

### Risks + mitigations

| Risk | Mitigation |
|---|---|
| AST parity test passes but narrative silently drops a number from the sentence (references key, never format-prints) | Parity brief spells out "must mention X"; review by human (user) catches. Consider lint: regex-scan narrative function body for `{key` or `{metrics["key"]`. Flag as follow-up if needed. |
| Downstream script reads `analysis-data.json` field that got removed | Only `explanation` / `pattern` fields are in-scope for deprecation. Neither is removed in this PR. `pattern_emit` is additive. |
| Stacked PR #17 conflicts when #15 or #16 edits aggregate.py / build_html.py | Rebase protocol documented: after parent merges, `git rebase origin/main` and resolve in favor of this PR's structure, preserving parent's logic changes. |
| Narrative module grows unwieldy (24 functions × 2 modules) | Each module is flat, ≤ 300 lines expected. Easy to scan. If one grows >500 lines, break by section (e.g., narrative_en/dims.py, narrative_en/methodology.py, narrative_en/__init__.py re-exports). Defer that split to a follow-up if it materializes. |
| `narrative_zh.py` leaks English idiom structure (translationese) despite fresh authoring | Parity brief's style rules + explicit forbidden-constructs list. Review by user pre-merge. If translationese slips through: open a follow-up PR with specific rewrites; don't revert the architecture. |

## Section 7 — Implementation order (for writing-plans)

1. Write parity test scaffolding (`tests/test_narrative_parity.py`). Should fail initially (no narrative modules exist).
2. Create empty `narrative_en.py` and `narrative_zh.py` with all 24 function stubs returning placeholder strings. Parity test should now pass (empty functions have empty key sets).
3. Extract `report_render.py` from `build_html.py` by lift-and-shift. No behavior change. Existing tests green.
4. Populate `narrative_en.py`: move all current English prose from `aggregate.py` and `locales.py` into the right narrative function. No new English. Full test suite green.
5. Modify `aggregate.py`: add `pattern_emit: bool` to each scoring function return dict. Retain `explanation` / `pattern` fields untouched (deprecated).
6. Modify `build_html.py`: become thin orchestrator. Call `narrative_en` when `--locale en`, pass strings to `report_render`.
7. Write `narrative-parity-brief.md` covering all 9 dims + methodology + outcome labels + badges.
8. Populate `narrative_zh.py` against the brief. AST parity test keeps key sets honest.
9. Update `locales.py`: remove `method_*` and `ev_*` keys that migrated. Update `REQUIRED_KEYS` in `test_locales.py`.
10. Add `tests/test_narrative_en.py` and `tests/test_narrative_zh.py` with behavior tests (each function invoked once against fixture metrics, assert non-empty string / correct format).
11. Write `docs/SCHEMA-CHANGES.md`. Document the deprecated `explanation` / `pattern` fields with a removal target (2 releases forward).
12. Full test matrix: `pytest` + `node --test tests/chart_layout.test.mjs`. Regenerate both locale reports. Visual verify zh report end-to-end.
13. Self-review diff. Push branch. Open PR #17 with base `fix/zh-tw-locale`.

Estimated size: ~700-900 lines diff (new files dominate; `aggregate.py` / `build_html.py` lose lines to compensate).
