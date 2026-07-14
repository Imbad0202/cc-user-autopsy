"""
Generate synthetic usage-data resembling a real Claude Code heavy user,
then run the full pipeline to produce assets/example-output.html.
No identifiable information; all projects/sids/summaries are fabricated.
"""
import json
import os
import random
import shutil
import string
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)

OUT_DIR = Path("/tmp/cc-autopsy-demo")
META_DIR = OUT_DIR / "usage-data/session-meta"
FACETS_DIR = OUT_DIR / "usage-data/facets"
PROJECTS_DIR = OUT_DIR / "projects"
CODEX_DIR = OUT_DIR / "codex-sessions"
GROK_DIR = OUT_DIR / "grok-sessions"
ANTIGRAVITY_DIR = OUT_DIR / "antigravity-conversations"
# Wipe stale outputs from previous runs — without this, transcript files
# accumulate across regenerations and metrics drift toward whichever schema
# was most recent (e.g. half the assistant records lack `model`).
for d in (META_DIR, FACETS_DIR, PROJECTS_DIR, CODEX_DIR, GROK_DIR, ANTIGRAVITY_DIR):
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)

DEMO_PROJECTS_CROSS = ["webapp", "data-pipeline", "infra"]

# --- Phase 2 blind-spot fixtures (Task 12) ---------------------------------
# These constants are injected by INDEX, never by random draw, so the three
# hard gate assertions in tests/test_demo_data.py never flake across
# regenerations. See .superpowers/sdd/task-12-brief.md for the exact gates.

# BS#1 (repeated-instruction tax): forced verbatim onto 8 Claude sessions
# spread over >=4 distinct ISO weeks, 3 codex sessions, and 2 grok sessions.
DEMO_REPEATED_INSTRUCTION = (
    "Reply in zh-TW, run the full pytest suite before claiming done, "
    "and never push without asking"
)

# BS#2 (sunk-cost pairs): 3 engineered (failed, retry) pairs. Failed session
# is not_achieved with an accelerating output-token curve; retry lands 1-2
# days later, fully_achieved, near-duplicate prompt (Jaccard >= 0.5), at
# <=50% of the failed session's duration, with a flat token curve. Each
# pair's prompt is deliberately worded with distinct vocabulary from the
# other two pairs (not just a swapped noun) so bs_sunk_cost's greedy
# first-match pairing can't cross-match a failed session in pair A to the
# retry in pair B — every failed session's best (and only >=0.5) match is
# its own retry.
DEMO_SUNK_COST_PAIRS = ["billing", "notifications", "search-index"]
_SUNK_COST_PROMPTS = {
    "billing": "refactor the billing export pipeline to stream batches",
    "notifications": "make the push notification worker retry with backoff "
                     "instead of dropping failed sends",
    "search-index": "rebuild the search index incrementally instead of a "
                    "full nightly reindex job",
}
_SUNK_COST_FAILED_DURATION_MIN = 120
_SUNK_COST_RETRY_DURATION_MIN = 45  # <= 50% of 120

# BS#4 (graveyard): 2 dedicated projects whose only sessions are 25-40 days
# old, with substantial edits and zero commits, and no newer activity.
DEMO_GRAVEYARD_PROJECTS = ["legacy-migration", "internal-docs-site"]
_GRAVEYARD_DAYS_AGO = {"legacy-migration": 28, "internal-docs-site": 36}

PROJECTS = [
    "acme-dashboard",
    "acme-dashboard",
    "acme-dashboard",
    "acme-dashboard",
    "spark-mobile",
    "spark-mobile",
    "writing-garden",
    "kb-index",
    "ci-scripts",
    "design-lab",
    "design-lab",
    "prod-monitor",
    # Long-named project to stress horizontal-bar / chart label rendering.
    "internal-platform-observability-toolkit",
]

# Realistic Claude Code model mix as of 2026-04. Heavy users see Opus 4.7
# dominate, with some Sonnet 4.6 for cheaper subagent-style work and a tiny
# fraction of Haiku 4.5 (now banned in this user's setup, but historical
# data still surfaces it). Weights drive both meta.input_model_counts and
# the per-assistant `model` field on transcripts.
MODEL_MIX = {
    "claude-opus-4-7": 0.62,
    "claude-sonnet-4-6": 0.30,
    "claude-haiku-4-5": 0.08,
}

SESSION_TYPES = {
    "multi_task": 0.35,
    "iterative_refinement": 0.28,
    "single_task": 0.15,
    "exploration": 0.12,
    "quick_question": 0.10,
}

OUTCOMES = {
    "fully_achieved": 0.42,
    "mostly_achieved": 0.26,
    "partially_achieved": 0.18,
    "not_achieved": 0.05,
    "unclear_from_transcript": 0.09,
}

HELPFULNESS = {
    "very_helpful": 0.46,
    "essential": 0.22,
    "moderately_helpful": 0.18,
    "slightly_helpful": 0.08,
    "unhelpful": 0.06,
}

