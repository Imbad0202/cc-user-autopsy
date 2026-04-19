# Design Tokens Audit + Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a two-layer CSS token system, refactor nine components in `scripts/build_html.py` off hard-coded values, and fix the thin zh-Hant hero title.

**Architecture:** All CSS lives inside one large Python f-string template in `scripts/build_html.py`. We add `--space-*`, `--radius-*`, `--text-*`, `--leading-*` primitives plus semantic aliases to the existing `:root` block, then replace hard-coded numeric values in each component CSS block with `var(...)` references. A new grep-based test module (`tests/test_css_tokens.py`) enforces token presence and absence of hard-coded spacing inside target component blocks. A zh-Hant-scoped font-weight override added to the existing i18n block fixes the hero weight regression.

**Tech Stack:** Python 3 (unittest), single-file HTML template in `scripts/build_html.py`, `/browse` skill for pixel diff.

---

## File structure

- Modify: `scripts/build_html.py` (CSS block lines ~332-1106 inside the `<style>` string)
- Create: `tests/test_css_tokens.py`
- Create: `docs/superpowers/plans/2026-04-19-design-tokens-audit.md` (this file)

## Context engineers need before starting

1. **CSS is embedded in a Python template.** `scripts/build_html.py` renders one HTML document by string-substituting into a giant template literal. The `<style>` block lives around lines 331-1106. Treat it as CSS — edits use the normal Edit tool with exact matches.
2. **Existing CSS variables** in `:root` (line 332-348): `--paper`, `--paper-deep`, `--ink`, `--ink-soft`, `--ink-muted`, `--rule`, `--rule-soft`, `--accent`, `--ochre`, `--forest`, `--oxblood`, `--plum`, `--serif`, `--sans`, `--mono`. Do not modify these.
3. **i18n override block** (line 387-394): `html[lang="zh-Hant"]` rules. The hero weight fix adds to this block. Do not touch the existing five font-size overrides.
4. **Target components with line numbers (baseline commit `37563e0`):**
   - `.profile-card` @ 732, `::before` @ 740
   - `.profile-lede`, `.profile-grid`, `.profile-cell` @ 751-800 (part of profile-card family)
   - `.metrics` @ 572, `.metric .n`/`.metric .lbl` @ 589-604
   - `.chart-box` @ 962, `.tall/.short/canvas/::after` @ 970-988
   - `details.evidence` and descendants @ 993-1054
   - `.intro-card` @ 446, `::before` @ 455
   - `.dek` @ 437
   - `.method` @ 1081 (+ `ul/li`)
   - `.caveat` @ 1088
   - `.evidence-header` @ 1056
5. **Whitelist of surviving hard-codes** inside target blocks:
   - `1px` for borders (too universal to tokenize usefully)
   - Font sizes `9.5px`, `10.5px`, `11.5px`, `14.5px` — sparse typographic trim
   - Letter-spacing `em` units
6. **Running tests:** `python3 -m unittest tests.test_css_tokens -v` from repo root.
7. **Running build (for pixel diff later):** `python3 scripts/build_html.py --help` to see args; synthesis data builds are already wired through `tests/smoke_test.py` — engineer should inspect it to learn command.

---

## Task 1: Add design-tokens spec reference to CHANGELOG

**Files:**
- Modify: `README.md` or `CHANGELOG.md` — check which exists

- [ ] **Step 1: Check which changelog file exists**

Run: `ls CHANGELOG.md README.md 2>&1`
Expected: file listing. Use whichever exists; if both, prefer CHANGELOG.md; if neither, skip this task.

- [ ] **Step 2: Add unreleased entry**

If CHANGELOG.md exists, prepend an unreleased section. If only README has a changelog-like list, add a bullet under the most recent section.

Example CHANGELOG entry:

```markdown
## Unreleased

- **Design tokens**: Two-layer CSS token system (primitives + semantic aliases) for spacing, radius, font-size, and line-height. All nine main/small components now consume tokens instead of hard-coded values.
- **Fix**: `zh-Hant` hero title no longer renders with thin font-weight 300 on CJK serif fallbacks.
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md  # or README.md
git commit -m "docs: changelog entry for design tokens + zh-Hant hero weight fix"
```

---

## Task 2: Add token primitives to `:root`

**Files:**
- Modify: `scripts/build_html.py` (after line 347, inside `:root { ... }`, before the closing brace at line 348)

- [ ] **Step 1: Write the failing test for primitives**

Create `tests/test_css_tokens.py`:

```python
"""Token system tests.

Enforces the two-layer design token architecture documented in
docs/superpowers/specs/2026-04-19-design-tokens-audit-design.md.
Primitives define the scale; semantic aliases name the intent.
Target component CSS blocks must not contain hard-coded spacing.
"""
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_HTML = REPO_ROOT / "scripts" / "build_html.py"


class TokenPrimitivesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = BUILD_HTML.read_text(encoding="utf-8")

    def test_spacing_primitives_defined(self):
        for n in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15):
            self.assertRegex(
                self.src,
                rf"--space-{n}\s*:",
                f"missing --space-{n} in :root",
            )

    def test_radius_primitives_defined(self):
        for name in ("sm", "md", "lg"):
            self.assertRegex(self.src, rf"--radius-{name}\s*:")

    def test_text_primitives_defined(self):
        for name in ("xs", "sm", "base", "md", "lg", "xl"):
            self.assertRegex(self.src, rf"--text-{name}\s*:")

    def test_leading_primitives_defined(self):
        for name in ("tight", "snug", "normal", "loose"):
            self.assertRegex(self.src, rf"--leading-{name}\s*:")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/Projects/cc-user-autopsy && python3 -m unittest tests.test_css_tokens.TokenPrimitivesTests -v`
