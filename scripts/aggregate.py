"""
cc-user-autopsy Step 1: aggregate.
Reads ~/.claude/usage-data/ and computes every metric + 8 rule-based scores.
Outputs analysis-data.json.
"""
import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DATA_DIR = Path.home() / ".claude/usage-data"
META_DIR = DEFAULT_DATA_DIR / "session-meta"
FACETS_DIR = DEFAULT_DATA_DIR / "facets"

WRITING_GOALS = {
    "writing_refinement", "content_writing", "documentation_update",
    "documentation", "writing", "copy_editing",
}


# Public API pricing in USD per 1M tokens. cache_write uses the 1h ephemeral
# tier (2× base input) as a conservative upper bound — Claude Code doesn't
# expose which TTL its caching layer actually picks, and 1h dominates system
# prompts. Pricing snapshot: 2026-04. Update when anthropic.com/pricing changes.
PRICING = {
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0, "cache_write": 30.0, "cache_read": 1.50},
    "claude-opus-4-6":   {"input": 15.0, "output": 75.0, "cache_write": 30.0, "cache_read": 1.50},
    "claude-opus-4-5":   {"input": 15.0, "output": 75.0, "cache_write": 30.0, "cache_read": 1.50},
    "claude-sonnet-4-6": {"input":  3.0, "output": 15.0, "cache_write":  6.0, "cache_read": 0.30},
    "claude-sonnet-4-5": {"input":  3.0, "output": 15.0, "cache_write":  6.0, "cache_read": 0.30},
    "claude-haiku-4-5":  {"input": 0.80, "output":  4.0, "cache_write":  1.6, "cache_read": 0.08},
}
# Fallback used when model_counts references a model not in PRICING. We
# choose Opus over cheaper tiers so missing-model cases over-report rather
# than silently drop to $0 — a recently-released Opus variant is the most
# likely gap.
_FALLBACK_PRICING = PRICING["claude-opus-4-6"]

_PATTERN_MIN_SAMPLE = 5  # minimum group size to emit a per-dimension pattern contrast sentence


def _normalize_model_id(m: str) -> str:
    """Strip Anthropic date suffixes so 'claude-haiku-4-5-20251001' matches
    the PRICING table key 'claude-haiku-4-5'."""
    import re
    return re.sub(r"-2\d{7}$", "", m)


def compute_api_equivalent_cost(sessions):
    """Estimate what these sessions would have cost at pay-per-use API rates.

    Rationale: Claude Code Max Plan has a flat monthly fee regardless of
    usage, so this number is informational — useful for understanding the
    order of magnitude of work done, not for billing.

    Pricing is blended by assistant-message share across models in
    `model_counts`, since that's the closest proxy we have for the actual
    per-token billing-model mix. (We don't have per-token model attribution
    in transcripts — only per-assistant-message.)
    """
    if not sessions:
        return 0.0

    # Aggregate model-message counts to derive weights.
    model_msgs = Counter()
    for s in sessions:
        for m, c in (s.get("model_counts") or {}).items():
            model_msgs[_normalize_model_id(m)] += c
    total_msgs = sum(model_msgs.values())
    if total_msgs == 0:
        # No model info — assume opus (conservative upper bound).
        weights = {"claude-opus-4-6": 1.0}
    else:
        weights = {m: c / total_msgs for m, c in model_msgs.items()}

    # Blended rate per token-type = Σ weight_m × rate_m
    def blended(token_type):
        total = 0.0
        for m, w in weights.items():
            p = PRICING.get(m, _FALLBACK_PRICING)
            total += w * p[token_type]
        return total

    in_rate = blended("input")
    out_rate = blended("output")
    cw_rate = blended("cache_write")
    cr_rate = blended("cache_read")

    total_in = sum(s.get("input_tokens", 0) or 0 for s in sessions)
    total_out = sum(s.get("output_tokens", 0) or 0 for s in sessions)
    total_cw = sum(s.get("cache_create_tokens", 0) or 0 for s in sessions)
    total_cr = sum(s.get("cache_read_tokens", 0) or 0 for s in sessions)

    return round(
        (total_in / 1e6) * in_rate +
        (total_out / 1e6) * out_rate +
        (total_cw / 1e6) * cw_rate +
        (total_cr / 1e6) * cr_rate,
        2,
    )


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def normalize_project_path(path: str) -> str:
    if not path:
        return "(unknown)"
    normalized = path.replace("\\", "/").rstrip("/")
    return normalized or "(unknown)"


def project_name(path: str) -> str:
    normalized = normalize_project_path(path)
    if normalized == "(unknown)":
        return normalized
    parts = [p for p in normalized.split("/") if p]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1]


def bucket_prompt_len(n: int) -> str:
    if n < 20:
        return "<20"
    if n < 50:
        return "20-50"
    if n < 100:
        return "50-100"
    if n < 300:
        return "100-300"
    return ">=300"


def detect_tz() -> timezone:
    """Pick a tz: TPE if system locale is Asia, else UTC. User can override."""
    try:
        import time
        # heuristic — if local time is currently >= UTC+5 or <= UTC-8, use local
        offset = -time.timezone // 3600
        if time.daylight:
            offset = -time.altzone // 3600
        return timezone(timedelta(hours=offset))
    except Exception:
        return timezone.utc


def load_all(meta_dir: Path, facets_dir: Path):
    metas, facets = {}, {}
    if meta_dir.exists():
        for f in meta_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                metas[d["session_id"]] = d
            except Exception as e:
                print(f"warn: meta load err {f.name}: {e}", file=sys.stderr)
    if facets_dir.exists():
        for f in facets_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                facets[d["session_id"]] = d
            except Exception as e:
                print(f"warn: facet load err {f.name}: {e}", file=sys.stderr)
    return metas, facets


