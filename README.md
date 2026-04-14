# cc-user-autopsy

An honest, evidence-traceable peer-review for Claude Code users — a skill that
analyzes your own `~/.claude/usage-data/` and `~/.claude/projects/` data and
generates an HTML report combining rule-based scoring with an LLM-written
personalized review.

Built because the built-in `/insights` is useful but leans celebratory; this
skill leans diagnostic.

## Preview

Two sample outputs, both generated from synthetic data (no real user's information):

- **[`assets/example-output.html`](assets/example-output.html)** — default self-audit layout (diagnostic letter)
- **[`assets/example-output-hr.html`](assets/example-output-hr.html)** — hiring-manager / portfolio layout (`--audience hr`)

The HR layout adds:
- At-a-glance profile card (scale · velocity · parallel work · tool breadth · self-audit · focus)
- "Shipped with Claude" section auto-extracted from fully-achieved essential sessions
- Public artifacts list (user-supplied via `--artifacts`)
- 30-second primer defining session / subagent / MCP / facet terms
- Re-ordered table of contents to lead with shipped outcomes

To regenerate it locally:

```bash
python3 scripts/generate_demo_data.py          # writes to /tmp/cc-autopsy-demo/
python3 scripts/aggregate.py --data-dir /tmp/cc-autopsy-demo/usage-data \
  --output /tmp/cc-autopsy-demo/analysis-data.json
python3 scripts/sample_sessions.py --input /tmp/cc-autopsy-demo/analysis-data.json \
  --output /tmp/cc-autopsy-demo/samples.json \
  --projects-dir /tmp/cc-autopsy-demo/projects
python3 scripts/build_html.py \
  --input /tmp/cc-autopsy-demo/analysis-data.json \
  --samples /tmp/cc-autopsy-demo/samples.json \
  --peer-review /tmp/cc-autopsy-demo/peer-review.md \
  --output assets/example-output.html
```

## What it produces

A standalone HTML file at `~/.claude/usage-data/cc-user-autopsy.html` with:

- **Overview** — session count, tokens, commits, duration, Task agent / MCP adoption
- **8-dimension rule-based scores** (1-10) with explicit metric evidence:
  1. Delegation (Task agent usage)
  2. Root-cause debugging
  3. Prompt quality
  4. Context management
  5. Interrupt judgment
  6. Tool breadth
  7. Writing consistency
  8. Time-of-day management
- **Personalized peer review** — 3 strengths + 3 specific improvements + 1
  neutral observation, written by Claude after reading your aggregate data
- **13 charts** (Chart.js CDN) — prompt-length × outcome, friction distribution,
  tool usage, weekly trends, weekday×hour heatmap, project breakdown
- **Evidence library** — up to 24 representative sessions, each expandable with
  traceable session IDs

## Installation

Clone this repo into your Claude Code skills directory:

```bash
git clone https://github.com/<your-username>/cc-user-autopsy.git \
  ~/.claude/skills/cc-user-autopsy
```

Or use the packaged `.skill` file:

```bash
# Inside Claude Code
/skill install cc-user-autopsy.skill
```

Requires Python 3.10+ (uses `Path | None` type hints). No Python dependencies
beyond the standard library.

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

Claude invokes the skill and walks through the 4 phases. The final HTML opens
in your browser.

### Portfolio mode (for AI job applications)

If you're producing the report to share with AI-company recruiters, ask:

> "Autopsy my Claude Code usage for a portfolio — I'm applying to AI jobs"

The skill will build both the self-audit and the HR variant. You can supply a
JSON file of links you want to surface:

```json
// ~/.claude/cc-autopsy-artifacts.json
[
  {"name": "My AI writing tool", "url": "https://github.com/me/tool", "description": "MIT-licensed skill I published"},
  {"name": "Personal blog", "url": "https://...", "description": "Technical writing about AI-native workflows"}
]
```

And an identity profile so the report isn't anonymous:

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

## How it differs from `/insights`

| | `/insights` | `cc-user-autopsy` |
|---|---|---|
| Honest peer review | Leans celebratory | Directive, no sandwiching |
| Scoring | No explicit scores | 8 rule-based scores with thresholds |
| Evidence traceability | Occasional | Every claim cites session ID or metric |
| Regenerate without LLM | Yes | Yes (rule-based part) |
| Personalized | Partially | Yes (Claude writes review after reading your data) |
| HTML output | Shareable report | Self-contained diagnostic dashboard |

The skill reuses `~/.claude/usage-data/facets/` (produced by `/insights`) if
present. Without facets, outcome/friction rates can't be computed but
quantitative dimensions (token / tool / time) still work.

## Data sources

Read-only; the skill never modifies your data.

- `~/.claude/usage-data/session-meta/*.json` — required
- `~/.claude/usage-data/facets/*.json` — optional (run `/insights` once to
  populate)
- `~/.claude/projects/**/*.jsonl` — sampled for evidence library only

## File layout

```
cc-user-autopsy/
├── SKILL.md                          # skill entry point
├── README.md                         # this file
├── LICENSE                           # MIT
├── scripts/
│   ├── aggregate.py                  # step 1: load data + rule-based scoring
│   ├── sample_sessions.py            # step 2: pick 24 representative sessions
│   └── build_html.py                 # step 4: render HTML dashboard
├── references/
│   └── scoring-rubric.md             # exact thresholds for each dimension
├── assets/                           # (reserved)
└── evals/
    └── evals.json                    # test prompts for skill-creator iteration
```

## Running manually (without the skill)

```bash
python3 scripts/aggregate.py --output /tmp/analysis-data.json
python3 scripts/sample_sessions.py --input /tmp/analysis-data.json --output /tmp/samples.json
# write your own peer review markdown, or skip this step
python3 scripts/build_html.py \
  --input /tmp/analysis-data.json \
  --samples /tmp/samples.json \
  --peer-review /tmp/peer-review.md \
  --output ~/.claude/usage-data/cc-user-autopsy.html
open ~/.claude/usage-data/cc-user-autopsy.html
```

## Limitations

- Assumes macOS/Linux paths (`~/.claude/...`). Windows paths not tested.
- Peer review quality depends on Claude having enough data to avoid generic
  advice. If you have fewer than ~20 rated sessions, the review is marked as
  preliminary and the dimensions dial down.
- Scoring thresholds are rules of thumb, not scientific — they exist to surface
  signal, not to pass judgment. Override them if your context legitimately
  deviates (see `references/scoring-rubric.md`).
- Facet labels come from an LLM pass and can be miscategorized, especially the
  `buggy_code` vs `wrong_approach` boundary.

## License

MIT. See `LICENSE`.
