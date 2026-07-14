"""TDD for direction-C rendering foundation: Exhibit frame, ledger narration
parser, and locale keys. See docs/superpowers/sdd/task-7-brief.md.

These are foundation-only tests — the section builders that call these
helpers land in a later task. Here we only verify the frame/parser
primitives and locale parity.
"""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import locales  # noqa: E402
from report_render import _exhibit, _parse_ledger_narration  # noqa: E402


class ExhibitTests(unittest.TestCase):
    def test_exhibit_frame(self):
        html = _exhibit(3, "Weekly share", "<p>body</p>",
                        "aggregate.py, transcript pool", locale="en")
        self.assertIn("EXHIBIT", html)
        self.assertIn("3", html)
        self.assertIn("<p>body</p>", html)
        self.assertIn("aggregate.py, transcript pool", html)

    def test_exhibit_escapes_source_line(self):
        html = _exhibit(1, "t", "<p>b</p>", "<script>x</script>", locale="en")
        self.assertNotIn("<script>x</script>", html)


class NarrationParseTests(unittest.TestCase):
    def test_parses_three_books(self):
        md = ("# opening\nOne sentence.\n"
              "# output-ledger\nClaim A.\n\nMore.\n"
              "# team-ledger\nClaim B.\n")
        d = _parse_ledger_narration(md)
        self.assertEqual(d["opening"], "One sentence.")
        self.assertTrue(d["output-ledger"].startswith("Claim A."))
        self.assertEqual(d["team-ledger"], "Claim B.")

    def test_missing_sections_empty(self):
        d = _parse_ledger_narration("")
        self.assertEqual(d, {"opening": "", "output-ledger": "", "team-ledger": ""})


class LedgerLocaleKeyTests(unittest.TestCase):
    REQUIRED = [
        "ledger_exhibit_label", "ledger_source_prefix", "ledger_opening_kicker",
        "ledger_output_title", "ledger_team_title", "ledger_source_card_full",
        "ledger_source_card_partial", "ledger_source_card_presence",
        "ledger_not_detected", "ledger_degraded_note",
        "ledger_common_window_note_template", "ledger_weekly_share_title",
        "ledger_parallel_title", "ledger_matrix_title", "ledger_h2h_title",
    ]

    def test_keys_in_both_locales(self):
        for loc in ("en", "zh_TW"):
            for key in self.REQUIRED:
                self.assertIn(key, locales.STRINGS[loc], f"{loc}:{key}")


if __name__ == "__main__":
    unittest.main()