Expected: FAIL — AssertionError "missing --space-0 in :root" (or similar).

- [ ] **Step 3: Add primitives to `:root`**

In `scripts/build_html.py`, locate the closing `}` of the `:root` block (line 348). Use Edit with `old_string` matching the last three declarations to anchor, add primitives before the closing brace:

```
old_string:
    --serif: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
    --sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    --mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  }

new_string:
    --serif: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
    --sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    --mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;

    /* --- Spacing primitives (2px granularity, matches existing component values) --- */
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

    /* --- Radius primitives --- */
    --radius-sm: 2px;
    --radius-md: 3px;
    --radius-lg: 6px;

    /* --- Font-size primitives (zh-Hant overrides handled separately) --- */
    --text-xs: 11.5px;
    --text-sm: 13px;
    --text-base: 15px;
    --text-md: 16px;
    --text-lg: 17px;
    --text-xl: 18px;

    /* --- Line-height primitives --- */
    --leading-tight: 1.2;
    --leading-snug: 1.35;
    --leading-normal: 1.55;
    --leading-loose: 1.7;
  }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_css_tokens.TokenPrimitivesTests -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full existing test suite to confirm no regression**

Run: `python3 -m unittest discover -s tests -v 2>&1 | tail -30`
Expected: all tests pass (existing tests don't touch these primitives).

- [ ] **Step 6: Build the HTML and verify output is well-formed**

Run: `python3 tests/smoke_test.py 2>&1 | tail -10`
Expected: script exits 0 (smoke test builds demo HTML successfully).

- [ ] **Step 7: Commit**

```bash
git add scripts/build_html.py tests/test_css_tokens.py
git commit -m "feat(css): add token primitives (space/radius/text/leading)"
```

---

## Task 3: Add semantic aliases to `:root`

**Files:**
- Modify: `scripts/build_html.py` (append to `:root` block after the primitives added in Task 2)
- Modify: `tests/test_css_tokens.py` (add semantic alias test class)

- [ ] **Step 1: Write the failing test for semantic aliases**

Append to `tests/test_css_tokens.py` before the `if __name__` block:

```python
class SemanticAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = BUILD_HTML.read_text(encoding="utf-8")

    def test_card_padding_defined(self):
        self.assertRegex(self.src, r"--card-padding\s*:\s*var\(--space-")

    def test_card_radius_defined(self):
        self.assertRegex(self.src, r"--card-radius\s*:\s*var\(--radius-")

    def test_section_gap_defined(self):
        self.assertRegex(self.src, r"--section-gap\s*:\s*var\(--space-")

    def test_tag_padding_defined(self):
        self.assertRegex(self.src, r"--tag-padding-y\s*:")
        self.assertRegex(self.src, r"--tag-padding-x\s*:")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_css_tokens.SemanticAliasTests -v`
Expected: FAIL.

- [ ] **Step 3: Add semantic aliases inside `:root`**

Edit `scripts/build_html.py`. Use the end of the `--leading-loose: 1.7;` line as anchor and insert aliases before the closing `}` of `:root`:

```
old_string:
    --leading-loose: 1.7;
  }

new_string:
    --leading-loose: 1.7;

    /* --- Semantic aliases (design intent — add new ones as components need them) --- */
    --card-padding: var(--space-12);
    --card-radius: var(--radius-lg);
    --section-gap: var(--space-15);
    --tag-padding-y: var(--space-1);
    --tag-padding-x: var(--space-3);
  }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_css_tokens.SemanticAliasTests -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Smoke build still works**

Run: `python3 tests/smoke_test.py 2>&1 | tail -5`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_html.py tests/test_css_tokens.py
git commit -m "feat(css): add semantic aliases (card-padding/card-radius/section-gap/tag-padding)"
```

---

## Task 4: Add no-hardcode enforcement test (progressively enabled)

**Files:**
- Modify: `tests/test_css_tokens.py`

Logic: the test takes a list of "cleaned components" and asserts no hardcoded px inside their CSS blocks (minus whitelist). Component list starts empty — we add entries in Tasks 5-10 as each component is refactored.

- [ ] **Step 1: Append the enforcement test class to `tests/test_css_tokens.py`**

Append before the `if __name__` block:

```python
# Components that MUST have zero hard-coded px (except whitelist).
# Tasks 5-10 add entries here as each component is refactored.
CLEANED_COMPONENTS: list[tuple[str, str]] = []
# Each tuple is (start_marker, end_marker) — raw substrings that bracket the
# component's CSS rule set in build_html.py. Matching uses find() so markers
# must be unique in the source.

HARDCODE_WHITELIST_PX = {"1px", "9.5px", "10.5px", "11.5px", "14.5px"}


class NoHardcodedSpacingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = BUILD_HTML.read_text(encoding="utf-8")

    def _block(self, start: str, end: str) -> str:
        i = self.src.find(start)
        self.assertNotEqual(i, -1, f"start marker not found: {start!r}")
        j = self.src.find(end, i + len(start))
        self.assertNotEqual(j, -1, f"end marker not found after start: {end!r}")
        return self.src[i:j + len(end)]

    def test_cleaned_components_have_no_hardcoded_px(self):
        pattern = re.compile(r"\b(\d+(?:\.\d+)?px)\b")
        for name, *markers in CLEANED_COMPONENTS:
            start, end = markers
            block = self._block(start, end)
            hits = [m.group(1) for m in pattern.finditer(block)]
            leaked = [h for h in hits if h not in HARDCODE_WHITELIST_PX]
            self.assertEqual(
                leaked, [],
                f"component {name!r} leaks hardcoded px: {leaked}",
            )
```

Update the tuple annotation at the top of the list for clarity:

```python
# Each entry: (name, start_marker, end_marker)
CLEANED_COMPONENTS: list[tuple[str, str, str]] = []
```

(Adjust the `for name, *markers in` loop to `for name, start, end in`.)

- [ ] **Step 2: Run the test to verify it passes with empty list**

Run: `python3 -m unittest tests.test_css_tokens.NoHardcodedSpacingTests -v`
Expected: PASS (1 test — iterates empty list).

- [ ] **Step 3: Commit**

```bash
git add tests/test_css_tokens.py
git commit -m "test: add progressive no-hardcode enforcement for CSS components"
```

---

## Task 5: Refactor `.profile-card` to use tokens

**Files:**
- Modify: `scripts/build_html.py` (lines ~732-800 — `.profile-card`, `::before`, `.profile-lede`, `.profile-grid`, `.profile-cell` family)
- Modify: `tests/test_css_tokens.py` (add entry to `CLEANED_COMPONENTS`)

- [ ] **Step 1: Add `.profile-card` to cleaned list in test (red)**

In `tests/test_css_tokens.py`, update `CLEANED_COMPONENTS`:

```python
CLEANED_COMPONENTS: list[tuple[str, str, str]] = [
    (
        ".profile-card",
        "  .profile-card {",
        "    margin-top: 3px;\n  }",   # end of .profile-cell .sub — last selector in family
    ),
]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_css_tokens.NoHardcodedSpacingTests -v`
Expected: FAIL — "profile-card leaks hardcoded px: ['24px', '48px', '30px', ...]".

- [ ] **Step 3: Refactor the `.profile-card` family block**

Edit `scripts/build_html.py`. Replace the entire block from `.profile-card {` (line 732) through `.profile-cell .sub { ... margin-top: 3px; }` (line 800):

```
old_string:
  .profile-card {
    margin: 24px 0 48px 0;
    padding: 30px 34px 34px 34px;
    background: linear-gradient(135deg, rgba(255,250,240,0.8) 0%, rgba(236,229,213,0.4) 100%);
    border: 1px solid var(--rule);
    border-left: 4px solid var(--accent);
    position: relative;
  }
  .profile-card::before {
    content: "AT A GLANCE";
    position: absolute;
    top: -10px; left: 30px;
    background: var(--paper);
    padding: 0 10px;
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.26em;
    color: var(--accent);
  }
  .profile-lede {
    font-family: var(--serif);
    font-variation-settings: "opsz" 36, "wght" 400;
    font-size: 22px;
    line-height: 1.42;
    letter-spacing: -0.012em;
    color: var(--ink);
    margin: 0 0 22px 0;
  }
  .profile-lede em {
    color: var(--accent);
    font-style: italic;
    font-weight: 500;
  }
  .profile-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
    margin-top: 20px;
    border-top: 1px solid var(--rule);
    border-left: 1px solid var(--rule);
  }
  @media (max-width: 640px) { .profile-grid { grid-template-columns: repeat(2, 1fr); } }
  .profile-cell {
    border-right: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    padding: 14px 16px 16px 16px;
  }
  .profile-cell .k {
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--ink-muted);
    margin-bottom: 6px;
  }
  .profile-cell .v {
    font-family: var(--serif);
    font-variation-settings: "opsz" 72, "wght" 400;
    font-size: 24px;
    line-height: 1.1;
    letter-spacing: -0.02em;
    color: var(--ink);
  }
  .profile-cell .sub {
    font-family: var(--sans);
    font-size: 12px;
    color: var(--ink-muted);
    margin-top: 3px;
  }

new_string:
  .profile-card {
    margin: var(--space-12) 0 var(--space-15) 0;  /* 24px 0 30px 0 — bottom tightened from 48 to 30 to use scale */
    padding: var(--space-15) 34px 34px 34px;       /* 34px horizontal stays hardcoded (exceeds scale, single component) */
    background: linear-gradient(135deg, rgba(255,250,240,0.8) 0%, rgba(236,229,213,0.4) 100%);
    border: 1px solid var(--rule);
    border-left: 4px solid var(--accent);
    position: relative;
  }
  .profile-card::before {
    content: "AT A GLANCE";
    position: absolute;
    top: -10px; left: var(--space-15);
    background: var(--paper);
    padding: 0 var(--space-5);
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.26em;
    color: var(--accent);
  }
  .profile-lede {
    font-family: var(--serif);
    font-variation-settings: "opsz" 36, "wght" 400;
    font-size: 22px;
    line-height: 1.42;
    letter-spacing: -0.012em;
    color: var(--ink);
    margin: 0 0 var(--space-11) 0;
  }
  .profile-lede em {
    color: var(--accent);
    font-style: italic;
    font-weight: 500;
  }
  .profile-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
    margin-top: var(--space-10);
    border-top: 1px solid var(--rule);
    border-left: 1px solid var(--rule);
  }
  @media (max-width: 640px) { .profile-grid { grid-template-columns: repeat(2, 1fr); } }
  .profile-cell {
    border-right: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    padding: var(--space-7) var(--space-8) var(--space-8) var(--space-8);
  }
  .profile-cell .k {
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--ink-muted);
    margin-bottom: var(--space-3);
  }
  .profile-cell .v {
    font-family: var(--serif);
    font-variation-settings: "opsz" 72, "wght" 400;
    font-size: var(--space-12);
    line-height: 1.1;
    letter-spacing: -0.02em;
    color: var(--ink);
  }
  .profile-cell .sub {
    font-family: var(--sans);
    font-size: 12px;
    color: var(--ink-muted);
    margin-top: var(--space-1);
  }
