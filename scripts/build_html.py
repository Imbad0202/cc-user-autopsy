"""
cc-user-autopsy Step 4: render final HTML report.
Editorial-clinical design: paper-tone background, Fraunces serif + JetBrains Mono,
diagnostic-note chrome. Not a dashboard — a typeset diagnostic letter.

This file is the CLI entry point.  All rendering logic lives in report_render.py.
"""
import argparse
import json
import sys
from datetime import date
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
    weekday_labels,
)


DEFAULT_HISTORY_FILE = Path.home() / ".claude" / "usage-data" / "autopsy-history.jsonl"


def append_history_snapshot(history_path, analysis, audience):
    """Append a one-line trend snapshot after a successful SELF build.

    The trend ledger (Phase 3) reads this file; it ships day one so
    history starts accumulating immediately. Never fails the build.
    """
    if audience != "self":
        return
    try:
        scores = {}
        for key, val in (analysis.get("scores") or {}).items():
            if isinstance(val, dict) and "score" in val:
                scores[key] = val["score"]
            elif isinstance(val, (int, float)):
                scores[key] = val
        ledger = analysis.get("ledger") or {}
        leaks_items = (ledger.get("leaks") or {}).get("items") or []
        leaks = []
        if isinstance(leaks_items, list):
            for item in leaks_items:
                if not isinstance(item, dict):
                    continue
                leaks.append({
                    "type": item.get("type"),
                    "weekly_cost_usd": item.get("weekly_cost_usd"),
                    "weekly_tokens": item.get("weekly_tokens"),
                    "occurrences": item.get("occurrences"),
                })
        entry = {
            "date": date.today().isoformat(),
            "schema_version": 1,
            "scores": scores,
            "badges": [],
            "ledger": {
                "git_commits": (ledger.get("output") or {}).get("git_commits"),
                "sessions": (analysis.get("meta") or {}).get("total_sessions"),
                "sources_detected": ledger.get("sources_detected") or [],
                "leaks": leaks,
            },
        }
        path = Path(history_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        # spec: append failure warns, never fails the build
        print(f"warning: could not append history snapshot: {exc}",
              file=sys.stderr)


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
    ap.add_argument("--try-this", default=None,
                    help="Optional markdown file with 3-5 'this week try this' "
                    "items. SELF audience only; ignored for HR.")
    ap.add_argument("--case-study", default=None,
                    help="Optional markdown file with the strongest-single-session "
                    "case study block. Rendered for both audiences.")
    ap.add_argument("--ledger-narration", default=None,
                    help="Markdown with # opening / # output-ledger / # team-ledger "
                    "books (SELF only; written by the skill in Step 3).")
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
    ap.add_argument(
        "--history-file", default=str(DEFAULT_HISTORY_FILE),
        help="Trend-snapshot jsonl appended after each successful self build. "
             "Corrupt lines are tolerated on read (Phase 3).",
    )
    args = ap.parse_args()

    data = json.loads(Path(args.input).expanduser().read_text())
    samples = json.loads(Path(args.samples).expanduser().read_text())
    pr_md = ""
    if args.peer_review:
        p = Path(args.peer_review).expanduser()
        if p.exists():
            pr_md = p.read_text()

    try_this_md = ""
    if args.try_this:
        p = Path(args.try_this).expanduser()
        if p.exists():
            try_this_md = p.read_text()

    case_study_md = ""
    if args.case_study:
        p = Path(args.case_study).expanduser()
        if p.exists():
            case_study_md = p.read_text()

    ledger_narration_md = ""
    if args.ledger_narration:
        p = Path(args.ledger_narration).expanduser()
        if p.exists():
            ledger_narration_md = p.read_text()

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
        try_this_md=try_this_md,
        case_study_md=case_study_md,
        ledger_narration_md=ledger_narration_md,
    )

    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out)
    print(f"wrote {out} ({out.stat().st_size} bytes)", file=sys.stderr)

    append_history_snapshot(Path(args.history_file), data, args.audience)


if __name__ == "__main__":
    main()
