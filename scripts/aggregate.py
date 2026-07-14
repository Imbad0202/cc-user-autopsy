"""
cc-user-autopsy Step 1: aggregate.
Reads ~/.claude/usage-data/ and computes every metric + 9 rule-based scores.
Outputs analysis-data.json.
"""
import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

try:
    from cross_llm_common import parse_jsonl_object
except ImportError:  # pragma: no cover - exercised when imported as scripts.aggregate
    from scripts.cross_llm_common import parse_jsonl_object

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
_USAGE_CHAR_MIN_SESSIONS = 10  # minimum session count to emit the usage_characteristics block
GROWTH_MIN_RATED_PER_WEEK = 3  # weeks with fewer rated sessions emit null for good_rate/composite (not plottable)


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


def _parse_dt(s):
    """Null-safe ISO parse. Reuses parse_iso; returns None on any bad input
    instead of raising, since cross-LLM adapter rows may carry missing or
    malformed timestamps (unknown is never imputed, per spec).

    Always returns an aware datetime (assumes UTC for naive input), THEN
    converts to the system's local zone via astimezone(). Cross-LLM rows
    come from adapters that may or may not include a UTC offset in
    start_time — Claude rows are always UTC ('Z'), adapter rows carry a
    local offset. Mixing naive and aware datetimes in the same max()/min()/
    comparison call raises TypeError and would abort the whole aggregate
    run, so aware-normalization alone is required. But comparison/ordering
    across aware datetimes with DIFFERENT offsets is correct in Python —
    the real problem is every downstream .date()/.hour/calendar-bucketing
    call (_split_at_midnight, _hours_touched, ISO week labels, common_window
    dates) reads the calendar day/hour in whatever offset a value happens to
    carry, so two truly-overlapping rows from different sources can land in
    different calendar-day/hour buckets and silently miss each other. Every
    value leaving this helper is therefore also normalized to ONE consistent
    zone (system local — matches what the adapters emit) so all
    calendar-bucketing downstream compares apples to apples.

    Note: this is OS-local, not the pipeline's configurable --tz (see
    detect_tz()/main()) — _parse_dt is a free function called from many
    sites inside compute_cross_llm without a tz parameter threaded through.
    In the default ("auto") case both resolve to the same zone; a mismatch
    is only possible if a user explicitly overrides --tz to a different
    zone than their OS. Acceptable for this fix's scope; revisit if
    --tz-aware cross-LLM bucketing is ever needed."""
    if not s:
        return None
    try:
        dt = parse_iso(s)
    except (ValueError, TypeError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


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


def is_shippable_project_key(key) -> bool:
    """Return True if a project_key is one we can attribute shipped work to.

    Sessions without a resolvable project_path surface as ``(unknown)`` —
    the scanner cannot read git_commits/pushes for them, so they must not
    be treated as shipped artefacts, as the "top project", or as
    contributing to commit-based velocity metrics.

    The comparison is defensive: strips surrounding whitespace and compares
    case-insensitively, so variants like ``"(Unknown)"``, ``"(UNKNOWN)"``,
    ``"  (unknown)  "``, and whitespace-only strings all map to "not
    shippable". Non-string inputs (``None``, etc.) are rejected.
    """
    if not isinstance(key, str):
        return False
    stripped = key.strip()
    if not stripped:
        return False
    return stripped.lower() != "(unknown)"


def pick_top_project(proj_detail: dict):
    """Pick the project with the most sessions, skipping (unknown).

    Returns (key, data) or None when no eligible project exists.
    """
    eligible = [
        (k, v) for k, v in proj_detail.items()
        if is_shippable_project_key(k)
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda x: x[1]["sessions"])


def count_active_projects(proj_detail: dict, min_sessions: int = 3) -> int:
    """Count projects with >= min_sessions, excluding (unknown)."""
    return sum(
        1 for k, v in proj_detail.items()
        if is_shippable_project_key(k) and v["sessions"] >= min_sessions
    )


def compute_efficiency(sessions: list) -> dict:
    """Compute efficiency metrics (tokens_per_commit, commits_per_hour, ...).

    ``commits_per_hour`` uses only known-project sessions for BOTH numerator
    and denominator. Unknown-project sessions' git_commits are structurally
    0 (the scanner cannot run ``git log`` without a project dir), so
    counting their duration in the denominator deflates the velocity ratio.
    """
    import statistics
    commits_sessions = [s for s in sessions if s["git_commits"] > 0]
    known_sessions = [
        s for s in sessions
        if is_shippable_project_key(s.get("project_key", ""))
    ]
    known_duration_hr = sum(s["duration_min"] for s in known_sessions) / 60
    known_commits = sum(s["git_commits"] for s in known_sessions)
    total_duration_hr = sum(s["duration_min"] for s in sessions) / 60
    return {
        "tokens_per_commit_median": round(statistics.median(
            [s["total_tokens"] / s["git_commits"] for s in commits_sessions]
        ), 0) if commits_sessions else 0,
        "sessions_with_commits": len(commits_sessions),
        "commits_per_hour": round(known_commits / known_duration_hr, 2) if known_duration_hr > 0 else 0,
        "total_duration_hr": round(total_duration_hr, 1),
    }


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


# --- Phase 2 shared helpers (blind-spot engine) ---

_NORM_KEEP_RE = re.compile(r"[^\w一-鿿]+")
_NORM_WS_RE = re.compile(r"\s+")


def normalize_prompt(text):
    """Normalize an instruction for exact-match repetition detection.

    Deliberately exact-match only (v1): lowercased, punctuation folded to
    spaces, whitespace collapsed. No truncation — identity uses the full
    normalized string, so two long instructions that only differ after a
    shared prefix must NOT collapse into one pattern (zero false positives
    beats higher recall for a tax the user will be told to fix). Sources
    already cap first_prompt at 500 chars upstream, so this never runs
    unbounded. No fuzzy matching either. Display truncation (the ≤120-char
    exemplar shown to the user) happens separately in bs_repeated_instructions.
    """
    if not isinstance(text, str):
        return ""
    t = _NORM_KEEP_RE.sub(" ", text.lower())
    return _NORM_WS_RE.sub(" ", t).strip()


_CJK_RE = re.compile(r"[一-鿿]")


def prompt_similarity(a_norm, b_norm):
    """Similarity between two normalize_prompt() outputs.

    Default: token-set Jaccard on whitespace-split words. CJK scripts
    (Chinese) have no whitespace between words, so a whole zh sentence
    normalizes to a single "token" and near-identical zh prompts would
    score 0.0 or 1.0 with nothing in between — breaking sunk-cost pair
    matching for zh users. When either normalized string contains a CJK
    character (U+4E00-U+9FFF), fall back to Jaccard over character
    BIGRAMS of the de-spaced string instead, which degrades gracefully
    for near-duplicate zh prompts. If a de-spaced string has fewer than 2
    characters (no bigrams possible), fall back to the word-token path
    for that comparison. Non-CJK (English etc.) behavior is unchanged.
    """
    if _CJK_RE.search(a_norm) or _CJK_RE.search(b_norm):
        a_flat, b_flat = a_norm.replace(" ", ""), b_norm.replace(" ", "")
        if len(a_flat) >= 2 and len(b_flat) >= 2:
            ba = {a_flat[i:i + 2] for i in range(len(a_flat) - 1)}
            bb = {b_flat[i:i + 2] for i in range(len(b_flat) - 1)}
            if not ba or not bb:
                return 0.0
            return len(ba & bb) / len(ba | bb)
    ta, tb = set(a_norm.split()), set(b_norm.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def week_key(dt):
    """ISO week label 'YYYY-Www' — the single week-bucketing helper.

    build_sessions and the cross_llm weekly loop previously inlined this
    format; a third copy for the blind-spot engine forced the factor-out.
    """
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


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
    "token_accel",
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


def load_cross_llm_rows(paths):
    """Load adapter-emitted rows (scan_codex/grok/antigravity output).

    Returns (rows, parse_errors_by_source). Bad lines are skipped and
    counted under the source guessed from the row, else "(unknown)".
    A trailing ``{"_meta": true, "source": ..., "parse_errors": N}`` line
    (see docs/SCHEMA-CHANGES.md) is consumed into the same errors dict
    instead of being treated as a session row — it's how the scanner's own
    skip-count (only visible on stderr otherwise) reaches
    cross_llm.sources[].parse_errors.
    These rows NEVER enter scoring_metas/activity_metas — the 9-dim
    rubric and the existing panels stay Claude-only by design (spec §6).
    """
    rows, errors = [], {}
    for p in paths:
        path = Path(p).expanduser()
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = parse_jsonl_object(line)
                if row is None:
                    errors["(unknown)"] = errors.get("(unknown)", 0) + 1
                    continue
                if row.get("_meta"):
                    src = row.get("source") or "(unknown)"
                    errors[src] = errors.get(src, 0) + int(row.get("parse_errors") or 0)
                    continue
                if not row.get("source") or not row.get("start_time"):
                    src = row.get("source") or "(unknown)"
                    errors[src] = errors.get(src, 0) + 1
                    continue
                rows.append(row)
    return rows, errors


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
            "week": week_key(local),
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
            "token_accel": m.get("token_accel"),
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
        return {"score": None, "reason": "no sessions", "pattern_emit": False, "pattern": None}
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
    pattern_emit = len(ta_rated) >= _PATTERN_MIN_SAMPLE
    if pattern_emit:
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
        "pattern_emit": pattern_emit,
        # DEPRECATED (see docs/SCHEMA-CHANGES.md): prose fields retained for
        # 2 releases so external JSON consumers don't break. Render layer
        # reads narrative modules instead.
        "explanation": f"{ta_rate:.0f}% of sessions used Task agent; good-outcome rate with Task agent was {good_rate_ta:.0f}%.",
        "pattern": pattern,
    }


def score_d2_rootcause(sessions, rated, facets_coverage):
    if facets_coverage < 30:
        return {"score": None, "reason": "insufficient facet coverage", "pattern_emit": False, "pattern": None}
    iter_buggy = [
        s for s in rated
        if s["session_type"] == "iterative_refinement"
        and s["friction_counts"].get("buggy_code", 0) > 0
    ]
    if not rated:
        return {"score": None, "reason": "no rated sessions", "pattern_emit": False, "pattern": None}
    R = 100 * len(iter_buggy) / len(rated)
    thresholds = [(2, 10), (4, 9), (7, 8), (10, 7), (15, 6), (20, 5), (25, 4)]
    score = 3
    for thr, sc in thresholds:
        if R <= thr:
            score = sc
            break
    iter_sessions = [s for s in rated if s["session_type"] == "iterative_refinement"]
    non_iter_sessions = [s for s in rated if s["session_type"] != "iterative_refinement"]
    pattern_emit = len(non_iter_sessions) >= _PATTERN_MIN_SAMPLE and len(iter_sessions) >= _PATTERN_MIN_SAMPLE
    pattern = None
    if pattern_emit:
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
        "pattern_emit": pattern_emit,
        # DEPRECATED (see docs/SCHEMA-CHANGES.md): prose fields retained for
        # 2 releases so external JSON consumers don't break. Render layer
        # reads narrative modules instead.
        "explanation": f"{len(iter_buggy)} sessions ({R:.0f}%) were iterative_refinement with buggy_code friction — a marker for symptom-level patching.",
        "pattern": pattern,
    }


