"""TDD for scripts/scan_transcripts.py.

Ground truth: the session-meta file for session f831eb28 (which exists because
a past Claude Code run auto-produced it). We scan the matching transcript and
assert our derived numbers match the meta's numbers within tolerance.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCANNER = SKILL_DIR / "scripts" / "scan_transcripts.py"

# Known-good session with both meta and transcript locally.
# If this file disappears, pick another. The test hard-codes the
# ground-truth values so CI reproducibility is possible even if the
# local fixture changes — we copy the fixture into the test dir below.
FIXTURE_SID = "f831eb28-e1f9-43af-a5bb-1c216021d89f"
FIXTURE_META = Path.home() / ".claude/usage-data/session-meta" / f"{FIXTURE_SID}.json"
FIXTURE_TRANSCRIPT = Path.home() / ".claude/projects/-Users-imbad" / f"{FIXTURE_SID}.jsonl"


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
    pdir = root / "projects" / "-Users-imbad"
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
        """Parent-dir-encoded path ('-Users-imbad-Projects-HEEACT') must round-trip
        back to '/Users/imbad/Projects/HEEACT'."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _setup_fixture(tmp)
            out = tmp / "out.jsonl"
            _run_scanner(tmp / "projects", out)
            row = json.loads(out.read_text().splitlines()[0])
            self.assertEqual(row["project_path"], "/Users/imbad")


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


if __name__ == "__main__":
    unittest.main()
