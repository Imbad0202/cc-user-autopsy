---
name: cc-user-autopsy
description: Produces a deep, honest peer-review of how someone uses Claude Code by statistically analyzing their local session data (~/.claude/usage-data/ and ~/.claude/projects/). Trigger whenever the user asks to review, analyze, audit, or critique their own Claude Code usage, workflow, habits, or skill level — including phrases like "analyze my cc usage", "review my cc sessions", "peer review my cc workflow", "deeper than /insights", or any ask for an honest audit of their AI workflow. Also covers portfolio/hiring-manager framings (e.g. "portfolio for Anthropic/OpenAI/xAI"), but ALWAYS ask the user in Step 0 which version to build (self / hr / both) before running — never silently produce an HR report, because that version goes to outsiders and needs explicit privacy setup. The HTML report is laid out story-first: a story-style peer review (when / how / where stuck / cost) leads, then 9-dim scoring (or 4-signal scoring for HR), then a "this week try this" action block, a strongest-single-session case study, and claim-indexed evidence. HR variant additionally suppresses the evidence library, collapses scoring into 4 hiring signals, and trims pattern charts.
---

# Claude Code User Autopsy

Produces an honest, evidence-traceable peer-review of a user's Claude Code workflow.

## When NOT to use

The frontmatter above describes when to trigger this skill. One case to skip:

**If the user only wants one narrow statistic** that a single grep / ls / wc can answer (e.g. "how many sessions did I run this week") — just answer directly. This skill is for holistic peer review, not ad-hoc lookups.

## What this skill produces

A self-contained HTML report at `~/.claude/usage-data/cc-user-autopsy.html` (or `-hr.html` for portfolio audience). The V4 layout is story-first, not dashboard-first:

**SELF audit layout** (private diagnostic letter):

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

**HR / portfolio layout** differs:

- Profile card + activity panel → Public Artifacts → Peer review (250-350-word candidate memo) §02 → Hiring signals (4 dims, not 9) §03 → Case study §04 → Growth curve + outcome donut §05 → Methodology disclosure.
- Evidence library is **hidden entirely**, no #evidence anchor.
- Scoring chrome reads "Hiring signals" (not "Rule-based scores"), shows only D1 delegation, D2 root-cause, D6 tool breadth, D9 token efficiency. No overall average.
- A short self-awareness caveat under the grid acknowledges that more dimensions exist privately. **Does not name the hidden ones.**
- Pattern mining is dropped entirely. Only growth curve + outcome donut survive.
- Shipped-with-Claude shows at most 3 items, all from the public-projects allowlist. Redacted private projects are dropped, not displayed as "Private platform project" filler.

Both audiences get a **benchmark caveat** disclaimer at the top reminding readers this is unbenchmarked individual data.

## Workflow overview

```
Step 0   → ASK which version (self / hr / both) and which locale (en / zh_TW).
           For HR, collect profile + public-projects allowlist + artifacts BEFORE running.
Step 1a  → scripts/scan_transcripts.py     (merges subagent tokens into parent sessions)
Step 1b  → scripts/aggregate.py            (combines transcript-rows + session-meta + facets)
Step 2   → scripts/sample_sessions.py      (picks 15-24 representative sessions)
Step 3   → Claude writes peer-review.{audience}.{locale}.md  (V4 story format)
Step 3.5 → Claude writes try-this-week.{locale}.md (SELF only)
           Claude writes case-study.{self|hr}.{locale}.md (BOTH audiences, two files)
Step 4.5 → (zh_TW only) rewrite the EN peer review natively into zh_TW
Step 4   → scripts/build_html.py with --peer-review --try-this --case-study --audience --locale
Step 5   → open the HTML in browser and tell the user
```

Each script is idempotent. If a step fails, re-run it.

## Step 0 — Ask first, build second

Before running anything, **ask the user two questions in a single prompt**. Never guess from keywords.

> "I can build two versions of this report:
>   **A. Self audit** — honest diagnostic letter for your eyes only. Shows every project name, session ID, and friction detail.
>   **B. HR / portfolio** — public-facing summary for recruiters. Hides private projects, redacts session IDs, and leads with a profile card.
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

### HR audience format (different file, different format)

Write a **separate** peer review to `/tmp/cc-autopsy/peer-review-hr.{locale}.md` in **candidate memo** format, not story format:

```markdown
### Signal

<2-3 sentences. The single load-bearing claim about who this user is as
an AI-native engineer. Cite top-line metrics.>

### Evidence

<One paragraph naming the strongest single session in third-person without
sid (e.g. "451-minute multi-task session that shipped 14 commits, 56 tests,
Vercel deploy"). Then list public-facing artifacts that back the claim.>

### Caveat

<Overall score. The self-awareness note: a private audit covers more
dimensions; this excerpt shows the four most hiring-relevant ones. DO NOT
name the hidden weak dimensions — that draws the reader's eye to weaknesses.>

### Why interview this person

- **<Role 1>**: <one-line pitch + concrete evidence>
- **<Role 2>**: <one-line pitch + concrete evidence>
- **<Role 3>**: <one-line pitch + concrete evidence>
```

Length target: 250-350 words English (~1000-1500 zh_TW characters at same density).

**HR memo MUST**:

- Not cite raw `sid` values or 8-char session IDs.
- Not name non-allowlisted projects. Use category labels from `--public-projects` (e.g. "higher-ed QA platform") or speak in aggregates.
- Not name the hidden lower-scored dimensions. The self-awareness caveat says "additional dimensions exist privately"; that's all.
- Keep quantitative claims that don't tie to private project names.

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
  --locale {locale} \
  --profile ~/.claude/cc-autopsy-profile.json \
  --output ~/.claude/usage-data/cc-user-autopsy.html
