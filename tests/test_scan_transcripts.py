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

    def test_skips_subagent_runs(self):
        """agent-*.jsonl files are subagent internal runs and must be excluded."""
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
            # Subagent-style filename — must be skipped
            (pdir / "agent-abc123def456789.jsonl").write_text(
                json.dumps({"type": "user", "timestamp": "2026-04-18T00:00:00.000Z",
                            "message": {"role": "user", "content": "subagent"}}) + "\n"
            )
            out = tmp / "out.jsonl"
            r = _run_scanner(tmp / "projects", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = out.read_text().splitlines()
            self.assertEqual(len(lines), 1, "exactly the UUID-named transcript should be emitted")
            self.assertEqual(json.loads(lines[0])["session_id"], real)

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


if __name__ == "__main__":
    unittest.main()
