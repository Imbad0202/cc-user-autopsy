#!/usr/bin/env python3
"""Classify each session as hand-driven, started by a tool, or unknown.

A session is the user's own usage only when the user drove it. A review
run that one tool starts inside another, a scheduled job, a script's
one-shot call: these are automation, and counting them would misstate
both how much the user uses a tool and what the user typed into it.

`direct` is given on one kind of evidence only: the transcript's own
record of a person at the keyboard. Earlier designs also inferred it,
from absence ("no launch was seen, and one would have been visible") and
from behaviour ("the user typed, got an answer, and typed again"). The
first has holes wherever a launcher leaves no transcript; the second is
something a script can do too. Both are gone. What is not recorded as
hand-driven is never `direct` (it is `launched` or `unknown`), and only
`direct` sessions feed the findings.

Rule (spec 2026-11-18 findings-first, section 5.2), first match wins:

  launched  the session's own header says another session spawned it
  direct    the transcript itself records a person at the keyboard
            (row field `interactive` is True: Claude Code marks each
            prompt's source and the session's entrypoint; Codex names an
            interactive client in its header)
  launched  the session began while some tool's shell call naming this
            tool's CLI was running (after the request, and until its
            result came back or 60 seconds, whichever is later)
  unknown   everything else: a non-interactive run with no launching
            call in sight (who started it — a script, a scheduler, a tool
            whose transcript is gone — is not recorded), and any session
            whose transcript does not say how it was run and that no call
            was seen to start (Grok sessions, a Codex session whose
            header names no source, a Claude Code transcript older than
            the prompt labels: none of these can ever be `direct`)
"""
from bisect import bisect_left
from datetime import timedelta, timezone

try:
    from cross_llm_common import parse_ts
except ImportError:  # pragma: no cover - exercised when imported as scripts.origin
    from scripts.cross_llm_common import parse_ts

ORIGINS = ("direct", "launched", "unknown")
# When two rows carry the same session key, the more cautious verdict
# stands (later index wins).
_CAUTION = {"direct": 0, "unknown": 1, "launched": 2}

# A session that starts while a shell call naming its tool's CLI is
# running is treated as launched by that call. The call runs from the
# moment it was requested until its result came back (a permission prompt
# can hold the start for minutes). The window is never shorter than this
# many seconds: the result time may be unknown, and a backgrounded call
# returns at once while the run it started is still coming up. Time alone decides: the working directory
# is not compared.
LAUNCH_WINDOW_SECONDS = 60

# Value of a session header's launch-source field (lowercased) that means
# another session of the same tool created this one.
SPAWNED_SOURCES = frozenset({"subagent"})

KNOWN_TARGETS = frozenset({"claude", "codex", "grok"})

# Sources whose transcripts can record a person at the keyboard. A row
# from any other source is never `direct`, whatever its `interactive`
# field says (Grok's history records nothing of the kind).
RECORDING_SOURCES = frozenset({"claude", "codex"})


def _source(row):
    """Claude rows from the activity pool carry no `source` field."""
    return row.get("source") or "claude"


def session_key(row):
    return f"{_source(row)}:{row.get('session_id')}"


def _ts(value):
    """Parse to an offset-aware datetime, or None. A timestamp without an
    offset is read as UTC — the same rule aggregate._parse_dt applies."""
    dt = parse_ts(value)
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _row_start(row):
    """First activity instant of a row: the earliest start among its
    well-formed `segments`, else its start_time. None if unusable."""
    starts = []
    segments = row.get("segments")
    for seg in segments if isinstance(segments, list) else []:
        if isinstance(seg, (list, tuple)) and len(seg) == 2:
            lo, hi = _ts(seg[0]), _ts(seg[1])
            if lo and hi and hi >= lo:
                starts.append(lo)
    return min(starts) if starts else _ts(row.get("start_time"))


def launch_windows(rows):
    """{target: (starts, reach)} — for each tool, the request times of
    every shell call that names its CLI, sorted, and beside each the
    latest `until` of any call at or before it. A session start S falls
    inside some call's window iff reach[i] >= S for the last call i with
    starts[i] < S.

    Every row contributes, orphan subagent fragments included: a fragment
    whose parent transcript rotated away still shows the call it made."""
    floor = timedelta(seconds=LAUNCH_WINDOW_SECONDS)
    by_target = {}
    for r in rows:
        events = r.get("cli_launches")
        if not isinstance(events, list):
            continue
        for ev in events:
            if not isinstance(ev, dict):
                continue
            target = ev.get("target")
            if not isinstance(target, str) or target not in KNOWN_TARGETS:
                continue
            ts = _ts(ev.get("ts"))
            if not ts:
                continue
            # A backgrounded call returns at once while the run it
            # started is still coming up, so the window never ends sooner
            # than the floor.
            until = _ts(ev.get("until"))
            try:
                earliest_end = ts + floor
            except OverflowError:
                # A timestamp at the very end of the calendar: corrupt.
                continue
            if until is None or until < earliest_end:
                until = earliest_end
            by_target.setdefault(target, []).append((ts, until))
    out = {}
    for target, spans in by_target.items():
        spans.sort()
        reach, latest = [], None
        for _, until in spans:
            latest = until if latest is None or until > latest else latest
            reach.append(latest)
        out[target] = ([ts for ts, _ in spans], reach)
    return out


def _in_a_launch_window(row, windows):
    start = _row_start(row)
    if start is None:
        return False
    starts, reach = windows.get(_source(row), ((), ()))
    # Strictly earlier calls only: a session cannot have been started by
    # a call made at or after its own first record (which also keeps a
    # session from matching a call it made itself).
    i = bisect_left(starts, start)
    return i > 0 and reach[i - 1] >= start


def classify(row, windows):
    declared = row.get("launch_source")
    if isinstance(declared, str) and declared.lower() in SPAWNED_SOURCES:
        return "launched"
    if row.get("interactive") is True and _source(row) in RECORDING_SOURCES:
        return "direct"
    if _in_a_launch_window(row, windows):
        return "launched"
    return "unknown"


def classify_all(rows):
    """{"source:session_id": origin} for every row that can carry one.
    Not classified: presence_only rows (no content to judge) and orphan
    subagent fragments (not a session anyone opened)."""
    windows = launch_windows(rows)
    out = {}
    for r in rows:
        if r.get("coverage") == "presence_only" or not r.get("session_id") \
                or r.get("orphan_subagent_only"):
            continue
        key, verdict = session_key(r), classify(r, windows)
        if key not in out or _CAUTION[verdict] > _CAUTION[out[key]]:
            out[key] = verdict
    return out


def count_by_source(origins):
    """{source: {"direct": n, "launched": n, "unknown": n}}."""
    out = {}
    for key, origin in origins.items():
        bucket = out.setdefault(key.split(":", 1)[0], {o: 0 for o in ORIGINS})
        bucket[origin] += 1
    return out
