"""Demo data must exercise the same fields the real scanner reads, otherwise
the example HTML shows zeros where the user's report shows real numbers and
visual-regression checks against the example are useless."""
import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

OUT_DIR = Path("/tmp/cc-autopsy-demo")


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


class CrossLlmDemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _regen_demo()

    def test_codex_demo_tree(self):
        files = list((OUT_DIR / "codex-sessions").glob("*/*/*/rollout-*.jsonl"))
        self.assertGreaterEqual(len(files), 30)
        # at least one file must span multiple days (resumed session)
        from scripts.scan_codex import scan_one
        multi = 0
        for f in files:
            row, errors = scan_one(f)
            self.assertIsNotNone(row, f)
            self.assertEqual(errors, 0, f)
            if row["segments"] and len(row["segments"]) > 1:
                multi += 1
        self.assertGreaterEqual(multi, 1)

    def test_grok_demo_tree_contains_xss_marker(self):
        hists = list((OUT_DIR / "grok-sessions").glob("*/prompt_history.jsonl"))
        self.assertGreaterEqual(len(hists), 2)
        blob = "".join(h.read_text() for h in hists)
        self.assertIn("GROK_PRIVATE_MARKER", blob)

    def test_antigravity_demo_files(self):
        pbs = list((OUT_DIR / "antigravity-conversations").glob("*.pb"))
        self.assertGreaterEqual(len(pbs), 5)


_full_pipeline_cache = None


def _run_full_pipeline():
    """Regenerate the demo tree and run the real pipeline (scan_transcripts +
    scan_codex + scan_grok + aggregate.py, all via subprocess, same as
    tests/smoke_test.py) over it. Returns the parsed analysis-data.json.

    Both blind-spot test classes below call this from their own
    setUpClass, so without caching the (expensive) pipeline runs twice per
    test session. Results are deterministic (seed=20260715 demo data), so
    the first result is cached at module level and reused for every
    subsequent call — the pipeline itself still only runs once."""
    global _full_pipeline_cache
    if _full_pipeline_cache is not None:
        return _full_pipeline_cache

    _regen_demo()
    transcript_rows = OUT_DIR / "transcript-rows.jsonl"
    codex_rows = OUT_DIR / "codex-rows.jsonl"
    grok_rows = OUT_DIR / "grok-rows.jsonl"
    analysis_path = OUT_DIR / "analysis-data.json"

    def run(*args):
        subprocess.run([sys.executable, *args], check=True,
                       cwd=REPO_ROOT, capture_output=True)

    run(str(REPO_ROOT / "scripts" / "scan_transcripts.py"),
        "--projects-dir", str(OUT_DIR / "projects"),
        "--output", str(transcript_rows))
    run(str(REPO_ROOT / "scripts" / "scan_codex.py"),
        "--sessions-dir", str(OUT_DIR / "codex-sessions"),
        "--output", str(codex_rows))
    run(str(REPO_ROOT / "scripts" / "scan_grok.py"),
        "--sessions-dir", str(OUT_DIR / "grok-sessions"),
        "--output", str(grok_rows))
    run(str(REPO_ROOT / "scripts" / "aggregate.py"),
        "--transcript-rows", str(transcript_rows),
        "--data-dir", str(OUT_DIR / "usage-data"),
        "--cross-llm-rows", str(codex_rows),
        "--cross-llm-rows", str(grok_rows),
        "--output", str(analysis_path))

    _full_pipeline_cache = json.loads(analysis_path.read_text())
    return _full_pipeline_cache


class BlindSpotDemoGateTests(unittest.TestCase):
    """Spec §11's 'hard test on demo fixtures' for the blind-spot engine.

    Runs the real pipeline (scan_transcripts + scan_codex + scan_grok +
    aggregate.py, all via subprocess, same as tests/smoke_test.py) over the
    generated demo tree and asserts the three engineered gates (BS#1
    repeated-instruction tax, BS#2 sunk-cost pairs, BS#4 graveyard) pass
    deterministically, and that they produce non-empty leak-ledger items.

    #3/#5/#6/#7 are NOT gate-asserted here (see class docstring on
    WellFormedBlindSpotBlockTests below) — those heuristics run on
    incidental (unseeded-by-index) demo data and asserting their gates
    would make this suite flaky.
    """

    @classmethod
    def setUpClass(cls):
        cls.analysis = _run_full_pipeline()
        cls.blind_spots = cls.analysis["blind_spots"]

    def test_repeated_instructions_gate_passes(self):
        bs1 = self.blind_spots["repeated_instructions"]
        self.assertTrue(bs1["gate_passed"], bs1.get("reason"))

    def test_engineered_cross_tool_pattern_survives_top5_cap(self):
        # The injected pattern spans Claude + Codex + Grok and must outrank
        # the incidental Claude-only patterns from the 12-string random
        # pool, or the demo report never exercises the cross-tool fix-text
        # path (top-5 cap would discard it).
        bs1 = self.blind_spots["repeated_instructions"]
        multi = [p for p in bs1["metrics"]["patterns"]
                 if len(p.get("sources", [])) > 1]
        self.assertTrue(multi, "no cross-tool pattern in the top 5")
        self.assertIn("codex", multi[0]["sources"])
        self.assertIn("grok", multi[0]["sources"])

    def test_sunk_cost_gate_passes(self):
        bs2 = self.blind_spots["sunk_cost"]
        self.assertTrue(bs2["gate_passed"], bs2.get("reason"))
        self.assertFalse(bs2["suppressed_by_guard"],
                         "sunk_cost gate must not be suppressed by the "
                         "counterexample guard on demo data")
        self.assertGreaterEqual(bs2["n"], 3)

    def test_graveyard_gate_passes(self):
        bs4 = self.blind_spots["graveyard"]
        self.assertTrue(bs4["gate_passed"], bs4.get("reason"))
        self.assertGreaterEqual(bs4["n"], 2)

    def test_leak_ledger_items_non_empty(self):
        items = self.analysis["ledger"]["leaks"]["items"]
        self.assertTrue(items, "ledger.leaks.items must be non-empty when "
                               "BS#1/#2 gates pass")


