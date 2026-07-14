"""Praise-word lint (spec §2 audit-discipline rule 1, §8).

One word list per locale, shared by two consumers: the hard test on demo
fixtures (tests/) and the build-time warning in build_html.py. The lint
flags cheerleading vocabulary WITHOUT a number in the same sentence — the
audit rule's remediation is "anchor the adjective to a number", so praise
that already has numeric support right next to it ("an impressive 92%
success rate") is not a violation and must not stay flagged forever. It is
a WARNING on real builds (prose review stays a human/LLM job); only the
test path is hard.
"""
import bisect
import re

PRAISE_WORDS_EN = (
    "impressive", "excellent", "amazing", "outstanding", "exceptional",
    "world-class", "stellar", "fantastic", "superb", "remarkable",
    "incredible", "phenomenal", "brilliant", "masterful", "elite",
)

PRAISE_WORDS_ZH = (
    "令人驚豔", "非常出色", "表現出色", "卓越", "頂尖", "亮眼",
    "出類拔萃", "優異", "驚人", "完美", "無可挑剔", "大師級",
    "世界級", "一流", "傑出",
)

_EN_RES = {w: re.compile(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])",
                         re.IGNORECASE)
           for w in PRAISE_WORDS_EN}
_ZH_RES = {w: re.compile(re.escape(w)) for w in PRAISE_WORDS_ZH}

# Sentence splitter shared by the suppression check below — English and
# full-width CJK terminators, plus bare newlines (narrative markdown often
# has no terminal punctuation at a line break).
_SENTENCE_SPLIT_RE = re.compile(r"[.!?。！？\n]")

# Any ASCII or full-width digit counts as "numeric support" for a sentence.
_DIGIT_RE = re.compile(r"[0-9０-９]")


def _sentence_digit_flags(text):
    """Precompute, once per find_praise() call, whether each sentence in
    text contains a digit — returns (boundaries, has_digit) where
    boundaries is the sorted list of sentence-start offsets and has_digit[i]
    says whether the i-th sentence has numeric support. Sentences are
    delimited by _SENTENCE_SPLIT_RE; commas are NOT sentence breaks, so
    "表現出色，成功率 92%" counts as one sentence.

    Callers look up a match's sentence via bisect on boundaries instead of
    rescanning the split regex from the start of text on every match —
    O(text_length) total instead of O(matches * text_length)."""
    starts = [0]
    for m in _SENTENCE_SPLIT_RE.finditer(text):
        starts.append(m.end())
    ends = starts[1:] + [len(text)]
    has_digit = [bool(_DIGIT_RE.search(text, s, e))
                for s, e in zip(starts, ends)]
    return starts, has_digit


def find_praise(text):
    """Scan text against BOTH locales (mixed-language docs are normal).
    Only counts occurrences whose containing sentence has no digit — praise
    anchored to a number in the same sentence is not a violation. A word
    whose count falls to 0 after suppression is dropped entirely.
    Returns [{"word", "locale", "count"}] sorted by count desc."""
    if not isinstance(text, str) or not text:
        return []
    boundaries, has_digit = _sentence_digit_flags(text)

    def _has_numeric_support(match_start):
        i = bisect.bisect_right(boundaries, match_start) - 1
        return has_digit[i]

    hits = []
    for w, rx in _EN_RES.items():
        n = sum(1 for m in rx.finditer(text)
                if not _has_numeric_support(m.start()))
        if n:
            hits.append({"word": w, "locale": "en", "count": n})
    for w, rx in _ZH_RES.items():
        n = sum(1 for m in rx.finditer(text)
                if not _has_numeric_support(m.start()))
        if n:
            hits.append({"word": w, "locale": "zh_TW", "count": n})
    hits.sort(key=lambda h: -h["count"])
    return hits
