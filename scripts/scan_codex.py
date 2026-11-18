#!/usr/bin/env python3
"""Scan OpenAI Codex CLI rollout logs into cc-user-autopsy cross-LLM rows.

Reads ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl (one file per session;
resumed sessions append to the same file across days, so activity is split
into idle-gap segments). Emits scan_transcripts-shaped rows plus
source/coverage/segments. Missing signals stay null, never imputed.
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    from cross_llm_common import (
        cli_launch_targets, make_cli_launch, parse_jsonl_object, parse_ts,
        prompt_identity, segments_and_duration, to_local_iso, write_rows)
except ImportError:  # pragma: no cover - exercised when imported as scripts.scan_codex
    from scripts.cross_llm_common import (
        cli_launch_targets, make_cli_launch, parse_jsonl_object, parse_ts,
        prompt_identity, segments_and_duration, to_local_iso, write_rows)

DEFAULT_SESSIONS_DIR = Path.home() / ".codex" / "sessions"


def _launch_source(payload):
    """How the session header says the session was started, as one
    lowercase word, or None when the header does not say (or says it in
    a form this scanner does not know). A spawned sub-session's header
    carries an object naming the sub-agent instead of a word."""
    src = payload.get("source")
    if isinstance(src, str) and src.strip():
        return src.strip().lower()
    if isinstance(src, dict) and "subagent" in src:
        return SPAWNED_SOURCE
    return None


# Header launch sources that are an interactive client (the terminal UI,
# the editor extension) and those that are a non-interactive run.
INTERACTIVE_SOURCES = frozenset({"cli", "vscode"})
NON_INTERACTIVE_SOURCES = frozenset({"exec", "mcp"})


SPAWNED_SOURCE = "subagent"


def _session_source(sources):
    """One launch source for the row from every header's: the spawned
    mark if any header carries it, else the first non-interactive one,
    else the last one named. None when no header names a source."""
    named = [src for src in sources if src]
    if SPAWNED_SOURCE in named:
        return SPAWNED_SOURCE
    for src in named:
        if src in NON_INTERACTIVE_SOURCES:
            return src
    return named[-1] if named else None


def _session_interactive(sources):
    """False when any header names a non-interactive run. True only when
    every header names an interactive client: a rollout with one stretch
    whose header does not say how it was run is not vouched for as a
    whole by the stretches that do. None otherwise."""
    if any(src in NON_INTERACTIVE_SOURCES for src in sources):
        return False
    if sources and all(src in INTERACTIVE_SOURCES for src in sources):
        return True
    return None


def _is_shell_tool(name):
    """Whether a tool name is one that runs a command line. Codex has
    renamed its shell tool across versions (shell, local_shell,
    exec_command, ...), so this matches the family, and leaves out tools
    whose arguments are file content (apply_patch) where a CLI's name is
    only a word."""
    low = name.lower() if isinstance(name, str) else ""
    return not _SHELL_WORDS.isdisjoint(re.split(r"[^a-z]+", low))


# Whole words of a tool name, so `exec_command` and `local_shell` match
# and `execute_sql` does not.
_SHELL_WORDS = frozenset({"shell", "exec", "bash", "command"})

# Argument fields that hold the command line. Only they are read: other
# fields (the working directory, an approval rule, a note, a query) can
# name a CLI without running it, and a tool that merely has "exec" in
# its name has none of them.
_COMMAND_KEYS = frozenset({"command", "cmd", "commands", "script", "argv", "args"})


_JSON_ESCAPE_RE = re.compile(r"\\.")


def _strings(value):
    """Every string inside a decoded JSON value, depth-first."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _call_text(payload):
    """The command line of a function_call, or "". Tools name the field
    differently (`command` as a string or an argv list, `cmd`, ...), so
    the fields in _COMMAND_KEYS are read; arguments that are not a JSON
    object (a bare string, a list) are read whole.

    The arguments are decoded only when they can name an AI CLI at all:
    most calls do not, and decoding every one would double the JSON work
    per call. That first look is at the raw JSON text with every escape
    sequence blanked, so an escaped newline or quote next to a name
    (`\ncodex`, `codex\"`) does not hide it; the decoded text is what
    is matched for real."""
    args = payload.get("arguments")
    if not isinstance(args, str) \
            or not cli_launch_targets(_JSON_ESCAPE_RE.sub(" ", args)):
        return ""
    try:
        decoded = json.loads(args)
        if isinstance(decoded, dict):
            decoded = [v for k, v in decoded.items() if k in _COMMAND_KEYS]
        return "\n".join(_strings(decoded))
    except (ValueError, RecursionError):
        # Not JSON, or nested too deeply to walk: read it as plain text.
        return args


