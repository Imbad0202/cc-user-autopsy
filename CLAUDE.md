# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A public Claude Code skill (`SKILL.md` is the skill entry point) that analyzes a user's local `~/.claude/projects/` transcripts and `~/.claude/usage-data/` metadata, then produces a self-contained HTML peer-review report. Python 3.9+, standard library only — no third-party runtime dependencies (pytest is used for testing only).

## Commands

```bash
# Python test suite (the merge gate)
python3 -m pytest tests/ -q

# Single file / filtered tests
python3 -m pytest tests/test_locales.py -q
python3 -m pytest tests/test_build_html_additions.py -k zh_tw -q

# JS chart-layout tests (separate suite — run BOTH suites when touching js/chart_layout.js)
node --test tests/chart_layout.test.mjs

# Regenerate synthetic demo data (tests/demos never use real usage data)
python3 scripts/generate_demo_data.py    # writes to /tmp/cc-autopsy-demo/
```

The manual 4-step pipeline run (no skill/LLM involved, useful for debugging) is documented in README.md § "Running manually".

Known baseline as of 2026-07-14: 2 tests in `tests/test_build_html_additions.py` fail on clean main (`test_zh_tw_build_contains_localized_strings`, `test_disclaimer_placeholder_in_template`) — stale expectations from the story-first template redesign (PR #24), not something you broke. Check against clean main before assuming a failure there is yours.

## Architecture

Two cooperating layers, orchestrated by SKILL.md:

1. **Deterministic Python pipeline** (`scripts/`) — computes every number.
2. **LLM-authored narrative** — Claude (running the skill) writes markdown files (peer-review, try-this-week, case-study) between pipeline steps; `build_html.py` injects them into the report.

Dataflow:

```
scan_transcripts.py → transcript-rows.jsonl   walks ~/.claude/projects/; merges agent-*.jsonl
                                              subagent runs into their parent session rows
aggregate.py        → analysis-data.json      + session-meta + facets; 9-dim rule-based
                                              scoring; API-cost estimate via PRICING dict
sample_sessions.py  → samples.json            ≤24 representative sessions across 7 buckets
[Claude writes peer-review / try-this-week / case-study markdown]
build_html.py       → standalone HTML         thin CLI only; all rendering in report_render.py
```

Cross-file facts to know before editing:

- **`report_render.py` owns all HTML rendering**, including the SELF-vs-HR audience-conditional branches; `build_html.py` is only argument parsing and file loading. When adding a section, decide its audience gate first (see the "Audience-conditional rendering" table in SKILL.md). HR output must never leak session IDs or non-allowlisted project names.
- **Two token universes**: activity/cost metrics come from the rotated transcript pool (~30–60 days of history); the 9-dim scores come from the session-meta pool (longer history, partial coverage). The two panels disagreeing is expected and explained by the report's scope note — don't "fix" it.
- **i18n**: `locales.py` is the single source of truth for UI chrome strings. Both locales (`en`, `zh_TW`) must share the exact same key set; `t()` raises KeyError on a miss (silent en-fallback is deliberately forbidden); zh_TW values must not contain em-dashes. All three rules are enforced by `tests/test_locales.py`. Longer prose lives in `narrative_en.py` / `narrative_zh.py` — the zh side is authored natively, not translated, with structural parity checked by `test_narrative_parity.py`. Locale keys named `chart_*` / `series_*` automatically flow into the inline-JS `I18N` const; the naming convention is the contract.
- **`js/chart_layout.js` is dual-consumed**: inlined into the HTML output by `report_render._load_chart_layout_js()` (which strips the CommonJS export) and loaded directly by `tests/chart_layout.test.mjs` under node:test. It must stay DOM/canvas-free — it takes a `charWidth` measurement function instead.
- **Output HTML must be fully self-contained**: no remote fonts, no CDN scripts, all user-derived text HTML-escaped. `tests/smoke_test.py` enforces offline-safety and XSS escaping end-to-end.
- **Pricing** is pinned in `aggregate.py`'s `PRICING` dict with a dated comment. Update it when Anthropic's public rates change and keep `test_cost_estimate.py`'s table-integrity checks green.
- **`analysis-data.json` is an external schema**: cross-machine merge tooling and third-party consumers read it. Additive fields are fine; deprecations/removals must be recorded in `docs/SCHEMA-CHANGES.md` in the same commit (2-release deprecation window).
- `references/scoring-rubric.md` holds the exact thresholds for the 9 scoring dimensions — keep it in sync when changing scoring logic in `aggregate.py`.

## Privacy / public-repo rules

This is a public repo about analyzing private usage data; the two must never mix:

- Never commit real transcripts, session-meta, facets, or generated reports. Tests and the committed `assets/example-output*.html` use synthetic data only (`generate_demo_data.py`).
- The privacy model is default-deny: in HR/showcase mode, any project not in the user's allowlist is redacted to a category label. Preserve that invariant when modifying the renderer.
- `.gitignore` already blocks the dangerous artifacts (analysis-data.json, profile/allowlist files, usage-data dirs) — don't weaken it.

## Conventions

- Conventional-commit subjects (`feat(scope): ...`, `fix: ...`, `docs: ...`); work lands on `main` via PRs.
- Design/implementation plans live in `docs/superpowers/plans/` as dated markdown files.