# Fields a redacted row carries on the meta side. Must stay in sync with
# _scripts/dump-redacted-sessions.py in claude-memory-sync.
# Last 4 fields (assistant_message_count, cache_*_tokens, model_counts) are only
# present when the dump was produced from scan_transcripts.py output; legacy
# dumps from session-meta don't have them and their absence is handled by
# .get() defaults.
_REDACTED_META_KEYS = {
    "session_id", "start_time", "project_path", "duration_minutes",
    "input_tokens", "output_tokens", "tool_counts", "user_message_count",
    "git_commits", "git_pushes", "user_interruptions", "tool_errors",
    "uses_task_agent", "uses_mcp", "uses_web_search", "uses_web_fetch",
    "lines_added", "lines_removed", "files_modified",
    "user_response_times", "message_hours",
    "assistant_message_count",
    "cache_creation_input_tokens", "cache_read_input_tokens",
    "model_counts",
    "hit_output_limit",
}
_REDACTED_FACETS_KEYS = {
    "session_id", "outcome", "claude_helpfulness", "session_type",
    "friction_counts", "primary_success", "goal_categories",
}


def load_transcript_rows(path: Path):
    """Read a scan_transcripts.py output jsonl, return meta-shaped dicts.

    Each line is a full (non-redacted) session row. Used when aggregate.py
    is run as --transcript-rows to bypass the partial session-meta dir.
    """
    metas, facets = {}, {}
    if not path.exists():
        return metas, facets
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception as e:
            print(f"warn: transcript-row parse err: {e}", file=sys.stderr)
            continue
        sid = r.get("session_id")
        if not sid:
            continue
        metas[sid] = r
    return metas, facets


def load_redacted(path: Path):
    """Read a sessions-redacted.jsonl file, return (metas, facets, source_by_sid).

    Redacted rows have first_prompt_len but no first_prompt raw text, and no
    brief_summary / friction_detail / underlying_goal text. We fabricate a
    first_prompt placeholder of the correct length so build_sessions'
    len(first_prompt) call matches. All text fields stay empty.
    """
    metas, facets, source_by_sid = {}, {}, {}
    if not path.exists():
        return metas, facets, source_by_sid
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception as e:
            print(f"warn: redacted parse err in {path.name}: {e}", file=sys.stderr)
            continue
        sid = r.get("session_id")
        if not sid:
            continue
        source_by_sid[sid] = r.get("source_machine", "unknown")
        m = {k: r[k] for k in _REDACTED_META_KEYS if k in r}
        # Rehydrate a placeholder first_prompt of the correct length so the
        # downstream len() call produces the right bucket. Content is a string
        # of non-leaky filler chars. Any code reading first_prompt as text will
        # see filler, not real content.
        n = r.get("first_prompt_len", 0)
        m["first_prompt"] = "\u00a0" * n  # NBSP filler — visually empty, len-preserving
        metas[sid] = m
        if r.get("outcome"):
            f = {k: r[k] for k in _REDACTED_FACETS_KEYS if k in r}
            # Empty text fields — explicit so downstream .get() works
            f["brief_summary"] = ""
            f["friction_detail"] = ""
            f["underlying_goal"] = ""
            facets[sid] = f
    return metas, facets, source_by_sid


def build_sessions(metas, facets, tz):
    rows = []
    for sid, m in metas.items():
        f = facets.get(sid, {})
        try:
            start = parse_iso(m.get("start_time", ""))
        except Exception:
            continue
        local = start.astimezone(tz)
        project_path = normalize_project_path(m.get("project_path", ""))
        row = {
            "sid": sid,
            "sid8": sid[:8],
            "project": project_name(project_path),
            "project_key": project_path,
            "project_path": project_path,
            "start": m.get("start_time", ""),
            "week": f"{local.isocalendar().year}-W{local.isocalendar().week:02d}",
            "hour": local.hour,
            "weekday": local.weekday(),
            "duration_min": m.get("duration_minutes", 0),
            "user_msgs": m.get("user_message_count", 0),
            "input_tokens": m.get("input_tokens", 0),
            "output_tokens": m.get("output_tokens", 0),
            "total_tokens": m.get("input_tokens", 0) + m.get("output_tokens", 0),
            "tool_counts": m.get("tool_counts", {}),
            "git_commits": m.get("git_commits", 0),
            "git_pushes": m.get("git_pushes", 0),
            "interrupts": m.get("user_interruptions", 0),
            "tool_errors": m.get("tool_errors", 0),
            "uses_task_agent": m.get("uses_task_agent", False),
            "uses_mcp": m.get("uses_mcp", False),
            "uses_web_search": m.get("uses_web_search", False),
            "uses_web_fetch": m.get("uses_web_fetch", False),
            "lines_added": m.get("lines_added", 0),
            "lines_removed": m.get("lines_removed", 0),
            "files_modified": m.get("files_modified", 0),
            "first_prompt": m.get("first_prompt", ""),
            "first_prompt_len": len(m.get("first_prompt", "")),
            "response_times": m.get("user_response_times", []),
            # Transcript-scanner extras. Session-meta doesn't carry these, so
            # they default to 0/empty for legacy rows.
            "assistant_msgs": m.get("assistant_message_count", 0),
            "cache_create_tokens": m.get("cache_creation_input_tokens", 0),
            "cache_read_tokens": m.get("cache_read_input_tokens", 0),
            "model_counts": m.get("model_counts", {}) or {},
            "hit_output_limit": m.get("hit_output_limit", False),
            # facet fields
            "outcome": f.get("outcome", ""),
            "helpfulness": f.get("claude_helpfulness", ""),
            "session_type": f.get("session_type", ""),
            "friction_counts": f.get("friction_counts", {}) or {},
            "friction_detail": f.get("friction_detail", ""),
            "primary_success": f.get("primary_success", ""),
            "brief_summary": f.get("brief_summary", ""),
            "goal_cats": f.get("goal_categories", {}) or {},
            "underlying_goal": f.get("underlying_goal", ""),
        }
        rows.append(row)
    return rows


def is_good(outcome):
    return outcome in ("fully_achieved", "mostly_achieved")


def _overall_good_rate(rated):
    """Overall good-outcome rate across rated sessions, as a 0-100 float.
    Returns 0.0 when rated is empty — keeps arithmetic contexts safe."""
    if not rated:
        return 0.0
    return 100 * sum(1 for s in rated if is_good(s["outcome"])) / len(rated)


# -------- Scoring rules --------

