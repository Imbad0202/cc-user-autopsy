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
        parse_jsonl_object, parse_ts, segments_and_duration, to_local_iso, write_rows)
except ImportError:  # pragma: no cover - exercised when imported as scripts.scan_codex
    from scripts.cross_llm_common import (
        parse_jsonl_object, parse_ts, segments_and_duration, to_local_iso, write_rows)

DEFAULT_SESSIONS_DIR = Path.home() / ".codex" / "sessions"


def scan_one(path: Path):
    session_id = None
    cwd = None
    model = None
    user_msgs = 0
    asst_msgs = 0
    tool_counts = {}
    first_prompt = None
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
                            first_prompt = text.strip()[:500]
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
        "source": "codex",
        "coverage": "full",
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