```

`--try-this` and `--case-study` are V4 additions. Both expect markdown files produced in Step 3.5.

### For a hiring-manager / portfolio audience

If the user is producing this report to share with AI-company recruiters, add
`--audience hr`. This re-orders sections to lead with a profile card (at-a-glance
scale / velocity / parallel-work / tool breadth / self-audit score / focus area),
then a "Shipped with Claude" section grouped by broad category (not raw repo name
unless the user allowlisted it), then optionally a list of public artifacts
they want to link.

**Privacy model in HR mode:**

- Project names are redacted by default. Only those listed in
  `--public-projects <file>` appear verbatim. Everything else becomes its
  `category_overrides` label (or `"Private project"` if no override).
- Session IDs (`sid`) are not shown. The evidence library is hidden in HR mode;
  it belongs in a self audit, not a public artefact.
- Per-session LLM-written summaries are replaced with category-level roll-ups in
  the shipped section. Only allowlisted projects get their verbatim summary.
- Friction detail, first-prompt text, and facet crosstabs tied to specific
  projects are aggregated to category buckets.

```bash
# HR omits --try-this (hiring managers can't act on the candidate's calendar).
# Case study is BOTH audiences and uses the HR-redacted version here.
python3 scripts/build_html.py \
  --input /tmp/cc-autopsy/analysis-data.json \
  --samples /tmp/cc-autopsy/samples.json \
  --peer-review /tmp/cc-autopsy/peer-review-hr.{locale}.md \
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

## V4 audience-conditional rendering

The same `build_html.py` produces both audiences from one analysis-data.json. Key conditional rules to be aware of when modifying the renderer:

| Aspect | SELF | HR |
|---|---|---|
| Hero block | Diagnostic letter framing | Practice summary framing |
| Overview / activity | Merged "usage snapshot" + 4-tile behavior strip | Profile card + activity panel + benchmark caveat |
| Reading guide vs zone-map | Short reading-guide paragraph | Full visual 4-zone map (first-time reader) |
| Peer review | Story format (4 zones + connect-back), 700–1000 words | Candidate memo (Signal/Evidence/Caveat/Why), 250-350 words |
| Scoring grid | 9 dimensions, overall average, full disclaimer | 4 hiring signals (D1+D2+D6+D9), no average, "Hiring signals" chrome |
| Self-awareness caveat | (none) | One line: "Private audit covers additional dimensions; this excerpt shows 4 most hiring-relevant signals" — DO NOT name the hidden ones |
| Try-this-week | §04 — 3-5 action items | (hidden — recruiter can't act on it) |
| Case study | §05 — metric strip + 3 paragraphs, raw project name + sid | §04 — same format, redacted project label, NO sid |
| Pattern mining | §06 — full 5-chart suite (plen / friction / tools / heatmap / helpfulness) | (hidden) |
| Weekly trends | §07 — growth curve + 5 weekly detail charts | §05 — growth curve only + outcome donut |
| Evidence library | §08 — claim-indexed (4 peer-review claims, 2-3 sessions per claim, empty groups hidden) | (hidden entirely, no #evidence anchor) |
| Shipped with Claude | (not rendered in SELF) | Top 3 only, public-allowlist filtered, redacted items dropped (not displayed as "Private project" filler) |
| Methodology | Full content but styled as footer (small font) | Compact disclosure note only |
| sid8 prefixes | Shown everywhere | Stripped from all chrome AND from peer-review prose |

When adding a new block, ask: does this block convey diagnostic value (SELF) or hiring signal (HR)? If only one, gate it with `if audience == "..."`. If both, ensure HR-side has no sid / private project leak.

## Known limits

- Only analyzes data in `~/.claude/usage-data/` and `~/.claude/projects/` — doesn't see Cloud sessions, external logs, or code quality outside the transcripts
- facet labels come from `/insights` (an LLM pass) and may be miscategorized
- On fresh installs with <20 sessions, the skill should tell the user data is too thin and stop
- **API-equivalent cost is informational, not a bill.** Claude Code Max Plan users pay a flat monthly fee regardless of usage. The cost estimate shows what the same token volume *would* cost on pay-per-use API pricing — useful for understanding scale, not for reconciliation. The number is blended by the user's actual model mix and uses conservative 1h cache-write pricing. Pricing is pinned in `scripts/aggregate.py`'s `PRICING` dict with a dated comment — update when Anthropic's public rates change.
- Claude Code rotates transcript files in `~/.claude/projects/` (typically keeps ~30–60 days). Activity/token/cost metrics cover only the rotation window; 9-dim scores cover the longer session-meta history. Scope disagreement between the two panels is expected and documented in the HTML.

## Files

- `scripts/scan_transcripts.py` — walks `~/.claude/projects/`, merges subagent tokens into parents, writes transcript-rows.jsonl
- `scripts/aggregate.py` — combines transcript rows + session-meta + facets, writes analysis-data.json (includes cost estimate via `PRICING` table)
- `scripts/sample_sessions.py` — picks representative sessions, writes samples.json
- `scripts/build_html.py` — CLI entry point. Wires `--peer-review`, `--try-this`, `--case-study`, `--audience`, `--locale`, `--profile`, `--public-projects`, `--artifacts` into the renderer.
- `scripts/report_render.py` — all HTML rendering logic. Owns the audience-conditional branches (SELF vs HR), claim-indexed evidence selectors, and section ordering.
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