def score_d1_delegation(sessions, rated):
    n = len(sessions)
    if n == 0:
        return {"score": None, "reason": "no sessions", "pattern": None}
    ta_count = sum(1 for s in sessions if s["uses_task_agent"])
    ta_rate = 100 * ta_count / n
    ta_rated = [s for s in rated if s["uses_task_agent"]]
    good_rate_ta = (
        100 * sum(1 for s in ta_rated if is_good(s["outcome"])) / len(ta_rated)
        if ta_rated else 0
    )
    if ta_rate >= 70 and good_rate_ta >= 75:
        score = 10
    elif ta_rate >= 60 and good_rate_ta >= 70:
        score = 9
    elif ta_rate >= 45 and good_rate_ta >= 65:
        score = 8
    elif ta_rate >= 30:
        score = 7
    elif ta_rate >= 15:
        score = 6
    elif ta_rate >= 5:
        score = 5
    elif ta_rate > 0:
        score = 3
    else:
        score = 1
    # Pattern string (descriptive contrast). None when TA sample < _PATTERN_MIN_SAMPLE.
    if len(ta_rated) >= _PATTERN_MIN_SAMPLE:
        pattern = (
            f"Sessions that used Task agent had a {good_rate_ta:.0f}% "
            f"good-outcome rate, versus {_overall_good_rate(rated):.0f}% overall."
        )
    else:
        pattern = None
    return {
        "score": score,
        "metric_ta_rate_pct": round(ta_rate, 1),
        "metric_good_rate_with_ta_pct": round(good_rate_ta, 1),
        "explanation": f"{ta_rate:.0f}% of sessions used Task agent; good-outcome rate with Task agent was {good_rate_ta:.0f}%.",
        "pattern": pattern,
    }


def score_d2_rootcause(sessions, rated, facets_coverage):
    if facets_coverage < 30:
        return {"score": None, "reason": "insufficient facet coverage", "pattern": None}
    iter_buggy = [
        s for s in rated
        if s["session_type"] == "iterative_refinement"
        and s["friction_counts"].get("buggy_code", 0) > 0
    ]
    if not rated:
        return {"score": None, "reason": "no rated sessions", "pattern": None}
    R = 100 * len(iter_buggy) / len(rated)
    thresholds = [(2, 10), (4, 9), (7, 8), (10, 7), (15, 6), (20, 5), (25, 4)]
    score = 3
    for thr, sc in thresholds:
        if R <= thr:
            score = sc
            break
    iter_sessions = [s for s in rated if s["session_type"] == "iterative_refinement"]
    non_iter_sessions = [s for s in rated if s["session_type"] != "iterative_refinement"]
    pattern = None
    if len(non_iter_sessions) >= _PATTERN_MIN_SAMPLE and len(iter_sessions) >= _PATTERN_MIN_SAMPLE:
        non_iter_good = 100 * sum(1 for s in non_iter_sessions if is_good(s["outcome"])) / len(non_iter_sessions)
        iter_good = 100 * sum(1 for s in iter_sessions if is_good(s["outcome"])) / len(iter_sessions)
        pattern = (
            f"Sessions without iterative_refinement friction reached good outcomes "
            f"{non_iter_good:.0f}% of the time, versus {iter_good:.0f}% for "
            f"iterative_refinement sessions."
        )
    return {
        "score": score,
        "metric_iter_buggy_pct": round(R, 1),
        "metric_iter_buggy_count": len(iter_buggy),
        "explanation": f"{len(iter_buggy)} sessions ({R:.0f}%) were iterative_refinement with buggy_code friction — a marker for symptom-level patching.",
        "pattern": pattern,
    }


def score_d3_prompt_quality(sessions):
    if not sessions:
        return {"score": None}
    plen_ge_100 = sum(1 for s in sessions if s["first_prompt_len"] >= 100)
    plen_lt_20 = sum(1 for s in sessions if s["first_prompt_len"] < 20)
    rate_100 = 100 * plen_ge_100 / len(sessions)
    rate_lt_20 = 100 * plen_lt_20 / len(sessions)

    buckets = defaultdict(list)
    for s in sessions:
        if s["git_commits"] > 0:
            buckets[bucket_prompt_len(s["first_prompt_len"])].append(
                s["total_tokens"] / s["git_commits"]
            )
    bucket_median = {
        b: (statistics.median(v) if v else None) for b, v in buckets.items()
    }
    best_bucket = min(
        (k for k, v in bucket_median.items() if v is not None),
        key=lambda k: bucket_median[k],
        default=None,
    )

    if rate_100 >= 60 and best_bucket == "100-300":
        score = 10
    elif rate_100 >= 40:
        score = 8
    elif rate_100 >= 25:
        score = 7
    elif rate_lt_20 > 50:
        score = 3
    else:
        score = 5
    return {
        "score": score,
        "metric_pct_prompts_ge_100_chars": round(rate_100, 1),
        "metric_pct_prompts_lt_20_chars": round(rate_lt_20, 1),
        "metric_bucket_median_tokens_per_commit": {
            k: (round(v, 0) if v else None) for k, v in bucket_median.items()
        },
        "metric_most_efficient_bucket": best_bucket,
        "explanation": f"{rate_100:.0f}% of sessions used prompts ≥ 100 chars. Most efficient prompt-length bucket for tokens/commit: {best_bucket}.",
    }


def score_d4_context_mgmt(sessions):
    if not sessions:
        return {"score": None}
    otl = [
        s for s in sessions
        if any(k in s["friction_counts"] for k in
               ("output_token_limit_exceeded", "output_token_limit"))
    ]
    long_s = [s for s in sessions if s["duration_min"] > 60]
    long_intr = [s for s in long_s if s["interrupts"] > 0]
    long_intr_rate = (100 * len(long_intr) / len(long_s)) if long_s else 0
    over20 = [s for s in sessions if s["duration_min"] > 20]
    over20_zero_commit = [s for s in over20 if s["git_commits"] == 0]
    enc_pct = (100 * len(over20_zero_commit) / len(over20)) if over20 else 0

    # per-project otl
    proj_otl = Counter(s["project_key"] for s in otl)
    max_proj_otl = max(proj_otl.values()) if proj_otl else 0

    score = 10
    if len(otl) > 2:
        score -= 1
    if len(otl) > 5:
        score -= 1
    if long_intr_rate > 25:
        score -= 1
    if enc_pct > 15:
        score -= 1
    if enc_pct > 30:
        score -= 1
    if max_proj_otl > 5:
        score -= 1
    score = max(score, 3)

    return {
        "score": score,
        "metric_output_token_limit_sessions": len(otl),
        "metric_long_session_interrupt_rate_pct": round(long_intr_rate, 1),
        "metric_effort_no_commit_pct": round(enc_pct, 1),
        "metric_max_otl_in_one_project": max_proj_otl,
        "explanation": f"{len(otl)} sessions hit output-token-limit. {enc_pct:.0f}% of >20min sessions had 0 commits. Long-session interrupt rate: {long_intr_rate:.0f}%.",
    }