FRICTION_TYPES_WEIGHTS = {
    "buggy_code": 0.32,
    "wrong_approach": 0.28,
    "misunderstood_request": 0.10,
    "excessive_changes": 0.08,
    "output_token_limit_exceeded": 0.05,
    "tool_limitation": 0.05,
    "user_rejected_action": 0.04,
    "tool_or_plugin_failure": 0.03,
    "external_api_error": 0.03,
    "environmental_issue": 0.02,
}

GOAL_CATEGORIES = [
    "bug_fix", "feature_implementation", "feature_addition", "debugging",
    "deployment", "documentation_update", "content_writing",
    "writing_refinement", "memory_update", "git_operations",
    "code_review", "ui_refinement", "information_query", "exploration",
    "quick_question",
]

TOOLS_COMMON = {
    "Bash": 18, "Read": 14, "Edit": 11, "Grep": 6, "TaskUpdate": 4,
    "Write": 3, "TaskCreate": 3, "Agent": 2, "Task": 2, "Glob": 2,
    "Skill": 1, "TodoWrite": 1, "WebSearch": 1,
}

MCP_TOOLS = [
    "mcp__plugin_supabase_supabase__execute_sql",
    "mcp__plugin_playwright_playwright__browser_navigate",
    "mcp__plugin_vercel_vercel__list_deployments",
]

FIRST_PROMPTS = [
    "Add an env-toggle so the staging deploy uses the mock data source instead of hitting production.",
    "There's a bug where the chart tooltip shows wrong percentages — can you trace the data flow and fix it",
    "help me write a short technical blog post about our latest release, 500-700 words",
    "run the migration for phase 3 and deploy to staging, then verify the new endpoint returns 200",
    "quick one — how many open PRs do we have right now",
    "the registration flow breaks when the user has a plus sign in their email, please fix",
    "Review the pull request #182 and leave constructive comments on the architecture",
    "I need to refactor the export module to use the new token-based auth. Start by mapping the current module boundaries.",
    "generate screenshots for the app store listing, must follow the new brand guidelines",
    "explore this codebase and summarize the test setup — are we using vitest or jest",
    "write a one-pager for next sprint's customer research plan",
    "debug why the background job is failing silently in production",
]

SUMMARIES_GOOD = [
    "User implemented phase 3 migration with full TDD, 12 new tests pass, deployed via CI.",
    "User fixed registration regression, root cause was email encoding in legacy middleware.",
    "User iterated on pricing page hero copy across three drafts; final version approved.",
    "User ran exploratory analysis of pricing experiment, identified a correlation and logged follow-up.",
    "User reviewed PR #182, accepted architecture; flagged three minor refactors to pick up later.",
]

SUMMARIES_MIXED = [
    "User shipped the feature but two follow-up issues were filed post-merge.",
    "User iterated on dashboard layout through v7; still unsatisfied with mobile spacing.",
    "User partially converted the export module but auth migration left for next sprint.",
    "User iterated on the blog draft; tone was still off after three revisions.",
]

SUMMARIES_BAD = [
    "Claude repeatedly broke the chart rendering across versions v10-v14; user had to roll back twice.",
    "Claude kept patching symptoms of the sign-in bug; root cause was found only after user redirected.",
    "Claude hit output-token-limit twice; session ended without deploying.",
    "User interrupted — Claude was exploring files instead of running the migration requested.",
    "Claude misread the style guide and introduced em-dashes repeatedly in the writing session.",
]

FRICTION_DETAILS = {
    "buggy_code": "Introduced a subtle regression in the chart rendering that only surfaced in mobile layouts after three passes.",
    "wrong_approach": "Attempted to solve the drift by patching the view layer; the real issue was in the query.",
    "misunderstood_request": "User asked to deploy; Claude spent the session reading files and writing a plan.",
    "excessive_changes": "One small copy edit led Claude to refactor 8 files; user reverted most of the diff.",
    "output_token_limit_exceeded": "Claude's responses exceeded the output token cap twice; session was truncated.",
    "user_rejected_action": "User interrupted Claude's plan — the proposed architecture was not acceptable.",
}


def weighted_choice(d):
    items, weights = list(d.keys()), list(d.values())
    return random.choices(items, weights=weights)[0]


def mk_sid():
    return str(uuid.uuid4())


def gen_tool_counts(intensity):
    counts = {}
    for tool, base in TOOLS_COMMON.items():
        counts[tool] = max(0, int(random.gauss(base * intensity, base * 0.5)))
    # occasionally add a subagent tool
    if random.random() < 0.5:
        counts["Agent"] = counts.get("Agent", 0) + random.randint(1, 6)
    # small chance of MCP usage
    if random.random() < 0.15:
        mcp = random.choice(MCP_TOOLS)
        counts[mcp] = random.randint(1, 8)
    # drop zeros
    return {k: v for k, v in counts.items() if v > 0}