```

**IMPORTANT note for engineer:** two values required an intentional design decision. Document both with inline comments:

1. `margin-bottom: 48px → 30px` (use `--space-15`). 48 was never on the 2/4/8 scale. This is a deliberate micro-regression the pixel diff will catch — if user rejects, fall back to hardcoded `48px` + a TODO instead.
2. `font-size: 24px → var(--space-12)` — reusing space token for a font-size is typographic sin. Replace with `12px` wait — actually `24px` doesn't match any `--text-*`. Add `--text-2xl: 24px` to primitives in Task 2's list **if encountered here**. If the engineer reaches this point without `--text-2xl`, stop and go back to Task 2.

Check before continuing: does `--text-2xl` exist? If not, **pause, add it to Task 2's primitives block, re-run Task 2 tests, then resume here**. Use `--text-2xl` for `.profile-cell .v`.

Replace `font-size: var(--space-12);` with `font-size: var(--text-2xl);` in the new_string above before applying the Edit. (Plan update: during execution, the engineer updates Task 2 in place and then this task.)

Similarly `font-size: 22px` in `.profile-lede` — not on scale. Hardcode survives, note in comment why. For `12px` in `.profile-cell .sub` — add `--text-xxs: 12px` if it occurs repeatedly elsewhere; otherwise hardcode with whitelist.

(The engineer's judgment should prefer adding tokens when the value appears 3+ times in target components; hardcode otherwise with a one-line comment.)

- [ ] **Step 4: Run the no-hardcode test**

Run: `python3 -m unittest tests.test_css_tokens.NoHardcodedSpacingTests -v`
Expected: PASS. If it fails with `22px`/`12px` listed — those are font-sizes not in whitelist. Decide per the judgment above:
- If used elsewhere → extend primitives + whitelist is unnecessary.
- If truly one-off → add to `HARDCODE_WHITELIST_PX` with a comment explaining why.

- [ ] **Step 5: Smoke build**

Run: `python3 tests/smoke_test.py 2>&1 | tail -5`
Expected: exit 0.

- [ ] **Step 6: Pixel diff vs main for profile-card only (manual)**

Run: `git stash && python3 scripts/build_html.py <demo-data-args> -o /tmp/before.html && git stash pop && python3 scripts/build_html.py <demo-data-args> -o /tmp/after.html`

Open both via `/browse`, compare the profile-card region. Any diff beyond ≤1px anti-aliasing: revert the offending rule or add to whitelist with justification.

(Engineer can skip the interactive pixel diff for intermediate commits and do a full diff pass at end.)

- [ ] **Step 7: Commit**

```bash
git add scripts/build_html.py tests/test_css_tokens.py
git commit -m "refactor(css): .profile-card family uses tokens"
```

---

## Task 6: Refactor `.metrics` to use tokens

**Files:**
- Modify: `scripts/build_html.py` (lines ~572-604)
- Modify: `tests/test_css_tokens.py`

- [ ] **Step 1: Add `.metrics` to cleaned list (red)**

In `tests/test_css_tokens.py`, extend `CLEANED_COMPONENTS`:

```python
CLEANED_COMPONENTS: list[tuple[str, str, str]] = [
    (".profile-card", "  .profile-card {", "    margin-top: var(--space-1);\n  }"),
    (".metrics", "  /* Metric cards grid */\n  .metrics {", "    margin-top: var(--space-4);\n  }"),
]
```

(Note: end marker matches the last line of `.metric .lbl` after refactor. Adjust if whitespace differs.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_css_tokens.NoHardcodedSpacingTests -v`
Expected: FAIL.

- [ ] **Step 3: Refactor the `.metrics` block**

Edit:

```
old_string:
  /* Metric cards grid */
  .metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0;
    margin: 30px 0 20px 0;
    border-top: 1px solid var(--rule);
    border-left: 1px solid var(--rule);
  }
  .metrics > .metric {
    border-right: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    padding: 16px 18px 18px 18px;
    background: rgba(255,250,240,0.35);
  }
  @media (max-width: 640px) {
    .metrics { grid-template-columns: repeat(2, 1fr); }
  }
  .metric .n {
    font-family: var(--serif);
    font-variation-settings: "opsz" 72, "wght" 400;
    font-size: 32px;
    line-height: 1;
    letter-spacing: -0.025em;
    color: var(--ink);
  }
  .metric .lbl {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ink-muted);
    margin-top: 8px;
  }

new_string:
  /* Metric cards grid */
  .metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0;
    margin: var(--space-15) 0 var(--space-10) 0;
    border-top: 1px solid var(--rule);
    border-left: 1px solid var(--rule);
  }
  .metrics > .metric {
    border-right: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    padding: var(--space-8) var(--space-9) var(--space-9) var(--space-9);
    background: rgba(255,250,240,0.35);
  }
  @media (max-width: 640px) {
    .metrics { grid-template-columns: repeat(2, 1fr); }
  }
  .metric .n {
    font-family: var(--serif);
    font-variation-settings: "opsz" 72, "wght" 400;
    font-size: 32px;   /* hero-size display number; not on type scale */
    line-height: 1;
    letter-spacing: -0.025em;
    color: var(--ink);
  }
  .metric .lbl {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ink-muted);
    margin-top: var(--space-4);
  }
```

