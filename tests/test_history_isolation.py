"""Guard: no test may let build_html.py write to the user's REAL
~/.claude/usage-data/autopsy-history.jsonl.

build_html.py appends a trend snapshot to --history-file (default:
the real per-user path) on every successful SELF build. Any test that
drives build_html.py as a subprocess without passing --history-file
therefore pollutes the user's actual snapshot history with fixture
junk — silently, across every pytest run.

This is a source-level lint (same style as the praise-word lint and
the locales key-parity tests): every subprocess invocation of
build_html.py in tests/ must pass --history-file at least as many
times as it references the script.
"""
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# The path-join form every subprocess call site uses, e.g.
#   str(skill_dir / "scripts" / "build_html.py")
#   str(SCRIPTS_DIR / "build_html.py")
_INVOCATION = '/ "build_html.py"'


class HistoryIsolationLintTests(unittest.TestCase):
    def test_every_build_html_subprocess_passes_history_file(self):
        offenders = []
        for path in sorted(TESTS_DIR.glob("*.py")):
            if path.name == Path(__file__).name:
                continue
            src = path.read_text()
            invocations = src.count(_INVOCATION)
            if not invocations:
                continue
            isolated = src.count("--history-file")
            if isolated < invocations:
                offenders.append(
                    f"{path.name}: {invocations} build_html.py invocation(s), "
                    f"only {isolated} --history-file flag(s)"
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
