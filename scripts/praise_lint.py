"""Praise-word lint (spec §2 audit-discipline rule 1, §8).

One word list per locale, shared by two consumers: the hard test on demo
fixtures (tests/) and the build-time warning in build_html.py. The lint
flags cheerleading vocabulary — evaluative praise with no number behind
it. It is a WARNING on real builds (prose review stays a human/LLM job);
only the test path is hard.
"""
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


def find_praise(text):
    """Scan text against BOTH locales (mixed-language docs are normal).
    Returns [{"word", "locale", "count"}] sorted by count desc."""
    if not isinstance(text, str) or not text:
        return []
    hits = []
    for w, rx in _EN_RES.items():
        n = len(rx.findall(text))
        if n:
            hits.append({"word": w, "locale": "en", "count": n})
    for w in PRAISE_WORDS_ZH:
        n = text.count(w)
        if n:
            hits.append({"word": w, "locale": "zh_TW", "count": n})
    hits.sort(key=lambda h: -h["count"])
    return hits