`32px` hero display size is intentionally not tokenized — it's a unique typographic use.

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_css_tokens -v`
Expected: PASS. If `32px` leaks, decide: add `HARDCODE_WHITELIST_PX.add("32px")` with comment, or introduce `--text-display: 32px`.

- [ ] **Step 5: Smoke build**

Run: `python3 tests/smoke_test.py 2>&1 | tail -5`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_html.py tests/test_css_tokens.py
git commit -m "refactor(css): .metrics uses tokens"
```

---

## Task 7: Refactor `.chart-box` to use tokens

**Files:**
- Modify: `scripts/build_html.py` (lines ~962-988)
- Modify: `tests/test_css_tokens.py`

- [ ] **Step 1: Add `.chart-box` to cleaned list (red)**

Append to `CLEANED_COMPONENTS`:

```python
(".chart-box", "  /* Charts */\n  .chart-box {", "    text-transform: uppercase;\n  }"),
```

(End marker = last line of `.chart-box::after`.)

- [ ] **Step 2: Run the test — FAIL**

Run: `python3 -m unittest tests.test_css_tokens.NoHardcodedSpacingTests -v`

- [ ] **Step 3: Refactor**

```
old_string:
  /* Charts */
  .chart-box {
    background: rgba(255,250,240,0.4);
    border: 1px solid var(--rule);
    padding: 18px 20px 14px 20px;
    margin: 20px 0;
    height: 340px;
    position: relative;
  }
  .chart-box.tall { height: 420px; }
  .chart-box.short { height: 260px; }
  .chart-box canvas {
    display: block;
    width: 100%;
    height: 100%;
  }
  .chart-box::after {
    content: attr(data-fig);
    position: absolute;
    top: -8px; right: 18px;
    background: var(--paper);
    padding: 0 8px;
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.2em;
    color: var(--ink-muted);
    text-transform: uppercase;
  }

new_string:
  /* Charts */
  .chart-box {
    background: rgba(255,250,240,0.4);
    border: 1px solid var(--rule);
    padding: var(--space-9) var(--space-10) var(--space-7) var(--space-10);
    margin: var(--space-10) 0;
    height: 340px;   /* fixed chart area; not a spacing token */
    position: relative;
  }
  .chart-box.tall { height: 420px; }
  .chart-box.short { height: 260px; }
  .chart-box canvas {
    display: block;
    width: 100%;
    height: 100%;
  }
  .chart-box::after {
    content: attr(data-fig);
    position: absolute;
    top: -8px; right: var(--space-9);
    background: var(--paper);
    padding: 0 var(--space-4);
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.2em;
    color: var(--ink-muted);
    text-transform: uppercase;
  }
```

`340px`/`420px`/`260px` are fixed chart canvas heights — not spacing; whitelist them:

Update test:

```python
HARDCODE_WHITELIST_PX = {"1px", "9.5px", "10.5px", "11.5px", "14.5px",
                         # Chart canvas fixed heights — not spacing
                         "260px", "340px", "420px",
                         # Negative offset for floating figure label
                         "-8px"}
```

Actually `-8px` would appear as `8px` in regex; the `\b` boundary treats `-` as non-word. Double check by running. If `-8px` leaks, adjust regex to skip negative values, or whitelist `8px` (but 8px is legit usage elsewhere). Preferred fix: make the regex capture `-?\d+...` and whitelist the negative separately.

Simplest: adjust `NoHardcodedSpacingTests._block` regex to `re.compile(r"-?\b(\d+(?:\.\d+)?px)\b")` and then whitelist just the unsigned "8px" once. Or keep current regex (which treats `-8px` as `8px`) and accept that — 8px is a scale-aligned value.

- [ ] **Step 4: Run tests, fix whitelist/regex as needed**

Run: `python3 -m unittest tests.test_css_tokens -v`
Expected: PASS.

- [ ] **Step 5: Smoke build + Commit**

```bash
git add scripts/build_html.py tests/test_css_tokens.py
git commit -m "refactor(css): .chart-box uses tokens"
```

---

## Task 8: Refactor `details.evidence` to use tokens

**Files:**
- Modify: `scripts/build_html.py` (lines ~993-1054)
- Modify: `tests/test_css_tokens.py`

This is the largest component (evidence + summary + .tag + variants + .sid + .proj + .right + [open] + p + p code).

- [ ] **Step 1: Add entry to cleaned list (red)**

```python
("details.evidence", "  /* §06 evidence library */\n  details.evidence {",
 "    word-break: break-all;\n  }"),
```

(End marker = last line of `details.evidence p code`.)

- [ ] **Step 2: Run the test — FAIL**

- [ ] **Step 3: Refactor**

