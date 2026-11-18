# Findings-first redesign

Status: draft for approval (2026-11-18)

## 1. Intent

The SELF report is long, and a reader cannot tell at a glance what is wrong or what to change. The report should open with at most three problems, each stated in one sentence, backed by the user's own words or counts, and paired with one change to make. Everything else becomes an appendix.

Two further requirements came with this:

- The report must cover every AI tool the user drives by hand, not only Claude Code. Runs that one tool launched inside another (for example a review run started from a Claude Code session) are not the user's own usage and must not count.
- The report must not promote any vendor's features or plans.
- A persistent profile of the user. A later run for the same user reads only what is new and adds to or revises the profile, instead of reading the whole history again.
- Advice aims at how the most capable practitioners work with AI today (engineers at frontier labs, leading designers, domain experts), and the report shows the gap between the user and that reference.

## 2. Why the current report misses

- **It measures the form of usage, not its content.** `scan_transcripts.py` keeps only the first prompt of each session. Corrections typed mid-session, which is where most recurring problems show, never reach the analysis. The repeated-instruction heuristic is an exact match on that first prompt.
- **Most blind-spot heuristics depend on outcome labels** from session-meta and facets. Five of the seven (`sunk_cost`, `switch_tax`, `habit_drift`, `ask_vs_ship`, `interrupt_win_rate`) read the rated pool and gate off when that pool is thin or absent.
- **Fixed structure dilutes the conclusion.** The SELF layout has ten-plus sections and the peer review must fill four zones whether or not the user's problem lives there.
- **Other tools feed only share and concurrency numbers.** The adapters do not separate hand-driven sessions from launched ones, so volume from automated runs inflates the other tools' share.
- **Advice has no follow-up.** Nothing checks whether last run's advice was acted on.
- **Some scores reward feature adoption.** D6 and the `tool_breadth` badge rise with the share of sessions using specific product features. That reads as promotion when shown as a problem to fix.

## 3. Goals, non-goals, anti-goals

Goals

- First screen of the SELF report: one headline, at most three findings, one fix each, one line on last run's fixes, one line on coverage.
- Findings come from what the user typed, across Claude Code, Codex and Grok, hand-driven sessions only.
- Every count shown in a finding is produced by a script. The LLM proposes; it does not count.
- Each run checks the previous run's findings against new data.

Non-goals

- No change to the HR / recruiter version, badges, or the 9-dimension scoring in this round. Findings never render in HR.
- No removal or change of existing `analysis-data.json` fields. The only addition is per-source origin counts in the `cross_llm` block (5.2). Findings and the profile live in separate local files.
- No reverse engineering of Antigravity. It stays presence-only and contributes nothing to findings.
- No percentile or ranking claim. The pipeline has measured no population, so it cannot say where the user stands among other users. The gap analysis compares the user against a published list of practices, not against people. The existing "self-referential comparison only" rule in SKILL.md is narrowed to say exactly this.
- Not a runtime system. The report audits and drafts; it does not sit inside a live session attaching past rulings to new questions, and it does not write to instruction or memory files.

Anti-goals (a build that does these has failed even if it works)

- A finding whose fix is "start using product or feature X", or any mention of plans, upgrades or subscriptions.
- A first screen that needs scrolling to reach the first fix.
- A finding that cannot show at least one verbatim quote or a script-produced count.
- Filling three slots when fewer than three findings pass their gates. Zero findings is a valid result and renders as one plain line.

## 4. Approaches considered

1. **New material and new presentation (chosen).** Capture every hand-typed turn across tools, let the LLM propose candidate findings, verify them with a script, show the top three first, demote existing statistics to an appendix. Largest build; turns the V5 ledger books from the opening into appendix material.
2. **New presentation only.** Add the first screen but fill it from the existing seven heuristics. Fast, but the material is unchanged: findings would still come from time-of-day, token and interrupt statistics, and cross-tool coverage would stay at one heuristic.
3. **A separate lightweight skill.** Leave the report alone and build a second tool that prints only the first screen. Safest for existing code, but two tools to maintain and the long report keeps its problem.

The user chose 1: half of the problem is layout, the other half is that what the report finds is not close enough to what actually goes wrong.

## 5. Design

### 5.1 Capture: user turns

Each scanner gains a second output, `user-turns.jsonl`, one row per turn the user typed:

`source, session_id, origin, project_path, ts, turn_index, text, after_interrupt, prev_assistant_tail`

`prev_assistant_tail` is the length-capped end of the assistant message the user was answering, where the source records one (Claude Code and Codex; null for Grok). It lets the analysis see what the user was asked before they ruled.

- Claude Code: text user records only. Tool results, system-injected records, sidechain and `agent-*` subagent records are excluded.
- Codex: user messages from the rollout stream. Harness-injected context blocks (environment and instruction-file dumps) are excluded.
- Grok: rows from `prompt_history.jsonl` with `is_bash` false.
- Antigravity: none.

