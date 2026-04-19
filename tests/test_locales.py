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

    def test_zh_tw_strings_have_no_ai_em_dash(self):
        offenders = [
            (k, v) for k, v in locales.STRINGS["zh_TW"].items() if "——" in v
        ]
        self.assertEqual(offenders, [],
                         f"zh_TW strings must not use AI em-dash: {offenders}")


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


if __name__ == "__main__":
    unittest.main()
