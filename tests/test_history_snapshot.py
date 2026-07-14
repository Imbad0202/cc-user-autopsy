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

ANALYSIS_WITH_LEAKS = {
    "meta": {"total_sessions": 12},
    "scores": {"D1_delegation": {"score": 7}, "_overall": {"score": 6.1}},
    "ledger": {"schema_version": 1,
               "output": {"git_commits": 9, "git_pushes": 4,
                          "sessions_with_commits": 5},
               "sources_detected": ["claude", "codex"],
               "leaks": {
                   "window_weeks": 4.0,
                   "items": [
                       {"type": "repeated_instructions",
                        "weekly_cost_usd": 1.23,
                        "weekly_tokens": 45000,
                        "occurrences": 6,
                        "evidence": [{"sid": "session-secret-abc"}]},
                       {"type": "sunk_cost",
                        "weekly_cost_usd": 0.55,
                        "weekly_tokens": 12000,
                        "occurrences": 2,
                        "evidence": ["session-secret-xyz"]},
                   ],
               }},
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

    def test_leaks_carried_as_compact_metrics_without_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "autopsy-history.jsonl"
            append_history_snapshot(hist, ANALYSIS_WITH_LEAKS, "self")
            line = hist.read_text().strip()
        self.assertNotIn("session-secret-abc", line)
        self.assertNotIn("session-secret-xyz", line)
        entry = json.loads(line)
        leaks = entry["ledger"]["leaks"]
        self.assertEqual(len(leaks), 2)
        self.assertEqual(leaks[0], {
            "type": "repeated_instructions",
            "weekly_cost_usd": 1.23,
            "weekly_tokens": 45000,
            "occurrences": 6,
        })
        self.assertEqual(leaks[1], {
            "type": "sunk_cost",
            "weekly_cost_usd": 0.55,
            "weekly_tokens": 12000,
            "occurrences": 2,
        })
        for item in leaks:
            self.assertNotIn("evidence", item)

    def test_leaks_absent_yields_empty_list(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "autopsy-history.jsonl"
            append_history_snapshot(hist, ANALYSIS, "self")
            entry = json.loads(hist.read_text().strip())
        self.assertEqual(entry["ledger"]["leaks"], [])

    def test_malformed_analysis_shapes_do_not_raise(self):
        # scores/output as non-dict truthy values (e.g. from a malformed or
        # foreign analysis-data.json) must warn, not crash the build.
        malformed = {"scores": ["not", "a", "dict"],
                     "ledger": {"output": "nope"}}
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "autopsy-history.jsonl"
            append_history_snapshot(hist, malformed, "self")  # must not raise


if __name__ == "__main__":
    unittest.main()
