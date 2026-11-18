# scripts/cross_llm_common.py
"""Shared helpers for the cross-LLM scanner adapters.

The adapters (scan_codex.py, scan_grok.py, scan_antigravity.py) emit the
same row shape as scan_transcripts.py plus `source` and `coverage`, and —
for sources whose log files span multiple days (observed with resumed
Codex rollouts) — a `segments` list of activity windows split at idle
gaps, so parallel detection never counts idle days as active time.
"""
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

SEGMENT_GAP_MINUTES = 30

_NORM_KEEP_RE = re.compile(r"[^\w一-鿿]+")
_NORM_WS_RE = re.compile(r"\s+")


def normalize_prompt(text):
    """Normalize an instruction for exact-match repetition detection.

    Deliberately exact-match only (v1): lowercased, punctuation folded to
    spaces, whitespace collapsed. No truncation — identity uses the full
    normalized string, so two long instructions that only differ after a
    shared prefix must NOT collapse into one pattern (zero false positives
    beats higher recall for a tax the user will be told to fix). No fuzzy
    matching either. Display truncation (the ≤120-char exemplar shown to the
    user) happens separately in aggregate.bs_repeated_instructions.

    Shared with aggregate.py (which imports this rather than keeping its own
    copy) and the scan_*.py adapters, which call prompt_identity() below on
    the FULL prompt text before they truncate first_prompt to 500 chars for
    display.
    """
    if not isinstance(text, str):
        return ""
    # \w keeps underscores, but "run_full_tests" and "run full tests" are
    # the same instruction under punctuation folding — fold "_" explicitly.
    t = _NORM_KEEP_RE.sub(" ", text.lower().replace("_", " "))
    return _NORM_WS_RE.sub(" ", t).strip()


def prompt_identity(text):
    """sha1 hexdigest of normalize_prompt(text) over the FULL (untruncated)
    prompt — an identity key for exact-match repetition grouping that
    survives adapters truncating first_prompt to 500 chars for display.

    Returns None for empty/falsy normalized text (nothing to key on)."""
    norm = normalize_prompt(text)
    if not norm:
        return None
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def parse_ts(s) -> Optional[datetime]:
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_jsonl_object(line: str) -> Optional[dict]:
    """Parse one JSONL line, returning the dict or None if the line is
    malformed JSON OR syntactically valid JSON that isn't an object (a bare
    number/string/array). Shared by scan_codex.py, scan_grok.py, and
    aggregate.load_cross_llm_rows so "is this line a usable record" is
    defined in exactly one place instead of three matching isinstance
    checks."""
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        return None
    return rec if isinstance(rec, dict) else None


def to_local_iso(dt: datetime) -> str:
    return dt.astimezone().isoformat()


def split_segments(timestamps, gap_minutes: int = SEGMENT_GAP_MINUTES):
    if not timestamps:
        return []
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


def segments_and_duration(timestamps, gap_minutes: int = SEGMENT_GAP_MINUTES):
    """Sort timestamps, split into idle-gap segments, and return
    (segments_as_local_iso_pairs, active_duration_minutes)."""
    ts = sorted(timestamps)
    segs = split_segments(ts, gap_minutes)
    duration = round(sum((e - s).total_seconds() for s, e in segs) / 60)
    return [[to_local_iso(s), to_local_iso(e)] for s, e in segs], duration


