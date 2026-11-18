#!/usr/bin/env python3
"""Classify each session as hand-driven, launched by another tool, or unknown.

A session is the user's own usage only when the user drove it. A review
run that one tool starts inside another is automation, and counting it
would misstate both how much the user uses that tool and what the user
typed into it.

Rule (spec 2026-11-18 findings-first, section 5.2):

  launched  the session's own header says another session spawned it, or
            another tool's transcript shows a shell call starting this
            tool's CLI and the session began while that call was running
  unknown   the header says the run was non-interactive (one-shot exec)
            and no launching call was seen: nobody sat in the session,
            but who started it — the user at a shell, a script, a tool
            whose transcript is gone — cannot be told
  direct    none of the above, and either the user and the tool went back
            and forth (multi_turn), or every tool that could have launched
            it still has transcripts covering that moment — so a launch
            would have been visible
  unknown   everything else

Absence of a launch counts as evidence only where a launch could have
been seen. When in doubt the session is not counted as the user's.
"""
from bisect import bisect_right
from datetime import timedelta, timezone

try:
    from cross_llm_common import parse_ts
except ImportError:  # pragma: no cover - exercised when imported as scripts.origin
    from scripts.cross_llm_common import parse_ts

ORIGINS = ("direct", "launched", "unknown")

# A session that starts while another tool's shell call to its CLI is
# running is treated as launched by that call. The call runs from the
# moment the tool asked for it until its result came back (a permission
# prompt can hold the start for minutes); the window is never shorter
# than this many seconds, which also covers calls whose result was not
# recorded. Time alone decides (no working-directory match): a launched
# run that changed directory must not pass as hand-driven.
LAUNCH_WINDOW_SECONDS = 60

# Values of a session header's launch-source field, compared lowercased.
# SPAWNED: another session of the same tool created this one.
# NON_INTERACTIVE: a one-shot run with nobody in the session. That alone
# does not say who started it, so it never makes a session "launched" —
# it only rules out "direct".
SPAWNED_SOURCES = frozenset({"subagent"})
NON_INTERACTIVE_SOURCES = frozenset({"exec", "mcp"})

# Sources whose transcripts record shell calls, i.e. the only tools that
# can be seen launching another one.
LAUNCHER_SOURCES = ("claude", "codex")


def _source(row):
    """Claude rows from the activity pool carry no `source` field."""
    return row.get("source") or "claude"


def session_key(row):
    return f"{_source(row)}:{row.get('session_id')}"


def _ts(value):
    """Parse to an offset-aware datetime, or None. A timestamp without an
    offset is read as UTC — the same rule aggregate._parse_dt applies, so
    both modules place a row at the same instant."""
    dt = parse_ts(value)
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _row_span(row):
    """(first, last) activity instant of a row: the hull of its well-formed
    `segments`, else its start_time for both ends. (None, None) if the row
    has no usable time."""
    starts, ends = [], []
    for seg in row.get("segments") or []:
        if not (isinstance(seg, (list, tuple)) and len(seg) == 2):
            continue
        lo, hi = _ts(seg[0]), _ts(seg[1])
        if lo and hi and hi >= lo:
            starts.append(lo)
            ends.append(hi)
    if starts:
        return min(starts), max(ends)
    start = _ts(row.get("start_time"))
    return start, start


def launch_windows(rows):
    """{target: (starts, reach)} — for each launched tool, the request
    times of every call that mentions it, sorted, and beside each the
    latest `until` of any call at or before it. A session start S falls
    inside some call's window iff reach[i] >= S for the last call i with
    starts[i] <= S.

    `until` is when the call's result came back, floored at the request
    time plus the minimum window. Every row contributes, orphan subagent
    fragments included: a fragment whose parent transcript rotated away
    still shows the shell call that started another tool."""
    floor = timedelta(seconds=LAUNCH_WINDOW_SECONDS)
    by_target = {}
    for r in rows:
        for ev in r.get("cli_launches") or []:
            ts = _ts(ev.get("ts"))
            if not ts or not ev.get("target"):
                continue
            until = _ts(ev.get("until"))
            if until is None or until < ts + floor:
                until = ts + floor
            by_target.setdefault(ev["target"], []).append((ts, until))
    out = {}
    for target, spans in by_target.items():
        spans.sort()
        reach, latest = [], None
        for _, until in spans:
            latest = until if latest is None or until > latest else latest
            reach.append(latest)
        out[target] = ([ts for ts, _ in spans], reach)
    return out


def _in_a_launch_window(source, start, windows):
    starts, reach = windows.get(source, ((), ()))
    i = bisect_right(starts, start)
    return i > 0 and reach[i - 1] >= start


def launcher_spans(rows):
    """{launcher: (earliest, latest) or None} for each tool that can be
    seen launching others AND that the user has sessions of.

    The span covers rows whose shell calls were scanned (they carry a
    cli_launches list). None means the tool's sessions exist but none
    were scanned — session-meta rows, an older scanner's output, or only
    orphan subagent fragments, whose parent transcript (where other
    launches would sit) is gone. A launcher the user has no sessions of
    is absent: it cannot have launched anything."""
    spans = {}
    for r in rows:
        src = _source(r)
        if src not in LAUNCHER_SOURCES or r.get("coverage") == "presence_only":
            continue
        spans.setdefault(src, None)
        if not isinstance(r.get("cli_launches"), list) \
                or r.get("orphan_subagent_only"):
            continue
        lo, hi = _row_span(r)
        if lo is None:
            continue
        cur = spans[src]
        spans[src] = (lo, hi) if cur is None else (min(cur[0], lo),
                                                   max(cur[1], hi))
    return spans


def _a_launch_would_have_been_seen(source, start, spans):
    """True when every OTHER launcher tool the user has sessions of still
    has scanned transcripts spanning `start`."""
    for launcher, span in spans.items():
        if launcher == source:
            continue
        if span is None or not (span[0] <= start <= span[1]):
            return False
    return True


def classify(row, windows, spans):
    source = _source(row)
    declared = row.get("launch_source")
    declared = declared.lower() if isinstance(declared, str) else None
    if declared in SPAWNED_SOURCES:
        return "launched"
    start = _row_span(row)[0]
    if start is None:
        return "unknown"
    if _in_a_launch_window(source, start, windows):
        return "launched"
    if declared in NON_INTERACTIVE_SOURCES:
        return "unknown"
    if row.get("multi_turn"):
        return "direct"
    if _a_launch_would_have_been_seen(source, start, spans):
        return "direct"
    return "unknown"


def classify_all(rows):
    """{"source:session_id": origin} for every row that can carry one.
    Not classified: presence_only rows (no content, no reliable start)
    and orphan subagent fragments (not a session anyone opened)."""
    windows = launch_windows(rows)
    spans = launcher_spans(rows)
    return {session_key(r): classify(r, windows, spans) for r in rows
            if r.get("coverage") != "presence_only" and r.get("session_id")
            and not r.get("orphan_subagent_only")}


def count_by_source(origins):
    """{source: {"direct": n, "launched": n, "unknown": n}}."""
    out = {}
    for key, origin in origins.items():
        bucket = out.setdefault(key.split(":", 1)[0], {o: 0 for o in ORIGINS})
        bucket[origin] += 1
    return out
