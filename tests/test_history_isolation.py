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
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
import build_html  # noqa: E402

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
            # is per call site, not a file-wide count. Helper indirection
            # (smoke_test.py's run_build) is lexically invisible here — the
            # helper embeds the flag itself, and the runtime backstop tests
            # below cover whatever this source lint can't see.
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


@contextlib.contextmanager
def _forced_pytest_env():
    """Guarantee PYTEST_CURRENT_TEST is set so the runtime tests below also
    exercise the guard when run via plain unittest (not just pytest)."""
    old = os.environ.get("PYTEST_CURRENT_TEST")
    os.environ["PYTEST_CURRENT_TEST"] = "test_history_isolation (forced)"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("PYTEST_CURRENT_TEST", None)
        else:
            os.environ["PYTEST_CURRENT_TEST"] = old


class HistoryBackstopRuntimeTests(unittest.TestCase):
    """Runtime coverage of the writer-side backstop in
    build_html.append_history_snapshot — the layer that catches what the
    source lint above can't see (call sites reached through helpers)."""

    def _append(self, history_path):
        stderr = io.StringIO()
        with _forced_pytest_env(), contextlib.redirect_stderr(stderr):
            build_html.append_history_snapshot(history_path, {}, "self")
        return stderr.getvalue()

    def test_default_path_is_skipped_under_pytest(self):
        # DEFAULT_HISTORY_FILE is patched to a temp path so that even a
        # BROKEN guard cannot touch the user's real snapshot file.
        with tempfile.TemporaryDirectory() as tmp:
            fake_default = Path(tmp) / "autopsy-history.jsonl"
            old_default = build_html.DEFAULT_HISTORY_FILE
            build_html.DEFAULT_HISTORY_FILE = fake_default
            try:
                err = self._append(str(fake_default))
            finally:
                build_html.DEFAULT_HISTORY_FILE = old_default
            self.assertFalse(fake_default.exists(),
                             "guard must not write the default path")
            self.assertIn("skipped history snapshot", err)

    def test_explicit_temp_path_stays_writable(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "history.jsonl"
            err = self._append(str(target))
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1, err)
            entry = json.loads(lines[0])
            self.assertEqual(entry.get("schema_version"), 1)

    def test_unresolvable_path_never_raises(self):
        # A symlink loop makes Path.resolve() raise (OSError or, on older
        # Pythons, RuntimeError). append_history_snapshot's contract is
        # "never fails the build": the guard must fail closed — skip with
        # a warning — instead of letting the exception escape.
        with tempfile.TemporaryDirectory() as tmp:
            loop = Path(tmp) / "loop"
            loop.symlink_to(loop)
            target = loop / "history.jsonl"
            err = self._append(str(target))  # must not raise
            self.assertIn("skipped history snapshot", err)


if __name__ == "__main__":
    unittest.main()
