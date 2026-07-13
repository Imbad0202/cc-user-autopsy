# AI Work Ledger — cc-user-autopsy V5 redesign

**Date:** 2026-07-14
**Status:** draft, pending user review
**Supersedes:** the V4 "story-first" report structure and the V4 HR-mode disclosure philosophy. Does NOT replace the pipeline architecture (scan → aggregate → sample → render), the privacy default-deny model, the i18n system, or the evidence-traceability discipline — those are retained.

---

## 1. Why rebuild

The V4 report answers "how closely does your behavior match a model user" — a report card. Report cards are read once and filed. Ledgers get consulted, because they answer questions the reader actually acts on.

A heavy user's real questions, ranked:

1. **What did my time and quota buy?** (output)
2. **Where am I leaking, how much, is it worth fixing?** (leaks)
3. **Is my tool mix and routing right?** (team)
4. **Am I getting better?** (trend)

V4 answers #2 partially and the rest barely.

**The decision test.** A report block earns its place only if reading it can change one of the four decisions the reader can actually make:

- which kind of work goes to which tool
- what to do in which time slot
- whether to invest more in up-front instructions before starting
- which subscriptions to keep

Blocks that map to none of these are demoted to the appendix or cut.

## 2. Two-layer credibility model (accreditation pattern)

The report follows the structure of an accreditation system: **the standard and process must be objective; results that pass the standard are legitimately promotable.**

- **Audit layer** (process — the SELF report): rigorous, symmetric, accountable. Full findings including failures, leaks, and blind spots. Equivalent to the full site-visit report, addressed to the auditee for improvement.
- **Badge layer** (results — external versions): claims that cleared published thresholds render as badges and may be displayed affirmatively, without apology. Claims that did not clear are silently absent — never shown as "failed", never inflated into a pass.

**Credibility source.** External versions do not derive credibility from displaying weaknesses. They derive it from the standard being public, versioned, threshold-explicit, and reproducible: this repo is public, badge criteria live in `references/scoring-rubric.md`, and anyone can run the same skill on their own data to earn (or fail to earn) the same badges. A self-drawn ruler is marketing; a public ruler is a standard.

**Scope-cutting vs conclusion-cutting.** Privacy redaction (hiding *which project*) is allowed everywhere. Conclusion manipulation (inflating a number, cherry-picking evidence within a claim, presenting an unearned badge) is forbidden everywhere.

### Audit discipline rules

Apply to the audit layer and to all generated prose in every version:

1. **Numbers before adjectives.** Evaluative adjectives must anchor to a number and threshold. Narrative-generation prompts explicitly forbid cheerleading and sandwiching. A praise-word lint (en + zh_TW word lists) runs as a hard test on demo fixtures and as a build-time warning on real builds.
2. **Symmetric sourcing.** Positive claims require evidence sessions at the same bar as negative claims. Unsourceable claims are cut.
3. **Self-referential comparison only.** No population data exists; the report never implies "better than most users". All comparisons are against the user's own history and are labeled as such. Badges are threshold-based, never percentile-based.
4. **Lower-bound output accounting.** The output ledger lists only evidence-backed deliverables, and the graveyard (unfinished work) is displayed alongside it, so the output chapter carries its own counterweight.
5. **Blind-spot findings are confidence-gated.** Below the gate, the entire block is suppressed. Fabricated surprise damages the report's credit more than absence.
6. **Badge wording is template text defined by the standard**, not LLM freestyle prose.

## 3. SELF report structure (the audit document)

0. **Opening line** — one sentence: what the AI team delivered this period, what it cost, the single biggest leak. Thirty-second read.
1. **Output ledger** — evidence-backed deliverables: commits, decks, reports, deployments, published skills. Opener blind spot: **the graveyard** (substantive artifacts written in sessions, never committed, project untouched since).
2. **Team ledger** — cross-LLM panorama: weekly share per tool, parallel-work heatmap (weekday × hour concurrency), project × tool routing matrix, Claude-vs-Codex head-to-head card (the only two full-tier sources). Opener blind spot: **the switch tax** (quality metrics in high-parallelism windows vs single-tool windows). Every source carries a coverage badge (full / partial / presence-only) and its own date range; cross-source comparisons render only over the common time window.
3. **Leak ledger** — top-3 leaks, each with an estimated weekly cost and one concrete fix. Opener blind spots: **repeated-instruction tax** and **sunk-cost sessions**.
4. **Trend ledger** — key ledger numbers this run vs last run vs three months ago. Opener blind spot: **habit drift** (instruction quality decaying as trust grows). Hidden until ≥3 snapshots exist; shows "unlocks after N more runs" instead.
5. **Appendix** — the 9-dimension scores (retained in full, demoted from main narrative), methodology, claim-indexed evidence library.