def write_rows(rows, output) -> None:
    out = Path(output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


# --- user turns + CLI launch detection (findings-first Phase 1) -----------
#
# Every scanner can emit a second file of the turns the user typed by hand
# (--user-turns-output). That file holds raw prompt text: it stays in the
# working directory and never flows into analysis-data.json or any HTML.

# A prompt longer than TURN_TEXT_CAP keeps its head and its tail (pasted
# material tends to sit in the middle; the instruction is at one end).
TURN_TEXT_CAP = 4000
ASSISTANT_TAIL_CAP = 300

# A shell command that mentions another AI CLI as a word of its own:
# `codex exec`, `/opt/bin/codex review`, `nohup codex ... &`, `bash -lc
# 'claude -p x'`, `codex.exe exec`. Deliberately loose. Parsing for
# "command position" would miss every wrapper nobody listed, and a miss is
# the costly error: the session it launched would then read as
# hand-driven. The tight filter is elsewhere — origin.py only counts a
# mention when a session of that tool also starts while the call is
# running. A stray mention (`command -v codex`) can therefore mark an
# unrelated session that happens to start in that window as launched;
# that errs on the side the design chooses (undercount hand-driven use).
# Names inside a longer word or a path component do not match
# (`codex-notes.md`, `~/.claude/settings.json`).
_CLI_MENTION_RE = re.compile(
    r"(?<![\w.\-])(codex|grok|claude)(?:\.exe)?(?![\w.\-/])")

USER_TURNS_HELP = ("Also write one row per prompt the user typed to this "
                   "JSONL file (created owner-readable only). It holds raw "
                   "prompt text: keep it out of version control and out of "
                   "any report.")


def add_user_turns_arg(parser):
    parser.add_argument("--user-turns-output", default=None,
                        help=USER_TURNS_HELP)


def check_distinct_outputs(parser, *paths):
    """Refuse two output flags that resolve to one file: the second write
    would silently replace the first (and put raw prompt text where
    session rows were expected)."""
    seen = set()
    for p in paths:
        if not p:
            continue
        path = Path(p).expanduser()
        resolved = path.resolve()
        try:
            st = path.stat()
            identity = (st.st_dev, st.st_ino)   # catches hard links too
        except OSError:
            identity = None
        # Most macOS and Windows volumes ignore case, and a file that does
        # not exist yet has no inode to compare: two spellings that differ
        # only in case are refused everywhere rather than probed for.
        folded = str(resolved).casefold()
        if resolved in seen or folded in seen \
                or (identity is not None and identity in seen):
            parser.error(f"two output flags point at the same file: {p}")
        seen.add(resolved)
        seen.add(folded)
        if identity is not None:
            seen.add(identity)


def cli_launch_targets(command):
    """Names of the AI CLIs a shell command mentions, in order of
    appearance, without duplicates."""
    if not isinstance(command, str) or not command:
        return []
    out = []
    for m in _CLI_MENTION_RE.finditer(command):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def make_cli_launch(target, ts, until=None):
    """One launch event. ts = when the call was requested; until = when
    its result came back (None if never recorded)."""
    return {"target": target, "ts": ts, "until": until}


def clip_turn_text(text):
    if len(text) <= TURN_TEXT_CAP:
        return text
    half = TURN_TEXT_CAP // 2
    omitted = len(text) - 2 * half
    return f"{text[:half]}\n[... {omitted} characters omitted ...]\n{text[-half:]}"


def make_user_turn(source, session_id, project_path, ts, turn_index, text,
                   after_interrupt=False, prev_assistant=None,
                   prompt_source=None):
    """One user-turns row. `text` is kept as typed, leading and trailing
    whitespace included; text longer than the cap is clipped in the middle
    and text_len keeps the original length. prev_assistant_tail is the end
    of the reply the user was answering, or None when there was none (or
    the source records no assistant text). prompt_source is the
    transcript's own label for how the prompt arrived, where it has one."""
    tail = None
    if isinstance(prev_assistant, str) and prev_assistant.strip():
        tail = prev_assistant.strip()[-ASSISTANT_TAIL_CAP:]
    return {
        "source": source,
        "session_id": session_id,
        "project_path": project_path,
        "ts": ts,
        "turn_index": turn_index,
        "text": clip_turn_text(text),
        "text_len": len(text),
        "after_interrupt": bool(after_interrupt),
        "prev_assistant_tail": tail,
        "prompt_source": prompt_source,
    }


def write_private_text(text, output) -> None:
    """Write a working file that holds prompt text or session ids so that
    only the current user can ever read it. The content goes to a fresh
    0600 file beside the target, which then replaces the target in one
    step: an earlier file at that path — whatever its mode, whoever has
    it open, symlink or hard link — is swapped out, never written into.
    The usual working directory is under /tmp, which other local accounts
    can list."""
    out = Path(output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{out.name}.", dir=out.parent)
    try:
        os.fchmod(fd, 0o600)   # exactly 0600, whatever the umask
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, out)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_user_turns(turns, output) -> None:
    write_private_text(
        "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in turns), output)
