from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DEMO_ROOT = Path("/tmp/cc-autopsy-demo")


def run(*args: str) -> None:
    subprocess.run(args, check=True, cwd=REPO_ROOT)


def main() -> None:
    if DEMO_ROOT.exists():
        shutil.rmtree(DEMO_ROOT)

    run(sys.executable, str(SCRIPTS_DIR / "generate_demo_data.py"))
    run(
        sys.executable,
        str(SCRIPTS_DIR / "aggregate.py"),
        "--data-dir",
        str(DEMO_ROOT / "usage-data"),
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

    output_path = DEMO_ROOT / "smoke.html"
    run(
        sys.executable,
        str(SCRIPTS_DIR / "build_html.py"),
        "--input",
        str(analysis_path),
        "--samples",
        str(samples_path),
        "--peer-review",
        str(peer_review_path),
        "--audience",
        "hr",
        "--profile",
        str(profile_path),
        "--artifacts",
        str(artifacts_path),
        "--output",
        str(output_path),
    )

    html = output_path.read_text()
    assert "fonts.googleapis.com" not in html
    assert "cdn.jsdelivr.net" not in html
    assert "javascript:alert" not in html
    assert "</script><script>window.__bad = true</script>" not in html
    assert "\\u003cimg src=x onerror=alert(" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert '&lt;img src=x onerror=alert(&quot;name&quot;)&gt;' in html
    assert 'href="#"' in html

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

    print(f"smoke test passed: {output_path}")


if __name__ == "__main__":
    main()
