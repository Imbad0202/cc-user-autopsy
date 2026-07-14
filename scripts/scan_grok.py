#!/usr/bin/env python3
"""Scan Grok CLI prompt histories into cc-user-autopsy cross-LLM rows.

~/.grok/sessions/<urlencoded-cwd>/prompt_history.jsonl has prompt text,
session_id, timestamp, is_bash — no tokens, no model, no tool calls.
Coverage tier: partial. Unknown fields are null, never imputed.
"""
import argparse
import sys
from pathlib import Path
from urllib.parse import unquote

try:
    from cross_llm_common import (
        parse_jsonl_object, parse_ts, segments_and_duration, to_local_iso, write_rows)
except ImportError:  # pragma: no cover - exercised when imported as scripts.scan_grok
    from scripts.cross_llm_common import (
        parse_jsonl_object, parse_ts, segments_and_duration, to_local_iso, write_rows)

DEFAULT_SESSIONS_DIR = Path.home() / ".grok" / "sessions"


def scan_sessions_dir(root: Path):
    rows = []
    parse_errors = 0
    if not root.is_dir():
        return rows, parse_errors
    for d in sorted(root.iterdir()):
        hist = d / "prompt_history.jsonl"
        if not hist.is_file():
            continue
        project_path = unquote(d.name)
        sessions = {}
        with open(hist, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = parse_jsonl_object(line)
                if rec is None:
                    parse_errors += 1
                    continue
                ts = parse_ts(rec.get("timestamp"))
                sid = rec.get("session_id")
                if not ts or not sid:
                    parse_errors += 1
                    continue
                s = sessions.setdefault(
                    sid, {"ts": [], "prompts": 0, "bash": 0, "first": None})
                s["ts"].append(ts)
                s["prompts"] += 1
                if rec.get("is_bash"):
                    s["bash"] += 1
                if s["first"] is None:
                    text = rec.get("prompt")
                    if isinstance(text, str) and text.strip():
                        s["first"] = text.strip()[:500]
        for sid, s in sessions.items():
            ts = sorted(s["ts"])
            segments, duration = segments_and_duration(ts)
            rows.append({
                "session_id": sid,
                "project_path": project_path,
                "start_time": to_local_iso(ts[0]),
                "duration_minutes": duration,
                "segments": segments,
                "user_message_count": s["prompts"],
                "assistant_message_count": None,
                "tool_counts": {"Bash": s["bash"]} if s["bash"] else {},
                "input_tokens": None,
                "output_tokens": None,
                "cache_read_input_tokens": None,
                "cache_creation_input_tokens": None,
                "model_counts": None,
                "first_prompt": s["first"],
                "source": "grok",
                "coverage": "partial",
            })
    return rows, parse_errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS_DIR))
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    rows, errors = scan_sessions_dir(Path(args.sessions_dir).expanduser())
    # Trailing meta line — how the scanner's own skip-count reaches
    # aggregate.py's cross_llm.sources[].parse_errors (see
    # docs/SCHEMA-CHANGES.md). load_cross_llm_rows() consumes "_meta" rows
    # instead of treating them as sessions.
    rows.append({"_meta": True, "source": "grok", "parse_errors": errors})
    write_rows(rows, args.output)
    print(f"grok: {len(rows) - 1} sessions, {errors} parse errors", file=sys.stderr)


if __name__ == "__main__":
    main()
