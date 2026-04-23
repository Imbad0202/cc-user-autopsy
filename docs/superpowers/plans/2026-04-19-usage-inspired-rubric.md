# Usage-Inspired Rubric Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship per-dimension pattern sentences, a five-item Usage-characteristics block in the Activity panel, and scoring-independence disclaimers — modelled on Anthropic's official `/usage` UX mechanics, scoped to cc-user-autopsy's skill-use diagnostic lane.

**Architecture:** Extend the scanner to record `hit_output_limit` per session. Extend each of the eight `score_dX_*` functions to return a deterministic `pattern` string (or `None`). Extend `compute_activity` to compute a `usage_characteristics` dict when prerequisites are met. Render all three in `build_html.py`, gated through `locales.py` (en canonical + zh_TW `[TODO]` placeholders). All logic rule-based; no runtime LLM calls.

**Tech Stack:** Python 3 stdlib only (json, collections, pathlib, datetime). `unittest` for tests. HTML via `string.Template`. No new runtime deps.

**Spec:** [`docs/superpowers/specs/2026-04-19-usage-inspired-rubric-design.md`](../specs/2026-04-19-usage-inspired-rubric-design.md)

---

## File inventory

**Create:**
- `tests/test_usage_characteristics.py` — unit tests for new aggregate math + render

**Modify:**
- `scripts/scan_transcripts.py` — emit `hit_output_limit` per row (~3 lines)
- `scripts/aggregate.py`
  - `_REDACTED_META_KEYS` — add `hit_output_limit` (1 line)
  - `build_sessions` / transcript-row merge — propagate `hit_output_limit` (~2 lines)
  - `score_d1_delegation` through `score_d8_time_mgmt` — each returns `pattern` field (~5 lines each)
  - `compute_activity` — append `usage_characteristics` block (~80 lines)
- `scripts/locales.py` — 6 new keys × 2 locales
- `scripts/build_html.py`
  - CSS block — `.pattern`, `.score-disclaimer`, `.usage-characteristics` group (~60 lines)
  - `score_rows` render loop — insert `<p class="pattern">` conditionally (~3 lines)
  - `$score_disclaimer` template variable + HTML placement (~5 lines)
  - `how_to_read_section` (HR mode) — append `<dt>/<dd>` pair (~2 lines)
  - `_build_activity_panel` — append Usage-characteristics render (~30 lines)
- `tests/test_build_html_additions.py` — extend with pattern + disclaimer + UC tests
- `tests/test_scan_transcripts.py` — extend with `hit_output_limit` case
- `tests/test_locales.py` — add `@skip`-marked TODO-marker test

---

## Task ordering rationale

Tasks run bottom-up: signal plumbing (scanner) → data model (aggregate) → text catalogue (locales) → render (build_html) → activity panel. Each task ships a passing test before the next starts. Commits are per-task to keep the diff reviewable.

---

## Task 1: Scanner emits `hit_output_limit`

**Files:**
- Modify: `scripts/scan_transcripts.py` (add field to emitted row)
- Test: `tests/test_scan_transcripts.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scan_transcripts.py` (create the class if not already structured this way — if it is, add a method):

```python
class HitOutputLimitTests(unittest.TestCase):
    def test_row_marks_hit_output_limit_when_max_tokens_seen(self):
        """Any assistant row with stop_reason='max_tokens' anywhere in the
        session should flip the session-level hit_output_limit flag True."""
        import json, tempfile, os
        from pathlib import Path
        # Build a minimal jsonl: one user, one assistant with max_tokens stop
        rows = [
            {"type": "user", "sessionId": "abc123",
             "message": {"role": "user", "content": "hi"},
             "timestamp": "2026-04-19T10:00:00Z"},
            {"type": "assistant", "sessionId": "abc123",
             "message": {"role": "assistant", "content": "truncated...",
                         "stop_reason": "max_tokens",
                         "usage": {"input_tokens": 10, "output_tokens": 8000}},
             "timestamp": "2026-04-19T10:00:05Z"},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "abc123.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in rows))
            # scan_transcripts exposes a per-file scan function; call whichever
            # is canonical. If the module exposes `scan_session_file(path)`,
            # use that. Otherwise, call the module as a subprocess and parse
            # the output line for this session.
            import subprocess, sys
            SKILL = Path(__file__).resolve().parent.parent
            result = subprocess.run(
                [sys.executable, str(SKILL / "scripts" / "scan_transcripts.py"),
                 "--projects-root", td, "--min-assistant-msgs", "0"],
                capture_output=True, text=True, check=True,
            )
            # Output is one JSON object per line on stdout
            emitted = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
            self.assertEqual(len(emitted), 1)
            self.assertTrue(emitted[0].get("hit_output_limit"))

    def test_row_hit_output_limit_false_when_no_max_tokens(self):
        import json, tempfile
        from pathlib import Path
        rows = [
            {"type": "user", "sessionId": "xyz789",
             "message": {"role": "user", "content": "hi"},
             "timestamp": "2026-04-19T10:00:00Z"},
            {"type": "assistant", "sessionId": "xyz789",
             "message": {"role": "assistant", "content": "done",
                         "stop_reason": "end_turn",
                         "usage": {"input_tokens": 10, "output_tokens": 20}},
             "timestamp": "2026-04-19T10:00:05Z"},
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "xyz789.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in rows))
            import subprocess, sys
            SKILL = Path(__file__).resolve().parent.parent
            result = subprocess.run(
                [sys.executable, str(SKILL / "scripts" / "scan_transcripts.py"),
                 "--projects-root", td, "--min-assistant-msgs", "0"],
                capture_output=True, text=True, check=True,
            )
            emitted = [json.loads(l) for l in result.stdout.splitlines() if l.strip()]
            self.assertEqual(len(emitted), 1)
            self.assertFalse(emitted[0].get("hit_output_limit", False))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/Projects/cc-user-autopsy
python3 -m unittest tests.test_scan_transcripts.HitOutputLimitTests -v
```
Expected: FAIL — `hit_output_limit` key absent from emitted row (assertTrue on None fails).

If the test errors because `--projects-root` isn't a recognized flag, first open `scripts/scan_transcripts.py` and confirm the argparse interface. Adjust the subprocess call to whatever flag the scanner accepts for a custom root (it's a small script; pick the closest existing flag — there's a `--projects-root` today; if named differently, match it). **Only adjust the test invocation, not the scanner expectation.**

- [ ] **Step 3: Implement minimal change in scanner**

In `scripts/scan_transcripts.py`, inside the per-session walk that assembles the emitted row, track a local flag and add it to output. Locate the block that builds the per-session dict (search for a return/emit that contains `"output_tokens": out_tok`; near line 315). Add next to the existing fields:

```python
# In the loop walking a session's jsonl lines:
#   initialize before the loop:
hit_limit = False
#   inside the loop, when handling an assistant message:
if isinstance(msg, dict) and msg.get("stop_reason") == "max_tokens":
    hit_limit = True
# ... existing code ...

# In the dict being emitted for the session:
"hit_output_limit": hit_limit,
```

Exact placement: add `hit_limit = False` near the other accumulators (line ~220 area where `user_interruptions = 0` is initialised). Add the detection inside whichever branch handles an assistant message. Add `"hit_output_limit": hit_limit,` in the emitted dict next to `"user_interruptions": user_interruptions,` (line ~321 area).

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest tests.test_scan_transcripts.HitOutputLimitTests -v
```
Expected: PASS on both methods.

- [ ] **Step 5: Run full test suite for scanner**

```bash
python3 -m unittest tests.test_scan_transcripts -v
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/scan_transcripts.py tests/test_scan_transcripts.py
git commit -m "feat(scanner): emit hit_output_limit per session row

Detects assistant messages with stop_reason='max_tokens' and flips a
session-level flag. Enables the Usage-characteristics block in later
commits. Rare event in practice (~2/50 in a real local sample), which
is what makes it a useful percent narrative.

Refs: docs/superpowers/specs/2026-04-19-usage-inspired-rubric-design.md"
```

---

## Task 2: Redacted schema propagates `hit_output_limit`

**Files:**
- Modify: `scripts/aggregate.py:175` (add to `_REDACTED_META_KEYS`)
- Modify: `scripts/aggregate.py:259` area (session builder merges the flag)
- Test: `tests/test_scan_transcripts.py` (extend redacted round-trip test if present; otherwise add minimal test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scan_transcripts.py`:

```python
class RedactedSchemaTests(unittest.TestCase):
    def test_redacted_keys_include_hit_output_limit(self):
        import sys
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(SKILL / "scripts"))
        import aggregate
        self.assertIn("hit_output_limit", aggregate._REDACTED_META_KEYS)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest tests.test_scan_transcripts.RedactedSchemaTests -v
```
Expected: FAIL — `hit_output_limit` not in set.

- [ ] **Step 3: Add field to redacted schema**

Edit `scripts/aggregate.py` at `_REDACTED_META_KEYS` (line 175). Add `"hit_output_limit"` to the set. The block becomes:

```python
_REDACTED_META_KEYS = {
    "session_id", "start_time", "project_path", "duration_minutes",
    "input_tokens", "output_tokens", "tool_counts", "user_message_count",
    "git_commits", "git_pushes", "user_interruptions", "tool_errors",
    "uses_task_agent", "uses_mcp", "uses_web_search", "uses_web_fetch",
    "lines_added", "lines_removed", "files_modified",
    "user_response_times", "message_hours",
    "assistant_message_count",
    "cache_creation_input_tokens", "cache_read_input_tokens",
    "model_counts",
    "hit_output_limit",
}
```

- [ ] **Step 4: Propagate in session builder**

Find the block around line 285-295 where transcript-row fields are copied into the session dict (the area with `"uses_task_agent": m.get("uses_task_agent", False),`). Add:

```python
"hit_output_limit": m.get("hit_output_limit", False),
```

next to `"uses_task_agent"` so meta-only sessions default to False.

- [ ] **Step 5: Run tests**

```bash
python3 -m unittest tests.test_scan_transcripts -v
```
Expected: All pass (new test + previously passing ones stay green).

- [ ] **Step 6: Commit**

```bash
git add scripts/aggregate.py tests/test_scan_transcripts.py
git commit -m "feat(aggregate): propagate hit_output_limit through session dict

Adds the field to _REDACTED_META_KEYS so cross-machine redacted dumps
round-trip the flag; propagates from transcript rows into the session
dict in build_sessions with a False default for meta-only rows."
```

---

## Task 3: `score_d1_delegation` returns `pattern`

**Files:**
- Modify: `scripts/aggregate.py:326-358` (score_d1_delegation)
- Test: `tests/test_usage_characteristics.py` (new)

- [ ] **Step 1: Create the test file with a failing test**

Create `tests/test_usage_characteristics.py`:

```python
"""TDD for per-dimension patterns and the usage_characteristics block.
See docs/superpowers/specs/2026-04-19-usage-inspired-rubric-design.md."""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import aggregate  # noqa: E402


def _session(sid, **overrides):
    base = {
        "session_id": sid,
        "uses_task_agent": False,
        "outcome": "",
        "session_type": "",
        "friction_counts": {},
        "duration_min": 10,
        "hour": 14,
        "prompt_chars": 60,
        "tool_counts": {},
        "hit_output_limit": False,
        "start": "2026-04-19T10:00:00Z",
        "user_msgs": 5,
        "assistant_msgs": 5,
    }
    base.update(overrides)
    return base


class ScoreD1PatternTests(unittest.TestCase):
    def test_pattern_present_when_sample_size_sufficient(self):
        """With ≥5 task-agent sessions and a mix of outcomes, D1 should
        return a pattern string comparing TA good-rate to overall."""
        sessions = [_session(f"s{i}", uses_task_agent=(i < 6),
                             outcome="fully_achieved" if i % 2 == 0 else "partial")
                    for i in range(12)]
        rated = sessions  # all have outcome set
        result = aggregate.score_d1_delegation(sessions, rated)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("%", result["pattern"])
        self.assertIn("Task agent", result["pattern"])

    def test_pattern_none_when_sample_too_small(self):
        """<5 sessions using Task agent → pattern is None."""
        sessions = [_session(f"s{i}", uses_task_agent=(i < 2),
                             outcome="fully_achieved")
                    for i in range(8)]
        rated = sessions
        result = aggregate.score_d1_delegation(sessions, rated)
        self.assertIn("pattern", result)
        self.assertIsNone(result["pattern"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest tests.test_usage_characteristics -v
```
Expected: FAIL — `pattern` key missing from returned dict.

- [ ] **Step 3: Implement pattern in score_d1_delegation**

In `scripts/aggregate.py` `score_d1_delegation` (line 326), before the final `return`, compute the pattern:

```python
    # Pattern string (descriptive contrast). None when sample too small.
    overall_good_rate = (
        100 * sum(1 for s in rated if is_good(s["outcome"])) / len(rated)
        if rated else 0
    )
    if len(ta_rated) >= 5:
        pattern = (
            f"Sessions that used Task agent had a {good_rate_ta:.0f}% "
            f"good-outcome rate, versus {overall_good_rate:.0f}% overall."
        )
    else:
        pattern = None
```

Then extend the returned dict:

```python
    return {
        "score": score,
        "metric_ta_rate_pct": round(ta_rate, 1),
        "metric_good_rate_with_ta_pct": round(good_rate_ta, 1),
        "explanation": f"{ta_rate:.0f}% of sessions used Task agent; good-outcome rate with Task agent was {good_rate_ta:.0f}%.",
        "pattern": pattern,
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD1PatternTests -v
```
Expected: PASS on both methods.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_usage_characteristics.py
git commit -m "feat(score d1): return descriptive pattern sentence

Compares Task-agent good-outcome rate vs overall when sample ≥5; None
otherwise. First of eight dimensions to grow the field."
```

---

## Task 4: `score_d2_rootcause` returns `pattern`

**Files:**
- Modify: `scripts/aggregate.py:361-384`
- Test: `tests/test_usage_characteristics.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_usage_characteristics.py`:

```python
class ScoreD2PatternTests(unittest.TestCase):
    def test_pattern_contrasts_non_iterative_vs_iterative(self):
        """With mixed session_type values and ≥5 rated, pattern contrasts
        good-outcome rates between iterative_refinement and not."""
        sessions = [_session(f"s{i}",
                             session_type="iterative_refinement" if i < 5 else "fresh_work",
                             outcome="fully_achieved" if i % 2 else "failed",
                             friction_counts={"buggy_code": 1} if i < 3 else {})
                    for i in range(12)]
        rated = sessions
        result = aggregate.score_d2_rootcause(sessions, rated, facets_coverage=80)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("iterative_refinement", result["pattern"])

    def test_pattern_none_when_facets_coverage_insufficient(self):
        """Low facet coverage → None (upstream returns None score anyway)."""
        sessions = [_session(f"s{i}") for i in range(12)]
        rated = sessions
        result = aggregate.score_d2_rootcause(sessions, rated, facets_coverage=10)
        self.assertIsNone(result.get("pattern"))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD2PatternTests -v
```
Expected: FAIL — `pattern` key missing.

- [ ] **Step 3: Implement**

In `score_d2_rootcause` (line 361), before the final `return`:

```python
    iter_sessions = [s for s in rated if s["session_type"] == "iterative_refinement"]
    non_iter_sessions = [s for s in rated if s["session_type"] != "iterative_refinement"]
    pattern = None
    if len(non_iter_sessions) >= 5 and len(iter_sessions) >= 1:
        non_iter_good = 100 * sum(1 for s in non_iter_sessions if is_good(s["outcome"])) / len(non_iter_sessions)
        iter_good = 100 * sum(1 for s in iter_sessions if is_good(s["outcome"])) / len(iter_sessions)
        pattern = (
            f"Sessions without iterative_refinement friction reached good outcomes "
            f"{non_iter_good:.0f}% of the time, versus {iter_good:.0f}% for "
            f"iterative_refinement sessions."
        )
```

Then add `"pattern": pattern,` to the returned dict. Also update the early-return at `facets_coverage < 30` to include `"pattern": None` so callers can always assume the key exists:

```python
    if facets_coverage < 30:
        return {"score": None, "reason": "insufficient facet coverage", "pattern": None}
```

And the `if not rated:` early-return likewise.

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD2PatternTests -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_usage_characteristics.py
git commit -m "feat(score d2): return pattern contrasting iterative vs non-iterative"
```

---

## Task 5: `score_d3_prompt_quality` returns `pattern`

**Files:**
- Modify: `scripts/aggregate.py:386-429`
- Test: `tests/test_usage_characteristics.py`

- [ ] **Step 1: Write the failing test**

```python
class ScoreD3PatternTests(unittest.TestCase):
    def test_pattern_compares_prompt_length_buckets(self):
        sessions = [_session(f"s{i}",
                             prompt_chars=150 if i < 6 else 30,
                             output_tokens=1000 if i < 6 else 300,
                             git_commits=1 if i % 2 == 0 else 0)
                    for i in range(12)]
        result = aggregate.score_d3_prompt_quality(sessions)
        self.assertIn("pattern", result)
        # Should either have a pattern string or be None — not missing entirely
        if result["pattern"] is not None:
            self.assertIn("≥100 chars", result["pattern"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD3PatternTests -v
```
Expected: FAIL — key missing.