def score_d5_interrupt(rated):
    interrupted = [s for s in rated if s["interrupts"] > 0]
    if len(interrupted) < 5:
        return {"score": None, "reason": "fewer than 5 interrupted rated sessions"}
    good = [s for s in interrupted if is_good(s["outcome"])]
    P = 100 * len(good) / len(interrupted)
    thresholds = [(60, 10), (50, 9), (40, 8), (30, 7), (20, 5)]
    score = 3
    for thr, sc in thresholds:
        if P >= thr:
            score = sc
            break
    return {
        "score": score,
        "metric_interrupt_recovery_pct": round(P, 1),
        "metric_interrupted_sessions": len(interrupted),
        "explanation": f"{P:.0f}% of interrupted sessions still reached good outcome ({len(good)}/{len(interrupted)}).",
    }


def score_d6_tool_breadth(sessions):
    if not sessions:
        return {"score": None}
    mcp_rate = 100 * sum(1 for s in sessions if s["uses_mcp"]) / len(sessions)
    tool_totals = Counter()
    for s in sessions:
        for t, c in s["tool_counts"].items():
            tool_totals[t] += c
    total_calls = sum(tool_totals.values())
    top3 = tool_totals["Bash"] + tool_totals["Read"] + tool_totals["Edit"]
    top3_share = 100 * top3 / total_calls if total_calls else 0

    if mcp_rate >= 30 and top3_share <= 40:
        score = 10
    elif mcp_rate >= 15 and top3_share <= 55:
        score = 8
    elif mcp_rate >= 10:
        score = 7
    elif mcp_rate >= 5:
        score = 6
    elif mcp_rate >= 2:
        score = 5
    else:
        score = 4
    return {
        "score": score,
        "metric_mcp_rate_pct": round(mcp_rate, 1),
        "metric_top3_share_pct": round(top3_share, 1),
        "metric_top_tools": dict(tool_totals.most_common(10)),
        "explanation": f"{mcp_rate:.0f}% of sessions used any MCP tool; top-3 tools (Bash/Read/Edit) consume {top3_share:.0f}% of all calls.",
    }


def score_d7_writing(rated):
    writing = [
        s for s in rated
        if any(g in WRITING_GOALS for g in s.get("goal_cats", {}).keys())
    ]
    if len(writing) < 5:
        return {"score": None, "reason": "fewer than 5 writing sessions"}
    misu = sum(s["friction_counts"].get("misunderstood_request", 0) for s in writing)
    W = misu / len(writing)
    thresholds = [(0.1, 10), (0.3, 8), (0.6, 7), (1.0, 5)]
    score = 3
    for thr, sc in thresholds:
        if W <= thr:
            score = sc
            break
    return {
        "score": score,
        "metric_misunderstood_per_writing_session": round(W, 2),
        "metric_writing_sessions": len(writing),
        "explanation": f"Across {len(writing)} writing-related sessions, avg misunderstood_request per session is {W:.2f}.",
    }


def score_d8_time_mgmt(sessions, rated):
    # Use rated sessions for friction, but all sessions to count session volume
    if len(rated) < 20:
        return {"score": None, "reason": "<20 rated sessions"}
    by_hour = defaultdict(lambda: {"n": 0, "fric": 0})
    for s in rated:
        h = s["hour"]
        by_hour[h]["n"] += 1
        by_hour[h]["fric"] += sum(s["friction_counts"].values())
    # only hours with >= 5 sessions
    rates = {
        h: d["fric"] / d["n"] for h, d in by_hour.items() if d["n"] >= 5
    }
    if len(rates) < 3:
        return {"score": None, "reason": "<3 hours with enough data"}
    hi = max(rates.values())
    lo = min(rates.values()) or 0.001
    ratio = hi / lo
    if ratio <= 1.5:
        score = 10
    elif ratio <= 2.0:
        score = 8
    elif ratio <= 2.5:
        score = 7
    elif ratio <= 3.5:
        score = 5
    else:
        score = 3
    worst_hour = max(rates, key=rates.get)
    best_hour = min(rates, key=rates.get)
    return {
        "score": score,
        "metric_friction_ratio_hi_lo": round(ratio, 2),
        "metric_worst_hour": {"hour": worst_hour, "friction_per_session": round(rates[worst_hour], 2)},
        "metric_best_hour": {"hour": best_hour, "friction_per_session": round(rates[best_hour], 2)},
        "explanation": f"Worst hour ({worst_hour:02d}:00) has {ratio:.1f}x the friction rate of best hour ({best_hour:02d}:00).",
    }


def compute_scores(sessions, rated, facets_coverage):
    scores = {}
    scores["D1_delegation"] = score_d1_delegation(sessions, rated)
    scores["D2_root_cause"] = score_d2_rootcause(sessions, rated, facets_coverage)
    scores["D3_prompt_quality"] = score_d3_prompt_quality(sessions)
    scores["D4_context_mgmt"] = score_d4_context_mgmt(sessions)
    scores["D5_interrupt_judgment"] = score_d5_interrupt(rated)
    scores["D6_tool_breadth"] = score_d6_tool_breadth(sessions)
    scores["D7_writing_consistency"] = score_d7_writing(rated)
    scores["D8_time_mgmt"] = score_d8_time_mgmt(sessions, rated)
    # overall
    valid = [v["score"] for v in scores.values() if v.get("score") is not None]
    total_dims = len(scores)
    scores["_overall"] = {
        "avg": round(statistics.mean(valid), 2) if valid else None,
        "dimensions_scored": len(valid),
        "dimensions_total": total_dims,
    }
    return scores


