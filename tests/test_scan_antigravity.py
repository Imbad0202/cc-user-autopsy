# tests/test_scan_antigravity.py
import os
import tempfile
import unittest
from pathlib import Path

from scripts.scan_antigravity import scan_conversations_dir


class ScanAntigravityTests(unittest.TestCase):
    def test_presence_only_rows(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "00000000-0000-4000-8000-00000000a915.pb"
            p.write_bytes(b"\x00\x01")  # opaque; never parsed
            os.utime(p, (1776600000, 1776600000))
            rows = scan_conversations_dir(Path(td))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["session_id"], "00000000-0000-4000-8000-00000000a915")
        self.assertEqual(row["source"], "antigravity")
        self.assertEqual(row["coverage"], "presence_only")
        self.assertRegex(row["start_time"], r"[+-]\d{2}:\d{2}$")
        for k in ("duration_minutes", "segments", "user_message_count",
                  "assistant_message_count", "tool_counts", "input_tokens",
                  "output_tokens", "model_counts", "first_prompt"):
            self.assertIsNone(row[k], k)

    def test_missing_dir_returns_empty(self):
        self.assertEqual(scan_conversations_dir(Path("/nonexistent/xyz")), [])


if __name__ == "__main__":
    unittest.main()
