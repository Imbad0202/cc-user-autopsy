# V5 Phase 1 — Cross-LLM Adapters + Ledger Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land Phase 1 of the AI-work-ledger redesign: three cross-LLM scanner adapters (Codex / Grok / Antigravity), `aggregate.py --cross-llm-rows` with new additive `cross_llm` + `ledger` blocks, the snapshot hook in `build_html.py`, the SELF report skeleton (opening band, output ledger, team ledger) in direction-C business-report style, `generate_demo_data.py` extended to four sources, and the SKILL.md Step 1/3 rewrite.

**Architecture:** Adapters are standalone stdlib scripts mirroring `scan_transcripts.py`'s row contract, plus `source` / `coverage` / `segments` fields, sharing helpers via a new `scripts/cross_llm_common.py`. `aggregate.py` keeps the two existing pools untouched and adds two *top-level* additive blocks (`cross_llm`, `ledger`) computed from Claude activity rows + cross-LLM rows. `report_render.py` gains three new SELF-only sections styled with direction-C tokens; HR output is untouched except privacy assertions. Spec: `docs/superpowers/specs/2026-07-14-ai-work-ledger-redesign.md` (approved 2026-07-14).

**Tech Stack:** Python 3.9+ stdlib only (pytest for tests), inline HTML/CSS in `report_render.py`, no new JS.

## Global Constraints

