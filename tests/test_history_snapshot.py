import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from build_html import append_history_snapshot  # noqa: E402

ANALYSIS = {
    "meta": {"total_sessions": 12},
    "scores": {"D1_delegation": {"score": 7}, "_overall": {"score": 6.1}},
    "ledger": {"schema_version": 1,
               "output": {"git_commits": 9, "git_pushes": 4,
                          "sessions_with_commits": 5},
               "sources_detected": ["claude", "codex"]},
}


class SnapshotTests(unittest.TestCase):
    def test_appends_one_line_for_self(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "sub" / "autopsy-history.jsonl"
            append_history_snapshot(hist, ANALYSIS, "self")
            append_history_snapshot(hist, ANALYSIS, "self")
            lines = hist.read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)
        entry = json.loads(lines[0])
        self.assertEqual(entry["schema_version"], 1)
        self.assertEqual(entry["scores"]["D1_delegation"], 7)
        self.assertEqual(entry["badges"], [])
        self.assertEqual(entry["ledger"]["git_commits"], 9)
        self.assertIn("date", entry)

    def test_hr_build_never_appends(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "autopsy-history.jsonl"
            append_history_snapshot(hist, ANALYSIS, "hr")
            self.assertFalse(hist.exists())

    def test_failure_warns_but_does_not_raise(self):
        # a directory at the target path makes open() fail
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td)  # is a dir, not a file
            append_history_snapshot(bad, ANALYSIS, "self")  # must not raise


if __name__ == "__main__":
    unittest.main()