## 4. Badge layer and external versions

### Badge definitions

Live in `references/scoring-rubric.md`, versioned alongside the suite. Each badge = explicit metric conditions + minimum sample size. Initial badge set (bars provisional, marked v1 in the rubric):

| Badge | Earned when (sketch) |
|---|---|
| Delegation | Task-agent adoption ≥ bar AND good-outcome rate on delegated sessions ≥ bar, over ≥ N scored sessions |
| Root-cause debugging | Debugging-loop co-occurrence below bar over ≥ N scored sessions |
| Tool breadth | Distinct-tool and MCP adoption ≥ bar |
| Token efficiency | Tokens-per-good-outcome and cache ratio within bar |
| Shipping cadence | Output-ledger deliverables per active week ≥ bar (evidence-backed count only) |
| Cross-tool orchestration | Sustained multi-source parallel work with ≥2 full-tier sources ≥ bar |

### External recruiter version (v1 scope; peer/public and manager versions deferred)

Order: identity card → earned badges (each with its criteria line and privacy-safe evidence pointer) → output ledger (allowlist-filtered) → one real case study → methodology & scope disclosure.

The scope disclosure states: which dimensions were assessed, the standard version, where the standard lives, and that the reader can reproduce the assessment on any user's data. It replaces V4's "self-awareness caveat". The V4 rules "do not name hidden weak dimensions" and the "Why interview this person" pitch section are **both removed** — the former is superseded by full scope disclosure, the latter by badges + verifiable characteristics (every line a falsifiable claim).

Privacy is unchanged from V4: default-deny allowlist, no session IDs, and additionally **no cross-LLM prompt text is ever quoted in any external version**.

## 5. Blind-spot engine

The report's unique value is surfacing what the user cannot self-report. Every ledger book opens with one. Heuristics, data requirements, and gates:

| # | Blind spot | Detection heuristic | Gate (below → suppress) |
|---|---|---|---|
| 1 | Repeated-instruction tax | Recurring normalized instruction patterns across sessions and across tools (Claude, Codex, Grok prompt histories) | ≥5 occurrences spanning ≥3 distinct weeks |
| 2 | Sunk-cost sessions | In-session token acceleration + not-achieved outcome, followed by a later fresh session on a similar prompt succeeding quickly | ≥3 confirmed pairs |
| 3 | Switch tax | Friction/interrupt/outcome rates in high-concurrency windows vs single-tool windows (outcome labels exist only for Claude sessions) | ≥20 scored sessions in each bucket |
| 4 | Graveyard | Sessions with substantive file writes, no commit, project untouched ≥14 days after; scratchpad/tmp paths and `(unknown)` project excluded | ≥2 qualifying items |
| 5 | Habit drift | Prompt length/specificity trend vs outcome trend over ≥8 weeks | ≥8 weeks of data or ≥3 snapshots |
| 6 | Ask-vs-ship mismatch | Goal-category share of prompts vs share of shipped output-ledger items | Facets present; ≥N scored sessions |
| 7 | Interrupt win-rate | Post-interrupt outcome vs non-interrupt baseline (upgrade of D5) | Existing D5 sample gates |

Placement: blind spots 1–5 open their books (§3). Blind spots 6 and 7 render inside the leak ledger body as secondary findings.

Counterexample guard: any pattern that occurs at a similar rate in `fully_achieved` sessions drops below gate automatically (exploration must not be mislabeled as waste).

## 6. Cross-LLM data layer

Local sources as probed on 2026-07-14 (formats owned by their vendors; adapters must degrade gracefully when formats change):

| Source | Location | Available signals | Tier |
|---|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` + usage-data | full transcripts, tokens, models, outcome labels | full |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` | session id, UTC timestamp, cwd, model + effort (`turn_context`), token_count incl. cached/reasoning, full message stream | full |
| Grok CLI | `~/.grok/sessions/<urlencoded-cwd>/prompt_history.jsonl` | prompt text, session_id, timestamp, is_bash — no tokens, no model, no tool calls | partial |
| Antigravity | `~/.gemini/antigravity/conversations/*.pb` | protobuf, no public schema; file count + mtime only. No reverse engineering. | presence-only |

**Adapters:** `scripts/scan_codex.py`, `scripts/scan_grok.py`, `scripts/scan_antigravity.py`, each emitting the same row shape as `scan_transcripts.py` plus two fields: `source` and `coverage`. Missing fields are `null`, never imputed. All timestamps normalized to local timezone (Codex stores UTC).

**Aggregation:** `aggregate.py --cross-llm-rows <file>` (repeatable). Cross-tool metrics land in new additive `analysis-data.json` blocks. The 9-dim scoring pool remains Claude-only — the rubric encodes Claude-specific work patterns and would misfire on other tools.

