# Design Tokens Audit + Refactor (cc-user-autopsy)

**Status**: design
**Date**: 2026-04-19
**Branch**: `feat/design-tokens`
**Base**: `main @ 37563e0` (post-PR #10 i18n merged)
**Scope**: `scripts/build_html.py` CSS only

## Problem

`scripts/build_html.py` has grown to 2,379 lines with a single embedded CSS block. PRs #7-10 shipped four independent improvements but left the component CSS fragmented:

- **Color + font-family** — 14 CSS variables, consistent
- **Spacing / radius / font-size / line-height** — zero variables, 67 distinct hard-coded numeric values across 257 occurrences
- **Top offenders**: `1px×31, 14px×14, 6px×10, 22px×10, 12px×9, 10px×8, 20px×8, 24px×8, 2px×8, 3px×8` — no consistent 4px/8px rhythm
- **Four main components** (`.profile-card`, `.metrics`, `.chart-box`, `details.evidence`) and **five smaller ones** (`.intro-card`, `.dek`, `.method`, `.caveat`, `.evidence-header`) each evolved independently; padding/margin/radius decisions conflict visually
- **Known bug**: Chinese `h1.title` renders too thin because `font-weight: 300` on variable-axis serif fallback (PingFang / system CJK) produces a bony weight

## Goals

1. Introduce a two-layer token system (primitives + semantic aliases) for spacing, radius, font-size, line-height.
2. Refactor all nine target components to consume tokens instead of hard-coded values.
3. Fix `html[lang="zh-Hant"] h1.title` to use `font-weight: 500` (+ `em` at 600) so the Chinese hero reads with proper weight.
4. Preserve pixel-level visual output for English + zh_TW (hero weight change is the sole intentional diff).

## Non-goals

- Refactor of top-level HTML elements (`body`, `h1`, `h2`, `h3`) outside hero title.
- Changes to `@media print` block layout.
- New shadow system (YAGNI — no `box-shadow` currently in use).
- Consolidation of sparse "one-off" numeric values (10.5px, 11.5px, 14.5px) where they appear 1-2 times in well-defined typography contexts — these stay hard-coded under a documented whitelist.
- Removal of existing color / font-family CSS variables (already clean).
- Changes to `zh-Hant` body/dek/intro-card/method/caveat font-size overrides (already validated in PR #10).

## Design

### Token architecture (two layers)

**Layer A — Primitives (system rhythm)**

```css
:root {
  /* Spacing scale — 2px base granularity to accommodate existing 2/3/4/6/8/10/12/14/16/18/20/22/24/30 */
  --space-0: 0;
  --space-1: 2px;
  --space-2: 4px;
  --space-3: 6px;
  --space-4: 8px;
  --space-5: 10px;
  --space-6: 12px;
  --space-7: 14px;
  --space-8: 16px;
  --space-9: 18px;
  --space-10: 20px;
  --space-11: 22px;
  --space-12: 24px;
  --space-14: 28px;
  --space-15: 30px;

  /* Radius */
  --radius-sm: 2px;
  --radius-md: 3px;
  --radius-lg: 6px;

  /* Font size */
  --text-xs: 11.5px;
  --text-sm: 13px;
  --text-base: 15px;
  --text-md: 16px;
  --text-lg: 17px;
  --text-xl: 18px;

  /* Line-height */
  --leading-tight: 1.2;
  --leading-snug: 1.35;
  --leading-normal: 1.55;
  --leading-loose: 1.7;
}
```

**Layer B — Semantic aliases (design intent)**

```css
:root {
  --card-padding: var(--space-12);     /* 24px — profile-card / intro-card */
  --card-radius: var(--radius-lg);     /* 6px */
  --section-gap: var(--space-15);      /* 30px */
  --tag-padding-y: var(--space-1);     /* 2px */
  --tag-padding-x: var(--space-3);     /* 6px */
  --rule-width: 1px;                   /* borders — stays primitive */
}
```

Semantic aliases are added **only when a concrete component needs them** (avoid inventing tokens for hypothetical consumers). Additional aliases can appear during component refactor commits.

### Hardcoded-value whitelist

These values remain hard-coded (too sparse or context-specific to deserve tokens):

- Font sizes appearing 1-2× in unique contexts: `10.5px`, `14.5px`, `11.5px` (if retained in one spot each after token pass)
- `zh-Hant` `font-size` overrides (`18.5px`, `17.5px`, `17px`, `15.5px`) — already tested in PR #10, untouched
- Letter-spacing `-0.02em`, `-0.03em`, `0.02em` — typographic trim, not a scale
- `clamp(38px, 6vw, 64px)` hero sizing — responsive formula, not a token

The whitelist is encoded in `tests/test_css_tokens.py` as a constant.

### Component refactor targets

**Main (4)**
1. `.profile-card` (line 732) + `::before`
2. `.metrics` + `.metrics > .metric` (line 572-587) + mobile override
3. `.chart-box` (line 962-977) + `.tall`/`.short` + `canvas` + `::after`
4. `details.evidence` (line 993-1056) + `summary` + `.tag` variants + `.sid/.proj/.right` + `[open]` + `p code`

**Small (5)**
5. `.intro-card` (line 446) + `::before`
6. `.dek` (line 437)
7. `.method` (line 1081) + `ul/li`
8. `.caveat` (line 1088)
9. `.evidence-header` (line 1056)

### Hero weight fix (zh-Hant)

Add to the existing `html[lang="zh-Hant"]` override block (near line 387):

```css
html[lang="zh-Hant"] h1.title {
  font-weight: 500;
  font-variation-settings: "opsz" 144, "wght" 500;
}
html[lang="zh-Hant"] h1.title em {
  font-weight: 600;
  font-variation-settings: "opsz" 144, "wght" 600;
}
```

English render path unaffected (override only matches `lang="zh-Hant"`).

## Execution strategy (method 3: mapping-first bottom-up)

1. **Write token mapping** — spec (this doc) contains the primitives table; detailed hardcode→token mapping lives in the PR body of the first refactor commit.
2. **Add Layer A + B token definitions** — no component changes yet. Build HTML, verify zero pixel diff.
3. **Add grep test** (red) — `tests/test_css_tokens.py` asserts tokens exist + target components have no hardcoded spacing. Test starts red because components still use hardcodes.
4. **Refactor components sequentially** — `.profile-card` → `.metrics` → `.chart-box` → `details.evidence` → `.intro-card` → `.dek` → `.method` → `.caveat` → `.evidence-header`. After each, run pixel diff (en + zh_TW) and progressively enable that component in the grep test.
5. **Apply zh-Hant hero weight fix** — separate commit.
6. **Final pixel diff pass** — full report in both locales, attach to PR.

## Verification / tests

### Layer 1: grep test (`tests/test_css_tokens.py`)

```python
# asserts
def test_token_primitives_defined(): ...     # all --space-*, --radius-*, --text-*, --leading-* present
def test_token_semantic_aliases_defined(): ...  # --card-padding etc.
def test_no_hardcoded_spacing_in_target_components(): ...
  # for each component CSS block, regex \d+(\.\d+)?px must not match
  # except: WHITELIST = {"10.5px", "11.5px", "14.5px"}
  # except: lines inside html[lang="zh-Hant"] override block
def test_zh_hant_hero_weight_override(): ...  # font-weight: 500 + em: 600 present
```

### Layer 2: build smoke test

Existing or new `tests/test_build_html.py` runs `scripts/build_html.py` against synthesis demo data (seed-fixed) in both locales, asserts:
- Process exits 0
- Output HTML parses (basic XML/HTML-ish validity)
- Output length within ±2% of main baseline (recorded once in a `expected_html_size.json` fixture)

### Layer 3: pixel diff (manual, in PR description)

Run `scripts/build_html.py` with identical synthesis data on `main` and on `feat/design-tokens`, open in `/browse`, screenshot four regions per locale:
1. Hero + intro-card
2. Metrics grid
3. Chart box (one representative chart)
4. Evidence section (one open `<details>`)

Before / after pairs attached to PR. Acceptable diff: ≤1px anti-aliasing drift. Intentional diff: zh_TW hero weight is heavier (called out in PR body).

## Commit sequence (single PR)

Branch `feat/design-tokens` off `main @ 37563e0`:

1. `docs: add design tokens spec`
2. `feat(css): add token primitives (space/radius/text/leading)`
3. `feat(css): add semantic aliases (card-padding/section-gap...)`
4. `test: add css token grep tests`
5. `refactor(css): profile-card uses tokens`
6. `refactor(css): metrics uses tokens`
7. `refactor(css): chart-box uses tokens`
8. `refactor(css): evidence uses tokens`
9. `refactor(css): intro-card/dek/method/caveat/evidence-header use tokens`
10. `fix(css): zh-Hant hero title weight 500`
11. `docs: CHANGELOG + pixel diff attachments in PR body`

## Risks + mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 1 | Pixel diff fails on one component because token mapping mis-rounded | Component-level pixel diff (not just final composite). Rollback = single commit revert |
| 2 | Whitelist (10.5/11.5/14.5px) governance rots | Whitelist lives in test constants + TODO comment pointing to future v2 cleanup |
| 3 | `h1.title em` forgotten → em too thin under zh-Hant | Explicitly in hero-weight commit + test `test_zh_hant_hero_weight_override` covers both |
| 4 | `@media print` contains component-specific hardcode that gets missed | Audit step in commit 5 (profile-card) checks print block for each target component |
| 5 | `build_html.py` is non-deterministic, pixel diff unreproducible | Use fixed-seed synthesis demo (already present via PR #9); document seed in PR body |
| 6 | Token names collide with existing vars | Grep confirmed: no `--space-*` / `--radius-*` / `--text-*` / `--leading-*` exists pre-PR |
| 7 | English serif hero regresses because of override bleed | `html[lang="zh-Hant"]` selector specificity tested; English HTML generated with `lang="en"` → no match |

## Out of scope (future work)

- v2 tokens: consolidate sparse sizes (10.5/11.5/14.5px) once their typographic role is clearer
- `@media print` full refactor
- Shadow token system (add when first `box-shadow` appears)
- Dark mode token overlay
- Token export as JSON for external consumers

## References

- PR #10 i18n locale design: `docs/superpowers/specs/2026-04-19-i18n-locale-design.md`
- Memory: `project_cc_user_autopsy_design_system_pending.md`