```
old_string:
  /* §06 evidence library */
  details.evidence {
    border-top: 1px solid var(--rule);
    padding: 14px 0;
    margin: 0;
  }
  details.evidence:last-of-type { border-bottom: 1px solid var(--rule); }
  details.evidence summary {
    cursor: pointer;
    list-style: none;
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.4;
    color: var(--ink);
    display: grid;
    grid-template-columns: 90px 1fr 80px;
    gap: 16px;
    align-items: center;
  }
  details.evidence summary::-webkit-details-marker { display: none; }
  details.evidence summary .tag {
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink-muted);
    padding: 3px 8px;
    border: 1px solid var(--rule);
    text-align: center;
    border-radius: 1px;
  }
  details.evidence summary .tag.high_friction,
  details.evidence summary .tag.not_achieved { color: var(--oxblood); border-color: var(--oxblood); }
  details.evidence summary .tag.control_good { color: var(--forest); border-color: var(--forest); }
  details.evidence summary .tag.top_interrupt { color: var(--ochre); border-color: var(--ochre); }
  details.evidence summary .tag.top_token { color: var(--plum); border-color: var(--plum); }
  details.evidence summary .sid {
    font-family: var(--mono);
    font-size: 13px;
    color: var(--ink-soft);
  }
  details.evidence summary .proj { color: var(--ink); }
  details.evidence summary .right {
    text-align: right;
    font-family: var(--mono);
    font-size: 11.5px;
    color: var(--ink-muted);
  }
  details.evidence[open] summary { margin-bottom: 14px; }
  details.evidence[open] summary .sid { color: var(--accent); }
  details.evidence p {
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.55;
    margin: 6px 0;
    padding-left: 106px;
  }
  details.evidence p code {
    font-size: 0.85em;
    background: rgba(0,0,0,0.04);
    color: var(--ink-soft);
    word-break: break-all;
  }

new_string:
  /* §06 evidence library */
  details.evidence {
    border-top: 1px solid var(--rule);
    padding: var(--space-7) 0;
    margin: 0;
  }
  details.evidence:last-of-type { border-bottom: 1px solid var(--rule); }
  details.evidence summary {
    cursor: pointer;
    list-style: none;
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.4;
    color: var(--ink);
    display: grid;
    grid-template-columns: 90px 1fr 80px;   /* summary tri-col layout */
    gap: var(--space-8);
    align-items: center;
  }
  details.evidence summary::-webkit-details-marker { display: none; }
  details.evidence summary .tag {
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink-muted);
    padding: var(--space-2) var(--space-4);
    border: 1px solid var(--rule);
    text-align: center;
    border-radius: 1px;
  }
  details.evidence summary .tag.high_friction,
  details.evidence summary .tag.not_achieved { color: var(--oxblood); border-color: var(--oxblood); }
  details.evidence summary .tag.control_good { color: var(--forest); border-color: var(--forest); }
  details.evidence summary .tag.top_interrupt { color: var(--ochre); border-color: var(--ochre); }
  details.evidence summary .tag.top_token { color: var(--plum); border-color: var(--plum); }
  details.evidence summary .sid {
    font-family: var(--mono);
    font-size: var(--text-sm);
    color: var(--ink-soft);
  }
  details.evidence summary .proj { color: var(--ink); }
  details.evidence summary .right {
    text-align: right;
    font-family: var(--mono);
    font-size: 11.5px;
    color: var(--ink-muted);
  }
  details.evidence[open] summary { margin-bottom: var(--space-7); }
  details.evidence[open] summary .sid { color: var(--accent); }
  details.evidence p {
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.55;
    margin: var(--space-3) 0;
    padding-left: 106px;    /* aligns after summary's 90px col + 16px gap */
  }
  details.evidence p code {
    font-size: 0.85em;
    background: rgba(0,0,0,0.04);
    color: var(--ink-soft);
    word-break: break-all;
  }
```

Note on `padding-left: 106px` and grid `90px 1fr 80px`: these are layout constants tied to summary tri-column. Tagging them as scale-aligned is misleading — whitelist as layout constants:

Update test:

```python
HARDCODE_WHITELIST_PX.update({"80px", "90px", "106px"})   # evidence summary grid
```

- [ ] **Step 4: Run tests and fix per Step 3 judgment**

Run: `python3 -m unittest tests.test_css_tokens -v`
Expected: PASS after whitelist update.

- [ ] **Step 5: Smoke + Commit**

```bash
git add scripts/build_html.py tests/test_css_tokens.py
git commit -m "refactor(css): details.evidence uses tokens"
```

---

## Task 9: Refactor small components (intro-card / dek / method / caveat / evidence-header)

**Files:**
- Modify: `scripts/build_html.py`
- Modify: `tests/test_css_tokens.py`

- [ ] **Step 1: Add all five entries (red)**

Append to `CLEANED_COMPONENTS`:

```python
(".intro-card", "  .intro-card {", "    color: var(--accent);\n  }"),   # ends at ::before
(".dek", "  .dek {", "    margin: 0 0 var(--space-15) 0;\n  }"),        # after refactor
(".method", "  /* §07 methodology */\n  .method {", "    line-height: 1.6;\n  }"),  # before .caveat
(".caveat", "  .caveat {", "    line-height: 1.6;\n  }"),
(".evidence-header", "  .evidence-header {", "    border-bottom: 1px solid var(--rule);\n  }"),
```

**Note:** end markers are sensitive to whitespace. If `find()` returns -1, re-open the file at the target line and copy the exact string verbatim.

- [ ] **Step 2: Run the test — FAIL**

- [ ] **Step 3: Refactor all five**

**3a. `.dek` (lines 437-444):**

