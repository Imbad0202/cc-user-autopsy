#!/usr/bin/env python3
"""Scan ~/.claude/projects/**/*.jsonl and produce session-meta-equivalent rows.

Claude Code writes two parallel sources of usage data:
  - ~/.claude/usage-data/session-meta/*.json — summary per session (~14% coverage)
  - ~/.claude/projects/<encoded-path>/<sid>.jsonl — raw transcript (~100% coverage)

session-meta only gets written under conditions this tool doesn't control,
and now covers only the tail of a long session. Transcripts are the ground
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

try:
    from cross_llm_common import (cli_launch_targets, make_cli_launch,
                                   prompt_identity, segments_and_duration,
                                   to_local_iso)
except ImportError:  # pragma: no cover - exercised when imported as scripts.scan_transcripts
    from scripts.cross_llm_common import (cli_launch_targets, make_cli_launch,
                                           prompt_identity,
                                           segments_and_duration,
                                           to_local_iso)

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


# How Claude Code labels a user-role record that a person produced: the
# prompt was typed, typed while the assistant was busy and queued, or an
# offered suggestion the user accepted. Every other label (system, sdk,
# task notifications, messages from peer sessions, scheduled runs) is the
# harness or another program speaking in the user's slot.
HUMAN_PROMPT_SOURCES = frozenset({"typed", "queued", "suggestion_accepted"})
# Session entrypoints that are programmatic by construction (`claude -p`,
# the Agent SDK). Matched by prefix.
_PROGRAMMATIC_ENTRYPOINT_PREFIX = "sdk"

def _content(record):
    """A record's message content, or None when the record has no message
    object (a malformed or truncated line must not stop the scan)."""
    message = record.get("message")
    return message.get("content") if isinstance(message, dict) else None


# Text that opens a user-role record Claude Code wrote for a slash command
# (`/clear`, `!cmd` output), not a prompt a person typed.
_INJECTED_PREFIXES = ("<command-name>", "<command-message>", "<local-command-",
                      "<bash-input>", "<bash-stdout>", "<bash-stderr>")


def _first_text(record):
    """The record's first non-empty text: the whole string content, or the
    first non-empty text block of a list content."""
    content = _content(record)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                return c["text"]
    return ""


def _provenance(record):
    """Who a user-role record's own labels say produced it: "human",
    "other", or None when it carries no label (tool results, and every
    record written by a Claude Code version that predates the labels).
    Every label present must name a person. A label that names anything
    else, or is not the kind of value expected (a list where a word
    should be, an explicit null), makes the record "other"."""
    votes = []
    if "promptSource" in record:
        source = record["promptSource"]
        votes.append(isinstance(source, str) and source in HUMAN_PROMPT_SOURCES)
    if "turnOrigin" in record:
        votes.append(record["turnOrigin"] == "human")
    if "origin" in record:
        origin = record["origin"]
        votes.append(isinstance(origin, dict) and origin.get("kind") == "human")
    if not votes:
        return None
    return "human" if all(votes) else "other"


def _carries_input(record):
    """Whether a user-role record holds something a person could have sent:
    non-blank text (a slash command included) or a non-text block such as
    an image. Tool output, blank text and a missing message do not count."""
    content = _content(record)
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list):
        return False
    for c in content:
        if not isinstance(c, dict):
            continue
        kind = c.get("type")
        if kind == "text":
            if isinstance(c.get("text"), str) and c["text"].strip():
                return True
        elif isinstance(kind, str) and kind and kind != "tool_result":
            return True
    return False


def _launch_time(value):
    """A record's timestamp as the local ISO string the session segments
    use, or None when it is not a usable time. Converting it the same way
    keeps a launch and the session it started on one clock, and keeps any
    other value out of the rows file."""
    dt = _parse_ts(value) if isinstance(value, str) else None
    if dt is None:
        return None
    try:
        return to_local_iso(dt)
    except (OverflowError, ValueError, OSError):
        return None


def _is_programmatic(entrypoint):
    return isinstance(entrypoint, str) \
        and entrypoint.lower().startswith(_PROGRAMMATIC_ENTRYPOINT_PREFIX)


def _is_human_prompt(record):
    """Is this a main-thread user record that its own labels attribute to
    a person, sent through an entrypoint the record itself names and that
    is not a programmatic one? Unlabelled records are never assumed to be
    the user's, and neither is a record that does not say how it arrived
    (every labelled record seen in practice names its entrypoint). The
    entrypoint is read per record, because a session can be resumed
    through a different one. A record with nothing a person could have
    sent (tool output, blank text, no message) is not a prompt, whatever
    labels it carries.

    Entrypoints are told apart by what marks a programmatic one (`sdk-*`),
    not by a list of interactive clients: the editor and desktop clients
    have names of their own, and a list would drop their users."""
    if record.get("type") != "user" or record.get("isSidechain") \
            or record.get("isMeta") or record.get("isCompactSummary") \
            or _provenance(record) != "human" or not _carries_input(record):
        return False
    entrypoint = record.get("entrypoint")
    return isinstance(entrypoint, str) and bool(entrypoint.strip()) \
        and not _is_programmatic(entrypoint)


def _interactive(records):
    """Whether the transcript itself records a person driving the session.

    True   some prompt is labelled as a person's and came through an
           interactive entrypoint
    False  no such prompt, and the transcript does say how it was run:
           some record names a programmatic entrypoint, or prompts are
           labelled and none is a person's (a scheduled run, a
           peer-driven session)
    None   the transcript carries no such labels (older versions)"""
    labelled = False
    for r in records:
        if _is_human_prompt(r):
            return True
        if _is_programmatic(r.get("entrypoint")) or (
                r.get("type") == "user" and not r.get("isSidechain")
                and _provenance(r) is not None):
            labelled = True
    return False if labelled else None


def _cli_launches(records):
    """[{target, ts, until}] for each Bash call, in any thread of the
    transcript, that starts an AI CLI (another tool's, or a fresh
    `claude -p` of its own) — the evidence that a session of that tool
    was launched from here rather than by hand. `until` is
    the timestamp of the call's tool_result (None if never recorded): the
    launched session starts somewhere between the two, and a permission
    prompt can stretch that gap well past a few seconds."""
    launches = []
    by_call_id = {}
    for r in records:
        content = _content(r)
        if not isinstance(content, list):
            continue
        if r.get("type") == "assistant":
            for c in content:
                if not (isinstance(c, dict) and c.get("type") == "tool_use"
                        and c.get("name") == "Bash"):
                    continue
                inp = c.get("input")
                cmd = inp.get("command", "") if isinstance(inp, dict) else ""
                call_id = c.get("id")
                for target in cli_launch_targets(cmd):
                    ev = make_cli_launch(target, _launch_time(r.get("timestamp")))
                    launches.append(ev)
                    # Without a usable id the result cannot be paired:
                    # `until` stays None and the minimum window applies.
                    if isinstance(call_id, str) and call_id:
                        by_call_id.setdefault(call_id, []).append(ev)
        elif r.get("type") == "user" and by_call_id:
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_result" \
                        and isinstance(c.get("tool_use_id"), str):
                    for ev in by_call_id.pop(c["tool_use_id"], []):
                        ev["until"] = _launch_time(r.get("timestamp"))
    return launches


def _load_jsonl(path: Path):
    lines = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if isinstance(rec, dict):
                lines.append(rec)
    return lines


def _scan_usage(records):
    """Return usage totals across assistant records: input/output/cache tokens,
    a model_counts Counter, a (timestamp, output_tokens) sequence per assistant
    message, and tool/git evidence (tool_counts Counter, git_commits,
    git_pushes). Shared by uuid-session and subagent scanning.

    Fix 2/3 (round 11): subagent (agent-*.jsonl) runs previously contributed
    only aggregate token TOTALS and models to their parent row — the merge
    pass (Pass 2 in main()) never saw per-message output timing or tool/git
    evidence, so token_accel was blind to late subagent burn and the
    graveyard heuristic couldn't see delegated Edit/Write/commit activity
    that happened entirely inside a subagent. Returning output_seq and
    tool/git counts here lets Pass 2 merge them into the parent's evidence
    before token_accel and graveyard-relevant fields are derived.

    Fix 1 (round 12): also returns `record_timestamps` — all parseable
    timestamps across every record in the subagent file (not just assistant
    messages), so Pass 2 can merge them into the parent's timestamp sequence
    and rebuild `segments`. A >30-min delegated run with no parent-transcript
    records during it would otherwise be idle-gap-split into two segments
    even though the subagent was active throughout.
    """
    asst = [r for r in records if r.get("type") == "assistant"]
    in_tok = out_tok = cache_create = cache_read = 0
    model_counts = Counter()
    output_seq = []  # list of (timestamp_str, output_tokens)
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
        output_seq.append((r.get("timestamp") or "", u.get("output_tokens", 0) or 0))

    # Tool/git evidence — same detection logic as scan_one's parent-transcript
    # path (reused here rather than duplicated ad hoc), so a subagent's Edit/
    # Write calls and `git commit`/`git push` invocations are visible to
    # bs_graveyard and compute_ledger once merged into the parent row.
    tool_counts = Counter()
    git_commits = git_pushes = 0
    for r in asst:
        content = _content(r)
        if not isinstance(content, list):
            continue
        for c in content:
            if not (isinstance(c, dict) and c.get("type") == "tool_use"):
                continue
            name = c.get("name", "")
            if name:
                tool_counts[name] += 1
            if name != "Bash":
                continue
            cmd = c.get("input", {}).get("command", "") if isinstance(c.get("input"), dict) else ""
            if not isinstance(cmd, str):
                continue
            if re.search(r"\bgit\s+commit\b", cmd):
                git_commits += 1
            if re.search(r"\bgit\s+push\b", cmd):
                git_pushes += 1

    return {
        # A subagent starting another AI CLI is as much a launch as the
        # parent doing it — reviews are routinely delegated this way.
        "cli_launches": _cli_launches(records),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_creation_input_tokens": cache_create,
        "cache_read_input_tokens": cache_read,
        "model_counts": model_counts,
        "output_seq": output_seq,
        "tool_counts": tool_counts,
        "git_commits": git_commits,
        "git_pushes": git_pushes,
        "record_timestamps": _record_timestamps(records),
    }


def _compute_token_accel(output_pairs):
    """token_accel: output burn in the session's second half vs first half.
    Proxy for "flailing": regenerating ever-larger responses late in a
    session. Input tokens are excluded on purpose — context growth makes
    input rise monotonically in every session, which would flag everything.
    For odd n, the middle element belongs to the second half (index n//2
    onward) so every message lands in exactly one half.

    `output_pairs` is a (timestamp_str, output_tokens) sequence, already
    ordered by timestamp (Fix 2: for a merged parent+subagent row, this is
    the union of both sequences re-sorted — see main()'s Pass 2 — so late
    subagent burn is visible to the second-half sum, not just the parent
    transcript's own messages).
    """
    seq = [out_tok for _, out_tok in output_pairs]
    n = len(seq)
    if n < 6:
        return None
    first = sum(seq[: n // 2])
    second = sum(seq[n // 2:])
    if first <= 0:
        return None
    return round(second / first, 2)


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


def _record_timestamps(records):
    """Return all parseable timestamps across records, as datetime objects.
    Used by Pass 2 (Fix 1, round 12) to merge a subagent's own record
    timestamps into the parent's timestamp sequence before rebuilding
    `segments`, so a long delegated run with no parent-transcript activity
    during it doesn't get idle-gap-split even though the subagent was
    active throughout."""
    out = []
    for r in records:
        dt = _parse_ts(r.get("timestamp"))
        if dt:
            out.append(dt)
    return out


def _derive_tool_flags(tool_counts):
    """Derive the uses_* booleans from a tool_counts mapping. Single source
    of truth for the name-based predicates, reused by scan_one (initial
    parent-only computation) and by main()'s Pass 2 (Fix 2, round 12:
    recomputation after subagent tool_counts are merged in) so a
    subagent-only MCP/WebSearch/WebFetch/Task call is never missed.

    uses_subagent: any(name in ("Agent", "Task") for name in tool_counts)
    uses_task_agent: broader — session-meta's definition includes the
      TODO-system tools (TaskCreate/TaskUpdate/TaskList/...), not just
      Agent dispatch.
    """
    names = list(tool_counts)
    return {
        "uses_subagent": any(name in ("Agent", "Task") for name in names),
        "uses_task_agent": any(
            name in ("Agent", "Task", "TaskCreate", "TaskUpdate", "TaskList",
                     "TaskGet", "TaskStop", "TaskOutput", "TodoWrite")
            for name in names
        ),
        "uses_mcp": any(name.startswith("mcp__") for name in names),
        "uses_web_search": "WebSearch" in tool_counts,
        "uses_web_fetch": "WebFetch" in tool_counts,
    }


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
                rec = json.loads(line)
            except Exception:
                continue
            if isinstance(rec, dict):
                lines.append(rec)

    all_user_records = [r for r in lines if r.get("type") == "user"]
    asst_msgs = [r for r in lines if r.get("type") == "assistant"]
    if not all_user_records and not asst_msgs:
        return None

    # "User message" for counting purposes = a user-role record whose content
    # is real text (not a tool_result auto-reply). session-meta uses this
    # definition; matching it lets us cross-validate against the ground truth.
    def _is_text_user(r):
        content = _content(r)
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

    # Split the same timestamps at idle gaps > 30 minutes: `segments` feeds
    # cross-LLM concurrency math, `active_minutes` is the report's work time.
    # duration_minutes above stays the full span.
    segments = None
    active_minutes = 0
    if all_ts:
        segments, active_minutes = segments_and_duration(all_ts)

    in_tok = out_tok = cache_create = cache_read = 0
    model_counts = Counter()
    hit_output_limit = False
    # (timestamp_str, output_tokens) per assistant message, in transcript
    # order. Fix 2: token_accel is no longer computed here — it must first
    # be merged with any subagent output_seq (Pass 2 in main()) so late
    # subagent burn is visible. Rows with no subagents merge against an
    # empty list, which is a no-op, so single-transcript scans (and every
    # existing test that calls scan_one directly) are unaffected.
    assistant_output_pairs = []
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
        assistant_output_pairs.append((r.get("timestamp") or "", u.get("output_tokens", 0) or 0))
        if msg.get("stop_reason") == "max_tokens":
            hit_output_limit = True

    tool_counts = Counter()
    for r in asst_msgs:
        content = _content(r)
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
        content = _content(r)
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
        content = _content(r)
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

    # uses_task_agent is broad (any Task-family tool, including the
    # TaskCreate/TaskUpdate/TaskList TODO system); uses_subagent is the
    # stricter "actually delegated a subagent" signal that scoring reads.
    # Computed here from parent-only tool_counts; main()'s Pass 3 recomputes
    # these (Fix 2, round 12) once subagent tool_counts are merged in.
    tool_flags = _derive_tool_flags(tool_counts)

    # The first prompt a person typed. Skip text Claude Code injects
    # (/clear caveats and skill bodies are isMeta; slash-command records
    # start with a command tag), compaction summaries, and records whose
    # own labels say a person did not type them. Unlabelled records from
    # older transcripts still count.
    first_prompt = ""
    for r in user_msgs:
        if (r.get("isMeta") or r.get("isCompactSummary")
                or _provenance(r) == "other"):
            continue
        text = _first_text(r)
        if text and not text.lstrip().startswith(_INJECTED_PREFIXES):
            first_prompt = text
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
            content = _content(r)
            is_text = False
            if isinstance(content, str):
                is_text = True
            elif isinstance(content, list):
                is_text = any(isinstance(c, dict) and c.get("type") == "text" for c in content)
            if is_text:
                response_times.append(round((ts - prev_asst_ts).total_seconds(), 3))
                prev_asst_ts = None

    # token_accel default: computed from THIS transcript's own messages only.
    # main()'s Pass 2 recomputes it after merging in any subagent output_seq
    # (Fix 2), overwriting this value for rows that have subagent runs; rows
    # without subagents keep exactly this value, so the formula/behavior for
    # non-subagent sessions is unchanged.
    token_accel = _compute_token_accel(assistant_output_pairs)

    return {
        "session_id": sid,
        "project_path": project_path,
        "start_time": start_time,
        "duration_minutes": duration_minutes,
        # Work time: the same span with idle gaps > 30 min removed.
        "active_minutes": active_minutes,
        "segments": segments,
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
        "hit_output_limit": hit_output_limit,
        "token_accel": token_accel,
        "uses_task_agent": tool_flags["uses_task_agent"],
        "uses_subagent": tool_flags["uses_subagent"],
        "uses_mcp": tool_flags["uses_mcp"],
        "uses_web_search": tool_flags["uses_web_search"],
        "uses_web_fetch": tool_flags["uses_web_fetch"],
        "first_prompt": first_prompt,
        # Identity key computed on the FULL prompt text — first_prompt above
        # is not truncated here (scan_transcripts has no 500-char cap), but
        # the hash is still emitted so this row can exact-match against a
        # truncated copy from scan_codex/scan_grok of the same prompt.
        "first_prompt_hash": prompt_identity(first_prompt),
        "user_response_times": response_times,
        "message_hours": msg_hours,
        "lines_added": 0,
        "lines_removed": 0,
        "files_modified": 0,
        # Pipeline-internal only (Fix 2): consumed by main()'s Pass 2 to
        # merge in any subagent output sequence before recomputing
        # token_accel, then stripped in Pass 3 before rows are written to
        # transcript-rows.jsonl. Never part of the emitted row schema.
        "_assistant_output_pairs": assistant_output_pairs,
        # Pipeline-internal only (Fix 1, round 12): this transcript's own
        # record timestamps (datetime objects), consumed by main()'s Pass 2
        # to merge in any subagent record_timestamps before rebuilding
        # `segments`. Stripped in Pass 3, never part of the emitted schema.
        "_all_ts": all_ts,
        # Origin evidence (findings-first Phase 1, read by origin.py).
        "interactive": _interactive(lines),
        "cli_launches": _cli_launches(lines),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR))
    ap.add_argument("--output", required=True)
    ap.add_argument("--min-assistant-msgs", type=int, default=0,
                    help="Drop sessions with fewer than N assistant messages. "
                         "Default 0 (keep all). Use 3 to match session-meta-like "
                         "filtering that excludes warmup/interrupted-at-start sessions. "
                         "Dropped sessions take their launch evidence with "
                         "them: a session one of them started is then "
                         "reported as unknown, not launched.")
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
    #
    # Fix 2/3 (round 11): subagent runs also carry per-message output timing
    # (output_seq) and tool/git evidence (tool_counts, git_commits,
    # git_pushes). Both are merged into the parent row here — output_seq by
    # timestamp-ordered union so token_accel (recomputed below, AFTER the
    # merge, not in scan_one) sees late subagent burn; tool_counts by
    # dict-sum and git_commits/git_pushes by int-add so bs_graveyard and
    # compute_ledger see delegated Edit/Write/commit activity that happened
    # entirely inside a Task/Agent subagent. Rows with no subagent_usages
    # entries never enter this loop, so their token_accel/tool_counts/
    # git_commits/git_pushes are byte-identical to today's values.
    #
    # Fix 1 (round 12): subagent record_timestamps are merged into the
    # parent's own timestamp sequence (_all_ts) and `segments` is rebuilt
    # from the merged, sorted sequence using the same segments_and_duration
    # call the parent path uses. Without this, a >30-min delegated run with no
    # parent-transcript records during it would idle-gap-split into two
    # segments even though the subagent was active throughout, which
    # confuses _row_windows-based concurrency/switch-tax classification.
    #
    # Fix 2 (round 12): uses_mcp/uses_web_search/uses_web_fetch/
    # uses_task_agent/uses_subagent must be recomputed from the MERGED
    # tool_counts (via _derive_tool_flags, the same predicate logic
    # scan_one uses) so a subagent-only MCP/WebSearch/WebFetch/Task call is
    # no longer invisible to these flags. The recomputation itself happens
    # once per row in Pass 3 below (not here) — a parent with N subagent
    # files would otherwise pay for N discarded recomputations when only
    # the value after the last merge is ever kept.
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
            tc = Counter(row.get("tool_counts") or {})
            tc.update(usage["tool_counts"])
            row["tool_counts"] = dict(tc)
            row["git_commits"] = (row.get("git_commits") or 0) + usage["git_commits"]
            row["git_pushes"] = (row.get("git_pushes") or 0) + usage["git_pushes"]
            row["cli_launches"] = (row.get("cli_launches") or []) + usage["cli_launches"]
            row["_assistant_output_pairs"] = (
                row.get("_assistant_output_pairs") or []) + usage["output_seq"]
            row["_all_ts"] = (row.get("_all_ts") or []) + usage["record_timestamps"]
            row["_merged_subagent_tools"] = True
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
                    "hit_output_limit": False,
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
            tc = Counter(orphan.get("tool_counts") or {})
            tc.update(usage["tool_counts"])
            orphan["tool_counts"] = dict(tc)
            # Orphan rows merge subagent tool calls too — mark them so
            # Pass 3 refreshes the derived uses_* flags exactly like it
            # does for merged parent rows (uses_mcp must not stay False
            # while tool_counts carries an mcp__ call).
            orphan["_merged_subagent_tools"] = True
            orphan["cli_launches"] = (orphan.get("cli_launches") or []) + usage["cli_launches"]
            orphan["git_commits"] = (orphan.get("git_commits") or 0) + usage["git_commits"]
            orphan["git_pushes"] = (orphan.get("git_pushes") or 0) + usage["git_pushes"]
            orphan["_assistant_output_pairs"] = (
                orphan.get("_assistant_output_pairs") or []) + usage["output_seq"]
            # Orphan activity windows: merge the subagent record timestamps
            # so Pass 3 builds segments (and an active-duration) for the
            # orphan row too — otherwise _row_windows collapses a
            # multi-hour delegated run to the 1-minute minimum and
            # concurrency/team-ledger math undercounts it.
            orphan["_all_ts"] = (
                orphan.get("_all_ts") or []) + usage["record_timestamps"]
            # Keep the earliest ts seen across fragments as the canonical start.
            ts = usage.get("_earliest_ts", "")
            if ts and (not orphan.get("start_time") or ts < orphan["start_time"]):
                orphan["start_time"] = ts
            n_orphan += 1

    # Pass 3: recompute token_accel from the (now fully merged) output-pair
    # sequence, sorted by timestamp so a subagent's later-timestamped bursts
    # land in the correct half regardless of Pass 1/2 iteration order (Fix
    # 2); rows without subagent_usages entries have a single-source pairs
    # list already in transcript order, so re-sorting is a no-op and their
    # token_accel is unchanged. Then write out, honoring
    # --min-assistant-msgs and stripping the pipeline-internal
    # _assistant_output_pairs field, which is never part of the emitted
    # schema. Orphan rows are exempt from the msg-count filter because their
    # purpose is to carry tokens, not to be scored.
    #
    # Fix 1 (round 12): also rebuild `segments` from the merged _all_ts
    # (parent timestamps + any subagent record_timestamps merged in Pass 2)
    # via the same segments_and_duration() helper cross_llm_common already
    # provides for "sort, split on idle gaps, format as local-iso pairs".
    # Every row gets segments and active_minutes from it; parent rows'
    # duration_minutes keeps scan_one's full-span semantics. Orphan rows
    # (no parent transcript) get BOTH: segments from their subagent record
    # timestamps and duration_minutes from the summed active-segment time.
    # Rows without subagent_usages entries have a single-source _all_ts
    # list identical to what scan_one already used to build `segments`, so
    # re-sorting and re-splitting is a no-op and their segments stay
    # byte-identical (regression guard).
    #
    # Fix 2 (round 12): uses_* flags are recomputed once per row here (not
    # per subagent merge in Pass 2) for rows that received a subagent
    # tool_counts merge, using the same _derive_tool_flags predicate logic
    # scan_one uses.
    n_emitted = 0
    n_filtered = 0
    with out.open("w", encoding="utf-8") as fh:
        for row in rows_by_sid.values():
            pairs = row.pop("_assistant_output_pairs", None)
            if pairs is not None:
                pairs.sort(key=lambda p: p[0] or "")
                row["token_accel"] = _compute_token_accel(pairs)
            all_ts = row.pop("_all_ts", None)
            if all_ts is not None:
                segs, active_min = (segments_and_duration(all_ts)
                                    if all_ts else (None, 0))
                row["segments"] = segs
                row["active_minutes"] = active_min
                # Orphan rows have no parent transcript to define a
                # full-span duration, so their duration IS the summed
                # active-segment time (otherwise a multi-hour delegated
                # run reads as 0 minutes). Parent rows keep scan_one's
                # full-span duration_minutes semantics.
                if row.get("orphan_subagent_only") and not row.get("duration_minutes"):
                    row["duration_minutes"] = active_min
            if row.pop("_merged_subagent_tools", False):
                row.update(_derive_tool_flags(row["tool_counts"]))
                # Orphan rows ARE subagent output by definition — the name
                # predicate can't see the (rotated-away) parent's Agent/Task
                # call, so keep the flag truthful.
                if row.get("orphan_subagent_only"):
                    row["uses_subagent"] = True
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