**Parallel detection:** overlapping `[start, end]` windows across sources → hourly concurrency series, weekday × hour parallel heatmap, daily max-parallel count. Midnight-spanning sessions are split at day boundaries.

## 7. Data model and schema changes

- `analysis-data.json`: new additive top-level blocks `ledger`, `cross_llm`, `blind_spots`, `badges`. Documented in `docs/SCHEMA-CHANGES.md` in the same commit (additive policy — no deprecations required).
- **Snapshot hook (ships in Phase 1, day one):** after a successful build, `build_html.py` appends one line `{date, schema_version, scores, badges, key ledger metrics}` to `~/.claude/usage-data/autopsy-history.jsonl`. Corrupt lines are skipped on read. Append failure warns, never fails the build.
- `SKILL.md` rewritten: Step 3 narrative becomes ledger narration (one opener claim per book, audit-discipline rules embedded in the writing instructions); Step 0's ask-first gate is unchanged.

## 8. Rendering

- New sections per §3; the audience-conditional table in SKILL.md is rewritten for audit/badge layers.
- `locales.py` gains keys for all new chrome in both locales (key-set parity and zh_TW em-dash bans enforced by existing tests).
- New charts: weekly tool-share (stacked), parallel heatmap, project × tool matrix, head-to-head card, graveyard list, leak cards, trend sparklines.
- Praise-word lint: shared word lists (en, zh_TW) consumed by both the hard test (demo fixtures) and the build-time warning path.

## 9. Phasing

Approved sequencing (option B, re-scoped to the ledger design). Each phase gets its own implementation plan, its own PR, and must pass both test suites plus a review pass before landing.

- **Phase 1:** adapters (Codex/Grok/Antigravity) + snapshot hook + SELF skeleton (opening line, output ledger, team ledger) + SKILL.md rewrite + `generate_demo_data.py` extended to emit synthetic data for all four sources.
- **Phase 2:** leak ledger + blind-spot engine (7 heuristics with gates and the counterexample guard).
- **Phase 3:** trend ledger UI + badge layer + recruiter version rebuild.

## 10. Error handling

- Per-file parse failure in any adapter: skip and count; `parse_errors` per source reported in methodology.
- Source directory absent: source card renders "not detected", everything else proceeds.
- Data below a gate: the dependent block is suppressed entirely (no apologetic placeholders).
- Snapshot read: tolerate and skip corrupt lines.

## 11. Testing

- Adapter units with synthetic fixtures only (never real user data), covering: format parsing, UTC→local normalization, URL-encoded cwd decoding (Grok), orphan/malformed rows.
- Common-window computation and concurrency overlap edge cases (midnight spans, zero-overlap sources).
- Blind-spot heuristics: threshold tests per gate + counterexample-guard tests.
- Praise-word lint: both locales, both the test path and the warning path.
- Locale key parity extended to all new keys.
- Privacy assertions for external builds: no session IDs, no non-allowlisted project names, no cross-LLM prompt text, badge section renders earned-only.
- Smoke: offline-safety + XSS with cross-LLM data present.

## 12. Out of scope

- Follow-through verification loop ("did you do last report's homework") — offered, declined by user.
- Antigravity protobuf parsing.
- Population benchmarks or percentile claims.
- Peer/public and manager external versions (deferred; badge layer is designed to support them later).
- Windows paths.

## 13. Defaults chosen (flag at review if wrong)

- Trend ledger unlocks at **3 snapshots**.
- Graveyard revisit horizon: **14 days**.
- Badge bars: initial values written into the rubric as **provisional v1**, revisited after first real runs.
- Common window shorter than **14 days** → cross-source comparison charts degrade to per-source panels with an explanatory note.

---

## Progress log

**2026-07-14** — Spec drafted and pushed; user review of the spec body still pending. Frontend direction explored with three synthetic-data mocks (in `mocks/`):

- `mock-a-audit-ledger.html` — audit dossier × bank statement (vermillion seals, red/black ledger ink). **Rejected**: reads as an official/cold costume.
- `mock-b-instrument-log.html` — instrument × engineering log (spec plate, channels, anomaly log). **Rejected**: same reason, technical costume.
- `mock-c-business-report.html` — professional business report: executive summary with assertive finding sentences, action-title section heads, numbered Exhibits with source lines, gold annotation callouts as the signature element, warm-white/charcoal/gold `#B08A2E`/negative-red `#9C201A` (gold-red CVD ΔE 25.5, validated). **Delivered, awaiting user confirmation.**

§8 Rendering is to be rewritten around direction C once the user confirms. Next step after confirmation: writing-plans for Phase 1.