def score_d3_prompt_quality(sessions):
    if not sessions:
        return {"score": None, "pattern_emit": False, "pattern": None}
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

    # Pattern: compare avg tokens/commit between long-prompt and short-prompt sessions
    long_prompt = [s for s in sessions if s["first_prompt_len"] >= 100 and s["git_commits"] > 0]
    short_prompt = [s for s in sessions if s["first_prompt_len"] <= 50 and s["git_commits"] > 0]
    pattern_emit = len(long_prompt) >= _PATTERN_MIN_SAMPLE and len(short_prompt) >= _PATTERN_MIN_SAMPLE
    pattern = None
    if pattern_emit:
        avg_long = sum(s["total_tokens"] / s["git_commits"] for s in long_prompt) / len(long_prompt)
        avg_short = sum(s["total_tokens"] / s["git_commits"] for s in short_prompt) / len(short_prompt)
        pattern = (
            f"Sessions with prompts ≥100 chars averaged {avg_long:.0f} tokens "
            f"per commit; ≤50-char prompts averaged {avg_short:.0f}."
        )

    return {
        "score": score,
        "metric_pct_prompts_ge_100_chars": round(rate_100, 1),
        "metric_pct_prompts_lt_20_chars": round(rate_lt_20, 1),
        "metric_bucket_median_tokens_per_commit": {
            k: (round(v, 0) if v else None) for k, v in bucket_median.items()
        },
        "metric_most_efficient_bucket": best_bucket,
        "pattern_emit": pattern_emit,
        # DEPRECATED (see docs/SCHEMA-CHANGES.md): prose fields retained for
        # 2 releases so external JSON consumers don't break. Render layer
        # reads narrative modules instead.
        "explanation": f"{rate_100:.0f}% of sessions used prompts ≥ 100 chars. Most efficient prompt-length bucket for tokens/commit: {best_bucket}.",
        "pattern": pattern,
    }


def score_d4_context_mgmt(sessions):
    if not sessions:
        return {"score": None, "pattern_emit": False, "pattern": None}
    otl = [
        s for s in sessions
        if any(k in s["friction_counts"] for k in
               ("output_token_limit_exceeded", "output_token_limit"))
    ]
    long_s = [s for s in sessions if s["duration_min"] > 60]
    long_intr = [s for s in long_s if s["interrupts"] > 0]
    long_intr_rate = (100 * len(long_intr) / len(long_s)) if long_s else 0
    # effort-no-commit only makes sense on sessions whose project_path is
    # resolvable — the scanner cannot read git_commits for (unknown)
    # sessions, so they are structurally zero and would inflate enc_pct.
    over20 = [
        s for s in sessions
        if s["duration_min"] > 20
        and is_shippable_project_key(s.get("project_key", ""))
    ]
    over20_zero_commit = [s for s in over20 if s["git_commits"] == 0]
    enc_pct = (100 * len(over20_zero_commit) / len(over20)) if over20 else 0
    enc_sample = len(over20)

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

    long_no_commit = [
        s for s in sessions
        if s.get("duration_min", 0) > 20
        and s.get("git_commits", 0) == 0
        and is_shippable_project_key(s.get("project_key", ""))
    ]
    other = [
        s for s in sessions
        if is_shippable_project_key(s.get("project_key", ""))
        and not (s.get("duration_min", 0) > 20 and s.get("git_commits", 0) == 0)
    ]
    pattern_emit = len(long_no_commit) >= _PATTERN_MIN_SAMPLE and len(other) >= _PATTERN_MIN_SAMPLE
    pattern = None
    if pattern_emit:
        otl_ids    = {id(s) for s in otl}
        lnc_rate   = 100 * sum(1 for s in long_no_commit if id(s) in otl_ids) / len(long_no_commit)
        other_rate = 100 * sum(1 for s in other         if id(s) in otl_ids) / len(other)
        pattern = (
            f"Sessions over 20 minutes without a commit hit output-token-limit "
            f"{lnc_rate:.0f}% of the time, versus {other_rate:.0f}% for other sessions."
        )

    return {
        "score": score,
        "metric_output_token_limit_sessions": len(otl),
        "metric_long_session_interrupt_rate_pct": round(long_intr_rate, 1),
        "metric_effort_no_commit_pct": round(enc_pct, 1),
        "metric_effort_no_commit_sample": enc_sample,
        "metric_max_otl_in_one_project": max_proj_otl,
        "pattern_emit": pattern_emit,
        # DEPRECATED (see docs/SCHEMA-CHANGES.md): prose fields retained for
        # 2 releases so external JSON consumers don't break. Render layer
        # reads narrative modules instead.
        "explanation": f"{len(otl)} sessions hit output-token-limit. {enc_pct:.0f}% of >20min sessions had 0 commits (n={enc_sample}). Long-session interrupt rate: {long_intr_rate:.0f}%.",
        "pattern": pattern,
    }


def score_d5_interrupt(rated):
    interrupted = [s for s in rated if s["interrupts"] > 0]
    # score guard uses literal 5: the scoring eligibility threshold is independent
    # from _PATTERN_MIN_SAMPLE (the pattern-floor constant). Keep separate so future
    # tuning of pattern floor doesn't silently move scoring.
    if len(interrupted) < 5:
        return {"score": None, "reason": "fewer than 5 interrupted rated sessions", "pattern_emit": False, "pattern": None}
    good = [s for s in interrupted if is_good(s["outcome"])]
    P = 100 * len(good) / len(interrupted)
    thresholds = [(60, 10), (50, 9), (40, 8), (30, 7), (20, 5)]
    score = 3
    for thr, sc in thresholds:
        if P >= thr:
            score = sc
            break
    non_interrupted = [s for s in rated if s["interrupts"] == 0]
    pattern_emit = len(interrupted) >= _PATTERN_MIN_SAMPLE and len(non_interrupted) >= _PATTERN_MIN_SAMPLE
    pattern = None
    if pattern_emit:
        non_good_rate = 100 * sum(1 for s in non_interrupted if is_good(s["outcome"])) / len(non_interrupted)
        pattern = (
            f"Interrupted sessions reached good outcomes {P:.0f}% of the time, "
            f"versus {non_good_rate:.0f}% for non-interrupted sessions."
        )
    return {
        "score": score,
        "metric_interrupt_recovery_pct": round(P, 1),
        "metric_interrupted_sessions": len(interrupted),
        "pattern_emit": pattern_emit,
        # DEPRECATED (see docs/SCHEMA-CHANGES.md): prose fields retained for
        # 2 releases so external JSON consumers don't break. Render layer
        # reads narrative modules instead.
        "explanation": f"{P:.0f}% of interrupted sessions still reached good outcome ({len(good)}/{len(interrupted)}).",
        "pattern": pattern,
    }


def score_d6_tool_breadth(sessions):
    if not sessions:
        return {"score": None, "pattern_emit": False, "pattern": None}
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

    # Rated-only subsets: unrated sessions (outcome == "") would bias is_good() toward
    # False, so restrict the contrast to sessions with a recorded outcome. 3-tool
    # sessions are intentionally excluded to sharpen the diverse/narrow contrast.
    rated_sessions = [s for s in sessions if s.get("outcome", "")]
    diverse = [s for s in rated_sessions if len(s.get("tool_counts", {})) >= 4]
    narrow  = [s for s in rated_sessions if 0 < len(s.get("tool_counts", {})) <= 2]
    pattern_emit = len(diverse) >= _PATTERN_MIN_SAMPLE and len(narrow) >= _PATTERN_MIN_SAMPLE
    pattern = None
    if pattern_emit:
        diverse_good = 100 * sum(1 for s in diverse if is_good(s["outcome"])) / len(diverse)
        narrow_good  = 100 * sum(1 for s in narrow  if is_good(s["outcome"])) / len(narrow)
        pattern = (
            f"Sessions using ≥4 distinct tools reached good outcomes {diverse_good:.0f}% of the time, "
            f"versus {narrow_good:.0f}% for sessions using 1\u20132 tools."
        )

    return {
        "score": score,
        "metric_mcp_rate_pct": round(mcp_rate, 1),
        "metric_top3_share_pct": round(top3_share, 1),
        "metric_top_tools": dict(tool_totals.most_common(10)),
        "pattern_emit": pattern_emit,
        # DEPRECATED (see docs/SCHEMA-CHANGES.md): prose fields retained for
        # 2 releases so external JSON consumers don't break. Render layer
        # reads narrative modules instead.
        "explanation": f"{mcp_rate:.0f}% of sessions used any MCP tool; top-3 tools (Bash/Read/Edit) consume {top3_share:.0f}% of all calls.",
        "pattern": pattern,
    }


def score_d7_writing(rated):
    writing = [
        s for s in rated
        if any(g in WRITING_GOALS for g in s.get("goal_cats", {}).keys())
    ]
    # score guard uses literal 5: the scoring eligibility threshold is independent
    # from _PATTERN_MIN_SAMPLE (the pattern-floor constant). Keep separate so future
    # tuning of pattern floor doesn't silently move scoring.
    if len(writing) < 5:
        return {"score": None, "reason": "fewer than 5 writing sessions", "pattern_emit": False, "pattern": None}
    misu = sum(s["friction_counts"].get("misunderstood_request", 0) for s in writing)
    W = misu / len(writing)
    thresholds = [(0.1, 10), (0.3, 8), (0.6, 7), (1.0, 5)]
    score = 3
    for thr, sc in thresholds:
        if W <= thr:
            score = sc
            break
    non_writing = [s for s in rated
                   if not any(g in WRITING_GOALS for g in s.get("goal_cats", {}).keys())]
    pattern_emit = len(writing) >= _PATTERN_MIN_SAMPLE and len(non_writing) >= _PATTERN_MIN_SAMPLE
    pattern = None
    if pattern_emit:
        w_avg = sum(s["friction_counts"].get("misunderstood_request", 0) for s in writing) / len(writing)
        nw_avg = sum(s["friction_counts"].get("misunderstood_request", 0) for s in non_writing) / len(non_writing)
        pattern = (
            f"Writing-related sessions averaged {w_avg:.1f} misunderstood_request "
            f"events per session, versus {nw_avg:.1f} for other sessions."
        )
    return {
        "score": score,
        "metric_misunderstood_per_writing_session": round(W, 2),
        "metric_writing_sessions": len(writing),
        "pattern_emit": pattern_emit,
        # DEPRECATED (see docs/SCHEMA-CHANGES.md): prose fields retained for
        # 2 releases so external JSON consumers don't break. Render layer
        # reads narrative modules instead.
        "explanation": f"Across {len(writing)} writing-related sessions, avg misunderstood_request per session is {W:.2f}.",
        "pattern": pattern,
    }


