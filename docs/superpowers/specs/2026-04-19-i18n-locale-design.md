# i18n locale mechanism for cc-user-autopsy reports

**Status:** Approved (2026-04-19)
**Scope:** PR #10 candidate — `feat: locale-aware HTML report (en + zh_TW)`

## Problem

The generated HTML report mixes languages. UI chrome ("Cache-read tokens", "FAVORITE MODEL", "OVERVIEW") is hard-coded English, while peer-review prose and sample summaries can be Chinese depending on what the user wrote in their sessions. Readers see two voices at once. Worse, there is no path for the user to ask for a fully Chinese report, even though the Chinese version of the prose would not be a translation — it would be a rewrite by a native zh_TW peer reviewer with the same facts and structure.

## Goals

- One CLI flag picks the locale for the entire report. No half-state where chrome is English but prose is Chinese.
- The peer-review document is written once in English (canonical), then re-written into other locales by a native-tone rewrite step — never machine-translated.
- Chrome strings (tile labels, section headers, tooltips, chart legends) live in one Python dict so contributors see both languages side by side.
- A test gate makes adding a new key without filling in every locale a hard build failure.

## Non-goals

- More than two locales for now. Architecture supports adding ja/ko/etc. later but only en + zh_TW ship in this PR.
- Locale auto-detect from transcript content. Mixed-language transcripts make this unreliable, and a wrong guess feels worse than asking.
- Translating chart canvas content with full layout reflow for RTL languages. Only LTR locales for now.

## Decisions (each resolved during brainstorm)

| Decision | Choice | Reasoning |
|---|---|---|
| Where locale is set | CLI flag (`--locale`) plus SKILL.md Step 0 prompt | Single source of truth; user is asked once and the value flows through pipeline |
| Peer-review text strategy | Always generate canonical en peer-review.md; rewrite into target locale as a separate step | Cache the rewrite to disk so the skill is not re-running an LLM on every build |
| Rewrite mechanism | SKILL.md Step 4.5 with the rewrite prompt embedded; agent (Claude) executes it | No extra API key for build_html; prompt is in the skill where it can be iterated by the user |
| String storage | Single `scripts/locales.py` Python dict | ~30 keys, two locales — single dict keeps both languages visible side by side |
| Missing-key behavior | KeyError (fail loud) | Silent fallback to en defeats the whole "no mixed languages" intent |

## Architecture

```
scripts/locales.py        # STRINGS dict + t() helper
scripts/build_html.py     # gains --locale flag; uses t() for all UI chrome
SKILL.md                  # Step 0 asks locale; Step 4.5 conditional rewrite
tests/test_locales.py     # NEW
tests/test_build_html_additions.py  # adds locale cases
```

### `scripts/locales.py`

```python
STRINGS = {
    "en": {
        "cache_read": "Cache-read tokens",
        "favorite_model": "Favorite model",
        # ~30 keys total
    },
    "zh_TW": {
        "cache_read": "快取讀取 Token",
        "favorite_model": "最常用模型",
        # same key set — enforced by test
    },
}

def t(locale: str, key: str) -> str:
    """Return the string for `key` in `locale`. Raises KeyError on miss."""
    return STRINGS[locale][key]
```

### `scripts/build_html.py` changes

- Add `--locale` argument, default `"en"`, choices `("en", "zh_TW")`.
- `<html lang="...">` becomes `lang="en"` or `lang="zh-Hant"`.
- `<title>` and every hard-coded UI string is wrapped in `t(args.locale, "...")`.
- Inline JS gets a `const I18N = $i18n_json;` block so chart legends / tooltips / "no data" placeholders also localize.

### Pipeline / SKILL.md changes

```
Step 0   ask: self/hr/both + locale (en/zh_TW)
Step 1-4 unchanged — peer-review.md is always English
Step 4.5 if locale != en:
           If peer-review.<locale>.md already exists → use it.
           Else: agent runs the embedded rewrite prompt against
                 peer-review.md → writes peer-review.<locale>.md
Step 5   build_html.py --locale <locale> --peer-review peer-review.<locale>.md
```

The rewrite prompt for zh_TW will instruct: native zh_TW peer-reviewer voice, preserve every fact and section header, no translation tone, no AI 公文體, no em-dash 濫用 (per `feedback_writing_style.md`).

## Testing strategy

`tests/test_locales.py` (new):

1. `test_locale_keysets_match` — `STRINGS["en"].keys() == STRINGS["zh_TW"].keys()`. Adding a key without filling both locales fails the build.
2. `test_t_raises_on_missing_key` — `t("en", "nonexistent")` raises KeyError.
3. `test_t_raises_on_unknown_locale` — `t("ja", "cache_read")` raises KeyError.
4. `test_zh_tw_strings_have_no_ai_em_dash` — scan zh_TW values, assert `"——"` is not present (codifies the writing-style rule).

`tests/test_build_html_additions.py` (additions):

5. `test_html_lang_attr_follows_locale` — building with `--locale zh_TW` produces `<html lang="zh-Hant">`.
6. `test_zh_tw_build_has_no_ui_english` — built HTML at `--locale zh_TW` does not contain key English chrome strings (`Cache-read tokens`, `FAVORITE MODEL`, `OVERVIEW`).
7. `test_default_locale_is_en` — omitting `--locale` is equivalent to `--locale en`.

## Files touched

| File | Change |
|---|---|
| `scripts/locales.py` | NEW |
| `scripts/build_html.py` | + `--locale` arg, swap hard-coded strings for `t()`, inject `I18N` JS const |
| `SKILL.md` | Step 0 locale question; new Step 4.5 with rewrite prompt |
| `tests/test_locales.py` | NEW (4 cases) |
| `tests/test_build_html_additions.py` | + 3 locale cases |

Untouched: `aggregate.py`, `sample_sessions.py`, `scan_transcripts.py`, `js/chart_layout.js`. Pure data layer; no UI strings.

## Out of scope (separately tracked)

- **Codex CLI support.** Decision tracked in the author's private memory notes. If pursued, will be a sibling skill, not a `--source` flag on this one — Codex transcripts have no cache_token / facets / scoring layer to align.
