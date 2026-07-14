"""TDD for scripts/scan_transcripts.py.

Ground truth: a locally-present session-meta file paired with its transcript.
We scan the transcript and assert our derived numbers match the meta's numbers
within tolerance. The fixture session id + projects-dir name are
environment-specific, so set them via env vars when running locally:

    CCUA_FIXTURE_SID=<uuid> CCUA_FIXTURE_PROJECTS_DIR=-Users-<you> \\
        python3 -m unittest tests.test_scan_transcripts

Tests that need the fixture skip when the referenced file is absent.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCANNER = SKILL_DIR / "scripts" / "scan_transcripts.py"

# Fixture config — env-overridable so the repo carries no owner-specific data.
# Placeholders cause the fixture-dependent tests to skip cleanly when unset.
FIXTURE_SID = os.environ.get("CCUA_FIXTURE_SID", "00000000-0000-0000-0000-000000000000")
FIXTURE_PROJECTS_DIR = os.environ.get("CCUA_FIXTURE_PROJECTS_DIR", "-Users-demo")
FIXTURE_META = Path.home() / ".claude/usage-data/session-meta" / f"{FIXTURE_SID}.json"
FIXTURE_TRANSCRIPT = Path.home() / ".claude/projects" / FIXTURE_PROJECTS_DIR / f"{FIXTURE_SID}.jsonl"

sys.path.insert(0, str(SKILL_DIR / "scripts"))
import aggregate  # noqa: E402


def _run_scanner(projects_dir: Path, out: Path):
    return subprocess.run(
        [sys.executable, str(SCANNER),
         "--projects-dir", str(projects_dir),
         "--output", str(out)],
        capture_output=True, text=True,
    )


def _setup_fixture(root: Path):
    """Copy fixture transcript into a mock projects dir, return row for that sid."""
    if not FIXTURE_TRANSCRIPT.exists():
        raise unittest.SkipTest(f"Fixture transcript missing: {FIXTURE_TRANSCRIPT}")
    pdir = root / "projects" / FIXTURE_PROJECTS_DIR
    pdir.mkdir(parents=True)
    (pdir / f"{FIXTURE_SID}.jsonl").write_bytes(FIXTURE_TRANSCRIPT.read_bytes())
    return pdir


def _run_single_row_session(rows, sid):
    """Write a synthetic jsonl with `rows` at `sid`, invoke scanner, return the first emitted row.
    Raises AssertionError if the scanner didn't emit exactly one row."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        pdir = td / "projects" / "-proj"
        pdir.mkdir(parents=True)
        (pdir / f"{sid}.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
        out = td / "out.jsonl"
        _run_scanner(td / "projects", out)
        emitted = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
        assert len(emitted) == 1, f"expected 1 row, got {len(emitted)}: {emitted}"
        return emitted[0]


class ScanTranscriptsTests(unittest.TestCase):
    def test_reproduces_meta_counts(self):
        """Scanner output for fixture must be close to ground-truth session-meta.

        Some fields won't match exactly because session-meta applies internal
        filtering we can't fully reproduce (e.g. user_message_count drops slash
        commands, hook-injected text, and some skill-launch messages). We assert
        exact match on the fields we CAN reproduce deterministically, and a
        sensible lower-bound on filtered counts.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_fixture(tmp)
            out = tmp / "out.jsonl"
            r = _run_scanner(tmp / "projects", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
            self.assertEqual(len(rows), 1)
            row = rows[0]

            meta = json.loads(FIXTURE_META.read_text())
            self.assertEqual(row["session_id"], FIXTURE_SID)
            # Transcript sees the full session including slash-commands and
            # continuation-after-interrupt that session-meta appears to cut
            # off. So our numbers are >= meta's numbers, not ==.
            for tool, n in meta["tool_counts"].items():
                self.assertGreaterEqual(row["tool_counts"].get(tool, 0), n,
                    f"tool {tool}: transcript {row['tool_counts'].get(tool,0)} < meta {n}")
            self.assertGreaterEqual(row["input_tokens"], meta["input_tokens"])
            self.assertGreaterEqual(row["output_tokens"], meta["output_tokens"])
            self.assertGreaterEqual(row["user_message_count"], meta["user_message_count"])
            self.assertGreaterEqual(row["assistant_message_count"], meta["assistant_message_count"])

    def test_first_prompt_extracted(self):
        """first_prompt must match the ground-truth meta's first_prompt."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_fixture(tmp)
            out = tmp / "out.jsonl"
            _run_scanner(tmp / "projects", out)
            row = json.loads(out.read_text().splitlines()[0])
            meta = json.loads(FIXTURE_META.read_text())
            self.assertEqual(row["first_prompt"], meta["first_prompt"])

    def test_cache_tokens_summed(self):
        """Cache tokens must be present (new field vs session-meta)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_fixture(tmp)
            out = tmp / "out.jsonl"
            _run_scanner(tmp / "projects", out)
            row = json.loads(out.read_text().splitlines()[0])
            # Cache tokens should be >= 0 (likely > 0 for any real session)
            self.assertIn("cache_creation_input_tokens", row)
            self.assertIn("cache_read_input_tokens", row)
            self.assertGreaterEqual(row["cache_creation_input_tokens"], 0)
            self.assertGreaterEqual(row["cache_read_input_tokens"], 0)

    def test_model_counts_extracted(self):
        """model_counts must be a non-empty dict (assistant messages have model)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_fixture(tmp)
            out = tmp / "out.jsonl"
            _run_scanner(tmp / "projects", out)
            row = json.loads(out.read_text().splitlines()[0])
            self.assertIn("model_counts", row)
            self.assertIsInstance(row["model_counts"], dict)
            self.assertGreater(sum(row["model_counts"].values()), 0)

    def test_start_and_duration(self):
        """start_time matches meta; duration >= meta (scanner sees the whole
        transcript including trailing tool_results; meta likely uses last user
        text)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_fixture(tmp)
            out = tmp / "out.jsonl"
            _run_scanner(tmp / "projects", out)
            row = json.loads(out.read_text().splitlines()[0])
            meta = json.loads(FIXTURE_META.read_text())
            self.assertEqual(row["start_time"], meta["start_time"])
            self.assertGreaterEqual(row["duration_minutes"], meta["duration_minutes"])

    def test_subagent_not_emitted_as_separate_session(self):
        """agent-*.jsonl files are subagent internal runs and must not produce
        their own session row — they belong to the parent session identified
        by the `sessionId` field inside each record."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pdir = tmp / "projects" / "subagents"
            pdir.mkdir(parents=True)
            # Real UUID — keep
            real = "11111111-2222-3333-4444-555555555555"
            (pdir / f"{real}.jsonl").write_text(
                json.dumps({"type": "user", "timestamp": "2026-04-18T00:00:00.000Z",
                            "message": {"role": "user", "content": "hello"}}) + "\n" +
                json.dumps({"type": "assistant", "timestamp": "2026-04-18T00:00:01.000Z",
                            "message": {"role": "assistant", "model": "claude-opus-4-6",
                                        "content": [], "usage": {"input_tokens": 1, "output_tokens": 1}}}) + "\n"
            )
            # Subagent-style filename — must not emit a separate row
            (pdir / "agent-abc123def456789.jsonl").write_text(
                json.dumps({"type": "user", "timestamp": "2026-04-18T00:00:00.000Z",
                            "sessionId": real,
                            "message": {"role": "user", "content": "subagent"}}) + "\n"
            )
            out = tmp / "out.jsonl"
            r = _run_scanner(tmp / "projects", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = out.read_text().splitlines()
            self.assertEqual(len(lines), 1, "only one session row (the parent) should be emitted")
            self.assertEqual(json.loads(lines[0])["session_id"], real)

    def test_subagent_tokens_aggregated_to_parent(self):
        """Subagent runs (agent-*.jsonl) carry a sessionId pointing to their
        parent. Their cache_creation_input_tokens, cache_read_input_tokens,
        input_tokens, output_tokens, and model_counts must be added to the
        parent session's row — not dropped."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pdir = tmp / "projects" / "p"
            pdir.mkdir(parents=True)
            parent_sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
            # Parent transcript: one opus-4-6 assistant turn with modest usage
            (pdir / f"{parent_sid}.jsonl").write_text(
                json.dumps({"type": "user", "timestamp": "2026-04-18T00:00:00.000Z",
                            "message": {"role": "user", "content": "hello"}}) + "\n" +
                json.dumps({"type": "assistant", "timestamp": "2026-04-18T00:00:01.000Z",
                            "message": {"role": "assistant", "model": "claude-opus-4-6",
                                        "content": [],
                                        "usage": {"input_tokens": 10, "output_tokens": 20,
                                                  "cache_creation_input_tokens": 100,
                                                  "cache_read_input_tokens": 1000}}}) + "\n"
            )
            # Subagent run: claude-haiku-4-5 with its own usage. Must be merged
            # into the parent sid (because agent-*.jsonl records carry
            # sessionId = parent sid).
            (pdir / "agent-subagent1.jsonl").write_text(
                json.dumps({"type": "user", "timestamp": "2026-04-18T00:00:02.000Z",
                            "sessionId": parent_sid,
                            "message": {"role": "user", "content": "go"}}) + "\n" +
                json.dumps({"type": "assistant", "timestamp": "2026-04-18T00:00:03.000Z",
                            "sessionId": parent_sid,
                            "message": {"role": "assistant", "model": "claude-haiku-4-5",
                                        "content": [],
                                        "usage": {"input_tokens": 5, "output_tokens": 7,
                                                  "cache_creation_input_tokens": 50,
                                                  "cache_read_input_tokens": 500}}}) + "\n"
            )
            out = tmp / "out.jsonl"
            r = _run_scanner(tmp / "projects", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["session_id"], parent_sid)
            # Token fields must be SUM of parent + subagent usage
            self.assertEqual(row["input_tokens"], 10 + 5)
            self.assertEqual(row["output_tokens"], 20 + 7)
            self.assertEqual(row["cache_creation_input_tokens"], 100 + 50)
            self.assertEqual(row["cache_read_input_tokens"], 1000 + 500)
            # model_counts must include BOTH the parent's model and the
            # subagent's model
            self.assertEqual(row["model_counts"].get("claude-opus-4-6"), 1)
            self.assertEqual(row["model_counts"].get("claude-haiku-4-5"), 1)

    def test_orphan_subagent_tokens_aggregated_into_pool(self):
        """If a subagent's sessionId points to a parent whose transcript file
        is not on disk (e.g. auto-cleaned), its tokens must still be emitted
        as a synthetic 'orphan' row so they contribute to the activity pool
        instead of being silently lost."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pdir = tmp / "projects" / "p"
            pdir.mkdir(parents=True)
            orphan_parent = "99999999-8888-7777-6666-555555555555"
            # No parent transcript — simulate cleaned-up session.
            (pdir / "agent-orphan1.jsonl").write_text(
                json.dumps({"type": "user", "timestamp": "2026-04-18T00:00:02.000Z",
                            "sessionId": orphan_parent,
                            "message": {"role": "user", "content": "go"}}) + "\n" +
                json.dumps({"type": "assistant", "timestamp": "2026-04-18T00:00:03.000Z",
                            "sessionId": orphan_parent,
                            "message": {"role": "assistant", "model": "claude-haiku-4-5",
                                        "content": [],
                                        "usage": {"input_tokens": 5, "output_tokens": 7,
                                                  "cache_creation_input_tokens": 50,
                                                  "cache_read_input_tokens": 500}}}) + "\n"
            )
            out = tmp / "out.jsonl"
            r = _run_scanner(tmp / "projects", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
            # One synthetic orphan row carrying the subagent tokens.
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["session_id"], orphan_parent)
            self.assertEqual(row["cache_read_input_tokens"], 500)
            self.assertEqual(row["model_counts"].get("claude-haiku-4-5"), 1)
            # Marked as orphan so downstream knows it lacks a parent transcript
            self.assertTrue(row.get("orphan_subagent_only"))

    def test_skips_non_transcript_files(self):
        """Files like skill-injections.jsonl must not produce rows."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pdir = tmp / "projects" / "-proj"
            pdir.mkdir(parents=True)
            # Write a skill-injections-like file: no type=user or type=assistant lines
            (pdir / "skill-injections.jsonl").write_text(
                json.dumps({"event": "whatever", "timestamp": "2026-04-18T00:00:00.000Z"}) + "\n"
            )
            out = tmp / "out.jsonl"
            r = _run_scanner(tmp / "projects", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(out.read_text().strip(), "")

    def test_project_path_decoded(self):
        """Parent-dir-encoded path ('-Users-alice-Projects-app') must round-trip
        back to '/Users/alice/Projects/app'. Uses the FIXTURE_PROJECTS_DIR, which
        decodes to the leading segments of the original path."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_fixture(tmp)
            out = tmp / "out.jsonl"
            _run_scanner(tmp / "projects", out)
            row = json.loads(out.read_text().splitlines()[0])
            # FIXTURE_PROJECTS_DIR = "-Users-<name>" decodes to "/Users/<name>".
            expected = "/" + FIXTURE_PROJECTS_DIR.lstrip("-").replace("-", "/")
            self.assertEqual(row["project_path"], expected)


class HitOutputLimitTests(unittest.TestCase):
    def test_row_marks_hit_output_limit_when_max_tokens_seen(self):
        """stop_reason lives on the inner `message` dict, not the outer transcript
        record — easy to miss, so both polarities are asserted."""
        sid = "abc12345-0000-0000-0000-000000000001"
        rows = [
            {"type": "user", "sessionId": sid,
             "message": {"role": "user", "content": "hi"},
             "timestamp": "2026-04-19T10:00:00Z"},
            {"type": "assistant", "sessionId": sid,
             "message": {"role": "assistant", "content": "truncated...",
                         "stop_reason": "max_tokens",
                         "usage": {"input_tokens": 10, "output_tokens": 8000}},
             "timestamp": "2026-04-19T10:00:05Z"},
        ]
        emitted = _run_single_row_session(rows, sid)
        self.assertTrue(emitted.get("hit_output_limit"))

    def test_row_hit_output_limit_false_when_no_max_tokens(self):
        """Complementary polarity: non-max-tokens stop must not flip the flag."""
        sid = "def45678-0000-0000-0000-000000000002"
        rows = [
            {"type": "user", "sessionId": sid,
             "message": {"role": "user", "content": "hi"},
             "timestamp": "2026-04-19T10:00:00Z"},
            {"type": "assistant", "sessionId": sid,
             "message": {"role": "assistant", "content": "done",
                         "stop_reason": "end_turn",
                         "usage": {"input_tokens": 10, "output_tokens": 20}},
             "timestamp": "2026-04-19T10:00:05Z"},
        ]
        emitted = _run_single_row_session(rows, sid)
        self.assertFalse(emitted.get("hit_output_limit", False))


class RedactedSchemaTests(unittest.TestCase):
    def test_redacted_keys_include_hit_output_limit(self):
        self.assertIn("hit_output_limit", aggregate._REDACTED_META_KEYS)

    def test_redacted_keys_include_token_accel(self):
        self.assertIn("token_accel", aggregate._REDACTED_META_KEYS)

    def test_redacted_keys_include_segments(self):
        # Fix 5: segments are timestamps only (no content) — dropping them
        # from the redaction allowlist forces cross-machine rows back onto
        # the full-span [start, start+duration] fallback, which counts idle
        # gaps as active time in the switch-tax / parallel-overlap sweeps.
        self.assertIn("segments", aggregate._REDACTED_META_KEYS)

    def test_load_redacted_round_trips_segments(self):
        # A redacted-rows dump that carries segments must have them survive
        # load_redacted intact, so downstream _row_windows() sees real
        # idle-gap-aware windows instead of falling back to full-span.
        sid = "30303030-0000-0000-0000-000000000003"
        segments = [
            ["2026-04-01T10:00:00+00:00", "2026-04-01T10:05:00+00:00"],
            ["2026-04-11T09:00:00+00:00", "2026-04-11T09:05:00+00:00"],
        ]
        row = {
            "session_id": sid,
            "start_time": "2026-04-01T10:00:00+00:00",
            "duration_minutes": 14400,
            "segments": segments,
            "first_prompt_len": 5,
            "source_machine": "test-machine",
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sessions-redacted.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            metas, facets, source_by_sid = aggregate.load_redacted(path)
        self.assertEqual(metas[sid]["segments"], segments)
        windows = aggregate._row_windows(metas[sid])
        self.assertEqual(len(windows), 2)


class TokenAccelTests(unittest.TestCase):
    def _scan_with_outputs(self, outputs):
        """Build a synthetic transcript with len(outputs) assistant messages
        whose usage.output_tokens follow `outputs`, scan it, return the row."""
        sid = "10101010-0000-0000-0000-000000000001"
        rows = [
            {"type": "user", "sessionId": sid,
             "message": {"role": "user", "content": "hi"},
             "timestamp": "2026-04-19T10:00:00Z"},
        ]
        for i, out_tok in enumerate(outputs):
            rows.append({
                "type": "assistant", "sessionId": sid,
                "message": {"role": "assistant", "content": "ok",
                            "model": "claude-opus-4-6",
                            "usage": {"input_tokens": 10, "output_tokens": out_tok}},
                "timestamp": f"2026-04-19T10:{i:02d}:05Z",
            })
        return _run_single_row_session(rows, sid)

    def test_accelerating_session(self):
        row = self._scan_with_outputs([100, 100, 100, 300, 300, 300])
        self.assertAlmostEqual(row["token_accel"], 3.0)

    def test_flat_session(self):
        row = self._scan_with_outputs([200] * 6)
        self.assertAlmostEqual(row["token_accel"], 1.0)

    def test_too_few_messages_is_none(self):
        row = self._scan_with_outputs([100] * 5)
        self.assertIsNone(row["token_accel"])

    def test_zero_first_half_is_none(self):
        row = self._scan_with_outputs([0, 0, 0, 100, 100, 100])
        self.assertIsNone(row["token_accel"])

    def test_odd_count_middle_message_in_second_half(self):
        # n=7: first = seq[:3] = [100,100,100] = 300;
        # second = seq[3:] = [300,300,300,300] = 1200 (middle index 3 included).
        row = self._scan_with_outputs([100, 100, 100, 300, 300, 300, 300])
        self.assertAlmostEqual(row["token_accel"], 4.0)


class SubagentAwareTokenAccelTests(unittest.TestCase):
    """Fix 2 (round 11): token_accel must see subagent output. Previously
    the subagent merge pass folded in token TOTALS and models but not
    per-message output timing, so a session whose flat parent transcript
    had a subagent burn late was scored as flat — wrongly suppressing (or
    triggering sunk-cost) for Task/Agent-heavy sessions."""

    def _write_parent_and_subagent(self, tmp, parent_outputs, subagent_outputs,
                                    subagent_start_minute=10):
        pdir = tmp / "projects" / "p"
        pdir.mkdir(parents=True)
        parent_sid = "aaaaaaaa-1111-2222-3333-444444444444"
        lines = [json.dumps({"type": "user", "sessionId": parent_sid,
                             "message": {"role": "user", "content": "hi"},
                             "timestamp": "2026-04-19T10:00:00Z"})]
        for i, out_tok in enumerate(parent_outputs):
            lines.append(json.dumps({
                "type": "assistant", "sessionId": parent_sid,
                "message": {"role": "assistant", "content": "ok",
                            "model": "claude-opus-4-6",
                            "usage": {"input_tokens": 10, "output_tokens": out_tok}},
                "timestamp": f"2026-04-19T10:{i:02d}:05Z",
            }))
        (pdir / f"{parent_sid}.jsonl").write_text("\n".join(lines))

        if subagent_outputs:
            sub_lines = []
            for i, out_tok in enumerate(subagent_outputs):
                minute = subagent_start_minute + i
                sub_lines.append(json.dumps({
                    "type": "assistant", "sessionId": parent_sid,
                    "message": {"role": "assistant", "content": [],
                                "model": "claude-opus-4-6",
                                "usage": {"input_tokens": 10, "output_tokens": out_tok}},
                    "timestamp": f"2026-04-19T{minute // 60 + 10:02d}:{minute % 60:02d}:05Z",
                }))
            (pdir / "agent-subagent1.jsonl").write_text("\n".join(sub_lines))
        return parent_sid

    def test_subagent_late_burn_raises_token_accel(self):
        # Parent transcript alone is flat (accel ~1.0); a subagent whose
        # outputs triple late in the session (timestamped after the parent's
        # messages) must pull the merged token_accel to >= 1.5.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            parent_sid = self._write_parent_and_subagent(
                tmp,
                parent_outputs=[100, 100, 100, 100, 100, 100],
                subagent_outputs=[300, 300, 300],
                subagent_start_minute=20,
            )
            out = tmp / "out.jsonl"
            r = _run_scanner(tmp / "projects", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
            row = next(x for x in rows if x["session_id"] == parent_sid)
            self.assertGreaterEqual(row["token_accel"], 1.5)

    def test_same_parent_without_subagent_has_lower_accel(self):
        # Same parent transcript, no subagent file at all: token_accel must
        # be lower than the merged case above (regression check that the
        # merge is actually responsible for the lift, not some other change).
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            parent_sid = self._write_parent_and_subagent(
                tmp,
                parent_outputs=[100, 100, 100, 100, 100, 100],
                subagent_outputs=[],
            )
            out = tmp / "out.jsonl"
            r = _run_scanner(tmp / "projects", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
            row = next(x for x in rows if x["session_id"] == parent_sid)
            self.assertAlmostEqual(row["token_accel"], 1.0)


class SubagentEvidenceMergeTests(unittest.TestCase):
    """Fix 3 (round 11): subagent tool/commit evidence must reach the
    merged parent row's activity fields — delegated Edit/Write or git
    commits inside a Task/Agent subagent were previously invisible to the
    graveyard heuristic and compute_ledger, which only saw parent-transcript
    tool_counts/git_commits/git_pushes."""

    def test_subagent_edits_and_commit_merge_into_parent_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pdir = tmp / "projects" / "p"
            pdir.mkdir(parents=True)
            parent_sid = "bbbbbbbb-1111-2222-3333-444444444444"
            (pdir / f"{parent_sid}.jsonl").write_text(
                json.dumps({"type": "user", "sessionId": parent_sid,
                            "message": {"role": "user", "content": "hi"},
                            "timestamp": "2026-04-19T10:00:00Z"}) + "\n" +
                json.dumps({"type": "assistant", "sessionId": parent_sid,
                            "message": {"role": "assistant", "model": "claude-opus-4-6",
                                        "content": [],
                                        "usage": {"input_tokens": 10, "output_tokens": 10}}},
                           ) + "\n"
            )
            sub_lines = []
            for i in range(6):
                sub_lines.append(json.dumps({
                    "type": "assistant", "sessionId": parent_sid,
                    "message": {"role": "assistant", "model": "claude-opus-4-6",
                                "content": [{"type": "tool_use", "name": "Edit",
                                            "input": {"file_path": f"f{i}.py"}}],
                                "usage": {"input_tokens": 5, "output_tokens": 5}},
                    "timestamp": f"2026-04-19T10:{10+i:02d}:00Z",
                }))
            sub_lines.append(json.dumps({
                "type": "assistant", "sessionId": parent_sid,
                "message": {"role": "assistant", "model": "claude-opus-4-6",
                            "content": [{"type": "tool_use", "name": "Bash",
                                        "input": {"command": "git commit -m 'wip'"}}],
                            "usage": {"input_tokens": 5, "output_tokens": 5}},
                "timestamp": "2026-04-19T10:20:00Z",
            }))
            (pdir / "agent-subagent1.jsonl").write_text("\n".join(sub_lines))
            out = tmp / "out.jsonl"
            r = _run_scanner(tmp / "projects", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
            row = next(x for x in rows if x["session_id"] == parent_sid)
            self.assertGreaterEqual(row["tool_counts"].get("Edit", 0), 6)
            self.assertGreaterEqual(row["git_commits"], 1)

    def test_bs_graveyard_sees_subagent_only_writes_and_commits(self):
        # Three stale (>= horizon days untouched) projects. A's only
        # substantive writes happened inside its subagent (no parent writes
        # at all) -> qualifies as a graveyard item. B's subagent committed
        # -> disqualified even though its parent-level writes alone would
        # have qualified. C is a plain parent-only qualifier, present so the
        # >=2-qualifying-items gate passes and metrics.items is populated
        # (the gate would otherwise suppress on A alone).
        import sys as _sys
        SKILL_DIR = Path(__file__).resolve().parent.parent
        _sys.path.insert(0, str(SKILL_DIR / "scripts"))
        import aggregate as agg
        from datetime import datetime, timezone

        window_end = datetime(2026, 5, 1, tzinfo=timezone.utc)
        old_start = "2026-01-01T09:00:00Z"

        row_a = {
            "session_id": "sa", "project_path": "/Users/demo/Projects/proj-a",
            "start_time": old_start, "duration_minutes": 5,
            "tool_counts": {},  # no parent-level writes
            "git_commits": 0, "git_pushes": 0,
        }
        row_b = {
            "session_id": "sb", "project_path": "/Users/demo/Projects/proj-b",
            "start_time": old_start, "duration_minutes": 5,
            "tool_counts": {"Edit": 5, "Write": 1},
            "git_commits": 0, "git_pushes": 0,
        }
        row_c = {
            "session_id": "sc", "project_path": "/Users/demo/Projects/proj-c",
            "start_time": old_start, "duration_minutes": 5,
            "tool_counts": {"Edit": 5, "Write": 1},
            "git_commits": 0, "git_pushes": 0,
        }
        # Simulate what Pass 2 merge now does: subagent Edit-only evidence
        # merged into A's tool_counts; subagent commit evidence merged into
        # B's git_commits.
        row_a["tool_counts"] = dict(Counter(row_a["tool_counts"])
                                    + Counter({"Edit": 6}))
        row_b["git_commits"] += 1

        items = agg.bs_graveyard([row_a, row_b, row_c], window_end)
        self.assertTrue(items["gate_passed"])
        project_keys = {i["project_key"] for i in items["metrics"].get("items", [])}
        self.assertIn("Projects/proj-a", project_keys)
        self.assertIn("Projects/proj-c", project_keys)
        self.assertNotIn("Projects/proj-b", project_keys)


class SegmentsTests(unittest.TestCase):
    """Fix 2: scan_transcripts.py emits idle-gap-split `segments` per row."""

    def test_two_clusters_ten_days_apart_yield_two_segments(self):
        sid = "20202020-0000-0000-0000-000000000002"
        rows = [
            {"type": "user", "sessionId": sid,
             "message": {"role": "user", "content": "hi"},
             "timestamp": "2026-04-01T10:00:00Z"},
            {"type": "assistant", "sessionId": sid,
             "message": {"role": "assistant", "content": "ok", "model": "claude-opus-4-6",
                         "usage": {"input_tokens": 10, "output_tokens": 10}},
             "timestamp": "2026-04-01T10:05:00Z"},
            {"type": "user", "sessionId": sid,
             "message": {"role": "user", "content": "resuming"},
             "timestamp": "2026-04-11T09:00:00Z"},
            {"type": "assistant", "sessionId": sid,
             "message": {"role": "assistant", "content": "ok", "model": "claude-opus-4-6",
                         "usage": {"input_tokens": 10, "output_tokens": 10}},
             "timestamp": "2026-04-11T09:05:00Z"},
        ]
        row = _run_single_row_session(rows, sid)
        self.assertIsNotNone(row.get("segments"))
        self.assertEqual(len(row["segments"]), 2)
        # duration_minutes must stay computed from full first/last span,
        # unaffected by the new segments field.
        self.assertGreater(row["duration_minutes"], 60 * 24 * 9)

    def test_row_windows_uses_segments_not_full_span(self):
        sys.path.insert(0, str(SKILL_DIR / "scripts"))
        from aggregate import _row_windows
        row = {
            "start_time": "2026-04-01T10:00:00+00:00",
            "duration_minutes": 14400,  # ~10 days, what the no-segments fallback would use
            "segments": [
                ["2026-04-01T10:00:00+00:00", "2026-04-01T10:05:00+00:00"],
                ["2026-04-11T09:00:00+00:00", "2026-04-11T09:05:00+00:00"],
            ],
        }
        windows = _row_windows(row)
        self.assertEqual(len(windows), 2)
        for start, end in windows:
            self.assertLess((end - start).total_seconds(), 3600)

    def test_switch_tax_false_positive_gone_for_row_in_idle_gap(self):
        """A codex row active inside the claude row's 10-day idle gap must NOT
        overlap the claude row's windows once segments are honored."""
        sys.path.insert(0, str(SKILL_DIR / "scripts"))
        from aggregate import _row_windows
        claude_row = {
            "start_time": "2026-04-01T10:00:00+00:00",
            "duration_minutes": 14400,
            "segments": [
                ["2026-04-01T10:00:00+00:00", "2026-04-01T10:05:00+00:00"],
                ["2026-04-11T09:00:00+00:00", "2026-04-11T09:05:00+00:00"],
            ],
        }
        codex_row = {
            "start_time": "2026-04-05T12:00:00+00:00",
            "duration_minutes": 20,
            "source": "codex",
        }
        claude_windows = _row_windows(claude_row)
        codex_windows = _row_windows(codex_row)

        def _overlaps(a, b):
            return a[0] < b[1] and b[0] < a[1]

        overlap_found = any(
            _overlaps(cw, kw) for cw in claude_windows for kw in codex_windows)
        self.assertFalse(
            overlap_found,
            "codex row inside claude's idle gap must not overlap claude's "
            "segment-derived windows")


if __name__ == "__main__":
    unittest.main()
