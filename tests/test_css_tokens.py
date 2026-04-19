"""Token system tests.

Enforces the two-layer design token architecture documented in
docs/superpowers/specs/2026-04-19-design-tokens-audit-design.md.
Primitives define the scale; semantic aliases name the intent.
Target component CSS blocks must not contain hard-coded spacing.
"""
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_HTML = REPO_ROOT / "scripts" / "build_html.py"


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


if __name__ == "__main__":
    unittest.main()
