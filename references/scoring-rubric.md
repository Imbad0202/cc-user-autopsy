# Auto-Scoring Rubric (8 Dimensions)

Each dimension scored 1-10. Rules are applied in `aggregate.py`. Scores may
differ from LLM-written peer review because rules are coarse — treat both views
as complementary.

## D1 — Delegation (Task agent usage)

Rationale: using `Task` subagents is the main mechanism for parallelizing work
and protecting the main context. Usage rate and outcome quality both matter.

| Score | Threshold |
|-------|-----------|
| 10 | task-agent rate ≥ 70% AND good-rate with TA ≥ 75% |
| 9 | task-agent rate ≥ 60% AND good-rate ≥ 70% |
| 8 | task-agent rate ≥ 45% AND good-rate ≥ 65% |
| 7 | task-agent rate ≥ 30% |
| 6 | task-agent rate ≥ 15% |
| 5 | task-agent rate ≥ 5% |
| 3 | task-agent rate > 0% but < 5% |
| 1 | no task-agent usage at all |

## D2 — Root-cause debugging

Rationale: iterative bug-fix sessions ("v11 → v12 → v13") signal symptom-level
patching. Measured via iterative_refinement sessions with buggy_code friction.

Let `R = (iterative_refinement sessions with buggy_code friction) / (all sessions with facets)`.

| Score | Threshold |
|-------|-----------|
| 10 | R ≤ 2% |
| 9 | R ≤ 4% |
| 8 | R ≤ 7% |
| 7 | R ≤ 10% |
| 6 | R ≤ 15% |
| 5 | R ≤ 20% |
| 4 | R ≤ 25% |
| 3 | R > 25% |

If facets coverage < 30%, return "insufficient data" instead of a score.

## D3 — Prompt quality

Rationale: the median tokens-per-commit for 150-400 char prompts vs <50 char
prompts tells us whether long prompts pay off AND whether the user uses them.

| Score | Threshold |
|-------|-----------|
| 10 | ≥ 60% of sessions have prompts ≥ 100 chars AND 150-400 bucket is the most efficient |
| 8 | ≥ 40% of sessions have prompts ≥ 100 chars |
| 7 | ≥ 25% of sessions have prompts ≥ 100 chars |
| 5 | < 25% of sessions use prompts ≥ 100 chars (heavy reliance on short prompts) |
| 3 | > 50% of sessions use prompts < 20 chars |

## D4 — Context management

Rationale: sessions > 60 min with higher friction, output-token-limit hits, and
"effort-no-commit" sessions indicate poor context hygiene.

Composite: penalize each of the following.

Start at 10, subtract:
- 1 if output-token-limit sessions > 2
- 1 if output-token-limit sessions > 5
- 1 if long-session (>60min) interrupt rate > 25%
- 1 if > 15% of sessions > 20 min had 0 commits (effort-no-commit)
- 1 if > 30% of sessions > 20 min had 0 commits
- 1 if any single project has > 5 output-token-limit sessions

Floor at 3.

## D5 — Interrupt judgment

Rationale: interrupts that correlate with recovered outcomes indicate good
intervention timing, not noise.

Let `P = fraction of interrupted sessions that reach good outcome (full+mostly)`.

| Score | Threshold |
|-------|-----------|
| 10 | P ≥ 60% |
| 9 | P ≥ 50% |
| 8 | P ≥ 40% |
| 7 | P ≥ 30% |
| 5 | P ≥ 20% |
| 3 | P < 20% |

If interrupt count < 5, return "insufficient data".

## D6 — Tool breadth

Rationale: over-reliance on Bash/Read/Edit compared to MCP tools and dedicated
tools (Glob, Grep, Skill, Task) signals narrow tool knowledge. MCP adoption rate
is a secondary check.

Composite metric `T`:
- `mcp_rate` = fraction of sessions using any MCP tool
- `top3_share` = share of Bash + Read + Edit calls out of total tool calls

| Score | Thresholds |
|-------|-----------|
| 10 | mcp_rate ≥ 30% AND top3_share ≤ 40% |
| 8 | mcp_rate ≥ 15% AND top3_share ≤ 55% |
| 7 | mcp_rate ≥ 10% |
| 6 | mcp_rate ≥ 5% |
| 5 | mcp_rate ≥ 2% |
| 4 | mcp_rate < 2% |

## D7 — Writing/consistency friction

Rationale: repeated misunderstood_request or wrong_approach in writing-related
goal categories (writing_refinement, content_writing, documentation_update)
hints at drifting prose without upfront style framing.

Let `W = sum of misunderstood_request across writing-related sessions /
writing-related session count`.

| Score | Threshold |
|-------|-----------|
| 10 | W ≤ 0.1 |
| 8 | W ≤ 0.3 |
| 7 | W ≤ 0.6 |
| 5 | W ≤ 1.0 |
| 3 | W > 1.0 |

If writing-related sessions < 5, skip this dimension (display "n/a").

## D8 — Time-of-day management

Rationale: if certain hour buckets have 2x+ the friction rate of the best hour,
the user isn't self-managing well.

Compute friction_per_session for each hour (TPE timezone if user has Asia
locale; otherwise UTC).
Let `ratio = max_friction_rate / min_friction_rate` across hours with ≥ 5
sessions.

| Score | Threshold |
|-------|-----------|
| 10 | ratio ≤ 1.5 |
| 8 | ratio ≤ 2.0 |
| 7 | ratio ≤ 2.5 |
| 5 | ratio ≤ 3.5 |
| 3 | ratio > 3.5 |

If fewer than 3 hours have ≥ 5 sessions, skip.

---

## Notes

- Every score is accompanied by the raw metric that drove it, so the user can
  decide if the threshold is fair for their context.
- Rules assume > 20 rated sessions. Below that, the aggregate script flags the
  report as "preliminary" and dials down confidence language in the HTML.
- When a dimension is skipped due to insufficient data, it's shown as "n/a"
  in the report and does not factor into the 9-dimension average.