def scan_one(path: Path):
    session_id = None
    # A rollout can be resumed, and each resume writes a header of its
    # own: one entry per header, None for a header that names no source.
    sources = []
    cli_launches = []
    launches_by_call = {}
    cwd = None
    model = None
    user_msgs = 0
    asst_msgs = 0
    tool_counts = {}
    first_prompt = None
    first_prompt_hash = None
    usage = None
    timestamps = []
    parse_errors = 0
    model_counts = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = parse_jsonl_object(line)
            if rec is None:
                parse_errors += 1
                continue
            ts = parse_ts(rec.get("timestamp"))
            if ts:
                timestamps.append(ts)
            payload = rec.get("payload")
            if payload is not None and not isinstance(payload, dict):
                parse_errors += 1
                continue
            payload = payload or {}
            rtype = rec.get("type")
            if rtype == "session_meta":
                session_id = payload.get("id")
                cwd = payload.get("cwd") or cwd
                sources.append(_launch_source(payload))
            elif rtype == "turn_context":
                model = payload.get("model") or model
                cwd = payload.get("cwd") or cwd
            elif rtype == "event_msg":
                ptype = payload.get("type")
                if ptype == "user_message":
                    user_msgs += 1
                    if first_prompt is None:
                        text = payload.get("message")
                        if isinstance(text, str) and text.strip():
                            stripped = text.strip()
                            # Hash the FULL prompt before truncating for
                            # display (Fix 3) — identity must survive the
                            # 500-char display cap below.
                            first_prompt_hash = prompt_identity(stripped)
                            first_prompt = stripped[:500]
                elif ptype == "agent_message":
                    asst_msgs += 1
                    # Attribute to whichever model is currently active (the
                    # most recent turn_context seen so far), not the LAST
                    # turn_context in the whole file — sessions can switch
                    # models mid-stream (e.g. after a /model command).
                    if model:
                        model_counts[model] = model_counts.get(model, 0) + 1
                elif ptype == "token_count":
                    info = payload.get("info")
                    if isinstance(info, dict) and info.get("total_token_usage"):
                        usage = info["total_token_usage"]  # cumulative; keep last
            elif rtype == "response_item":
                if payload.get("type") == "function_call":
                    name = payload.get("name") or "(unknown)"
                    tool_counts[name] = tool_counts.get(name, 0) + 1
                    if ts and _is_shell_tool(name):
                        for target in cli_launch_targets(_call_text(payload)):
                            ev = make_cli_launch(target, to_local_iso(ts))
                            cli_launches.append(ev)
                            if isinstance(payload.get("call_id"), str) \
                                    and payload["call_id"]:
                                launches_by_call.setdefault(
                                    payload["call_id"], []).append(ev)
                elif payload.get("type") == "function_call_output" and ts \
                        and isinstance(payload.get("call_id"), str):
                    # The call's result: the launched session started
                    # somewhere between the request and this moment.
                    for ev in launches_by_call.pop(payload.get("call_id"), []):
                        ev["until"] = to_local_iso(ts)
    if session_id is None or not timestamps:
        return None, parse_errors
    timestamps.sort()
    segments, duration = segments_and_duration(timestamps)
    row = {
        "session_id": session_id,
        "project_path": cwd or "",
        "start_time": to_local_iso(timestamps[0]),
        "duration_minutes": duration,
        "segments": segments,
        "user_message_count": user_msgs,
        "assistant_message_count": asst_msgs,
        "tool_counts": tool_counts,
        "input_tokens": usage.get("input_tokens") if usage else None,
        "output_tokens": usage.get("output_tokens") if usage else None,
        "cache_read_input_tokens": usage.get("cached_input_tokens") if usage else None,
        "cache_creation_input_tokens": None,
        "reasoning_output_tokens": usage.get("reasoning_output_tokens") if usage else None,
        "model_counts": model_counts or None,
        "first_prompt": first_prompt,
        "first_prompt_hash": first_prompt_hash,
        "source": "codex",
        "coverage": "full",
        # Origin evidence (findings-first Phase 1, read by origin.py).
        "launch_source": _session_source(sources),
        "interactive": _session_interactive(sources),
        "cli_launches": cli_launches,
    }
    return row, parse_errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS_DIR))
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    root = Path(args.sessions_dir).expanduser()
    rows = []
    total_errors = 0
    if root.is_dir():
        for p in sorted(root.glob("*/*/*/rollout-*.jsonl")):
            row, errors = scan_one(p)
            total_errors += errors
            if row:
                rows.append(row)
    # Trailing meta line — how the scanner's own skip-count reaches
    # aggregate.py's cross_llm.sources[].parse_errors (see
    # docs/SCHEMA-CHANGES.md). load_cross_llm_rows() consumes "_meta" rows
    # instead of treating them as sessions.
    rows.append({"_meta": True, "source": "codex", "parse_errors": total_errors})
    write_rows(rows, args.output)
    print(f"codex: {len(rows) - 1} sessions, {total_errors} parse errors",
          file=sys.stderr)


if __name__ == "__main__":
    main()