```
old_string:
  .dek {
    font-family: var(--sans);
    font-size: 15px;
    line-height: 1.55;
    color: var(--ink-soft);
    max-width: 56ch;
    margin: 0 0 30px 0;
  }

new_string:
  .dek {
    font-family: var(--sans);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    color: var(--ink-soft);
    max-width: 56ch;
    margin: 0 0 var(--section-gap) 0;
  }
```

**3b. `.intro-card` (lines 446-465):**

```
old_string:
  .intro-card {
    border: 1px solid var(--rule);
    background: rgba(255,250,240,0.5);
    padding: 22px 26px;
    margin: 0 0 60px 0;
    font-size: 15.5px;
    line-height: 1.6;
    position: relative;
  }
  .intro-card::before {
    content: "NOTE";
    position: absolute;
    top: -9px; left: 22px;
    background: var(--paper);
    padding: 0 8px;
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.2em;
    color: var(--accent);
  }

new_string:
  .intro-card {
    border: 1px solid var(--rule);
    background: rgba(255,250,240,0.5);
    padding: var(--space-11) 26px;     /* 26px horizontal is component-unique, keep hardcode */
    margin: 0 0 60px 0;                /* 60px = 2× section-gap; rhetorical breathing room */
    font-size: 15.5px;                 /* 15.5 = zh-Hant baseline, intentional parity */
    line-height: 1.6;
    position: relative;
  }
  .intro-card::before {
    content: "NOTE";
    position: absolute;
    top: -9px; left: var(--space-11);
    background: var(--paper);
    padding: 0 var(--space-4);
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.2em;
    color: var(--accent);
  }
```

Whitelist additions as needed: `{"10px", "15.5px", "26px", "60px"}`. Judgment: `26px`, `60px` are intro-card-unique; whitelist with comment. `10px` and `15.5px` — if used elsewhere, tokenize; otherwise whitelist.

**3c. `.method` (lines 1081-1087):**

```
old_string:
  /* §07 methodology */
  .method {
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.6;
  }
  .method ul { padding-left: 20px; margin: 8px 0 14px 0; }
  .method li { margin: 4px 0; }

new_string:
  /* §07 methodology */
  .method {
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.6;
  }
  .method ul { padding-left: var(--space-10); margin: var(--space-4) 0 var(--space-7) 0; }
  .method li { margin: var(--space-2) 0; }
```

**3d. `.caveat` (lines 1088-1096):**

```
old_string:
  .caveat {
    background: rgba(160, 67, 30, 0.06);
    border: 1px solid rgba(160, 67, 30, 0.2);
    border-left: 3px solid var(--accent);
    padding: 14px 20px;
    margin: 16px 0;
    font-size: 14px;
    line-height: 1.6;
  }

new_string:
  .caveat {
    background: rgba(160, 67, 30, 0.06);
    border: 1px solid rgba(160, 67, 30, 0.2);
    border-left: 3px solid var(--accent);
    padding: var(--space-7) var(--space-10);
    margin: var(--space-8) 0;
    font-size: 14px;
    line-height: 1.6;
  }
```

**3e. `.evidence-header` (lines 1056-1065):**

```
old_string:
  .evidence-header {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 34px 0 8px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--rule);
  }

new_string:
  .evidence-header {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 34px 0 var(--space-4) 0;   /* 34px = unique above-header breathing room */
    padding-bottom: var(--space-3);
    border-bottom: 1px solid var(--rule);
  }
```

Whitelist `34px` as a component-unique rhythmic value.

- [ ] **Step 4: Run all tests**

Run: `python3 -m unittest tests.test_css_tokens -v`
Expected: PASS across all 6 cleaned components. Any hardcoded leaks → whitelist + one-line comment, or extend primitives if recurring.

- [ ] **Step 5: Smoke build**

Run: `python3 tests/smoke_test.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_html.py tests/test_css_tokens.py
git commit -m "refactor(css): small components use tokens (intro-card/dek/method/caveat/evidence-header)"
```

---

## Task 10: Fix zh-Hant hero title font-weight

**Files:**
- Modify: `scripts/build_html.py` (append to the `html[lang="zh-Hant"]` override block near line 391, before the `@media` query at 392)
- Modify: `tests/test_css_tokens.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_css_tokens.py`:

```python
class ZhHantHeroWeightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = BUILD_HTML.read_text(encoding="utf-8")

    def test_hero_title_weight_override(self):
        pattern = re.compile(
            r'html\[lang="zh-Hant"\]\s+h1\.title\s*\{[^}]*font-weight:\s*500',
            re.DOTALL,
        )
        self.assertRegex(self.src, pattern)

    def test_hero_title_em_weight_override(self):
        pattern = re.compile(
            r'html\[lang="zh-Hant"\]\s+h1\.title\s+em\s*\{[^}]*font-weight:\s*600',
            re.DOTALL,
        )
        self.assertRegex(self.src, pattern)
```

- [ ] **Step 2: Run — FAIL**

Run: `python3 -m unittest tests.test_css_tokens.ZhHantHeroWeightTests -v`
Expected: FAIL.

- [ ] **Step 3: Add override rules**

Edit `scripts/build_html.py`. Insert after the existing `.caveat` font-size override and before the `@media (max-width: 720px)` block:

