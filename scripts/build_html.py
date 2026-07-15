"""
cc-user-autopsy Step 4: render final HTML report.
Editorial-clinical design: paper-tone background, Fraunces serif + JetBrains Mono,
diagnostic-note chrome. Not a dashboard — a typeset diagnostic letter.

This file is the CLI entry point.  All rendering logic lives in report_render.py.
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from locales import STRINGS

try:
    from scripts import report_render
except ImportError:
    import report_render  # type: ignore[no-redef]

try:
    from scripts.praise_lint import find_praise
except ImportError:
    from praise_lint import find_praise  # type: ignore[no-redef]

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
    # Writer-side backstop: a build running under pytest (including
    # subprocess-spawned ones, which inherit PYTEST_CURRENT_TEST) must never
    # append to the real per-user snapshot file. Tests that exercise the
    # append pass an explicit temp --history-file, which stays writable;
    # tests/test_history_isolation.py lints the call sites, this guards
    # everything the lint can't see.
    if "PYTEST_CURRENT_TEST" in os.environ:
        try:
            is_default = (Path(history_path).expanduser().resolve()
                          == DEFAULT_HISTORY_FILE.resolve())
        except Exception as exc:
            # Unresolvable path (symlink loop → OSError/RuntimeError,
            # embedded null byte → ValueError, ...). Can't prove it isn't
            # the default file, so fail closed: skip, never fail the build.
            print("warning: skipped history snapshot append under pytest "
                  f"(could not resolve path: {exc})", file=sys.stderr)
            return
        if is_default:
            print("warning: skipped history snapshot append to the default "
                  "path under pytest", file=sys.stderr)
            return
    try:
        # Field extraction lives in report_render.snapshot_entry — the SAME
        # mapping the trend ledger's "This run" column reads — so the
        # recorded snapshot and the rendered current values cannot drift.
        entry = {
            "date": date.today().isoformat(),
            "schema_version": 1,
            **report_render.snapshot_entry(analysis),
        }
        path = Path(history_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        # spec: append failure warns, never fails the build
        print(f"warning: could not append history snapshot: {exc}",
              file=sys.stderr)


def read_history_snapshots(history_path):
    """Load trend snapshots for the trend ledger (Phase 3).

    Tolerates corrupt lines (spec §7: skip on read). Entries are deduped
    by date — the LAST line for a given date wins, so re-running a report
    the same day doesn't fake trend progress — and returned sorted
    ascending by date. Entries without a parseable ISO date are skipped.

    Also skips entries that are syntactically valid JSON dicts with a good
    date but carry wrong-typed containers (e.g. `"ledger": [1]` instead of
    a dict) — those pass a top-level-dict + ISO-date check but crash
    downstream readers like report_render._entry_trend_values, which call
    `.get()` on `ledger`/`badges`/`scores` assuming their documented shapes
    (dict/list/dict respectively).
    """
    p = Path(history_path).expanduser()
    if not p.exists():
        return []
    by_date = {}
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"warn: could not read history file: {exc}", file=sys.stderr)
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        d = entry.get("date")
        if not isinstance(d, str):
            continue
        try:
            date.fromisoformat(d)
        except ValueError:
            continue
        if "ledger" in entry and not isinstance(entry["ledger"], dict):
            continue
        if "badges" in entry and not isinstance(entry["badges"], list):
            continue
        if "scores" in entry and not isinstance(entry["scores"], dict):
            continue
        by_date[d] = entry
    return [by_date[d] for d in sorted(by_date)]


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

    for label, md in (("peer-review", pr_md),
                      ("ledger-narration", ledger_narration_md),
                      ("try-this", try_this_md),
                      ("case-study", case_study_md)):
        hits = find_praise(md)
        if hits:
            words = ", ".join(f"{h['word']}×{h['count']}" for h in hits[:5])
            print(f"warning: praise-word lint: {label} contains praise "
                  f"vocabulary ({words}) — audit discipline wants numbers "
                  f"before adjectives", file=sys.stderr)

    artifacts_list = load_json_or_warn(args.artifacts, "artifacts", [])
    profile_info = load_json_or_warn(args.profile, "profile", {})
    allowlist = load_json_or_warn(args.public_projects, "public-projects", {})
    public_set = set(allowlist.get("public_projects", []))
    category_map = allowlist.get("category_overrides", {}) or {}

    narrative = _load_narrative(args.locale)

    # Read before append_history_snapshot() runs below, so "last run" in the
    # report is genuinely the previous build, not this one.
    history_entries = read_history_snapshots(Path(args.history_file))

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
        history_entries=history_entries,
    )

    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out)
    print(f"wrote {out} ({out.stat().st_size} bytes)", file=sys.stderr)

    append_history_snapshot(Path(args.history_file), data, args.audience)


if __name__ == "__main__":
    main()
