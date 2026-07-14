import unittest

from scripts.praise_lint import PRAISE_WORDS_EN, PRAISE_WORDS_ZH, find_praise


class WordListTests(unittest.TestCase):
    def test_lists_nonempty_and_lowercase(self):
        self.assertGreaterEqual(len(PRAISE_WORDS_EN), 10)
        self.assertGreaterEqual(len(PRAISE_WORDS_ZH), 10)
        for w in PRAISE_WORDS_EN:
            self.assertEqual(w, w.lower())

    def test_no_em_dash_in_zh_list(self):
        for w in PRAISE_WORDS_ZH:
            self.assertNotIn("—", w)


class FindPraiseTests(unittest.TestCase):
    def test_en_word_boundary(self):
        hits = find_praise("This result is impressive, truly world-class.")
        words = {h["word"] for h in hits}
        self.assertIn("impressive", words)
        self.assertIn("world-class", words)

    def test_en_substring_not_flagged(self):
        # "impressively" must not fire the "impressive" entry via substring
        self.assertEqual(
            [h for h in find_praise("compression ratio") if h["word"] == "impressive"],
            [])

    def test_zh_substring_match(self):
        hits = find_praise("這輪產出非常出色，維持水準")
        self.assertIn("非常出色", {h["word"] for h in hits})

    def test_clean_text_empty(self):
        clean = ("Commits per active week: 4.2, above the 3.0 bar. "
                 "本週提交 4.2 次，高於 3.0 的門檻。")
        self.assertEqual(find_praise(clean), [])

    def test_counts_and_ordering(self):
        hits = find_praise("excellent work. excellent choice. superb.")
        self.assertEqual(hits[0]["word"], "excellent")
        self.assertEqual(hits[0]["count"], 2)

    def test_praise_with_number_in_same_sentence_not_flagged(self):
        hits = find_praise("an impressive 92% success rate.")
        self.assertEqual(
            [h for h in hits if h["word"] == "impressive"], [])

    def test_praise_flagged_when_number_in_different_sentence(self):
        hits = find_praise("impressive work. throughput rose 40%.")
        words = {h["word"]: h["count"] for h in hits}
        self.assertEqual(words.get("impressive"), 1)

    def test_zh_praise_with_number_same_sentence_comma_not_break(self):
        # comma is not a sentence break, so the number after it still
        # counts as numeric support for the praise word before it.
        hits = find_praise("表現出色，成功率 92%")
        self.assertEqual(
            [h for h in hits if h["word"] == "表現出色"], [])


if __name__ == "__main__":
    unittest.main()
