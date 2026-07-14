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

    def test_malformed_scalar_json_line_counted(self):
        # A syntactically valid JSON line that isn't an object (bare number)
        # must not raise when the scanner does rec.get(...); it should be
        # counted as a parse error and skipped.
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "%2Fx"
            d.mkdir()
            (d / "prompt_history.jsonl").write_text(
                '{"timestamp": "2026-06-24T06:00:00Z", "session_id": "g-1", '
                '"prompt": "p", "is_bash": false}\n7\n', encoding="utf-8")
            rows, errors = scan_sessions_dir(Path(td))
        self.assertEqual(errors, 1)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
