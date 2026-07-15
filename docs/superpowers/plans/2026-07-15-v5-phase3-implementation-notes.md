# V5 Phase 3 — implementation notes (temporary; delete after merge)

Substantive deviations from the plan only (deviation point / choice taken / reason). Mechanical transcription of the plan is not logged.

## Task 3 (trend ledger)

- **CSS tokens**: plan's Step 4(e) offered literal hex with a "use CSS vars if the direction-C block defines them" tie-breaker; implementation reuses the existing `var(--c-gold)` / `.c-neg-num` (`var(--c-neg)`) rules instead of redefining. Behaviorally identical; matches `.c-leak-*` idiom.
- **Wiring nesting**: trend-ledger call nested inside the existing `if ledger_block:` (as the plan's Step 4(d) sketch showed). Consequence flagged by review: with a missing/empty `ledger` block the trend section (including its locked note) is skipped even at ≥3 snapshots. Latent-only — `aggregate.py` always emits `ledger`. Accepted as plan-mandated; candidate cleanup on next render touch.

## Task 4 (recruiter rebuild)

- **`hr_scope_body_template` reworded**: the plan's en text ("badges not shown were not earned…") contradicted the plan's own test (`assertNotIn("not earned", html.lower())`). Reworded to "either fell short of the bar or lacked minimum sample" — same semantics, test-consistent, and drops an em-dash. Plan self-contradiction, resolved in favor of the test.
- **`_hr_section_wrap()` helper added** (not in plan): both new HR sections repeated an identical 4-part section skeleton; extracted once. Markup output unchanged.
- **`_exhibit()` deliberately NOT reused** for HR badges/output: the Exhibit frame carries SELF audit vocabulary ("EXHIBIT n" + source lines); leaking it into the recruiter version would blur the two-layer separation. Plain section markup used instead.
- **Shipped-item chrome**: plan offered inline text vs reusing old `hr_shipped_*` keys; implementation chose a third, cleaner variant — new `hr_output_*` locale keys (proj-sub / commits / tok labels) so the HR output ledger is fully localized; old `hr_shipped_*` keys removed with the rest of the dead V4-HR keys.
- **`earned_count` computed twice** (badges section + scope disclosure): accepted duplication; the builder's `-> str` contract wasn't worth breaking for ≤6-item list passes.

## Task 5 (demo + docs)

- **Root-cause fix beyond plan text**: `gen_transcript()` previously emitted `input: {}` for Bash tool calls, so `scan_transcripts.py`'s regex commit detection (`\bgit\s+commit\b` over `input.command`) saw zero commits in ALL demo transcripts — the `shipping_cadence` badge gate was unpassable regardless of session-meta counts. Fixed at the source (demo generator now emits real `git commit` commands matching the meta's claimed commit counts). No production script touched; no bar loosened. This is the Phase-2 "sentinel must actually pass the gate" lesson applied.
- **Determinism**: `random.seed(20260715)` first statement of `main()`; earned badge set pinned exactly as `{root_cause, shipping_cadence, token_efficiency}`, verified across 3 regenerations.

## Final whole-branch review

- Verdict: ready to merge, 0 Critical / 0 Important. All 10 deferred Minor findings triaged SHIP AS-IS; 3 mechanical items (named orchestration constant, seed-42 docstring, dead module-level seed) bundled into a follow-up `chore:` commit on reviewer recommendation.
- Controller-resolved ⚠️: `_BADGE_TEMPLATE_ARGS` keys verified against real `compute_badges` output (script run, zero mismatches).