The file holds raw prompt text. It is written to the working directory only, is never committed, never copied into `analysis-data.json`, and never reaches HR output. Add it to `.gitignore`.

### 5.2 Origin: hand-driven versus launched

Every session, from every source, gets `origin`: `direct`, `launched`, or `unknown`.

- `launched`, signal 1: the launch-source field in the session header says another session spawned this one (observed in Codex headers as a structured `source` naming a sub-agent).
- `launched`, signal 2: another tool's transcript, in the main thread or in any subagent, contains a shell call that invokes this tool's CLI, and this session started while that call was running: from the moment the call was requested until its result came back, and never less than 60 seconds. Time alone decides; the working directory is not compared, so a launched run that changed directory cannot pass as hand-driven. This runs in both directions, so a Claude Code session started from a Codex session is caught the same way as the reverse.
- `unknown`, by header: the header says the run was non-interactive (Codex `source: exec`) and no launching call was seen. Nobody sat in that session, but the header does not say who started it: the user at a shell, a script, or a tool whose transcript has rotated away. It is never `direct`.
- `direct`: none of the above, and either (a) the session has two or more user turns with an assistant reply between them, or (b) the transcripts of every other tool that could have launched it still exist for that time, so a launch would have been visible.
- `unknown`: everything else, typically a single-prompt session from a period whose other-tool transcripts have rotated away.

Absence of a launch counts as evidence only where a launch could have been seen. Only `direct` sessions feed findings. `launched` and `unknown` counts are shown in the coverage line so the reader sees what was left out. This follows the existing lower-bound accounting rule: when in doubt, undercount.

`aggregate.py` adds per-source `direct` / `launched` / `unknown` session counts to the `cross_llm` block, and the team ledger shows them beside the existing share numbers. Existing share, parallel-hours, switch-tax and badge computations are not changed in this round, so trend snapshots stay comparable. Whether those should later exclude launched sessions is a follow-up (section 8).

### 5.3 Finding types (closed list)

| Type | What it says | Minimum to pass |
|---|---|---|
| `repeated_instruction` | The same instruction was typed again and again | 5 turns, 3 sessions, 2 distinct weeks |
| `late_stop` | A session kept going after the user corrected the same thing again and again | 3 sessions, each with 3 or more corrections of one thing |
| `rule_not_holding` | A rule already written in an instruction or memory file still had to be typed by hand | rule text found verbatim in the named file, plus 3 turns dated after that file's modification time |
| `repeat_ruling` | The AI keeps asking the same kind of question and the user gives the same answer every time | 4 asks of that kind, 80% or more answered the same way, 2 sessions |

Thresholds are starting values and get published in `references/scoring-rubric.md` with the others. No type measures how many product features the user has adopted.

Two things are deliberately not finding types. Which kind of work goes to which tool is shown descriptively in the profile's work map, with no verdict: Codex and Grok record no outcomes, so "the wrong tool for this work" cannot be backed by data. Abandoned work keeps its existing graveyard heuristic and gate; when that gate passes, the verifier carries the item into the ranking unchanged, as a fifth kind of first-screen entry with counts and no quotes.

`rule_not_holding` needs the user's written rules. During the skill run Claude reads the instruction files of each tool (user-level, and project-level for projects active in the window) and Claude Code's per-project memory directories. No script scans these files and nothing from them is stored except the one matched rule sentence and its file path. It also covers the cross-tool case: the rule is written in one tool's instruction file but the user types it by hand in another tool that has no such rule.

`repeat_ruling` is the audit behind two ideas the user wants to borrow: an AI that only brings up what truly needs a ruling, and a record of past rulings that travels with each new question. A kind of question that is answered the same way four times out of five did not need asking; the fix is a standing rule. The 80% bar is the guard in the other direction: where the user's answers vary, the question was worth asking and no finding is raised. Unavailable for Grok, which records no assistant text.

### 5.4 Propose, then verify

Step A, LLM (new SKILL.md step replacing the peer-review step): Claude reads the new turns in chunks, plus the profile, and writes `finding-candidates.json`. Each candidate has `type`, a one-sentence `claim`, a `fix`, and `turn_refs`. A `turn_ref` is `source` + `session_id` + `turn_index` plus the label the type needs:

- `repeated_instruction`: no label; every ref is an instance.
- `late_stop`: no label; every ref is a correction of the one thing named in the claim.
- `repeat_ruling`: `answer`, a short key for which way the user ruled (for example `approve`, `decline`); every ref is an answer to the one kind of question named in the claim.
- `rule_not_holding`: no label on refs; the candidate also carries `rule_file` and `rule_text`.

Step B, script (`scripts/verify_findings.py`): for each candidate it