def score_d8_time_mgmt(sessions, rated):
    # Use rated sessions for friction, but all sessions to count session volume
    # Scoring eligibility guards — literal thresholds, NOT _PATTERN_MIN_SAMPLE.
    # These control whether the score itself is computable, not the pattern floor.
    if len(rated) < 20:
        return {"score": None, "reason": "<20 rated sessions", "pattern_emit": False, "pattern": None}
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
        return {"score": None, "reason": "<3 hours with enough data", "pattern_emit": False, "pattern": None}
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
    # Pattern: good-outcome rate by time-of-day bucket (morning vs after-10am).
    # This is a DIFFERENT metric from the score (friction ratio) — complementary
    # angle. Uses rated only so unrated sessions can't skew is_good().
    before_10 = [s for s in rated if s.get("hour", 12) < 10]
    after_10  = [s for s in rated if s.get("hour", 12) >= 10]
    pattern_emit = len(before_10) >= _PATTERN_MIN_SAMPLE and len(after_10) >= _PATTERN_MIN_SAMPLE
    pattern = None
    if pattern_emit:
        before_good = 100 * sum(1 for s in before_10 if is_good(s["outcome"])) / len(before_10)
        after_good  = 100 * sum(1 for s in after_10  if is_good(s["outcome"])) / len(after_10)
        pattern = (
            f"Sessions started before 10am had a {before_good:.0f}% good-outcome rate, "
            f"versus {after_good:.0f}% for after-10am sessions."
        )
    return {
        "score": score,
        "metric_friction_ratio_hi_lo": round(ratio, 2),
        "metric_worst_hour": {"hour": worst_hour, "friction_per_session": round(rates[worst_hour], 2)},
        "metric_best_hour": {"hour": best_hour, "friction_per_session": round(rates[best_hour], 2)},
        "pattern_emit": pattern_emit,
        # DEPRECATED (see docs/SCHEMA-CHANGES.md): prose fields retained for
        # 2 releases so external JSON consumers don't break. Render layer
        # reads narrative modules instead.
        "explanation": f"Worst hour ({worst_hour:02d}:00) has {ratio:.1f}x the friction rate of best hour ({best_hour:02d}:00).",
        "pattern": pattern,
    }


