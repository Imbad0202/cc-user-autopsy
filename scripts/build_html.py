"""
cc-user-autopsy Step 4: render final HTML report.
Editorial-clinical design: paper-tone background, Fraunces serif + JetBrains Mono,
diagnostic-note chrome. Not a dashboard — a typeset diagnostic letter.

This file is the CLI entry point.  All rendering logic lives in report_render.py.
"""
import argparse
import json
import sys
from pathlib import Path

from locales import STRINGS

try:
    from scripts import report_render
except ImportError:
    import report_render  # type: ignore[no-redef]

# Re-export helpers that tests import directly via `build_html.<name>`.
from report_render import (  # noqa: F401  (re-exported for test compatibility)
    _build_activity_panel,
    _build_models_chart,
    _category_for,
    _fmt_cost,
    _load_chart_layout_js,
    _matches_allowlist,
    display_project,
    display_url,
    esc,
    fmt,
    inline_md,
    json_for_script,
    md_to_html,
    prettify_model,
    sanitize_url,
    score_band,
    JS_KEY_PREFIXES,
    PAGE_TEMPLATE,
    SAFE_URL_SCHEMES,
    SAFE_URL_SCHEMES_WITH_MAILTO,
    WEEKDAY_LABELS,
)


def _load_narrative(locale: str):
    """Return the narrative module for the given locale."""
    if locale == "zh_TW":
        try:
            from scripts import narrative_zh as narrative
        except ImportError:
            import narrative_zh as narrative  # type: ignore[no-redef]
    else:
        try:
            from scripts import narrative_en as narrative
        except ImportError:
            import narrative_en as narrative  # type: ignore[no-redef]
    return narrative


def load_json_or_warn(path_arg, label, default):
    """Load a JSON file if the path resolves. Warn on parse error, return default."""
    if not path_arg:
        return default
    p = Path(path_arg).expanduser()
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except Exception as e:
        print(f"warn: failed to parse {label} file: {e}", file=sys.stderr)
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--samples", required=True)
    ap.add_argument("--peer-review", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--audience", choices=["self", "hr"], default="self",
                    help="'self' for the diagnostic letter (default); 'hr' re-orders sections "
                    "to lead with a portfolio-style profile card for hiring managers.")
    ap.add_argument("--artifacts", default=None,
                    help="Optional JSON file: list of public artifacts. Each entry "
                    "{name, url, description}. Appears in HR layout only.")
    ap.add_argument("--public-projects", default=None,
                    help="HR mode only. JSON file with allowlist of project names "
                    "to show verbatim, plus optional category overrides for "
                    "redacted projects. Schema: "
                    "{public_projects: [name,...], category_overrides: {name: label}}. "
                    "Without this flag, ALL projects are anonymised in HR mode.")
    ap.add_argument("--profile", default=None,
                    help="Optional JSON file with identity info to put in the header. "
                    "Schema: {name, role, location, tagline, contact: {email, github, "
                    "twitter, website}, links: [{label, url}]}. HR version shows a full "
                    "letterhead; self version shows a subtle signature.")
    ap.add_argument(
        "--locale", choices=sorted(STRINGS.keys()), default="en",
        help="Output language for chrome and prose. en = canonical English; "
             "zh_TW = Traditional Chinese (peer-review prose must be rewritten "
             "natively, see SKILL.md Step 4.5).",
    )
    args = ap.parse_args()

    data = json.loads(Path(args.input).expanduser().read_text())
    samples = json.loads(Path(args.samples).expanduser().read_text())
    pr_md = ""
    if args.peer_review:
        p = Path(args.peer_review).expanduser()
        if p.exists():
            pr_md = p.read_text()

    artifacts_list = load_json_or_warn(args.artifacts, "artifacts", [])
    profile_info = load_json_or_warn(args.profile, "profile", {})
    allowlist = load_json_or_warn(args.public_projects, "public-projects", {})
    public_set = set(allowlist.get("public_projects", []))
    category_map = allowlist.get("category_overrides", {}) or {}

    narrative = _load_narrative(args.locale)

    html_out = report_render.render(
        analysis=data,
        samples_data=samples,
        peer_review_md=pr_md,
        locale=args.locale,
        audience=args.audience,
        narrative=narrative,
        profile_info=profile_info,
        artifacts_list=artifacts_list,
        public_set=public_set,
        category_map=category_map,
    )

    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out)
    print(f"wrote {out} ({out.stat().st_size} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
