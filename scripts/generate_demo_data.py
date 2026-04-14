"""
Generate synthetic usage-data resembling a real Claude Code heavy user,
then run the full pipeline to produce assets/example-output.html.
No identifiable information; all projects/sids/summaries are fabricated.
"""
import json
import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)

OUT_DIR = Path("/tmp/cc-autopsy-demo")
META_DIR = OUT_DIR / "usage-data/session-meta"
FACETS_DIR = OUT_DIR / "usage-data/facets"
PROJECTS_DIR = OUT_DIR / "projects"
for d in (META_DIR, FACETS_DIR, PROJECTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

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
]

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


def gen_transcript(sid, meta, facet):
    """Minimal .jsonl — enough for sample_sessions.py to parse."""
    lines = []
    start = datetime.fromisoformat(meta["start_time"].replace("Z", "+00:00"))

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
    lines.append({
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": content,
        },
        "timestamp": (start + timedelta(seconds=30)).isoformat(),
    })
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
        lines.append({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Understood, revising."}],
            },
            "timestamp": (start + timedelta(minutes=i + 1, seconds=40)).isoformat(),
        })
    return lines


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

    # Write meta + facet files
    for sid, m in sessions_meta.items():
        (META_DIR / f"{sid}.json").write_text(json.dumps(m, indent=2))
    for sid, f in sessions_facets.items():
        (FACETS_DIR / f"{sid}.json").write_text(json.dumps(f, indent=2))

    # Write transcripts for most sessions so sampling has coverage
    pick_sids = list(sessions_meta.keys())
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

    print(f"Generated {len(sessions_meta)} meta, {len(sessions_facets)} facets, {len(pick_sids)} transcripts")
    print(f"Output dirs:\n  {META_DIR}\n  {FACETS_DIR}\n  {PROJECTS_DIR}")


if __name__ == "__main__":
    main()
