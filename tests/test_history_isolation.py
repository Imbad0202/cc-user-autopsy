"""Guard: no test may let build_html.py write to the user's REAL
~/.claude/usage-data/autopsy-history.jsonl.

build_html.py appends a trend snapshot to --history-file (default:
the real per-user path) on every successful SELF build. Any test that
drives build_html.py as a subprocess without passing --history-file
therefore pollutes the user's actual snapshot history with fixture
junk — silently, across every pytest run.

This is a source-level lint (same style as the praise-word lint and
the locales key-parity tests): between one build_html.py invocation and
the next (comment lines excluded), a --history-file flag must appear,
so every call site is individually isolated — one flagged invocation
cannot compensate for an unflagged one elsewhere in the file.
"""
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# The path-join form every subprocess call site uses, e.g.
#   str(skill_dir / "scripts" / "build_html.py")
#   str(SCRIPTS_DIR / "build_html.py")
_INVOCATION = '/ "build_html.py"'


def _strip_comment_lines(src):
    return "\n".join(
        line for line in src.splitlines()
        if not line.lstrip().startswith("#")
    )


class HistoryIsolationLintTests(unittest.TestCase):
    def test_every_build_html_subprocess_passes_history_file(self):
        offenders = []
        for path in sorted(TESTS_DIR.glob("*.py")):
            if path.name == Path(__file__).name:
                continue
            src = _strip_comment_lines(path.read_text())
            if _INVOCATION not in src:
                continue
            # Segment i spans from invocation i to invocation i+1 (or EOF).
            # Each segment must carry its own --history-file, so the check
            # is per call site, not a file-wide count. A helper that takes
            # the flag via *extra (smoke_test.py) still passes: its single
            # invocation's segment runs to EOF and contains the call sites.
            segments = src.split(_INVOCATION)[1:]
            missing = sum(1 for seg in segments if "--history-file" not in seg)
            if missing:
                offenders.append(
                    f"{path.name}: {missing} of {len(segments)} build_html.py "
                    "invocation(s) not followed by --history-file"
                )
        self.assertEqual(
            offenders, [],
            "these test files run build_html.py without isolating the trend "
            "snapshot; every call must pass --history-file to a temp path, or "
            "SELF builds append junk to the user's real autopsy-history.jsonl:\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