def gen_session(sid, start_time, project):
    stype = weighted_choice(SESSION_TYPES)
    if stype == "quick_question":
        dur = random.randint(1, 10)
        intensity = 0.2
    elif stype == "single_task":
        dur = random.randint(10, 35)
        intensity = 0.7
    elif stype == "multi_task":
        dur = random.randint(20, 90)
        intensity = 1.2
    elif stype == "iterative_refinement":
        dur = random.randint(25, 140)
        intensity = 1.5
    else:  # exploration
        dur = random.randint(15, 60)
        intensity = 0.9

    tool_counts = gen_tool_counts(intensity)
    total_tool = sum(tool_counts.values())
    user_msgs = max(2, int(random.gauss(total_tool * 0.4, 3)))
    assistant_msgs = user_msgs + random.randint(5, 30)

    in_tok = int(random.gauss(2000 * intensity, 1000))
    out_tok = int(random.gauss(12000 * intensity, 6000))
    # occasional token spike (to trigger the output-token-limit path)
    if random.random() < 0.03:
        out_tok += random.randint(60_000, 150_000)

    commits = 0
    if stype in ("single_task", "multi_task") and random.random() < 0.6:
        commits = random.randint(1, 4)
    elif stype == "iterative_refinement" and random.random() < 0.35:
        commits = random.randint(1, 2)

    interrupts = 0
    if stype == "iterative_refinement" and random.random() < 0.45:
        interrupts = random.randint(1, 3)
    elif random.random() < 0.08:
        interrupts = 1

    uses_task_agent = "Agent" in tool_counts or "Task" in tool_counts
    uses_mcp = any(k.startswith("mcp__") for k in tool_counts)

    fp_text = random.choice(FIRST_PROMPTS)
    response_times = [abs(random.gauss(80, 50)) for _ in range(user_msgs)]

    meta = {
        "session_id": sid,
        "project_path": f"/home/user/projects/{project}",
        "start_time": start_time.isoformat().replace("+00:00", "Z"),
        "duration_minutes": dur,
        "user_message_count": user_msgs,
        "assistant_message_count": assistant_msgs,
        "tool_counts": tool_counts,
        "languages": {"TypeScript": random.randint(0, 10), "Python": random.randint(0, 6)},
        "git_commits": commits,
        "git_pushes": commits if commits > 0 and random.random() < 0.7 else 0,
        "input_tokens": max(0, in_tok),
        "output_tokens": max(0, out_tok),
        # Cache tokens scale with input — realistic Claude Code users see
        # heavy cache reuse because the system prompt + CLAUDE.md stays stable
        # across turns. cache_read typically 4-8× input; cache_creation
        # much smaller (only when context shifts).
        "cache_read_input_tokens": int(max(0, in_tok) * random.uniform(4.0, 8.0)),
        "cache_creation_input_tokens": int(max(0, in_tok) * random.uniform(0.15, 0.35)),
        # model_counts: which model answered how many turns. Use session's
        # primary model plus a small rotation so the favorite_model tile and
        # models-breakdown chart render plausibly.
        "model_counts": (lambda primary: {
            primary: assistant_msgs - (1 if assistant_msgs > 3 else 0),
            **({weighted_choice({m: w for m, w in MODEL_MIX.items() if m != primary}): 1}
               if assistant_msgs > 3 else {}),
        })(weighted_choice(MODEL_MIX)),
        "first_prompt": fp_text,
        "user_interruptions": interrupts,
        "user_response_times": response_times,
        "tool_errors": random.randint(0, 2) if random.random() < 0.1 else 0,
        "tool_error_categories": {},
        "uses_task_agent": uses_task_agent,
        "uses_mcp": uses_mcp,
        "uses_web_search": random.random() < 0.1,
        "uses_web_fetch": random.random() < 0.08,
        "lines_added": commits * random.randint(20, 120) if commits else random.randint(0, 30),
        "lines_removed": commits * random.randint(5, 80) if commits else random.randint(0, 20),
        "files_modified": commits * random.randint(1, 5) if commits else 0,
        "message_hours": [start_time.hour] * user_msgs,
        "user_message_timestamps": [start_time.isoformat().replace("+00:00", "Z")] * user_msgs,
    }

    # Facet only for ~55% of sessions
    facet = None
    if random.random() < 0.55:
        outcome = weighted_choice(OUTCOMES)
        # bias: iterative_refinement less likely fully_achieved
        if stype == "iterative_refinement" and outcome == "fully_achieved":
            outcome = "mostly_achieved" if random.random() < 0.5 else outcome
        helpf = weighted_choice(HELPFULNESS)
        fric = {}
        if outcome in ("partially_achieved", "not_achieved"):
            for _ in range(random.randint(2, 5)):
                ft = weighted_choice(FRICTION_TYPES_WEIGHTS)
                fric[ft] = fric.get(ft, 0) + random.randint(1, 3)
        elif outcome == "mostly_achieved" and random.random() < 0.4:
            ft = weighted_choice(FRICTION_TYPES_WEIGHTS)
            fric[ft] = random.randint(1, 2)
        elif random.random() < 0.1:
            ft = weighted_choice(FRICTION_TYPES_WEIGHTS)
            fric[ft] = 1
        # goal categories
        gc = {}
        for _ in range(random.randint(1, 3)):
            g = random.choice(GOAL_CATEGORIES)
            gc[g] = gc.get(g, 0) + 1

        if outcome == "fully_achieved":
            summary = random.choice(SUMMARIES_GOOD)
        elif outcome in ("mostly_achieved", "unclear_from_transcript"):
            summary = random.choice(SUMMARIES_MIXED)
        else:
            summary = random.choice(SUMMARIES_BAD)

        fric_detail = ""
        if fric:
            primary = max(fric, key=fric.get)
            fric_detail = FRICTION_DETAILS.get(primary, "")

        primary_success = random.choice([
            "multi_file_changes", "code_generation", "explanation", "debugging",
            "refactoring", "planning",
        ])

        facet = {
            "session_id": sid,
            "underlying_goal": fp_text[:120],
            "goal_categories": gc,
            "outcome": outcome,
            "user_satisfaction_counts": {"satisfied": 1, "likely_satisfied": 2},
            "claude_helpfulness": helpf,
            "session_type": stype,
            "friction_counts": fric,
            "friction_detail": fric_detail,
            "primary_success": primary_success,
            "brief_summary": summary,
        }

    return meta, facet


