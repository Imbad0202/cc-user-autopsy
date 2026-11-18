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
            and forth (multi_turn), or a launch would have been visible:
            every other tool that can launch one was scanned, and its
            retained transcripts cover that moment without a gap
  unknown   everything else

"Would have been visible" is judged narrowly. A launcher tool whose
adapter was not run, or whose sessions at that moment are known only
from rows without scanned shell calls, hides whatever it launched.
Transcripts are rotated by age, so what is retained is the recent,
unbroken run of sessions; an older straggler that survived rotation does
not vouch for the weeks between it and that run.

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

# Two retained sessions of one tool further apart than this are treated as
# separated by rotated-away history, not by the user simply being away.
COVERAGE_GAP_DAYS = 7

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
    `segments`, else start_time to start_time + duration_minutes.
    (None, None) if the row has no usable time."""
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
    if start is None:
        return None, None
    minutes = row.get("duration_minutes")
    if isinstance(minutes, (int, float)) and minutes > 0:
        return start, start + timedelta(minutes=minutes)
    return start, start


def launch_windows(rows):
    """{target: (starts, reach)} — for each launched tool, the request
    times of every call that mentions it, sorted, and beside each the
    latest `until` of any call at or before it. A session start S falls
    inside some call's window iff reach[i] >= S for the last call i with
    starts[i] <= S.

    `until` is when the call's result came back. A call to a DIFFERENT
    tool gets at least the minimum window (a backgrounded call returns at
    once while the run it started is still coming up). A call that names
    the row's own tool — `claude -p` from a Claude session — keeps its
    real duration when known: sessions of one tool start beside each
    other all the time, and a padded window would sweep them in.

    Every row contributes, orphan subagent fragments included: a fragment
    whose parent transcript rotated away still shows the shell call that
    started another tool."""
    floor = timedelta(seconds=LAUNCH_WINDOW_SECONDS)
    by_target = {}
    for r in rows:
        events = r.get("cli_launches")
        if not isinstance(events, list):
            continue
        own = _source(r)
        for ev in events:
            if not isinstance(ev, dict) or not ev.get("target"):
                continue
            ts = _ts(ev.get("ts"))
            if not ts:
                continue
            until = _ts(ev.get("until"))
            if until is None or until < ts:
                until = ts + floor
            elif ev["target"] != own and until < ts + floor:
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


def _in_a_launch_window(row, start, windows):
    """A session cannot have been started by a call made after it began,
    so its own calls never match it: they all come later than `start`."""
    starts, reach = windows.get(_source(row), ((), ()))
    i = bisect_right(starts, start)
    return i > 0 and reach[i - 1] >= start


def launcher_coverage(rows, scanned_sources=None):
    """What is known about each tool that can launch others:

      {launcher: {"retained": (lo, hi) or None, "blind": [(lo, hi), ...]}}

    retained  the recent unbroken run of this tool's scanned sessions
              (rows with a cli_launches list, orphan fragments excluded):
              walking back from the latest one, the run ends at the first
              gap longer than COVERAGE_GAP_DAYS. None if no scanned row
              has a usable time, or if the tool was not scanned at all.
    blind     spans of this tool's sessions that exist but whose shell
              calls were NOT scanned (session-meta rows, an older
              scanner's output). Whatever they launched is invisible.

    scanned_sources: the tools whose adapter actually ran. A launcher
    missing from it gets retained=None — "no rows" then means "not
    looked", not "launched nothing". When the argument is None, only
    launchers with at least one scanned row count as scanned."""
    scanned, blind, has_sessions = {}, {}, set()
    for r in rows:
        src = _source(r)
        if src not in LAUNCHER_SOURCES or r.get("coverage") == "presence_only":
            continue
        has_sessions.add(src)
        if r.get("orphan_subagent_only"):
            # Proof the tool was in use, but its parent transcript — where
            # other launches would sit — is gone: no coverage from it.
            continue
        lo, hi = _row_span(r)
        if lo is None:
            continue
        bucket = scanned if isinstance(r.get("cli_launches"), list) else blind
        bucket.setdefault(src, []).append((lo, hi))
    if scanned_sources is None:
        scanned_sources = set(scanned)
    gap = timedelta(days=COVERAGE_GAP_DAYS)
    out = {}
    for launcher in LAUNCHER_SOURCES:
        retained = None
        spans = sorted(scanned.get(launcher, ()))
        if launcher in scanned_sources and spans:
            lo, hi = spans[-1]
            for s_lo, s_hi in reversed(spans[:-1]):
                if lo - s_hi > gap:
                    break
                lo, hi = min(lo, s_lo), max(hi, s_hi)
            retained = (lo, hi)
        elif launcher in scanned_sources and launcher not in has_sessions:
            # Scanned, and the user has no sessions of it: nothing to hide.
            continue
        out[launcher] = {"retained": retained,
                         "blind": blind.get(launcher, [])}
    return out


def _a_launch_would_have_been_seen(source, start, coverage):
    """True when, for every OTHER launcher tool, `start` lies inside its
    retained run and inside none of its unscanned sessions."""
    pad = timedelta(seconds=LAUNCH_WINDOW_SECONDS)
    for launcher, known in coverage.items():
        if launcher == source:
            continue
        retained = known["retained"]
        if retained is None or not (retained[0] <= start <= retained[1]):
            return False
        if any(lo <= start <= hi + pad for lo, hi in known["blind"]):
            return False
    return True


def classify(row, windows, coverage):
    source = _source(row)
    declared = row.get("launch_source")
    declared = declared.lower() if isinstance(declared, str) else None
    if declared in SPAWNED_SOURCES:
        return "launched"
    start = _row_span(row)[0]
    if start is None:
        return "unknown"
    if _in_a_launch_window(row, start, windows):
        return "launched"
    if declared in NON_INTERACTIVE_SOURCES:
        return "unknown"
    if row.get("multi_turn"):
        return "direct"
    if _a_launch_would_have_been_seen(source, start, coverage):
        return "direct"
    return "unknown"


def classify_all(rows, scanned_sources=None):
    """{"source:session_id": origin} for every row that can carry one.
    Not classified: presence_only rows (no content, no reliable start)
    and orphan subagent fragments (not a session anyone opened).
    scanned_sources: see launcher_coverage."""
    windows = launch_windows(rows)
    coverage = launcher_coverage(rows, scanned_sources)
    return {session_key(r): classify(r, windows, coverage) for r in rows
            if r.get("coverage") != "presence_only" and r.get("session_id")
            and not r.get("orphan_subagent_only")}


def count_by_source(origins):
    """{source: {"direct": n, "launched": n, "unknown": n}}."""
    out = {}
    for key, origin in origins.items():
        bucket = out.setdefault(key.split(":", 1)[0], {o: 0 for o in ORIGINS})
        bucket[origin] += 1
    return out