- drops any `turn_ref` that does not exist or is not `direct`,
- recomputes turns, sessions, weeks and tools from what remains,
- applies the type's gate using those counts: per-session correction counts for `late_stop`; the share of the most common `answer` for `repeat_ruling`, where a ref with a null `prev_assistant_tail` is dropped; for `rule_not_holding`, that `rule_text` occurs in `rule_file` after whitespace normalisation and that the refs are dated after the file's modification time,
- drops the candidate if the gate fails,
- picks the verbatim quotes (length-capped) from the surviving turns,
- ranks survivors by occurrences in the most recent four weeks, then total occurrences, and keeps three.

Output is `findings.json`. Every number the report prints comes from this file.

The division of labour, stated plainly because the report's credibility rests on it: the LLM decides which turns belong together and, for rulings, which way each one went. The script decides whether those turns exist, are the user's own, and are numerous and spread enough to report. So a count in the report is always a true count of real turns, but the grouping behind it is a judgement. The report labels findings as "grouped by Claude, counted by script", shows the quotes so the reader can check the grouping, and SKILL.md instructs Claude to cite only turns that state the instruction, correction or ruling outright.

### 5.5 Fix rules

A fix is one sentence in the imperative and names one of four mechanisms: `write_rule` (put it in an instruction file the user already has), `stop_rule` (a personal cut-off), `cleanup`, `habit`.

- A `write_rule` fix carries paste-ready text: the rule sentence drafted from the user's own repeated wording, plus which tool's instruction file lacks it. For `repeat_ruling` the text is the standing ruling ("when asked X, do Y") with the count of past rulings behind it. The report shows the draft; it never edits the user's instruction files.
- A fix may only name tools that appear in the user's own data.
- `scripts/promo_lint.py`, modelled on `praise_lint.py`, warns at build time on upgrade, plan, subscription and feature-adoption wording in fixes and claims.
- The appendix keeps D6 as computed, but the first screen never presents a feature-adoption number as a problem.

### 5.6 Profile and incremental runs

One local file, `~/.claude/usage-data/autopsy-user-profile.json`, is the lasting record of the user. (The existing `cc-autopsy-profile.json` is the HR identity letterhead and is unrelated.) It holds:

- **Watermarks**: per source, the point up to which turns have been processed.
- **Work map**: the kinds of work the user does and which tool each kind goes to, with session counts.
- **Standing instructions**: instructions the user repeats, with counts and where each is or is not written down.
- **Rulings**: kinds of question the user has ruled on, the usual answer, and how often.
- **Findings history**: every finding ever kept, its fix, and its status over time.
- **Practice status**: the latest verdict per reference practice (5.7).

Every entry carries `first_seen`, `last_confirmed`, its counts, at most three quotes, and `origin`: `observed` or `user`.

Run behaviour:

- Scanners take the watermarks and emit only newer turns. The LLM step reads the new turns plus the profile, never the old turns. The verifier adds new counts to stored counts.
- The first run, or `--rebuild`, reads everything still on disk.
- The user can correct the profile, by telling Claude during a run or by editing the file. Such entries become `origin: user`. A run never overwrites or drops a `user` entry; if new data contradicts one, the report says so and leaves the entry alone.
- An `observed` entry not confirmed for 90 days is marked stale and stops feeding findings. It is kept, not deleted.
- Follow-up: each previous finding is recounted in the new window and labelled `improved` (rate down by half or more), `unchanged`, `worse`, or `too little data`. The first screen prints this as one line. This reverses the V5 decision not to build a follow-up loop.

Two consequences worth stating. Transcripts rotate after roughly 30 to 60 days, so the profile is the only place older patterns survive. And because old turns are not re-read, a wrong entry persists until the user corrects it or it goes stale; that is the cost of incremental runs, and `--rebuild` only reaches what is still on disk.

The profile contains quotes. It is local only, git-ignored, never read by the HR build, and follows the same never-fail and test-isolation rules as `autopsy-history.jsonl`.

The report also renders the profile's standing instructions and rulings as a tool-neutral "how to work with me" card the user can paste into any tool's instruction file.

### 5.7 Reference practices and gap analysis

`references/practice-benchmark.md` is a dated, versioned list of practices, maintained in the repo the same way the pricing table is. Each practice has:

- a statement of the behaviour, written without naming a product,
- the group it belongs to: engineering, design, or domain-expert work,
- sources with dates,
- the signal that would show it, chosen from a closed list of script-computed measures (the finding-type counters and the work-map counters), or `not observable`. A practice cannot define a new measure of its own; adding a measure is a code change with tests.

Entry rules:

- A practice needs two independent sources. Material published by an AI vendor about its own product counts as one source at most and cannot stand alone; a practice resting on vendor material only is not admitted. This keeps the benchmark from becoming a channel for promotion.
- A practice is a way of working (how work is specified, checked, split, stopped), never "uses feature X".
- The list carries a review date. A build warns when the list is older than 90 days, because this field moves fast.

Gap analysis: the work map selects which groups apply to this user. For each applicable practice the verifier produces one verdict from script-counted signals: `meets`, `partly`, `not seen`, or `cannot tell from this data`. `meets` needs evidence at the same bar as a problem does. Practices marked `not observable` are listed as such and never judged.

How it reaches the reader: every fix on the first screen names the reference practice it moves toward, where one applies. The full gap table is the first appendix section, open by default.

The label in the report is "reference practices", with the review date and source count. It is not called a percentile.

Building the first version of the list is research work of its own and its content is the maintainer's call: which practices count as the reference is a judgement, not a computation.

### 5.8 Rendering

SELF report, top to bottom:

1. Headline: the top finding as one sentence.
2. Up to three findings: claim, evidence (quote and counts with tool names), fix, and the reference practice the fix moves toward.
3. Last run's fixes: one line.
4. Coverage: tools read, hand-driven sessions counted, launched and unknown sessions left out, date window, whether this was an incremental run.
5. Gap table against the reference practices, open by default.
6. Profile: work map and the "how to work with me" card.
7. Appendix, collapsed by default: ledger books, usage snapshot, 9-dimension scoring, pattern mining, weekly trends, case study, methodology.

Removed from SELF: the four-zone peer review and try-this-week (findings and fixes replace them), and the old evidence library (it indexed peer-review claims). `--peer-review` and `--try-this` stay accepted and ignored with a warning for one release.

The SELF report and the profile may show verbatim text the user typed into any tool, including Codex and Grok. This narrows the V5 rule that cross-tool prompt text reaches no output: it still never reaches HR output or `analysis-data.json`, and the tests for those stay; the SELF-side assertions are rewritten to allow text only inside finding quotes and the profile card. All quotes are HTML-escaped. Output stays self-contained. New chrome strings go into both locales; zh_TW text is written natively. HR output is unchanged and a test asserts no finding text or quote appears in it.

### 5.9 Testing

- `generate_demo_data.py` gains synthetic cross-tool user turns, including launched sessions and injected context blocks.
- Origin classifier: direct, launched by time-and-directory match, unknown.
- Verifier: fabricated `turn_refs` dropped; counts recomputed; each gate at its boundary; ranking; zero-findings path.
- Renderer: first-screen structure, escaping, offline safety, HR leak test, locale key parity.
- `promo_lint` word list.
- Profile: watermark-bounded scan reads nothing older; counts accumulate across two runs; `user` entries survive contradicting data; stale marking at 90 days; follow-up labels; test builds never touch the real profile file.
- Benchmark: every practice has two sources and no vendor-only entry; age warning; each verdict path including `cannot tell`.

## 6. Phasing

1. Capture and origin: `user-turns.jsonl`, origin classification, team-ledger split.
2. Verify and show: verifier, new SKILL.md step, first screen, appendix collapse, promo lint.
3. Profile: the profile file, incremental runs, follow-up labels, the "how to work with me" card.
4. Reference practices, in two steps: (a) candidate list researched and drafted with sources, reviewed and settled by the maintainer; (b) the gap table and practice references on fixes. The closed list of measures is built in phases 2 and 3, so (b) does not wait on new detectors.

Each phase is a separate PR and leaves the report buildable.

## 7. Left to the builder

- Chunking strategy for the LLM step when `user-turns.jsonl` is large.
- The time window for the launched-session match.
- Normalisation used to recount a previous finding's pattern.
- Quote length cap.

## 8. Calls made without asking (flag at review if wrong)

- HR version, badges and 9-dimension scoring are untouched this round. Reworking D6 and the `tool_breadth` badge so they stop rewarding feature adoption is a follow-up, not part of this design.
- `unknown` origin sessions are excluded from findings rather than included. A session with no sign of being launched counts as `direct` only where a launch could have been seen.
- Existing share, parallel-hours and badge numbers still include launched sessions this round. The cross-tool badge may therefore be earned partly by launched runs; fixing that belongs with the D6 follow-up.
- "Wrong tool for this work" is not a finding. The work map is descriptive.
- Written rules are read by Claude during the run from instruction files and Claude Code memory directories; only the matched sentence is kept.
- The peer review and try-this-week are removed rather than kept alongside the findings.
- No schema change to `analysis-data.json`.
- The reference practices are a reviewed list shipped in the repo, not a web search run at report time. A list can be checked and reproduced; a live search cannot.
- A practice resting only on an AI vendor's own material is not admitted.
- The gap analysis is labelled "reference practices", never a percentile.
- The profile is one JSON file; user corrections are entries in it, not a separate notes file.