def _gen_usage(intensity):
    """Synthesize an assistant `usage` dict resembling real Claude Code data.
    Cache-read dominates input volume (typical hit rate >95%), so the totals
    we emit must reflect that for downstream reports to look realistic."""
    in_tok = max(50, int(random.gauss(800 * intensity, 300)))
    out_tok = max(50, int(random.gauss(2500 * intensity, 1200)))
    cache_create = max(0, int(random.gauss(40_000 * intensity, 15_000)))
    cache_read = max(0, int(random.gauss(450_000 * intensity, 180_000)))
    return {
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_creation_input_tokens": cache_create,
        "cache_read_input_tokens": cache_read,
    }


def gen_transcript(sid, meta, facet):
    """Minimal .jsonl — enough for sample_sessions.py and scan_transcripts.py
    to parse. Each assistant record carries a `model` and a `usage` dict so
    the cache-token / model-mix / API-equivalent-cost panels render."""
    lines = []
    start = datetime.fromisoformat(meta["start_time"].replace("Z", "+00:00"))
    intensity = max(0.2, sum(meta["tool_counts"].values()) / 30)
    # Pick a primary model for this session — heavy users tend to stick to
    # one per session — with occasional secondary usage on iterative work.
    primary_model = weighted_choice(MODEL_MIX)
    secondary_model = (
        weighted_choice({m: w for m, w in MODEL_MIX.items() if m != primary_model})
        if random.random() < 0.25 else None
    )

    def asst_record(text_or_content, ts, model):
        if isinstance(text_or_content, str):
            content = [{"type": "text", "text": text_or_content}]
        else:
            content = text_or_content
        return {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "model": model,
                "content": content,
                "usage": _gen_usage(intensity),
            },
            "timestamp": ts,
        }

    # Record 1: user message
    lines.append({
        "type": "user",
        "message": {
            "role": "user",
            "content": meta["first_prompt"],
        },
        "timestamp": start.isoformat(),
    })
    # Record 2: assistant with tool use
    tool_names = list(meta["tool_counts"].keys())[:5]
    content = [{"type": "text", "text": "I'll get started on that."}]
    for tn in tool_names:
        content.append({"type": "tool_use", "name": tn, "id": f"t_{random.randint(1,99999)}", "input": {}})
    lines.append(asst_record(content, (start + timedelta(seconds=30)).isoformat(), primary_model))
    # Some back-and-forth
    for i in range(random.randint(2, 8)):
        lines.append({
            "type": "user",
            "message": {
                "role": "user",
                "content": random.choice([
                    "looks good, continue",
                    "can you double-check that part",
                    "actually let's try a different angle",
                    "that's close but not quite",
                ]),
            },
            "timestamp": (start + timedelta(minutes=i + 1)).isoformat(),
        })
        # Most turns use the primary model; if a secondary is set, rotate
        # in occasionally to mimic a subagent dispatch.
        model = secondary_model if (secondary_model and random.random() < 0.3) else primary_model
        lines.append(asst_record(
            "Understood, revising.",
            (start + timedelta(minutes=i + 1, seconds=40)).isoformat(),
            model,
        ))
    return lines