class HistorySnapshotsAndBadgesTests(unittest.TestCase):
    """Phase 3: the demo must emit a readable trend-snapshot file and the
    aggregate pipeline must deterministically earn >=1 badge on it, or the
    trend ledger / badges section never render on demo data (assets/
    example-output*.html and the smoke test both depend on this)."""

    @classmethod
    def setUpClass(cls):
        cls.analysis = _run_full_pipeline()

    def test_history_snapshots_written_and_readable(self):
        hist = OUT_DIR / "autopsy-history.jsonl"
        self.assertTrue(hist.exists())
        from build_html import read_history_snapshots
        entries = read_history_snapshots(hist)
        self.assertEqual(len(entries), 3)
        self.assertEqual([e["date"] for e in entries], sorted(e["date"] for e in entries))

    def test_badges_block_present_with_six_items(self):
        badges = self.analysis["badges"]
        self.assertEqual(len(badges["items"]), 6)
        self.assertEqual(badges["standard_version"], "v1.1")

    def test_at_least_one_badge_earned_deterministically(self):
        # Phase 2 lesson: a badge path nobody reaches is a fake sentinel.
        # With random.seed frozen this either always passes or always
        # fails — if it fails, raise the demo's commit density (gen_session)
        # until shipping_cadence clears its bar, don't loosen the bar.
        earned = [b["id"] for b in self.analysis["badges"]["items"] if b["earned"]]
        self.assertTrue(earned, "demo data earns zero badges — engineer the fixture")

    def test_earned_badge_set_is_pinned(self):
        # Verified empirically across repeated regenerations under
        # random.seed(20260715) (see generate_demo_data.main): the demo
        # deterministically earns exactly these three badges. A different
        # set here means either the seed, the demo fixtures, or a badge
        # bar changed — investigate before loosening this assertion.
        earned = sorted(b["id"] for b in self.analysis["badges"]["items"] if b["earned"])
        self.assertEqual(earned, ["root_cause", "shipping_cadence", "token_efficiency"])


class WellFormedBlindSpotBlockTests(unittest.TestCase):
    """#3 (switch tax), #5 (habit drift), #6 (ask-vs-ship), #7 (interrupt
    win-rate) run on the same incidental (non-index-forced) demo data as
    every other heuristic that isn't Task 12's fixture target. Their gates
    are legitimately data-dependent and unseeded by index, so asserting
    gate_passed on them would flake across otherwise-valid regenerations.
    This class only checks the block is well-formed (keys present, no
    KeyError), which the deterministic seed=20260715 draw does guarantee."""

    @classmethod
    def setUpClass(cls):
        cls.blind_spots = _run_full_pipeline()["blind_spots"]

    def test_all_seven_heuristics_present_and_well_formed(self):
        expected_ids = {
            "repeated_instructions", "sunk_cost", "switch_tax", "graveyard",
            "habit_drift", "ask_vs_ship", "interrupt_win_rate",
        }
        self.assertIn("schema_version", self.blind_spots)
        heuristic_blocks = {k: v for k, v in self.blind_spots.items()
                            if k != "schema_version"}
        self.assertEqual(set(heuristic_blocks.keys()), expected_ids)
        for bs_id, block in heuristic_blocks.items():
            self.assertEqual(block["id"], bs_id)
            self.assertIn("gate_passed", block)
            self.assertIn("suppressed_by_guard", block)
            self.assertIn("n", block)
            self.assertIn("metrics", block)
            self.assertIn("reason", block)
            self.assertIsInstance(block["gate_passed"], bool)


if __name__ == "__main__":
    unittest.main()
