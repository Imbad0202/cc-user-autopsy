"""
cc-user-autopsy Step 2: sample representative sessions.
Reads analysis-data.json, picks up to 24 representative sessions,
finds each session's transcript (.jsonl) under ~/.claude/projects/,
writes a compact summary to samples.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict, deque

DEFAULT_PROJECTS_DIR = Path.home() / ".claude/projects"

HEAD_KEEP = 10
TAIL_KEEP = 10


import re as _re
_SID_RE = _re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


def build_jsonl_index(projects_dir: Path) -> dict[str, Path]:
    """Build a sid → path index by scanning transcripts once.

    Two passes: first by filename stem (covers most transcripts in Claude Code's
    native layout), then a head scan of remaining files for embedded sid
    substrings. Total I/O stays O(jsonl count) rather than O(picks × jsonl).
    """
    index: dict[str, Path] = {}
    unresolved: list[Path] = []

    for f in projects_dir.rglob("*.jsonl"):
        stem = f.stem
        if _SID_RE.fullmatch(stem):
            index.setdefault(stem, f)
        else:
            unresolved.append(f)

    for f in unresolved:
        try:
            with open(f, "r") as fp:
                head = "".join(fp.readline() for _ in range(3))
        except Exception:
            continue
        for match in _SID_RE.findall(head):
            index.setdefault(match, f)

    return index


def stream_summary(jsonl_path: Path):
    """Stream the transcript once, producing (summarized_turns, total_turns).

    Keeps only the first HEAD_KEEP meaningful summaries plus a rolling deque
    of the last TAIL_KEEP — never loads the whole file into memory.
    """
    head: list[dict] = []
    tail: deque = deque(maxlen=TAIL_KEEP)
    total = 0
    try:
        with open(jsonl_path, "r") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                turn = _summarize_one(rec)
                if turn is None:
                    continue
                if len(head) < HEAD_KEEP:
                    head.append(turn)
                else:
                    tail.append(turn)
    except Exception as e:
        return None, total, str(e)

    out = list(head)
    if tail and total > HEAD_KEEP + TAIL_KEEP:
        skipped = total - len(head) - len(tail)
        if skipped > 0:
            out.append({"role": "_skip", "n_skipped": skipped})
    out.extend(tail)
    return out, total, None


def _summarize_one(rec) -> dict | None:
    """Reduce one raw JSONL record to the compact turn format, or None to skip."""
    msg = rec.get("message") or {}
    role = msg.get("role")
    content = msg.get("content", "")

    if role == "user":
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for blk in content:
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "text":
                    parts.append(blk.get("text", ""))
                elif blk.get("type") == "tool_result":
                    c = blk.get("content", "")
                    if isinstance(c, list):
                        c = " ".join(
                            b.get("text", "")[:120] for b in c
                            if isinstance(b, dict)
                        )
                    parts.append(f"[tool_result: {str(c)[:120]}]")
            text = "\n".join(parts)
        if text.strip() and not text.startswith("[tool_result"):
            return {"role": "user", "text": text[:700]}
        return None

    if role == "assistant":
        text_parts = []
        tool_names = []
        if isinstance(content, list):
            for blk in content:
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "text":
                    text_parts.append(blk.get("text", ""))
                elif blk.get("type") == "tool_use":
                    tool_names.append(blk.get("name", ""))
        text = " ".join(text_parts)
        if text.strip() or tool_names:
            return {
                "role": "assistant",
                "text": text[:350],
                "tools": tool_names[:10],
            }
    return None


def pick_representatives(sessions, have_facets):
    picks = {}

    def add(tag, s):
        picks.setdefault(s["sid"], (tag, s))

    # Always: top tokens, top interrupts (they don't need facets)
    for s in sorted(sessions, key=lambda x: -x["total_tokens"])[:5]:
        add("top_token", s)
    for s in sorted(sessions, key=lambda x: -x["interrupts"])[:5]:
        if s["interrupts"] > 0:
            add("top_interrupt", s)

    if have_facets:
        # Highest friction
        fric_sessions = [s for s in sessions if s["friction_counts"]]
        for s in sorted(fric_sessions,
                        key=lambda x: -sum(x["friction_counts"].values()))[:5]:
            add("high_friction", s)

        # not_achieved
        for s in [s for s in sessions if s["outcome"] == "not_achieved"][:4]:
            add("not_achieved", s)

        # partially_achieved (highest friction within)
        partials = [s for s in sessions if s["outcome"] == "partially_achieved"]
        for s in sorted(
            partials, key=lambda x: -sum(x["friction_counts"].values())
        )[:3]:
            add("partial", s)

        # control: fully_achieved + essential, diverse projects
        ess_by_proj = defaultdict(list)
        for s in sessions:
            if s["outcome"] == "fully_achieved" and s["helpfulness"] == "essential":
                ess_by_proj[s.get("project_key") or s["project"]].append(s)
        for proj in list(ess_by_proj.keys())[:4]:
            best = max(ess_by_proj[proj], key=lambda x: x["total_tokens"])
            add("control_good", best)

        # user_rejected_action
        rej = [
            s for s in sessions
            if s["friction_counts"]
            and "user_rejected_action" in s["friction_counts"]
        ]
        for s in rej[:2]:
            add("user_rejected", s)
    else:
        # No facets — grab highest-duration sessions as proxies
        for s in sorted(sessions, key=lambda x: -x["duration_min"])[:5]:
            add("long_duration", s)

    return picks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="analysis-data.json path")
    ap.add_argument("--output", required=True, help="samples.json output path")
    ap.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR),
                    help="override projects dir")
    args = ap.parse_args()

    projects_dir = Path(args.projects_dir).expanduser()

    data = json.loads(Path(args.input).expanduser().read_text())
    sessions = data.get("_sessions", [])
    have_facets = data["meta"]["sessions_with_facets"] > 0

    picks = pick_representatives(sessions, have_facets)
    print(f"picked {len(picks)} representative sessions", file=sys.stderr)

    index = build_jsonl_index(projects_dir)
    print(f"indexed {len(index)} transcripts", file=sys.stderr)

    samples = {}
    for sid, (tag, s) in picks.items():
        jsonl = index.get(sid)
        entry = {"tag": tag, "meta": s}
        if not jsonl:
            entry["error"] = "jsonl not found"
            samples[sid] = entry
            continue
        compact, total, err = stream_summary(jsonl)
        if err:
            entry["error"] = err
            entry["jsonl_path"] = str(jsonl)
            samples[sid] = entry
            continue
        entry["jsonl_path"] = str(jsonl)
        entry["total_turns"] = total
        entry["compact_turns"] = compact
        samples[sid] = entry

    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(samples, ensure_ascii=False, indent=2))
    found = sum(1 for v in samples.values() if v.get("compact_turns"))
    print(f"wrote {out}, {found}/{len(samples)} had transcripts", file=sys.stderr)


if __name__ == "__main__":
    main()
