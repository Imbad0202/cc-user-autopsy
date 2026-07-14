#!/usr/bin/env python3
"""Scan Antigravity conversation files into presence-only rows.

~/.gemini/antigravity/conversations/*.pb is protobuf with no public
schema. Per spec: NO reverse engineering — file count + mtime only.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

try:
    from cross_llm_common import write_rows
except ImportError:  # pragma: no cover - exercised when imported as scripts.scan_antigravity
    from scripts.cross_llm_common import write_rows

DEFAULT_CONVERSATIONS_DIR = (
    Path.home() / ".gemini" / "antigravity" / "conversations")

_NULL_FIELDS = (
    "duration_minutes", "segments", "user_message_count",
    "assistant_message_count", "tool_counts", "input_tokens",
    "output_tokens", "cache_read_input_tokens",
    "cache_creation_input_tokens", "model_counts", "first_prompt",
)


def scan_conversations_dir(root: Path):
    rows = []
    if not root.is_dir():
        return rows
    for p in sorted(root.glob("*.pb")):
        mtime = datetime.fromtimestamp(p.stat().st_mtime).astimezone()
        row = {"session_id": p.stem, "project_path": "",
               "start_time": mtime.isoformat(),
               "source": "antigravity", "coverage": "presence_only"}
        for k in _NULL_FIELDS:
            row[k] = None
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conversations-dir", default=str(DEFAULT_CONVERSATIONS_DIR))
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    rows = scan_conversations_dir(Path(args.conversations_dir).expanduser())
    write_rows(rows, args.output)
    print(f"antigravity: {len(rows)} conversations (presence only)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
