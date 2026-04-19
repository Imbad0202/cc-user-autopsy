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
BUILD_HTML = REPO_ROOT / "scripts" / "build_html.py"

# Components that have been refactored to use tokens. Each entry:
# (name, start_marker, end_marker) — raw substrings bracketing the CSS rule set.
# Tasks 5-9 add entries here as each component is cleaned.
CLEANED_COMPONENTS: list[tuple[str, str, str]] = []

# Hard-coded px values that are allowed inside cleaned component blocks.
# Each entry should have a reason documented in the plan or in later tasks.
# - 1px: universal border width
# - 9.5/10.5/11.5/14.5px: sparse typographic trim (mono caps, labels)
HARDCODE_WHITELIST_PX = {"1px", "9.5px", "10.5px", "11.5px", "14.5px"}


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
        for name in ("xs", "sm", "base", "md", "lg", "xl"):
            self.assertRegex(self.src, rf"--text-{name}\s*:")

    def test_leading_primitives_defined(self):
        for name in ("tight", "snug", "normal", "loose"):
            self.assertRegex(self.src, rf"--leading-{name}\s*:")


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
        for name, start, end in CLEANED_COMPONENTS:
            with self.subTest(component=name):
                block = self._block(start, end)
                hits = [m.group(1) for m in pattern.finditer(block)]
                leaked = [h for h in hits if h not in HARDCODE_WHITELIST_PX]
                self.assertEqual(
                    leaked, [],
                    f"component {name!r} leaks hardcoded px: {leaked}",
                )


if __name__ == "__main__":
    unittest.main()
