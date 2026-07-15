---
name: cc-user-autopsy
description: Produces a deep, honest peer-review of how someone uses Claude Code by statistically analyzing their local session data (~/.claude/usage-data/ and ~/.claude/projects/). Trigger whenever the user asks to review, analyze, audit, or critique their own Claude Code usage, workflow, habits, or skill level — including phrases like "analyze my cc usage", "review my cc sessions", "peer review my cc workflow", "deeper than /insights", or any ask for an honest audit of their AI workflow. Also covers portfolio/hiring-manager framings (e.g. "portfolio for Anthropic/OpenAI/xAI"), but ALWAYS ask the user in Step 0 which version to build (self / hr / both) before running — never silently produce an HR report, because that version goes to outsiders and needs explicit privacy setup. The HTML report is laid out ledger-first for SELF (opening band, output/team/leak/trend ledgers, then peer review, 9-dim scoring, try-this-week, case study, claim-indexed evidence). The HR variant is a recruiter version v1: identity card, earned badges (threshold-based, earned-only), allowlist-filtered output ledger, one case study, and a methodology & scope disclosure — no scores, no peer-review memo, no charts.
---

# Claude Code User Autopsy

Produces an honest, evidence-traceable peer-review of a user's Claude Code workflow.

## When NOT to use

The frontmatter above describes when to trigger this skill. One case to skip:

**If the user only wants one narrow statistic** that a single grep / ls / wc can answer (e.g. "how many sessions did I run this week") — just answer directly. This skill is for holistic peer review, not ad-hoc lookups.

## What this skill produces

A self-contained HTML report at `~/.claude/usage-data/cc-user-autopsy.html` (or `-hr.html` for portfolio audience). The V4 layout is story-first, not dashboard-first:

**SELF audit layout** (private diagnostic letter):

0. **AI work ledger** (opening band, output ledger, team ledger, leak ledger, trend ledger) — SELF-only, rendered before everything else including the usage snapshot; see Step 3b. Trend ledger unlocks at 3 snapshots (before that it renders a locked one-liner instead of the exhibit).
1. **Usage snapshot** §01 — activity panel (cache, models, cost, characteristics) + a 4-tile behavior strip (commits / interactive time / Task agent % / MCP %). Replaces the old 8-tile metric grid. Benchmark caveat at the top.
2. **Reading guide** — short paragraph orienting the four-zone story (when / how / where stuck / cost).
3. **Peer review** §02 — Claude-written story in 4 sections plus a "connecting it back" paragraph. Comes BEFORE scoring so the grid reads as an index, not a verdict.
4. **9-dim scoring** §03 — 9 rule-based scores (1-10) across delegation, root-cause debugging, prompt quality, context management, interrupt judgment, tool breadth, writing consistency, time-of-day management, token efficiency.
5. **This week, try this** §04 — 3-5 hand-curated action items derived from peer-review claims.
6. **Case study** §05 — the strongest single session, opened by a metric strip headline (e.g., "451 min · 14 commits · 56 tests · deploy · fully achieved") and three paragraphs (problem / orchestration / shipped).
7. **Pattern mining** §06 — charts for prompt-length × outcome, friction categories, tool usage, weekday × hour heatmap, helpfulness self-rating.
8. **Weekly trends** §07 — growth curve plus 5 weekly detail charts (sessions / tokens / good rate / friction / prompt length).
9. **Evidence library** §08 — claim-indexed (not by 7 tag buckets). Each peer-review claim shows 2-3 sessions that prove it. Empty claim groups are hidden, not apologetically labeled.
10. **Methodology footer** — small-type appendix, not a full section.

**HR / portfolio layout** is the recruiter version v1 — a five-block layout, not a trimmed copy of the SELF layout:

- **Identity letterhead** (`--profile`, full letterhead style, not the SELF subtle signature).
- **Hero block** — practice summary framing (not the SELF diagnostic-letter framing).
- **Earned badges** (`id="badges"`) — threshold-based, earned-only. A badge either clears its published bar or it doesn't show at all; if zero badges are earned the whole section is absent (never rendered as a row of greyed-out locks).
- **Output ledger** (`id="hr-output"`) — allowlist-filtered counters (git commits/pushes/sessions-with-commits) plus the top-3 public shipped items and public artifact links. Non-public items are excluded entirely, never shown as "Private project" filler.
- **One case study** — same format as SELF's case study, redacted project label, no sid.
- **Methodology & scope disclosure** (`id="method"`) — standard version, earned/total badge count, rubric location, reproducibility note, privacy model. Replaces the old self-awareness caveat.

No scores, no peer-review memo, no pattern mining, no weekly-trends charts, no evidence library, no trend ledger in HR — all of that is SELF-only.

Both audiences get a **benchmark caveat** disclaimer at the top reminding readers this is unbenchmarked individual data.

## Workflow overview