- Python 3.9+ **standard library only** at runtime (spec repo rule; pytest is test-only).
- Output HTML fully self-contained: no remote assets; all user-derived text through `esc()` / `json_for_script()` (enforced by `tests/smoke_test.py`).
- `locales.py`: en and zh_TW must share the exact same key set; zh_TW values must not contain `—`; `t()` raises KeyError on miss (enforced by `tests/test_locales.py`).
- Adapter tests use **synthetic fixtures only, never real user data** (spec §11 — stricter than the env-var convention in `test_scan_transcripts.py`).
- `analysis-data.json` is an external schema: new blocks are **additive**, documented in `docs/SCHEMA-CHANGES.md` **in the same commit** as the code change.
- Cross-LLM rows: missing fields are `null`, **never imputed** (spec §6). All adapter timestamps normalized to local timezone with explicit UTC offset in the ISO string.
- No cross-LLM prompt text ever renders in HR/external output (spec §4). New ledger sections are SELF-only in Phase 1.
- 9-dim scoring pool stays Claude-only (spec §6) — cross-LLM rows must never enter `scoring_metas`.
- Direction-C visual grammar (spec §8): gold `#B08A2E` single accent (deep `#7E6119`), negative red `#9C201A` only for bad numbers, numbered Exhibits with source lines, action-title section heads.
- Common cross-source window < **14 days** → comparison exhibits degrade to per-source panels with an explanatory note (spec §13).
- Conventional-commit subjects; both test suites (`python3 -m pytest tests/ -q` and `node --test tests/chart_layout.test.mjs`) must pass per task. Known baseline: 2 pre-existing failures in `tests/test_build_html_additions.py` on clean main (PR #24 staleness) — not yours to fix here, but do not add new failures.

## Known deviations from spec (decided at plan time — carry into implementation-notes)

1. **`segments` field** (beyond spec's "plus two fields"): rollout files for these tools are appended to again when a session resumes days later (a file can span 10+ days). Treating `[start, start+duration]` as one activity window would fabricate many days of parallel activity for a resumed session. Adapters therefore also emit `segments`: activity windows split at idle gaps > 30 min. Claude rows don't have it; aggregation falls back to `[start, start+duration]` for them.
2. **Phase 1 exhibits are HTML/CSS, not canvas**: weekly tool-share (stacked bars), parallel heatmap (CSS grid), project × tool matrix (table), head-to-head (card) are rendered server-side as HTML. No changes to `js/chart_layout.js`. Canvas polish, if wanted, is Phase 3 work.
3. **Praise-word lint deferred to Phase 2** (spec lists it under Rendering but Phase 1's narrative surface is small; it lands with the leak ledger where most prose lives). SKILL.md Step 3 rewrite in this phase embeds the audit-discipline rules as writing instructions.
4. **Ledger narration file**: the opening line + per-book opener claims are LLM-written (SKILL.md Step 3) and enter the build via a new `--ledger-narration <md>` flag, structured with `# opening` / `# output-ledger` / `# team-ledger` headings.

---

### Task 1: `scripts/cross_llm_common.py` — shared adapter helpers

**Files:**
- Create: `scripts/cross_llm_common.py`
- Test: `tests/test_cross_llm_common.py`

**Interfaces:**
- Produces: `parse_ts(s: str) -> Optional[datetime]` (aware, UTC on `Z`); `to_local_iso(dt: datetime) -> str` (ISO-8601 with local offset); `split_segments(timestamps: list[datetime], gap_minutes: int = 30) -> list[list[datetime]]` (sorted input → list of `[start, end]` pairs); `write_rows(rows: list[dict], output: str) -> None` (jsonl, `ensure_ascii=False`). Constant `SEGMENT_GAP_MINUTES = 30`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cross_llm_common.py
import unittest
from datetime import datetime, timedelta, timezone

from scripts.cross_llm_common import parse_ts, split_segments, to_local_iso


class ParseTsTests(unittest.TestCase):
    def test_z_suffix_parses_as_utc(self):
        dt = parse_ts("2026-04-20T02:44:00.313Z")
        self.assertEqual(dt.tzinfo.utcoffset(dt), timedelta(0))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_ts("not-a-date"))
        self.assertIsNone(parse_ts(None))


class ToLocalIsoTests(unittest.TestCase):
    def test_output_carries_utc_offset(self):
        dt = datetime(2026, 4, 20, 2, 44, tzinfo=timezone.utc)
        s = to_local_iso(dt)
        # aware ISO string: ends with +HH:MM / -HH:MM offset (never bare, never Z)
        self.assertRegex(s, r"[+-]\d{2}:\d{2}$")


class SplitSegmentsTests(unittest.TestCase):
    def _ts(self, *minutes):
        base = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
        return [base + timedelta(minutes=m) for m in minutes]

    def test_single_cluster_is_one_segment(self):
        ts = self._ts(0, 5, 12, 20)
        segs = split_segments(ts)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0], [ts[0], ts[-1]])

    def test_resumed_session_splits_at_gap(self):
        # models a resumed rollout file: reopened and appended to 10 days later
        ts = self._ts(0, 10) + self._ts(14400, 14405)  # +10 days
        segs = split_segments(ts)
        self.assertEqual(len(segs), 2)
        active = sum((e - s).total_seconds() for s, e in segs) / 60
        self.assertEqual(active, 15)  # 10 + 5, not 14405

    def test_empty_input(self):
        self.assertEqual(split_segments([]), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cross_llm_common.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'scripts.cross_llm_common'` (note: other tests import via `scripts.` package path only if an `__init__.py` or sys.path trick exists — check how `tests/test_scan_transcripts.py` imports the scanner and copy that exact import mechanism; adjust the test import to match).

- [ ] **Step 3: Write the implementation**

```python
# scripts/cross_llm_common.py
"""Shared helpers for the cross-LLM scanner adapters.

The adapters (scan_codex.py, scan_grok.py, scan_antigravity.py) emit the
same row shape as scan_transcripts.py plus `source` and `coverage`, and —
for sources whose log files can span multiple days (a session resumed
days later reopens and appends to the same rollout file) — a `segments`
list of activity windows split at idle gaps, so parallel detection never
counts idle days as active time.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

SEGMENT_GAP_MINUTES = 30


def parse_ts(s) -> Optional[datetime]:
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def to_local_iso(dt: datetime) -> str:
    return dt.astimezone().isoformat()


def split_segments(timestamps, gap_minutes: int = SEGMENT_GAP_MINUTES):
    if not timestamps:
        return []
    from datetime import timedelta
    gap = timedelta(minutes=gap_minutes)
    segs = []
    seg_start = prev = timestamps[0]
    for ts in timestamps[1:]:
        if ts - prev > gap:
            segs.append([seg_start, prev])
            seg_start = ts
        prev = ts
    segs.append([seg_start, prev])
    return segs


def write_rows(rows, output) -> None:
    out = Path(output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cross_llm_common.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/cross_llm_common.py tests/test_cross_llm_common.py
git commit -m "feat(cross-llm): shared adapter helpers (ts parse, local ISO, segment split)"
```

---

### Task 2: `scripts/scan_codex.py` — Codex adapter (full tier)

**Files:**
- Create: `scripts/scan_codex.py`
- Test: `tests/test_scan_codex.py`

**Interfaces:**
- Consumes: `cross_llm_common.parse_ts / to_local_iso / split_segments / write_rows`.
- Produces: CLI `python3 scripts/scan_codex.py --sessions-dir <dir> --output <jsonl>` (`--sessions-dir` defaults to `~/.codex/sessions`). Function `scan_one(path: Path) -> tuple[Optional[dict], int]` returning `(row, parse_error_count)`. Row fields: `session_id, project_path, start_time, duration_minutes, segments, user_message_count, assistant_message_count, tool_counts, input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens (None), reasoning_output_tokens, model_counts, first_prompt, source="codex", coverage="full"`.

Event format verified against the vendor's current rollout format: each `rollout-*.jsonl` line is `{"timestamp": "...Z", "type": ..., "payload": {...}}`. Relevant types: `session_meta` (payload: `id`, `cwd`), `turn_context` (payload: `model`, `effort`, `cwd`), `event_msg` (payload.type ∈ `user_message` / `agent_message` / `token_count`; token_count payload.info may be `null`, else `info.total_token_usage = {input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens}` — cumulative, take the **last** non-null), `response_item` (payload.type `function_call` has `name`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scan_codex.py
import json
import tempfile
import unittest
from pathlib import Path

from scripts.scan_codex import scan_one  # match the repo's import mechanism


def _line(ts, type_, payload):
    return json.dumps({"timestamp": ts, "type": type_, "payload": payload})


def make_rollout(dirpath: Path, lines) -> Path:
    p = dirpath / "2026" / "04" / "20" / "rollout-2026-04-20T10-00-00-test.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


BASE = [
    _line("2026-04-20T02:00:00.000Z", "session_meta",
          {"id": "0000-codex-1", "cwd": "/home/user/projects/webapp"}),
    _line("2026-04-20T02:00:01.000Z", "turn_context",
          {"model": "gpt-5.4", "effort": "high", "cwd": "/home/user/projects/webapp"}),
    _line("2026-04-20T02:00:02.000Z", "event_msg",
          {"type": "user_message", "message": "fix the flaky test"}),
    _line("2026-04-20T02:00:10.000Z", "response_item",
          {"type": "function_call", "name": "shell"}),
    _line("2026-04-20T02:01:00.000Z", "event_msg",
          {"type": "token_count", "info": None}),
    _line("2026-04-20T02:05:00.000Z", "event_msg",
          {"type": "token_count",
           "info": {"total_token_usage": {
               "input_tokens": 22112, "cached_input_tokens": 2432,
               "output_tokens": 596, "reasoning_output_tokens": 279,
               "total_tokens": 22708}}}),
    _line("2026-04-20T02:06:00.000Z", "event_msg",
          {"type": "agent_message", "message": "done"}),
]


class ScanCodexTests(unittest.TestCase):
    def test_parses_full_session(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_rollout(Path(td), BASE)
            row, errors = scan_one(p)
        self.assertEqual(errors, 0)
        self.assertEqual(row["session_id"], "0000-codex-1")
        self.assertEqual(row["project_path"], "/home/user/projects/webapp")
        self.assertEqual(row["source"], "codex")
        self.assertEqual(row["coverage"], "full")
        self.assertEqual(row["user_message_count"], 1)
        self.assertEqual(row["assistant_message_count"], 1)
        self.assertEqual(row["tool_counts"], {"shell": 1})
        self.assertEqual(row["input_tokens"], 22112)
        self.assertEqual(row["cache_read_input_tokens"], 2432)
        self.assertEqual(row["output_tokens"], 596)
        self.assertEqual(row["reasoning_output_tokens"], 279)
        self.assertIsNone(row["cache_creation_input_tokens"])
        self.assertEqual(row["model_counts"], {"gpt-5.4": 1})
        self.assertEqual(row["first_prompt"], "fix the flaky test")

    def test_start_time_is_local_with_offset(self):
        with tempfile.TemporaryDirectory() as td:
            row, _ = scan_one(make_rollout(Path(td), BASE))
        self.assertRegex(row["start_time"], r"[+-]\d{2}:\d{2}$")

    def test_resumed_session_duration_excludes_idle_gap(self):
        resumed = BASE + [
            _line("2026-04-30T09:00:00.000Z", "event_msg",
                  {"type": "user_message", "message": "continue"}),
            _line("2026-04-30T09:05:00.000Z", "event_msg",
                  {"type": "agent_message", "message": "ok"}),
        ]
        with tempfile.TemporaryDirectory() as td:
            row, _ = scan_one(make_rollout(Path(td), resumed))
        self.assertEqual(len(row["segments"]), 2)
        self.assertLess(row["duration_minutes"], 30)  # 6min + 5min, not 10 days

    def test_malformed_lines_counted_not_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_rollout(Path(td), BASE + ["{not json", ""])
            row, errors = scan_one(p)
        self.assertEqual(errors, 1)
        self.assertIsNotNone(row)

    def test_file_without_session_meta_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_rollout(Path(td), [BASE[2]])
            row, errors = scan_one(p)
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_scan_codex.py -q`
Expected: FAIL with module-not-found for `scripts.scan_codex`.

- [ ] **Step 3: Write the implementation**

```python
# scripts/scan_codex.py
#!/usr/bin/env python3
"""Scan OpenAI Codex CLI rollout logs into cc-user-autopsy cross-LLM rows.

Reads ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl (one file per session;
resumed sessions append to the same file across days, so activity is split
into idle-gap segments). Emits scan_transcripts-shaped rows plus
source/coverage/segments. Missing signals stay null, never imputed.
"""
import argparse
import json
import sys
from pathlib import Path

from cross_llm_common import parse_ts, split_segments, to_local_iso, write_rows

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
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            ts = parse_ts(rec.get("timestamp"))
            if ts:
                timestamps.append(ts)
            payload = rec.get("payload") or {}
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
    segs = split_segments(timestamps)
    duration = round(sum((e - s).total_seconds() for s, e in segs) / 60)
    row = {
        "session_id": session_id,
        "project_path": cwd or "",
        "start_time": to_local_iso(timestamps[0]),
        "duration_minutes": duration,
        "segments": [[to_local_iso(s), to_local_iso(e)] for s, e in segs],
        "user_message_count": user_msgs,
        "assistant_message_count": asst_msgs,
        "tool_counts": tool_counts,
        "input_tokens": usage.get("input_tokens") if usage else None,
        "output_tokens": usage.get("output_tokens") if usage else None,
        "cache_read_input_tokens": usage.get("cached_input_tokens") if usage else None,
        "cache_creation_input_tokens": None,
        "reasoning_output_tokens": usage.get("reasoning_output_tokens") if usage else None,
        "model_counts": {model: asst_msgs} if model and asst_msgs else None,
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
    write_rows(rows, args.output)
    print(f"codex: {len(rows)} sessions, {total_errors} parse errors",
          file=sys.stderr)


if __name__ == "__main__":
    main()
```

Note: use the same import mechanism as `scan_transcripts.py` uses for any intra-`scripts/` imports; if scripts are run as files (not a package), `from cross_llm_common import ...` works because they share a directory. Make the test's import path match `tests/test_scan_transcripts.py`'s convention.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_scan_codex.py tests/test_cross_llm_common.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/scan_codex.py tests/test_scan_codex.py
git commit -m "feat(cross-llm): Codex adapter (full tier) with resumed-session segment split"
```

---

### Task 3: `scripts/scan_grok.py` + `scripts/scan_antigravity.py`

**Files:**
- Create: `scripts/scan_grok.py`, `scripts/scan_antigravity.py`
- Test: `tests/test_scan_grok.py`, `tests/test_scan_antigravity.py`

**Interfaces:**
- Produces: CLIs `scan_grok.py --sessions-dir <dir> --output <jsonl>` (default `~/.grok/sessions`) and `scan_antigravity.py --conversations-dir <dir> --output <jsonl>` (default `~/.gemini/antigravity/conversations`). Grok rows: `coverage="partial"`, `source="grok"`, tokens/model all `None`, `tool_counts={"Bash": n}` when bash prompts exist else `{}`. Antigravity rows: `coverage="presence_only"`, `source="antigravity"`, only `session_id` (file stem) + `start_time` (file mtime, local ISO) populated; every other row field `None` (`project_path` is `""`).

Verified Grok format: dir name is URL-encoded cwd (e.g. `%2FUsers%2Fdemo`), `prompt_history.jsonl` lines are `{"timestamp": "...Z", "session_id": ..., "prompt": ..., "is_bash": bool}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scan_grok.py
import json
import tempfile
import unittest
from pathlib import Path

from scripts.scan_grok import scan_sessions_dir


def make_grok(root: Path, dirname: str, lines):
    d = root / dirname
    d.mkdir(parents=True)
    (d / "prompt_history.jsonl").write_text(
        "\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")


class ScanGrokTests(unittest.TestCase):
    def test_urlencoded_cwd_is_decoded(self):
        with tempfile.TemporaryDirectory() as td:
            make_grok(Path(td), "%2Fhome%2Fuser%2Fprojects%2Fwebapp", [
                {"timestamp": "2026-06-24T06:46:27.778811Z",
                 "session_id": "g-1", "prompt": "explain this repo", "is_bash": False},
            ])
            rows, errors = scan_sessions_dir(Path(td))
        self.assertEqual(errors, 0)
        self.assertEqual(rows[0]["project_path"], "/home/user/projects/webapp")
        self.assertEqual(rows[0]["source"], "grok")
        self.assertEqual(rows[0]["coverage"], "partial")

    def test_groups_by_session_id_and_counts_bash(self):
        with tempfile.TemporaryDirectory() as td:
            make_grok(Path(td), "%2Fx", [
                {"timestamp": "2026-06-24T06:00:00Z", "session_id": "g-1",
                 "prompt": "ls the repo", "is_bash": True},
                {"timestamp": "2026-06-24T06:05:00Z", "session_id": "g-1",
                 "prompt": "now fix it", "is_bash": False},
                {"timestamp": "2026-06-24T07:00:00Z", "session_id": "g-2",
                 "prompt": "unrelated", "is_bash": False},
            ])
            rows, _ = scan_sessions_dir(Path(td))
        by_sid = {r["session_id"]: r for r in rows}
        self.assertEqual(len(rows), 2)
        self.assertEqual(by_sid["g-1"]["user_message_count"], 2)
        self.assertEqual(by_sid["g-1"]["tool_counts"], {"Bash": 1})
        self.assertEqual(by_sid["g-1"]["duration_minutes"], 5)
        self.assertIsNone(by_sid["g-1"]["input_tokens"])
        self.assertIsNone(by_sid["g-1"]["model_counts"])
        self.assertEqual(by_sid["g-1"]["first_prompt"], "ls the repo")

    def test_malformed_line_counted(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "%2Fx"
            d.mkdir()
            (d / "prompt_history.jsonl").write_text(
                '{"timestamp": "2026-06-24T06:00:00Z", "session_id": "g-1", '
                '"prompt": "p", "is_bash": false}\n{broken\n', encoding="utf-8")
            rows, errors = scan_sessions_dir(Path(td))
        self.assertEqual(errors, 1)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
```

```python
# tests/test_scan_antigravity.py
import os
import tempfile
import unittest
from pathlib import Path

from scripts.scan_antigravity import scan_conversations_dir


class ScanAntigravityTests(unittest.TestCase):
    def test_presence_only_rows(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "00000000-0000-4000-8000-00000000a915.pb"
            p.write_bytes(b"\x00\x01")  # opaque; never parsed
            os.utime(p, (1776600000, 1776600000))
            rows = scan_conversations_dir(Path(td))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["session_id"], "00000000-0000-4000-8000-00000000a915")
        self.assertEqual(row["source"], "antigravity")
        self.assertEqual(row["coverage"], "presence_only")
        self.assertRegex(row["start_time"], r"[+-]\d{2}:\d{2}$")
        for k in ("duration_minutes", "segments", "user_message_count",
                  "assistant_message_count", "tool_counts", "input_tokens",
                  "output_tokens", "model_counts", "first_prompt"):
            self.assertIsNone(row[k], k)

    def test_missing_dir_returns_empty(self):
        self.assertEqual(scan_conversations_dir(Path("/nonexistent/xyz")), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_scan_grok.py tests/test_scan_antigravity.py -q`
Expected: FAIL with module-not-found.

- [ ] **Step 3: Write the implementations**

```python
# scripts/scan_grok.py
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

import json

from cross_llm_common import parse_ts, split_segments, to_local_iso, write_rows

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
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
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
            segs = split_segments(ts)
            rows.append({
                "session_id": sid,
                "project_path": project_path,
                "start_time": to_local_iso(ts[0]),
                "duration_minutes": round(
                    sum((e - b).total_seconds() for b, e in segs) / 60),
                "segments": [[to_local_iso(b), to_local_iso(e)] for b, e in segs],
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
    write_rows(rows, args.output)
    print(f"grok: {len(rows)} sessions, {errors} parse errors", file=sys.stderr)


if __name__ == "__main__":
    main()
```

```python
# scripts/scan_antigravity.py
#!/usr/bin/env python3
"""Scan Antigravity conversation files into presence-only rows.

~/.gemini/antigravity/conversations/*.pb is protobuf with no public
schema. Per spec: NO reverse engineering — file count + mtime only.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from cross_llm_common import write_rows

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
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_scan_grok.py tests/test_scan_antigravity.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/scan_grok.py scripts/scan_antigravity.py tests/test_scan_grok.py tests/test_scan_antigravity.py
git commit -m "feat(cross-llm): Grok (partial) and Antigravity (presence-only) adapters"
```

---

### Task 4: `generate_demo_data.py` — synthetic data for all four sources

**Files:**
- Modify: `scripts/generate_demo_data.py` (add after the existing `main()` body; new dirs beside the existing `META_DIR`/`FACETS_DIR`/`PROJECTS_DIR` constants at lines 16-26)
- Test: `tests/test_demo_data.py` (extend)

**Interfaces:**
- Produces: `/tmp/cc-autopsy-demo/codex-sessions/YYYY/MM/DD/rollout-*.jsonl` (≥30 sessions, ≥1 resumed multi-day file), `/tmp/cc-autopsy-demo/grok-sessions/<urlencoded>/prompt_history.jsonl` (≥2 cwd dirs, ≥15 sessions, one prompt containing the XSS marker `<script>alert("grok")</script> GROK_PRIVATE_MARKER`), `/tmp/cc-autopsy-demo/antigravity-conversations/*.pb` (≥5 dummy files). New module constants `CODEX_DIR`, `GROK_DIR`, `ANTIGRAVITY_DIR`; new functions `gen_codex_sessions()`, `gen_grok_sessions()`, `gen_antigravity_files()` called from `main()`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_demo_data.py`, following its existing structure — it asserts on the generated tree)

```python
class CrossLlmDemoDataTests(unittest.TestCase):
    def test_codex_demo_tree(self):
        files = list((OUT_DIR / "codex-sessions").glob("*/*/*/rollout-*.jsonl"))
        self.assertGreaterEqual(len(files), 30)
        # at least one file must span multiple days (resumed session)
        from scripts.scan_codex import scan_one
        multi = 0
        for f in files:
            row, errors = scan_one(f)
            self.assertIsNotNone(row, f)
            self.assertEqual(errors, 0, f)
            if row["segments"] and len(row["segments"]) > 1:
                multi += 1
        self.assertGreaterEqual(multi, 1)

    def test_grok_demo_tree_contains_xss_marker(self):
        hists = list((OUT_DIR / "grok-sessions").glob("*/prompt_history.jsonl"))
        self.assertGreaterEqual(len(hists), 2)
        blob = "".join(h.read_text() for h in hists)
        self.assertIn("GROK_PRIVATE_MARKER", blob)

    def test_antigravity_demo_files(self):
        pbs = list((OUT_DIR / "antigravity-conversations").glob("*.pb"))
        self.assertGreaterEqual(len(pbs), 5)
```

(`OUT_DIR` import: match how `tests/test_demo_data.py` already references the demo tree.)

- [ ] **Step 2: Run to verify failure**

Run: `python3 scripts/generate_demo_data.py && python3 -m pytest tests/test_demo_data.py -q`
Expected: the three new tests FAIL (dirs missing).

- [ ] **Step 3: Implement generators** (append to `generate_demo_data.py`; reuse its existing `random` seeding and `now` conventions from `main()`, lines 422-430)

```python
CODEX_DIR = OUT_DIR / "codex-sessions"
GROK_DIR = OUT_DIR / "grok-sessions"
ANTIGRAVITY_DIR = OUT_DIR / "antigravity-conversations"

DEMO_PROJECTS_CROSS = ["webapp", "data-pipeline", "infra"]


def _codex_line(ts, type_, payload):
    return json.dumps({"timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                       "type": type_, "payload": payload})


def gen_codex_sessions(now, n=32):
    for i in range(n):
        start = now - timedelta(days=int(random.triangular(0, 60, 20)),
                                hours=random.randint(0, 12))
        sid = mk_sid()
        proj = random.choice(DEMO_PROJECTS_CROSS)
        cwd = f"/home/user/projects/{proj}"
        lines = [
            _codex_line(start, "session_meta", {"id": sid, "cwd": cwd}),
            _codex_line(start, "turn_context",
                        {"model": "gpt-5.4", "effort": "high", "cwd": cwd}),
        ]
        t = start
        for turn in range(random.randint(1, 6)):
            t += timedelta(minutes=random.randint(1, 8))
            lines.append(_codex_line(t, "event_msg",
                                     {"type": "user_message",
                                      "message": f"demo codex prompt {turn}"}))
            t += timedelta(minutes=random.randint(1, 5))
            lines.append(_codex_line(t, "response_item",
                                     {"type": "function_call", "name": "shell"}))
            lines.append(_codex_line(t, "event_msg",
                                     {"type": "agent_message", "message": "ok"}))
        lines.append(_codex_line(t, "event_msg", {"type": "token_count", "info": {
            "total_token_usage": {
                "input_tokens": random.randint(5000, 90000),
                "cached_input_tokens": random.randint(1000, 30000),
                "output_tokens": random.randint(500, 9000),
                "reasoning_output_tokens": random.randint(100, 3000),
                "total_tokens": 0}}}))
        if i == 0:  # one resumed session spanning days (real-world case)
            t2 = t + timedelta(days=6)
            lines.append(_codex_line(t2, "event_msg",
                                     {"type": "user_message", "message": "resume"}))
            lines.append(_codex_line(t2 + timedelta(minutes=4), "event_msg",
                                     {"type": "agent_message", "message": "ok"}))
        day_dir = CODEX_DIR / start.strftime("%Y/%m/%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        fname = f"rollout-{start.strftime('%Y-%m-%dT%H-%M-%S')}-{sid}.jsonl"
        (day_dir / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")


def gen_grok_sessions(now, n=16):
    from urllib.parse import quote
    dirs = {p: GROK_DIR / quote(f"/home/user/projects/{p}", safe="")
            for p in DEMO_PROJECTS_CROSS[:2]}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    marker_written = False
    for i in range(n):
        start = now - timedelta(days=int(random.triangular(0, 60, 25)))
        sid = mk_sid()
        proj = random.choice(list(dirs))
        lines = []
        for k in range(random.randint(1, 4)):
            prompt = f"demo grok prompt {k}"
            if not marker_written:
                prompt = '<script>alert("grok")</script> GROK_PRIVATE_MARKER'
                marker_written = True
            lines.append(json.dumps({
                "timestamp": (start + timedelta(minutes=3 * k))
                .strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "session_id": sid, "prompt": prompt,
                "is_bash": random.random() < 0.2}, ensure_ascii=False))
        with open(dirs[proj] / "prompt_history.jsonl", "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


def gen_antigravity_files(now, n=6):
    ANTIGRAVITY_DIR.mkdir(parents=True, exist_ok=True)
    for _ in range(n):
        p = ANTIGRAVITY_DIR / f"{mk_sid()}.pb"
        p.write_bytes(b"\x0a\x00")
        age = now - timedelta(days=int(random.triangular(0, 60, 15)))
        os.utime(p, (age.timestamp(), age.timestamp()))
```

Wire into `main()` (after the existing session loop): `gen_codex_sessions(now)`, `gen_grok_sessions(now)`, `gen_antigravity_files(now)`. Add the needed imports (`os`, `timedelta` already imported — verify) and add the three new dirs to the wipe-and-recreate block at lines 20-26.

- [ ] **Step 4: Regenerate and test**

Run: `python3 scripts/generate_demo_data.py && python3 -m pytest tests/test_demo_data.py tests/test_scan_codex.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_demo_data.py tests/test_demo_data.py
git commit -m "feat(demo): synthetic Codex/Grok/Antigravity source trees in demo data"
```

---

### Task 5: `aggregate.py` — `--cross-llm-rows` + `cross_llm` and `ledger` blocks + SCHEMA-CHANGES entry

**Files:**
- Modify: `scripts/aggregate.py` (CLI at lines 1445-1461; final dict assembly at lines 1592-1617)
- Modify: `docs/SCHEMA-CHANGES.md` (same commit — repo rule)
- Test: `tests/test_cross_llm_aggregate.py`

**Interfaces:**
- Consumes: adapter row shape from Tasks 2-3; `load_transcript_rows` pattern (aggregate.py:267-289).
- Produces: CLI flag `--cross-llm-rows <path>` (repeatable, `action="append"`). New top-level `analysis-data.json` blocks, siblings of `meta`/`aggregates`/`scores`/`_sessions`:

```
"cross_llm": {
  "sources": [{"source", "coverage", "session_count", "first_date", "last_date",
               "total_input_tokens" (null when unknown), "total_output_tokens",
               "parse_errors"}...],           # always includes "claude"
  "common_window": {"start", "end", "days", "degraded": bool},   # degraded = days < 14
  "weekly_share": [{"week": "2026-W15", "minutes": {"claude": int, "codex": int, ...}}...],
  "parallel": {"heatmap": [[int]*24]*7,      # weekday x hour, count of hours with >=2 active sources
               "daily_max": [{"date", "max_parallel"}...],
               "hours_multi_source": int, "hours_single_source": int},
  "project_matrix": {"projects": [name...], "sources": [source...],
                     "counts": [[int]*len(sources)]*len(projects)},  # top 10 by total
  "head_to_head": {"window_days": int, "claude": {...}, "codex": {...}} | null,
      # per side: {"sessions", "active_days", "total_tokens" (in+out), "median_duration_minutes"}
      # null unless both sources have >=1 session inside the common window
}
"ledger": {
  "schema_version": 1,
  "window": {"start", "end", "days"},        # transcript-pool date range
  "output": {"git_commits", "git_pushes", "sessions_with_commits"},
  "sources_detected": ["claude", "codex", ...]
}
```

Functions: `load_cross_llm_rows(paths: list) -> tuple[list[dict], dict]` (rows, per-source parse-error counts — bad lines skipped and counted); `compute_cross_llm(claude_rows: list[dict], cross_rows: list[dict]) -> dict`; `compute_ledger(activity_metas: dict, cross_llm: dict) -> dict`. Claude activity rows are adapted internally with `source="claude"`, `coverage="full"`.

**Design constraints baked in:** cross-LLM rows must NOT touch `scoring_metas` or `activity_metas` (9-dim scores and existing panels stay Claude-only); presence-only sources are excluded from `common_window`, `weekly_share`, `parallel`, `project_matrix`, `head_to_head` — they appear in `sources` cards only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cross_llm_aggregate.py
import unittest
from datetime import datetime, timedelta, timezone

from scripts.aggregate import compute_cross_llm, compute_ledger


def _iso(dt):
    return dt.isoformat()


def _claude_row(sid, start, dur=60, project="/home/user/projects/webapp",
                commits=0):
    return {"session_id": sid, "project_path": project,
            "start_time": _iso(start), "duration_minutes": dur,
            "input_tokens": 1000, "output_tokens": 200,
            "git_commits": commits, "git_pushes": 0}


def _codex_row(sid, start, dur=60, project="/home/user/projects/webapp"):
    return {"session_id": sid, "project_path": project,
            "start_time": _iso(start), "duration_minutes": dur,
            "segments": [[_iso(start), _iso(start + timedelta(minutes=dur))]],
            "input_tokens": 500, "output_tokens": 100,
            "source": "codex", "coverage": "full"}


BASE = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


class CrossLlmTests(unittest.TestCase):
    def _twenty_days_both(self):
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i)) for i in range(20)]
        codex = [_codex_row(f"x{i}", BASE + timedelta(days=i, minutes=30))
                 for i in range(20)]
        return claude, codex

    def test_sources_cards_include_claude(self):
        claude, codex = self._twenty_days_both()
        block = compute_cross_llm(claude, codex)
        srcs = {s["source"]: s for s in block["sources"]}
        self.assertIn("claude", srcs)
        self.assertIn("codex", srcs)
        self.assertEqual(srcs["codex"]["session_count"], 20)

    def test_common_window_not_degraded_at_20_days(self):
        claude, codex = self._twenty_days_both()
        block = compute_cross_llm(claude, codex)
        self.assertFalse(block["common_window"]["degraded"])
        self.assertGreaterEqual(block["common_window"]["days"], 14)

    def test_common_window_degraded_below_14_days(self):
        claude = [_claude_row(f"c{i}", BASE + timedelta(days=i)) for i in range(30)]
        codex = [_codex_row("x0", BASE + timedelta(days=25))]  # 5-day overlap tail
        block = compute_cross_llm(claude, codex)
        self.assertTrue(block["common_window"]["degraded"])

    def test_parallel_overlap_detected(self):
        claude = [_claude_row("c0", BASE, dur=120)]
        codex = [_codex_row("x0", BASE + timedelta(minutes=10), dur=60)]
        block = compute_cross_llm(claude, codex)
        self.assertGreaterEqual(block["parallel"]["hours_multi_source"], 1)

    def test_presence_only_excluded_from_comparisons(self):
        claude, codex = self._twenty_days_both()
        anti = [{"session_id": "a0", "project_path": "",
                 "start_time": _iso(BASE), "duration_minutes": None,
                 "segments": None, "input_tokens": None, "output_tokens": None,
                 "source": "antigravity", "coverage": "presence_only"}]
        block = compute_cross_llm(claude, codex + anti)
        srcs = {s["source"] for s in block["sources"]}
        self.assertIn("antigravity", srcs)
        for wk in block["weekly_share"]:
            self.assertNotIn("antigravity", wk["minutes"])
        self.assertNotIn("antigravity", block["project_matrix"]["sources"])

    def test_head_to_head_present_with_both_sources(self):
        claude, codex = self._twenty_days_both()
        h2h = compute_cross_llm(claude, codex)["head_to_head"]
        self.assertIsNotNone(h2h)
        self.assertEqual(h2h["claude"]["sessions"], 20)
        self.assertEqual(h2h["codex"]["sessions"], 20)

    def test_midnight_spanning_session_splits_by_day(self):
        late = datetime(2026, 6, 1, 23, 30, tzinfo=timezone.utc)
        claude = [_claude_row("c0", late, dur=120)]  # crosses midnight
        codex = [_codex_row("x0", late + timedelta(minutes=5), dur=120)]
        block = compute_cross_llm(claude, codex)
        days = {d["date"] for d in block["parallel"]["daily_max"]}
        self.assertIn("2026-06-01", days)
        self.assertIn("2026-06-02", days)


class LedgerTests(unittest.TestCase):
    def test_ledger_output_counts(self):
        metas = {f"c{i}": _claude_row(f"c{i}", BASE + timedelta(days=i),
                                      commits=(1 if i % 2 else 0))
                 for i in range(10)}
        cross = compute_cross_llm(list(metas.values()), [])
        ledger = compute_ledger(metas, cross)
        self.assertEqual(ledger["schema_version"], 1)
        self.assertEqual(ledger["output"]["git_commits"], 5)
        self.assertEqual(ledger["output"]["sessions_with_commits"], 5)
        self.assertIn("claude", ledger["sources_detected"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_cross_llm_aggregate.py -q`
Expected: FAIL with ImportError (`compute_cross_llm` not defined).

- [ ] **Step 3: Implement in `aggregate.py`**

Add near `load_transcript_rows` (after line 289):

```python
def load_cross_llm_rows(paths):
    """Load adapter-emitted rows (scan_codex/grok/antigravity output).

    Returns (rows, parse_errors_by_source). Bad lines are skipped and
    counted under the source guessed from the row, else "(unknown)".
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
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    errors["(unknown)"] = errors.get("(unknown)", 0) + 1
                    continue
                if not row.get("source") or not row.get("start_time"):
                    src = row.get("source") or "(unknown)"
                    errors[src] = errors.get(src, 0) + 1
                    continue
                rows.append(row)
    return rows, errors
```

Add the computation functions (new section before `main()`); helpers used below — `_parse_dt(s)` reuses the module's existing ISO parsing helper if one exists, else `datetime.fromisoformat(s.replace("Z", "+00:00"))`:

```python
def _row_windows(row):
    """Activity windows for a row: explicit segments, else start+duration."""
    segs = row.get("segments")
    out = []
    if segs:
        for pair in segs:
            try:
                s, e = _parse_dt(pair[0]), _parse_dt(pair[1])
            except (ValueError, TypeError, IndexError):
                continue
            if s and e and e >= s:
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
    yield cur.date(), cur, end


def _project_key(path_str):
    return Path(path_str).name if path_str else "(unknown)"


def compute_cross_llm(claude_rows, cross_rows):
    """Build the cross_llm block. claude_rows = activity-pool row dicts."""
    tagged = [dict(r, source="claude", coverage="full") for r in claude_rows]
    all_rows = tagged + list(cross_rows)
    comparable = [r for r in all_rows if r.get("coverage") != "presence_only"]

    # --- source cards ---
    sources = []
    for src in sorted({r["source"] for r in all_rows}):
        rs = [r for r in all_rows if r["source"] == src]
        dates = sorted(d for d in (_parse_dt(r.get("start_time") or "")
                                   for r in rs) if d)
        def _tok(key):
            vals = [r.get(key) for r in rs if isinstance(r.get(key), int)]
            return sum(vals) if vals else None
        sources.append({
            "source": src,
            "coverage": rs[0].get("coverage", "full"),
            "session_count": len(rs),
            "first_date": dates[0].date().isoformat() if dates else None,
            "last_date": dates[-1].date().isoformat() if dates else None,
            "total_input_tokens": _tok("input_tokens"),
            "total_output_tokens": _tok("output_tokens"),
            "parse_errors": 0,
        })

    # --- common window across comparable sources ---
    per_source_range = {}
    for src in {r["source"] for r in comparable}:
        ds = sorted(d for d in (_parse_dt(r.get("start_time") or "")
                    for r in comparable if r["source"] == src) if d)
        if ds:
            per_source_range[src] = (ds[0], ds[-1])
    common_window = None
    if len(per_source_range) >= 2:
        start = max(a for a, _ in per_source_range.values())
        end = min(b for _, b in per_source_range.values())
        days = max((end - start).days, 0)
        common_window = {"start": start.date().isoformat(),
                         "end": end.date().isoformat(),
                         "days": days, "degraded": days < 14}

    # --- weekly share (active minutes per ISO week per source) ---
    weekly = {}
    for r in comparable:
        for s, e in _row_windows(r):
            wk = f"{s.isocalendar()[0]}-W{s.isocalendar()[1]:02d}"
            weekly.setdefault(wk, {}).setdefault(r["source"], 0)
            weekly[wk][r["source"]] += round((e - s).total_seconds() / 60)
    weekly_share = [{"week": wk, "minutes": mins}
                    for wk, mins in sorted(weekly.items())]

    # --- parallel detection (hour buckets, midnight-split) ---
    hour_sources = {}   # (date, hour) -> set(sources)
    for r in comparable:
        for s, e in _row_windows(r):
            for day, ss, ee in _split_at_midnight(s, e):
                for h in range(ss.hour, ee.hour + (1 if ee.minute or ee.second
                                                   or ee.hour == ss.hour else 0) + 1):
                    if h > 23:
                        break
                    hour_sources.setdefault((day, h), set()).add(r["source"])
    heatmap = [[0] * 24 for _ in range(7)]
    daily = {}
    multi = single = 0
    for (day, h), srcs in hour_sources.items():
        n = len(srcs)
        daily[day] = max(daily.get(day, 0), n)
        if n >= 2:
            heatmap[day.weekday()][h] += 1
            multi += 1
        else:
            single += 1
    parallel = {
        "heatmap": heatmap,
        "daily_max": [{"date": d.isoformat(), "max_parallel": m}
                      for d, m in sorted(daily.items())],
        "hours_multi_source": multi,
        "hours_single_source": single,
    }

    # --- project x tool matrix (top 10 projects by total sessions) ---
    matrix = {}
    for r in comparable:
        proj = _project_key(r.get("project_path") or "")
        matrix.setdefault(proj, {}).setdefault(r["source"], 0)
        matrix[proj][r["source"]] += 1
    top = sorted(matrix.items(), key=lambda kv: -sum(kv[1].values()))[:10]
    matrix_sources = sorted({r["source"] for r in comparable})
    project_matrix = {
        "projects": [p for p, _ in top],
        "sources": matrix_sources,
        "counts": [[counts.get(s, 0) for s in matrix_sources]
                   for _, counts in top],
    }

    # --- head-to-head: claude vs codex inside the common window ---
    head_to_head = None
    if common_window and {"claude", "codex"} <= set(per_source_range):
        # compare on calendar dates to stay tz-simple
        def _side(src):
            rs = [r for r in comparable if r["source"] == src]
            inside = [r for r in rs
                      if common_window["start"]
                      <= (_parse_dt(r["start_time"]).date().isoformat())
                      <= common_window["end"]]
            if not inside:
                return None
            durs = sorted(r.get("duration_minutes") or 0 for r in inside)
            toks = [(r.get("input_tokens") or 0) + (r.get("output_tokens") or 0)
                    for r in inside]
            return {"sessions": len(inside),
                    "active_days": len({_parse_dt(r["start_time"]).date()
                                        for r in inside}),
                    "total_tokens": sum(toks),
                    "median_duration_minutes": durs[len(durs) // 2]}
        claude_side, codex_side = _side("claude"), _side("codex")
        if claude_side and codex_side:
            head_to_head = {"window_days": common_window["days"],
                            "claude": claude_side, "codex": codex_side}

    return {"sources": sources, "common_window": common_window,
            "weekly_share": weekly_share, "parallel": parallel,
            "project_matrix": project_matrix, "head_to_head": head_to_head}


def compute_ledger(activity_metas, cross_llm):
    rows = list(activity_metas.values())
    dates = sorted(d for d in (_parse_dt(r.get("start_time") or "")
                               for r in rows) if d)
    commits = sum(r.get("git_commits") or 0 for r in rows)
    pushes = sum(r.get("git_pushes") or 0 for r in rows)
    with_commits = sum(1 for r in rows if (r.get("git_commits") or 0) > 0)
    return {
        "schema_version": 1,
        "window": {
            "start": dates[0].date().isoformat() if dates else None,
            "end": dates[-1].date().isoformat() if dates else None,
            "days": (dates[-1] - dates[0]).days if len(dates) > 1 else 0,
        },
        "output": {"git_commits": commits, "git_pushes": pushes,
                   "sessions_with_commits": with_commits},
        "sources_detected": [s["source"] for s in cross_llm["sources"]],
    }
```

(Imports: ensure `time` from `datetime import time` and `timedelta` are available at module top; `_parse_dt` — if `aggregate.py` has no existing ISO helper, add one next to these functions.)

Wire into `main()`:
1. CLI (after `--extra-redacted`, line ~1461): `parser.add_argument("--cross-llm-rows", action="append", default=[], help="Path to scan_codex/grok/antigravity output jsonl. Repeatable. Rows feed the cross_llm/ledger blocks only — never the 9-dim scoring pool.")`
2. After `final = {...}` assembly (lines 1592-1617): load rows, compute, attach; fill `parse_errors` on the matching source cards from the loader's error dict:

```python
    cross_rows, cross_errors = load_cross_llm_rows(args.cross_llm_rows)
    cross_llm = compute_cross_llm(list(activity_metas.values()), cross_rows)
    for card in cross_llm["sources"]:
        card["parse_errors"] = cross_errors.get(card["source"], 0)
    final["cross_llm"] = cross_llm
    final["ledger"] = compute_ledger(activity_metas, cross_llm)
```

(When `--transcript-rows` is not set, `activity_metas` may not exist as a name at that point — check `main()`'s branches around lines 1479-1519 and use whichever dict of session rows feeds `compute_activity`; the blocks must work in both session-meta mode and transcript-rows mode.)

Add to `docs/SCHEMA-CHANGES.md` (same commit), following the file's existing entry format:

```markdown
## 2026-07-14 — additive: `cross_llm` and `ledger` top-level blocks (V5 Phase 1)

- `cross_llm`: cross-tool sources / common_window / weekly_share / parallel /
  project_matrix / head_to_head. Present even with no external sources
  (sources then lists only `claude`). Fields inside rows may be null —
  unknown is never imputed.
- `ledger`: schema_version 1; window / output counters / sources_detected.
- No existing fields changed or removed.
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_cross_llm_aggregate.py tests/test_cost_estimate.py -q`
Expected: PASS. Then end-to-end sanity:

```bash
python3 scripts/generate_demo_data.py
python3 scripts/scan_transcripts.py --projects-dir /tmp/cc-autopsy-demo/projects --output /tmp/cc-autopsy-demo/rows.jsonl
python3 scripts/scan_codex.py --sessions-dir /tmp/cc-autopsy-demo/codex-sessions --output /tmp/cc-autopsy-demo/codex-rows.jsonl
python3 scripts/scan_grok.py --sessions-dir /tmp/cc-autopsy-demo/grok-sessions --output /tmp/cc-autopsy-demo/grok-rows.jsonl
python3 scripts/scan_antigravity.py --conversations-dir /tmp/cc-autopsy-demo/antigravity-conversations --output /tmp/cc-autopsy-demo/anti-rows.jsonl
python3 scripts/aggregate.py --data-dir /tmp/cc-autopsy-demo/usage-data --transcript-rows /tmp/cc-autopsy-demo/rows.jsonl --cross-llm-rows /tmp/cc-autopsy-demo/codex-rows.jsonl --cross-llm-rows /tmp/cc-autopsy-demo/grok-rows.jsonl --cross-llm-rows /tmp/cc-autopsy-demo/anti-rows.jsonl --output /tmp/cc-autopsy-demo/analysis-data.json
python3 -c "import json; d=json.load(open('/tmp/cc-autopsy-demo/analysis-data.json')); print(sorted(d)); print([s['source'] for s in d['cross_llm']['sources']])"
```

Expected: keys include `cross_llm` and `ledger`; sources list `['antigravity','claude','codex','grok']`.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_cross_llm_aggregate.py docs/SCHEMA-CHANGES.md
git commit -m "feat(aggregate): --cross-llm-rows with additive cross_llm and ledger blocks"
```

---

### Task 6: snapshot hook in `build_html.py`

**Files:**
- Modify: `scripts/build_html.py` (CLI at lines 76-110; tail of `main()` at lines 154-158)
- Test: `tests/test_history_snapshot.py`

**Interfaces:**
- Produces: `append_history_snapshot(history_path: Path, analysis: dict, audience: str) -> None` in `build_html.py`; CLI flag `--history-file` (default `~/.claude/usage-data/autopsy-history.jsonl`; pass a tmp path in tests). Appends ONE json line after a successful SELF build: `{"date": "YYYY-MM-DD", "schema_version": 1, "scores": {D1..: number|null}, "badges": [], "ledger": {git_commits, sessions, sources_detected}}`. HR builds never append. Failure to append prints a warning to stderr and never fails the build.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_history_snapshot.py
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_html import append_history_snapshot

ANALYSIS = {
    "meta": {"total_sessions": 12},
    "scores": {"D1_delegation": {"score": 7}, "_overall": {"score": 6.1}},
    "ledger": {"schema_version": 1,
               "output": {"git_commits": 9, "git_pushes": 4,
                          "sessions_with_commits": 5},
               "sources_detected": ["claude", "codex"]},
}


class SnapshotTests(unittest.TestCase):
    def test_appends_one_line_for_self(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "sub" / "autopsy-history.jsonl"
            append_history_snapshot(hist, ANALYSIS, "self")
            append_history_snapshot(hist, ANALYSIS, "self")
            lines = hist.read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)
        entry = json.loads(lines[0])
        self.assertEqual(entry["schema_version"], 1)
        self.assertEqual(entry["scores"]["D1_delegation"], 7)
        self.assertEqual(entry["badges"], [])
        self.assertEqual(entry["ledger"]["git_commits"], 9)
        self.assertIn("date", entry)

    def test_hr_build_never_appends(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "autopsy-history.jsonl"
            append_history_snapshot(hist, ANALYSIS, "hr")
            self.assertFalse(hist.exists())

    def test_failure_warns_but_does_not_raise(self):
        # a directory at the target path makes open() fail
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td)  # is a dir, not a file
            append_history_snapshot(bad, ANALYSIS, "self")  # must not raise


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_history_snapshot.py -q`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

In `build_html.py`, add near the top (after existing imports):

```python
from datetime import date

DEFAULT_HISTORY_FILE = Path.home() / ".claude" / "usage-data" / "autopsy-history.jsonl"


def append_history_snapshot(history_path, analysis, audience):
    """Append a one-line trend snapshot after a successful SELF build.

    The trend ledger (Phase 3) reads this file; it ships day one so
    history starts accumulating immediately. Never fails the build.
    """
    if audience != "self":
        return
    try:
        scores = {}
        for key, val in (analysis.get("scores") or {}).items():
            if isinstance(val, dict) and "score" in val:
                scores[key] = val["score"]
            elif isinstance(val, (int, float)):
                scores[key] = val
        ledger = analysis.get("ledger") or {}
        entry = {
            "date": date.today().isoformat(),
            "schema_version": 1,
            "scores": scores,
            "badges": [],
            "ledger": {
                "git_commits": (ledger.get("output") or {}).get("git_commits"),
                "sessions": (analysis.get("meta") or {}).get("total_sessions"),
                "sources_detected": ledger.get("sources_detected") or [],
            },
        }
        path = Path(history_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"warning: could not append history snapshot: {exc}",
              file=sys.stderr)
```

CLI: `ap.add_argument("--history-file", default=str(DEFAULT_HISTORY_FILE), help="Trend-snapshot jsonl appended after each successful self build. Corrupt lines are tolerated on read (Phase 3).")`

Tail of `main()` — after `out.write_text(html_out)` and the size print (lines 154-158):

```python
    append_history_snapshot(Path(args.history_file), analysis, args.audience)
```

(`analysis` = the dict loaded from `--input`; check the actual local variable name in `main()` and use it.)

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_history_snapshot.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/build_html.py tests/test_history_snapshot.py
git commit -m "feat(build): trend snapshot hook appends to autopsy-history.jsonl on self builds"
```

---

### Task 7: direction-C foundation in `report_render.py` + locales

**Files:**
- Modify: `scripts/report_render.py` (CSS inside `PAGE_TEMPLATE`; new helpers near `_build_activity_panel`, line 117)
- Modify: `scripts/locales.py` (new keys, both locales)
- Test: `tests/test_ledger_render.py` (new)

**Interfaces:**
- Produces: CSS custom properties on `:root` — `--c-gold: #B08A2E; --c-gold-deep: #7E6119; --c-gold-soft: rgba(176,138,46,0.12); --c-neg: #9C201A;` plus component classes `c-exhibit`, `c-exhibit-no`, `c-exhibit-src`, `c-finding`, `c-finding-no`, `c-sec-title` (styles copied from the approved mock `docs/superpowers/specs/mocks/mock-c-business-report.html`, adapted to the template's existing CSS variable system — do NOT restyle existing sections in this phase). Python helpers:
  - `_exhibit(no: int, title: str, body_html: str, source_line: str) -> str` — wraps body in the numbered-Exhibit frame: `EXHIBIT {no}` label (gold-deep), title, body, `source_line` footer (escaped).
  - `_parse_ledger_narration(md: str) -> dict` — splits on `^# ` headings; returns `{"opening": str, "output-ledger": str, "team-ledger": str}` (missing keys → `""`).
- Locale keys (add to BOTH `en` and `zh_TW` in `locales.py`; zh_TW natively phrased, NO em-dash):
  `ledger_exhibit_label` ("EXHIBIT" / "圖表"), `ledger_source_prefix` ("Source:" / "資料來源:"), `ledger_opening_kicker` ("AI WORK LEDGER" / "AI 工作總帳"), `ledger_output_title` ("Output ledger" / "產出帳"), `ledger_team_title` ("Team ledger" / "團隊帳"), `ledger_source_card_full` ("full data" / "完整資料"), `ledger_source_card_partial` ("partial data" / "部分資料"), `ledger_source_card_presence` ("presence only" / "僅偵測到活動"), `ledger_not_detected` ("not detected" / "未偵測到"), `ledger_degraded_note` ("Overlap between sources is under 14 days; sources are shown separately instead of compared." / "工具間資料重疊期不足 14 天, 改為分開呈現不做比較。"), `ledger_common_window_note_template` ("Cross-tool comparisons cover the common window {start} to {end} ({days} days)." / "跨工具比較僅涵蓋共同期間 {start} 至 {end}, 共 {days} 天。"), `ledger_weekly_share_title` ("Weekly active minutes by tool" / "各工具每週活躍分鐘數"), `ledger_parallel_title` ("Multi-tool parallel hours (weekday x hour)" / "多工具並行時段 (星期 x 小時)"), `ledger_matrix_title` ("Projects by tool" / "專案 x 工具分佈"), `ledger_h2h_title` ("Claude vs Codex, common window" / "Claude 與 Codex 共同期間對照"), `ledger_h2h_sessions` ("sessions" / "場次"), `ledger_h2h_active_days` ("active days" / "活躍天數"), `ledger_h2h_tokens` ("total tokens" / "token 總量"), `ledger_h2h_median_dur` ("median session length (min)" / "session 長度中位數 (分)"), `ledger_output_commits` ("git commits" / "git commit 數"), `ledger_output_pushes` ("git pushes" / "git push 數"), `ledger_output_sessions_with_commits` ("sessions that shipped commits" / "有 commit 產出的 session 數").

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ledger_render.py
import unittest

from scripts import locales
from scripts.report_render import _exhibit, _parse_ledger_narration


class ExhibitTests(unittest.TestCase):
    def test_exhibit_frame(self):
        html = _exhibit(3, "Weekly share", "<p>body</p>",
                        "aggregate.py, transcript pool", locale="en")
        self.assertIn("EXHIBIT", html)
        self.assertIn("3", html)
        self.assertIn("<p>body</p>", html)
        self.assertIn("aggregate.py, transcript pool", html)

    def test_exhibit_escapes_source_line(self):
        html = _exhibit(1, "t", "<p>b</p>", "<script>x</script>", locale="en")
        self.assertNotIn("<script>x</script>", html)


class NarrationParseTests(unittest.TestCase):
    def test_parses_three_books(self):
        md = ("# opening\nOne sentence.\n"
              "# output-ledger\nClaim A.\n\nMore.\n"
              "# team-ledger\nClaim B.\n")
        d = _parse_ledger_narration(md)
        self.assertEqual(d["opening"], "One sentence.")
        self.assertTrue(d["output-ledger"].startswith("Claim A."))
        self.assertEqual(d["team-ledger"], "Claim B.")

    def test_missing_sections_empty(self):
        d = _parse_ledger_narration("")
        self.assertEqual(d, {"opening": "", "output-ledger": "", "team-ledger": ""})


class LedgerLocaleKeyTests(unittest.TestCase):
    REQUIRED = [
        "ledger_exhibit_label", "ledger_source_prefix", "ledger_opening_kicker",
        "ledger_output_title", "ledger_team_title", "ledger_source_card_full",
        "ledger_source_card_partial", "ledger_source_card_presence",
        "ledger_not_detected", "ledger_degraded_note",
        "ledger_common_window_note_template", "ledger_weekly_share_title",
        "ledger_parallel_title", "ledger_matrix_title", "ledger_h2h_title",
    ]

    def test_keys_in_both_locales(self):
        for loc in ("en", "zh_TW"):
            for key in self.REQUIRED:
                self.assertIn(key, locales.STRINGS[loc], f"{loc}:{key}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_ledger_render.py -q`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement**

In `report_render.py` (near `esc()` and the other helpers):

```python
def _exhibit(no, title, body_html, source_line, locale="en"):
    """Direction-C numbered Exhibit frame: label + title + body + source line.

    Every chart/table in the ledger sections goes through this so each
    visual carries its own provenance (claim-indexed evidence discipline).
    """
    return (
        '<figure class="c-exhibit">'
        '<figcaption class="c-exhibit-head">'
        f'<span class="c-exhibit-no">{t(locale, "ledger_exhibit_label")} '
        f'{int(no)}</span> '
        f'<span class="c-exhibit-t">{esc(title)}</span>'
        '</figcaption>'
        f'{body_html}'
        f'<div class="c-exhibit-src">{t(locale, "ledger_source_prefix")} '
        f'{esc(source_line)}</div>'
        '</figure>'
    )


def _parse_ledger_narration(md: str) -> dict:
    books = {"opening": "", "output-ledger": "", "team-ledger": ""}
    current = None
    buf = []
    for line in (md or "").splitlines():
        if line.startswith("# "):
            if current in books:
                books[current] = "\n".join(buf).strip()
            current = line[2:].strip().lower()
            buf = []
        else:
            buf.append(line)
    if current in books:
        books[current] = "\n".join(buf).strip()
    return books
```

CSS added inside `PAGE_TEMPLATE`'s `<style>` (values from the approved mock; keep them as literal additions, do not touch existing token declarations — `tests/test_css_tokens.py` guards those):

```css
:root { --c-gold: #B08A2E; --c-gold-deep: #7E6119;
        --c-gold-soft: rgba(176,138,46,0.12); --c-neg: #9C201A; }
.c-exhibit { margin: 30px 0 6px; }
.c-exhibit-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 14px; }
.c-exhibit-no { font-size: 11.5px; font-weight: 800; letter-spacing: 0.14em;
                color: var(--c-gold-deep); white-space: nowrap; }
.c-exhibit-t { font-size: 14px; font-weight: 600; }
.c-exhibit-src { font-size: 11.5px; opacity: 0.65; margin-top: 10px; }
.c-finding { display: grid; grid-template-columns: 64px 1fr; gap: 20px;
             padding: 18px 0; border-bottom: 1px solid rgba(128,128,128,0.25); }
.c-finding-no { font-size: 30px; font-weight: 800; color: var(--c-gold); line-height: 1.2; }
.c-finding-head { font-size: 19px; font-weight: 700; line-height: 1.6; }
.c-neg-num { color: var(--c-neg); }
.c-sec-title { font-size: 23px; font-weight: 800; line-height: 1.5; max-width: 30em; }
.c-kicker { font-size: 12.5px; letter-spacing: 0.22em; color: var(--c-gold-deep); font-weight: 700; }
.c-source-cards { display: flex; gap: 12px; flex-wrap: wrap; margin: 14px 0; }
.c-source-card { border: 1px solid rgba(128,128,128,0.3); padding: 10px 14px;
                 font-size: 13px; min-width: 150px; }
.c-share-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 12.5px; }
.c-share-bar { display: flex; height: 14px; flex: 1; }
.c-share-seg { height: 100%; }
.c-h2h { display: grid; grid-template-columns: 1fr 1fr; gap: 0; border: 1px solid rgba(128,128,128,0.3); }
.c-h2h > div { padding: 14px 18px; }
.c-h2h .num { font-size: 22px; font-weight: 800; }
```

Add the locale keys listed in Interfaces to both dicts in `locales.py` (place in a new `# --- V5 ledger ---` section; zh_TW values exactly as given — no em-dashes).

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_ledger_render.py tests/test_locales.py tests/test_css_tokens.py -q`
Expected: PASS (locale parity + em-dash ban + CSS token tests all green)

- [ ] **Step 5: Commit**

```bash
git add scripts/report_render.py scripts/locales.py tests/test_ledger_render.py
git commit -m "feat(render): direction-C tokens, Exhibit frame, ledger narration parser, locale keys"
```

---

### Task 8: SELF skeleton sections — opening band, output ledger, team ledger

**Files:**
- Modify: `scripts/report_render.py` (new section builders + wiring into `render()`; audience gate `audience == "self"`), `scripts/build_html.py` (new `--ledger-narration` flag threaded through like `--peer-review`, lines 114-153)
- Test: `tests/test_ledger_render.py` (extend)

**Interfaces:**
- Consumes: `analysis["cross_llm"]`, `analysis["ledger"]` (Task 5 shapes), `_exhibit`, `_parse_ledger_narration`, locale keys (Task 7).
- Produces:
  - `_build_opening_band(ledger: dict, narration: dict, locale: str) -> str` — kicker + the LLM-written opening sentence (from `narration["opening"]`, escaped via the module's markdown-inline helper `inline_md()`), plus a numbered-finding list built from the `output-ledger` / `team-ledger` opener claims (first line of each book's narration; number styled `c-finding-no`). Empty narration → renders numbers-only band (no fabricated prose).
  - `_build_output_ledger(ledger: dict, narration: dict, locale: str) -> str` — action-title head (first line of `narration["output-ledger"]`, else localized `ledger_output_title`), body prose, then Exhibit 1: a 3-metric row (`git_commits`, `git_pushes`, `sessions_with_commits`) with source line `"aggregate.py ledger.output, transcript pool"`.
  - `_build_team_ledger(cross_llm: dict, narration: dict, locale: str) -> str` — source cards (every source: name, localized coverage label, session count, date range; absent sources are simply not present — `aggregate` only emits detected ones); then, **if `common_window` exists and not `degraded`**: Exhibit 2 weekly-share stacked bars (HTML divs, one row per week, segment width % = minutes share, distinct CSS classes per source), Exhibit 3 parallel heatmap (CSS grid 7×24, cell intensity = count, gold scale), Exhibit 4 project × tool matrix (table, project names escaped), Exhibit 5 head-to-head card (two columns, four numbers each). **If `degraded` or no window**: render the localized `ledger_degraded_note` + per-source panels (per source: sessions, active span, tokens when known) instead of Exhibits 2/5; matrix and heatmap still render (they don't compare rates across sources).
  - `render()` wiring: new params `ledger_narration_md=""`; sections inserted at the TOP of the SELF layout (before the current hero/peer-review), in order: opening band → output ledger → team ledger. **HR branch: none of the three render.** No session IDs and no `first_prompt`/prompt text are ever printed by these builders (team ledger uses counts, dates, minutes, tokens only).
- `build_html.py`: `ap.add_argument("--ledger-narration", default=None, help="Markdown with # opening / # output-ledger / # team-ledger books (SELF only; written by the skill in Step 3).")`; load like `--peer-review` (lines 114-130), pass `ledger_narration_md=...` into `render(...)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_ledger_render.py`)

```python
from scripts.report_render import (
    _build_opening_band, _build_output_ledger, _build_team_ledger)

CROSS = {
    "sources": [
        {"source": "claude", "coverage": "full", "session_count": 40,
         "first_date": "2026-05-01", "last_date": "2026-06-20",
         "total_input_tokens": 1000, "total_output_tokens": 200, "parse_errors": 0},
        {"source": "codex", "coverage": "full", "session_count": 12,
         "first_date": "2026-05-10", "last_date": "2026-06-18",
         "total_input_tokens": 500, "total_output_tokens": 90, "parse_errors": 0},
    ],
    "common_window": {"start": "2026-05-10", "end": "2026-06-18",
                      "days": 39, "degraded": False},
    "weekly_share": [{"week": "2026-W20", "minutes": {"claude": 300, "codex": 120}}],
    "parallel": {"heatmap": [[0] * 24 for _ in range(7)],
                 "daily_max": [], "hours_multi_source": 3,
                 "hours_single_source": 50},
    "project_matrix": {"projects": ["webapp"], "sources": ["claude", "codex"],
                       "counts": [[30, 10]]},
    "head_to_head": {"window_days": 39,
                     "claude": {"sessions": 35, "active_days": 30,
                                "total_tokens": 1200, "median_duration_minutes": 40},
                     "codex": {"sessions": 12, "active_days": 10,
                               "total_tokens": 590, "median_duration_minutes": 25}},
}
LEDGER = {"schema_version": 1,
          "window": {"start": "2026-05-01", "end": "2026-06-20", "days": 50},
          "output": {"git_commits": 21, "git_pushes": 9,
                     "sessions_with_commits": 14},
          "sources_detected": ["claude", "codex"]}
NARR = {"opening": "Your AI team shipped 21 commits for about $80.",
        "output-ledger": "21 commits landed in 50 days.\n\nDetail prose.",
        "team-ledger": "Codex took the long jobs.\n\nMore prose."}


class OpeningBandTests(unittest.TestCase):
    def test_contains_opening_sentence(self):
        html = _build_opening_band(LEDGER, NARR, "en")
        self.assertIn("Your AI team shipped 21 commits", html)

    def test_empty_narration_renders_without_fabricated_prose(self):
        html = _build_opening_band(LEDGER,
                                   {"opening": "", "output-ledger": "",
                                    "team-ledger": ""}, "en")
        self.assertNotIn("None", html)


class OutputLedgerTests(unittest.TestCase):
    def test_metrics_and_source_line(self):
        html = _build_output_ledger(LEDGER, NARR, "en")
        self.assertIn("21", html)
        self.assertIn("EXHIBIT", html)
        self.assertIn("ledger.output", html)


class TeamLedgerTests(unittest.TestCase):
    def test_source_cards_and_h2h(self):
        html = _build_team_ledger(CROSS, NARR, "en")
        self.assertIn("codex", html.lower())
        self.assertIn("39", html)          # window days
        self.assertIn("EXHIBIT", html)

    def test_degraded_window_drops_comparisons(self):
        degraded = dict(CROSS, common_window={"start": "2026-06-10",
                                              "end": "2026-06-18",
                                              "days": 8, "degraded": True})
        html = _build_team_ledger(degraded, NARR, "en")
        self.assertNotIn("2026-W20", html)   # no weekly comparison exhibit
        from scripts.locales import STRINGS
        self.assertIn(STRINGS["en"]["ledger_degraded_note"], html)

    def test_never_prints_prompt_text(self):
        cross = dict(CROSS)
        cross["sources"] = CROSS["sources"] + [
            {"source": "grok", "coverage": "partial", "session_count": 3,
             "first_date": "2026-06-01", "last_date": "2026-06-05",
             "total_input_tokens": None, "total_output_tokens": None,
             "parse_errors": 0}]
        html = _build_team_ledger(cross, NARR, "en")
        self.assertNotIn("GROK_PRIVATE_MARKER", html)
```

Also add a build-level test (same file) that `render()` with `audience="hr"` contains none of the three sections: call `render()` the same way `tests/test_build_html_additions.py` does (copy its minimal-arguments invocation pattern), passing an analysis dict containing `CROSS`/`LEDGER` and `ledger_narration_md=NARR`-equivalent markdown, and assert `"c-exhibit" not in html_hr` while `"c-exhibit" in html_self`.

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_ledger_render.py -q`
Expected: new tests FAIL (builders undefined).

- [ ] **Step 3: Implement the three builders + wiring**

```python
def _first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _rest_lines(text):
    lines = (text or "").splitlines()
    seen_first = False
    out = []
    for line in lines:
        if not seen_first and line.strip():
            seen_first = True
            continue
        if seen_first:
            out.append(line)
    return "\n".join(out).strip()


def _build_opening_band(ledger, narration, locale="en"):
    opening = _first_line(narration.get("opening", ""))
    findings = []
    for i, book in enumerate(("output-ledger", "team-ledger"), start=1):
        claim = _first_line(narration.get(book, ""))
        if claim:
            findings.append(
                '<div class="c-finding">'
                f'<div class="c-finding-no">{i}</div>'
                f'<div class="c-finding-head">{inline_md(claim)}</div>'
                '</div>')
    opening_html = (
        f'<p class="c-finding-head" style="margin-top:14px">{inline_md(opening)}</p>'
        if opening else "")
    win = ledger.get("window") or {}
    period = ""
    if win.get("start") and win.get("end"):
        period = (f'<p class="method">{esc(win["start"])} – {esc(win["end"])}'
                  f' · {int(win.get("days") or 0)}d</p>')
    return (
        '<section class="section" id="ledger-opening">'
        f'<div class="c-kicker">{t(locale, "ledger_opening_kicker")}</div>'
        f'{opening_html}{period}'
        f'{"".join(findings)}'
        '</section>')


def _build_output_ledger(ledger, narration, locale="en"):
    out = ledger.get("output") or {}
    title = _first_line(narration.get("output-ledger", "")) or t(
        locale, "ledger_output_title")
    prose = _rest_lines(narration.get("output-ledger", ""))
    prose_html = f"<div>{inline_md(prose)}</div>" if prose else ""
    metrics = (
        '<div class="metrics">'
        f'<div class="metric"><div class="n">{int(out.get("git_commits") or 0)}</div>'
        f'<div class="lbl">{t(locale, "ledger_output_commits")}</div></div>'
        f'<div class="metric"><div class="n">{int(out.get("git_pushes") or 0)}</div>'
        f'<div class="lbl">{t(locale, "ledger_output_pushes")}</div></div>'
        f'<div class="metric"><div class="n">{int(out.get("sessions_with_commits") or 0)}</div>'
        f'<div class="lbl">{t(locale, "ledger_output_sessions_with_commits")}</div></div>'
        '</div>')
    ex = _exhibit(1, t(locale, "ledger_output_title"), metrics,
                  "aggregate.py ledger.output, transcript pool", locale=locale)
    return ('<section class="section" id="ledger-output">'
            f'<h2 class="c-sec-title">{inline_md(title)}</h2>'
            f'{prose_html}{ex}</section>')
```

`_build_team_ledger` (source cards + conditional exhibits; heatmap intensity via inline `background: rgba(176,138,46, A)` with `A = min(count / max_count, 1) * 0.85`, `0` count → transparent; weekly-share segment colors: assign each source a class `c-src-0..c-src-5` from a fixed palette declared in the Task 7 CSS — claude uses `var(--c-gold)`, others muted grays/darks so gold stays the accent):

```python
_SRC_LABEL_KEYS = {"full": "ledger_source_card_full",
                   "partial": "ledger_source_card_partial",
                   "presence_only": "ledger_source_card_presence"}


def _build_team_ledger(cross_llm, narration, locale="en"):
    if not cross_llm or not cross_llm.get("sources"):
        return ""
    title = _first_line(narration.get("team-ledger", "")) or t(
        locale, "ledger_team_title")
    prose = _rest_lines(narration.get("team-ledger", ""))
    prose_html = f"<div>{inline_md(prose)}</div>" if prose else ""

    cards = ""
    for s in cross_llm["sources"]:
        label = t(locale, _SRC_LABEL_KEYS.get(s.get("coverage"),
                                              "ledger_source_card_full"))
        span = ""
        if s.get("first_date") and s.get("last_date"):
            span = f'{esc(s["first_date"])} – {esc(s["last_date"])}'
        cards += ('<div class="c-source-card">'
                  f'<b>{esc(s["source"])}</b> · {esc(label)}<br>'
                  f'{int(s.get("session_count") or 0)} · {span}</div>')
    cards = f'<div class="c-source-cards">{cards}</div>'

    win = cross_llm.get("common_window")
    parts = [cards]
    exhibit_no = 2

    if win and not win.get("degraded"):
        note = t(locale, "ledger_common_window_note_template").format(
            start=win["start"], end=win["end"], days=win["days"])
        parts.append(f'<p class="method">{esc(note)}</p>')
        # Exhibit: weekly share stacked bars
        rows = ""
        srcs = sorted({src for wk in cross_llm.get("weekly_share", [])
                       for src in wk["minutes"]})
        for wk in cross_llm.get("weekly_share", []):
            total = sum(wk["minutes"].values()) or 1
            segs = "".join(
                f'<div class="c-share-seg c-src-{srcs.index(src) % 6}" '
                f'style="width:{100 * mins / total:.1f}%" '
                f'title="{esc(src)}: {int(mins)}"></div>'
                for src, mins in sorted(wk["minutes"].items()))
            rows += (f'<div class="c-share-row"><span>{esc(wk["week"])}</span>'
                     f'<div class="c-share-bar">{segs}</div></div>')
        parts.append(_exhibit(exhibit_no, t(locale, "ledger_weekly_share_title"),
                              rows, "aggregate.py cross_llm.weekly_share",
                              locale=locale))
        exhibit_no += 1
    elif win and win.get("degraded"):
        parts.append(f'<p class="method">'
                     f'{esc(t(locale, "ledger_degraded_note"))}</p>')

    # heatmap + matrix render regardless of degradation (no cross-rate claims)
    hm = cross_llm.get("parallel", {}).get("heatmap")
    if hm and any(any(r) for r in hm):
        mx = max(max(r) for r in hm) or 1
        grid = "".join(
            f'<div style="background: rgba(176,138,46,{0.85 * c / mx:.2f})"></div>'
            for row in hm for c in row)
        body = (f'<div style="display:grid;grid-template-columns:repeat(24,1fr);'
                f'gap:2px;height:120px">{grid}</div>')
        parts.append(_exhibit(exhibit_no, t(locale, "ledger_parallel_title"),
                              body, "aggregate.py cross_llm.parallel",
                              locale=locale))
        exhibit_no += 1

    pm = cross_llm.get("project_matrix") or {}
    if pm.get("projects"):
        head = "".join(f"<th>{esc(s)}</th>" for s in pm["sources"])
        body_rows = "".join(
            f'<tr><td>{esc(proj)}</td>' +
            "".join(f"<td>{c}</td>" for c in pm["counts"][i]) + "</tr>"
            for i, proj in enumerate(pm["projects"]))
        table = (f'<table><thead><tr><th></th>{head}</tr></thead>'
                 f'<tbody>{body_rows}</tbody></table>')
        parts.append(_exhibit(exhibit_no, t(locale, "ledger_matrix_title"),
                              table, "aggregate.py cross_llm.project_matrix",
                              locale=locale))
        exhibit_no += 1

    h2h = cross_llm.get("head_to_head")
    if h2h and win and not win.get("degraded"):
        def _col(name, side):
            return ('<div>'
                    f'<div class="c-kicker">{esc(name)}</div>'
                    f'<div class="num">{int(side["sessions"])}</div>'
                    f'<div class="lbl">{t(locale, "ledger_h2h_sessions")}</div>'
                    f'<div>{int(side["active_days"])} '
                    f'{t(locale, "ledger_h2h_active_days")}</div>'
                    f'<div>{fmt(side["total_tokens"])} '
                    f'{t(locale, "ledger_h2h_tokens")}</div>'
                    f'<div>{int(side["median_duration_minutes"])} '
                    f'{t(locale, "ledger_h2h_median_dur")}</div>'
                    '</div>')
        card = ('<div class="c-h2h">'
                + _col("Claude", h2h["claude"]) + _col("Codex", h2h["codex"])
                + '</div>')
        parts.append(_exhibit(exhibit_no, t(locale, "ledger_h2h_title"), card,
                              "aggregate.py cross_llm.head_to_head",
                              locale=locale))

    return ('<section class="section" id="ledger-team">'
            f'<h2 class="c-sec-title">{inline_md(title)}</h2>'
            f'{prose_html}{"".join(parts)}</section>')
```

Wiring in `render()`: add `ledger_narration_md=""` parameter; at the start of the SELF-layout branch:

```python
    ledger_sections = ""
    if audience == "self":
        narration = _parse_ledger_narration(ledger_narration_md)
        ledger_block = analysis.get("ledger") or {}
        cross_block = analysis.get("cross_llm") or {}
        if ledger_block:
            ledger_sections += _build_opening_band(ledger_block, narration, locale)
            ledger_sections += _build_output_ledger(ledger_block, narration, locale)
        if cross_block:
            ledger_sections += _build_team_ledger(cross_block, narration, locale)
```

and prepend `ledger_sections` to the SELF body (find where the hero/peer-review section string is assembled and place these before it). Use the section-class names the template already styles (`section`, `metrics`, `metric`, `method` — verify against `PAGE_TEMPLATE`; `_build_activity_panel` at lines 117-198 shows the exact class vocabulary). `analysis` top-level dict must be threaded: `build_html.py` already passes the loaded analysis; confirm `render()`'s signature exposes it (it does — the existing sections read `aggregates`/`scores` from it) and read `analysis["cross_llm"]` / `analysis["ledger"]` the same way.

Add the `c-src-0..c-src-5` palette classes to the Task 7 CSS block:

```css
.c-src-0 { background: var(--c-gold); }
.c-src-1 { background: #5C5850; }
.c-src-2 { background: #918C82; }
.c-src-3 { background: #7E6119; }
.c-src-4 { background: #26231E; }
.c-src-5 { background: #C9C4B8; }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_ledger_render.py tests/test_locales.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/report_render.py scripts/build_html.py scripts/locales.py tests/test_ledger_render.py
git commit -m "feat(render): SELF ledger skeleton — opening band, output ledger, team ledger (direction C)"
```

---

### Task 9: smoke test end-to-end with cross-LLM data + privacy assertions

**Files:**
- Modify: `tests/smoke_test.py` (pipeline steps + assertions; build invocation at lines 99-119)

**Interfaces:**
- Consumes: everything from Tasks 2-8; the `GROK_PRIVATE_MARKER` planted by Task 4.

- [ ] **Step 1: Extend the smoke pipeline**

In `tests/smoke_test.py`, after the existing `generate_demo_data` → `scan_transcripts` → `aggregate` steps, insert the three adapter runs and change the aggregate invocation to include the `--cross-llm-rows` flags (exact commands as in Task 5 Step 4's sanity block, using `DEMO_ROOT` paths). Add `--ledger-narration` to `run_build` with a narration file written by the test:

```python
narration_path = DEMO_ROOT / "ledger-narration.md"
narration_path.write_text(
    "# opening\nDemo opening sentence <script>alert('n')</script>.\n"
    "# output-ledger\nDemo output claim.\n"
    "# team-ledger\nDemo team claim.\n", encoding="utf-8")
```

(passed via `extra=("--ledger-narration", str(narration_path))` for the SELF build only) and `--history-file` pointed at `DEMO_ROOT / "history.jsonl"` for both builds.

- [ ] **Step 2: Add assertions**

```python
self_html = self_output.read_text()
hr_html = output_path.read_text()

# ledger skeleton present on SELF, absent on HR
assert "c-exhibit" in self_html, "SELF build missing ledger exhibits"
assert "c-exhibit" not in hr_html, "HR build must not render ledger sections"

# cross-LLM prompt text never reaches ANY output (spec §4)
for name, html_text in (("self", self_html), ("hr", hr_html)):
    assert "GROK_PRIVATE_MARKER" not in html_text, (
        f"{name} build leaked grok prompt text")

# narration is escaped, not executed
assert "<script>alert('n')</script>" not in self_html

# snapshot hook: SELF appended exactly one line, HR none
history = (DEMO_ROOT / "history.jsonl").read_text().strip().splitlines()
assert len(history) == 1, f"expected 1 snapshot line, got {len(history)}"
```

(Match the file's existing assertion style — it may use plain `assert` or a helper; copy whatever `tests/smoke_test.py` already does. Keep the existing hostile-payload injections untouched. Note build order matters for the history assertion: run the SELF build after writing the tmp history path, and give the HR build the same `--history-file` to prove it doesn't append.)

- [ ] **Step 3: Run the full suites**

Run: `python3 -m pytest tests/ -q && node --test tests/chart_layout.test.mjs`
Expected: all green except the 2 known-baseline failures in `tests/test_build_html_additions.py` (verify they are exactly `test_zh_tw_build_contains_localized_strings` and `test_disclaimer_placeholder_in_template`, same as clean main).

- [ ] **Step 4: Commit**

```bash
git add tests/smoke_test.py
git commit -m "test(smoke): end-to-end cross-LLM pipeline, ledger privacy + snapshot assertions"
```

---

### Task 10: SKILL.md rewrite (Step 1 adapters, Step 3 ledger narration, audience table)

**Files:**
- Modify: `SKILL.md`

**Interfaces:**
- Consumes: CLI shapes from Tasks 2, 3, 5, 6, 8 (exact flags).

- [ ] **Step 1: Add Step 1c — cross-LLM scan** (after `### Step 1b — Aggregate`)

New subsection instructing the skill to run the three adapters (each wrapped so a missing source dir is fine — the scripts already handle it), then re-run `aggregate.py` with the `--cross-llm-rows` flags. Include the exact commands from Task 5 Step 4 with real paths (`~/.codex/sessions` etc. — defaults, so no `--sessions-dir` needed in the real run). State the tier table (full / partial / presence-only) in one sentence each and that the 9-dim scores remain Claude-only.

- [ ] **Step 2: Rewrite Step 3 as ledger narration**

Replace the `### SELF audience format` 4-zone story template with the ledger-narration format. The new instructions must specify:
- Output file: `ledger-narration.md`, structure exactly `# opening` / `# output-ledger` / `# team-ledger` (first line of each book = the opener claim; the rest = body prose).
- The opening line: ONE sentence — what the AI team delivered this period, what it cost, biggest leak if known ("thirty-second read").
- Embedded audit-discipline rules (spec §2), verbatim as writing rules: numbers before adjectives (every evaluative adjective anchors to a number + threshold); no cheerleading, no sandwiching; positive claims need evidence at the same bar as negative ones — unsourceable claims are cut; self-referential comparison only (never "better than most users"); lower-bound accounting (only evidence-backed deliverables count).
- Pass the file to the build via `--ledger-narration ledger-narration.md` (SELF builds only).
- Keep Step 3's existing HR-memo instructions untouched (recruiter rebuild is Phase 3).

- [ ] **Step 3: Update the audience-conditional table** (`## V4 audience-conditional rendering`, line 502)

Add three rows: `Opening band | rendered | absent`, `Output ledger | rendered | absent`, `Team ledger | rendered | absent`. Add one sentence below the table: cross-LLM prompt text never renders in any external version. Update `## Files` with one-liners for the four new scripts (`cross_llm_common.py`, `scan_codex.py`, `scan_grok.py`, `scan_antigravity.py`) and the snapshot hook file path. Rename the section header from "V4 audience-conditional rendering" to "Audience-conditional rendering" (drop the version stamp; also fix the two `V4` references in `CLAUDE.md`'s architecture notes if the wording no longer matches).

- [ ] **Step 4: Verify consistency**

Run: `grep -n "ledger-narration\|cross-llm-rows\|scan_codex\|scan_grok\|scan_antigravity\|history-file" SKILL.md`
Expected: every flag name matches the implemented CLIs exactly (`--ledger-narration`, `--cross-llm-rows`, `--history-file`).

- [ ] **Step 5: Commit**

```bash
git add SKILL.md CLAUDE.md
git commit -m "docs(skill): Step 1c cross-LLM scan, Step 3 ledger narration, audience table update"
```

---

### Task 11: finish — full-suite run, /simplify, PR

- [ ] **Step 1: Run everything**

```bash
python3 -m pytest tests/ -q
node --test tests/chart_layout.test.mjs
```

Expected: green except the 2 known-baseline failures (verify identical on clean main first: `git stash && python3 -m pytest tests/test_build_html_additions.py -q && git stash pop`).

- [ ] **Step 2: Regenerate the committed example output** if `assets/example-output*.html` generation is scripted (check README § "Running manually"); otherwise skip — never commit real-data output.

- [ ] **Step 3: /simplify pass, then verification-before-completion, then PR**

PR title: `feat: V5 Phase 1 — cross-LLM adapters, ledger skeleton, snapshot hook (#spec 2026-07-14)`. Base: `main`. Include the implementation-notes deviations log in the PR body.

---

## Self-review (done at plan time)

- **Spec coverage (Phase 1 items, §9):** adapters → Tasks 2-3; snapshot hook → Task 6; SELF skeleton (opening line, output ledger, team ledger) → Tasks 7-8; SKILL.md rewrite → Task 10; demo data 4 sources → Task 4. Cross-cutting: §6 aggregation → Task 5; §7 schema + SCHEMA-CHANGES → Task 5; §10 error handling (parse-failure counts → Tasks 2-3/5; absent dir → adapters return empty; snapshot tolerance → Task 6); §11 testing rows 1, 2, 5, 6, 7 → Tasks 2-5, 7-9 (rows 3-4 are Phase 2 scope: blind-spot gates + praise lint).
- **Not covered on purpose:** blind-spot openers (Phase 2), badges (Phase 3 — snapshot writes `badges: []` so the line format is forward-compatible), canvas charts (deviation 2), praise lint (deviation 3), recruiter rebuild (Phase 3).
- **Type consistency check:** row field names identical across Tasks 2/3/4/5 (`source`, `coverage`, `segments`, `start_time`, `duration_minutes`, token fields); `compute_cross_llm(claude_rows, cross_rows)` consumed in Task 5 test and `main()` wiring; `_exhibit(no, title, body_html, source_line, locale=)` signature identical in Tasks 7/8; locale keys in Task 7 Interfaces = keys used in Task 8 code = keys asserted in tests. `append_history_snapshot(history_path, analysis, audience)` same in Task 6 test/impl/Task 9 smoke.
- **Open risks flagged for the implementer:** exact import mechanism for `scripts/` modules in tests (mirror `test_scan_transcripts.py`), the local-variable name of the loaded analysis dict in `build_html.main()`, `render()`'s parameter threading, and the `activity_metas` variable availability in session-meta mode (Task 5 note). These are look-and-match items, not design decisions.