- [ ] **Step 3: Read the existing function to confirm field names**

```bash
sed -n '386,429p' scripts/aggregate.py
```

The fields used inside `score_d3_prompt_quality` determine which are available. If `prompt_chars` isn't named that way (it may be `first_prompt_len` or similar), adjust the test fixture AND the pattern formula to match. **Rule: pattern uses only fields already read by the function — don't introduce new field names.**

- [ ] **Step 4: Implement pattern inside score_d3**

Add before the final `return`:

```python
    # Pattern: compare output-per-commit between long-prompt and short-prompt sessions
    long_prompt = [s for s in sessions if s.get("prompt_chars", 0) >= 100 and s.get("git_commits", 0) > 0]
    short_prompt = [s for s in sessions if s.get("prompt_chars", 0) <= 50 and s.get("git_commits", 0) > 0]
    pattern = None
    if len(long_prompt) >= 5 and len(short_prompt) >= 5:
        avg_long = sum(s.get("output_tokens", 0) / max(s.get("git_commits", 1), 1)
                       for s in long_prompt) / len(long_prompt)
        avg_short = sum(s.get("output_tokens", 0) / max(s.get("git_commits", 1), 1)
                        for s in short_prompt) / len(short_prompt)
        pattern = (
            f"Sessions with prompts ≥100 chars averaged {avg_long:.0f} tokens "
            f"per commit; ≤50-char prompts averaged {avg_short:.0f}."
        )
```

Ensure `"pattern": pattern,` is in every returned dict (including any early-return paths in the function).

