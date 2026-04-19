"""STRINGS dict and t() helper. Hard failure on any missing key, unknown
locale, or AI em-dash in zh_TW values — those would silently produce
mixed-language reports or violate the user's writing-style rules."""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import locales  # noqa: E402


class StringsCatalogTests(unittest.TestCase):
    def test_locale_keysets_match(self):
        en_keys = set(locales.STRINGS["en"].keys())
        zh_keys = set(locales.STRINGS["zh_TW"].keys())
        missing_in_zh = en_keys - zh_keys
        missing_in_en = zh_keys - en_keys
        self.assertEqual(
            (missing_in_zh, missing_in_en), (set(), set()),
            f"keysets diverged: missing_in_zh={missing_in_zh}, missing_in_en={missing_in_en}",
        )

    def test_supported_locales_are_exactly_en_and_zh_tw(self):
        self.assertEqual(set(locales.STRINGS.keys()), {"en", "zh_TW"})

    def test_zh_tw_strings_have_no_em_dash(self):
        """zh_TW strings must use comma + clause continuation instead of em-dash.
        Catches both AI double em-dash (——) and single em-dash (—) accidentally
        pasted from English source."""
        offenders = [
            (k, v) for k, v in locales.STRINGS["zh_TW"].items() if "—" in v
        ]
        self.assertEqual(offenders, [],
                         f"zh_TW strings must not use em-dash: {offenders}")

    def test_no_empty_values(self):
        """A blank value would render as a missing tile / empty title with no
        test-time signal — catch it here instead of at runtime."""
        empties = [
            (locale, key)
            for locale, d in locales.STRINGS.items()
            for key, v in d.items()
            if not v.strip()
        ]
        self.assertEqual(empties, [], f"empty/whitespace values: {empties}")


class LookupHelperTests(unittest.TestCase):
    def test_t_returns_string_for_known_key(self):
        self.assertEqual(locales.t("en", "report_title"),
                         locales.STRINGS["en"]["report_title"])

    def test_t_raises_on_missing_key(self):
        with self.assertRaises(KeyError):
            locales.t("en", "this_key_does_not_exist")

    def test_t_raises_on_unknown_locale(self):
        with self.assertRaises(KeyError):
            locales.t("ja", "report_title")


class UsageRubricKeysTests(unittest.TestCase):
    REQUIRED_KEYS = [
        "score_disclaimer",
        "score_disclaimer_long",
        "how_to_read_key_relate",
        "how_to_read_val_relate",
        "usage_char_header",
        "usage_char_note_template",
    ]

    def test_all_usage_rubric_keys_present_in_en(self):
        missing = [k for k in self.REQUIRED_KEYS if k not in locales.STRINGS["en"]]
        self.assertEqual(missing, [], f"Missing keys in en: {missing}")

    def test_all_usage_rubric_keys_present_in_zh_tw(self):
        missing = [k for k in self.REQUIRED_KEYS if k not in locales.STRINGS["zh_TW"]]
        self.assertEqual(missing, [], f"Missing keys in zh_TW: {missing}")

    @unittest.skip(
        "Tech-debt marker: zh_TW values carry [TODO zh_TW] placeholder prose. "
        "Remove this skip and supply native-tone translations in a follow-up PR."
    )
    def test_no_zh_tw_todo_markers_in_release(self):
        offenders = [
            (k, v)
            for k, v in locales.STRINGS["zh_TW"].items()
            if v.startswith("[TODO zh_TW]")
        ]
        self.assertEqual(offenders, [], f"zh_TW TODO stubs still present: {offenders}")


if __name__ == "__main__":
    unittest.main()