def compute_activity(sessions):
    """Desktop-style activity panel.

    Derivable from any session row: session_count + message totals + active
    days + streaks. cache_* and model_counts come from transcript-scanner
    output only; legacy session-meta rows contribute 0 to these.
    """
    if not sessions:
        return {
            "total_sessions": 0, "total_messages": 0, "active_days": 0,
            "current_streak": 0, "longest_streak": 0,
            "cache_creation_tokens": 0, "cache_read_tokens": 0,
            "models": {}, "favorite_model": None,
            "api_equivalent_cost_usd": 0.0,
        }

    total_msgs = sum((s.get("user_msgs", 0) or 0) + (s.get("assistant_msgs", 0) or 0)
                     for s in sessions)

    # Active days = distinct YYYY-MM-DD across all session start_times
    dates = set()
    for s in sessions:
        start = s.get("start", "")
        if start and len(start) >= 10:
            dates.add(start[:10])

    # Streak: sort unique dates, walk them; longest_streak = max consecutive run.
    # current_streak is measured from today backward — but for deterministic
    # test behaviour we compute it as: trailing consecutive run from the most
    # recent active date. If today isn't in the set and the gap to the latest
    # date is > 1 day, current_streak = 0.
    longest_streak = 0
    current_streak = 0
    if dates:
        sorted_dates = sorted(dates)
        run = 1
        longest_streak = 1
        for i in range(1, len(sorted_dates)):
            prev = datetime.fromisoformat(sorted_dates[i - 1])
            cur = datetime.fromisoformat(sorted_dates[i])
            if (cur - prev).days == 1:
                run += 1
                longest_streak = max(longest_streak, run)
            else:
                run = 1
        # Current streak: walk backward from the latest date
        latest = datetime.fromisoformat(sorted_dates[-1])
        today = datetime.utcnow().date()
        days_since_latest = (today - latest.date()).days
        if days_since_latest <= 1:
            # Latest date is today or yesterday — count trailing run
            current_streak = 1
            for i in range(len(sorted_dates) - 2, -1, -1):
                prev = datetime.fromisoformat(sorted_dates[i])
                cur = datetime.fromisoformat(sorted_dates[i + 1])
                if (cur - prev).days == 1:
                    current_streak += 1
                else:
                    break
        else:
            current_streak = 0

    # Cache + model aggregation
    cache_create = sum(s.get("cache_create_tokens", 0) or 0 for s in sessions)
    cache_read = sum(s.get("cache_read_tokens", 0) or 0 for s in sessions)
    models = Counter()
    for s in sessions:
        for m, c in (s.get("model_counts", {}) or {}).items():
            models[m] += c

    return {
        "total_sessions": len(sessions),
        "total_messages": total_msgs,
        "active_days": len(dates),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "cache_creation_tokens": cache_create,
        "cache_read_tokens": cache_read,
        "models": dict(models),
        "favorite_model": models.most_common(1)[0][0] if models else None,
        "api_equivalent_cost_usd": compute_api_equivalent_cost(sessions),
    }