- [ ] **Step 5: Run test to verify it passes**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD3PatternTests -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/aggregate.py tests/test_usage_characteristics.py
git commit -m "feat(score d3): return pattern comparing prompt-length buckets"
```

---

## Task 6: `score_d4_context_mgmt` returns `pattern`

**Files:**
- Modify: `scripts/aggregate.py:431-473`
- Test: `tests/test_usage_characteristics.py`

- [ ] **Step 1: Write the failing test**

```python
class ScoreD4PatternTests(unittest.TestCase):
    def test_pattern_reports_hit_output_limit_rate_for_long_sessions(self):
        sessions = [_session(f"s{i}",
                             duration_min=25,
                             git_commits=0,
                             hit_output_limit=(i < 3))
                    for i in range(8)]
        result = aggregate.score_d4_context_mgmt(sessions)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("output-token-limit", result["pattern"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD4PatternTests -v
```
Expected: FAIL — key missing.

- [ ] **Step 3: Implement**

In `score_d4_context_mgmt` (line 431), before the final return:

```python
    long_no_commit = [s for s in sessions
                      if s.get("duration_min", 0) > 20 and s.get("git_commits", 0) == 0]
    pattern = None
    if len(long_no_commit) >= 5:
        hit_rate = 100 * sum(1 for s in long_no_commit if s.get("hit_output_limit", False)) / len(long_no_commit)
        pattern = (
            f"Sessions over 20 minutes without a commit hit output-token-limit "
            f"{hit_rate:.0f}% of the time."
        )
```

Add `"pattern": pattern,` to every returned dict (including any early-returns).

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD4PatternTests -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_usage_characteristics.py
git commit -m "feat(score d4): return pattern reporting output-token-limit rate"
```

---

## Task 7: `score_d5_interrupt` returns `pattern`

**Files:**
- Modify: `scripts/aggregate.py:475-493`
- Test: `tests/test_usage_characteristics.py`

- [ ] **Step 1: Write the failing test**

```python
class ScoreD5PatternTests(unittest.TestCase):
    def test_pattern_reports_interrupt_good_outcome_rate(self):
        rated = [_session(f"s{i}",
                          user_interruptions=1 if i < 8 else 0,
                          outcome="fully_achieved" if i % 2 == 0 else "partial")
                 for i in range(12)]
        result = aggregate.score_d5_interrupt(rated)
        self.assertIn("pattern", result)
        self.assertIsNotNone(result["pattern"])
        self.assertIn("interrupted", result["pattern"].lower())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD5PatternTests -v
```
Expected: FAIL.

- [ ] **Step 3: Read and implement**

Inspect `score_d5_interrupt` (line 475) to confirm how it detects interrupts — it likely uses `user_interruptions > 0`. Pattern:

```python
    interrupted = [s for s in rated if s.get("user_interruptions", 0) > 0]
    pattern = None
    if len(interrupted) >= 5:
        good_rate = 100 * sum(1 for s in interrupted if is_good(s["outcome"])) / len(interrupted)
        pattern = (
            f"Of interrupted sessions, {good_rate:.0f}% still reached good outcomes "
            f"— a resilience signal."
        )
```

Adjust `rated` parameter and field name if the actual function uses a different variable; do not invent fields. Add `"pattern": pattern,` to all returns.

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD5PatternTests -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_usage_characteristics.py
git commit -m "feat(score d5): return pattern on interrupt recovery rate"
```

---

## Task 8: `score_d6_tool_breadth` returns `pattern`

**Files:**
- Modify: `scripts/aggregate.py:495-526`
- Test: `tests/test_usage_characteristics.py`

- [ ] **Step 1: Write the failing test**

```python
class ScoreD6PatternTests(unittest.TestCase):
    def test_pattern_reports_top_tool_concentration(self):
        sessions = [_session(f"s{i}",
                             tool_counts={"Read": 20, "Bash": 5} if i < 6
                                         else {"Read": 5, "Bash": 3, "Edit": 4, "Grep": 2},
                             outcome="fully_achieved" if i % 2 == 0 else "partial")
                    for i in range(12)]
        result = aggregate.score_d6_tool_breadth(sessions)
        self.assertIn("pattern", result)
        if result["pattern"] is not None:
            self.assertIn("%", result["pattern"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD6PatternTests -v
```
Expected: FAIL — pattern key missing.

- [ ] **Step 3: Implement**

Inside `score_d6_tool_breadth`:

```python
    # Top-tool concentration across all sessions
    total_tool_calls = sum(sum(s.get("tool_counts", {}).values()) for s in sessions)
    tool_totals = {}
    for s in sessions:
        for t, c in s.get("tool_counts", {}).items():
            tool_totals[t] = tool_totals.get(t, 0) + c
    pattern = None
    if total_tool_calls >= 20 and tool_totals:
        top_tool, top_count = max(tool_totals.items(), key=lambda kv: kv[1])
        top_pct = 100 * top_count / total_tool_calls
        # Diversity outcome correlation: sessions using >=4 distinct tools vs rest
        diverse = [s for s in sessions if len(s.get("tool_counts", {})) >= 4]
        narrow = [s for s in sessions if 0 < len(s.get("tool_counts", {})) <= 2]
        if len(diverse) >= 5 and len(narrow) >= 5:
            d_good = 100 * sum(1 for s in diverse if s.get("outcome", "") in ("fully_achieved", "mostly_achieved")) / len(diverse)
            n_good = 100 * sum(1 for s in narrow if s.get("outcome", "") in ("fully_achieved", "mostly_achieved")) / len(narrow)
            delta = d_good - n_good
            pattern = (
                f"Your top tool consumes {top_pct:.0f}% of calls — sessions "
                f"diversifying tools had {delta:+.0f}% outcome-quality delta."
            )
```

Add `"pattern": pattern,` to all returns.

Note: if the delta is 0 or negative, the `:+` formatter still renders a sign. That's fine; readers see "-5%" and understand it's a contrast.

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD6PatternTests -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_usage_characteristics.py
git commit -m "feat(score d6): return pattern on top-tool concentration + diversity delta"
```

---

## Task 9: `score_d7_writing` returns `pattern`

**Files:**
- Modify: `scripts/aggregate.py:528-549`
- Test: `tests/test_usage_characteristics.py`

- [ ] **Step 1: Write the failing test**

```python
class ScoreD7PatternTests(unittest.TestCase):
    def test_pattern_reports_misunderstood_request_rate(self):
        rated = [_session(f"s{i}",
                          goal_categories=["writing"] if i < 6 else ["coding"],
                          friction_counts={"misunderstood_request": 2} if i < 3 else {})
                 for i in range(12)]
        result = aggregate.score_d7_writing(rated)
        self.assertIn("pattern", result)
        if result["pattern"] is not None:
            self.assertIn("Writing", result["pattern"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD7PatternTests -v
```
Expected: FAIL.

- [ ] **Step 3: Implement**

In `score_d7_writing`, check the real field name for writing-session detection (inspect lines 528-549 — probably filters on `goal_categories` containing "writing"):

```python
    writing_sessions = [s for s in rated
                        if "writing" in (s.get("goal_categories") or [])]
    pattern = None
    if len(writing_sessions) >= 5:
        total_misu = sum(s.get("friction_counts", {}).get("misunderstood_request", 0)
                         for s in writing_sessions)
        avg = total_misu / len(writing_sessions)
        pattern = (
            f"Writing-related sessions averaged {avg:.1f} misunderstood_request "
            f"events per session."
        )
```

Add `"pattern": pattern,` to all returns.

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD7PatternTests -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_usage_characteristics.py
git commit -m "feat(score d7): return pattern on writing-session misunderstood-request rate"
```

---

## Task 10: `score_d8_time_mgmt` returns `pattern`

**Files:**
- Modify: `scripts/aggregate.py:551-588`
- Test: `tests/test_usage_characteristics.py`

- [ ] **Step 1: Write the failing test**

```python
class ScoreD8PatternTests(unittest.TestCase):
    def test_pattern_compares_morning_vs_after_10am(self):
        rated = [_session(f"s{i}",
                          hour=9 if i < 6 else 14,
                          outcome="fully_achieved" if i % 2 == 0 else "partial")
                 for i in range(12)]
        sessions = rated
        result = aggregate.score_d8_time_mgmt(sessions, rated)
        self.assertIn("pattern", result)
        if result["pattern"] is not None:
            self.assertIn("10am", result["pattern"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD8PatternTests -v
```
Expected: FAIL.

- [ ] **Step 3: Implement**

In `score_d8_time_mgmt`, before final return:

```python
    before_10 = [s for s in rated if s.get("hour", 12) < 10]
    after_10 = [s for s in rated if s.get("hour", 12) >= 10]
    pattern = None
    if len(before_10) >= 5 and len(after_10) >= 5:
        before_good = 100 * sum(1 for s in before_10 if is_good(s["outcome"])) / len(before_10)
        after_good = 100 * sum(1 for s in after_10 if is_good(s["outcome"])) / len(after_10)
        pattern = (
            f"Sessions started before 10am had a {before_good:.0f}% "
            f"good-outcome rate, versus {after_good:.0f}% for after-10am sessions."
        )
```

Add `"pattern": pattern,` to all returns.

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest tests.test_usage_characteristics.ScoreD8PatternTests -v
```
Expected: PASS.

- [ ] **Step 5: Run full aggregate test suite as a regression gate**

```bash
python3 -m unittest discover tests -v
```
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/aggregate.py tests/test_usage_characteristics.py
git commit -m "feat(score d8): return pattern contrasting morning vs after-10am outcomes

All eight dimensions now carry the pattern field. Next commits wire it
into the HTML template and add the activity-panel Usage-characteristics
block."
```

---

## Task 11: `compute_activity` emits `usage_characteristics`

**Files:**
- Modify: `scripts/aggregate.py:611-692` (`compute_activity`)
- Test: `tests/test_usage_characteristics.py`

- [ ] **Step 1: Write the failing test**

```python
class UsageCharacteristicsTests(unittest.TestCase):
    def test_block_emitted_when_10_plus_sessions(self):
        sessions = [_session(f"s{i}",
                             hit_output_limit=(i < 4),
                             duration_min=25 if i < 7 else 5,
                             friction_counts={"buggy_code": 1} if i < 6 else {},
                             uses_task_agent=(i < 3),
                             outcome="fully_achieved" if i % 2 == 0 else "partial",
                             tool_counts={"Read": 5} if i < 5 else {"Read": 2, "Bash": 1, "Edit": 1},
                             hour=22 if i % 3 == 0 else 14)
                    for i in range(20)]
        activity = aggregate.compute_activity(sessions)
        self.assertIn("usage_characteristics", activity)
        uc = activity["usage_characteristics"]
        self.assertEqual(len(uc["items"]), 5)
        self.assertEqual(uc["n_sessions"], 20)
        self.assertIn("since", uc)
        self.assertIn("until", uc)
        # Each item has pct, label, tip
        for item in uc["items"]:
            self.assertIn("pct", item)
            self.assertIn("label", item)
            self.assertIn("tip", item)
            self.assertIsInstance(item["pct"], int)

    def test_block_omitted_below_10_sessions(self):
        sessions = [_session(f"s{i}") for i in range(8)]
        activity = aggregate.compute_activity(sessions)
        self.assertNotIn("usage_characteristics", activity)

    def test_block_omitted_when_no_sessions(self):
        activity = aggregate.compute_activity([])
        self.assertNotIn("usage_characteristics", activity)

    def test_since_until_span_session_dates(self):
        sessions = [_session(f"s{i}", start=f"2026-03-{i+1:02d}T10:00:00Z")
                    for i in range(15)]
        activity = aggregate.compute_activity(sessions)
        uc = activity["usage_characteristics"]
        self.assertEqual(uc["since"], "2026-03-01")
        self.assertEqual(uc["until"], "2026-03-15")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m unittest tests.test_usage_characteristics.UsageCharacteristicsTests -v
```
Expected: FAIL — `usage_characteristics` key not present.

- [ ] **Step 3: Implement**

In `scripts/aggregate.py` `compute_activity` function, after the final dict assembly (just before `return`), compute the block:

```python
    # Usage characteristics block (5 fixed items, rule-computed)
    usage_char = None
    if len(sessions) >= 10:
        uc_dates = [s.get("start", "")[:10] for s in sessions if s.get("start")]
        uc_dates = [d for d in uc_dates if len(d) == 10]
        if uc_dates:
            since = min(uc_dates)
            until = max(uc_dates)
            n = len(sessions)

            # Item 1: hit_output_limit rate
            hit = sum(1 for s in sessions if s.get("hit_output_limit", False))
            pct1 = round(100 * hit / n)

            # Item 2: of friction sessions, how many were long (>20min)
            friction = [s for s in sessions if sum(s.get("friction_counts", {}).values()) > 0]
            long_friction = [s for s in friction if s.get("duration_min", 0) > 20]
            pct2 = round(100 * len(long_friction) / len(friction)) if friction else 0

            # Item 3: of good-outcome sessions, how many used Task agent
            good = [s for s in sessions if s.get("outcome", "") in ("fully_achieved", "mostly_achieved")]
            good_ta = [s for s in good if s.get("uses_task_agent", False)]
            pct3 = round(100 * len(good_ta) / len(good)) if good else 0

            # Item 4: sessions using only 1-2 distinct tools
            narrow = [s for s in sessions if 1 <= len(s.get("tool_counts", {})) <= 2]
            pct4 = round(100 * len(narrow) / n)

            # Item 5: sessions after 10pm (hour >= 22)
            late = [s for s in sessions if s.get("hour", 12) >= 22]
            pct5 = round(100 * len(late) / n)

            usage_char = {
                "since": since,
                "until": until,
                "n_sessions": n,
                "items": [
                    {"pct": pct1,
                     "label": "of your sessions hit output-token-limit",
                     "tip": "Sessions that /compact mid-task rarely hit the wall."},
                    {"pct": pct2,
                     "label": "of your high-friction sessions were long (>20min)",
                     "tip": "Long sessions concentrate friction; consider /clear between subtasks."},
                    {"pct": pct3,
                     "label": "of your good-outcome sessions delegated to Task agent",
                     "tip": "Task-agent delegation correlates with ship-level outcomes."},
                    {"pct": pct4,
                     "label": "of your sessions used only 1-2 distinct tools",
                     "tip": "Narrow tool use is fine for focused work but misses MCP leverage."},
                    {"pct": pct5,
                     "label": "of your sessions were after 10pm",
                     "tip": "Evening sessions produce more tokens per friction event."},
                ],
            }
```

Then attach it to the return dict if computed:

```python
    result = {
        "total_sessions": len(sessions),
        # ... existing fields ...
    }
    if usage_char is not None:
        result["usage_characteristics"] = usage_char
    return result
```

(Replace the existing `return { ... }` literal with this two-step assembly.)

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest tests.test_usage_characteristics.UsageCharacteristicsTests -v
```
Expected: PASS on all four methods.

- [ ] **Step 5: Run full test suite**

```bash
python3 -m unittest discover tests -v
```
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/aggregate.py tests/test_usage_characteristics.py
git commit -m "feat(aggregate): emit usage_characteristics with five fixed %-items

Activity now carries a five-item narrative block with since/until/
n_sessions metadata. Guards: omit block when <10 sessions or no session
dates. Next commit wires it into build_html."
```

---

## Task 12: Add locale keys (en + zh_TW placeholders)

**Files:**
- Modify: `scripts/locales.py`
- Test: `tests/test_locales.py` (extend)

- [ ] **Step 1: Write a test that requires the new keys**

Append to `tests/test_locales.py`:

```python
class UsageRubricKeysTests(unittest.TestCase):
    REQUIRED_KEYS = {
        "score_disclaimer",
        "score_disclaimer_long",
        "how_to_read_key_relate",
        "how_to_read_val_relate",
        "usage_char_header",
        "usage_char_note_template",
    }

    def test_all_usage_rubric_keys_present_in_en(self):
        import sys
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(SKILL / "scripts"))
        import locales
        missing = self.REQUIRED_KEYS - set(locales.STRINGS["en"].keys())
        self.assertEqual(missing, set(), f"en missing keys: {missing}")

    def test_all_usage_rubric_keys_present_in_zh_tw(self):
        import sys
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(SKILL / "scripts"))
        import locales
        missing = self.REQUIRED_KEYS - set(locales.STRINGS["zh_TW"].keys())
        self.assertEqual(missing, set(), f"zh_TW missing keys: {missing}")

    @unittest.skip(
        "zh_TW native-tone rewrite scheduled for follow-up PR. Delete this "
        "skip marker and replace placeholder strings once the rewrite lands."
    )
    def test_no_zh_tw_todo_markers_in_release(self):
        import sys
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(SKILL / "scripts"))
        import locales
        offenders = [k for k, v in locales.STRINGS["zh_TW"].items()
                     if v.startswith("[TODO zh_TW]")]
        self.assertEqual(offenders, [],
                         f"zh_TW still carries TODO placeholders: {offenders}")
```

- [ ] **Step 2: Run tests to verify the non-skipped ones fail**

```bash
python3 -m unittest tests.test_locales.UsageRubricKeysTests -v
```
Expected: FAIL on `test_all_usage_rubric_keys_present_in_en` and `test_all_usage_rubric_keys_present_in_zh_tw`; `test_no_zh_tw_todo_markers_in_release` is skipped.

- [ ] **Step 3: Add keys to `scripts/locales.py`**

Inside `STRINGS["en"]`, append:

```python
    "score_disclaimer": "These are independent characteristics, not a breakdown — scores do not sum.",
    "score_disclaimer_long": "Each dimension is scored from the sessions that apply to it. A session can contribute to multiple dimensions, so the eight scores describe independent slices, not shares of a whole.",
    "how_to_read_key_relate": "HOW SCORES RELATE",
    "how_to_read_val_relate": "Each dimension scores a different aspect of sessions. A session can score high on Delegation but low on Time-of-day; they are independent characteristics, not shares of a total.",
    "usage_char_header": "Usage characteristics",
    "usage_char_note_template": "Across {n_sessions} sessions from {since} to {until}, local only.",
```

Inside `STRINGS["zh_TW"]`, append (note: em-dash must be avoided per existing test `test_zh_tw_strings_have_no_em_dash` — placeholder prose uses no em-dash):

```python
    "score_disclaimer": "[TODO zh_TW] These are independent characteristics, not a breakdown; scores do not sum.",
    "score_disclaimer_long": "[TODO zh_TW] Each dimension is scored from the sessions that apply to it.",
    "how_to_read_key_relate": "[TODO zh_TW] HOW SCORES RELATE",
    "how_to_read_val_relate": "[TODO zh_TW] Each dimension scores a different aspect of sessions.",
    "usage_char_header": "[TODO zh_TW] Usage characteristics",
    "usage_char_note_template": "[TODO zh_TW] Across {n_sessions} sessions from {since} to {until}, local only.",
```

**Important:** The zh_TW placeholders use the token `{n_sessions}` / `{since}` / `{until}` in the template string, matching the en version — so the `.format(...)` call in build_html works identically for either locale.

- [ ] **Step 4: Run all locale tests**

```bash
python3 -m unittest tests.test_locales -v
```
Expected:
- `test_locale_keysets_match` PASS
- `test_no_empty_values` PASS (placeholders are non-empty)
- `test_zh_tw_strings_have_no_em_dash` PASS (no em-dash in placeholders — the en `—` is inside the English `score_disclaimer`, which is NOT in zh_TW)
- `test_all_usage_rubric_keys_present_in_*` PASS
- `test_no_zh_tw_todo_markers_in_release` SKIP

- [ ] **Step 5: Commit**

```bash
git add scripts/locales.py tests/test_locales.py
git commit -m "feat(locales): add six usage-rubric keys; zh_TW stubs carry [TODO zh_TW] markers

en is canonical this PR. zh_TW placeholders pass the empty-value and
em-dash gates but are tagged for native-tone rewrite in a follow-up PR.
A skipped test documents the debt."
```

---

## Task 13: CSS additions in `build_html.py`

**Files:**
- Modify: `scripts/build_html.py` — CSS block (around line 607 / 663 / 800)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_html_additions.py`:

```python
class CssRuleTests(unittest.TestCase):
    """Light smoke tests that the new CSS rules are present in the full
    rendered HTML output. We test the rule strings exist and are syntactically
    plausible; full visual correctness is checked by the user in-browser."""

    def _render_minimal(self):
        """Render a minimal HTML using the module's template — enough to
        assert CSS presence without requiring full demo data."""
        import sys
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(SKILL / "scripts"))
        import build_html
        # Read the raw template text to inspect CSS — simpler than full render
        template_path = SKILL / "scripts" / "build_html.py"
        return template_path.read_text()

    def test_pattern_class_css_present(self):
        src = self._render_minimal()
        self.assertIn(".score-row .body .pattern", src)
        self.assertIn("font-style: italic", src)

    def test_score_disclaimer_css_present(self):
        src = self._render_minimal()
        self.assertIn(".score-disclaimer", src)
        self.assertIn("text-align: left", src)

    def test_usage_characteristics_css_present(self):
        src = self._render_minimal()
        self.assertIn(".usage-characteristics", src)
        self.assertIn(".uc-row", src)
        self.assertIn("grid-template-columns: 72px 1fr", src)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m unittest tests.test_build_html_additions.CssRuleTests -v
```
Expected: FAIL — new CSS rules absent.

- [ ] **Step 3: Add CSS after the existing `.score-row.na` rule**

In `scripts/build_html.py`, find line 663 (the `.score-row.na .score` rule). After it, insert:

```css
  .score-row .body .pattern {
    font-family: var(--sans);
    font-size: 13.5px;
    line-height: 1.5;
    color: var(--ink-muted);
    font-style: italic;
    margin: 6px 0 0 0;
  }

  .score-disclaimer {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.08em;
    color: var(--ink-muted);
    text-transform: uppercase;
    margin: 0 0 14px 0;
    text-align: left;
  }

  .usage-characteristics {
    margin: 28px 0 0 0;
    padding: 20px 0 0 0;
    border-top: 1px solid var(--rule);
  }
  .uc-header {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.12em;
    color: var(--ink-muted);
    text-transform: uppercase;
    margin: 0 0 4px 0;
  }
  .uc-note {
    font-family: var(--sans);
    font-size: 12.5px;
    color: var(--ink-muted);
    margin: 0 0 14px 0;
  }
  .uc-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .uc-row {
    display: grid;
    grid-template-columns: 72px 1fr;
    gap: 16px;
    padding: 8px 0;
    border-bottom: 1px dotted var(--rule);
    align-items: baseline;
  }
  .uc-row:last-child { border-bottom: none; }
  .uc-row .pct {
    font-family: var(--serif);
    font-variation-settings: "opsz" 24, "wght" 400;
    font-size: 24px;
    line-height: 1;
    color: var(--ink);
    text-align: right;
    letter-spacing: -0.01em;
  }
  .uc-body .label {
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.45;
    color: var(--ink);
    margin: 0 0 2px 0;
  }
  .uc-body .tip {
    font-family: var(--sans);
    font-size: 13px;
    line-height: 1.5;
    color: var(--ink-muted);
    font-style: italic;
    margin: 0;
  }
```

**Placement note:** `build_html.py` uses `string.Template` — the CSS lives as a literal inside a Python triple-quoted string. Braces don't need escaping in string.Template (they only care about `$`); but double-check the surrounding lines' indent and keep braces unescaped.

- [ ] **Step 4: Run tests**

```bash
python3 -m unittest tests.test_build_html_additions.CssRuleTests -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_html.py tests/test_build_html_additions.py
git commit -m "feat(build_html): add CSS for .pattern, .score-disclaimer, .usage-characteristics

Typography + layout rules matching spec Section 2 decisions: italic
pattern, left-aligned mono disclaimer, 72px percent column with
right-aligned digits for vertical alignment across 2-/3-digit values."
```

---

## Task 14: Render pattern inside each score row

**Files:**
- Modify: `scripts/build_html.py:1861-1877` (the score_rows loop)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_html_additions.py`:

```python
class PatternRenderTests(unittest.TestCase):
    def test_pattern_block_rendered_when_non_none(self):
        import sys, tempfile, json
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(SKILL / "scripts"))
        import build_html
        # Call the score-row builder directly. If no helper fn exists, invoke
        # the module's full render is overkill — instead assert on the
        # string-concatenation logic by rendering a synthetic scores dict via
        # the main() path using in-memory JSON, OR extract a minimum test:
        # check that the template contains the <p class="pattern"> fragment
        # generator when pattern is non-None.
        src = (SKILL / "scripts" / "build_html.py").read_text()
        # Look for the conditional render snippet
        self.assertIn('class="pattern"', src,
                      "score_rows render should include <p class=\"pattern\"> when pattern is non-None")

    def test_pattern_block_absent_when_pattern_is_none(self):
        # The conditional check itself must exist in source — verifies intent,
        # not runtime behaviour (that's covered at integration by the smoke test)
        import sys
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        src = (SKILL / "scripts" / "build_html.py").read_text()
        # Must guard with truthy check on the pattern value
        self.assertTrue(
            "s.get('pattern')" in src or 's.get("pattern")' in src,
            "score_rows render must read pattern from scores dict with .get()"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m unittest tests.test_build_html_additions.PatternRenderTests -v
```
Expected: FAIL.

- [ ] **Step 3: Modify the score_rows loop**

In `scripts/build_html.py` around line 1861-1877, modify the loop. Replace:

```python
    score_rows = ""
    for key, title in dim_titles.items():
        s = scores.get(key, {})
        sc = s.get("score")
        band = score_band(sc)
        display = f'<span class="num">{sc}</span><span class="out">/ 10</span>' if sc is not None else 'n/a'
        dim_label = f"{key.split('_', 1)[0]} · {key.split('_', 1)[1].replace('_', ' ')}"
        reason = s.get("explanation") or s.get("reason", "")
        score_rows += f'''<div class="score-row {band}">
  <div class="dim">{esc(dim_label)}</div>
  <div class="body">
    <div class="h">{esc(title)}</div>
    <p class="exp">{esc(reason)}</p>
  </div>
  <div class="score">{display}</div>
</div>
'''
```

With:

```python
    score_rows = ""
    for key, title in dim_titles.items():
        s = scores.get(key, {})
        sc = s.get("score")
        band = score_band(sc)
        display = f'<span class="num">{sc}</span><span class="out">/ 10</span>' if sc is not None else 'n/a'
        dim_label = f"{key.split('_', 1)[0]} · {key.split('_', 1)[1].replace('_', ' ')}"
        reason = s.get("explanation") or s.get("reason", "")
        pattern_html = ""
        pattern_val = s.get("pattern")
        if pattern_val:
            pattern_html = f'\n    <p class="pattern">{esc(pattern_val)}</p>'
        score_rows += f'''<div class="score-row {band}">
  <div class="dim">{esc(dim_label)}</div>
  <div class="body">
    <div class="h">{esc(title)}</div>
    <p class="exp">{esc(reason)}</p>{pattern_html}
  </div>
  <div class="score">{display}</div>
</div>
'''
```

- [ ] **Step 4: Run tests**

```bash
python3 -m unittest tests.test_build_html_additions.PatternRenderTests -v
```
Expected: PASS.

- [ ] **Step 5: XSS test**

Add one more test method to `PatternRenderTests`:

```python
    def test_pattern_xss_escaped_in_full_render(self):
        """Render a full report with a malicious pattern string and verify
        it's escaped, not executed."""
        import sys, subprocess, tempfile, json, shutil, os
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        # Use existing demo data as a base, inject a script tag into one score's pattern
        demo = Path("/tmp/cc-autopsy-demo")
        if not demo.exists():
            self.skipTest("demo data not generated yet; run generate_demo_data.py first")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            # copy aggregate.json, inject malicious pattern
            agg_src = demo / "aggregate.json"
            if not agg_src.exists():
                self.skipTest("demo aggregate.json missing")
            data = json.loads(agg_src.read_text())
            for dim_key in data.get("scores", {}):
                if dim_key.startswith("D"):
                    data["scores"][dim_key]["pattern"] = "<script>alert(1)</script>"
                    break
            (td / "aggregate.json").write_text(json.dumps(data))
            # Copy the rest of the expected inputs
            for fname in ("samples.json", "peer-review.md"):
                src_f = demo / fname
                if src_f.exists():
                    shutil.copy(src_f, td / fname)
            out = td / "report.html"
            result = subprocess.run(
                ["python3", str(SKILL / "scripts" / "build_html.py"),
                 "--input", str(td / "aggregate.json"),
                 "--samples", str(td / "samples.json"),
                 "--output", str(out),
                 "--mode", "self"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                self.skipTest(f"build_html failed on demo data: {result.stderr[:500]}")
            html = out.read_text()
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("&lt;script&gt;", html)
```

Run:

```bash
python3 -m unittest tests.test_build_html_additions.PatternRenderTests -v
```
Expected: PASS (or gracefully SKIP if demo data absent — the real regression gate is `assertNotIn` on the raw script tag).

- [ ] **Step 6: Commit**

```bash
git add scripts/build_html.py tests/test_build_html_additions.py
git commit -m "feat(build_html): render <p class=\"pattern\"> inside each score row

Conditional on scores[dim].get('pattern') being truthy. XSS-escaped via
esc(). Absent when pattern is None."
```

---

## Task 15: Render `.score-disclaimer` above score table

**Files:**
- Modify: `scripts/build_html.py:1147-1152` (template around `<div class="score-table">`)
- Modify: `scripts/build_html.py:2321` area (template variable binding)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_html_additions.py`:

```python
class ScoreDisclaimerTests(unittest.TestCase):
    def test_disclaimer_placeholder_in_template(self):
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        src = (SKILL / "scripts" / "build_html.py").read_text()
        self.assertIn("$score_disclaimer", src)
        self.assertIn('class="score-disclaimer"', src)

    def test_disclaimer_rendered_above_score_table(self):
        """In the template string, score-disclaimer appears before score-table."""
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        src = (SKILL / "scripts" / "build_html.py").read_text()
        disclaimer_pos = src.find('class="score-disclaimer"')
        table_pos = src.find('class="score-table"')
        self.assertGreater(disclaimer_pos, 0)
        self.assertGreater(table_pos, disclaimer_pos)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m unittest tests.test_build_html_additions.ScoreDisclaimerTests -v
```
Expected: FAIL.

- [ ] **Step 3: Modify the HTML template**

In `scripts/build_html.py` around line 1147-1152, change:

```html
  <div class="overall-strip">$section_scoring_overall_label &nbsp;·&nbsp; $overall_line</div>

  <div class="score-table">
    $score_rows
  </div>
```

to:

```html
  <div class="overall-strip">$section_scoring_overall_label &nbsp;·&nbsp; $overall_line</div>

  <p class="score-disclaimer">$score_disclaimer</p>
  <div class="score-table">
    $score_rows
  </div>
```

- [ ] **Step 4: Bind the template variable**

In `scripts/build_html.py` around line 2321 (the dict passed to `Template.substitute(...)` — search for `"score_rows": score_rows,`). Add:

```python
        "score_disclaimer": t(args.locale, "score_disclaimer"),
```

alongside the other `t(args.locale, ...)` bindings.

- [ ] **Step 5: Run tests**

```bash
python3 -m unittest tests.test_build_html_additions.ScoreDisclaimerTests -v
```
Expected: PASS.

- [ ] **Step 6: Full smoke test**

```bash
python3 -m unittest tests -v
```
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add scripts/build_html.py tests/test_build_html_additions.py
git commit -m "feat(build_html): render score-disclaimer above score table

Mono/uppercase/muted/left-aligned line localized via locales.py."
```

---

## Task 16: Append `HOW SCORES RELATE` to HR mode how-to-read

**Files:**
- Modify: `scripts/build_html.py:2161-2188` (`how_to_read_section` HR mode block)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_html_additions.py`:

```python
class HowScoresRelateTests(unittest.TestCase):
    def test_how_to_read_hr_mode_includes_relate_entry(self):
        """HR mode how-to-read should end with HOW SCORES RELATE dt/dd."""
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        src = (SKILL / "scripts" / "build_html.py").read_text()
        # New keys referenced in the HR how-to-read block
        self.assertIn("how_to_read_key_relate", src)
        self.assertIn("how_to_read_val_relate", src)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m unittest tests.test_build_html_additions.HowScoresRelateTests -v
```
Expected: FAIL.

- [ ] **Step 3: Modify the HR mode how-to-read block**

Locate the block starting at line 2161:

```python
        how_to_read_section = '''<details class="how-to-read" open>
<summary>How to read this report (30-second primer)</summary>
<div class="how-body">
...
<dl>
<dt>Session</dt>
<dd>One continuous Claude Code conversation...</dd>
...existing entries...
</dl>
</div>
</details>'''
```

Change to f-string so we can interpolate localized strings, and add the new dt/dd pair at the end of the `<dl>`:

```python
        how_to_read_section = f'''<details class="how-to-read" open>
<summary>How to read this report (30-second primer)</summary>
<div class="how-body">
<p>This report is generated by <code>cc-user-autopsy</code>, a skill that reads a user's local Claude Code usage data. It combines deterministic rule-based scoring with an LLM-written peer review.</p>
<dl>
<dt>Session</dt>
<dd>One continuous Claude Code conversation, bounded by either a fresh start or a <code>/clear</code>. A typical heavy user has hundreds per quarter.</dd>
<dt>Task agent / Subagent</dt>
<dd>Claude Code lets you spawn isolated child agents to run a subtask in parallel. Heavy adoption signals fluency with agentic workflows.</dd>
<dt>MCP (Model Context Protocol)</dt>
<dd>A standard for connecting Claude to external tools (Playwright, Supabase, GitHub, etc). MCP adoption rate correlates with tool breadth.</dd>
<dt>Facet</dt>
<dd>LLM-classified outcome / friction labels per session, produced by the built-in <code>/insights</code> command. Coverage &lt; 100% is normal.</dd>
<dt>Interrupt recovery rate</dt>
<dd>[existing text — preserve verbatim from current file]</dd>
<dt>{t(args.locale, "how_to_read_key_relate")}</dt>
<dd>{t(args.locale, "how_to_read_val_relate")}</dd>
</dl>
</div>
</details>'''
```

**IMPORTANT:** When converting the block to an f-string, all existing `{` / `}` inside HTML (there are none currently in this block — confirm by inspection) would need doubling. Read the current block to verify. If it contains no literal braces, the f-string conversion is safe.

Alternative: use a simpler string-concatenation approach that leaves the existing block as-is and only appends the new `<dt>/<dd>` pair before `</dl>`:

```python
        # Build the HR how-to-read block (existing text preserved verbatim)
        how_to_read_relate_dt = t(args.locale, "how_to_read_key_relate")
        how_to_read_relate_dd = t(args.locale, "how_to_read_val_relate")
        how_to_read_section = f'''<details class="how-to-read" open>
<summary>How to read this report (30-second primer)</summary>
<div class="how-body">
<p>This report is generated by <code>cc-user-autopsy</code>, a skill that reads a user's local Claude Code usage data. It combines deterministic rule-based scoring with an LLM-written peer review.</p>
<dl>
<dt>Session</dt>
<dd>One continuous Claude Code conversation, bounded by either a fresh start or a <code>/clear</code>. A typical heavy user has hundreds per quarter.</dd>
<!-- ...remaining existing entries preserved verbatim from line ~2168-2186... -->
<dt>{how_to_read_relate_dt}</dt>
<dd>{how_to_read_relate_dd}</dd>
</dl>
</div>
</details>'''
```

**Implementation instruction to the subagent:** Read the current `how_to_read_section` block fully (lines 2161 through its closing `'''`); copy every existing `<dt>/<dd>` pair verbatim into the new f-string; append the two new `<dt>/<dd>` pair before `</dl>`. Do not invent or omit any existing entry.

- [ ] **Step 4: Run tests**

```bash
python3 -m unittest tests.test_build_html_additions.HowScoresRelateTests -v
```
Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
python3 -m unittest discover tests -v
```
Expected: All pass. If any HR-mode rendering test breaks, inspect — most likely cause is an accidentally-dropped `<dt>/<dd>` pair.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_html.py tests/test_build_html_additions.py
git commit -m "feat(build_html): append HOW SCORES RELATE dt/dd to HR mode how-to-read

Visible only in HR mode (self mode hides how-to-read). The shorter
score-disclaimer above the table remains the primary signal for self
readers."
```

---

## Task 17: Render `usage-characteristics` block in activity panel

**Files:**
- Modify: `scripts/build_html.py:66-...` (`_build_activity_panel`)
- Test: `tests/test_build_html_additions.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build_html_additions.py`:

```python
class UsageCharacteristicsRenderTests(unittest.TestCase):
    def _activity_with_uc(self, **overrides):
        base = _activity_panel()
        base["usage_characteristics"] = {
            "since": "2026-03-20",
            "until": "2026-04-19",
            "n_sessions": 280,
            "items": [
                {"pct": 42, "label": "of your sessions hit output-token-limit",
                 "tip": "Sessions that /compact mid-task rarely hit the wall."},
                {"pct": 71, "label": "of your high-friction sessions were long (>20min)",
                 "tip": "Long sessions concentrate friction; consider /clear between subtasks."},
                {"pct": 34, "label": "of your good-outcome sessions delegated to Task agent",
                 "tip": "Task-agent delegation correlates with ship-level outcomes."},
                {"pct": 58, "label": "of your sessions used only 1-2 distinct tools",
                 "tip": "Narrow tool use is fine for focused work but misses MCP leverage."},
                {"pct": 22, "label": "of your sessions were after 10pm",
                 "tip": "Evening sessions produce more tokens per friction event."},
            ],
        }
        base.update(overrides)
        return base

    def test_usage_characteristics_block_rendered(self):
        import sys
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(SKILL / "scripts"))
        import build_html
        html = build_html._build_activity_panel(self._activity_with_uc())
        self.assertIn('class="usage-characteristics"', html)
        self.assertIn("42%", html)
        self.assertEqual(html.count('class="uc-row"'), 5)
        self.assertIn("output-token-limit", html)
        self.assertIn("Across 280 sessions", html)

    def test_usage_characteristics_absent_when_missing(self):
        import sys
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(SKILL / "scripts"))
        import build_html
        html = build_html._build_activity_panel(_activity_panel())
        self.assertNotIn('class="usage-characteristics"', html)

    def test_usage_characteristics_xss_escaped(self):
        import sys
        from pathlib import Path
        SKILL = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(SKILL / "scripts"))
        import build_html
        activity = self._activity_with_uc()
        activity["usage_characteristics"]["items"][0]["label"] = "<script>alert(1)</script>"
        activity["usage_characteristics"]["items"][0]["tip"] = '"><script>alert(2)</script>'
        html = build_html._build_activity_panel(activity)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn('<script>alert(2)</script>', html)
        self.assertIn("&lt;script&gt;", html)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m unittest tests.test_build_html_additions.UsageCharacteristicsRenderTests -v
```
Expected: FAIL.

- [ ] **Step 3: Add render logic to `_build_activity_panel`**

Open `scripts/build_html.py` and find `_build_activity_panel` (line 66). Near the end of the function, **before the final `return` that stitches the panel HTML**, add a block that renders `usage_characteristics` when present.

Approximate structure (find the location just before the function returns, after all existing tiles/content are assembled):

```python
    # Usage characteristics block (appended after existing panel content)
    uc = activity.get("usage_characteristics")
    uc_html = ""
    if uc and uc.get("items"):
        header = t(locale, "usage_char_header")
        note = t(locale, "usage_char_note_template").format(
            n_sessions=uc.get("n_sessions", 0),
            since=uc.get("since", ""),
            until=uc.get("until", ""),
        )
        rows = ""
        for item in uc["items"]:
            rows += (
                '<div class="uc-row">'
                f'<span class="pct">{int(item.get("pct", 0))}%</span>'
                '<div class="uc-body">'
                f'<p class="label">{esc(item.get("label", ""))}</p>'
                f'<p class="tip">{esc(item.get("tip", ""))}</p>'
                '</div>'
                '</div>'
            )
        uc_html = (
            '<div class="usage-characteristics">'
            f'<h4 class="uc-header">{esc(header)}</h4>'
            f'<p class="uc-note">{esc(note)}</p>'
            f'<div class="uc-list">{rows}</div>'
            '</div>'
        )
```

Then append `uc_html` to the existing panel HTML string being returned. The exact variable name carrying the panel HTML depends on `_build_activity_panel`'s internals — read the function and append `uc_html` to whatever string variable is `return`ed at the end (just before `</section>` if present, or as the last child of the panel wrapper).

**Subagent instruction:** Read the full body of `_build_activity_panel` (start line 66) before editing, identify the variable being returned, and append `uc_html` to it.

- [ ] **Step 4: Run tests**

```bash
python3 -m unittest tests.test_build_html_additions.UsageCharacteristicsRenderTests -v
```
Expected: PASS on all three methods.

- [ ] **Step 5: Run full suite**

```bash
python3 -m unittest discover tests -v
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_html.py tests/test_build_html_additions.py
git commit -m "feat(build_html): render usage-characteristics block in activity panel

Five rows: percent (serif 24px right-aligned in 72px column) + label
(sans) + tip (sans italic muted). XSS-escaped. Omitted when
activity dict lacks the block."
```

---

## Task 18: End-to-end smoke test with demo data

**Files:**
- (No file modified — this is a manual verification gate)

- [ ] **Step 1: Regenerate demo data with new scanner fields**

```bash
cd ~/Projects/cc-user-autopsy
python3 scripts/generate_demo_data.py --out /tmp/cc-autopsy-demo
```

If the demo generator doesn't know about `hit_output_limit` and emits sessions without the field, that's fine — `.get("hit_output_limit", False)` handles the default. If no demo session has the field True, the `usage_characteristics` item 1 will render 0% — still valid output.

- [ ] **Step 2: Run full build**

```bash
python3 scripts/build_html.py \
  --input /tmp/cc-autopsy-demo/aggregate.json \
  --samples /tmp/cc-autopsy-demo/samples.json \
  --output /tmp/cc-autopsy-demo/report.html \
  --mode self
```

Expected: Exit 0.

- [ ] **Step 3: Visual inspection**

Open `/tmp/cc-autopsy-demo/report.html` in browser. Verify:
- `.score-disclaimer` line visible above the score table (left-aligned mono uppercase).
- At least one `.score-row` shows an italic muted pattern sentence under the explanation.
- Activity panel bottom contains `Usage characteristics` header, a note with the date range, and 5 rows with percent + label + tip.
- No browser-console errors.
- Percent values are vertically aligned across rows (same right-edge for `%` in `42%` and `100%` — test with a row that hits each threshold).

Also render HR mode and verify HOW SCORES RELATE entry appears inside `how-to-read` when expanded:

```bash
python3 scripts/build_html.py \
  --input /tmp/cc-autopsy-demo/aggregate.json \
  --samples /tmp/cc-autopsy-demo/samples.json \
  --output /tmp/cc-autopsy-demo/report-hr.html \
  --mode hr
```

- [ ] **Step 4: Run full test suite one more time**

```bash
python3 -m unittest discover tests -v
```
Expected: All tests pass; `test_no_zh_tw_todo_markers_in_release` skipped.

- [ ] **Step 5: If visual issues found**

Each issue → new failing test → minimal fix → commit. Do NOT bundle visual fixes with feature commits.

- [ ] **Step 6: Commit verification artifact if useful**

If the subagent wants to record that verification happened (not required, but optional):

```bash
# No commit needed — tests are the contract. Only commit if new tests were added.
```

---

## Task 19: PR preparation

**Files:**
- (no code changes)

- [ ] **Step 1: Confirm branch state**

```bash
cd ~/Projects/cc-user-autopsy
git log --oneline main..HEAD
git status
```

Expected: Clean worktree; ~17-18 commits on `feat/usage-inspired-rubric`.

- [ ] **Step 2: Push branch**

```bash
git push -u origin feat/usage-inspired-rubric
```

- [ ] **Step 3: Create PR**

```bash
gh pr create --title "feat: usage-inspired rubric (per-dim patterns, usage characteristics, score disclaimers)" --body "$(cat <<'EOF'
## Summary

Borrow three UX mechanics from Anthropic's official `/usage` dashboard (2026-04-19 release), adapted for `cc-user-autopsy`'s skill-use diagnostic lane:

- **Per-dimension patterns**: each scored dimension now carries a descriptive contrast sentence (e.g. "Sessions that used Task agent had a 34% good-outcome rate, versus 51% overall"). Rule-computed; None when sample too small.
- **Usage characteristics block**: Activity panel grows a 5-item %-based narrative section with since/until/n_sessions footer.
- **Score disclaimers**: mono-uppercase line above the score table + HOW SCORES RELATE entry inside the how-to-read expandable, clarifying that dimensions are independent, not a breakdown.

No runtime LLM calls. Scanner gains `hit_output_limit` detection (stop_reason == "max_tokens") to power one of the five usage-characteristics items.

**en is canonical this PR.** zh_TW gets non-empty `[TODO zh_TW]` placeholders keeping the locale-parity gate green; follow-up PR fills native-tone zh_TW.

## Test plan

- [ ] All existing tests pass (smoke, locales, scan_transcripts, build_html additions, cost estimate, demo data).
- [ ] New `tests/test_usage_characteristics.py` passes (~20 new unit tests).
- [ ] Extended `tests/test_build_html_additions.py` passes (CSS, pattern render, disclaimer, UC render, XSS).
- [ ] `test_no_zh_tw_todo_markers_in_release` skipped with dated TODO pointing at follow-up PR.
- [ ] Manual browser render of `/tmp/cc-autopsy-demo/report.html` (self + HR) — visual verification of pattern italics, disclaimer left-align, UC 72px column percent alignment.

## Spec

`docs/superpowers/specs/2026-04-19-usage-inspired-rubric-design.md` (Q1-Q7 brainstorm + D-A/B/C design micro-decisions).

## Follow-ups

- PR to fill zh_TW translations and delete `test_no_zh_tw_todo_markers_in_release` skip marker.
- (Optional, not blocking) Dynamic tip variants by pct threshold — structure already supports.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Report PR URL to user**

Return the PR URL in the final message. Do not merge unprompted.

---

## Self-review checklist (run after writing this plan)

- [ ] Every spec section has a task that implements it.
  - Section 1a (pattern in each score_dX) → Tasks 3-10 ✓
  - Section 1a-bis (scanner hit_output_limit) → Tasks 1-2 ✓
  - Section 1b (usage_characteristics in activity) → Task 11 ✓
  - Section 1c (locale keys) → Task 12 ✓
  - Section 2a (.pattern CSS + render) → Tasks 13, 14 ✓
  - Section 2b (.score-disclaimer CSS + render) → Tasks 13, 15 ✓
  - Section 2c (HOW SCORES RELATE in how-to-read) → Task 16 ✓
  - Section 2d (usage-characteristics CSS + render) → Tasks 13, 17 ✓
  - Section 3 (locale parity handling) → Task 12 ✓
  - Section 4 (tests) → distributed across all tasks; XSS in Tasks 14, 17 ✓
  - Acceptance criteria → Task 18 ✓
- [ ] No "TBD", "implement later", "fill in details" markers. ✓
- [ ] Code shown for every code step (no "add appropriate logic"). ✓
- [ ] Type consistency: field names (`hit_output_limit`, `pattern`, `usage_characteristics`, `items`, `pct`/`label`/`tip`, `since`/`until`/`n_sessions`) identical across aggregate, render, tests. ✓
- [ ] Commit messages follow conventional-commit style matching existing repo history. ✓

## Execution risks & mitigations

| Risk | Mitigation |
|---|---|
| `scripts/scan_transcripts.py` internal structure differs from what Task 1 assumes | Task 1 Step 3 tells the subagent to read the area and match existing field naming. |
| `score_dX_*` functions may have multiple early-return paths — easy to miss adding `"pattern": None` | Each task's Step 3 mentions "add to every returned dict (including any early-return paths)". Tests catch miss via `assertIn("pattern", result)`. |
| `_build_activity_panel` return structure differs from test assumption | Task 17 Step 3 explicitly instructs subagent to read the function's return shape before editing. |
| HR mode how-to-read block uses literal braces that an f-string conversion would break | Task 16 Step 3 warns and suggests concatenation fallback if braces exist. |
| Demo data doesn't trigger any `hit_output_limit=True` | Acceptable — item 1 renders 0%. Still a valid narrative. |
| Self mode readers don't see HOW SCORES RELATE (only HR mode has how-to-read) | Acknowledged intentional per spec Section 2c. The `.score-disclaimer` above the table covers self-mode readers. |
