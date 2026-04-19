"""Demo data must exercise the same fields the real scanner reads, otherwise
the example HTML shows zeros where the user's report shows real numbers and
visual-regression checks against the example are useless."""
import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _regen_demo():
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "generate_demo_data.py")],
        check=True, cwd=REPO_ROOT, capture_output=True,
    )


class DemoTranscriptUsageTests(unittest.TestCase):
    """generate_demo_data.py must emit assistant records with `model` and
    `usage.cache_*` so scan_transcripts.py picks up the same fields it does
    on real data."""

    @classmethod
    def setUpClass(cls):
        _regen_demo()
        cls.projects_dir = Path("/tmp/cc-autopsy-demo/projects")

    def _all_assistant_records(self):
        for proj in self.projects_dir.iterdir():
            if not proj.is_dir():
                continue
            for jsonl in proj.glob("*.jsonl"):
                for line in jsonl.read_text().splitlines():
                    rec = json.loads(line)
                    if rec.get("type") == "assistant":
                        yield rec

    def test_assistant_records_have_model_field(self):
        records = list(self._all_assistant_records())
        with_model = [r for r in records if r.get("message", {}).get("model")]
        self.assertGreater(len(with_model), 0,
                           "no assistant records carry a model field")
        # Real users overwhelmingly have model on every assistant record.
        self.assertGreater(
            len(with_model) / max(1, len(records)), 0.8,
            f"only {len(with_model)}/{len(records)} assistant records have model")

    def test_assistant_usage_includes_cache_tokens(self):
        records = list(self._all_assistant_records())
        with_cache = [
            r for r in records
            if (r.get("message", {}).get("usage", {}) or {}).get("cache_read_input_tokens", 0) > 0
        ]
        self.assertGreater(len(with_cache), 0,
                           "no assistant records have cache_read_input_tokens > 0")

    def test_demo_uses_realistic_model_mix(self):
        """Real heavy users mix opus + sonnet (+ sometimes haiku). Demo
        must reflect that so the favorite-model tile and models chart
        render meaningfully."""
        models = set()
        for r in self._all_assistant_records():
            m = r.get("message", {}).get("model")
            if m:
                models.add(m)
        self.assertGreaterEqual(len(models), 2,
                                f"expected >=2 distinct models in demo, got {models}")


class DemoLabelStressTests(unittest.TestCase):
    """Demo should include at least one extreme-length label per axis the
    layout helpers care about, so visual regression catches truncation
    regressions."""

    @classmethod
    def setUpClass(cls):
        _regen_demo()
        cls.meta_dir = Path("/tmp/cc-autopsy-demo/usage-data/session-meta")

    def test_at_least_one_long_project_path(self):
        """Project bar/chart labels are clipped to 25-28 chars in build_html;
        the demo should include a project whose name reaches that limit so
        we can see how clipping renders."""
        names = set()
        for f in self.meta_dir.glob("*.json"):
            data = json.loads(f.read_text())
            names.add(data.get("project_path", "").split("/")[-1])
        longest = max((len(n) for n in names), default=0)
        self.assertGreaterEqual(longest, 22,
                                f"longest project name only {longest} chars; "
                                "add a long-named project to stress chart labels")


if __name__ == "__main__":
    unittest.main()