```
Step 0   → ASK which version (self / hr / both) and which locale (en / zh_TW).
           For HR, collect profile + public-projects allowlist + artifacts BEFORE running.
Step 1a  → scripts/scan_transcripts.py     (merges subagent tokens into parent sessions)
Step 1b  → scripts/aggregate.py            (combines transcript-rows + session-meta + facets)
Step 1c  → scripts/scan_codex.py / scan_grok.py / scan_antigravity.py  (optional, cross-LLM)
           re-run aggregate.py with --cross-llm-rows (repeatable)
Step 2   → scripts/sample_sessions.py      (picks 15-24 representative sessions)
Step 3   → Claude writes peer-review.{locale}.md  (SELF only, V4 story format — HR needs no peer-review file, see Step 3 HR note below)
Step 3b  → Claude writes ledger-narration.md (SELF only, V5 addition; opening/output/team/leak)
           (SELF only; books: opening/output-ledger/team-ledger/leak-ledger/trend-ledger — write the trend-ledger book ONLY if ~/.claude/usage-data/autopsy-history.jsonl has ≥3 snapshot lines; check with wc -l)
Step 3.5 → Claude writes try-this-week.{locale}.md (SELF only)
           Claude writes case-study.{self|hr}.{locale}.md (BOTH audiences, two files)
Step 4.5 → (zh_TW only) rewrite the EN peer review natively into zh_TW
Step 4   → scripts/build_html.py with --peer-review --try-this --case-study --audience --locale
           (SELF adds --ledger-narration; both audiences take --history-file)
Step 5   → open the HTML in browser and tell the user
```

Each script is idempotent. If a step fails, re-run it.

## Step 0 — Ask first, build second

Before running anything, **ask the user two questions in a single prompt**. Never guess from keywords.

> "I can build two versions of this report:
>   **A. Self audit** — honest diagnostic letter for your eyes only. Shows every project name, session ID, and friction detail.
>   **B. HR / portfolio** — public-facing summary for recruiters. Hides private projects, redacts session IDs, and leads with an identity letterhead + earned badges.
>   **C. Both.**
> Which one(s)?
>
> Output language:
>   **1. English (default)**
>   **2. Traditional Chinese (zh_TW)** — chrome strings and peer-review prose will be in zh_TW. The peer-review will be rewritten natively (not translated) in Step 4.5.
>
> If you don't specify, I'll build English."

Running `/cc-user-autopsy` without an explicit request is a **self** audit in **English** by default. Never silently produce an HR version — that version will be shown to outsiders and the user may not want certain projects visible.

### If the user picks B or C, collect BEFORE Step 1:

1. **Profile** — name, role, location, tagline, contact (email / github / website), extra links. Check memory first so you don't re-ask things already known. Confirm each field before writing `~/.claude/cc-autopsy-profile.json`.

2. **Public-repo allowlist** — ask explicitly:
   > "The HR report will show project names in charts and shipped-work highlights. Which repos are you comfortable listing by name? Everything else will be anonymised to a generic category label so private/client work doesn't leak."
   You can offer to check `gh repo list <user> --visibility public --json name,isFork` as a starting point, then confirm with the user which of those they actually want in the report (public ≠ auto-include). Save the final list to `~/.claude/cc-autopsy-public-projects.json`:
   ```json
   {
     "public_projects": ["repo-name-1", "repo-name-2"],
     "category_overrides": {
       "internal-repo-a": "Higher-ed QA platform",
       "client-work-b": "Consumer iOS app"
     }
   }
   ```
   Default-deny: anything not in `public_projects` is redacted. `category_overrides` gives a human-readable label for redacted projects (optional; falls back to "Private project").

3. **Optional public artifacts** — live URLs the user *wants* to surface (personal site, published skills, open-source work). Save to `~/.claude/cc-autopsy-artifacts.json`.

The HR build MUST run with `--public-projects ~/.claude/cc-autopsy-public-projects.json` whenever that file exists. Without it, HR mode anonymises **every** project — safe default, but the report is thinner.

Self version does not need any of this; it shows raw data to the user themselves.

## Step 1 — Aggregate quantitative data

### Step 1a — Scan transcripts (recommended; enables accurate tokens/models/cost)

```bash
python3 scripts/scan_transcripts.py --output /tmp/cc-autopsy/transcript-rows.jsonl
```

