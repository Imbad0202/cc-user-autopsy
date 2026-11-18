#!/usr/bin/env python3
"""Scan OpenAI Codex CLI rollout logs into cc-user-autopsy cross-LLM rows.

Reads ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl (one file per session;
resumed sessions append to the same file across days, so activity is split
into idle-gap segments). Emits scan_transcripts-shaped rows plus
source/coverage/segments. Missing signals stay null, never imputed.
"""
import argparse
import sys
from pathlib import Path

try:
    from cross_llm_common import (
        add_user_turns_arg, cli_launch_targets, make_cli_launch,
        make_user_turn, parse_jsonl_object, parse_ts, prompt_identity,
        segments_and_duration, to_local_iso, write_rows)
except ImportError:  # pragma: no cover - exercised when imported as scripts.scan_codex
    from scripts.cross_llm_common import (
        add_user_turns_arg, cli_launch_targets, make_cli_launch,
        make_user_turn, parse_jsonl_object, parse_ts, prompt_identity,
        segments_and_duration, to_local_iso, write_rows)

DEFAULT_SESSIONS_DIR = Path.home() / ".codex" / "sessions"


def _launch_source(payload):
    """How the session header says the session was started, as one
    lowercase word, or None when the header does not say. A non-string
    value is the header of a spawned sub-session."""
    src = payload.get("source")
    if isinstance(src, str) and src.strip():
        return src.strip().lower()
    if isinstance(src, dict):
        return "subagent"
    return None


def _shell_command(payload):
    """The command text of a function_call payload, or "". `arguments` is
    a JSON string whose `command` is a string or an argv list. Only
    decoded when the raw text names another AI CLI at all — most calls
    do not, and decoding every one would double the JSON work per call."""
    args = payload.get("arguments")
    if not isinstance(args, str) or not cli_launch_targets(args, "codex"):
        return ""
    parsed = parse_jsonl_object(args)
    if parsed is None:
        return ""
    cmd = parsed.get("command")
    if isinstance(cmd, list):
        return " ".join(c for c in cmd if isinstance(c, str))
    return cmd if isinstance(cmd, str) else ""


def scan_one(path: Path, turns_out=None):
    """Returns (row, parse_errors). When turns_out is a list, the prompts
    the user typed are appended to it (raw text — see cross_llm_common)."""
    session_id = None
    launch_source = None
    turns = []
    cli_launches = []
    launches_by_call = {}
    last_assistant = None
    replied_since_turn = False
    multi_turn = False
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
                launch_source = _launch_source(payload) or launch_source
            elif rtype == "turn_context":
                model = payload.get("model") or model
                cwd = payload.get("cwd") or cwd
            elif rtype == "event_msg":
                ptype = payload.get("type")
                if ptype == "user_message":
                    user_msgs += 1
                    text = payload.get("message")
                    stripped = text.strip() if isinstance(text, str) else ""
                    if stripped:
                        if turns and replied_since_turn:
                            multi_turn = True
                        turns.append((ts, stripped, last_assistant))
                        replied_since_turn = False
                    if first_prompt is None:
                        if stripped:
                            # Hash the FULL prompt before truncating for
                            # display (Fix 3) — identity must survive the
                            # 500-char display cap below.
                            first_prompt_hash = prompt_identity(stripped)
                            first_prompt = stripped[:500]
                elif ptype == "agent_message":
                    asst_msgs += 1
                    replied_since_turn = True
                    reply = payload.get("message")
                    if isinstance(reply, str) and reply.strip():
                        last_assistant = reply
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
                    if ts:
                        for target in cli_launch_targets(
                                _shell_command(payload), "codex"):
                            ev = make_cli_launch(target, to_local_iso(ts))
                            cli_launches.append(ev)
                            launches_by_call.setdefault(
                                payload.get("call_id"), []).append(ev)
                elif payload.get("type") == "function_call_output" and ts:
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
        "launch_source": launch_source,
        "multi_turn": multi_turn,
        "cli_launches": cli_launches,
    }
    if turns_out is not None:
        for i, (tts, text, prev) in enumerate(turns):
            turns_out.append(make_user_turn(
                "codex", session_id, cwd or "",
                to_local_iso(tts) if tts else "", i, text,
                prev_assistant=prev))
    return row, parse_errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS_DIR))
    ap.add_argument("--output", required=True)
    add_user_turns_arg(ap)
    args = ap.parse_args()
    root = Path(args.sessions_dir).expanduser()
    rows = []
    total_errors = 0
    user_turns = [] if args.user_turns_output else None
    if root.is_dir():
        for p in sorted(root.glob("*/*/*/rollout-*.jsonl")):
            row, errors = scan_one(p, user_turns)
            total_errors += errors
            if row:
                rows.append(row)
    # Trailing meta line — how the scanner's own skip-count reaches
    # aggregate.py's cross_llm.sources[].parse_errors (see
    # docs/SCHEMA-CHANGES.md). load_cross_llm_rows() consumes "_meta" rows
    # instead of treating them as sessions.
    rows.append({"_meta": True, "source": "codex", "parse_errors": total_errors})
    write_rows(rows, args.output)
    if user_turns is not None:
        write_rows(user_turns, args.user_turns_output)
    print(f"codex: {len(rows) - 1} sessions, {total_errors} parse errors",
          file=sys.stderr)


if __name__ == "__main__":
    main()
