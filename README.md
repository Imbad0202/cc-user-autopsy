# cc-user-autopsy

An honest, evidence-traceable peer-review for Claude Code users — a skill that
analyzes your own `~/.claude/projects/` transcripts and `~/.claude/usage-data/`
session metadata, then generates a standalone HTML report combining rule-based
scoring with an LLM-written personalized review.

Built because the built-in `/insights` is useful but leans celebratory; this
skill leans diagnostic.

## Preview

Two sample outputs, both generated from synthetic data (no real user's information):

- **[`assets/example-output.html`](assets/example-output.html)** — default self-audit layout (diagnostic letter)
- **[`assets/example-output-hr.html`](assets/example-output-hr.html)** — hiring-manager / portfolio layout (`--audience hr`)

To regenerate them locally, see [Running manually](#running-manually).

## Three output modes

The same pipeline can produce three variants depending on who the report is for:

| Mode | Flag | Audience | Shows project names | Shows session IDs | Shows profile card |
|---|---|---|---|---|---|
| **Self audit** | *(default)* | You | Verbatim | Verbatim | No |
| **HR / portfolio** | `--audience hr` + `--profile` + `--public-projects` | Recruiters | Allowlisted verbatim; rest bucketed | Hidden | Full letterhead |
| **Showcase** | `--audience hr` + empty `public_projects: []` | Public readers (blog, demo) | All bucketed into category labels | Hidden | Minimal signature |

The skill's Step 0 asks which version(s) to build and walks you through the
setup files before running anything. It never silently produces the HR or
showcase variant.

## What it produces

A standalone HTML file (no remote fonts, no CDN scripts) with:

- **Overview** — session count, tokens, active days, API-equivalent cost, Task agent / MCP adoption, favorite model, cache hit ratio
- **9-dimension rule-based scores** (1–10) with explicit metric evidence:
  1. **D1 Delegation** — Task agent adoption and good-outcome rate
  2. **D2 Root-cause debugging** — iterative_refinement × buggy_code co-occurrence
  3. **D3 Prompt quality** — prompt-length bucket vs tokens-per-commit efficiency
  4. **D4 Context management** — long-session commit rate, output-token-limit hits, compact usage
  5. **D5 Interrupt judgment** — post-interrupt recovery to good outcome
  6. **D6 Tool breadth** — distinct tools per session, MCP adoption
  7. **D7 Writing consistency** — misunderstood_request rate on writing sessions
  8. **D8 Time-of-day management** — best-hour vs worst-hour friction ratio
  9. **D9 Token efficiency** — tokens per good outcome, cache hit ratio, per-turn burn
- **Personalized peer review** — 3 strengths + 3 specific improvements + 1 neutral observation, written by Claude after reading your aggregated data
- **14 charts** — prompt-length × outcome, friction distribution, tool usage, weekly trends (sessions / tokens / commits / friction / prompt-len / good-rate), weekday×hour heatmap, project breakdown, growth curve, model mix, subagent effect
- **Evidence library** — up to 24 representative sessions across 7 buckets (top-tokens / most-interrupts / high-friction / not-achieved / partial / control / user-rejected), each expandable with traceable session IDs (self audit only)
- **Methodology section** — data sources, scope notes, honest caveats
- **Locale support** — English (default) or Traditional Chinese (`--locale zh_TW`) with natively-rewritten peer review, not translation

## Installation

Clone this repo into your Claude Code skills directory:

```bash
git clone https://github.com/Imbad0202/cc-user-autopsy.git \
  ~/.claude/skills/cc-user-autopsy
```

Requires Python 3.9+ and only the Python standard library.

## Usage

In Claude Code, just ask:

> "Autopsy my Claude Code usage"
>
> or
>
> "Give me a deep review of how I use Claude Code"
>
> or
>
> "Peer review my cc workflow"

Claude invokes the skill. The skill asks which mode (self / HR / both) and
which locale (en / zh_TW), then walks through the 5 phases. The final HTML
opens in your browser at `~/.claude/usage-data/cc-user-autopsy.html`.

### Portfolio mode (for AI job applications)

If you're producing the report to share with AI-company recruiters, ask:

> "Autopsy my Claude Code usage for a portfolio — I'm applying to AI jobs"

The skill walks you through three small setup files in `~/.claude/`:

**Identity profile** so the report isn't anonymous:

```json
// ~/.claude/cc-autopsy-profile.json
{
  "name": "Your Name",
  "role": "Your role / one-line pitch",
  "location": "City · timezone",
  "tagline": "One italic sentence summarizing how you work.",
  "contact": {
    "email": "you@example.com",
    "github": "handle",
    "website": "https://..."
  },
  "links": [{"label": "writing", "url": "https://..."}]
}
```

**Public-repo allowlist** so private project names don't leak:

```json
// ~/.claude/cc-autopsy-public-projects.json
{
  "public_projects": ["my-open-source-lib", "published-skill-xyz"],
  "category_overrides": {
    "internal-platform-repo": "Enterprise B2B platform",
    "client-mobile-app": "Consumer mobile app"
  }
}
```

**Public artifacts** — live URLs you want surfaced (optional):

```json
// ~/.claude/cc-autopsy-artifacts.json
[
  {"name": "My AI writing tool", "url": "https://github.com/me/tool", "description": "MIT-licensed skill I published"},
  {"name": "Personal blog", "url": "https://...", "description": "Technical writing about AI-native workflows"}
]
```

### Showcase mode (for blog posts / public demos)

If you want to share a report publicly (Substack, demo video, conference talk)
without exposing project specifics, use the same HR flags but pass an empty
`public_projects: []` allowlist. Every project shows as a category label
("Higher-ed QA platform", "Consumer iOS app", "Open-source Claude Code skill"),
every session summary renders as "Details withheld — private project", and
only the profile fields you explicitly include appear.

A PII sweep on the showcase HTML confirms: 0 session UUIDs, 0 project path
fragments, 0 file paths, 0 embedded JSON data islands — the only identity
anchors are the profile fields you chose to include.

### Privacy model

Default behaviour is redact-first: if a project isn't in your public
allowlist, it's not shown by name.

| Field | Self audit | HR without allowlist | HR with allowlist | Showcase (empty allowlist) |
|---|---|---|---|---|
| Project names in charts | Verbatim | All anonymised | Allowlisted verbatim; rest bucketed | All bucketed |
| "Shipped with Claude" project name | Verbatim | Anonymised | Allowlisted verbatim; rest bucketed | All bucketed |
| "Shipped with Claude" LLM summary | Verbatim | "Details withheld" | Shown for allowlisted only | "Details withheld" for all |
| Evidence library (24 cards) | Shown | **Hidden entirely** | **Hidden entirely** | **Hidden entirely** |
| Session IDs | Shown | Hidden | Hidden | Hidden |
| Peer review text | As written | As written — see note | As written | As written |

The peer-review markdown is the one place the skill can't redact
automatically. The skill instructs Claude to produce a separate
`peer-review-hr.md` for HR builds that strips session-ID citations and
non-allowlisted project names. Open the HTML and read the peer-review section
before sharing.

## How it differs from `/insights`

| | `/insights` | `cc-user-autopsy` |
|---|---|---|
| Honest peer review | Leans celebratory | Directive, no sandwiching |
| Scoring | No explicit scores | 9 rule-based scores with thresholds |
| Evidence traceability | Occasional | Every claim cites session ID or metric |
| Regenerate without LLM | Yes | Yes (rule-based part) |
| Personalized | Partially | Yes (Claude writes review after reading your data) |
| Cost estimate | No | API-equivalent USD via model-mix-blended pricing |
| Subagent accounting | Orphan rows | Merged into parent sessions |
| Cross-machine merge | No | `--extra-redacted` accepts dumps from other machines |
| HTML output | Shareable report | Self-contained, offline-safe diagnostic dashboard |

The skill reuses `~/.claude/usage-data/facets/` (produced by `/insights`) if
present. Without facets, outcome/friction rates can't be computed but
quantitative dimensions (token / tool / time / cost) still work.

## Data sources

Read-only; the skill never modifies your data.

- `~/.claude/projects/**/*.jsonl` — **primary source** for activity, tokens, cost, models, cache hit ratio. Includes `agent-*.jsonl` subagent runs, which `scan_transcripts.py` merges into their parent session (matched on the subagent's `sessionId` field)
- `~/.claude/usage-data/session-meta/*.json` — session-level metadata (durations, commit counts, first prompt, helpfulness). Used for 9-dim scoring
- `~/.claude/usage-data/facets/*.json` — optional outcome / friction / goal labels from `/insights`

### Two token universes

Activity metrics (tokens, cache, models, cost, active days) come from the
**full transcript pool**, which Claude Code rotates — typically the last
~30–60 days.

9-dim scores come from the **session-meta pool**, which has LLM-derived
labels but partial coverage of history.

If both numbers disagree (e.g., activity shows 150 sessions, scoring shows
420), that's expected. The HTML `scope_note` explains this to the reader.

## Cross-machine merge

If you work on two machines and want one report covering both, `aggregate.py`
accepts `--extra-redacted <file>` (repeatable). Each file is a
`sessions-redacted.jsonl` produced on another machine — per-session numbers
with all free text stripped. Local sessions win on `session_id` collisions;
scores recompute over the combined pool.

Paired tooling lives in
[`claude-memory-sync`](https://github.com/Imbad0202/claude-memory-sync):

- `_scripts/dump-redacted-sessions.py` — produce the jsonl from `~/.claude/usage-data/`
- `_scripts/merge-cross-machine-autopsy.sh` — one-shot: dump + push + pull + aggregate + build

The evidence library only samples local transcripts; cross-machine sessions
contribute to aggregate numbers only.

## File layout

```
cc-user-autopsy/
├── SKILL.md                          # skill entry point (5-step workflow)
├── README.md                         # this file
├── LICENSE                           # MIT
├── scripts/
│   ├── scan_transcripts.py           # step 1a: walk ~/.claude/projects/, merge subagent runs
│   ├── aggregate.py                  # step 1b: combine transcripts + session-meta + facets, rule-based scoring, cost estimate
│   ├── sample_sessions.py            # step 2: pick up to 24 representative sessions across 7 buckets
│   ├── build_html.py                 # step 4: orchestrate HTML render (CLI thin layer)
│   ├── report_render.py              # HTML rendering engine (canvas charts, semantic layout)
│   ├── narrative_en.py               # English narrative for auto-generated prose
│   ├── narrative_zh.py               # Traditional Chinese narrative (native, not translated)
│   ├── locales.py                    # i18n strings for UI chrome
│   └── generate_demo_data.py         # produce synthetic data for demos / tests
├── references/
│   └── scoring-rubric.md             # exact thresholds for each of the 9 dimensions
├── tests/                            # 244 tests across 14 files — see Testing below
├── assets/
│   ├── example-output.html           # demo self-audit HTML
│   └── example-output-hr.html        # demo HR HTML
└── evals/
    └── evals.json                    # test prompts for skill-creator iteration
```

## Running manually

Without the skill (useful for debugging or CI):

```bash
# Step 1a — walk transcripts, merge subagent runs into parent sessions
python3 scripts/scan_transcripts.py --output /tmp/cc-autopsy/transcript-rows.jsonl

# Step 1b — aggregate + rule-based scoring + cost estimate
python3 scripts/aggregate.py \
  --transcript-rows /tmp/cc-autopsy/transcript-rows.jsonl \
  --output /tmp/cc-autopsy/analysis-data.json

# Step 2 — sample representative sessions
python3 scripts/sample_sessions.py \
  --input /tmp/cc-autopsy/analysis-data.json \
  --output /tmp/cc-autopsy/samples.json

# Step 3 — write your own peer review as markdown (or skip)

# Step 4 — render HTML
python3 scripts/build_html.py \
  --input /tmp/cc-autopsy/analysis-data.json \
  --samples /tmp/cc-autopsy/samples.json \
  --peer-review /tmp/cc-autopsy/peer-review.md \
  --output ~/.claude/usage-data/cc-user-autopsy.html

open ~/.claude/usage-data/cc-user-autopsy.html
```

To regenerate the demo HTMLs committed to `assets/`:

```bash
python3 scripts/generate_demo_data.py          # writes synthetic data to /tmp/cc-autopsy-demo/
# then run the 4 steps above against /tmp/cc-autopsy-demo/ paths
```

## Testing

244 tests across 14 test files:

```bash
python3 -m pytest tests/ -q
```

Covers:

- `test_scan_transcripts.py` — transcript walking, subagent merge, orphan handling
- `test_cost_estimate.py` — API-equivalent cost calculation, `PRICING` table integrity
- `test_d9_token_efficiency.py` — token efficiency scoring dimension
- `test_unknown_project_bias.py` — `(unknown)`-project exclusion from commit-based metrics (18 cases)
- `test_usage_characteristics.py` — 5 pattern-tip generation rules
- `test_locales.py`, `test_narrative_en.py`, `test_narrative_zh.py`, `test_narrative_parity.py` — i18n
- `test_build_html_additions.py`, `test_build_html_prettify.py`, `test_css_tokens.py` — render regression
- `test_demo_data.py` — synthetic fixture integrity
- `smoke_test.py` — end-to-end offline-safe + XSS-escape check on generated HTML

## Limitations

- Assumes macOS/Linux paths (`~/.claude/...`). Windows paths not tested.
- Peer review quality depends on Claude having enough data to avoid generic advice. Fewer than ~20 rated sessions → review marked preliminary and dimensions dial down.
- Scoring thresholds are rules of thumb, not scientific — they exist to surface signal, not to pass judgment. Override them if your context legitimately deviates (see `references/scoring-rubric.md`).
- Facet labels come from an LLM pass and can be miscategorized, especially the `buggy_code` vs `wrong_approach` boundary.
- **API-equivalent cost is informational, not a bill.** Claude Code Max Plan users pay a flat fee regardless of usage. The cost estimate shows what the same token volume *would* cost on pay-per-use API pricing — useful for understanding scale, not reconciliation. Pricing is pinned in `aggregate.py`'s `PRICING` dict with a dated comment.
- Claude Code rotates transcript files (typically keeps ~30–60 days). Activity / token / cost metrics cover only the rotation window; 9-dim scores cover the longer session-meta history.

## License

MIT. See `LICENSE`.