def compute_aggregates(sessions, rated, facets_coverage):
    result = {}
    result["activity"] = compute_activity(sessions)

    # tokens
    toks = [s["total_tokens"] for s in sessions if s["total_tokens"]]
    result["tokens"] = {
        "total": sum(toks),
        "median": statistics.median(toks) if toks else 0,
        "p90": sorted(toks)[int(len(toks) * 0.9)] if toks else 0,
        "max": max(toks) if toks else 0,
        "dist_buckets": {
            "<10k": len([t for t in toks if t < 10000]),
            "10-50k": len([t for t in toks if 10000 <= t < 50000]),
            "50-200k": len([t for t in toks if 50000 <= t < 200000]),
            "200k-1M": len([t for t in toks if 200000 <= t < 1000000]),
            ">=1M": len([t for t in toks if t >= 1000000]),
        },
    }

    # tools
    tool_totals = Counter()
    for s in sessions:
        for t, c in s["tool_counts"].items():
            tool_totals[t] += c
    result["tools"] = {
        "totals": dict(tool_totals.most_common()),
        "sessions_using_task_agent": sum(1 for s in sessions if s["uses_task_agent"]),
        "sessions_using_mcp": sum(1 for s in sessions if s["uses_mcp"]),
        "sessions_using_web_search": sum(1 for s in sessions if s["uses_web_search"]),
        "sessions_using_web_fetch": sum(1 for s in sessions if s["uses_web_fetch"]),
    }

    # heatmap
    heat = defaultdict(int)
    for s in sessions:
        heat[(s["weekday"], s["hour"])] += 1
    result["heatmap"] = {f"{wd},{hr}": c for (wd, hr), c in heat.items()}

    # projects
    proj_detail = defaultdict(lambda: {
        "label": "(unknown)",
        "path": "(unknown)",
        "sessions": 0,
        "tokens": 0,
        "commits": 0,
        "friction": 0,
        "duration_min": 0,
        "outcomes": Counter(),
    })
    for s in sessions:
        p = s["project_key"]
        proj_detail[p]["label"] = s["project"]
        proj_detail[p]["path"] = s["project_path"]
        proj_detail[p]["sessions"] += 1
        proj_detail[p]["tokens"] += s["total_tokens"]
        proj_detail[p]["commits"] += s["git_commits"]
        proj_detail[p]["friction"] += sum(s["friction_counts"].values())
        proj_detail[p]["duration_min"] += s["duration_min"]
        if s["outcome"]:
            proj_detail[p]["outcomes"][s["outcome"]] += 1
    result["projects"] = {
        p: {
            "label": d["label"],
            "path": d["path"],
            "sessions": d["sessions"],
            "tokens": d["tokens"],
            "commits": d["commits"],
            "friction": d["friction"],
            "duration_min": d["duration_min"],
            "outcomes": dict(d["outcomes"]),
        }
        for p, d in sorted(proj_detail.items(), key=lambda x: -x[1]["sessions"])
    }

    # outcomes, friction
    result["outcomes"] = dict(Counter(s["outcome"] for s in rated))
    fric_tot = Counter()
    fric_by_out = defaultdict(Counter)
    for s in rated:
        for f, n in s["friction_counts"].items():
            fric_tot[f] += n
            fric_by_out[s["outcome"]][f] += n
    result["friction"] = {
        "totals": dict(fric_tot.most_common()),
        "by_outcome": {o: dict(c) for o, c in fric_by_out.items()},
    }

    # interrupts
    interr = [s for s in sessions if s["interrupts"] > 0]
    result["interrupts"] = {
        "sessions_with_interrupt": len(interr),
        "total_interrupts": sum(s["interrupts"] for s in sessions),
        "interrupt_rate_pct": round(100 * len(interr) / len(sessions), 1) if sessions else 0,
    }

    # prompt len vs outcome
    plen_o = defaultdict(Counter)
    for s in rated:
        plen_o[bucket_prompt_len(s["first_prompt_len"])][s["outcome"]] += 1
    result["prompt_len_vs_outcome"] = {k: dict(v) for k, v in plen_o.items()}

    # weekly
    weekly = defaultdict(lambda: {
        "sessions": 0, "tokens": 0, "commits": 0, "friction": 0,
        "interrupts": 0, "prompt_lens": [], "uses_task_agent": 0,
        "duration_min": 0, "outcomes": Counter(),
    })
    for s in sessions:
        w = s["week"]
        weekly[w]["sessions"] += 1
        weekly[w]["tokens"] += s["total_tokens"]
        weekly[w]["commits"] += s["git_commits"]
        weekly[w]["friction"] += sum(s["friction_counts"].values())
        weekly[w]["interrupts"] += s["interrupts"]
        weekly[w]["prompt_lens"].append(s["first_prompt_len"])
        if s["uses_task_agent"]:
            weekly[w]["uses_task_agent"] += 1
        weekly[w]["duration_min"] += s["duration_min"]
        if s["outcome"]:
            weekly[w]["outcomes"][s["outcome"]] += 1
    wk = []
    for w, d in sorted(weekly.items()):
        total_oc = sum(d["outcomes"].values())
        good = d["outcomes"].get("fully_achieved", 0) + d["outcomes"].get("mostly_achieved", 0)
        wk.append({
            "week": w,
            "sessions": d["sessions"],
            "tokens": d["tokens"],
            "commits": d["commits"],
            "friction": d["friction"],
            "interrupts": d["interrupts"],
            "avg_prompt_len": round(statistics.mean(d["prompt_lens"]) if d["prompt_lens"] else 0, 1),
            "uses_task_agent": d["uses_task_agent"],
            "duration_min": d["duration_min"],
            "good_rate_pct": round(100 * good / total_oc, 1) if total_oc else 0,
            "rated": total_oc,
            "outcomes": dict(d["outcomes"]),
        })
    result["weekly"] = wk

    def top_by(key, n=10, reverse=True):
        rows = sorted(sessions, key=lambda x: x.get(key, 0), reverse=reverse)
        return [{
            "sid": r["sid"],
            "sid8": r["sid8"],
            "project": r["project"],
            "project_key": r["project_key"],
            "value": r.get(key), "outcome": r["outcome"],
            "brief_summary": r["brief_summary"][:150] if r["brief_summary"] else "",
        } for r in rows[:n]]

    highest_fric = sorted(
        [s for s in rated if s["friction_counts"]],
        key=lambda x: -sum(x["friction_counts"].values()))[:15]
    result["extremes"] = {
        "top_tokens": top_by("total_tokens"),
        "top_interrupts": top_by("interrupts"),
        "top_duration": top_by("duration_min"),
        "highest_friction": [{
            "sid": s["sid"], "sid8": s["sid8"], "project": s["project"], "project_key": s["project_key"],
            "outcome": s["outcome"], "friction_counts": s["friction_counts"],
            "brief_summary": s["brief_summary"][:200],
        } for s in highest_fric],
        "outcome_not_achieved": [{
            "sid": s["sid"], "sid8": s["sid8"], "project": s["project"], "project_key": s["project_key"],
            "outcome": s["outcome"], "friction_counts": s["friction_counts"],
            "brief_summary": s["brief_summary"][:200],
        } for s in rated if s["outcome"] == "not_achieved"][:10],
    }

    # session types & helpfulness
    result["session_types"] = dict(Counter(s["session_type"] for s in rated if s["session_type"]))
    result["helpfulness"] = dict(Counter(s["helpfulness"] for s in rated if s["helpfulness"]))

    # response time stats
    all_rt = []
    for s in sessions:
        all_rt.extend(s["response_times"])
    result["response_times"] = {
        "median_seconds": round(statistics.median(all_rt), 1) if all_rt else 0,
        "mean_seconds": round(statistics.mean(all_rt), 1) if all_rt else 0,
        "p90_seconds": round(sorted(all_rt)[int(len(all_rt) * 0.9)], 1) if all_rt else 0,
        "sample_count": len(all_rt),
    }

    # goal cats
    gc = Counter()
    for s in rated:
        for g, n in s["goal_cats"].items():
            gc[g] += n
    result["goal_categories"] = dict(gc.most_common(25))

    # efficiency
    commits_sessions = [s for s in sessions if s["git_commits"] > 0]
    total_duration_hr = sum(s["duration_min"] for s in sessions) / 60
    result["efficiency"] = {
        "tokens_per_commit_median": round(statistics.median(
            [s["total_tokens"] / s["git_commits"] for s in commits_sessions]
        ), 0) if commits_sessions else 0,
        "sessions_with_commits": len(commits_sessions),
        "commits_per_hour": round(sum(s["git_commits"] for s in sessions) / total_duration_hr, 2) if total_duration_hr > 0 else 0,
        "total_duration_hr": round(total_duration_hr, 1),
    }

    # -------- SHIPPED ARTIFACTS (HR-facing) --------
    # Group rated "fully_achieved + essential/very_helpful" sessions by project,
    # pick the richest brief_summary per project (longest one), cap top 8.
    shipped_by_proj = defaultdict(list)
    for s in rated:
        if s["outcome"] == "fully_achieved" and s["helpfulness"] in ("essential", "very_helpful"):
            if s["brief_summary"]:
                shipped_by_proj[s["project_key"]].append(s)
    shipped = []
    for proj, sess_list in shipped_by_proj.items():
        # pick the session with the longest summary (most context) per project
        best = max(sess_list, key=lambda x: len(x["brief_summary"]))
        proj_stats = proj_detail[proj]
        shipped.append({
            "project": proj_stats["label"],
            "project_path": proj_stats["path"],
            "summary": best["brief_summary"],
            "sid8": best["sid8"],
            "total_tokens": best["total_tokens"],
            "project_sessions": proj_stats["sessions"],
            "project_commits": proj_stats["commits"],
            "project_duration_min": proj_stats["duration_min"],
        })
    # sort by duration contribution (proxy for project importance)
    shipped.sort(key=lambda x: -x["project_duration_min"])
    result["shipped_artifacts"] = shipped[:8]

    # -------- GROWTH CURVE (HR-facing) --------
    # For each week, compute a composite skill score combining:
    #   interrupt_recovery_rate, good_rate, task_agent_adoption,
    #   inverse friction rate (1 - friction_per_session / max).
    # Need at least 4 weeks of rated data.
    growth = []
    max_fric_per_session = 0
    # first pass: find max friction/session
    for w in result["weekly"]:
        if w["sessions"] > 0:
            f = w["friction"] / w["sessions"]
            max_fric_per_session = max(max_fric_per_session, f)
    for w in result["weekly"]:
        if w["sessions"] == 0:
            continue
        ta_rate_w = 100 * w["uses_task_agent"] / w["sessions"]
        good_rate_w = w["good_rate_pct"]
        fric_ratio = (w["friction"] / w["sessions"]) / max_fric_per_session if max_fric_per_session else 0
        fric_score = 100 * (1 - fric_ratio)
        # composite: good rate * 0.4, ta_rate * 0.3, fric_score * 0.3
        composite = round(0.4 * good_rate_w + 0.3 * ta_rate_w + 0.3 * fric_score, 1)
        growth.append({
            "week": w["week"],
            "composite_score": composite,
            "ta_rate": round(ta_rate_w, 1),
            "good_rate": good_rate_w,
            "fric_score": round(fric_score, 1),
            "rated_sessions": w["rated"],
        })
    result["growth_curve"] = growth

    # -------- PROFILE SUMMARY (HR-facing headline) --------
    # Auto-derived 2-sentence self-description for the top of the page.
    ta_pct = 100 * sum(1 for s in sessions if s["uses_task_agent"]) / len(sessions) if sessions else 0
    mcp_pct = 100 * sum(1 for s in sessions if s["uses_mcp"]) / len(sessions) if sessions else 0
    project_count = len([p for p, d in proj_detail.items() if d["sessions"] >= 3])
    top_project = max(proj_detail.items(), key=lambda x: x[1]["sessions"]) if proj_detail else None
    top_project_share = 100 * top_project[1]["sessions"] / len(sessions) if top_project and sessions else 0

    # Pick a specialty tag based on goal_categories
    gc_top3 = list(gc.most_common(3))
    specialty_keywords = {
        "bug_fix": "debugging", "debugging": "debugging",
        "feature_implementation": "feature engineering",
        "feature_addition": "feature engineering",
        "deployment": "deployment / DevOps",
        "content_writing": "technical writing",
        "writing_refinement": "technical writing",
        "documentation_update": "documentation",
        "ui_refinement": "UI / design-adjacent work",
        "code_review": "code review",
        "memory_update": "knowledge-base curation",
    }
    specialty = []
    seen_kw = set()
    for cat, _ in gc_top3:
        kw = specialty_keywords.get(cat)
        if kw and kw not in seen_kw:
            specialty.append(kw)
            seen_kw.add(kw)
    specialty_str = " + ".join(specialty[:2]) if specialty else "multi-domain engineering"

    # decile-ish descriptor for scale
    if total_duration_hr >= 500:
        scale_tier = "heavy"
    elif total_duration_hr >= 200:
        scale_tier = "active"
    elif total_duration_hr >= 60:
        scale_tier = "moderate"
    else:
        scale_tier = "early-stage"

    result["profile_summary"] = {
        "scale_tier": scale_tier,
        "total_duration_hr": round(total_duration_hr, 1),
        "total_sessions": len(sessions),
        "project_count_active": project_count,
        "top_project_share_pct": round(top_project_share, 1),
        "top_project_label": top_project[1]["label"] if top_project else "(unknown)",
        "ta_pct": round(ta_pct, 1),
        "mcp_pct": round(mcp_pct, 1),
        "specialty": specialty_str,
        "date_span_days": (parse_iso(max(s["start"] for s in sessions))
                           - parse_iso(min(s["start"] for s in sessions))).days,
    }

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR),
                        help="Path to ~/.claude/usage-data (session-meta mode). "
                             "Ignored when --transcript-rows is set.")
    parser.add_argument("--transcript-rows", default=None,
                        help="Path to scan_transcripts.py output jsonl. When set, "
                             "this is the primary session source and --data-dir is "
                             "only used for facets.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--tz", default="auto",
                        help="timezone offset hours (e.g. 8) or 'auto' or 'utc'")
    parser.add_argument("--extra-redacted", action="append", default=[],
                        help="Path to sessions-redacted.jsonl from another machine. "
                             "Can be given multiple times. Each row augments the session pool. "
                             "Local sessions take precedence on session_id collisions.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser()
    meta_dir = data_dir / "session-meta"
    facets_dir = data_dir / "facets"
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.tz == "auto":
        tz = detect_tz()
    elif args.tz == "utc":
        tz = timezone.utc
    else:
        try:
            tz = timezone(timedelta(hours=float(args.tz)))
        except Exception:
            tz = timezone.utc

    # Two universes:
    #  - scoring_metas: the rich, LLM-labeled subset used for 8-dimension scores
    #  - activity_metas: the full session universe (transcript-scan output)
    # When --transcript-rows is set, activity_metas uses it; scoring_metas
    # prefers session-meta's richer data (uses_task_agent etc.) intersected
    # with transcript rows.
    if args.transcript_rows:
        tr_path = Path(args.transcript_rows).expanduser()
        activity_metas, _ = load_transcript_rows(tr_path)
        _, facets = load_all(Path("/dev/null"), facets_dir)
        meta_raw, _ = load_all(meta_dir, Path("/dev/null"))
        # Scoring pool = sessions with session-meta (which carries the LLM
        # uses_task_agent flag plus accurate user_msg/tool counts). Transcripts
        # without session-meta are quick one-shot sessions that would distort
        # scores if included. They still power the full activity panel.
        # Meta-only sessions (transcript cleaned up) are also kept.
        scoring_metas = {}
        for sid, m in meta_raw.items():
            if sid in activity_metas:
                # Merge: scanner provides extras (cache tokens, models),
                # session-meta provides the definitional flags + accurate counts
                merged = dict(activity_metas[sid])
                for k in ("uses_task_agent", "uses_mcp", "uses_web_search",
                          "uses_web_fetch", "user_interruptions", "tool_errors",
                          "user_message_count", "assistant_message_count",
                          "tool_counts", "duration_minutes",
                          "lines_added", "lines_removed", "files_modified",
                          "first_prompt"):
                    if m.get(k) is not None:
                        merged[k] = m[k]
                scoring_metas[sid] = merged
            else:
                scoring_metas[sid] = m
        print(f"loaded {len(activity_metas)} transcript rows, {len(facets)} facets, "
              f"{len(meta_raw)} session-meta → {len(scoring_metas)} scoring pool",
              file=sys.stderr)
        metas = scoring_metas
    else:
        metas, facets = load_all(meta_dir, facets_dir)
        activity_metas = None  # fall back to metas in compute_activity
        print(f"loaded {len(metas)} session-meta, {len(facets)} facets", file=sys.stderr)
    source_by_sid = {sid: "local" for sid in metas}

    # Merge each --extra-redacted jsonl. Local wins on sid collision.
    # These rows also augment activity_metas when they carry the scanner extras
    # (cache tokens, model_counts) — that's the point of the extended schema.
    for p in args.extra_redacted:
        rp = Path(p).expanduser()
        rm, rf, rsrc = load_redacted(rp)
        added = 0
        for sid, m in rm.items():
            if sid not in metas:
                metas[sid] = m
                source_by_sid[sid] = rsrc.get(sid, "unknown")
                added += 1
        for sid, f in rf.items():
            if sid not in facets:
                facets[sid] = f
        # Also grow activity universe with these redacted rows so cache
        # tokens + model breakdown + active_days reflect all machines, not
        # just the local transcript scan.
        if activity_metas is not None:
            activity_added = 0
            for sid, m in rm.items():
                if sid not in activity_metas:
                    activity_metas[sid] = m
                    activity_added += 1
            print(f"merged {added} sessions (+{activity_added} into activity pool) "
                  f"from {rp.name}", file=sys.stderr)
        else:
            print(f"merged {added} sessions from {rp.name} "
                  f"({len(rm) - added} skipped as duplicates)", file=sys.stderr)

    if len(metas) == 0:
        # If transcript-rows supplied data but no meta, fall back to using
        # activity_metas (full transcript universe) as the scoring pool.
        # Scores will be thin (no LLM flags) but it's better than refusing.
        if args.transcript_rows and activity_metas:
            metas = activity_metas
            source_by_sid = {sid: "local" for sid in metas}
        else:
            print("error: no session-meta files found and no --extra-redacted data. Use Claude Code first.", file=sys.stderr)
            sys.exit(2)

    sessions = build_sessions(metas, facets, tz)
    rated = [s for s in sessions if s["outcome"]]
    facets_coverage = 100 * len(rated) / len(sessions) if sessions else 0

    meta = {
        "total_sessions": len(sessions),
        "sessions_with_facets": len(rated),
        "facets_coverage_pct": round(facets_coverage, 1),
        "date_range": {
            "first": min(s["start"] for s in sessions),
            "last": max(s["start"] for s in sessions),
        },
        "tz_offset_hours": tz.utcoffset(datetime.now()).total_seconds() / 3600,
        "data_thin_warning": len(rated) < 20,
    }
    aggregates = compute_aggregates(sessions, rated, facets_coverage)
    # When transcript-rows mode supplied a wider universe, recompute the
    # activity panel using the full pool rather than just the scoring subset.
    if activity_metas is not None:
        activity_sessions = build_sessions(activity_metas, {}, tz)
        aggregates["activity"] = compute_activity(activity_sessions)
        # Expose both scopes so the HTML can choose which to surface
        aggregates["activity"]["scoring_pool_sessions"] = len(sessions)
        aggregates["activity"]["full_pool_sessions"] = len(activity_sessions)
    scores = compute_scores(sessions, rated, facets_coverage)

    # _sessions is the per-session row schema consumed by sample_sessions.py
    # and build_html.py. Keys listed below are the contract — removing or
    # renaming one will silently break downstream scripts.
    final = {
        "meta": meta,
        "aggregates": aggregates,
        "scores": scores,
        "_sessions": [{
            "sid": s["sid"],
            "sid8": s["sid8"],
            "project": s["project"],
            "project_key": s["project_key"],
            "project_path": s["project_path"],
            "start": s["start"],
            "week": s["week"],
            "duration_min": s["duration_min"], "total_tokens": s["total_tokens"],
            "interrupts": s["interrupts"], "git_commits": s["git_commits"],
            "outcome": s["outcome"], "session_type": s["session_type"],
            "helpfulness": s["helpfulness"], "friction_counts": s["friction_counts"],
            "primary_success": s["primary_success"],
            "first_prompt": s["first_prompt"][:500],
            "first_prompt_len": s["first_prompt_len"],
            "uses_task_agent": s["uses_task_agent"],
            "goal_cats": s["goal_cats"],
            "brief_summary": s["brief_summary"],
            "friction_detail": s["friction_detail"],
            "source_machine": source_by_sid.get(s["sid"], "local"),
        } for s in sessions],
    }

    out.write_text(json.dumps(final, ensure_ascii=False, indent=2))
    print(f"wrote {out} ({out.stat().st_size} bytes)", file=sys.stderr)
    print(f"sessions={meta['total_sessions']} facets_coverage={meta['facets_coverage_pct']}%",
          file=sys.stderr)
    print(f"overall_avg_score={scores['_overall']['avg']}", file=sys.stderr)


if __name__ == "__main__":
    main()