def gen_engineered_transcript(meta, output_seq, model):
    """Build a transcript whose assistant `usage.output_tokens` sequence is
    exactly `output_seq` (in order) — used by the sunk-cost fixture so
    `token_accel` (scan_transcripts.py: second-half sum / first-half sum of
    per-assistant-message output_tokens) is deterministic rather than drawn
    from `_gen_usage`'s gaussian noise."""
    lines = []
    start = datetime.fromisoformat(meta["start_time"].replace("Z", "+00:00"))
    total_minutes = meta["duration_minutes"]
    n = len(output_seq)
    step = max(1, total_minutes // max(1, n))

    lines.append({
        "type": "user",
        "message": {"role": "user", "content": meta["first_prompt"]},
        "timestamp": start.isoformat(),
    })
    for i, out_tok in enumerate(output_seq):
        ts = start + timedelta(minutes=step * i, seconds=30)
        usage = {
            "input_tokens": 600,
            "output_tokens": out_tok,
            "cache_creation_input_tokens": 8_000,
            "cache_read_input_tokens": 200_000,
        }
        lines.append({
            "type": "assistant",
            "message": {"role": "assistant", "model": model,
                       "content": [{"type": "text", "text": "Working on it."}],
                       "usage": usage},
            "timestamp": ts.isoformat(),
        })
        if i < n - 1:
            lines.append({
                "type": "user",
                "message": {"role": "user", "content": "continue"},
                "timestamp": (ts + timedelta(seconds=45)).isoformat(),
            })
    return lines


def _base_engineered_meta(sid, project, start, duration_minutes, n_msgs,
                          output_tokens, prompt, **overrides):
    """Shared session-meta skeleton for the Task 12 engineered fixtures
    (sunk-cost pairs, graveyard projects) — factored out of gen_session()'s
    field set because those fixtures need exact/deterministic values
    (duration, token curve, tool_counts) that gen_session()'s randomized
    draws can't guarantee, but still share the same ~20 low-signal
    boilerplate fields (interruption/error/usage-flag defaults, per-message
    timestamp lists) verbatim. Callers pass the fields that make their
    fixture what it is (tool_counts, git_commits, cache tokens, ...) as
    keyword overrides."""
    start_iso = start.isoformat().replace("+00:00", "Z")
    meta = {
        "session_id": sid,
        "project_path": f"/home/user/projects/{project}",
        "start_time": start_iso,
        "duration_minutes": duration_minutes,
        "user_message_count": n_msgs,
        "assistant_message_count": n_msgs,
        "tool_counts": {},
        "languages": {},
        "git_commits": 0,
        "git_pushes": 0,
        "input_tokens": 0,
        "output_tokens": output_tokens,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "model_counts": {},
        "first_prompt": prompt,
        "user_interruptions": 0,
        "user_response_times": [50.0] * n_msgs,
        "tool_errors": 0,
        "tool_error_categories": {},
        "uses_task_agent": False,
        "uses_mcp": False,
        "uses_web_search": False,
        "uses_web_fetch": False,
        "lines_added": 0,
        "lines_removed": 0,
        "files_modified": 0,
        "message_hours": [start.hour] * n_msgs,
        "user_message_timestamps": [start_iso] * n_msgs,
    }
    meta.update(overrides)
    return meta


def gen_sunk_cost_pairs(now):
    """BS#2 fixture — 3 (failed, retry) pairs. Returns (metas, facets,
    transcripts) dicts keyed by session_id, ready to be merged into the
    main pools. Failed sessions accelerate late (token_accel >= 1.5);
    retries are flat (token_accel < 1.5, well under the guard)."""
    metas, facets, transcripts = {}, {}, {}
    # Anchor the pairs comfortably inside the demo's 100-day window, spaced
    # out so all 3 retries land on distinct calendar days without colliding
    # with the graveyard/repeated-instruction anchors below.
    base_days_ago = [50, 55, 60]
    for name, days_ago in zip(DEMO_SUNK_COST_PAIRS, base_days_ago):
        project = f"leak-{name}"
        prompt = _SUNK_COST_PROMPTS[name]
        fail_sid = mk_sid()
        fail_start = now - timedelta(days=days_ago, hours=10)
        # 8 assistant messages: first half small and flat, second half more
        # than 1.5x the first half's sum -> token_accel >= 1.5.
        fail_seq = [1200, 1300, 1250, 1300, 4200, 4400, 4300, 4500]
        fail_meta = _base_engineered_meta(
            fail_sid, project, fail_start, _SUNK_COST_FAILED_DURATION_MIN,
            len(fail_seq), sum(fail_seq), prompt,
            tool_counts={"Bash": 6, "Read": 8, "Edit": 5},
            languages={"TypeScript": 4, "Python": 2},
            input_tokens=4800,
            cache_read_input_tokens=800_000,
            cache_creation_input_tokens=32_000,
            model_counts={"claude-opus-4-7": len(fail_seq)},
            user_response_times=[60.0] * len(fail_seq),
            lines_added=40, lines_removed=10, files_modified=3,
        )
        fail_facet = {
            "session_id": fail_sid,
            "underlying_goal": prompt,
            "goal_categories": {"feature_implementation": 1},
            "outcome": "not_achieved",
            "user_satisfaction_counts": {"unsatisfied": 1},
            "claude_helpfulness": "slightly_helpful",
            "session_type": "iterative_refinement",
            "friction_counts": {"wrong_approach": 3},
            "friction_detail": f"Repeated attempts on the {name} task "
                               "regressed; session ended without a fix.",
            "primary_success": "debugging",
            "brief_summary": f"Claude thrashed on the {name} task; output "
                             "grew each retry with no fix landed.",
        }
        metas[fail_sid] = fail_meta
        facets[fail_sid] = fail_facet
        transcripts[fail_sid] = (project, gen_engineered_transcript(
            fail_meta, fail_seq, "claude-opus-4-7"))

        retry_sid = mk_sid()
        retry_start = fail_start + timedelta(days=1, hours=3)
        retry_prompt = prompt + " correctly"  # +1 word, Jaccard >= 0.5
        # Flat curve: second half is NOT >= 1.5x the first half.
        retry_seq = [1100, 1150, 1200, 1100, 1150, 1200]
        retry_meta = _base_engineered_meta(
            retry_sid, project, retry_start, _SUNK_COST_RETRY_DURATION_MIN,
            len(retry_seq), sum(retry_seq), retry_prompt,
            tool_counts={"Bash": 4, "Read": 3, "Edit": 4},
            languages={"TypeScript": 3, "Python": 1},
            git_commits=2, git_pushes=1,
            input_tokens=3200,
            cache_read_input_tokens=500_000,
            cache_creation_input_tokens=18_000,
            model_counts={"claude-opus-4-7": len(retry_seq)},
            user_response_times=[40.0] * len(retry_seq),
            lines_added=60, lines_removed=15, files_modified=3,
        )
        retry_facet = {
            "session_id": retry_sid,
            "underlying_goal": retry_prompt,
            "goal_categories": {"feature_implementation": 1},
            "outcome": "fully_achieved",
            "user_satisfaction_counts": {"satisfied": 1},
            "claude_helpfulness": "very_helpful",
            "session_type": "single_task",
            "friction_counts": {},
            "friction_detail": "",
            "primary_success": "code_generation",
            "brief_summary": f"User retried the {name} task with a tighter "
                             "prompt; shipped in under half the time of the "
                             "failed attempt.",
        }
        metas[retry_sid] = retry_meta
        facets[retry_sid] = retry_facet
        transcripts[retry_sid] = (project, gen_engineered_transcript(
            retry_meta, retry_seq, "claude-opus-4-7"))
    return metas, facets, transcripts


def gen_graveyard_transcript(meta, edit_count, write_count):
    """Engineered transcript whose scan_transcripts.py-derived tool_counts
    has exactly `edit_count` Edit and `write_count` Write tool_use blocks —
    gen_transcript() only emits one tool_use per distinct tool NAME, which
    can't reach the BS#4 gate's >=5-write threshold on its own."""
    start = datetime.fromisoformat(meta["start_time"].replace("Z", "+00:00"))
    lines = [{
        "type": "user",
        "message": {"role": "user", "content": meta["first_prompt"]},
        "timestamp": start.isoformat(),
    }]
    tool_calls = ["Edit"] * edit_count + ["Write"] * write_count + ["Read"] * 12 + ["Bash"] * 4
    content = [{"type": "text", "text": "Working through the pass now."}]
    for j, tn in enumerate(tool_calls):
        content.append({"type": "tool_use", "name": tn,
                        "id": f"t_{j}_{random.randint(1, 99999)}", "input": {}})
    lines.append({
        "type": "assistant",
        "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                   "content": content,
                   "usage": {"input_tokens": 5000, "output_tokens": 22000,
                             "cache_creation_input_tokens": 30_000,
                             "cache_read_input_tokens": 700_000}},
        "timestamp": (start + timedelta(minutes=30)).isoformat(),
    })
    return lines


