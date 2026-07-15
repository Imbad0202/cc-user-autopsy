from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DEMO_ROOT = Path("/tmp/cc-autopsy-demo")


def run(*args: str, capture: bool = False) -> subprocess.CompletedProcess | None:
    """Run a subprocess. With capture=True, also captures+returns stdout/
    stderr (still echoed live) so callers can assert on build-time warnings
    (e.g. the praise-word lint) without losing the live pass-through a smoke
    test benefits from when run interactively."""
    if not capture:
        subprocess.run(args, check=True, cwd=REPO_ROOT)
        return None
    proc = subprocess.run(args, check=True, cwd=REPO_ROOT,
                          capture_output=True, text=True)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    return proc


def main() -> None:
    if DEMO_ROOT.exists():
        shutil.rmtree(DEMO_ROOT)

    run(sys.executable, str(SCRIPTS_DIR / "generate_demo_data.py"))

    codex_rows = DEMO_ROOT / "codex-rows.jsonl"
    grok_rows = DEMO_ROOT / "grok-rows.jsonl"
    anti_rows = DEMO_ROOT / "anti-rows.jsonl"
    run(
        sys.executable,
        str(SCRIPTS_DIR / "scan_codex.py"),
        "--sessions-dir",
        str(DEMO_ROOT / "codex-sessions"),
        "--output",
        str(codex_rows),
    )
    run(
        sys.executable,
        str(SCRIPTS_DIR / "scan_grok.py"),
        "--sessions-dir",
        str(DEMO_ROOT / "grok-sessions"),
        "--output",
        str(grok_rows),
    )
    run(
        sys.executable,
        str(SCRIPTS_DIR / "scan_antigravity.py"),
        "--conversations-dir",
        str(DEMO_ROOT / "antigravity-conversations"),
        "--output",
        str(anti_rows),
    )

    run(
        sys.executable,
        str(SCRIPTS_DIR / "aggregate.py"),
        "--data-dir",
        str(DEMO_ROOT / "usage-data"),
        "--cross-llm-rows",
        str(codex_rows),
        "--cross-llm-rows",
        str(grok_rows),
        "--cross-llm-rows",
        str(anti_rows),
        "--output",
        str(DEMO_ROOT / "analysis-data.json"),
    )
    run(
        sys.executable,
        str(SCRIPTS_DIR / "sample_sessions.py"),
        "--input",
        str(DEMO_ROOT / "analysis-data.json"),
        "--output",
        str(DEMO_ROOT / "samples.json"),
        "--projects-dir",
        str(DEMO_ROOT / "projects"),
    )

    analysis_path = DEMO_ROOT / "analysis-data.json"
    samples_path = DEMO_ROOT / "samples.json"

    analysis = json.loads(analysis_path.read_text())
    hostile_label = "</script><script>window.__bad = true</script>"
    analysis["aggregates"]["tools"]["totals"][hostile_label] = 999
    first_project = next(iter(analysis["aggregates"]["projects"].values()))
    first_project["label"] = "<img src=x onerror=alert(1)>"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2))

    samples = json.loads(samples_path.read_text())
    first_sample = next(iter(samples.values()))
    first_sample["meta"]["brief_summary"] = "<script>alert(1)</script> summary"
    first_sample["meta"]["first_prompt"] = 'prompt with "quotes" and <b>html</b>'
    samples_path.write_text(json.dumps(samples, ensure_ascii=False, indent=2))

    profile_path = DEMO_ROOT / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "name": '<img src=x onerror=alert("name")>',
                "role": "AI workflow reviewer",
                "location": "Taipei",
                "tagline": "<b>unsafe tagline</b>",
                "contact": {
                    "email": "tester@example.com",
                    "website": "javascript:alert(1)",
                },
                "links": [{"label": "<script>bad()</script>", "url": "javascript:alert(2)"}],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    artifacts_path = DEMO_ROOT / "artifacts.json"
    artifacts_path.write_text(
        json.dumps(
            [
                {
                    "name": "<svg onload=alert(1)>",
                    "url": "javascript:alert(3)",
                    "description": "<b>artifact</b>",
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
    )

    peer_review_path = DEMO_ROOT / "peer-review.md"
    peer_review_path.write_text(
        "### Three things you are doing well\n\n"
        "1. **Unsafe input** — <script>alert(1)</script>\n"
    )

    narration_path = DEMO_ROOT / "ledger-narration.md"
    narration_path.write_text(
        "# opening\nDemo opening sentence <script>alert('n')</script>.\n"
        "# output-ledger\nDemo output claim.\n"
        "# team-ledger\nDemo team claim, an impressive quarter overall.\n"
        "# leak-ledger\n"
        "Biggest leak this period: repeated instructions cost 420 tokens/week"
        " <script>alert('leak')</script>.\n"
        "Body prose backing the claim goes here.\n",
        encoding="utf-8",
    )
    history_path = DEMO_ROOT / "history.jsonl"

    output_path = DEMO_ROOT / "smoke.html"
    def run_build(audience, output, extra=(), capture=False):
        return run(
            sys.executable,
            str(SCRIPTS_DIR / "build_html.py"),
            "--input",
            str(analysis_path),
            "--samples",
            str(samples_path),
            "--peer-review",
            str(peer_review_path),
            "--audience",
            audience,
            "--profile",
            str(profile_path),
            "--artifacts",
            str(artifacts_path),
            "--output",
            str(output),
            *extra,
            capture=capture,
        )

    # Seed history with the demo's 3 synthetic trend snapshots BEFORE the
    # SELF build so the trend ledger unlocks (_TREND_MIN_SNAPSHOTS == 3);
    # the SELF build below then appends a 4th line via the snapshot hook.
    shutil.copy(DEMO_ROOT / "autopsy-history.jsonl", history_path)

    # Self audit shows verbatim project labels so XSS escaping is exercised
    # end-to-end on the hostile payloads injected above. Captured so we can
    # assert the praise-word lint fired on the "impressive" seeded above.
    self_output = DEMO_ROOT / "smoke-self.html"
    self_build = run_build(
        "self",
        self_output,
        extra=(
            "--ledger-narration",
            str(narration_path),
            "--history-file",
            str(history_path),
        ),
        capture=True,
    )
    assert "praise-word lint" in self_build.stderr, (
        "SELF build stderr must warn about the seeded praise word "
        "('impressive' in the team-ledger book)"
    )
    html = self_output.read_text()
    assert "fonts.googleapis.com" not in html
    assert "cdn.jsdelivr.net" not in html
    assert "javascript:alert" not in html
    assert "</script><script>window.__bad = true</script>" not in html
    assert "\\u003cimg src=x onerror=alert(" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert '&lt;img src=x onerror=alert(&quot;name&quot;)&gt;' in html

    # HR build without an allowlist must redact hostile project labels to
    # the generic placeholder — verify the raw payload doesn't reach HTML,
    # while artifact sanitisation (javascript: URLs → #) still runs.
    run_build("hr", output_path, extra=("--history-file", str(history_path)))
    hr_html = output_path.read_text()
    assert "<img src=x onerror=alert(1)>" not in hr_html
    assert "\\u003cimg src=x onerror=alert(1)" not in hr_html
    assert "javascript:alert" not in hr_html
    assert 'href="#"' in hr_html

    # --- Phase 3 recruiter rebuild invariants ---
    assert 'id="hr-output"' in hr_html, "HR build missing output ledger"
    assert 'id="scores"' not in hr_html, "HR must not render the scoring grid"
    assert 'id="peer-review-section"' not in hr_html, "HR must not render peer review"
    assert 'id="trends"' not in hr_html, "HR must not render trend charts"
    assert "legacy-migration" not in hr_html, (
        "non-allowlisted demo project name leaked into HR output")

    # --- Phase 3 trend ledger + badges: seeded 3-snapshot history unlocks
    # the trend book on SELF; badges are earned-only and HR-only ---
    self_html = html
    assert 'id="ledger-trend"' in self_html, "SELF build missing trend ledger"
    assert '<svg class="c-spark"' in self_html, "trend sparklines missing"
    assert 'id="ledger-trend"' not in hr_html, "HR must not render the trend ledger"
    # badge section in HR: earned-only. Demo earns >=1 badge (test_demo_data
    # pins the exact set), so the section must be present.
    assert 'id="badges"' in hr_html, "HR build missing earned badges section"
    assert 'id="badges"' not in self_html, "badge cards are external-only"

    # --- V5 ledger: SELF renders the exhibit skeleton, HR must not ---
    assert 'id="ledger-opening"' in self_html, "SELF build missing ledger-opening"
    assert 'id="ledger-output"' in self_html, "SELF build missing ledger-output"
    assert 'id="ledger-team"' in self_html, "SELF build missing ledger-team"
    assert 'class="c-exhibit"' in self_html, "SELF build missing ledger exhibits"
    assert 'id="ledger-' not in hr_html, "HR build must not render ledger sections"
    assert 'class="c-exhibit"' not in hr_html, "HR build must not render ledger exhibits"

    # --- V5 leak ledger (Task 12): SELF renders it, XSS payload never raw,
    # HR must not render the section OR the blind-spot callout element ---
    assert 'id="ledger-leaks"' in self_html, "SELF build missing leak ledger"
    assert "<script>alert('leak')</script>" not in self_html, (
        "leak-ledger narration XSS payload must be escaped, not executed"
    )
    assert 'id="ledger-leaks"' not in hr_html, "HR build must not render the leak ledger"
    assert 'class="c-blindspot"' not in hr_html, (
        "HR build must not render blind-spot callout elements"
    )
    assert 'class="c-blindspot"' in self_html, (
        "SELF build must render blind-spot callout elements"
    )

    # cross-LLM prompt text must never reach ANY output (spec §4). The demo
    # data plants GROK_PRIVATE_MARKER both as a one-off prompt AND inside a
    # cross-only (codex+grok, no Claude) repeat pattern engineered to
    # survive the top-5 pattern cap (DEMO_CROSS_ONLY_INSTRUCTION) — so
    # these assertions exercise the real exemplar leak path, not just
    # prompts that never qualified for storage.
    for name, html_text in (("self", self_html), ("hr", hr_html)):
        assert "GROK_PRIVATE_MARKER" not in html_text, (
            f"{name} build leaked grok prompt text"
        )
    analysis_text = analysis_path.read_text()
    assert "GROK_PRIVATE_MARKER" not in analysis_text, (
        "analysis-data.json leaked grok prompt text (blind-spot exemplar?)"
    )
    bs1_patterns = (json.loads(analysis_text).get("blind_spots", {})
                    .get("repeated_instructions", {})
                    .get("metrics", {}).get("patterns", []))
    cross_only = [p for p in bs1_patterns if "claude" not in p["sources"]]
    assert cross_only, (
        "expected the engineered cross-only pattern in the stored top 5; "
        "the privacy sentinel above would otherwise pass vacuously"
    )
    assert all(p["exemplar"] == "" for p in cross_only), (
        "cross-only pattern stored a non-empty exemplar"
    )

    # narration is escaped, not executed
    assert "<script>alert('n')</script>" not in self_html

    # snapshot hook: history was seeded with 3 demo snapshots, SELF appended
    # exactly one more line, HR appended none.
    history_lines = history_path.read_text().strip().splitlines()
    assert len(history_lines) == 4, f"expected 4 snapshot lines, got {len(history_lines)}"

    node = shutil.which("node")
    if node:
        script_path = DEMO_ROOT / "smoke.js"
        inside_script = False
        script_lines = []
        for line in html.splitlines():
            if line.strip() == "<script>":
                inside_script = True
                continue
            if line.strip() == "</script>":
                inside_script = False
                continue
            if inside_script:
                script_lines.append(line)
        script_path.write_text("\n".join(script_lines))
        run(node, "--check", str(script_path))
        # Run pure JS layout helper unit tests (node:test, no deps).
        run(node, "--test", str(REPO_ROOT / "tests" / "chart_layout.test.mjs"))

    print(f"smoke test passed: {output_path}")


if __name__ == "__main__":
    main()