```
old_string:
  html[lang="zh-Hant"] .method,
  html[lang="zh-Hant"] .caveat { font-size: 15.5px; }
  @media (max-width: 720px) {
    html[lang="zh-Hant"] body { font-size: 17px; }
  }

new_string:
  html[lang="zh-Hant"] .method,
  html[lang="zh-Hant"] .caveat { font-size: 15.5px; }
  /* Serif variable-weight 300 looks bony on CJK fallbacks (PingFang, Noto
     Serif CJK). Bump to 500 (em: 600) so the Chinese hero reads with
     intent rather than fragility. Latin hero unaffected (lang="en"). */
  html[lang="zh-Hant"] h1.title {
    font-weight: 500;
    font-variation-settings: "opsz" 144, "wght" 500;
  }
  html[lang="zh-Hant"] h1.title em {
    font-weight: 600;
    font-variation-settings: "opsz" 144, "wght" 600;
  }
  @media (max-width: 720px) {
    html[lang="zh-Hant"] body { font-size: 17px; }
  }
```

- [ ] **Step 4: Run — PASS**

Run: `python3 -m unittest tests.test_css_tokens -v`
Expected: all tests pass.

- [ ] **Step 5: Smoke build**

Run: `python3 tests/smoke_test.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_html.py tests/test_css_tokens.py
git commit -m "fix(css): zh-Hant hero title weight 500 (em 600)"
```

---

## Task 11: Full-report pixel diff + PR description

**Files:**
- Nothing committed here — this task produces PR body content and optional screenshots.

- [ ] **Step 1: Build HTML on main and on feat/design-tokens with identical synthesis data**

Run:
```bash
cd ~/Projects/cc-user-autopsy
# Determine the synthesis-demo build command from tests/smoke_test.py
cat tests/smoke_test.py | head -40
```

Based on smoke_test.py, build the demo in both locales on both branches and save four files: `/tmp/en-main.html`, `/tmp/en-branch.html`, `/tmp/zh-main.html`, `/tmp/zh-branch.html`.

- [ ] **Step 2: Open in `/browse` and take screenshots of four regions per locale**

Regions:
1. Letterhead + hero + intro-card
2. Metrics grid
3. One chart box
4. One open `<details.evidence>`

Save before/after pairs to `/tmp/screenshots/`.

- [ ] **Step 3: Diff screenshots manually**

Use any diff tool (e.g. macOS Preview side-by-side, or `/browse` dual-tab). Expected diffs:
- **Intentional**: zh-Hant hero title heavier (task 10)
- **Possibly**: 1-2px anti-aliasing drift on rounded corners
- **Unexpected**: any structural layout shift → investigate before opening PR

- [ ] **Step 4: Push branch + open PR**

Run:
```bash
git push -u origin feat/design-tokens
gh pr create --title "Design tokens: two-layer token system + zh-Hant hero weight fix" --body "$(cat <<'EOF'
## Summary

- Introduce two-layer CSS token system (primitives + semantic aliases): `--space-*`, `--radius-*`, `--text-*`, `--leading-*` + `--card-padding` / `--card-radius` / `--section-gap` / `--tag-padding-*`
- Refactor nine components off hard-coded spacing: `.profile-card`, `.metrics`, `.chart-box`, `details.evidence`, `.intro-card`, `.dek`, `.method`, `.caveat`, `.evidence-header`
- Fix thin `zh-Hant` hero title: new `html[lang="zh-Hant"] h1.title` override bumps `font-weight` 300 → 500 (em 400 → 600) so the Chinese hero reads with proper weight on CJK serif fallbacks

## Test plan

- [x] `tests/test_css_tokens.py` enforces token presence + no hardcoded spacing in cleaned components
- [x] Existing `tests/smoke_test.py` still builds demo HTML in both locales
- [x] Pixel diff `/tmp/screenshots/` pairs: en letterhead/metrics/chart/evidence; zh letterhead/metrics/chart/evidence
- [x] Intentional diff: zh-Hant hero visibly heavier (see screenshots)
- [x] No unexpected layout shift

Spec: `docs/superpowers/specs/2026-04-19-design-tokens-audit-design.md`
Plan: `docs/superpowers/plans/2026-04-19-design-tokens-audit.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (for the engineer)

- **Values expected to survive as hardcode** due to uniqueness: `32px` (metric hero number), `22px` (profile-lede), `340/420/260px` (chart heights), `90/80/106px` (evidence grid), `34px` (evidence-header margin), `26/60px` (intro-card), `10px` (intro NOTE badge), `15.5px` (intro-card font mirrors zh-Hant baseline), `14px/14.5px/9.5px` (micro-typography).
- **Values expected to enter primitives on encounter:** if `24px font-size` shows up repeatedly, add `--text-2xl`. If `12px font-size` does, add `--text-xxs`. **Stop and update Task 2** if needed — don't create scattered new tokens mid-refactor.
- **Whitelist governance:** each whitelisted value gets a one-line comment in the test file explaining why it's not on the scale.
- **If pixel diff shows a regression** beyond anti-aliasing, revert the specific `var(...)` replacement and restore the hardcode with a `/* TODO: tokenize in v2 */` comment.
- **zh-Hant hero diff is intentional** and called out in PR body + screenshot caption.
- **The `NoHardcodedSpacingTests` regex** currently matches `\b(\d+(?:\.\d+)?px)\b`. Negative values like `-8px` get captured as `8px`. If a negative offset breaks the test and `8px` is otherwise a legitimate scale value, adjust the regex to `-?\d+(?:\.\d+)?px` and explicitly whitelist `-8px`.