What it does:
- Walks every `~/.claude/projects/**/*.jsonl`
- Emits one row per real session (UUID-named jsonl)
- **Critically: merges `agent-*.jsonl` (subagent runs) into the parent session's row.** Parent sid comes from the `sessionId` field inside each subagent record. Without this, haiku/sonnet usage from subagent dispatches is invisible and cache tokens undercount by ~2x.
- Orphan subagents (parent transcript already cleaned up by Claude Code's rotation) produce a synthetic row marked `orphan_subagent_only=true` so their tokens still count in the activity pool.

### Step 1b — Aggregate

```bash
python3 scripts/aggregate.py \
  --transcript-rows /tmp/cc-autopsy/transcript-rows.jsonl \
  --output /tmp/cc-autopsy/analysis-data.json
```

What it does:
- Reads the transcript-rows file (for the activity/cost/model panel — the "full pool")
- Reads every `~/.claude/usage-data/session-meta/*.json` (for the 9-dim scoring pool — Claude Code's LLM-labeled subset)
- Reads every `~/.claude/usage-data/facets/*.json` if present (optional — report facets_coverage=0 if absent)
- Computes: token distribution, tool counts, weekday×hour heatmap, project breakdown, friction/outcome crosstabs, interrupt × outcome correlation, weekly series, efficiency ratios, prompt-length vs outcome, extremes lists, **API-equivalent cost** (blended by model-share across `PRICING` table)
- Writes `analysis-data.json` with every number the HTML needs

### Methodology note: two token universes

Activity metrics (tokens, cache, models, cost, active_days) come from the **full transcript pool**, which Claude Code rotates — typically the last ~30–60 days.

9-dim scores come from the **session-meta pool**, which has LLM-derived labels (outcome, friction, goal categories) but partial coverage of history.

If both numbers disagree (e.g. activity shows 150 sessions, scoring shows 420), that's expected. The HTML scope_note explains this to the reader.

### Step 1c — Cross-LLM scan (optional; enables the AI work ledger)

If the user works across multiple AI coding tools (Codex CLI, Grok CLI, Antigravity), run the three adapters before re-aggregating. Each adapter is safe to run even if its source directory doesn't exist — it just emits zero rows, don't skip the step to "check first."

```bash
python3 scripts/scan_codex.py --output /tmp/cc-autopsy/codex-rows.jsonl
python3 scripts/scan_grok.py --output /tmp/cc-autopsy/grok-rows.jsonl
python3 scripts/scan_antigravity.py --output /tmp/cc-autopsy/anti-rows.jsonl
```

(Defaults: `~/.codex/sessions`, `~/.grok/sessions`, `~/.gemini/antigravity/conversations` — no need to pass `--sessions-dir` / `--conversations-dir` unless the user's install is non-standard.)

Then re-run `aggregate.py` with the three outputs added:

```bash
python3 scripts/aggregate.py \
  --transcript-rows /tmp/cc-autopsy/transcript-rows.jsonl \
  --cross-llm-rows /tmp/cc-autopsy/codex-rows.jsonl \
  --cross-llm-rows /tmp/cc-autopsy/grok-rows.jsonl \
  --cross-llm-rows /tmp/cc-autopsy/anti-rows.jsonl \
  --output /tmp/cc-autopsy/analysis-data.json
```

Coverage tiers, one sentence each:
- **Codex — full**: tokens, models, and transcript content are all read, same shape as Claude's own transcript pool.
- **Grok — partial**: only prompt text and timestamps are available; no token counts, no model names.
- **Antigravity — presence-only**: no parsing of conversation content at all, just file count and mtime (the format has no public schema, so the scanner deliberately does not reverse-engineer it).

`--cross-llm-rows` only feeds the `cross_llm` / `ledger` blocks (Step 3b's ledger narration, specifically the team-ledger book). **The 9-dim scores stay Claude-only** — cross-LLM rows never enter the scoring pool.

### If you skip Step 1a

`aggregate.py` still works without `--transcript-rows` — it falls back to session-meta-only. But you'll get:
- **0 cache tokens** (session-meta doesn't record them)
- **0 cost estimate** (needs token breakdown to compute)
- **null favorite_model** (session-meta doesn't record models)
- **2-5x undercount of total tokens** (session-meta's `input+output` misses cache_read, which dominates)

Skip Step 1a only if transcripts are unavailable.

Required: session-meta dir must exist. If it doesn't, tell the user to run a few Claude Code sessions first so usage data accumulates.

Facets are optional but recommended. If `facets/` is empty:
- Tell the user: "Your report will be rule-based only — no outcome/friction labels. Running `/insights` once will produce facets and enable richer analysis."
- Continue with best-effort report.

## Step 2 — Sample representative sessions

Run:

```bash
python3 scripts/sample_sessions.py \
  --input /tmp/cc-autopsy/analysis-data.json \
  --output /tmp/cc-autopsy/samples.json
```

What it does:
- Picks up to 24 representative sessions across 7 buckets:
  - 5 highest-friction (if facets available)
  - 5 top-tokens
  - 5 most-interrupts
  - 4 not_achieved (if facets)
  - 3 partial_achieved (if facets)
  - 4 control (fully_achieved + essential helpfulness)
  - 2 user_rejected_action (if facets)
- Finds each session's `.jsonl` under `~/.claude/projects/**/*.jsonl`
- Writes a compact transcript summary (first/last 10 turns, user prompts, tool call sequences) into `samples.json`

Do not pass full transcripts back to yourself — the compact summary is enough.

## Step 3 — Write the personalized peer review (V4 story format)

Read `/tmp/cc-autopsy/analysis-data.json` and `/tmp/cc-autopsy/samples.json`. Write a peer review as markdown.

**Do NOT use the old "3 strengths + 3 improvements + 1 observation" format.** That format reads as a performance review and buries causality. V4 uses a four-zone story structure with causal flow.

### SELF audience format

Write to `/tmp/cc-autopsy/peer-review.{locale}.md` (e.g. `peer-review.zh_TW.md` or `peer-review.en.md`):

```markdown
### The story in one frame

<2-3 sentences. Open with one big scale number, then declare the four-zone outline:
when you work, how you direct the AI, where you get stuck, what it costs.>

---

### 1. When: <one-line claim about time-of-day patterns>

<paragraph(s) of evidence: hour-by-hour friction or good-rate numbers, the
worst/best hour, the score (D8). Then an actionable fix tied to specific hours.>

> Maps to D<n> <dimension>. <Optional: which chart visualises it.>

---

### 2. How: <one-line claim about delegation/prompts/tools>

<3 sub-sections (bolded inline): **Delegation**, **Prompts**, **Tools**.
Each names the metric, cites at least one session ID for SELF.>

These score D1 / D3 / D6 at <scores>. **The "how" layer is not the problem.**

---

### 3. Where you get stuck: <one-line claim about meander / debugging / interrupt>

<Meander block with token-without-commit data; context-management note;
interrupt-recovery rate with one good-recovery session example.>

Maps to D2 / D4 / D5.

---

### 4. What it costs: <one-line claim about efficiency + leaks>

<Token-efficiency ratio. Then 1-2 lower-confidence "leaks" worth naming:
project concentration, weekly volatility, path-hygiene concerns.>

---

### Connecting it back

<One paragraph saying which zone is upstream of which, naming the single
load-bearing fix. End with a one-line redirect to the appendix below.>
```

Length target: 700–1000 words. The story format runs longer than the old 3+3+1 list but reads in one pass.

### How to write this section well

- **Be honest and direct.** No sandwiching. No performance-review platitudes.
- **Every claim cites a number from `analysis-data.json` or a session ID from `samples.json`.** Numbers are the spine.
- **Connect zones causally.** The "connecting it back" paragraph must state which zone is upstream (cause) and which is downstream (effect). If you can't connect them, the story isn't ready.
- **Pick ONE load-bearing fix.** The story has to end with "fix this upstream zone first" so the reader has somewhere to act. Don't list 5 things — pick the strongest leverage point and say so.
- **No em-dash overuse in zh_TW.** Use commas, colons, or new sentences. Per `feedback_writing_style`: 中文寫作不濫用破折號。

## Step 3b — Write the AI work ledger narration (SELF only, V5 addition)

The ledger narration is a **separate file from the peer review**, feeding a **separate, earlier-rendered block** in the HTML (before the usage snapshot and the peer review). It is not a replacement for Step 3's four-zone story — both files are written and passed to the build for a SELF report.

Where the peer review (Step 3) is a diagnostic story about the user's own habits, the ledger is an **audit-style record of what the AI team (Claude Code plus any other AI CLIs the user runs) actually delivered**, written under strict audit-discipline rules — a ledger a reader should be able to trust, not a narrative that talks them into a conclusion.

Write to `/tmp/cc-autopsy/ledger-narration.md`. Structure is exactly four `# ` headings (case-insensitive, but write them lowercase to match the source), each parsed as **first line = the opener claim, everything after = body prose**:

```markdown
# opening

<ONE sentence: what the AI team delivered this period, what it cost, and the
biggest leak if one is known. This is the "thirty-second read" — a reader who
stops here still has the headline.>

# output-ledger

<First line: the opener claim for the output ledger (e.g. "42 commits shipped
across 6 projects at an estimated $38 API-equivalent cost.").
Rest: body prose backing the claim — deliverables, counts, costs, all
evidence-backed per the audit-discipline rules below.>

# team-ledger

<First line: the opener claim for the team ledger (e.g. "Claude Code carried
81% of active days; Codex covered the other 19%, mostly late-night sessions.").
Rest: body prose on how work split across sources in `cross_llm.sources` —
coverage tier caveats apply (see Step 1c): only claim what the tier can prove.>

# leak-ledger

<First line: the opener claim states the single biggest leak with its weekly
number (e.g. "The repeated-instruction tax cost an estimated 420 tokens/week
across 8 sessions retyping the same guardrail prompt.") — read it from
`ledger.leaks.items[0]` (highest `weekly_cost_usd`), not from a guess.
Rest: body prose on the remaining leak-ledger items in `ledger.leaks.items`
and any blind-spot findings in `blind_spots` whose `gate_passed` is true.
The audit-discipline rules above apply here too — numbers before adjectives,
no cheerleading. The praise-word lint (build-time, see Step 4) will warn on
cheerleading vocabulary in this book same as any other.

Empty-catalog path: `ledger.leaks.items` can legitimately be empty on a
valid run. When it is, do NOT invent a leak. Instead:
  - If `blind_spots.ask_vs_ship.gate_passed` or
    `blind_spots.interrupt_win_rate.gate_passed` is true, write the opener
    from whichever of those passed (they are the leak ledger's secondary
    findings, #6 and #7) — same numbers-before-adjectives rule applies.
  - If neither passed either, omit the `# leak-ledger` book entirely.
    The renderer (`_build_leak_ledger` in report_render.py) suppresses the
    section gracefully when there is nothing to show, and falls back to
    the locale-default title if the book is missing. Never fabricate a
    leak or a number to fill the opener.>

# trend-ledger

<Only write this book if ~/.claude/usage-data/autopsy-history.jsonl has
>= 3 snapshot lines (check with `wc -l`) — below that the renderer shows
a locked one-liner regardless of what you write here, so writing it early
is wasted tokens.

First line: the opener claim compares a key ledger number across
snapshots (e.g. "Commits per run rose from 20 to 44 across three runs.") —
read the actual snapshot values from the history file, don't estimate.
Rest: body prose comparing this run to the last run and to the reference
run (~90 days back), covering the same numbers-before-adjectives audit-
discipline rules as every other book above. Only counts, dates, scores,
and dollar totals — never sids, prompt text, or project names.>
```

Pass the file to the build with `--ledger-narration /tmp/cc-autopsy/ledger-narration.md` (SELF builds only — HR never sees the ledger; see the audience table below).

### Audit-discipline writing rules (apply to every sentence in ledger-narration.md)

This is a ledger, not a pep talk. Write it the way an auditor writes a finding, not the way a coach writes feedback:

- **Numbers before adjectives.** Every evaluative adjective ("heavy", "light", "consistent", "sparse") must anchor to a specific number and the threshold that number is being judged against. An adjective with no number behind it is a claim with no evidence — cut it or find the number.
- **No cheerleading, no sandwiching.** Don't wrap a weak finding in praise to soften it, and don't manufacture praise to balance a criticism. State what the data shows.
- **Positive claims need evidence at the same bar as negative claims.** A good number gets exactly the same sourcing discipline as a bad one. If a positive claim can't be sourced to `analysis-data.json` / `cross_llm` / `ledger`, it gets cut — same as an unsourceable negative claim would.
- **Self-referential comparison only.** Compare the user's own numbers across time or across sources (this week vs last, Claude Code vs Codex). Never compare to other users or invoke "better than most" — there is no peer population this pipeline has measured.
- **Lower-bound accounting.** Only count deliverables the evidence actually backs. If a commit, a session, or a claimed output can't be tied to a row in the data, it does not go in the count. When in doubt, undercount.

### How to write ledger-narration.md well

- **Be honest and direct.** No sandwiching. No performance-review platitudes.
- **Every claim cites a number from `analysis-data.json` (including its `cross_llm` / `ledger` blocks) or a session ID from `samples.json`.** Numbers are the spine.
- **The opening line is load-bearing.** It has to survive as a standalone "thirty-second read" — assume some readers stop there.
- **No em-dash overuse in zh_TW.** Use commas, colons, or new sentences. Per `feedback_writing_style`: 中文寫作不濫用破折號。

### HR

HR needs no peer-review file — the recruiter version renders badges + output ledger + case study only. Write only `case-study.hr.{locale}.md` (Step 3.5).

## Step 3.5 — Write try-this-week + case-study markdowns (V4)

V4 adds two more author-written blocks that feed into the same HTML build.

### Try-this-week (SELF only)

Write `/tmp/cc-autopsy/try-this-week.{locale}.md`. 3-5 numbered action items derived directly from the peer-review claims. Each item:

- Starts with a **bold imperative** (e.g. "Block 13–15h for non-Claude work").
- Names the dimension it maps to (e.g. "(maps to D8 time-of-day)").
- Gives a concrete daily-life mechanism (calendar block, CLAUDE.md rule, grep command, single-page checklist).
- Stays runnable inside the next 7 days. No multi-quarter plans.

Skip this entirely for HR (the audience can't act on the user's calendar).

### Case study (BOTH audiences)

Pick the strongest single session from `samples.json` — usually a high-token, high-commit, `fully_achieved` Task-agent session. Write two files:

- `/tmp/cc-autopsy/case-study.self.{locale}.md` — SELF version, raw project name and sid OK.
- `/tmp/cc-autopsy/case-study.hr.{locale}.md` — HR version, redacted project label, NO sid.

Required structure for both:

```markdown
### <metric strip headline>

<Sub-line: session identifier and project label.>

**The problem**: <one paragraph naming the scope and why it was non-trivial>

**How the orchestration ran**: <one paragraph: Task agent dispatch, parallel
TDD, cross-file coordination, friction events that were caught.>

**What shipped**: <one paragraph: concrete artifacts. Reinforce why this
session demonstrates the upper bound of the user's AI-native engineering.>
```

The **metric strip headline** is critical. Format `<duration> · <commits> · <tests> · <deploy/outcome>`. Example:

> ### 451 min · 14 commits · 56 tests passing · Vercel deploy · fully achieved

Don't use HTML `<dl><dt><dd>` tags — `md_to_html` escapes them. Use bold + paragraph instead.

## Step 4.5 — Locale rewrite (only when locale != en)

**Skip this step entirely if the user picked `en` in Step 0.**

**Cache check:** if `/tmp/cc-autopsy/peer-review.zh_TW.md` already exists and is newer than `/tmp/cc-autopsy/peer-review.md`, use it as-is and skip the rewrite. Re-running the skill should not re-spend tokens on rewriting unchanged peer-review prose.

**Rewrite prompt** (run via the Task tool with `model=claude-sonnet-4-5` or newer, never haiku):

> You are a native zh_TW peer reviewer of Claude Code workflow. Rewrite the following English peer-review report into Traditional Chinese.
>
> Rules:
> - This is a REWRITE, not a translation. The voice should be a native zh_TW peer reviewer who happened to read the same data and write their own review. Avoid translation tone, avoid sentence-by-sentence parallelism with the source.
> - Preserve every fact, number, and section heading structure. Do not invent claims, do not omit findings.
> - No AI 公文體 connectors (然而, 值得注意的是, 此外). Let the logic carry the paragraph.
> - No em-dash 濫用 (——). If you reach for one, restructure with a comma or a new sentence.
> - The user has a QA / 品保 background; technical terms can stay in English where natural (e.g. "Task agent", "MCP", "facet coverage").
>
> Source (English):
> ```
> <paste contents of peer-review.md here>
> ```
>
> Output: pure markdown, same heading structure as the source.

Save the output to `/tmp/cc-autopsy/peer-review.zh_TW.md`. In Step 4, pass `--peer-review /tmp/cc-autopsy/peer-review.zh_TW.md` to `build_html.py`.

## Step 4 — Build the HTML

### Default (self audit)

```bash
# Replace .{locale} suffix per Step 0 (zh_TW for Traditional Chinese, en for English).
python3 scripts/build_html.py \
  --input /tmp/cc-autopsy/analysis-data.json \
  --samples /tmp/cc-autopsy/samples.json \
  --peer-review /tmp/cc-autopsy/peer-review.{locale}.md \
  --try-this /tmp/cc-autopsy/try-this-week.{locale}.md \
  --case-study /tmp/cc-autopsy/case-study.self.{locale}.md \
  --ledger-narration /tmp/cc-autopsy/ledger-narration.md \
  --locale {locale} \
  --profile ~/.claude/cc-autopsy-profile.json \
  --output ~/.claude/usage-data/cc-user-autopsy.html
```

`--try-this` and `--case-study` are V4 additions. Both expect markdown files produced in Step 3.5. `--ledger-narration` is a V5 addition (SELF only, Step 3b) — if omitted, the ledger sections simply don't render, the rest of the build is unaffected. On a successful SELF build, `build_html.py` also appends one line to `--history-file` (default `~/.claude/usage-data/autopsy-history.jsonl`) as a trend snapshot; this never fails the build even if the write errors.

**Praise-word lint warnings on stderr are expected output to read and act on, not build errors.** `build_html.py` scans every narrative markdown file (peer-review, ledger-narration, try-this, case-study) against the praise-word list (`scripts/praise_lint.py`) and prints `warning: praise-word lint: <file> contains praise vocabulary (...)` to stderr when it finds cheerleading vocabulary with no number behind it. The build still succeeds — this is a nudge to go back and either cut the adjective or attach the number that justifies it, not a failure to fix and retry.

### For a hiring-manager / portfolio audience

If the user is producing this report to share with AI-company recruiters, add
`--audience hr`. This produces the recruiter version v1 (see "What you get"
above): identity letterhead, hero, earned badges, allowlist-filtered output
ledger (top-3 public shipped items + public artifact links), one case study,
and a scope-disclosure methodology footer. No scores, no peer-review memo,
no pattern mining, no trends.

**Privacy model in HR mode:**

- Project names are redacted by default. Only those listed in
  `--public-projects <file>` appear verbatim. Everything else becomes its
  `category_overrides` label (or is dropped entirely if no override — never
  shown as generic "Private project" filler).
- Session IDs (`sid`) are not shown anywhere. The evidence library and trend
  ledger don't render in HR mode at all; they belong in a self audit, not a
  public artefact.
- Per-session LLM-written summaries are replaced with category-level roll-ups
  in the output ledger. Only allowlisted projects get their verbatim summary.
- Friction detail, first-prompt text, and facet crosstabs tied to specific
  projects are aggregated to category buckets.

```bash
# HR needs no --peer-review or --try-this (no peer-review memo or
# calendar-actionable items in the recruiter version).
# Case study is BOTH audiences and uses the HR-redacted version here.
python3 scripts/build_html.py \
  --input /tmp/cc-autopsy/analysis-data.json \
  --samples /tmp/cc-autopsy/samples.json \
  --case-study /tmp/cc-autopsy/case-study.hr.{locale}.md \
  --audience hr \
  --locale {locale} \
  --public-projects ~/.claude/cc-autopsy-public-projects.json \
  --artifacts ~/.claude/cc-autopsy-artifacts.json \
  --profile ~/.claude/cc-autopsy-profile.json \
  --output ~/.claude/usage-data/cc-user-autopsy-hr.html
```

`--public-projects` file format:
```json
{
  "public_projects": ["my-open-source-lib", "published-skill-xyz"],
  "category_overrides": {
    "internal-platform-repo": "Enterprise B2B platform",
    "client-mobile-app": "Consumer mobile app",
    "research-prototype-a": "ML research prototype"
  }
}
```

`--artifacts` file format (optional):
```json
[
  {"name": "Project name", "url": "https://...", "description": "One line."}
]
```

### Identity header (`--profile`)

If the user provides a profile JSON, the report gets a proper identity header
(a full letterhead in HR mode, a subtle signature in self mode). Without this,
the report is anonymous — fine for self-audit, bad for portfolio use.

If the user mentions wanting to share the report or mentions a job application
but doesn't have a profile file yet, ask them for:
- Name (required)
- Role / one-line description
- Location (optional)
- Tagline (optional — one italic line summarizing how they work)
- Contact (email / github / twitter / website)
- Extra links (blog, portfolio, writing collection)

Then write `~/.claude/cc-autopsy-profile.json`:

```json
{
  "name": "Full Name",
  "role": "Short role description",
  "location": "City · timezone",
  "tagline": "One sentence about how you work with Claude.",
  "contact": {
    "email": "you@example.com",
    "github": "handle",
    "website": "https://..."
  },
  "links": [
    {"label": "writing", "url": "https://..."}
  ]
}
```

Pass it to `build_html.py --profile ~/.claude/cc-autopsy-profile.json`.

### When to suggest `--audience hr`

If the user mentions any of: "portfolio", "job application", "hiring", "HR",
"recruiter", "show to employer", "AI company", "applying to Anthropic/OpenAI/xAI",
offer the HR option in Step 0 and note that it needs privacy setup. Still ask
before building — don't silently produce an HR version. If the user confirms
they want HR, walk through the profile + public-repo allowlist collection
before running any script.

### What it does

- Loads inputs
- Renders HTML with built-in canvas charts (14 charts including growth curve)
- Injects peer-review markdown into `<div id="peer-review">`
- Writes standalone HTML with no remote fonts or CDN scripts

If `--peer-review` is omitted or the file is empty, the HTML still builds — the
peer review section shows "(no peer review written for this run)".

## Step 5 — Report to user

Tell the user:
1. The HTML path: `~/.claude/usage-data/cc-user-autopsy.html`
2. One sentence summarizing the most load-bearing finding (usually from your peer review, e.g., "Your top improvement area is X, see Section 5.2")
3. Open it with `open <path>` on macOS, `xdg-open` on Linux

Do not dump the entire report into the conversation — the user reads it in the browser.

## Diagnostic rules (used in Step 1's auto-scoring)

The `aggregate.py` script assigns each user a 1-10 score across 9 dimensions using the rules below. These are rule-based and will be shown alongside your (LLM-generated) peer review, giving the user both views.

Read `references/scoring-rubric.md` for the exact threshold logic if you need to discuss or override scores.

## Audience-conditional rendering

The same `build_html.py` produces both audiences from one analysis-data.json. Key conditional rules to be aware of when modifying the renderer:

| Aspect | SELF | HR (recruiter v1) |
|---|---|---|
| Opening band / output / team / leak ledgers | rendered | absent |
| Trend ledger | rendered (locked note below 3 snapshots) | absent |
| Badges section | absent (badge data still in analysis-data.json + snapshots) | earned-only cards, criteria + n + window; zero earned → section absent |
| Hero block | Diagnostic letter framing | Practice summary framing |
| Benchmark caveat | rendered (Usage snapshot §01) | rendered (immediately after hero) |
| Identity | subtle signature | full letterhead |
| Peer review | Story format (4 zones + connect-back) | absent |
| Scoring grid | 9 dimensions, overall average, full disclaimer | absent |
| Output ledger (HR) | n/a (SELF has ledger books) | counters + top-3 allowlisted shipped + artifact links; non-public items excluded entirely |
| Try-this-week | §04 | absent |
| Case study | §05, raw project name + sid | § HR-03, redacted label, NO sid |
| Pattern mining / weekly trends / evidence library | rendered | absent |
| Methodology | full footer | scope disclosure: standard version, earned/total badges, rubric location, reproducibility, privacy model |
| sid8 prefixes | shown | never |

Cross-LLM prompt text (e.g. Grok's `prompt_history.jsonl` entries) never renders in any external version of the report — the ledger builders only ever take counts, dates, minutes, and tokens from cross-LLM rows, never raw prompt text, and the whole ledger is gated `audience == "self"` besides.

When adding a new block, ask: does this block convey diagnostic value (SELF) or hiring signal (HR)? If only one, gate it with `if audience == "..."`. If both, ensure HR-side has no sid / private project leak.

## Known limits

- Only analyzes data in `~/.claude/usage-data/` and `~/.claude/projects/` — doesn't see Cloud sessions, external logs, or code quality outside the transcripts
- facet labels come from `/insights` (an LLM pass) and may be miscategorized
- On fresh installs with <20 sessions, the skill should tell the user data is too thin and stop
- **API-equivalent cost is informational, not a bill.** Claude Code Max Plan users pay a flat monthly fee regardless of usage. The cost estimate shows what the same token volume *would* cost on pay-per-use API pricing — useful for understanding scale, not for reconciliation. The number is blended by the user's actual model mix and uses conservative 1h cache-write pricing. Pricing is pinned in `scripts/aggregate.py`'s `PRICING` dict with a dated comment — update when Anthropic's public rates change.
- Claude Code rotates transcript files in `~/.claude/projects/` (typically keeps ~30–60 days). Activity/token/cost metrics cover only the rotation window; 9-dim scores cover the longer session-meta history. Scope disagreement between the two panels is expected and documented in the HTML.

## Files

- `scripts/scan_transcripts.py` — walks `~/.claude/projects/`, merges subagent tokens into parents, writes transcript-rows.jsonl
- `scripts/cross_llm_common.py` — shared helpers for the three cross-LLM adapters below (row shape, idle-gap segment splitting, timestamp parsing)
- `scripts/scan_codex.py` — full-tier adapter: walks `~/.codex/sessions`, writes tokens/models/transcript-shaped rows to codex-rows.jsonl
- `scripts/scan_grok.py` — partial-tier adapter: walks `~/.grok/sessions`, writes prompt-text/timestamp rows (no tokens/models) to grok-rows.jsonl
- `scripts/scan_antigravity.py` — presence-only adapter: walks `~/.gemini/antigravity/conversations`, writes file count + mtime only (no content parsing) to anti-rows.jsonl
- `scripts/aggregate.py` — combines transcript rows + session-meta + facets, writes analysis-data.json (includes cost estimate via `PRICING` table); `--cross-llm-rows` (repeatable) feeds the additive `cross_llm` / `ledger` blocks only + `badges` block (`compute_badges`, bars in scoring-rubric.md)
- `scripts/sample_sessions.py` — picks representative sessions, writes samples.json
- `scripts/build_html.py` — CLI entry point. Wires `--peer-review`, `--try-this`, `--case-study`, `--ledger-narration`, `--audience`, `--locale`, `--profile`, `--public-projects`, `--artifacts`, `--history-file` into the renderer. Also owns `append_history_snapshot()` — the SELF-only, warn-never-fail trend-snapshot append to `--history-file` (default `~/.claude/usage-data/autopsy-history.jsonl`) that runs after a successful build — and `read_history_snapshots()`, which loads those snapshots back for the trend ledger.
- `scripts/report_render.py` — all HTML rendering logic. Owns the audience-conditional branches (SELF vs HR), claim-indexed evidence selectors, section ordering, and the SELF-only ledger builders (`_parse_ledger_narration`, `_build_opening_band`, `_build_output_ledger`, `_build_team_ledger`, `_build_leak_ledger`, `_build_trend_ledger`, `_build_badges_section`, `_build_hr_output_ledger`).
- `scripts/locales.py` — single source of truth for every UI chrome string. Both locales must share the same key set (enforced by tests). Two locales: `en` (canonical), `zh_TW`.
- `scripts/narrative_en.py` / `scripts/narrative_zh.py` — locale-specific narrative helpers (outcome labels, evidence badges, methodology sub-blocks).
- `tests/test_scan_transcripts.py` — scanner unit tests
- `tests/test_cost_estimate.py` — cost calc + pricing table tests
- `tests/test_build_html_additions.py` — cost tile + models chart render tests
- `tests/test_locales.py` — locales key-set parity tests
- `tests/smoke_test.py` — end-to-end offline/sanitization smoke test
- `references/scoring-rubric.md` — the 9 rule-based scoring rules

## Cross-machine merge (optional)

If the user works on two machines and wants one report covering both, `aggregate.py` accepts `--extra-redacted <file>` (repeatable). Each file is a `sessions-redacted.jsonl` produced on another machine — per-session numbers with all free text stripped. Sessions are merged into the pool; local wins on `session_id` collisions; scores/aggregates recompute over the combined pool.

Paired tooling for this lives in `claude-memory-sync`:
- `_scripts/dump-redacted-sessions.py` — produce the jsonl from `~/.claude/usage-data/`
- `_scripts/merge-cross-machine-autopsy.sh` — one-shot: dump + push + pull + aggregate + build

Evidence library (the 24 session cards in Section 6) only samples local transcripts; cross-machine sessions contribute to aggregate numbers only. If the user asks for this workflow, point them at `claude-memory-sync`'s README section "cc-user-autopsy 跨機合併".
