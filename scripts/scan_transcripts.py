#!/usr/bin/env python3
"""Scan ~/.claude/projects/**/*.jsonl and produce session-meta-equivalent rows.

Claude Code writes two parallel sources of usage data:
  - ~/.claude/usage-data/session-meta/*.json — summary per session (~14% coverage)
  - ~/.claude/projects/<encoded-path>/<sid>.jsonl — raw transcript (~100% coverage)

session-meta is richer (has LLM-derived `uses_task_agent` etc.) but only gets
written under conditions this tool doesn't control. Transcripts are the ground
truth for everything that can be derived deterministically.

This scanner walks transcripts and emits one JSONL row per session with all
the fields aggregate.py needs, plus three new ones:
  - cache_creation_input_tokens
  - cache_read_input_tokens
  - model_counts (dict model_id -> assistant message count)

Downstream: aggregate.py can consume this via --transcript-rows instead of
--data-dir, giving it full-coverage aggregates rather than session-meta's
partial view.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def _decode_project_path(encoded: str) -> str:
    """Encoded project paths in ~/.claude/projects/ turn '/' into '-' and strip
    the leading /. Decoding is lossy if any directory legitimately starts with
    '-', which is rare enough to ignore.
    """
    if not encoded.startswith("-"):
        return encoded
    return "/" + encoded[1:].replace("-", "/")


def _parse_ts(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


# Tool errors that indicate a user-triggered interrupt (ESC). The canonical
# marker Claude Code emits is a tool_result with is_error=true whose content
# starts with "<tool_use_error>Cancelled: ...". Permissive match on any
# is_error=true tool_result with "Cancelled" or "interrupted" in its content.
_INTERRUPT_RE = re.compile(r"(cancelled|interrupted)", re.IGNORECASE)


import re as _re
_UUID_RE = _re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", _re.I)
_AGENT_RE = _re.compile(r"^agent-", _re.I)


def _load_jsonl(path: Path):
    lines = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except Exception:
                continue
    return lines


def _scan_usage(records):
    """Return usage totals across assistant records: input/output/cache tokens
    plus a model_counts Counter. Shared by uuid-session and subagent scanning."""
    asst = [r for r in records if r.get("type") == "assistant"]
    in_tok = out_tok = cache_create = cache_read = 0
    model_counts = Counter()
    for r in asst:
        msg = r.get("message", {}) if isinstance(r.get("message"), dict) else {}
        model = msg.get("model")
        if model:
            model_counts[model] += 1
        u = msg.get("usage", {}) or {}
        in_tok += u.get("input_tokens", 0) or 0
        out_tok += u.get("output_tokens", 0) or 0
        cache_create += u.get("cache_creation_input_tokens", 0) or 0
        cache_read += u.get("cache_read_input_tokens", 0) or 0
    return {
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_creation_input_tokens": cache_create,
        "cache_read_input_tokens": cache_read,
        "model_counts": model_counts,
    }


def _parent_sid(records):
    """Subagent jsonl records carry the parent session's UUID in the
    `sessionId` field. Return the first one seen, or None."""
    for r in records:
        sid = r.get("sessionId")
        if sid:
            return sid
    return None


def _earliest_timestamp(records):
    """Return the first timestamp string across records, or empty if none."""
    for r in records:
        ts = r.get("timestamp")
        if ts:
            return ts
    return ""


def scan_one(path: Path):
    """Return a session-meta-equivalent dict, or None if the file isn't a
    user-facing session transcript.

    Only UUID-named files are real user sessions. Filenames like 'agent-*'
    are subagent internal runs (each Task/Agent tool invocation creates one)
    and 'skill-injections.jsonl' / others are metadata logs. Including them
    would inflate session counts by ~20× and double-count tokens already
    folded into the parent session via the Task tool's usage reporting.
    """
    if not _UUID_RE.match(path.stem):
        return None

    lines = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except Exception:
                continue

    all_user_records = [r for r in lines if r.get("type") == "user"]
    asst_msgs = [r for r in lines if r.get("type") == "assistant"]
    if not all_user_records and not asst_msgs:
        return None

    # "User message" for counting purposes = a user-role record whose content
    # is real text (not a tool_result auto-reply). session-meta uses this
    # definition; matching it lets us cross-validate against the ground truth.
    def _is_text_user(r):
        content = r.get("message", {}).get("content")
        if isinstance(content, str):
            return bool(content.strip())
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    return True
        return False

    user_msgs = [r for r in all_user_records if _is_text_user(r)]

    encoded_proj = path.parent.name
    project_path = _decode_project_path(encoded_proj)
    sid = path.stem

    all_ts = []
    msg_hours = []
    for r in lines:
        ts = r.get("timestamp")
        if not ts:
            continue
        dt = _parse_ts(ts)
        if dt:
            all_ts.append(dt)
            msg_hours.append(dt.hour)
    all_ts.sort()
    # Emit the original ISO string for start_time, preserving whatever
    # millisecond precision the transcript used (session-meta uses 3-digit ms
    # like ".781Z"; Python's isoformat produces 6-digit microseconds).
    start_time = ""
    if all_ts:
        first_raw = None
        for r in lines:
            ts = r.get("timestamp")
            if ts and _parse_ts(ts) == all_ts[0]:
                first_raw = ts
                break
        start_time = first_raw if first_raw else all_ts[0].isoformat().replace("+00:00", "Z")
    duration_minutes = 0
    if len(all_ts) >= 2:
        duration_minutes = round((all_ts[-1] - all_ts[0]).total_seconds() / 60)

    in_tok = out_tok = cache_create = cache_read = 0
    model_counts = Counter()
    for r in asst_msgs:
        msg = r.get("message", {})
        if not isinstance(msg, dict):
            continue
        model = msg.get("model")
        if model:
            model_counts[model] += 1
        u = msg.get("usage", {}) or {}
        in_tok += u.get("input_tokens", 0) or 0
        out_tok += u.get("output_tokens", 0) or 0
        cache_create += u.get("cache_creation_input_tokens", 0) or 0
        cache_read += u.get("cache_read_input_tokens", 0) or 0

    tool_counts = Counter()
    for r in asst_msgs:
        content = r.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                name = c.get("name", "")
                if name:
                    tool_counts[name] += 1

    tool_errors = 0
    user_interruptions = 0
    for r in all_user_records:
        content = r.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if not (isinstance(c, dict) and c.get("type") == "tool_result"):
                continue
            if c.get("is_error"):
                tool_errors += 1
                txt = c.get("content", "")
                if not isinstance(txt, str):
                    txt = json.dumps(txt, ensure_ascii=False)
                if _INTERRUPT_RE.search(txt):
                    user_interruptions += 1

    git_commits = git_pushes = 0
    for r in asst_msgs:
        content = r.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if not (isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Bash"):
                continue
            cmd = c.get("input", {}).get("command", "") if isinstance(c.get("input"), dict) else ""
            if not isinstance(cmd, str):
                continue
            if re.search(r"\bgit\s+commit\b", cmd):
                git_commits += 1
            if re.search(r"\bgit\s+push\b", cmd):
                git_pushes += 1

    # session-meta defines uses_task_agent broadly — any use of Task-family
    # tools including TaskCreate/TaskUpdate/TaskList (the TODO system), not
    # just Agent dispatch. Match that definition so scores are comparable.
    # uses_subagent is the stricter "actually delegated a subagent" signal.
    uses_subagent = any(name in ("Agent", "Task") for name in tool_counts)
    uses_task_agent = any(
        name in ("Agent", "Task", "TaskCreate", "TaskUpdate", "TaskList",
                 "TaskGet", "TaskStop", "TaskOutput", "TodoWrite")
        for name in tool_counts
    )
    uses_mcp = any(name.startswith("mcp__") for name in tool_counts)
    uses_web_search = "WebSearch" in tool_counts
    uses_web_fetch = "WebFetch" in tool_counts

    first_prompt = ""
    for r in user_msgs:
        content = r.get("message", {}).get("content")
        if isinstance(content, str):
            first_prompt = content
            break
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    t = c.get("text", "")
                    if t:
                        first_prompt = t
                        break
            if first_prompt:
                break

    response_times = []
    prev_asst_ts = None
    for r in lines:
        t = r.get("type")
        ts = _parse_ts(r.get("timestamp", ""))
        if not ts:
            continue
        if t == "assistant":
            prev_asst_ts = ts
        elif t == "user" and prev_asst_ts is not None:
            content = r.get("message", {}).get("content")
            is_text = False
            if isinstance(content, str):
                is_text = True
            elif isinstance(content, list):
                is_text = any(isinstance(c, dict) and c.get("type") == "text" for c in content)
            if is_text:
                response_times.append(round((ts - prev_asst_ts).total_seconds(), 3))
                prev_asst_ts = None

    return {
        "session_id": sid,
        "project_path": project_path,
        "start_time": start_time,
        "duration_minutes": duration_minutes,
        "user_message_count": len(user_msgs),
        "assistant_message_count": len(asst_msgs),
        "tool_counts": dict(tool_counts),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_creation_input_tokens": cache_create,
        "cache_read_input_tokens": cache_read,
        "model_counts": dict(model_counts),
        "git_commits": git_commits,
        "git_pushes": git_pushes,
        "user_interruptions": user_interruptions,
        "tool_errors": tool_errors,
        "uses_task_agent": uses_task_agent,
        "uses_subagent": uses_subagent,
        "uses_mcp": uses_mcp,
        "uses_web_search": uses_web_search,
        "uses_web_fetch": uses_web_fetch,
        "first_prompt": first_prompt,
        "user_response_times": response_times,
        "message_hours": msg_hours,
        "lines_added": 0,
        "lines_removed": 0,
        "files_modified": 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    ap.add_argument("--output", required=True)
    ap.add_argument("--min-assistant-msgs", type=int, default=0,
                    help="Drop sessions with fewer than N assistant messages. "
                         "Default 0 (keep all). Use 3 to match session-meta-like "
                         "filtering that excludes warmup/interrupted-at-start sessions.")
    args = ap.parse_args()

    projects_dir = Path(args.projects_dir).expanduser()
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    # Pass 1: scan every uuid-named jsonl (one row per real session) and
    # every agent-* jsonl (subagent fragments). Keep them in memory because
    # we need to merge subagents into their parent session before emitting.
    rows_by_sid = {}        # parent_sid -> row dict
    subagent_usages = []    # list of (parent_sid, usage_dict)
    n_scanned = 0
    for f in projects_dir.glob("**/*.jsonl"):
        n_scanned += 1
        stem = f.stem
        if _UUID_RE.match(stem):
            row = scan_one(f)
            if row is None:
                continue
            rows_by_sid[row["session_id"]] = row
        elif _AGENT_RE.match(stem):
            records = _load_jsonl(f)
            if not records:
                continue
            parent = _parent_sid(records)
            if not parent:
                continue
            usage = _scan_usage(records)
            usage["_earliest_ts"] = _earliest_timestamp(records)
            subagent_usages.append((parent, usage))

    # Pass 2: merge subagent usage into parent rows; orphans (parent
    # transcript absent from disk) get a synthetic row so their tokens are
    # still visible to downstream cost/activity aggregation.
    n_merged = 0
    n_orphan = 0
    for parent, usage in subagent_usages:
        row = rows_by_sid.get(parent)
        if row is not None:
            row["input_tokens"] += usage["input_tokens"]
            row["output_tokens"] += usage["output_tokens"]
            row["cache_creation_input_tokens"] += usage["cache_creation_input_tokens"]
            row["cache_read_input_tokens"] += usage["cache_read_input_tokens"]
            mc = Counter(row["model_counts"])
            mc.update(usage["model_counts"])
            row["model_counts"] = dict(mc)
            n_merged += 1
        else:
            # Synthetic orphan row — minimal fields; downstream aggregate.py
            # uses these for activity token/model pool only, not scoring.
            orphan = rows_by_sid.get(parent)
            if orphan is None:
                # Orphan start_time = earliest subagent record timestamp, so
                # aggregate.py can place it on the timeline / active-day
                # accounting instead of silently dropping the row.
                orphan = {
                    "session_id": parent,
                    "project_path": "",
                    "start_time": usage.get("_earliest_ts", ""),
                    "duration_minutes": 0,
                    "user_message_count": 0,
                    "assistant_message_count": sum(usage["model_counts"].values()),
                    "tool_counts": {},
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "model_counts": {},
                    "git_commits": 0, "git_pushes": 0,
                    "user_interruptions": 0, "tool_errors": 0,
                    "uses_task_agent": False, "uses_subagent": True,
                    "uses_mcp": False, "uses_web_search": False, "uses_web_fetch": False,
                    "first_prompt": "",
                    "user_response_times": [],
                    "message_hours": [],
                    "lines_added": 0, "lines_removed": 0, "files_modified": 0,
                    "orphan_subagent_only": True,
                }
                rows_by_sid[parent] = orphan
            orphan["input_tokens"] += usage["input_tokens"]
            orphan["output_tokens"] += usage["output_tokens"]
            orphan["cache_creation_input_tokens"] += usage["cache_creation_input_tokens"]
            orphan["cache_read_input_tokens"] += usage["cache_read_input_tokens"]
            mc = Counter(orphan["model_counts"])
            mc.update(usage["model_counts"])
            orphan["model_counts"] = dict(mc)
            orphan["assistant_message_count"] = sum(mc.values())
            # Keep the earliest ts seen across fragments as the canonical start.
            ts = usage.get("_earliest_ts", "")
            if ts and (not orphan.get("start_time") or ts < orphan["start_time"]):
                orphan["start_time"] = ts
            n_orphan += 1

    # Pass 3: write out, honoring --min-assistant-msgs. Orphan rows are
    # exempt from that filter because their purpose is to carry tokens, not
    # to be scored.
    n_emitted = 0
    n_filtered = 0
    with out.open("w", encoding="utf-8") as fh:
        for row in rows_by_sid.values():
            if (not row.get("orphan_subagent_only")) and \
                    row["assistant_message_count"] < args.min_assistant_msgs:
                n_filtered += 1
                continue
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_emitted += 1

    msg = (f"scanned {n_scanned} jsonl files, emitted {n_emitted} session rows "
           f"to {out} (merged {n_merged} subagent runs into parents, "
           f"{n_orphan} orphan subagent fragments)")
    if n_filtered:
        msg += f" ({n_filtered} filtered by --min-assistant-msgs={args.min_assistant_msgs})"
    print(msg, file=sys.stderr)


if __name__ == "__main__":
    main()