def score_d9_token_efficiency(sessions, rated):
    """Compare tokens per good-outcome session vs per other rated session.

    Primary signal: ratio = mean(total_tokens | not-good) / mean(total_tokens | good).
    Secondary: cache hit ratio over all sessions adjusts score by ±1.
    total_tokens is billable non-cache (input + output); cache tokens counted
    separately via cache hit ratio. Returns score=None when either rated
    subgroup is below _PATTERN_MIN_SAMPLE.
    """
    rated_good = [s for s in rated if is_good(s["outcome"])]
    rated_not_good = [s for s in rated if not is_good(s["outcome"])]
    if len(rated_good) < _PATTERN_MIN_SAMPLE or len(rated_not_good) < _PATTERN_MIN_SAMPLE:
        return {
            "score": None,
            "reason": "insufficient good/not-good sample",
            "pattern_emit": False,
            "pattern": None,
        }

    tokens_per_good = sum(s["total_tokens"] for s in rated_good) / len(rated_good)
    tokens_per_not_good = sum(s["total_tokens"] for s in rated_not_good) / len(rated_not_good)
    if tokens_per_good <= 0:
        return {
            "score": None,
            "reason": "zero-token good sessions",
            "pattern_emit": False,
            "pattern": None,
        }
    ratio = tokens_per_not_good / tokens_per_good

    turns_good = sum(s["user_msgs"] for s in rated_good)
    turns_not_good = sum(s["user_msgs"] for s in rated_not_good)
    tokens_per_turn_good = (
        sum(s["total_tokens"] for s in rated_good) / turns_good
        if turns_good > 0 else None
    )
    tokens_per_turn_not_good = (
        sum(s["total_tokens"] for s in rated_not_good) / turns_not_good
        if turns_not_good > 0 else None
    )

    cache_read_all = sum(s.get("cache_read_tokens", 0) or 0 for s in sessions)
    cache_create_all = sum(s.get("cache_create_tokens", 0) or 0 for s in sessions)
    cache_total = cache_read_all + cache_create_all
    cache_hit = cache_read_all / cache_total if cache_total > 0 else None

    if ratio <= 0.9:
        base = 10
    elif ratio <= 1.1:
        base = 8
    elif ratio <= 1.5:
        base = 6
    elif ratio <= 2.0:
        base = 4
    else:
        base = 2

    adj = 0
    if cache_hit is not None:
        if cache_hit < 0.20:
            adj = -1
        elif cache_hit >= 0.60:
            adj = +1
    score = max(1, min(10, base + adj))

    per_turn_frag = ""
    if tokens_per_turn_good is not None and tokens_per_turn_not_good is not None:
        per_turn_frag = (
            f" per-turn: {tokens_per_turn_not_good:,.0f} "
            f"vs {tokens_per_turn_good:,.0f};"
        )
    cache_frag = (
        f" Cache hit ratio {cache_hit*100:.0f}%." if cache_hit is not None else ""
    )
    trailer = f"{per_turn_frag}{cache_frag}"
    explanation = (
        f"Other rated sessions averaged {tokens_per_not_good:,.0f} tokens "
        f"versus {tokens_per_good:,.0f} for good outcomes "
        f"({ratio:.2f}× more)"
        + (f";{trailer}" if trailer else ".")
    )
    pattern = (
        f"Good-outcome sessions averaged {tokens_per_good:,.0f} tokens; "
        f"other rated sessions averaged {tokens_per_not_good:,.0f} "
        f"({ratio:.2f}× more)."
    )

    return {
        "score": score,
        "metric_tokens_per_good": round(tokens_per_good),
        "metric_tokens_per_not_good": round(tokens_per_not_good),
        "metric_ratio": round(ratio, 2),
        "metric_cache_hit_pct": round(cache_hit * 100, 1) if cache_hit is not None else None,
        "pattern_emit": True,
        # DEPRECATED (see docs/SCHEMA-CHANGES.md): prose fields retained for
        # 2 releases so external JSON consumers don't break. Render layer
        # reads narrative modules instead.
        "explanation": explanation,
        "pattern": pattern,
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
    scores["D9_token_efficiency"] = score_d9_token_efficiency(sessions, rated)
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

    result = {
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

    # Build usage_characteristics block when enough sessions exist and dates are available.
    # Guard: omit if < _USAGE_CHAR_MIN_SESSIONS or no valid session start dates.
    uc_dates = [s["start"][:10] for s in sessions
                if s.get("start") and len(s.get("start", "")) >= 10]
    if len(sessions) >= _USAGE_CHAR_MIN_SESSIONS and uc_dates:
        since = min(uc_dates)
        until = max(uc_dates)
        total = len(sessions)

        # Item 1: sessions with hit_output_limit=True / total
        hit_limit = sum(1 for s in sessions if s.get("hit_output_limit"))
        pct1 = round(100 * hit_limit / total)

        # Item 2: long-friction / total-friction
        # "long" = duration_min > 20 AND friction_counts has at least one event
        # "friction" = sessions with at least one friction event
        friction_sessions = [s for s in sessions
                             if sum((s.get("friction_counts") or {}).values()) > 0]
        long_friction = sum(
            1 for s in friction_sessions
            if (s.get("duration_min") or 0) > 20
        )
        denom2 = len(friction_sessions)
        pct2 = round(100 * long_friction / denom2) if denom2 > 0 else 0

        # Item 3: good+task_agent / good-total
        good_sessions = [s for s in sessions if is_good(s.get("outcome", ""))]
        good_task_agent = sum(1 for s in good_sessions if s.get("uses_task_agent"))
        denom3 = len(good_sessions)
        pct3 = round(100 * good_task_agent / denom3) if denom3 > 0 else 0

        # Item 4: sessions with 1-2 distinct tools / total
        narrow_tool = sum(
            1 for s in sessions
            if len(s.get("tool_counts") or {}) <= 2
        )
        pct4 = round(100 * narrow_tool / total)

        # Item 5: sessions hour >= 22 / total
        late_night = sum(1 for s in sessions if (s.get("hour") or 0) >= 22)
        pct5 = round(100 * late_night / total)

        result["usage_characteristics"] = {
            "since": since,
            "until": until,
            "n_sessions": total,
            "items": [
                {
                    "pct": pct1,
                    "label": "of your sessions hit output-token-limit",
                    "tip": "Sessions that /compact mid-task rarely hit the wall.",
                },
                {
                    "pct": pct2,
                    "label": "of your high-friction sessions were long (>20min)",
                    "tip": "Long sessions concentrate friction; consider /clear between subtasks.",
                },
                {
                    "pct": pct3,
                    "label": "of your good-outcome sessions delegated to Task agent",
                    "tip": "Task-agent delegation correlates with ship-level outcomes.",
                },
                {
                    "pct": pct4,
                    "label": "of your sessions used only 1-2 distinct tools",
                    "tip": "Narrow tool use is fine for focused work but misses MCP leverage.",
                },
                {
                    "pct": pct5,
                    "label": "of your sessions were after 10pm",
                    "tip": "Evening sessions produce more tokens per friction event.",
                },
            ],
        }

    return result


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
        # `week` is kept as "YYYY-WWW" for cross-year sorting/joining.
        # `week_label` strips the year prefix for axis display ("W15" not "2026-W15").
        week_label = w.split("-", 1)[-1] if "-" in w else w
        wk.append({
            "week": w,
            "week_label": week_label,
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

    # efficiency (commits_per_hour excludes (unknown)-project duration —
    # see compute_efficiency for rationale)
    result["efficiency"] = compute_efficiency(sessions)
    total_duration_hr = result["efficiency"]["total_duration_hr"]

    # -------- SHIPPED ARTIFACTS (HR-facing) --------
    # Group rated "fully_achieved + essential/very_helpful" sessions by project,
    # pick the richest brief_summary per project (longest one), cap top 8.
    shipped_by_proj = defaultdict(list)
    for s in rated:
        if s["outcome"] == "fully_achieved" and s["helpfulness"] in ("essential", "very_helpful"):
            if s["brief_summary"] and is_shippable_project_key(s["project_key"]):
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
        week_rated_count = w["rated"]
        insufficient = week_rated_count < GROWTH_MIN_RATED_PER_WEEK
        ta_rate_w = 100 * w["uses_task_agent"] / w["sessions"]
        good_rate_w = w["good_rate_pct"]
        fric_ratio = (w["friction"] / w["sessions"]) / max_fric_per_session if max_fric_per_session else 0
        fric_score = 100 * (1 - fric_ratio)
        # composite: good rate * 0.4, ta_rate * 0.3, fric_score * 0.3
        composite = round(0.4 * good_rate_w + 0.3 * ta_rate_w + 0.3 * fric_score, 1)
        growth.append({
            "week": w["week"],
            "week_label": w.get("week_label", w["week"]),
            "composite_score": None if insufficient else composite,
            "ta_rate": round(ta_rate_w, 1),  # uses sessions denominator, no gate
            "good_rate": None if insufficient else good_rate_w,
            "fric_score": round(fric_score, 1),
            "rated_sessions": week_rated_count,
        })
    result["growth_curve"] = growth

    # -------- PROFILE SUMMARY (HR-facing headline) --------
    # Auto-derived 2-sentence self-description for the top of the page.
    ta_pct = 100 * sum(1 for s in sessions if s["uses_task_agent"]) / len(sessions) if sessions else 0
    mcp_pct = 100 * sum(1 for s in sessions if s["uses_mcp"]) / len(sessions) if sessions else 0
    project_count = count_active_projects(proj_detail, min_sessions=3)
    top_project = pick_top_project(proj_detail)
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


def _row_windows(row):
    """Activity windows for a row: explicit segments, else start+duration.

    Zero-length windows (a single-event session's [t, t] segment, or a
    duration_minutes of 0) are expanded to a minimum of 1 minute — otherwise
    they contribute 0 minutes to weekly_share and no presence to the
    parallel-overlap sweep, silently vanishing from both.
    """
    segs = row.get("segments")
    out = []
    if segs:
        for pair in segs:
            try:
                s, e = _parse_dt(pair[0]), _parse_dt(pair[1])
            except (TypeError, IndexError):
                continue
            if s and e and e >= s:
                if e == s:
                    e = s + timedelta(minutes=1)
                out.append((s, e))
        if out:
            return out
    s = _parse_dt(row.get("start_time") or "")
    if not s:
        return []
    dur = row.get("duration_minutes") or 0
    return [(s, s + timedelta(minutes=max(dur, 1)))]


def _split_at_midnight(start, end):
    """Yield (day_date, seg_start, seg_end) pieces, split at local midnights."""
    cur = start
    while cur.date() < end.date():
        boundary = datetime.combine(
            cur.date() + timedelta(days=1), time.min, tzinfo=cur.tzinfo)
        yield cur.date(), cur, boundary
        cur = boundary
    if cur < end or cur == start:
        # Skip the zero-length terminal piece a window ending exactly at
        # local midnight would otherwise produce (23:00-00:00 must count
        # one active day, not two) — but still yield instantaneous
        # single-point windows (cur == start) so they aren't dropped.
        yield cur.date(), cur, end


def _hours_touched(day, ss, ee):
    """Hour-of-day buckets (0-23) touched by the half-open interval
    [ss, ee) within a single calendar `day`. Uses minutes-since-midnight
    rather than raw .hour comparisons: a naive `range(ss.hour, ee.hour+1)`
    approach either double-counts sessions that end exactly on an hour
    boundary, or (worse) counts a phantom extra hour past the window end
    for any same-hour or minute-carrying end time. `ee` may legitimately
    fall on the next calendar day's midnight (the exclusive end produced
    by `_split_at_midnight`'s last piece of a day) — that is treated as
    minute 1440 of `day`, giving hour 23 rather than an empty range.
    """
    def _minute_of_day(dt):
        if dt.date() > day:
            return 24 * 60
        return dt.hour * 60 + dt.minute + dt.second / 60

    start_m = _minute_of_day(ss)
    end_m = _minute_of_day(ee)
    if end_m <= start_m:
        return []
    start_h = int(start_m // 60)
    # The last touched minute is end_m - epsilon (end is exclusive).
    end_h = int((end_m - 1e-9) // 60)
    return list(range(start_h, min(end_h, 23) + 1))


def _project_key(path_str):
    return Path(path_str).name if path_str else "(unknown)"


def _merge_intervals(intervals):
    """Merge a list of (start, end) datetime tuples into a sorted list of
    non-overlapping (start, end) tuples (touching/overlapping intervals
    from the SAME source are unioned so that source is counted once)."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda p: p[0])
    merged = [list(ordered[0])]
    for s, e in ordered[1:]:
        if s <= merged[-1][1]:
            if e > merged[-1][1]:
                merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _sweep_concurrent_intervals(rows, windows):
    """True-overlap sweep line across sources.

    Per source: merge that source's own activity windows into a union of
    non-overlapping intervals (so a source's own back-to-back/overlapping
    sessions are never double counted). Then sweep +1 at each merged
    interval's start and -1 at its end across ALL sources, producing the
    piecewise-constant "number of distinct sources active" function.

    Returns (concurrent_intervals, source_count_by_instant_change) where
    concurrent_intervals is a list of (start, end, n_sources) covering
    every maximal sub-interval with a constant concurrency count > 0.
    """
    by_source = defaultdict(list)
    for r in rows:
        for s, e in windows.get(id(r), []):
            by_source[r["source"]].append((s, e))

    events = []  # (time, delta) — delta is +1 at interval start, -1 at end
    for src, ivals in by_source.items():
        for s, e in _merge_intervals(ivals):
            if e <= s:
                continue
            events.append((s, 1))
            events.append((e, -1))

    if not events:
        return []

    events.sort(key=lambda ev: (ev[0], -ev[1]))  # starts (+1) before ends (-1) at same instant
    result = []
    count = 0
    prev_t = None
    for t, delta in events:
        if prev_t is not None and t > prev_t and count > 0:
            result.append((prev_t, t, count))
        count += delta
        prev_t = t
    return result


def _bucket_concurrent_intervals_by_hour(concurrent_intervals):
    """Bucket concurrency>=1 sub-intervals into (date, hour) -> max concurrency
    touching that bucket, splitting at local midnight boundaries."""
    hour_max = {}  # (date, hour) -> max concurrency seen in that bucket
    for s, e, n in concurrent_intervals:
        for day, ss, ee in _split_at_midnight(s, e):
            for h in _hours_touched(day, ss, ee):
                key = (day, h)
                hour_max[key] = max(hour_max.get(key, 0), n)
    return hour_max


def compute_cross_llm(claude_rows, cross_rows):
    """Build the cross_llm block. claude_rows = activity-pool row dicts.

    Cross-LLM rows never enter scoring_metas/activity_metas; this function
    only reads the two row lists it's given and returns a new block, so
    the 9-dim scores and existing panels stay untouched (spec §6).
    """
    tagged = [dict(r, source="claude", coverage="full") for r in claude_rows]
    all_rows = tagged + list(cross_rows)
    comparable = [r for r in all_rows if r.get("coverage") != "presence_only"]

    # One pass up front: group rows by source and parse each row's
    # start_time / activity windows exactly once; every block below reads
    # these instead of re-filtering and re-parsing the same rows.
    rows_by_source = {}
    for r in all_rows:
        rows_by_source.setdefault(r["source"], []).append(r)
    comparable_by_source = {}
    for r in comparable:
        comparable_by_source.setdefault(r["source"], []).append(r)
    start_dt = {id(r): _parse_dt(r.get("start_time") or "") for r in all_rows}
    windows = {id(r): _row_windows(r) for r in comparable}

    # Per-row (first, last) activity instant used for coverage ranges (source
    # cards' first_date/last_date). For comparable rows, use the row's
    # windows (min window start, max window end) — a resumed segment days
    # after the first one must extend last_date, not just start_time. Windows
    # are only computed for `comparable` rows (see `windows` above); presence-
    # only rows keep using start_time for both ends, per spec.
    row_range = {}
    for r in all_rows:
        rid = id(r)
        ws = windows.get(rid)
        if ws:
            row_range[rid] = (min(s for s, _ in ws), max(e for _, e in ws))
        else:
            d = start_dt[rid]
            row_range[rid] = (d, d) if d else (None, None)

    def _rows_span(rs):
        """(earliest first, latest last) across a set of rows' row_range
        entries, or (None, None) if none have a resolvable range."""
        firsts = [a for a, _ in (row_range[id(r)] for r in rs) if a]
        lasts = [b for _, b in (row_range[id(r)] for r in rs) if b]
        return (min(firsts) if firsts else None, max(lasts) if lasts else None)

    # --- source cards ---
    # Every source in the known set gets a card, even when never detected —
    # spec: absent sources render "not detected" rather than being omitted.
    _KNOWN_SOURCES = ("claude", "codex", "grok", "antigravity")
    sources = []
    for src in sorted(set(_KNOWN_SOURCES) | set(rows_by_source)):
        rs = rows_by_source.get(src)
        if not rs:
            sources.append({
                "source": src, "coverage": None, "session_count": 0,
                "first_date": None, "last_date": None,
                "total_input_tokens": None, "total_output_tokens": None,
                "parse_errors": 0, "detected": False,
            })
            continue
        first, last = _rows_span(rs)

        def _tok(key, _rs=rs):
            vals = [r.get(key) for r in _rs if isinstance(r.get(key), int)]
            return sum(vals) if vals else None

        sources.append({
            "source": src,
            "coverage": rs[0].get("coverage", "full"),
            "session_count": len(rs),
            "first_date": first.date().isoformat() if first else None,
            "last_date": last.date().isoformat() if last else None,
            "total_input_tokens": _tok("input_tokens"),
            "total_output_tokens": _tok("output_tokens"),
            "parse_errors": 0,
            "detected": True,
        })

    # --- common window across comparable sources ---
    # Uses row_range (windows-derived) rather than start_dt directly, so a
    # resumed segment's later end also extends the window used for
    # common_window overlap math (same rationale as source cards above).
    per_source_range = {}
    for src, rs in comparable_by_source.items():
        first, last = _rows_span(rs)
        if first and last:
            per_source_range[src] = (first, last)
    common_window = None
    if len(per_source_range) >= 2:
        start = max(a for a, _ in per_source_range.values())
        end = min(b for _, b in per_source_range.values())
        days = max((end - start).days, 0)
        common_window = {"start": start.date().isoformat(),
                         "end": end.date().isoformat(),
                         "days": days, "degraded": days < 14}

    # --- weekly share (active minutes per ISO week per source) ---
    # When a common_window exists, the renderer's note tells the reader the
    # cross-tool comparison is scoped to that window — so windows are
    # clipped to [window start, window end] (dates inclusive) before
    # aggregation; activity fully outside the window contributes nothing.
    # Without a common_window (or when degraded — the renderer hides the
    # chart anyway), keep the unclipped behavior.
    clip_start = clip_end = None
    if common_window is not None:
        # Boundaries must be local-zone midnights, matching the tzinfo
        # _parse_dt normalizes every row datetime to (system local, via
        # astimezone() — see _parse_dt's docstring). Building these as UTC
        # midnights instead (the original bug) silently drops activity in
        # positive-UTC-offset zones: local midnight on the window's first
        # day falls BEFORE the wrongly-UTC clip_start, so real activity
        # between local midnight and that boundary gets clipped away.
        # datetime.min/max().astimezone() has no tz to convert FROM, so we
        # instead combine the naive date/time and attach the local offset
        # directly via .astimezone() on an already-local reference value.
        clip_start = datetime.combine(
            date.fromisoformat(common_window["start"]), time.min).astimezone()
        clip_end = datetime.combine(
            date.fromisoformat(common_window["end"]) + timedelta(days=1),
            time.min).astimezone()

    def _clip(s, e):
        """Clip window (s, e) to [clip_start, clip_end]; None if it falls
        fully outside. clip_start is None (no common_window) means no clip."""
        if clip_start is None:
            return (s, e)
        cs, ce = max(s, clip_start), min(e, clip_end)
        return (cs, ce) if ce > cs else None

    weekly = {}
    for r in comparable:
        for s, e in windows[id(r)]:
            clipped = _clip(s, e)
            if clipped is None:
                continue
            s, e = clipped
            wk = week_key(s)
            weekly.setdefault(wk, {}).setdefault(r["source"], 0)
            weekly[wk][r["source"]] += round((e - s).total_seconds() / 60)
    weekly_share = [{"week": wk, "minutes": mins}
                    for wk, mins in sorted(weekly.items())]

    # --- scope to common window for cross-source comparisons ---
    # Spec §13: cross-source comparison charts (parallel heatmap, project x
    # tool matrix) degrade to per-source panels below 14 days. When a
    # healthy (non-degraded) common_window exists, clip both windows AND row
    # membership to it before parallel detection / matrix counting, so
    # activity outside the window a reader is told the comparison covers
    # doesn't leak in. When degraded or absent, keep full history in the
    # emitted blocks (schema stability) — report_render.py is responsible
    # for suppressing the exhibit in that case, not aggregate.py for hiding
    # the data.
    if common_window is not None and not common_window["degraded"]:
        scoped_windows = {}
        scoped_comparable = []
        for r in comparable:
            rid = id(r)
            clipped = [c for s, e in windows[rid] if (c := _clip(s, e)) is not None]
            if clipped:
                scoped_windows[rid] = clipped
                scoped_comparable.append(r)
    else:
        scoped_windows = windows
        scoped_comparable = comparable

    # --- parallel detection: true interval overlap via sweep line ---
    # Per source, merge that source's own activity windows first (so a
    # source's own overlapping/adjacent sessions count as one presence);
    # then sweep across sources to find sub-intervals where >=2 distinct
    # sources are simultaneously active. Only THOSE sub-intervals are
    # bucketed into the hour heatmap — two sessions that merely touch the
    # same hour without ever running concurrently no longer count.
    concurrent_intervals = _sweep_concurrent_intervals(scoped_comparable, scoped_windows)
    concurrency_hour_max = _bucket_concurrent_intervals_by_hour(concurrent_intervals)

    # Hours touched by >=1 source at all (regardless of concurrency) — one
    # pass, used both to derive hours_single_source = touched - multi AND
    # to floor daily_max at 1 for days that never reach concurrency>=2.
    touched_hours = set()
    for r in scoped_comparable:
        for s, e in scoped_windows[id(r)]:
            for day, ss, ee in _split_at_midnight(s, e):
                for h in _hours_touched(day, ss, ee):
                    touched_hours.add((day, h))

    heatmap = [[0] * 24 for _ in range(7)]
    daily = defaultdict(int)  # date -> max concurrent sources that day
    multi = 0
    for (day, h), n in concurrency_hour_max.items():
        daily[day] = max(daily[day], n)
        if n >= 2:
            heatmap[day.weekday()][h] += 1
            multi += 1
    # Days with only single-source activity (no concurrency>=2 sub-interval
    # touched that day) still need a daily_max entry — max_parallel 1.
    # Derived from touched_hours (already computed above) rather than a
    # fresh walk over comparable/windows.
    for day, _h in touched_hours:
        daily[day] = max(daily[day], 1)
    single = len(touched_hours) - multi
    parallel = {
        "heatmap": heatmap,
        "daily_max": [{"date": d.isoformat(), "max_parallel": m}
                      for d, m in sorted(daily.items())],
        "hours_multi_source": multi,
        "hours_single_source": single,
    }

    # --- project x tool matrix (top 10 projects by total sessions) ---
    # Row membership scoped the same way as parallel detection above.
    matrix = {}
    for r in scoped_comparable:
        proj = _project_key(r.get("project_path") or "")
        matrix.setdefault(proj, {}).setdefault(r["source"], 0)
        matrix[proj][r["source"]] += 1
    top = sorted(matrix.items(), key=lambda kv: -sum(kv[1].values()))[:10]
    matrix_sources = sorted(comparable_by_source)
    project_matrix = {
        "projects": [p for p, _ in top],
        "sources": matrix_sources,
        "counts": [[counts.get(s, 0) for s in matrix_sources]
                   for _, counts in top],
    }

    # --- head-to-head: claude vs codex inside the common window ---
    # NOTE: head_to_head is computed and emitted even when common_window is
    # degraded (days < 14); report_render.py gates its display on
    # `not win.get("degraded")`, so any other consumer of analysis-data.json
    # must check common_window.degraded itself before trusting this block.
    head_to_head = None
    if common_window and {"claude", "codex"} <= set(per_source_range):
        window_start_date = date.fromisoformat(common_window["start"])
        window_end_date = date.fromisoformat(common_window["end"])

        def _side(src):
            # Membership: a session is "inside" the window when ANY of its
            # activity windows intersects the common window — matching how
            # the parallel/project_matrix blocks above select rows (via
            # `windows`/`_clip`), rather than filtering on start_time alone.
            # A session that STARTED before the window but was resumed with
            # a segment inside it (a real rollout-file pattern for these
            # adapters) is counted by the matrix/heatmap but was previously
            # excluded here — the two exhibits describing the same window
            # must agree on which sessions fall inside it.
            inside = []
            for r in comparable_by_source.get(src, []):
                clipped = [c for s, e in windows[id(r)] if (c := _clip(s, e)) is not None]
                if clipped:
                    inside.append((r, clipped))
            if not inside:
                return None
            # Duration: only the minutes that actually fall INSIDE the
            # common window (clipped segments), so a resumed session with
            # one minute in-window doesn't smuggle in hours of pre-window
            # activity under a "common window" heading.
            durs = [
                round(sum((e - s).total_seconds() for s, e in clipped) / 60)
                for _, clipped in inside
            ]
            # total_tokens: sum only rows that carry at least one token
            # field, so a row missing both input/output doesn't silently
            # count as 0 and drag the total down. If NO row in the window
            # has token data at all, emit None rather than a misleading 0.
            # Token counts are SESSION-level facts (adapters get one
            # cumulative figure per session, not per segment), so a session
            # partially inside the window contributes its full total —
            # apportioning by time would be imputation, which this pipeline
            # forbids. Consumers should read this as "tokens of sessions
            # active in the window".
            tok_rows = [
                (r.get("input_tokens"), r.get("output_tokens"))
                for r, _ in inside
                if r.get("input_tokens") is not None or r.get("output_tokens") is not None
            ]
            total_tokens = (
                sum((i or 0) + (o or 0) for i, o in tok_rows)
                if tok_rows else None
            )
            # active_days: distinct calendar days covered by the CLIPPED
            # windows inside the common window (a clipped window spanning
            # local midnight contributes each day it touches).
            active_days = {
                day for _, clipped in inside
                for s, e in clipped
                for day, _ss, _ee in _split_at_midnight(s, e)
            }
            return {"sessions": len(inside),
                    "active_days": len(active_days),
                    "total_tokens": total_tokens,
                    "median_duration_minutes": round(statistics.median(durs))}

        claude_side, codex_side = _side("claude"), _side("codex")
        if claude_side and codex_side:
            head_to_head = {"window_days": common_window["days"],
                            "claude": claude_side, "codex": codex_side}

    return {"sources": sources, "common_window": common_window,
            "weekly_share": weekly_share, "parallel": parallel,
            "project_matrix": project_matrix, "head_to_head": head_to_head}


def compute_ledger(activity_metas, cross_llm, window_end=None):
    """window_end (aware datetime, optional): the max activity END across
    all activity windows (see main()'s shared computation — blind_spots,
    leaks, and ledger.window share one end-aware window). When omitted,
    falls back to the max session START date (prior behavior), for callers
    that don't have the end-aware value on hand.
    """
    rows = list(activity_metas.values())
    dates = sorted(d for d in (_parse_dt(r.get("start_time") or "")
                               for r in rows) if d)
    commits = sum(r.get("git_commits") or 0 for r in rows)
    pushes = sum(r.get("git_pushes") or 0 for r in rows)
    with_commits = sum(1 for r in rows if (r.get("git_commits") or 0) > 0)
    start_date = dates[0].date() if dates else None
    end_date = window_end.date() if window_end else (dates[-1].date() if dates else None)
    if start_date and end_date and end_date < start_date:
        end_date = start_date
    return {
        "schema_version": 1,
        "window": {
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None,
            "days": (end_date - start_date).days if start_date and end_date else 0,
        },
        "output": {"git_commits": commits, "git_pushes": pushes,
                   "sessions_with_commits": with_commits},
        # cross_llm.sources always has one card per known source, including
        # undetected ones (detected: false, session_count 0) — see the
        # "detected" field added in the codex-fix-wave. Filter to sources
        # that actually produced rows this run; `.get("detected", True)` and
        # the session_count fallback keep this correct for pre-"detected"-
        # field JSON where every listed source was, by construction, one
        # that had rows.
        "sources_detected": [
            s["source"] for s in cross_llm["sources"]
            if s.get("detected", True) or (s.get("session_count") or 0) > 0
        ],
    }


# --- Blind-spot engine (Phase 2, spec §5) -----------------------------
# Gate literals below are heuristic-eligibility thresholds: independent
# from _PATTERN_MIN_SAMPLE (the pattern-floor constant). Keep separate so
# future tuning of the pattern floor doesn't silently move these gates.
_BS_MIN_PATTERN_CHARS = 20
_BS_REPEAT_MIN_OCC = 5
_BS_REPEAT_MIN_WEEKS = 3
_BS_SUNK_MIN_PAIRS = 3
_BS_ACCEL_FLAG = 1.5
_BS_SIMILARITY_MIN = 0.5
_BS_RETRY_MAX_DURATION_SHARE = 0.5
_BS_GUARD_FACTOR = 1.5


def _bs_result(id_, gate, metrics=None, n=0, reason=None, guarded=False):
    return {"id": id_, "gate_passed": bool(gate),
            "suppressed_by_guard": bool(guarded), "n": n,
            "metrics": metrics or {}, "reason": reason}


def bs_repeated_instructions(claude_rows, cross_rows, window_start=None, window_end=None):
    """Spec §5 #1 — repeated-instruction tax.

    Exact-match on normalize_prompt(first_prompt) across Claude + full/
    partial cross-LLM rows. Not outcome-guarded by design: a repeated
    instruction is a tax whether or not the sessions succeed (see rubric).
    Wasted-token estimate is a lower bound: only the retyped prompt text.

    window_start/window_end (aware datetimes, optional): when BOTH are
    given, rows whose parsed start_time falls outside [window_start,
    window_end] are skipped entirely — codex/grok history extending beyond
    the transcript-derived ledger window must not contribute occurrences,
    since compute_leaks divides all-time totals by the window's weeks and
    the render claims "N occurrences in window". Either bound alone (or
    both None) disables windowing, matching prior behavior. The comparison
    is by calendar DATE, inclusive at both ends (Fix 6): a cross-source row
    earlier in the day than window_start (or later than window_end) on the
    SAME calendar date still counts as in-window, matching the date-range
    the rendered window note claims to cover.
    """
    occ = {}
    windowed = window_start is not None and window_end is not None
    win_start_d = window_start.date() if windowed else None
    win_end_d = window_end.date() if windowed else None
    for row in list(claude_rows) + list(cross_rows):
        if row.get("coverage") == "presence_only":
            continue
        norm = normalize_prompt(row.get("first_prompt"))
        if len(norm) < _BS_MIN_PATTERN_CHARS:
            continue
        dt = _parse_dt(row.get("start_time"))
        if dt is None:
            continue
        if windowed and not (win_start_d <= dt.date() <= win_end_d):
            continue
        occ.setdefault(norm, []).append({
            "week": week_key(dt),
            "source": row.get("source") or "claude",
            "sid": row.get("session_id") or "",
            "raw": row.get("first_prompt") or ""})
    patterns = []
    for hits in occ.values():
        weeks = {h["week"] for h in hits}
        if len(hits) < _BS_REPEAT_MIN_OCC or len(weeks) < _BS_REPEAT_MIN_WEEKS:
            continue
        raw_counts = {}
        for h in hits:
            raw_counts[h["raw"]] = raw_counts.get(h["raw"], 0) + 1
        exemplar = max(raw_counts, key=raw_counts.get)[:120]
        # claude_wasted_tokens prices only the Claude share as a defensible
        # lower bound: est_wasted_tokens counts occurrences across
        # Claude+Codex+Grok, but non-Claude tokens have no Claude rate to
        # honestly price at. This additive field feeds compute_leaks' USD
        # figure; est_wasted_tokens (all-source) still drives the
        # tokens/week display.
        claude_occurrences = sum(1 for h in hits if h["source"] == "claude")
        claude_wasted_tokens = max(claude_occurrences - 1, 0) * (len(exemplar) // 4)
        patterns.append({
            "exemplar": exemplar,
            "occurrences": len(hits),
            "weeks": len(weeks),
            "sources": sorted({h["source"] for h in hits}),
            "est_wasted_tokens": (len(hits) - 1) * (len(exemplar) // 4),
            "claude_wasted_tokens": claude_wasted_tokens,
            "evidence": [h["sid"] for h in hits[:3]]})
    patterns.sort(key=lambda p: -p["occurrences"])
    if not patterns:
        return _bs_result("repeated_instructions", False,
                          reason="no pattern with >=5 occurrences over >=3 weeks")
    return _bs_result("repeated_instructions", True,
                      metrics={"patterns": patterns[:5]}, n=len(patterns))


def counterexample_similar(rate_flagged, rate_good):
    """Spec §5 counterexample guard: True when the flagged behavior occurs
    at a similar rate in fully_achieved sessions (within _BS_GUARD_FACTOR),
    i.e. the pattern must NOT be reported as waste."""
    if rate_flagged <= 0:
        return True
    return rate_good * _BS_GUARD_FACTOR >= rate_flagged


def bs_sunk_cost(rated):
    """Spec §5 #2 — sunk-cost sessions.

    A confirmed pair = a not_achieved session with late-session output
    acceleration, followed by a later good-outcome session on a similar
    prompt finishing in <= half the minutes. Guard: if acceleration is
    about as common in fully_achieved sessions, suppress entirely.
    """
    def accel_flag(s):
        a = s.get("token_accel")
        return a is not None and a >= _BS_ACCEL_FLAG

    failed = [s for s in rated
              if s["outcome"] == "not_achieved" and accel_flag(s)]
    good = [s for s in rated if is_good(s["outcome"])]
    # The pairing loop below is failed x good; dt parsing and prompt
    # normalization depend only on g, so hoist them out of the inner loop.
    candidates = []
    for g in good:
        g_dt = _parse_dt(g.get("start"))
        if g_dt is None:
            continue
        candidates.append((g, g_dt, normalize_prompt(g.get("first_prompt"))))
    pairs = []
    for f in failed:
        fn = normalize_prompt(f.get("first_prompt"))
        if len(fn) < _BS_MIN_PATTERN_CHARS:
            continue
        f_dt = _parse_dt(f.get("start"))
        f_dur = f.get("duration_min") or 0
        if f_dt is None or f_dur <= 0:
            continue
        for g, g_dt, g_norm in candidates:
            if g_dt <= f_dt:
                continue
            sim = prompt_similarity(fn, g_norm)
            if sim < _BS_SIMILARITY_MIN:
                continue
            if (g.get("duration_min") or 0) > _BS_RETRY_MAX_DURATION_SHARE * f_dur:
                continue
            pairs.append({"failed_sid": f["sid"], "retry_sid": g["sid"],
                          "failed_tokens": f.get("total_tokens") or 0,
                          "failed_minutes": f_dur,
                          "retry_minutes": g.get("duration_min") or 0,
                          "similarity": round(sim, 2)})
            break
    fa = [s for s in rated if s["outcome"] == "fully_achieved"
          and s.get("token_accel") is not None]
    na = [s for s in rated if s["outcome"] == "not_achieved"
          and s.get("token_accel") is not None]
    rate_good = (sum(accel_flag(s) for s in fa) / len(fa)) if fa else 0.0
    rate_bad = (sum(accel_flag(s) for s in na) / len(na)) if na else 0.0
    metrics = {"pairs": pairs,
               "accel_rate_not_achieved": round(rate_bad, 2),
               "accel_rate_fully_achieved": round(rate_good, 2)}
    if pairs and counterexample_similar(rate_bad, rate_good):
        return _bs_result("sunk_cost", False, metrics=metrics, n=len(pairs),
                          reason="acceleration equally common in successful sessions",
                          guarded=True)
    if len(pairs) < _BS_SUNK_MIN_PAIRS:
        return _bs_result("sunk_cost", False, metrics=metrics, n=len(pairs),
                          reason="fewer than 3 confirmed pairs")
    return _bs_result("sunk_cost", True, metrics=metrics, n=len(pairs))


_BS_SWITCH_MIN_PER_BUCKET = 20


def _multi_source_intervals(activity_rows, cross_rows):
    """Merged wall-clock intervals where >=2 sources were active.
    Reuses the cross_llm sweep helpers; presence-only rows excluded."""
    rows = []
    for r in activity_rows:
        rr = dict(r)
        rr.setdefault("source", "claude")
        rows.append(rr)
    rows += [r for r in cross_rows if r.get("coverage") != "presence_only"]
    windows = {id(r): _row_windows(r) for r in rows}
    concurrent = _sweep_concurrent_intervals(rows, windows)
    return _merge_intervals([(s, e) for s, e, n in concurrent if n >= 2])


def _common_window_dates(rows):
    """Per-source [min start, max end] -> common window, mirroring
    compute_cross_llm's common_window derivation (spec §13): the window a
    reader is told cross-source comparisons cover is the overlap of every
    source's own coverage span, not each source's full history. `rows` must
    already be source-tagged (each row carries a "source" key) and exclude
    presence_only rows. Returns (start_date, end_date) as `date` objects, or
    None if fewer than 2 sources have any resolvable window.

    Boundaries are calendar dates (inclusive) per spec: callers compare
    `dt.date()` against these bounds rather than exact timestamps, so a
    cross-source occurrence earlier in the day than the Claude minimum
    start (or later than its maximum end) on the SAME calendar date still
    counts as in-window (Fix 6)."""
    per_source = {}
    for r in rows:
        windows = _row_windows(r)
        if not windows:
            continue
        src = r.get("source") or "claude"
        starts = [s for s, _ in windows]
        ends = [e for _, e in windows]
        lo, hi = min(starts), max(ends)
        if src not in per_source:
            per_source[src] = [lo, hi]
        else:
            per_source[src][0] = min(per_source[src][0], lo)
            per_source[src][1] = max(per_source[src][1], hi)
    if len(per_source) < 2:
        return None
    start = max(lo for lo, _ in per_source.values())
    end = min(hi for _, hi in per_source.values())
    if end < start:
        return None
    return start.date(), end.date()


def bs_switch_tax(rated, activity_rows, cross_rows):
    """Spec §5 #3 — switch tax. Outcome labels exist only for Claude, so
    both buckets are Claude sessions; concurrency is measured against all
    full/partial sources. Symmetric comparison — no counterexample guard.

    Comparison runs over the cross-source common window only (spec: cross-
    source comparisons render only over the common time window). Claude
    history predating Codex/Grok adoption would otherwise flood the
    single-tool bucket — those pre-overlap sessions could never have been
    multi-tool, biasing the comparison — so BOTH buckets are restricted to
    rated sessions whose start date falls inside the common window
    (calendar-date comparison, inclusive at both ends per Fix 6)."""
    # Meta-only rated sessions (transcript rotated away) still exist in the
    # scoring pool but may be missing from activity_rows entirely — without
    # synthesizing minimal Claude activity for them, their Claude-side
    # presence never reaches _multi_source_intervals, so real overlaps with
    # Codex/Grok go undetected and those sessions are mis-bucketed
    # single-tool. _row_windows' missing-segments fallback (start+duration)
    # and 1-minute minimum handle these synthesized rows the same as any
    # other activity row.
    activity_sids = {r.get("session_id") for r in activity_rows}
    extra = [{"session_id": s["sid"], "start_time": s["start"],
              "duration_minutes": s.get("duration_min") or 0}
             for s in rated if s["sid"] not in activity_sids]
    comparable_pool = list(activity_rows) + extra
    tagged_pool = []
    for r in comparable_pool:
        rr = dict(r)
        rr.setdefault("source", "claude")
        tagged_pool.append(rr)
    tagged_pool += [r for r in cross_rows if r.get("coverage") != "presence_only"]

    window = _common_window_dates(tagged_pool)
    if window is None:
        return _bs_result("switch_tax", False, reason="no multi-source windows")
    win_start_d, win_end_d = window

    multi_iv = _multi_source_intervals(comparable_pool, cross_rows)
    if not multi_iv:
        return _bs_result("switch_tax", False, reason="no multi-source windows")
    multi, single = [], []
    for s in rated:
        st = _parse_dt(s.get("start"))
        if st is None:
            continue
        if not (win_start_d <= st.date() <= win_end_d):
            continue
        # Mirror _row_windows' 1-minute minimum: a 0-minute session would
        # otherwise yield an empty [st, st) probe interval that never
        # overlaps anything, always bucketing it single-tool even when it
        # started inside a real multi-source window.
        en = st + timedelta(minutes=max(s.get("duration_min") or 0, 1))
        hit = any(a < en and st < b for a, b in multi_iv)
        (multi if hit else single).append(s)
    if len(multi) < _BS_SWITCH_MIN_PER_BUCKET or len(single) < _BS_SWITCH_MIN_PER_BUCKET:
        return _bs_result("switch_tax", False,
                          n=min(len(multi), len(single)),
                          reason="fewer than 20 scored sessions in a bucket")

    def side(sessions):
        n = len(sessions)
        return {"n": n,
                "good_rate": round(100 * sum(is_good(s["outcome"]) for s in sessions) / n, 1),
                "friction_per_session": round(
                    sum(sum((s.get("friction_counts") or {}).values())
                        for s in sessions) / n, 2),
                "interrupts_per_session": round(
                    sum(s.get("interrupts") or 0 for s in sessions) / n, 2)}

    return _bs_result("switch_tax", True, n=len(multi) + len(single),
                      metrics={"multi": side(multi), "single": side(single)})


def bs_interrupt_win_rate(rated):
    """Spec §5 #7 — interrupt win-rate, the D5 upgrade: same buckets as
    score_d5_interrupt but symmetric (both rates + delta). Gate mirrors
    D5's literal 5 plus a baseline floor of the same size."""
    interrupted = [s for s in rated if (s.get("interrupts") or 0) > 0]
    baseline = [s for s in rated if not (s.get("interrupts") or 0)]
    if len(interrupted) < 5 or len(baseline) < 5:
        return _bs_result("interrupt_win_rate", False,
                          n=len(interrupted),
                          reason="fewer than 5 sessions in a bucket")

    def rate(ss):
        return round(100 * sum(is_good(s["outcome"]) for s in ss) / len(ss), 1)

    ri, rb = rate(interrupted), rate(baseline)
    return _bs_result("interrupt_win_rate", True, n=len(interrupted),
                      metrics={"interrupted": {"n": len(interrupted), "good_rate": ri},
                               "baseline": {"n": len(baseline), "good_rate": rb},
                               "delta_pp": round(ri - rb, 1)})


_BS_GRAVEYARD_MIN_WRITES = 5
_BS_GRAVEYARD_HORIZON_DAYS = 14   # spec §13
_BS_GRAVEYARD_MIN_ITEMS = 2
_SCRATCH_PATH_MARKERS = ("/tmp/", "/scratchpad", "/private/tmp/")
_WRITE_TOOLS = ("Edit", "Write", "NotebookEdit")
_BS_ASKSHIP_MIN_RATED = 20
_BS_ASKSHIP_MIN_SHIPPED = 5
_BS_NONSHIP_GOALS = {"information_query", "exploration", "quick_question"}
_BS_ASKSHIP_MIN_GAP_PP = 10  # provisional v1: below this, "gap" is noise


def bs_graveyard(activity_rows, window_end):
    """Spec §5 #4 — the graveyard: substantive writes, no commit, project
    untouched >= 14 days after. Structural guards (scratch paths, unknown
    project) replace the outcome guard: achieved-but-never-shipped is
    precisely the finding, not a counterexample.

    Staleness is measured from each row's activity END, not its session
    START: a resumed multi-day session that started 20 days ago but has a
    segment active as recently as yesterday is not stale, even though its
    start_time is old. `_row_windows(row)` already resolves explicit
    segments (else start+duration) per row, so per-project "last touched"
    is the max END across every row's windows, and the qualifying-session
    fields (writes, commits, evidence, last_active_date) come from the row
    that owns that latest end.
    """
    by_project = {}
    for r in activity_rows:
        key = normalize_project_path(r.get("project_path") or "")
        if not is_shippable_project_key(key):
            continue
        # normalize_project_path() strips trailing slashes, so a project
        # rooted exactly at a scratch root ("/tmp", "/private/tmp") no
        # longer contains the "/tmp/"-style marker as a substring. Match
        # the marker as the whole (trailing-slash-stripped) path, as a
        # path-root prefix, or (unchanged) anywhere in the path.
        p = key.lower()
        if any(p == m.rstrip("/") or p.startswith(m.rstrip("/") + "/") or m in p
               for m in _SCRATCH_PATH_MARKERS):
            continue
        windows = _row_windows(r)
        if not windows:
            continue
        row_end = max(e for _, e in windows)
        by_project.setdefault(key, []).append((row_end, r))
    items = []
    for key, entries in by_project.items():
        entries.sort(key=lambda e: e[0])
        last_end, last_row = entries[-1]
        days_untouched = (window_end - last_end).days
        if days_untouched < _BS_GRAVEYARD_HORIZON_DAYS:
            continue
        tc = last_row.get("tool_counts") or {}
        writes = sum(tc.get(t, 0) for t in _WRITE_TOOLS)
        if writes < _BS_GRAVEYARD_MIN_WRITES:
            continue
        if (last_row.get("git_commits") or 0) > 0:
            continue
        items.append({"project_key": project_name(key),
                      "last_active_date": last_end.date().isoformat(),
                      "days_untouched": days_untouched,
                      "writes": writes,
                      "evidence": [last_row.get("session_id") or ""]})
    items.sort(key=lambda i: -i["days_untouched"])
    if len(items) < _BS_GRAVEYARD_MIN_ITEMS:
        return _bs_result("graveyard", False, n=len(items),
                          reason="fewer than 2 qualifying items")
    return _bs_result("graveyard", True, metrics={"items": items[:8]},
                      n=len(items))


def bs_ask_vs_ship(rated):
    """Spec §5 #6 — goal-category share of asks vs share of sessions that
    shipped (git_commits > 0). Non-shipping categories are excluded from
    flagging: asking questions is not a leak (structural guard).

    Shares are SESSION-MEMBERSHIP shares, not goal-tag-count shares: for
    each category, ask_share_pct = 100 * (# rated sessions whose goal_cats
    contains the category) / len(rated); ship_share_pct = 100 * (# shipped
    sessions containing it) / shipped_sessions. A session with multiple
    categories counts once per category it contains — this matches what the
    rendered locale text claims ("% of asks / % of shipped sessions"),
    whereas counting goal-tag occurrences would let a category present in
    every shipped session display as an arbitrary percentage unrelated to
    session counts.
    """
    if len(rated) < _BS_ASKSHIP_MIN_RATED:
        return _bs_result("ask_vs_ship", False, n=len(rated),
                          reason="fewer than 20 scored sessions")
    ask, ship = {}, {}
    shipped_sessions = 0
    for s in rated:
        cats = set((s.get("goal_cats") or {}).keys())
        shipped = (s.get("git_commits") or 0) > 0
        if shipped:
            shipped_sessions += 1
        for c in cats:
            ask[c] = ask.get(c, 0) + 1
            if shipped:
                ship[c] = ship.get(c, 0) + 1
    if not ask or shipped_sessions < _BS_ASKSHIP_MIN_SHIPPED:
        return _bs_result("ask_vs_ship", False, n=len(rated),
                          reason="facets or shipped sessions below floor")
    gaps = []
    for c, n in ask.items():
        if c in _BS_NONSHIP_GOALS:
            continue
        a = 100 * n / len(rated)
        p = 100 * ship.get(c, 0) / shipped_sessions if shipped_sessions else 0.0
        gaps.append((a - p, c, a, p))
    if not gaps:
        return _bs_result("ask_vs_ship", False, n=len(rated),
                          reason="no shippable goal categories present")
    gap_pp, cat, a, p = max(gaps)
    if gap_pp < _BS_ASKSHIP_MIN_GAP_PP:
        return _bs_result("ask_vs_ship", False, n=len(rated),
                          metrics={"top_gap": {"category": cat,
                                               "ask_share_pct": round(a, 1),
                                               "ship_share_pct": round(p, 1),
                                               "gap_pp": round(gap_pp, 1)},
                                   "shipped_sessions": shipped_sessions},
                          reason="no category gap >= 10pp")
    return _bs_result("ask_vs_ship", True, n=len(rated),
                      metrics={"top_gap": {"category": cat,
                                           "ask_share_pct": round(a, 1),
                                           "ship_share_pct": round(p, 1),
                                           "gap_pp": round(gap_pp, 1)},
                               "shipped_sessions": shipped_sessions})


_BS_DRIFT_MIN_WEEKS = 8
_BS_DRIFT_LEN_DROP = 0.75
_BS_DRIFT_GOOD_TOL_PP = 5


def bs_habit_drift(rated):
    """Spec §5 #5 — habit drift: prompt length falling while outcomes are
    not improving. Guard: shorter prompts WITH better outcomes = skill
    gained, suppress (the counterexample guard for this heuristic).

    Weeks are split early/late at the midpoint; a week only counts if it
    has >= GROWTH_MIN_RATED_PER_WEEK rated sessions (same floor the growth
    panel uses, so "8 weeks" means 8 *plottable* weeks, not calendar weeks).
    """
    weeks = {}
    for s in rated:
        dt = _parse_dt(s.get("start"))
        if dt is None:
            continue
        weeks.setdefault(week_key(dt), []).append(s)
    eligible = {w: ss for w, ss in weeks.items()
                if len(ss) >= GROWTH_MIN_RATED_PER_WEEK}
    if len(eligible) < _BS_DRIFT_MIN_WEEKS:
        return _bs_result("habit_drift", False, n=len(eligible),
                          reason="fewer than 8 weeks with enough rated sessions")
    ordered = [eligible[w] for w in sorted(eligible)]
    half = len(ordered) // 2
    early = [s for wk in ordered[:half] for s in wk]
    late = [s for wk in ordered[-half:] for s in wk]

    def med_len(ss):
        # early/late are non-empty by construction (>= 4 eligible weeks each,
        # every eligible week has >= GROWTH_MIN_RATED_PER_WEEK sessions).
        return statistics.median([s.get("first_prompt_len") or
                                  len(s.get("first_prompt") or "")
                                  for s in ss])

    def good_rate(ss):
        return 100 * sum(is_good(s["outcome"]) for s in ss) / len(ss)

    el, ll = med_len(early), med_len(late)
    eg, lg = good_rate(early), good_rate(late)
    metrics = {"weeks": len(eligible),
               "early_median_len": round(el), "late_median_len": round(ll),
               "early_good_rate": round(eg, 1), "late_good_rate": round(lg, 1)}

    shortening = el > 0 and ll <= _BS_DRIFT_LEN_DROP * el
    if not shortening:
        return _bs_result("habit_drift", False, metrics=metrics,
                          n=len(eligible), reason="no shortening trend")

    improved = lg > eg + _BS_DRIFT_GOOD_TOL_PP
    if improved:
        return _bs_result("habit_drift", False, metrics=metrics,
                          n=len(eligible), guarded=True,
                          reason="outcomes improved while prompts shortened")

    # shortening AND good rate flat-or-worse (within tolerance or down) = drift
    return _bs_result("habit_drift", True, metrics=metrics, n=len(eligible))


_BS_FAILED_BURN_MIN_SESSIONS = 5


def _dominant_input_rate(rated):
    """Input $/1M of the most-used model across the rated pool.

    Leaks are lower-bound accounting only (see compute_leaks docstring): an
    unknown/legacy model prices at the CHEAPEST known input rate, not the
    Opus fallback the cost panel uses (_FALLBACK_PRICING) — that fallback's
    over-report policy belongs to the cost panel, not the leak ledger, whose
    guarantee is that every dollar traces to tokens the evidence actually
    shows without inflating the estimate."""
    counts = {}
    for s in rated:
        for m, n in (s.get("model_counts") or {}).items():
            counts[_normalize_model_id(m)] = counts.get(_normalize_model_id(m), 0) + n
    if counts:
        top = max(counts, key=counts.get)
        if top in PRICING:
            return PRICING[top]["input"]
    return min(p["input"] for p in PRICING.values())


def compute_leaks(blind_spots, rated, window):
    """Leak catalog v1 (spec §3 book 3). Lower-bound accounting only:
    every dollar traces to tokens the evidence actually shows (audit
    discipline rule 4). Items are independently gated; 'top 3' is all
    passers ranked by weekly cost.

    Invariant: every USD/token number in leaks is summed over the same
    date window its per-week denominator describes. `rated` spans the
    session-meta pool (longer history than the transcript-derived
    `window`), so costs must be restricted to sessions whose start date
    falls inside `window` before dividing by `weeks` — otherwise the
    numerator sums a longer history than the denominator describes,
    inflating the weekly figure.
    """
    weeks = round(max((window.get("days") or 0) / 7.0, 1.0), 1)
    items = []

    # ledger window bounds are calendar dates, not instants — parse them
    # with date.fromisoformat() directly rather than _parse_dt(...).date().
    # _parse_dt assumes UTC for naive input then converts to local time, so
    # west of UTC "2026-07-11" would shift to 2026-07-10 local and silently
    # exclude sessions that started on the inclusive end date.
    def _safe_date(s):
        try:
            return date.fromisoformat(s) if s else None
        except (TypeError, ValueError):
            return None
    win_start_d = _safe_date(window.get("start"))
    win_end_d = _safe_date(window.get("end"))
    if win_start_d is not None and win_end_d is not None:
        in_window = []
        for s in rated:
            dt = _parse_dt(s.get("start"))
            if dt is None:
                continue
            if win_start_d <= dt.date() <= win_end_d:
                in_window.append(s)
    else:
        in_window = list(rated)

    bs1 = blind_spots.get("repeated_instructions") or {}
    if bs1.get("gate_passed"):
        pats = bs1["metrics"]["patterns"]
        tokens_week = int(sum(p["est_wasted_tokens"] for p in pats) / weeks)
        # USD is priced from the Claude share only (claude_wasted_tokens) —
        # a defensible lower bound. Cross-tool (Codex/Grok) tokens show up
        # in weekly_tokens (the all-source display figure) but are never
        # priced at the Claude input rate, since they weren't billed there.
        claude_tokens_week = sum(
            p.get("claude_wasted_tokens", 0) for p in pats) / weeks
        # Additive field: sorted union of sources across the qualifying
        # patterns, so the renderer can tell whether any occurrences came
        # from a tool that doesn't read CLAUDE.md (Fix 5) and pick the
        # right fix text.
        sources = sorted({src for p in pats for src in (p.get("sources") or [])})
        items.append({"type": "repeated_instructions",
                      "weekly_cost_usd": round(
                          claude_tokens_week / 1e6 * _dominant_input_rate(rated), 2),
                      "weekly_tokens": tokens_week,
                      "occurrences": sum(p["occurrences"] for p in pats),
                      "evidence": pats[0]["evidence"],
                      "sources": sources})

    sunk_sids = set()
    bs2 = blind_spots.get("sunk_cost") or {}
    if bs2.get("gate_passed"):
        pair_sids = [p["failed_sid"] for p in bs2["metrics"]["pairs"]]
        sunk_sids = set(pair_sids)
        # Costed list is windowed; occurrences reflects only the costed
        # (in-window) failed sessions, not the full sunk_cost pair count.
        failed = [s for s in in_window if s["sid"] in sunk_sids]
        # The gate may have passed entirely on out-of-window pairs — only
        # emit the card when at least one failed session actually falls
        # inside the window, otherwise a $0.00 / 0 occurrences / no-evidence
        # card would render for a finding with no in-window support.
        if failed:
            items.append({"type": "sunk_cost",
                          "weekly_cost_usd": round(
                              compute_api_equivalent_cost(failed) / weeks, 2),
                          "weekly_tokens": int(sum(s.get("total_tokens") or 0
                                                   for s in failed) / weeks),
                          "occurrences": len(failed),
                          "evidence": [s["sid"] for s in failed[:3]]})

    burn = [s for s in in_window
            if s["outcome"] == "not_achieved" and s["sid"] not in sunk_sids]
    if len(burn) >= _BS_FAILED_BURN_MIN_SESSIONS:
        items.append({"type": "failed_session_burn",
                      "weekly_cost_usd": round(
                          compute_api_equivalent_cost(burn) / weeks, 2),
                      "weekly_tokens": int(sum(s.get("total_tokens") or 0
                                               for s in burn) / weeks),
                      "occurrences": len(burn),
                      "evidence": [s["sid"] for s in burn[:3]]})

    items.sort(key=lambda i: -(i["weekly_cost_usd"] or 0))
    return {"window_weeks": weeks, "items": items[:3]}


def compute_blind_spots(sessions, rated, activity_rows, cross_rows, window_end,
                        window_start=None):
    """Phase 2 blind-spot engine (spec §5). Additive analysis-data block;
    every heuristic self-gates and the whole entry ships regardless so the
    renderer (and later phases) can see WHY something was suppressed."""
    return {
        "schema_version": 1,
        "repeated_instructions": bs_repeated_instructions(
            activity_rows, cross_rows,
            window_start=window_start, window_end=window_end),
        "sunk_cost": bs_sunk_cost(rated),
        "switch_tax": bs_switch_tax(rated, activity_rows, cross_rows),
        "graveyard": bs_graveyard(activity_rows, window_end),
        "habit_drift": bs_habit_drift(rated),
        "ask_vs_ship": bs_ask_vs_ship(rated),
        "interrupt_win_rate": bs_interrupt_win_rate(rated),
    }


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
    parser.add_argument("--cross-llm-rows", action="append", default=[],
                        help="Path to scan_codex/grok/antigravity output jsonl. "
                             "Repeatable. Rows feed the cross_llm/ledger blocks "
                             "only — never the 9-dim scoring pool.")
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
    #  - scoring_metas: the rich, LLM-labeled subset used for 9-dimension scores
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

    # cross_llm / ledger: additive top-level blocks, computed from the same
    # activity-pool rows compute_activity() uses (activity_metas in
    # --transcript-rows mode, else metas in session-meta mode) plus any
    # --cross-llm-rows adapter output. Never touches scoring_metas/
    # activity_metas themselves — read-only inputs to a new output block.
    activity_rows = activity_metas if activity_metas is not None else metas
    cross_rows, cross_errors = load_cross_llm_rows(args.cross_llm_rows)
    cross_llm = compute_cross_llm(list(activity_rows.values()), cross_rows)
    for card in cross_llm["sources"]:
        card["parse_errors"] = cross_errors.get(card["source"], 0)
    # Errors bucketed under "(unknown)" (malformed JSON, or a row missing
    # both `source` and `start_time` so no source could be guessed) never
    # attach to any per-source card — surface them as a separate count so
    # they aren't silently dropped from the report. 0 default keeps older
    # consumers that don't check this key unaffected.
    cross_llm["unattributed_parse_errors"] = cross_errors.get("(unknown)", 0)
    final["cross_llm"] = cross_llm

    # window_end anchors both blind_spots (graveyard staleness) and
    # ledger.window.end to the newest activity seen — that must be the max
    # END across all activity windows (not max START): a resumed multi-day
    # session's newest activity can land days after its start, and
    # anchoring on start alone would (a) understate days_untouched for
    # every OTHER project in the graveyard check and (b) leave
    # ledger.window.end stale relative to the numerators compute_leaks
    # divides by that same window. blind_spots, leaks, and ledger.window
    # share one end-aware window — compute it once here. window_start
    # stays min start (unaffected).
    all_starts, all_ends = [], []
    for r in activity_rows.values():
        d = _parse_dt(r.get("start_time"))
        if d:
            all_starts.append(d)
        all_ends.extend(e for _, e in _row_windows(r))
    if all_ends:
        window_end = max(all_ends)
    elif all_starts:
        window_end = max(all_starts)
    else:
        window_end = datetime.now().astimezone()
    window_start = min(all_starts) if all_starts else None

    final["ledger"] = compute_ledger(activity_rows, cross_llm, window_end=window_end)

    # blind_spots: additive top-level block (Phase 2, spec §5/§7).
    final["blind_spots"] = compute_blind_spots(
        sessions, rated, list(activity_rows.values()), cross_rows, window_end,
        window_start=window_start)
    final["ledger"]["leaks"] = compute_leaks(
        final["blind_spots"], rated, final["ledger"]["window"])

    out.write_text(json.dumps(final, ensure_ascii=False, indent=2))
    print(f"wrote {out} ({out.stat().st_size} bytes)", file=sys.stderr)
    print(f"sessions={meta['total_sessions']} facets_coverage={meta['facets_coverage_pct']}%",
          file=sys.stderr)
    print(f"overall_avg_score={scores['_overall']['avg']}", file=sys.stderr)


if __name__ == "__main__":
    main()
