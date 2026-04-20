"""Token system tests.

Enforces the two-layer design token architecture documented in
docs/superpowers/specs/2026-04-19-design-tokens-audit-design.md.
Primitives define the scale; semantic aliases name the intent.
Target component CSS blocks must not contain hard-coded spacing.
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# PAGE_TEMPLATE and CSS live in report_render.py after the Task 7 extraction.
BUILD_HTML = REPO_ROOT / "scripts" / "report_render.py"

# Components that have been refactored to use tokens. Each entry:
# (name, start_marker, end_marker) — raw substrings bracketing the CSS rule set.
# Tasks 5-9 add entries here as each component is cleaned.
CLEANED_COMPONENTS: list[tuple[str, str, str]] = [
    (
        ".profile-card",
        "  .profile-card {",
        "    margin-top: var(--space-1);\n  }",
    ),
    (
        ".metrics",
        "  /* Metric cards grid */\n  .metrics {",
        "    margin-top: var(--space-4);\n  }",
    ),
    (
        ".chart-box",
        "  /* Charts */\n  .chart-box {",
        "    text-transform: uppercase;\n  }",
    ),
    (
        "details.evidence",
        "  /* §06 evidence library */\n  details.evidence {",
        "    word-break: break-all;\n  }",
    ),
    (
        ".dek",
        "  .dek {",
        "    margin: 0 0 var(--section-gap) 0;\n  }",
    ),
    (
        ".intro-card",
        "  .intro-card {",
        "    color: var(--accent);\n  }",
    ),
    (
        ".method",
        "  /* §07 methodology */\n  .method {",
        "  .method li { margin: var(--space-2) 0; }\n",
    ),
    (
        ".caveat",
        "  .caveat {",
        "    line-height: 1.6;\n  }",
    ),
    (
        ".evidence-header",
        "  .evidence-header {",
        "    border-bottom: 1px solid var(--rule);\n  }",
    ),
]

# Hard-coded px values that are allowed inside cleaned component blocks.
# Each entry should have a reason documented in the plan or in later tasks.
HARDCODE_WHITELIST_PX = {
    # --- Universal ---
    "1px",                                   # border width

    # --- Sparse typographic trim (mono caps labels, no token home) ---
    "9.5px", "10.5px", "11.5px", "14.5px",

    # --- Evidence prose font-size (no --text-* step between 13 and 15) ---
    "14px",                                  # details.evidence p — body text

    # --- Display-size typography (unique hero numerics) ---
    "32px",                                  # .metric .n display-size number

    # --- Evidence summary grid layout constants (tri-column summary) ---
    "80px", "90px", "106px",                 # grid cols + p padding-left alignment

    # --- Fixed chart canvas heights (not spacing) ---
    "260px", "340px", "420px",              # .chart-box .short / default / .tall

    # --- Border indicator widths (used as visual accents, not spacing) ---
    "3px", "4px",                            # caveat / profile-card accent border-left

    # --- Responsive breakpoints (shared across components) ---
    "640px",                                 # mobile breakpoint (max-width)

    # --- Component-unique spacing (profile-card + small components) ---
    "34px",                                  # profile-card horiz padding + evidence-header top margin (coincident value, unrelated intent)
    "48px",                                  # profile-card bottom margin (not on 2px scale)
    "22px",                                  # profile-lede font-size (unique hero-ish)
    "12px",                                  # profile-cell .sub font-size (small-print)

    # --- Small component unique values ---
    "10px",                                  # intro-card ::before NOTE badge font-size
    "15.5px",                                # intro-card font-size (mirrors zh-Hant body baseline)
    "26px",                                  # intro-card horizontal padding
}


class TokenPrimitivesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = BUILD_HTML.read_text(encoding="utf-8")

    def test_spacing_primitives_defined(self):
        for n in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15):
            self.assertRegex(
                self.src,
                rf"--space-{n}\s*:",
                f"missing --space-{n} in :root",
            )

    def test_radius_primitives_defined(self):
        for name in ("sm", "md", "lg"):
            self.assertRegex(self.src, rf"--radius-{name}\s*:")

    def test_text_primitives_defined(self):
        for name in ("xs", "sm", "base", "md", "lg", "xl", "2xl"):
            self.assertRegex(self.src, rf"--text-{name}\s*:")

    def test_leading_primitives_defined(self):
        for name in ("tight", "snug", "normal", "loose"):
            self.assertRegex(self.src, rf"--leading-{name}\s*:")


# Note: --card-padding and --card-radius were originally planned but removed
# in the YAGNI pass (no concrete downstream consumer). If future components
# require them, restore the aliases in :root AND add matching tests here.
class SemanticAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = BUILD_HTML.read_text(encoding="utf-8")

    def test_section_gap_defined(self):
        self.assertRegex(self.src, r"--section-gap\s*:\s*var\(--space-")

    def test_tag_padding_defined(self):
        self.assertRegex(self.src, r"--tag-padding-y\s*:\s*var\(--space-")
        self.assertRegex(self.src, r"--tag-padding-x\s*:\s*var\(--space-")


class NoHardcodedSpacingTests(unittest.TestCase):
    """For each component in CLEANED_COMPONENTS, verify its CSS block
    contains no hard-coded px values outside the whitelist.

    Tasks 5-9 populate CLEANED_COMPONENTS incrementally. This test starts
    as a no-op (empty list) and catches regressions as refactor progresses.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = BUILD_HTML.read_text(encoding="utf-8")

    def _block(self, start: str, end: str) -> str:
        i = self.src.find(start)
        self.assertNotEqual(i, -1, f"start marker not found: {start!r}")
        j = self.src.find(end, i + len(start))
        self.assertNotEqual(j, -1, f"end marker not found after start: {end!r}")
        return self.src[i:j + len(end)]

    def test_cleaned_components_have_no_hardcoded_px(self):
        pattern = re.compile(r"(?<!-)\b(\d+(?:\.\d+)?px)\b")
        css_comment = re.compile(r"/\*.*?\*/", re.DOTALL)
        for name, start, end in CLEANED_COMPONENTS:
            with self.subTest(component=name):
                block = css_comment.sub("", self._block(start, end))
                hits = [m.group(1) for m in pattern.finditer(block)]
                leaked = [h for h in hits if h not in HARDCODE_WHITELIST_PX]
                self.assertEqual(
                    leaked, [],
                    f"component {name!r} leaks hardcoded px: {leaked}",
                )


class ZhHantHeroWeightTests(unittest.TestCase):
    """Verify zh-Hant hero title overrides font-weight to 500 (em to 600).
    Reason: variable serif weight 300 renders fragile on CJK fallbacks
    (PingFang, Noto Serif CJK) which lack a weight axis.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = BUILD_HTML.read_text(encoding="utf-8")

    def test_hero_title_weight_override(self):
        pattern = re.compile(
            r'html\[lang="zh-Hant"\]\s+h1\.title\s*\{[^}]*font-weight:\s*500',
            re.DOTALL,
        )
        self.assertRegex(self.src, pattern)

    def test_hero_title_em_weight_override(self):
        pattern = re.compile(
            r'html\[lang="zh-Hant"\]\s+h1\.title\s+em\s*\{[^}]*font-weight:\s*600',
            re.DOTALL,
        )
        self.assertRegex(self.src, pattern)


if __name__ == "__main__":
    unittest.main()