def gen_graveyard_projects(now):
    """BS#4 fixture — 2 dedicated projects whose only (and therefore last)
    session is 25-40 days old, with >=5 write-tool calls and zero commits."""
    metas, transcripts = {}, {}
    for project in DEMO_GRAVEYARD_PROJECTS:
        sid = mk_sid()
        days_ago = _GRAVEYARD_DAYS_AGO[project]
        start = now - timedelta(days=days_ago, hours=14)
        prompt = f"do a big pass on {project.replace('-', ' ')}, lots of edits needed"
        meta = _base_engineered_meta(
            sid, project, start, 70, 9, 22000, prompt,
            assistant_message_count=14,
            tool_counts={"Edit": 9, "Write": 3, "Read": 12, "Bash": 4},
            languages={"Markdown": 6, "TypeScript": 2},
            input_tokens=5000,
            cache_read_input_tokens=700_000,
            cache_creation_input_tokens=30_000,
            model_counts={"claude-sonnet-4-6": 14},
            lines_added=150, lines_removed=40, files_modified=6,
        )
        metas[sid] = meta
        transcripts[sid] = (project, gen_graveyard_transcript(meta, 9, 3))
    return metas, transcripts


def _codex_line(ts, type_, payload):
    return json.dumps({"timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                       "type": type_, "payload": payload})


def gen_codex_sessions(now, n=32):
    # BS#1 fixture: force the repeated instruction onto 3 codex sessions,
    # spread over 3 distinct weeks (by index, not random), so the
    # repeated_instructions gate's "sources" field includes "codex".
    _REPEAT_INDICES = {2: 8, 10: 22, 18: 36}  # session index -> days_ago
    for i in range(n):
        if i in _REPEAT_INDICES:
            start = now - timedelta(days=_REPEAT_INDICES[i], hours=9)
        else:
            start = now - timedelta(days=int(random.triangular(0, 60, 20)),
                                    hours=random.randint(0, 12))
        sid = mk_sid()
        proj = random.choice(DEMO_PROJECTS_CROSS)
        cwd = f"/home/user/projects/{proj}"
        lines = [
            _codex_line(start, "session_meta", {"id": sid, "cwd": cwd}),
            _codex_line(start, "turn_context",
                        {"model": "gpt-5.4", "effort": "high", "cwd": cwd}),
        ]
        t = start
        first_msg = DEMO_REPEATED_INSTRUCTION if i in _REPEAT_INDICES else None
        for turn in range(random.randint(1, 6)):
            t += timedelta(minutes=random.randint(1, 8))
            msg_text = first_msg if (first_msg and turn == 0) else f"demo codex prompt {turn}"
            lines.append(_codex_line(t, "event_msg",
                                     {"type": "user_message",
                                      "message": msg_text}))
            t += timedelta(minutes=random.randint(1, 5))
            lines.append(_codex_line(t, "response_item",
                                     {"type": "function_call", "name": "shell"}))
            lines.append(_codex_line(t, "event_msg",
                                     {"type": "agent_message", "message": "ok"}))
        lines.append(_codex_line(t, "event_msg", {"type": "token_count", "info": {
            "total_token_usage": {
                "input_tokens": random.randint(5000, 90000),
                "cached_input_tokens": random.randint(1000, 30000),
                "output_tokens": random.randint(500, 9000),
                "reasoning_output_tokens": random.randint(100, 3000),
                "total_tokens": 0}}}))
        if i == 0:  # one resumed session spanning days (real-world case)
            t2 = t + timedelta(days=6)
            lines.append(_codex_line(t2, "event_msg",
                                     {"type": "user_message", "message": "resume"}))
            lines.append(_codex_line(t2 + timedelta(minutes=4), "event_msg",
                                     {"type": "agent_message", "message": "ok"}))
        day_dir = CODEX_DIR / start.strftime("%Y/%m/%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        fname = f"rollout-{start.strftime('%Y-%m-%dT%H-%M-%S')}-{sid}.jsonl"
        (day_dir / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")


def gen_grok_sessions(now, n=16):
    from urllib.parse import quote
    dirs = {p: GROK_DIR / quote(f"/home/user/projects/{p}", safe="")
            for p in DEMO_PROJECTS_CROSS[:2]}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    marker_written = False
    # BS#1 fixture: force the repeated instruction onto 2 grok sessions,
    # on 2 distinct days (by index, not random).
    _REPEAT_INDICES = {3: 12, 11: 44}  # session index -> days_ago
    for i in range(n):
        if i in _REPEAT_INDICES:
            start = now - timedelta(days=_REPEAT_INDICES[i])
        else:
            start = now - timedelta(days=int(random.triangular(0, 60, 25)))
        sid = mk_sid()
        proj = random.choice(list(dirs))
        lines = []
        forced = i in _REPEAT_INDICES
        for k in range(random.randint(1, 4)):
            if forced and k == 0:
                prompt = DEMO_REPEATED_INSTRUCTION
            else:
                prompt = f"demo grok prompt {k}"
            if not marker_written:
                prompt = '<script>alert("grok")</script> GROK_PRIVATE_MARKER'
                marker_written = True
            lines.append(json.dumps({
                "timestamp": (start + timedelta(minutes=3 * k))
                .strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "session_id": sid, "prompt": prompt,
                "is_bash": random.random() < 0.2}, ensure_ascii=False))
        with open(dirs[proj] / "prompt_history.jsonl", "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


def gen_antigravity_files(now, n=6):
    ANTIGRAVITY_DIR.mkdir(parents=True, exist_ok=True)
    for _ in range(n):
        p = ANTIGRAVITY_DIR / f"{mk_sid()}.pb"
        p.write_bytes(b"\x0a\x00")
        age = now - timedelta(days=int(random.triangular(0, 60, 15)))
        os.utime(p, (age.timestamp(), age.timestamp()))


def _force_repeated_instruction(sessions_meta, sessions_facets, now):
    """BS#1 fixture: overwrite 8 already-generated Claude sessions' prompts
    to DEMO_REPEATED_INSTRUCTION, picked by their position in dict insertion
    order (not random) — a post-pass over the finished random pool, kept
    separate from gen_session()'s random draw the same way the BS#2/BS#4
    fixture pools are built and merged in rather than interleaved into the
    random loop. Each picked session also gets its start_time moved to a
    fixed days_ago so the 8 land in >=4 distinct ISO weeks (spaced 14 days
    apart guarantees this even across month/year boundaries)."""
    # position-in-pool -> days_ago
    picks = {0: 5, 35: 19, 70: 33, 105: 47, 140: 61, 175: 75, 210: 89, 245: 96}
    sids = list(sessions_meta.keys())
    for pos, days_ago in picks.items():
        sid = sids[pos]
        start = (now - timedelta(days=days_ago)).replace(hour=10, minute=0)
        meta = sessions_meta[sid]
        meta["first_prompt"] = DEMO_REPEATED_INSTRUCTION
        meta["start_time"] = start.isoformat().replace("+00:00", "Z")
        facet = sessions_facets.get(sid)
        if facet:
            facet["underlying_goal"] = DEMO_REPEATED_INSTRUCTION[:120]


def main():
    # Generate ~280 sessions over 14 weeks
    now = datetime(2026, 4, 10, tzinfo=timezone.utc)
    sessions_meta = {}
    sessions_facets = {}
    for _ in range(280):
        project = random.choice(PROJECTS)
        # Time distribution: bias to afternoon + occasional night
        days_ago = int(random.triangular(0, 100, 30))
        hour = random.choices(
            range(24),
            weights=[0.1, 0.1, 0.05, 0.05, 0.05, 0.05, 0.2, 0.5, 1.5, 2.5, 3, 3, 2, 3.5, 4, 4, 3, 2, 2, 1.5, 2, 2, 1.5, 0.8],
        )[0]
        minute = random.randint(0, 59)
        start = now - timedelta(days=days_ago, hours=hour, minutes=minute)
        start = start.replace(hour=hour, minute=minute)
        sid = mk_sid()
        meta, facet = gen_session(sid, start, project)
        sessions_meta[sid] = meta
        if facet:
            sessions_facets[sid] = facet

    # BS#1 fixture: force DEMO_REPEATED_INSTRUCTION onto 8 of the sessions
    # just generated (picked by pool position, not random).
    _force_repeated_instruction(sessions_meta, sessions_facets, now)

    # BS#2 fixture: 3 engineered sunk-cost pairs.
    sunk_metas, sunk_facets, sunk_transcripts = gen_sunk_cost_pairs(now)
    sessions_meta.update(sunk_metas)
    sessions_facets.update(sunk_facets)

    # BS#4 fixture: 2 graveyard projects (no facets — activity-only, per brief).
    grave_metas, grave_transcripts = gen_graveyard_projects(now)
    sessions_meta.update(grave_metas)

    # Write meta + facet files
    for sid, m in sessions_meta.items():
        (META_DIR / f"{sid}.json").write_text(json.dumps(m, indent=2))
    for sid, f in sessions_facets.items():
        (FACETS_DIR / f"{sid}.json").write_text(json.dumps(f, indent=2))

    # Write transcripts for most sessions so sampling has coverage
    pick_sids = [sid for sid in sessions_meta.keys()
                if sid not in sunk_transcripts and sid not in grave_transcripts]
    for sid in pick_sids:
        m = sessions_meta[sid]
        f = sessions_facets.get(sid)
        transcript = gen_transcript(sid, m, f)
        proj = m["project_path"].split("/")[-1]
        proj_dir = PROJECTS_DIR / f"-home-user-projects-{proj}"
        proj_dir.mkdir(parents=True, exist_ok=True)
        with open(proj_dir / f"{sid}.jsonl", "w") as fp:
            for rec in transcript:
                fp.write(json.dumps(rec) + "\n")

    # Engineered transcripts (BS#2 sunk-cost pairs, BS#4 graveyard) — written
    # verbatim, not through gen_transcript, so their token_accel and
    # tool_counts stay exactly what the gate assertions expect.
    engineered_count = 0
    for sid, (proj, transcript) in {**sunk_transcripts, **grave_transcripts}.items():
        proj_dir = PROJECTS_DIR / f"-home-user-projects-{proj}"
        proj_dir.mkdir(parents=True, exist_ok=True)
        with open(proj_dir / f"{sid}.jsonl", "w") as fp:
            for rec in transcript:
                fp.write(json.dumps(rec) + "\n")
        engineered_count += 1

    gen_codex_sessions(now)
    gen_grok_sessions(now)
    gen_antigravity_files(now)

    print(f"Generated {len(sessions_meta)} meta, {len(sessions_facets)} facets, "
          f"{len(pick_sids) + engineered_count} transcripts "
          f"({engineered_count} engineered blind-spot fixtures)")
    print(f"Output dirs:\n  {META_DIR}\n  {FACETS_DIR}\n  {PROJECTS_DIR}\n"
          f"  {CODEX_DIR}\n  {GROK_DIR}\n  {ANTIGRAVITY_DIR}")


if __name__ == "__main__":
    main()
