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
