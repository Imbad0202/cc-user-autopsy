"""
HTML render layer for cc-user-autopsy reports.

This module owns the PAGE_TEMPLATE constant, all HTML-building helpers, and
the single public entry point ``render()``.  It has no dependency on argparse
or the filesystem — callers (build_html.py) are responsible for loading data
and picking the locale narrative module, then passing structured inputs here.
"""
import html
import json
import re
import string
from datetime import date, timedelta
from itertools import count
from pathlib import Path
from urllib.parse import urlparse

from locales import STRINGS, t


_WEEKDAY_KEYS = ["wd_mon", "wd_tue", "wd_wed", "wd_thu", "wd_fri", "wd_sat", "wd_sun"]


def weekday_labels(locale: str):
    """Return localized weekday labels (Mon–Sun)."""
    return [t(locale, k) for k in _WEEKDAY_KEYS]

# Keys whose name starts with one of these prefixes are exposed to inline JS
# via the `I18N` const.  Naming convention is the contract: name a chart-side
# key `chart_*` or `series_*` and it flows through automatically.
JS_KEY_PREFIXES = ("chart_", "series_")

_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")

def prettify_model(name: str | None) -> str:
    """Convert a raw model identifier to a human-readable display label.

    Rules:
    - None or empty string → empty string.
    - Strip 'claude-' prefix if present.
    - Strip any trailing date suffix matching -YYYYMMDD (generalised).
    - Tokenize on '-': first token is the family name (capitalize it).
      Remaining tokens (version digits, e.g. '4', '7') are joined with '.'
      to form the version string.
    - Known families: opus, sonnet, haiku — all follow <family>-<major>-<minor>.
    - Unknown / non-standard: title-case each token, join with spaces.

    Examples:
        'claude-opus-4-7-20251101' → 'Opus 4.7'
        'claude-sonnet-4-6-20251001' → 'Sonnet 4.6'
        'opus-4-7'                  → 'Opus 4.7'
        'claude-opus'               → 'Opus'
        'unknown-model-x'           → 'Unknown Model X'
        ''                          → ''
        None                        → ''
    """
    if not name:
        return ""
    # Strip claude- prefix
    if name.startswith("claude-"):
        name = name[len("claude-"):]
    # Strip generic date suffix -YYYYMMDD
    name = _DATE_SUFFIX_RE.sub("", name)
    if not name:
        return ""
    tokens = name.split("-")
    family = tokens[0].capitalize()
    version_tokens = tokens[1:]
    if not version_tokens:
        return family
    # Heuristic: if all version tokens are digit strings, join with dots (version).
    if all(tok.isdigit() for tok in version_tokens):
        return f"{family} {'.'.join(version_tokens)}"
    # Fallback: title-case all tokens and join with spaces.
    return " ".join(tok.capitalize() for tok in tokens)


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


def _matches_allowlist(name, public_set):
    """Match on full label or any path-suffix segment — allowlist entries
    can be short repo names (`tw-formal-writing`) and still match a
    two-segment label (`Claude Code Project/tw-formal-writing`)."""
    if name in public_set:
        return True
    tail = name.rsplit("/", 1)[-1]
    return tail in public_set


def _category_for(name, category_map, locale: str = "en"):
    if name in category_map:
        return category_map[name]
    tail = name.rsplit("/", 1)[-1]
    return category_map.get(tail, t(locale, "redacted_project"))


def display_project(name, redact, public_set, category_map, locale: str = "en"):
    """Label for a project under the current audience's privacy rules."""
    if not redact or _matches_allowlist(name, public_set):
        return name.rsplit("/", 1)[-1] if redact else name
    return _category_for(name, category_map, locale)

SAFE_URL_SCHEMES = {"http", "https"}
SAFE_URL_SCHEMES_WITH_MAILTO = SAFE_URL_SCHEMES | {"mailto"}


def _build_activity_panel(activity: dict, locale: str = "en") -> str:
    """Render the Desktop-style Activity overview if present. Empty string if not."""
    if not activity or not activity.get("total_sessions"):
        return ""
    total = activity.get("total_sessions", 0)
    msgs = activity.get("total_messages", 0)
    days = activity.get("active_days", 0)
    cur = activity.get("current_streak", 0)
    lng = activity.get("longest_streak", 0)
    fav = activity.get("favorite_model") or "—"
    cache_c = activity.get("cache_creation_tokens", 0)
    cache_r = activity.get("cache_read_tokens", 0)
    cost = activity.get("api_equivalent_cost_usd", 0) or 0
    models = activity.get("models") or {}
    scoring_pool = activity.get("scoring_pool_sessions")
    full_pool = activity.get("full_pool_sessions")

    # Compact favorite model label
    fav_short = prettify_model(fav) if fav != "—" else "—"

    scope_note = ""
    if scoring_pool is not None and full_pool is not None and full_pool != scoring_pool:
        scope_note = (
            f'<p class="method" style="margin-top:8px">'
            f'Activity metrics count every transcript ({full_pool:,}). '
            f'Scores below use the {scoring_pool:,}-session pool that has Claude Code\'s '
            f'labeled session-meta — partial coverage of your full history.'
            f'</p>'
        )

    cost_tile = ""
    if cost > 0:
        cost_tile = (
            f'  <div class="metric"><div class="n">${_fmt_cost(cost)}</div>'
            f'<div class="lbl">{t(locale, "tile_api_equivalent")}</div></div>\n'
        )

    chart = _build_models_chart(models, locale=locale) if models else ""

    uc = activity.get("usage_characteristics")
    uc_html = ""
    if uc and uc.get("items"):
        header = t(locale, "usage_char_header")
        note = t(locale, "usage_char_note_template").format(
            n_sessions=uc.get("n_sessions", 0),
            since=uc.get("since", ""),
            until=uc.get("until", ""),
        )
        rows = ""
        for item in uc["items"]:
            rows += (
                '<div class="uc-row">'
                f'<span class="pct">{int(item.get("pct", 0))}%</span>'
                '<div class="uc-body">'
                f'<p class="label">{esc(item.get("label", ""))}</p>'
                f'<p class="tip">{esc(item.get("tip", ""))}</p>'
                '</div>'
                '</div>'
            )
        uc_html = (
            '<div class="usage-characteristics">'
            f'<h4 class="uc-header">{esc(header)}</h4>'
            f'<p class="uc-note">{esc(note)}</p>'
            f'<div class="uc-list">{rows}</div>'
            '</div>'
        )

    return f"""
<div class="metrics" style="margin-bottom:16px">
  <div class="metric"><div class="n">{total:,}</div><div class="lbl">{t(locale, "tile_full_sessions")}</div></div>
  <div class="metric"><div class="n">{msgs:,}</div><div class="lbl">{t(locale, "tile_total_messages")}</div></div>
  <div class="metric"><div class="n">{days}</div><div class="lbl">{t(locale, "tile_active_days")}</div></div>
  <div class="metric"><div class="n">{cur}d</div><div class="lbl">{t(locale, "tile_current_streak")}</div></div>
  <div class="metric"><div class="n">{lng}d</div><div class="lbl">{t(locale, "tile_longest_streak")}</div></div>
  <div class="metric"><div class="n">{fmt(cache_r)}</div><div class="lbl">{t(locale, "tile_cache_read")}</div></div>
  <div class="metric"><div class="n">{fmt(cache_c)}</div><div class="lbl">{t(locale, "tile_cache_create")}</div></div>
{cost_tile}  <div class="metric"><div class="n">{esc(fav_short)}</div><div class="lbl">{t(locale, "tile_favorite_model")}</div></div>
</div>
{chart}
{scope_note}
{uc_html}
""".strip()


def _fmt_cost(n: float) -> str:
    """Compact USD formatter — '$12.3k' / '$1.2M'. No fractional dollars
    below $100 to avoid implying precision we don't have."""
    n = float(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return f"{int(round(n)):,}"


def _build_models_chart(models: dict, locale: str = "en") -> str:
    """Stacked horizontal bar showing assistant-message share per model.
    Pure inline SVG — no external dependencies, renders in any static HTML."""
    items = sorted(models.items(), key=lambda kv: -kv[1])
    total = sum(v for _, v in items) or 1
    # Readable colour palette; extra models fall back to grey.
    palette = ["#6b8afd", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#14b8a6", "#94a3b8"]
    # Build the stacked bar as SVG rects — one per model.
    bar_w = 720
    bar_h = 18
    x = 0
    rects = []
    legend = []
    for i, (m, v) in enumerate(items):
        pct = v / total
        w = round(bar_w * pct, 2)
        color = palette[i] if i < len(palette) else "#94a3b8"
        short = prettify_model(m)
        rects.append(
            f'<rect x="{x}" y="0" width="{w}" height="{bar_h}" fill="{color}">'
            f'<title>{esc(short)}: {v:,} messages ({pct*100:.1f}%)</title>'
            f'</rect>'
        )
        legend.append(
            f'<span class="lg-item"><span class="lg-dot" style="background:{color}"></span>'
            f'{esc(short)} <span class="muted">{pct*100:.1f}%</span></span>'
        )
        x += w
    return f"""
<div id="models-chart" style="margin-top:4px">
  <div class="method" style="margin-bottom:6px">{t(locale, "chart_models_label")}</div>
  <svg width="{bar_w}" height="{bar_h}" role="img" aria-label="Models breakdown"
       style="max-width:100%;height:auto;display:block">{''.join(rects)}</svg>
  <div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:10px;font-size:12px">
    {''.join(legend)}
  </div>
</div>
""".strip()


def fmt(n):
    if n is None:
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n >= 1_000_000_000_000:
        return f"{n / 1_000_000_000_000:.1f}T"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    if n == int(n):
        return str(int(n))
    return f"{n:.1f}"


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def json_for_script(value) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _exhibit(no, title, body_html, source_line, locale="en"):
    """Direction-C numbered Exhibit frame: label + title + body + source line.

    Every chart/table in the ledger sections goes through this so each
    visual carries its own provenance (claim-indexed evidence discipline).
    """
    return (
        '<figure class="c-exhibit">'
        '<figcaption class="c-exhibit-head">'
        f'<span class="c-exhibit-no">{t(locale, "ledger_exhibit_label")} '
        f'{int(no)}</span> '
        f'<span class="c-exhibit-t">{esc(title)}</span>'
        '</figcaption>'
        f'{body_html}'
        f'<div class="c-exhibit-src">{t(locale, "ledger_source_prefix")} '
        f'{esc(source_line)}</div>'
        '</figure>'
    )


def _parse_ledger_narration(md: str) -> dict:
    """Split an LLM-authored ledger narration markdown file on `^# ` headings.

    Returns {"opening": str, "output-ledger": str, "team-ledger": str,
    "leak-ledger": str, "trend-ledger": str}; missing sections default to "".
    """
    books = {"opening": "", "output-ledger": "", "team-ledger": "",
             "leak-ledger": "", "trend-ledger": ""}
    current = None
    buf = []
    for line in (md or "").splitlines():
        if line.startswith("# "):
            if current in books:
                books[current] = "\n".join(buf).strip()
            current = line[2:].strip().lower()
            buf = []
        else:
            buf.append(line)
    if current in books:
        books[current] = "\n".join(buf).strip()
    return books


def _first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _rest_lines(text):
    lines = (text or "").splitlines()
    seen_first = False
    out = []
    for line in lines:
        if not seen_first and line.strip():
            seen_first = True
            continue
        if seen_first:
            out.append(line)
    return "\n".join(out).strip()


def _build_opening_band(ledger, narration, locale="en", include_leak_finding=True,
                        include_trend_finding=False):
    """SELF-only opening band: kicker + LLM-written opening sentence, plus a
    numbered-finding list built from the output-ledger / team-ledger /
    leak-ledger / trend-ledger opener claims. Never fabricates prose — an
    empty narration renders numbers-only. Finding numbers only increment for
    books that actually have a first line, so a missing leak-ledger book
    leaves the list at two findings rather than skipping a number.

    include_leak_finding=False suppresses the leak-ledger opener claim even
    when the narration has one: the leak section itself can be gated off
    (no leak data passed a blind-spot gate) while stale/manually-supplied
    narration still contains a "# leak-ledger" book with an opener line —
    rendering that line would assert a leak the report's own leak section
    doesn't support. Output/team opener findings are unaffected.

    include_trend_finding follows the same never-fabricate rule: the trend
    claim only renders when the trend section itself is unlocked (>= 3
    history snapshots), defaulting to False since most runs are locked.
    """
    opening = _first_line(narration.get("opening", ""))
    findings = []
    n = 0
    for book in ("output-ledger", "team-ledger", "leak-ledger", "trend-ledger"):
        if book == "leak-ledger" and not include_leak_finding:
            continue
        if book == "trend-ledger" and not include_trend_finding:
            continue
        claim = _first_line(narration.get(book, ""))
        if claim:
            n += 1
            findings.append(
                '<div class="c-finding">'
                f'<div class="c-finding-no">{n}</div>'
                f'<div class="c-finding-head">{inline_md(claim)}</div>'
                '</div>')
    opening_html = (
        f'<p class="c-finding-head" style="margin-top:14px">{inline_md(opening)}</p>'
        if opening else "")
    win = ledger.get("window") or {}
    period = ""
    if win.get("start") and win.get("end"):
        period = (f'<p class="method">{esc(win["start"])} – {esc(win["end"])}'
                  f' · {int(win.get("days") or 0)}d</p>')
    return (
        '<section class="section" id="ledger-opening">'
        f'<div class="c-kicker">{t(locale, "ledger_opening_kicker")}</div>'
        f'{opening_html}{period}'
        f'{"".join(findings)}'
        '</section>')


def _blindspot_callout(locale, title_key, sentence, detail=None,
                       sentence_html=None):
    """One blind-spot opener callout: gold label chip + title + metric
    sentence + optional escaped detail line (e.g. a repeated-instruction
    exemplar). `sentence` is plain text formatted from a locale template,
    so it is escaped here rather than passed through inline_md.
    `sentence_html` overrides it with pre-escaped markup for the one caller
    (switch tax) that highlights a number inside the sentence."""
    d = f'<div class="c-blindspot-detail">{detail}</div>' if detail else ""
    metric = sentence_html if sentence_html is not None else esc(sentence)
    return ('<div class="c-blindspot">'
            f'<span class="c-blindspot-label">{esc(t(locale, "ledger_blindspot_label"))}</span>'
            f'<strong>{esc(t(locale, title_key))}</strong>'
            f'<div class="c-blindspot-metric">{metric}</div>{d}</div>')


def _goal_category_label(locale, category):
    """Localized display label for a goal-category facet key. The facet
    vocabulary is open-ended (session-meta emits whatever it saw), so only
    the known keys have locale entries; unknown ones fall back to the
    de-underscored key rather than leaking raw snake_case into the report."""
    key = "goal_cat_" + category
    if key in STRINGS[locale]:
        return t(locale, key)
    return category.replace("_", " ")


def _build_output_ledger(ledger, narration, locale="en", exhibit_no=None,
                          blind_spots=None):
    """SELF-only output ledger: action-title head + prose + graveyard opener
    (blind spot #4, when its gate passed) + output metrics exhibit
    (git_commits, git_pushes, sessions_with_commits). Counts only — no
    session IDs or prompt text ever flow through this builder.

    Every book opens with its blind spot: the graveyard callout + exhibit
    render BEFORE the output metrics exhibit, so a passed gate claims the
    earlier exhibit number (numbering is pure order-of-appearance).

    exhibit_no is a shared itertools.count() the caller advances across all
    ledger sections so numbering is pure order-of-appearance (Phase 2
    refactor); a fresh count(1) is used when not supplied, preserving the
    original hard-coded-Exhibit-1 behavior for standalone/legacy callers."""
    if exhibit_no is None:
        exhibit_no = count(1)
    bs = blind_spots or {}
    out = ledger.get("output") or {}
    title = _first_line(narration.get("output-ledger", "")) or t(
        locale, "ledger_output_title")
    prose = _rest_lines(narration.get("output-ledger", ""))
    prose_html = f"<div>{inline_md(prose)}</div>" if prose else ""

    graveyard_html = ""
    bs4 = bs.get("graveyard") or {}
    if bs4.get("gate_passed"):
        callout = _blindspot_callout(
            locale, "blindspot_graveyard_title",
            t(locale, "blindspot_graveyard_template").format(n=bs4["n"]))
        items = bs4.get("metrics", {}).get("items") or []
        rows = "".join(
            '<tr>'
            f'<td>{esc(it["project_key"])}</td>'
            f'<td>{esc(t(locale, "ledger_graveyard_untouched_template").format(days=it["days_untouched"]))}</td>'
            f'<td>{esc(t(locale, "ledger_graveyard_writes_template").format(writes=it["writes"]))}</td>'
            '</tr>'
            for it in items)
        table = f'<table><tbody>{rows}</tbody></table>'
        graveyard_exhibit = _exhibit(
            next(exhibit_no), t(locale, "ledger_graveyard_exhibit_title"),
            table, t(locale, "ledger_source_graveyard"), locale=locale)
        graveyard_html = callout + graveyard_exhibit

    metrics = (
        '<div class="metrics">'
        f'<div class="metric"><div class="n">{int(out.get("git_commits") or 0)}</div>'
        f'<div class="lbl">{t(locale, "ledger_output_commits")}</div></div>'
        f'<div class="metric"><div class="n">{int(out.get("git_pushes") or 0)}</div>'
        f'<div class="lbl">{t(locale, "ledger_output_pushes")}</div></div>'
        f'<div class="metric"><div class="n">{int(out.get("sessions_with_commits") or 0)}</div>'
        f'<div class="lbl">{t(locale, "ledger_output_sessions_with_commits")}</div></div>'
        '</div>')
    ex = _exhibit(next(exhibit_no), t(locale, "ledger_output_title"), metrics,
                  "aggregate.py ledger.output, transcript pool", locale=locale)

    return ('<section class="section" id="ledger-output">'
            f'<h2 class="c-sec-title">{inline_md(title)}</h2>'
            f'{prose_html}{graveyard_html}{ex}</section>')


_SRC_LABEL_KEYS = {"full": "ledger_source_card_full",
                   "partial": "ledger_source_card_partial",
                   "presence_only": "ledger_source_card_presence"}


def _source_card_html(s: dict, locale: str) -> str:
    """One source card: either the normal (label / count / date-span) body,
    or — for a source that produced no rows this run — the not-detected
    variant. Both share the same outer markup so the card's base styling
    only needs to change in one place.

    parse_errors renders on BOTH variants: a source whose every line was
    malformed shows session_count 0 (so it's "not detected"), but the
    reader still needs the hint that something WAS there and failed to
    parse, rather than silent absence."""
    parse_errors = s.get("parse_errors") or 0
    err_line_html = ""
    if parse_errors > 0:
        err_line = t(locale, "ledger_parse_errors_template").format(n=parse_errors)
        err_line_html = f'<br><span class="c-source-card-errs">{esc(err_line)}</span>'
    if s.get("detected") is False:
        modifier = " c-source-card--absent"
        body = f'{esc(t(locale, "ledger_not_detected"))}{err_line_html}'
    else:
        modifier = ""
        label = t(locale, _SRC_LABEL_KEYS.get(s.get("coverage"),
                                              "ledger_source_card_full"))
        span = ""
        if s.get("first_date") and s.get("last_date"):
            span = f'{esc(s["first_date"])} – {esc(s["last_date"])}'
        body = f'{esc(label)}<br>{int(s.get("session_count") or 0)} · {span}{err_line_html}'
    return (f'<div class="c-source-card{modifier}">'
            f'<b>{esc(s["source"])}</b> · {body}</div>')


def _build_team_ledger(cross_llm, narration, locale="en", exhibit_no=None,
                        blind_spots=None):
    """SELF-only team ledger: per-source cards, switch-tax opener (blind spot
    #3, when its gate passed AND the common_window is healthy — the callout
    is itself a cross-source comparison, so it must not render next to the
    degraded note that tells the reader cross-source comparisons were
    suppressed), then (only when a non-degraded common_window exists)
    weekly-share / parallel-heatmap / project-matrix / head-to-head
    exhibits. Degraded or missing window: localized degraded note instead of
    the comparison exhibits; heatmap and matrix still render since they
    don't compare rates across sources. Counts, dates, minutes, and tokens
    only — no session IDs or prompt text ever flow through here.

    exhibit_no is a shared itertools.count() the caller advances across all
    ledger sections (Phase 2 order-of-appearance refactor); a fresh count(2)
    is used when not supplied, preserving the original behavior (Exhibit 1
    lives in the output ledger) for standalone/legacy callers."""
    if not cross_llm or not cross_llm.get("sources"):
        return ""
    if exhibit_no is None:
        exhibit_no = count(2)  # Exhibit 1 lives in the output ledger
    bs = blind_spots or {}
    title = _first_line(narration.get("team-ledger", "")) or t(
        locale, "ledger_team_title")
    prose = _rest_lines(narration.get("team-ledger", ""))
    prose_html = f"<div>{inline_md(prose)}</div>" if prose else ""

    cards = "".join(_source_card_html(s, locale) for s in cross_llm["sources"])
    cards = f'<div class="c-source-cards">{cards}</div>'

    unattributed = cross_llm.get("unattributed_parse_errors") or 0
    if unattributed > 0:
        note = t(locale, "ledger_unknown_parse_errors_template").format(n=unattributed)
        cards += f'<p class="method">{esc(note)}</p>'

    win = cross_llm.get("common_window")
    # Single source of truth for "is this a healthy (present, non-degraded)
    # common_window" — computed here (before the switch-tax callout below)
    # so it is available to gate that callout too, in addition to weekly
    # share, heatmap/matrix, and head-to-head, all of which are cross-source
    # COMPARISONS gated the same way (spec §13).
    window_healthy = bool(win) and not win.get("degraded")

    bs3 = bs.get("switch_tax") or {}
    if bs3.get("gate_passed") and window_healthy:
        m = bs3.get("metrics", {})
        multi_rate = m.get("multi", {}).get("good_rate")
        single_rate = m.get("single", {}).get("good_rate")
        sentence = t(locale, "blindspot_switch_template").format(
            multi=multi_rate, single=single_rate)
        if multi_rate is not None and single_rate is not None and multi_rate < single_rate:
            # Wrap only the worse (multi-tool) rate — negative-red is for
            # bad numbers, not the whole sentence. The markup is built by
            # splitting the TEMPLATE on its {multi} placeholder and
            # injecting the highlighted value directly — not by substring-
            # searching the formatted sentence, which mis-highlighted
            # whenever a template reordered the numbers, used a localized
            # percent sign, or one rate was a digit-suffix of the other.
            tmpl = t(locale, "blindspot_switch_template")
            pre, _, post = tmpl.partition("{multi}")
            val = str(multi_rate)
            # Absorb a percent sign (ASCII or full-width) that immediately
            # follows the placeholder, so "35%" reads as one red token.
            if post[:1] in ("%", "％"):
                val += post[0]
                post = post[1:]
            sentence_html = (
                esc(pre.format(single=single_rate))
                + f'<span class="c-neg-num">{esc(val)}</span>'
                + esc(post.format(single=single_rate)))
            cards += _blindspot_callout(locale, "blindspot_switch_title",
                                        sentence, sentence_html=sentence_html)
        else:
            cards += _blindspot_callout(locale, "blindspot_switch_title", sentence)

    parts = [cards]

    if window_healthy:
        note = t(locale, "ledger_common_window_note_template").format(
            start=win["start"], end=win["end"], days=win["days"])
        parts.append(f'<p class="method">{esc(note)}</p>')
        # Exhibit: weekly share stacked bars
        rows = ""
        srcs = sorted({src for wk in cross_llm.get("weekly_share", [])
                       for src in wk["minutes"]})
        for wk in cross_llm.get("weekly_share", []):
            total = sum(wk["minutes"].values()) or 1
            segs = "".join(
                f'<div class="c-share-seg c-src-{srcs.index(src) % 6}" '
                f'style="width:{100 * mins / total:.1f}%" '
                f'title="{esc(src)}: {int(mins)}"></div>'
                for src, mins in sorted(wk["minutes"].items()))
            rows += (f'<div class="c-share-row"><span>{esc(wk["week"])}</span>'
                     f'<div class="c-share-bar">{segs}</div></div>')
        parts.append(_exhibit(next(exhibit_no),
                              t(locale, "ledger_weekly_share_title"),
                              rows, "aggregate.py cross_llm.weekly_share",
                              locale=locale))
    else:
        # Degraded window OR no window at all — no cross-tool comparison claim.
        parts.append(f'<p class="method">'
                     f'{esc(t(locale, "ledger_degraded_note"))}</p>')

    # heatmap + matrix are cross-source COMPARISONS (spec §13) — like weekly
    # share and head-to-head, they only render for a healthy (non-degraded,
    # present) common_window. aggregate.py still computes them over full
    # history when degraded/absent for schema stability; the source cards +
    # degraded note above are the per-source fallback in that case.
    if window_healthy:
        hm = cross_llm.get("parallel", {}).get("heatmap")
        if hm and any(any(r) for r in hm):
            mx = max(max(r) for r in hm) or 1
            grid = "".join(
                f'<div style="background: rgba(176,138,46,{0.85 * c / mx:.2f})"></div>'
                for row in hm for c in row)
            body = (f'<div style="display:grid;grid-template-columns:repeat(24,1fr);'
                    f'gap:2px;height:120px">{grid}</div>')
            parts.append(_exhibit(next(exhibit_no),
                                  t(locale, "ledger_parallel_title"),
                                  body, "aggregate.py cross_llm.parallel",
                                  locale=locale))

        pm = cross_llm.get("project_matrix") or {}
        if pm.get("projects"):
            head = "".join(f"<th>{esc(s)}</th>" for s in pm["sources"])
            body_rows = "".join(
                f'<tr><td>{esc(proj)}</td>' +
                "".join(f"<td>{c}</td>" for c in pm["counts"][i]) + "</tr>"
                for i, proj in enumerate(pm["projects"]))
            table = (f'<table><thead><tr><th></th>{head}</tr></thead>'
                     f'<tbody>{body_rows}</tbody></table>')
            parts.append(_exhibit(next(exhibit_no),
                                  t(locale, "ledger_matrix_title"),
                                  table, "aggregate.py cross_llm.project_matrix",
                                  locale=locale))

    h2h = cross_llm.get("head_to_head")
    if h2h and window_healthy:
        def _col(name, side):
            return ('<div>'
                    f'<div class="c-kicker">{esc(name)}</div>'
                    f'<div class="num">{int(side["sessions"])}</div>'
                    f'<div class="lbl">{t(locale, "ledger_h2h_sessions")}</div>'
                    f'<div>{int(side["active_days"])} '
                    f'{t(locale, "ledger_h2h_active_days")}</div>'
                    f'<div>{fmt(side["total_tokens"])} '
                    f'{t(locale, "ledger_h2h_tokens")}</div>'
                    f'<div>{int(side["median_duration_minutes"])} '
                    f'{t(locale, "ledger_h2h_median_dur")}</div>'
                    '</div>')
        card = ('<div class="c-h2h">'
                + _col("Claude", h2h["claude"]) + _col("Codex", h2h["codex"])
                + '</div>')
        parts.append(_exhibit(next(exhibit_no),
                              t(locale, "ledger_h2h_title"), card,
                              "aggregate.py cross_llm.head_to_head",
                              locale=locale))

    return ('<section class="section" id="ledger-team">'
            f'<h2 class="c-sec-title">{inline_md(title)}</h2>'
            f'{prose_html}{"".join(parts)}</section>')


def _leak_section_available(blind_spots, ledger):
    """Shared availability predicate for the leak ledger section (spec §10:
    whole section suppressed when nothing passes a gate — no apologetic
    placeholders) and the opening-band leak finding, which must not claim a
    finding the leak section itself won't render.

    bs2 (sunk_cost) is deliberately NOT gate-based here: compute_leaks may
    pass bs2's gate entirely on pairs OUTSIDE the ledger window, in which
    case it emits no `sunk_cost` item — gating availability on
    bs2.gate_passed would then render a section (and an opening-band
    finding) with zero in-window support. `items` non-empty already covers
    the case where a sunk_cost item DID get emitted, so checking `items`
    instead of bs2.gate_passed is both correct and sufficient.

    bs1 (repeated_instructions) stays gate-based: its occurrences are
    window-scoped inside the heuristic itself, and compute_blind_spots
    gates the heuristic off entirely when no valid window exists to scope
    against — so gate_passed already implies in-window support without
    needing an items check.
    """
    bs = blind_spots or {}
    items = ((ledger or {}).get("leaks") or {}).get("items") or []
    bs1 = bs.get("repeated_instructions") or {}
    bs6 = bs.get("ask_vs_ship") or {}
    bs7 = bs.get("interrupt_win_rate") or {}
    return bool(items or bs1.get("gate_passed")
                or bs6.get("gate_passed") or bs7.get("gate_passed"))


def _build_leak_ledger(ledger, blind_spots, narration, locale, exhibit_no):
    """Leak ledger (spec §3 book 3), SELF only. Openers: repeated-instruction
    tax (#1) + sunk-cost (#2). Body: top-3 leak cards. Secondary findings:
    ask-vs-ship (#6) + interrupt win-rate (#7). Habit drift (#5) is computed
    but renders in Phase 3's trend ledger. Whole section suppressed when
    nothing passes a gate (spec §10 — no apologetic placeholders)."""
    bs = blind_spots or {}
    leaks = (ledger or {}).get("leaks") or {}
    items = leaks.get("items") or []
    bs1 = bs.get("repeated_instructions") or {}
    bs6, bs7 = bs.get("ask_vs_ship") or {}, bs.get("interrupt_win_rate") or {}
    if not _leak_section_available(blind_spots, ledger):
        return ""
    sunk_item = next((it for it in items if it.get("type") == "sunk_cost"), None)
    title = _first_line(narration.get("leak-ledger", "")) or t(locale, "ledger_leaks_title")
    prose = _rest_lines(narration.get("leak-ledger", ""))
    out = ['<section class="section" id="ledger-leaks">',
           f'<div class="c-kicker">{esc(t(locale, "ledger_leaks_kicker"))}</div>',
           f'<h2 class="c-sec-title">{inline_md(title)}</h2>']
    if prose:
        out.append(f'<div>{inline_md(prose)}</div>')
    # openers
    if bs1.get("gate_passed"):
        p = bs1["metrics"]["patterns"][0]
        out.append(_blindspot_callout(
            locale, "blindspot_repeated_title",
            t(locale, "blindspot_repeated_template").format(
                n=p["occurrences"], weeks=p["weeks"],
                sources=", ".join(p["sources"])),
            detail=esc(p["exemplar"])))
    if sunk_item is not None:
        out.append(_blindspot_callout(
            locale, "blindspot_sunk_title",
            t(locale, "blindspot_sunk_template").format(
                n=sunk_item["occurrences"])))
    # leak cards exhibit
    if items:
        cards = []
        for it in items:
            cost = t(locale, "ledger_leak_weekly_cost_template").format(
                cost=f"{it['weekly_cost_usd']:.2f}")
            tokens_str = f"{it['weekly_tokens']:,}"
            leak_type = it["type"]
            # repeated_instructions is the only leak type whose fix advice
            # depends on which tools produced the occurrences: CLAUDE.md is
            # Claude-Code-specific, so an item whose sources include a
            # non-Claude tool (Codex/Grok) needs the cross-tool fix text
            # instead (Fix 5) — other leak types are unaffected.
            fix_key = "leak_fix_" + leak_type
            if leak_type == "repeated_instructions":
                sources = it.get("sources") or []
                if any(s != "claude" for s in sources):
                    fix_key = "leak_fix_repeated_instructions_cross"
            cards.append(
                '<div class="c-leak-card">'
                f'<div class="c-leak-type">{esc(t(locale, "leak_type_" + leak_type))}</div>'
                f'<div class="c-leak-cost">{esc(cost)}</div>'
                f'<div class="c-leak-meta">{esc(t(locale, "ledger_leak_tokens_template").format(tokens=tokens_str))}'
                f' · {esc(t(locale, "ledger_leak_occurrences_template").format(n=it["occurrences"]))}</div>'
                f'<div class="c-leak-fix"><span>{esc(t(locale, "ledger_leak_fix_label"))}</span> '
                f'{esc(t(locale, fix_key))}</div></div>')
        out.append(_exhibit(next(exhibit_no),
                            t(locale, "ledger_leaks_exhibit_title"),
                            '<div class="c-leak-cards">' + "".join(cards) + "</div>",
                            t(locale, "ledger_source_leaks"), locale))
    # secondary findings (#6, #7)
    sec = []
    if bs6.get("gate_passed"):
        g = bs6["metrics"]["top_gap"]
        sec.append(t(locale, "blindspot_askship_template").format(
            cat=_goal_category_label(locale, g["category"]),
            ask=g["ask_share_pct"], ship=g["ship_share_pct"]))
    if bs7.get("gate_passed"):
        m = bs7["metrics"]
        sec.append(t(locale, "blindspot_interrupt_template").format(
            i=m["interrupted"]["good_rate"], b=m["baseline"]["good_rate"]))
    if sec:
        out.append('<div class="c-secondary"><h3>'
                   + esc(t(locale, "ledger_secondary_findings")) + "</h3><ul>"
                   + "".join(f"<li>{esc(x)}</li>" for x in sec) + "</ul></div>")
    out.append("</section>")
    return "".join(out)


# Trend ledger (Phase 3, spec §3 book 4). Unlock floor is a spec §13
# default, independent of every other gate constant in this file.
_TREND_MIN_SNAPSHOTS = 3
_TREND_REF_TARGET_DAYS = 90


def _sparkline_svg(values, width=120, height=28):
    """Inline-SVG mini line chart (no JS, self-containment-safe).
    Non-numeric entries are skipped; needs >= 2 numeric points."""
    pts = [(i, v) for i, v in enumerate(values)
           if isinstance(v, (int, float))]
    if len(pts) < 2:
        return ""
    lo = min(v for _, v in pts)
    hi = max(v for _, v in pts)
    span = (hi - lo) or 1.0
    n = len(values)
    coords = []
    for i, v in pts:
        x = 2 + i * (width - 4) / max(n - 1, 1)
        y = height - 3 - (v - lo) / span * (height - 6)
        coords.append(f"{x:.1f},{y:.1f}")
    return (f'<svg class="c-spark" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-hidden="true">'
            f'<polyline fill="none" stroke="currentColor" stroke-width="1.5" '
            f'points="{" ".join(coords)}"/></svg>')


def _entry_overall(entry):
    """overall_avg (Phase 3 snapshots) with pre-Phase-3 fallback: mean of
    the per-dim scores map."""
    v = entry.get("overall_avg")
    if isinstance(v, (int, float)):
        return v
    vals = [x for x in (entry.get("scores") or {}).values()
            if isinstance(x, (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else None


def _entry_leak_cost(entry):
    """Weekly leak cost from a HISTORY snapshot. Snapshot ledger.leaks is
    the COMPACT LIST shape ({type, weekly_cost_usd, ...} items, no
    evidence) — NOT analysis-data.json's {window_weeks, items} dict (see
    docs/SCHEMA-CHANGES.md). Tolerate the dict shape anyway."""
    leaks = (entry.get("ledger") or {}).get("leaks")
    if isinstance(leaks, dict):
        leaks = leaks.get("items") or []
    if not isinstance(leaks, list):
        return None
    vals = [it.get("weekly_cost_usd") for it in leaks
            if isinstance(it, dict)
            and isinstance(it.get("weekly_cost_usd"), (int, float))]
    return round(sum(vals), 2) if vals else None


def _current_trend_values(analysis):
    """The same five metrics the snapshot records, taken from THIS run's
    analysis dict (the snapshot for this run is appended after render)."""
    ledger = analysis.get("ledger") or {}
    items = ((ledger.get("leaks") or {}).get("items")) or []
    cost_vals = [it.get("weekly_cost_usd") for it in items
                 if isinstance(it, dict)
                 and isinstance(it.get("weekly_cost_usd"), (int, float))]
    badges = analysis.get("badges") or {}
    earned = sum(1 for b in (badges.get("items") or [])
                 if isinstance(b, dict) and b.get("earned"))
    return {
        "overall": ((analysis.get("scores") or {}).get("_overall") or {}).get("avg"),
        "commits": (ledger.get("output") or {}).get("git_commits"),
        "sessions": (analysis.get("meta") or {}).get("total_sessions"),
        "leak_cost": round(sum(cost_vals), 2) if cost_vals else None,
        "badges": earned,
    }


def _entry_trend_values(entry):
    led = entry.get("ledger") or {}
    badges = entry.get("badges")
    return {
        "overall": _entry_overall(entry),
        "commits": led.get("git_commits"),
        "sessions": led.get("sessions"),
        "leak_cost": _entry_leak_cost(entry),
        "badges": len(badges) if isinstance(badges, list) else None,
    }


def _pick_reference(entries):
    """Among all snapshots except the newest, the one closest to
    (newest date - 90 days). Callers guarantee len(entries) >= 3 and
    ISO-parseable dates (read_history_snapshots enforces both)."""
    newest = date.fromisoformat(entries[-1]["date"])
    target = newest - timedelta(days=_TREND_REF_TARGET_DAYS)
    return min(entries[:-1],
               key=lambda e: abs((date.fromisoformat(e["date"]) - target).days))


def _fmt_trend(key, v, locale):
    if v is None:
        return t(locale, "ledger_trend_na")
    if key == "leak_cost":
        return f"${v:,.2f}"
    if key == "overall":
        return f"{v:g}"
    return fmt(v)


def _build_trend_ledger(analysis, history_entries, narration, locale,
                        exhibit_no, blind_spots):
    """SELF-only trend ledger (spec §3 book 4). Locked (< 3 snapshots)
    renders the spec-mandated one-line unlock note — the single allowed
    exception to the no-placeholder suppression rule. Unlocked renders
    the habit-drift opener (gated) + a this/last/reference comparison
    exhibit with inline-SVG sparklines over all snapshots. Only counts,
    dates, scores and dollar totals are read — never sids, prompt text,
    or project names."""
    entries = history_entries or []
    if len(entries) < _TREND_MIN_SNAPSHOTS:
        n_more = _TREND_MIN_SNAPSHOTS - len(entries)
        return ('<section class="section" id="ledger-trend">'
                f'<div class="c-kicker">{esc(t(locale, "ledger_trend_kicker"))}</div>'
                f'<p class="c-trend-locked">'
                f'{esc(t(locale, "ledger_trend_locked_template").format(n=n_more))}'
                '</p></section>')

    title = _first_line(narration.get("trend-ledger", "")) or t(
        locale, "ledger_trend_title")
    prose = _rest_lines(narration.get("trend-ledger", ""))

    out = ['<section class="section" id="ledger-trend">',
           f'<div class="c-kicker">{esc(t(locale, "ledger_trend_kicker"))}</div>',
           f'<h2 class="c-action-title">{esc(title)}</h2>']

    drift = (blind_spots or {}).get("habit_drift") or {}
    if drift.get("gate_passed"):
        m = drift.get("metrics") or {}
        sentence = t(locale, "blindspot_drift_template").format(
            weeks=m.get("weeks", 0),
            early=fmt(m.get("early_median_len", 0)),
            late=fmt(m.get("late_median_len", 0)),
            early_rate=m.get("early_good_rate", 0),
            late_rate=m.get("late_good_rate", 0))
        out.append(_blindspot_callout(locale, "blindspot_drift_title", sentence))

    if prose:
        out.append(md_to_html(prose))

    prev = entries[-1]
    ref = _pick_reference(entries)
    current = _current_trend_values(analysis)
    rows_spec = [("overall", "ledger_trend_row_overall"),
                 ("commits", "ledger_trend_row_commits"),
                 ("sessions", "ledger_trend_row_sessions"),
                 ("leak_cost", "ledger_trend_row_leak_cost"),
                 ("badges", "ledger_trend_row_badges")]
    prev_vals = _entry_trend_values(prev)
    ref_vals = _entry_trend_values(ref)
    all_series = [_entry_trend_values(e) for e in entries]

    body = ['<table class="c-trend-table"><thead><tr>',
            f'<th>{esc(t(locale, "ledger_trend_col_metric"))}</th>',
            f'<th>{esc(t(locale, "ledger_trend_col_this"))}</th>',
            f'<th>{esc(t(locale, "ledger_trend_col_prev_template").format(date=prev["date"]))}</th>',
            f'<th>{esc(t(locale, "ledger_trend_col_ref_template").format(date=ref["date"]))}</th>',
            f'<th>{esc(t(locale, "ledger_trend_col_spark"))}</th>',
            '</tr></thead><tbody>']
    for key, label_key in rows_spec:
        series = [vals[key] for vals in all_series] + [current[key]]
        # negative red is reserved for bad numbers: leak cost is the only
        # inherently-bad row in this table.
        neg = ' class="c-neg-num"' if key == "leak_cost" else ""
        body.append(
            f'<tr><td>{esc(t(locale, label_key))}</td>'
            f'<td{neg}>{esc(_fmt_trend(key, current[key], locale))}</td>'
            f'<td{neg}>{esc(_fmt_trend(key, prev_vals[key], locale))}</td>'
            f'<td{neg}>{esc(_fmt_trend(key, ref_vals[key], locale))}</td>'
            f'<td>{_sparkline_svg(series)}</td></tr>')
    body.append('</tbody></table>')

    out.append(_exhibit(next(exhibit_no),
                        t(locale, "ledger_trend_exhibit_title"),
                        "".join(body),
                        t(locale, "ledger_source_trend"), locale))
    out.append('</section>')
    return "".join(out)


# Badge layer (Phase 3, spec §4) — external versions only. Wording is
# fixed locale template text (spec §2 rule 6); earned-only; zero-earned
# suppresses the whole section (never render "failed").
_BADGE_TEMPLATE_ARGS = {
    "delegation": lambda m, th, n: {
        "ta": fmt(m.get("ta_rate_pct")), "bar_ta": fmt(th.get("ta_rate_pct")),
        "good": fmt(m.get("good_rate_with_ta_pct")),
        "bar_good": fmt(th.get("good_rate_with_ta_pct"))},
    "root_cause": lambda m, th, n: {
        "pct": fmt(m.get("iter_buggy_pct")),
        "bar": fmt(th.get("max_iter_buggy_pct"))},
    "tool_breadth": lambda m, th, n: {
        "mcp": fmt(m.get("mcp_rate_pct")), "bar_mcp": fmt(th.get("mcp_rate_pct")),
        "top3": fmt(m.get("top3_share_pct")),
        "bar_top3": fmt(th.get("max_top3_share_pct"))},
    "token_efficiency": lambda m, th, n: {
        "ratio": fmt(m.get("ratio")), "bar_ratio": fmt(th.get("max_ratio")),
        "cache": fmt(m.get("cache_hit_pct")),
        "bar_cache": fmt(th.get("min_cache_hit_pct"))},
    "shipping_cadence": lambda m, th, n: {
        "per_week": fmt(m.get("commits_per_week")),
        "bar": fmt(th.get("commits_per_week")), "n": fmt(n)},
    "cross_tool_orchestration": lambda m, th, n: {
        "hours": fmt(m.get("hours_multi_source")),
        "days": fmt(m.get("common_window_days")),
        "bar": fmt(th.get("min_multi_hours"))},
}


def _hr_section_wrap(section_id, heading_key, subtitle_key, method_key,
                     body_html, locale):
    """Shared skeleton for a recruiter-v1 top-level section: id + numberless
    §-heading + subtitle + method line + body. Both _build_badges_section
    and _build_hr_output_ledger render this same 4-part shape."""
    return (
        f'<section id="{section_id}">'
        f'<h2 class="sec" data-num="">{t(locale, heading_key)}</h2>'
        f'<h2 class="sec-title">{t(locale, subtitle_key)}</h2>'
        f'<p class="method">{t(locale, method_key)}</p>'
        f'{body_html}'
        '</section>')


def _build_badges_section(badges, window, locale):
    """Earned badges for external versions. Evidence pointer is
    privacy-safe by construction: sample size + window dates only."""
    items = [b for b in ((badges or {}).get("items") or [])
             if isinstance(b, dict) and b.get("earned")]
    if not items:
        return ""
    win = window or {}
    cards = []
    for b in items:
        bid = b.get("id")
        args_fn = _BADGE_TEMPLATE_ARGS.get(bid)
        if args_fn is None:
            continue
        name = t(locale, f"badge_{bid}_name")
        criteria = t(locale, f"badge_{bid}_criteria").format(
            **args_fn(b.get("metrics") or {}, b.get("thresholds") or {},
                      b.get("n", 0)))
        evidence = t(locale, "badge_evidence_template").format(
            n=fmt(b.get("n", 0)), start=win.get("start") or "?",
            end=win.get("end") or "?")
        cards.append(
            '<div class="c-badge">'
            f'<div class="c-badge-name">{esc(name)}</div>'
            f'<div class="c-badge-criteria">{esc(criteria)}</div>'
            f'<div class="c-badge-evidence">{esc(evidence)}</div>'
            '</div>')
    if not cards:
        return ""
    return _hr_section_wrap(
        "badges", "hr_badges_h", "hr_badges_subtitle", "hr_badges_method",
        f'<div class="c-badge-grid">{"".join(cards)}</div>', locale)


def _build_hr_output_ledger(ledger, shipped, artifacts_list, is_public,
                            locale):
    """Recruiter output ledger (spec §4): ledger.output counters +
    allowlist-filtered shipped work + public artifact links. Non-public
    items are excluded entirely, not shown as redacted filler."""
    out = (ledger or {}).get("output") or {}
    counters = (
        '<div class="metrics">'
        f'<div class="metric"><div class="n">{fmt(out.get("git_commits") or 0)}</div>'
        f'<div class="lbl">{t(locale, "hr_output_commits")}</div></div>'
        f'<div class="metric"><div class="n">{fmt(out.get("git_pushes") or 0)}</div>'
        f'<div class="lbl">{t(locale, "hr_output_pushes")}</div></div>'
        f'<div class="metric"><div class="n">{fmt(out.get("sessions_with_commits") or 0)}</div>'
        f'<div class="lbl">{t(locale, "hr_output_sessions_with_commits")}</div></div>'
        '</div>')

    # Codex v3 (V4 HR review): at most 3 PUBLIC items. Redacted items add
    # near-zero signal for a hiring manager and read as padding, so a
    # non-public item is dropped entirely rather than shown as filler.
    MAX_SHIPPED_ITEMS = 3
    shipped_items = ""
    for item in [s for s in (shipped or []) if is_public(s["project"])][:MAX_SHIPPED_ITEMS]:
        dur_hr = item["project_duration_min"] / 60
        proj_sub = t(locale, "hr_output_proj_sub_template").format(
            sessions=item["project_sessions"], hours=f'{dur_hr:.0f}')
        shipped_items += (
            '<div class="shipped-item"><div>'
            f'<div class="proj">{esc(item["project"])}</div>'
            f'<div class="proj-sub">{esc(proj_sub)}</div>'
            '</div>'
            f'<div class="desc">{esc(item["summary"])}</div>'
            f'<div class="stats">{item["project_commits"]} {t(locale, "hr_output_commits_label")}<br>'
            f'{fmt(item["total_tokens"])} {t(locale, "hr_output_tok_label")}</div></div>')
    shipped_html = (f'<div class="shipped-list">{shipped_items}</div>'
                    if shipped_items else "")

    artifact_rows = ""
    for a in (artifacts_list or []):
        safe_url = sanitize_url(str(a.get("url", "")).strip())
        artifact_rows += (
            '<div class="artifact-row"><div>'
            f'<div class="name">{esc(a.get("name", "(unnamed)"))}</div>'
            f'<div class="desc">{esc(a.get("description", ""))}</div></div>'
            f'<div class="link"><a rel="noopener noreferrer" href="{esc(safe_url)}">'
            f'{esc(display_url(safe_url))}</a></div></div>')

    return _hr_section_wrap(
        "hr-output", "hr_output_h", "hr_output_subtitle", "hr_output_method",
        f'{counters}{shipped_html}{artifact_rows}', locale)


def sanitize_url(url: str, *, allow_mailto: bool = False) -> str:
    if not url:
        return "#"
    parsed = urlparse(url.strip())
    allowed = SAFE_URL_SCHEMES_WITH_MAILTO if allow_mailto else SAFE_URL_SCHEMES
    if parsed.scheme.lower() not in allowed:
        return "#"
    return parsed.geturl()


def display_url(url: str) -> str:
    cleaned = url.strip()
    for prefix in ("https://", "http://", "mailto:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    return cleaned.rstrip("/") or url


def md_to_html(md: str) -> str:
    """Minimal markdown → HTML."""
    if not md:
        return "<p class='muted'><em>(no peer review written for this run)</em></p>"
    out_lines = []
    in_list = False
    list_tag = "ol"
    pending_blanks = 0

    def close_list():
        nonlocal in_list
        if in_list:
            out_lines.append(f"</{list_tag}>")
            in_list = False

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            # Blank lines inside a list are part of the list (CommonMark "loose
            # list"): only close the list when we see the next non-blank line
            # that isn't a list item.
            pending_blanks += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            close_list()
            out_lines.extend([""] * pending_blanks)
            pending_blanks = 0
            level = len(m.group(1))
            out_lines.append(f"<h{level+2}>{inline_md(m.group(2))}</h{level+2}>")
            continue

        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            if in_list and list_tag != "ol":
                close_list()
            if not in_list:
                out_lines.extend([""] * pending_blanks)
                out_lines.append("<ol>")
                in_list = True
                list_tag = "ol"
            pending_blanks = 0
            out_lines.append(f"<li>{inline_md(m.group(2))}</li>")
            continue

        if line.startswith("- ") or line.startswith("* "):
            if in_list and list_tag != "ul":
                close_list()
            if not in_list:
                out_lines.extend([""] * pending_blanks)
                out_lines.append("<ul>")
                in_list = True
                list_tag = "ul"
            pending_blanks = 0
            out_lines.append(f"<li>{inline_md(line[2:])}</li>")
            continue

        close_list()
        out_lines.extend([""] * pending_blanks)
        pending_blanks = 0
        out_lines.append(f"<p>{inline_md(line)}</p>")

    close_list()
    return "\n".join(out_lines)


def inline_md(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def score_band(sc):
    """Return tone class name for a 1-10 score."""
    if sc is None:
        return "na"
    if sc >= 7:
        return "strong"
    if sc >= 5:
        return "mixed"
    return "weak"


def _load_chart_layout_js() -> str:
    """Read js/chart_layout.js and strip its CommonJS export so it can be
    inlined into a browser <script> tag. node:test still loads the original
    file directly via require()."""
    js_path = Path(__file__).resolve().parent.parent / "js" / "chart_layout.js"
    src = js_path.read_text()
    marker = "if (typeof module"
    idx = src.find(marker)
    if idx != -1:
        src = src[:idx].rstrip() + "\n"
    return src



# ---- Big HTML template as a module-level string.
# Uses string.Template's $placeholder style so CSS/JS braces don't need escaping.
PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="$html_lang">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$report_title</title>

<style>
  :root {
    --paper: #f4efe6;
    --paper-deep: #ece5d5;
    --ink: #1a1916;
    --ink-soft: #464239;
    --ink-muted: #7a7363;
    --rule: #c9bfa8;
    --rule-soft: #ddd3bc;
    --accent: #a0431e;        /* burnt sienna */
    --ochre: #b28121;
    --forest: #2e5b3e;
    --oxblood: #6b1b1b;
    --plum: #63355c;
    --serif: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, "Songti TC", "Noto Serif CJK TC", serif;
    --sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Noto Sans CJK TC", sans-serif;
    --mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;

    /* --- Spacing primitives (2px granularity, matches existing component values) --- */
    --space-0: 0;
    --space-1: 2px;
    --space-2: 4px;
    --space-3: 6px;
    --space-4: 8px;
    --space-5: 10px;
    --space-6: 12px;
    --space-7: 14px;
    --space-8: 16px;
    --space-9: 18px;
    --space-10: 20px;
    --space-11: 22px;
    --space-12: 24px;
    /* --space-13 (26px) omitted — only used in intro-card's unique horizontal padding */
    --space-14: 28px;
    --space-15: 30px;

    /* --- Radius primitives --- */
    --radius-sm: 2px;
    --radius-md: 3px;
    --radius-lg: 6px;

    /* --- Font-size primitives (zh-Hant overrides handled separately) --- */
    --text-xs: 11.5px;
    --text-sm: 13px;
    --text-base: 15px;
    --text-md: 16px;
    --text-lg: 17px;
    --text-xl: 18px;
    --text-2xl: 24px;

    /* --- Line-height primitives --- */
    --leading-tight: 1.2;
    --leading-snug: 1.35;
    --leading-normal: 1.55;
    --leading-loose: 1.7;

    /* --- Semantic aliases (design intent — add new ones as components need them).
       --card-padding / --card-radius were considered but removed pending a concrete
       consumer. --- */
    --section-gap: var(--space-15);
    --tag-padding-y: var(--space-1);
    --tag-padding-x: var(--space-3);
  }

  * { box-sizing: border-box; }

  html, body {
    margin: 0; padding: 0;
    background: var(--paper);
    color: var(--ink);
  }

  body {
    font-family: var(--serif);
    font-optical-sizing: auto;
    font-variation-settings: "opsz" 14;
    font-size: 17px;
    line-height: 1.58;
    letter-spacing: -0.005em;
    background-image:
      radial-gradient(rgba(0,0,0,0.035) 1px, transparent 1px),
      linear-gradient(180deg, rgba(255,250,240,0.4), rgba(0,0,0,0) 40%);
    background-size: 3px 3px, 100% 100%;
  }

  .page {
    max-width: 900px;
    margin: 0 auto;
    padding: 70px 56px 120px 56px;
  }

  @media (max-width: 720px) {
    .page { padding: 40px 22px 80px 22px; }
    body { font-size: 16px; }
  }

  /* CJK characters render visually smaller than Latin at the same px size
     (lower x-height, denser strokes). Bump base + key prose contexts so the
     zh_TW report doesn't feel cramped. Latin runs inside Chinese paragraphs
     (model names, code samples) inherit the bigger size, which is what we
     want — they should match the surrounding type, not snap back to 17px. */
  html[lang="zh-Hant"] body { font-size: 18.5px; line-height: 1.7; }
  html[lang="zh-Hant"] .dek { font-size: 17.5px; }
  html[lang="zh-Hant"] .intro-card { font-size: 17px; }
  html[lang="zh-Hant"] .method,
  html[lang="zh-Hant"] .caveat { font-size: 15.5px; }
  /* Variable serif weight 300 renders bony on CJK fallbacks (PingFang TC,
     Noto Serif CJK). Bump to 500 (em to 600) so the Chinese hero reads
     with intent, not fragility. English hero unaffected (lang="en"). */
  html[lang="zh-Hant"] h1.title {
    font-weight: 500;
    font-variation-settings: "opsz" 144, "wght" 500;
  }
  html[lang="zh-Hant"] h1.title em {
    font-weight: 600;
    font-variation-settings: "opsz" 144, "wght" 600;
  }
  /* CJK editorial rhythm: 字距補償（中英夾雜時西文後方需微距）+ 等寬數字
     （stat tile 的 19,872 / 15,019 縱向對齊，避免 proportional 飄移）*/
  html[lang="zh-Hant"] body,
  html[lang="zh-Hant"] p {
    letter-spacing: 0.02em;
  }
  html[lang="zh-Hant"] .metric .n,
  html[lang="zh-Hant"] .num,
  html[lang="zh-Hant"] .tile .n {
    font-feature-settings: "tnum" 1, "lnum" 1;
  }
  @media (max-width: 720px) {
    html[lang="zh-Hant"] body { font-size: 17px; }
  }

  /* Letterhead */
  .letterhead {
    border-bottom: 1px solid var(--rule);
    padding-bottom: 28px;
    margin-bottom: 44px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 40px;
  }
  .mark {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--ink-muted);
  }
  .letterhead .right {
    text-align: right;
    font-family: var(--mono);
    font-size: 11px;
    line-height: 1.45;
    color: var(--ink-muted);
  }
  .letterhead .right b { color: var(--ink); font-weight: 500; }

  h1.title {
    font-family: var(--serif);
    font-variation-settings: "opsz" 144, "wght" 300;
    font-weight: 300;
    font-size: clamp(38px, 6vw, 64px);
    line-height: 1.02;
    letter-spacing: -0.03em;
    margin: 14px 0 12px 0;
  }
  h1.title em {
    font-style: italic;
    font-variation-settings: "opsz" 144, "wght" 400;
    color: var(--accent);
  }

  .dek {
    font-family: var(--sans);
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    color: var(--ink-soft);
    max-width: 56ch;
    margin: 0 0 var(--section-gap) 0;
  }

  .intro-card {
    border: 1px solid var(--rule);
    background: rgba(255,250,240,0.5);
    padding: var(--space-11) 26px;       /* 26px horizontal kept hardcode (component-unique) */
    margin: 0 0 calc(2 * var(--section-gap)) 0;   /* 60px = 2× section-gap */
    font-size: 15.5px;
    line-height: 1.6;
    position: relative;
  }
  .intro-card::before {
    content: "NOTE";
    position: absolute;
    top: -9px; left: var(--space-11);   /* 22px — intentionally 4px inside the 26px horizontal padding */
    background: var(--paper);
    padding: 0 var(--space-4);
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.2em;
    color: var(--accent);
  }

  .preliminary {
    background: #fbe9d8;
    border: 1px dashed var(--accent);
    color: var(--accent);
    padding: 12px 18px;
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.04em;
    margin: 18px 0 0 0;
  }

  /* Plain-language intro + 4-zone relationship diagram */
  .story-section {
    margin-top: 64px;
    margin-bottom: 64px;
  }
  .plain-intro {
    border-left: 4px solid var(--accent);
    background: rgba(255, 248, 232, 0.55);
    padding: 22px 28px 18px 28px;
    margin-bottom: 36px;
    font-size: 15.5px;
    line-height: 1.65;
  }
  .plain-intro-h {
    font-family: var(--serif);
    font-size: 22px;
    font-weight: 600;
    margin: 0 0 12px 0;
    color: var(--ink);
    letter-spacing: 0.01em;
  }
  .plain-intro p { margin: 0 0 12px 0; }
  .plain-intro ul { margin: 8px 0 12px 0; padding-left: 24px; }
  .plain-intro li { margin-bottom: 6px; }
  .plain-intro b { color: var(--accent); }

  /* SELF reading guide */
  .reading-guide {
    border-left: 3px solid var(--rule);
    background: transparent;
    padding: 4px 0 4px 18px;
    margin-top: 24px;
    font-size: 14px;
    line-height: 1.6;
    color: var(--ink-muted);
  }
  .reading-guide-h {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 0 0 6px 0;
  }
  html[lang="zh-Hant"] .reading-guide-h {
    letter-spacing: 0.05em;
    font-size: 13px;
    text-transform: none;
    font-family: var(--serif);
    font-weight: 600;
  }
  .reading-guide p { margin: 0; }

  /* Benchmark caveat — italic disclaimer line, low key */
  .benchmark-caveat {
    font-size: 12.5px;
    color: var(--ink-muted);
    font-style: italic;
    margin: 16px 0 8px 0;
    line-height: 1.5;
  }

  /* Try-this-week block (SELF) */
  .try-this-section {
    background: rgba(255, 248, 232, 0.40);
    border: 1px solid var(--rule);
    padding: 24px 28px 18px 28px;
    margin: 48px 0;
  }
  .try-this-section h2.sec {
    margin-top: 0;
  }
  .try-this-body {
    font-size: 15px;
    line-height: 1.7;
  }
  .try-this-body ol, .try-this-body ul {
    padding-left: 22px;
    margin: 12px 0;
  }
  .try-this-body li {
    margin-bottom: 10px;
  }
  .try-this-body strong {
    color: var(--accent);
  }

  /* Method as footer (BOTH, smaller typography) */
  .method-footer {
    margin-top: 64px;
    padding: 24px 0 8px 0;
    border-top: 1px solid var(--rule);
    color: var(--ink-muted);
  }
  .method-footer-h {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 0 0 10px 0;
  }
  html[lang="zh-Hant"] .method-footer-h {
    letter-spacing: 0.06em;
    font-size: 13px;
    text-transform: none;
    font-family: var(--serif);
    font-weight: 600;
  }
  .method-footer-body {
    font-size: 12.5px;
    line-height: 1.55;
  }
  .method-footer-body h4 {
    font-size: 13px;
    font-weight: 600;
    margin: 14px 0 4px 0;
    color: var(--ink);
  }
  .method-footer-body ul {
    padding-left: 18px;
    margin: 4px 0;
  }
  .method-footer-body li {
    margin-bottom: 3px;
  }

  /* Claim-indexed evidence (SELF) */
  .claim-header {
    margin-top: 36px;
    margin-bottom: 14px;
    padding: 12px 0 10px 0;
    border-top: 1px solid var(--rule);
  }
  .claim-header:first-child {
    margin-top: 0;
    border-top: none;
  }
  .claim-header h3 {
    font-family: var(--serif);
    font-size: 18px;
    margin: 0 0 4px 0;
    color: var(--ink);
  }
  .claim-intro {
    font-size: 13.5px;
    color: var(--ink-muted);
    margin: 0;
    line-height: 1.5;
  }
  .claim-empty {
    font-style: italic;
    color: var(--ink-muted);
    font-size: 13.5px;
    margin: 8px 0;
  }

  /* Case study block (BOTH) */
  .case-study-section {
    border-top: 2px solid var(--rule);
    border-bottom: 2px solid var(--rule);
    padding: 28px 0;
    margin: 48px 0;
  }
  .case-study-body {
    font-size: 14.5px;
    line-height: 1.65;
  }
  .case-study-body dl {
    margin: 16px 0;
  }
  .case-study-body dt {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--accent);
    margin-top: 12px;
  }
  html[lang="zh-Hant"] .case-study-body dt {
    letter-spacing: 0.05em;
    font-size: 12.5px;
    text-transform: none;
    font-family: var(--serif);
    font-weight: 600;
  }
  .case-study-body dd {
    margin: 4px 0 0 0;
    padding-left: 0;
  }

  /* Section headers */
  section { margin: 80px 0 0 0; }
  h2.sec {
    font-family: var(--serif);
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.32em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 0 0 6px 0;
    padding-bottom: 0;
    border: 0;
    display: flex;
    align-items: baseline;
    gap: 12px;
  }
  h2.sec::before {
    content: attr(data-num);
    font-family: var(--mono);
    font-size: 12px;
    color: var(--ink-muted);
    letter-spacing: 0.08em;
  }
  h2.sec-title {
    font-family: var(--serif);
    font-variation-settings: "opsz" 72, "wght" 400;
    font-weight: 400;
    font-size: clamp(26px, 3.4vw, 36px);
    line-height: 1.12;
    letter-spacing: -0.02em;
    margin: 0 0 32px 0;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--rule);
  }

  h3 {
    font-family: var(--serif);
    font-variation-settings: "opsz" 24, "wght" 500;
    font-weight: 500;
    font-size: 20px;
    line-height: 1.35;
    letter-spacing: -0.01em;
    margin: 38px 0 14px 0;
  }
  h4 {
    font-family: var(--mono);
    font-size: 11.5px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--ink-muted);
    margin: 24px 0 10px 0;
  }

  p { margin: 0 0 14px 0; }
  p.muted { color: var(--ink-muted); }
  a { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; text-decoration-thickness: 1px; }
  a:hover { color: var(--oxblood); }
  strong { font-weight: 600; color: var(--ink); }
  code {
    font-family: var(--mono);
    font-size: 0.82em;
    background: rgba(160, 67, 30, 0.07);
    padding: 1px 6px;
    border-radius: 2px;
    color: var(--oxblood);
  }

  /* TOC */
  .toc {
    font-family: var(--mono);
    font-size: 12px;
    line-height: 1.85;
    letter-spacing: 0.02em;
    margin: 22px 0 0 0;
    counter-reset: toc;
    columns: 2;
    column-gap: 40px;
  }
  .toc a {
    display: block;
    color: var(--ink-soft);
    text-decoration: none;
    padding: 3px 0;
    border-bottom: 1px dotted transparent;
  }
  .toc a::before {
    counter-increment: toc;
    content: counter(toc, decimal-leading-zero) "  ";
    color: var(--accent);
  }
  .toc a:hover { color: var(--accent); border-bottom-color: var(--rule); }

  /* Metric cards grid */
  .metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0;
    margin: var(--space-15) 0 var(--space-10) 0;
    border-top: 1px solid var(--rule);
    border-left: 1px solid var(--rule);
  }
  .metrics > .metric {
    border-right: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    padding: var(--space-8) var(--space-9) var(--space-9) var(--space-9);
    background: rgba(255,250,240,0.35);
  }
  @media (max-width: 640px) {
    .metrics { grid-template-columns: repeat(2, 1fr); }
  }
  .metric .n {
    font-family: var(--serif);
    font-variation-settings: "opsz" 72, "wght" 400;
    font-size: 32px;   /* hero-size display number; not on type scale */
    line-height: 1;
    letter-spacing: -0.025em;
    color: var(--ink);
  }
  .metric .lbl {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ink-muted);
    margin-top: var(--space-4);
  }

  /* Score rows — like rubric scores on a form */
  .score-table {
    margin: 32px 0 0 0;
    border-top: 2px solid var(--ink);
  }
  .score-row {
    display: grid;
    grid-template-columns: 80px 1fr 70px;
    gap: 24px;
    padding: 22px 0;
    border-bottom: 1px solid var(--rule);
    align-items: start;
  }
  .score-row .dim {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.12em;
    color: var(--ink-muted);
    text-transform: uppercase;
    padding-top: 6px;
  }
  .score-row .body { }
  .score-row .body .h {
    font-family: var(--serif);
    font-variation-settings: "opsz" 24, "wght" 500;
    font-size: 20px;
    line-height: 1.25;
    margin: 0 0 6px 0;
  }
  .score-row .body .exp {
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.55;
    color: var(--ink-soft);
    margin: 0;
  }
  .score-row .score {
    font-family: var(--serif);
    font-variation-settings: "opsz" 144, "wght" 300;
    font-size: 44px;
    line-height: 1;
    text-align: right;
    letter-spacing: -0.03em;
    color: var(--ink);
    position: relative;
  }
  .score-row .score .out {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.1em;
    color: var(--ink-muted);
    display: block;
    margin-top: 4px;
  }
  .score-row.strong .score { color: var(--forest); }
  .score-row.mixed .score { color: var(--ochre); }
  .score-row.weak .score { color: var(--oxblood); }
  .score-row.na .score { color: var(--ink-muted); font-size: 22px; padding-top: 12px; }

  .score-row .body .pattern {
    font-family: var(--sans);
    font-size: 13.5px;
    line-height: 1.5;
    color: var(--ink-muted);
    font-style: italic;
    margin: 6px 0 0 0;
  }

  .score-disclaimer {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.08em;
    color: var(--ink-muted);
    text-transform: uppercase;
    margin: 0 0 14px 0;
    text-align: left;
  }

  .usage-characteristics {
    margin: 28px 0 0 0;
    padding: 20px 0 0 0;
    border-top: 1px solid var(--rule);
  }
  .uc-header {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.12em;
    color: var(--ink-muted);
    text-transform: uppercase;
    margin: 0 0 4px 0;
  }
  .uc-note {
    font-family: var(--sans);
    font-size: 12.5px;
    color: var(--ink-muted);
    margin: 0 0 14px 0;
  }
  .uc-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .uc-row {
    display: grid;
    grid-template-columns: 72px 1fr;
    gap: 16px;
    padding: 8px 0;
    border-bottom: 1px dotted var(--rule);
    align-items: baseline;
  }
  .uc-row:last-child { border-bottom: none; }
  .uc-row .pct {
    font-family: var(--serif);
    font-variation-settings: "opsz" 24, "wght" 400;
    font-size: 24px;
    line-height: 1;
    color: var(--ink);
    text-align: right;
    letter-spacing: -0.01em;
  }
  .uc-body .label {
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.45;
    color: var(--ink);
    margin: 0 0 2px 0;
  }
  .uc-body .tip {
    font-family: var(--sans);
    font-size: 13px;
    line-height: 1.5;
    color: var(--ink-muted);
    font-style: italic;
    margin: 0;
  }

  /* ---- Identity header ---- */
  .identity-header {
    margin: 0 0 48px 0;
    padding: 0 0 24px 0;
    border-bottom: 1px solid var(--rule);
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 30px;
    align-items: end;
  }
  @media (max-width: 640px) { .identity-header { grid-template-columns: 1fr; } }
  .identity-header .name {
    font-family: var(--serif);
    font-variation-settings: "opsz" 72, "wght" 500;
    font-size: clamp(32px, 4.8vw, 44px);
    line-height: 1.02;
    letter-spacing: -0.022em;
    margin: 0 0 6px 0;
    color: var(--ink);
  }
  .identity-header .role {
    font-family: var(--sans);
    font-size: 15px;
    color: var(--ink-soft);
    margin: 0 0 3px 0;
  }
  .identity-header .loc {
    font-family: var(--mono);
    font-size: 11.5px;
    letter-spacing: 0.08em;
    color: var(--ink-muted);
    text-transform: uppercase;
  }
  .identity-header .tagline {
    font-family: var(--serif);
    font-style: italic;
    font-variation-settings: "opsz" 24, "wght" 400;
    font-size: 15.5px;
    color: var(--ink-soft);
    margin: 8px 0 0 0;
    max-width: 50ch;
  }
  .identity-header .contact {
    font-family: var(--mono);
    font-size: 11px;
    line-height: 1.85;
    letter-spacing: 0.02em;
    color: var(--ink-soft);
    text-align: right;
  }
  @media (max-width: 640px) { .identity-header .contact { text-align: left; } }
  .identity-header .contact a { color: var(--ink); text-decoration: underline; text-underline-offset: 2px; }
  .identity-header .contact b { font-family: var(--serif); font-style: normal; font-weight: 500; color: var(--accent); font-size: 10px; letter-spacing: 0.2em; display: block; margin-bottom: 4px; text-transform: uppercase; }

  .identity-sig {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ink-muted);
    margin: 0 0 22px 0;
    padding: 0 0 16px 0;
    border-bottom: 1px dotted var(--rule);
  }
  .identity-sig b { color: var(--ink); font-family: var(--serif); font-size: 13px; letter-spacing: -0.01em; text-transform: none; font-weight: 500; }

  /* ---- HR-facing additions ---- */

  /* Shipped artifacts */
  .shipped-list { margin: 24px 0 0 0; border-top: 2px solid var(--ink); }
  .shipped-item {
    padding: 22px 0;
    border-bottom: 1px solid var(--rule);
    display: grid;
    grid-template-columns: 160px 1fr 120px;
    gap: 24px;
    align-items: start;
  }
  @media (max-width: 720px) {
    .shipped-item { grid-template-columns: 1fr; gap: 8px; }
  }
  .shipped-item .proj {
    font-family: var(--serif);
    font-variation-settings: "opsz" 24, "wght" 500;
    font-size: 17px;
    color: var(--ink);
    line-height: 1.3;
  }
  .shipped-item .proj-sub {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.06em;
    color: var(--ink-muted);
    margin-top: 4px;
    text-transform: uppercase;
  }
  .shipped-item .desc {
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.55;
    color: var(--ink-soft);
  }
  .shipped-item .stats {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.04em;
    color: var(--ink-muted);
    text-align: right;
    line-height: 1.7;
  }
  @media (max-width: 720px) {
    .shipped-item .stats { text-align: left; }
  }

  /* Public artifacts */
  .artifact-row {
    padding: 14px 0;
    border-bottom: 1px solid var(--rule);
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 20px;
    align-items: baseline;
  }
  .artifact-row:first-of-type { border-top: 2px solid var(--ink); }
  .artifact-row .name {
    font-family: var(--serif);
    font-size: 17px;
    font-variation-settings: "opsz" 24, "wght" 500;
  }
  .artifact-row .desc {
    font-family: var(--sans);
    font-size: 14px;
    color: var(--ink-soft);
    margin-top: 3px;
  }
  .artifact-row .link {
    font-family: var(--mono);
    font-size: 11.5px;
    letter-spacing: 0.04em;
  }

  .overall-strip {
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.06em;
    color: var(--ink-soft);
    padding: 18px 0 28px 0;
    border-bottom: 2px solid var(--ink);
    text-transform: uppercase;
  }
  .overall-strip b {
    font-family: var(--serif);
    font-size: 22px;
    color: var(--ink);
    letter-spacing: -0.02em;
    text-transform: none;
  }

  /* §03 block */
  #peer-review {
    background: rgba(255,250,240,0.55);
    border-left: 2px solid var(--accent);
    padding: 28px 34px 30px 34px;
    margin: 24px 0 0 0;
    font-size: 17px;
    line-height: 1.65;
  }
  #peer-review h3 {
    font-family: var(--serif);
    font-variation-settings: "opsz" 24, "wght" 500;
    font-size: 17px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--accent);
    margin: 28px 0 14px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--rule-soft);
  }
  #peer-review h3:first-child { margin-top: 0; }
  #peer-review ol { padding-left: 20px; margin: 0; }
  #peer-review ol li {
    margin: 14px 0;
    padding-left: 6px;
  }
  #peer-review ol li::marker { color: var(--accent); font-family: var(--mono); font-size: 0.85em; }

  /* Charts */
  .chart-box {
    background: rgba(255,250,240,0.4);
    border: 1px solid var(--rule);
    padding: var(--space-9) var(--space-10) var(--space-7) var(--space-10);
    margin: var(--space-10) 0;
    height: 340px;     /* fixed chart area; not a spacing token */
    position: relative;
  }
  .chart-box.tall { height: 420px; }
  .chart-box.short { height: 260px; }
  .chart-box canvas {
    display: block;
    width: 100%;
    height: 100%;
  }
  .chart-box::after {
    content: attr(data-fig);
    position: absolute;
    top: -8px; right: var(--space-9);
    background: var(--paper);
    padding: 0 var(--space-4);
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.2em;
    color: var(--ink-muted);
    text-transform: uppercase;
  }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  @media (max-width: 700px) { .two-col { grid-template-columns: 1fr; } }

  /* §06 evidence library */
  details.evidence {
    border-top: 1px solid var(--rule);
    padding: var(--space-7) 0;
    margin: 0;
  }
  details.evidence:last-of-type { border-bottom: 1px solid var(--rule); }
  details.evidence summary {
    cursor: pointer;
    list-style: none;
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.4;
    color: var(--ink);
    display: grid;
    grid-template-columns: 90px 1fr 80px;   /* summary tri-column layout */
    gap: var(--space-8);
    align-items: center;
  }
  details.evidence summary::-webkit-details-marker { display: none; }
  details.evidence summary .tag {
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink-muted);
    padding: var(--tag-padding-y) var(--tag-padding-x);   /* 2px 6px, intentional -1/-2px from orig 3/8 */
    border: 1px solid var(--rule);
    text-align: center;
    border-radius: 1px;
  }
  details.evidence summary .tag.high_friction,
  details.evidence summary .tag.not_achieved { color: var(--oxblood); border-color: var(--oxblood); }
  details.evidence summary .tag.control_good { color: var(--forest); border-color: var(--forest); }
  details.evidence summary .tag.top_interrupt { color: var(--ochre); border-color: var(--ochre); }
  details.evidence summary .tag.top_token { color: var(--plum); border-color: var(--plum); }
  details.evidence summary .sid {
    font-family: var(--mono);
    font-size: var(--text-sm);
    color: var(--ink-soft);
  }
  details.evidence summary .proj { color: var(--ink); }
  details.evidence summary .right {
    text-align: right;
    font-family: var(--mono);
    font-size: 11.5px;
    color: var(--ink-muted);
  }
  details.evidence[open] summary { margin-bottom: var(--space-7); }
  details.evidence[open] summary .sid { color: var(--accent); }
  details.evidence p {
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.55;
    margin: var(--space-3) 0;
    padding-left: 106px;     /* aligns after summary's 90px col + space-8 gap */
  }
  details.evidence p code {
    font-size: 0.85em;
    background: rgba(0,0,0,0.04);
    color: var(--ink-soft);
    word-break: break-all;
  }

  .evidence-header {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 34px 0 var(--space-4) 0;     /* 34px = component-unique top gap */
    padding-bottom: var(--space-3);
    border-bottom: 1px solid var(--rule);
  }

  /* Footer */
  footer {
    margin-top: 80px;
    padding-top: 30px;
    border-top: 1px solid var(--rule);
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.06em;
    color: var(--ink-muted);
    text-align: center;
  }
  footer a { color: var(--accent); }

  /* §07 methodology */
  .method {
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.6;
  }
  .method ul { padding-left: var(--space-10); margin: var(--space-4) 0 var(--space-7) 0; }
  .method li { margin: var(--space-2) 0; }
  .caveat {
    background: rgba(160, 67, 30, 0.06);
    border: 1px solid rgba(160, 67, 30, 0.2);
    border-left: 3px solid var(--accent);
    padding: var(--space-7) var(--space-10);
    margin: var(--space-8) 0;
    font-size: 14px;
    line-height: 1.6;
  }

  /* print */
  @media print {
    body { font-size: 11pt; }
    .page { padding: 0; max-width: none; }
    .chart-box { break-inside: avoid; }
    details.evidence { break-inside: avoid; }
    details.evidence[open] { break-inside: avoid; }
  }

  /* --- Direction-C foundation (AI work ledger, V5) ---
     Tokens + component classes only in this phase; section builders that
     consume them land in a later task. Values copied from the approved
     mock docs/superpowers/specs/mocks/mock-c-business-report.html. */
  :root {
    --c-gold: #B08A2E;
    --c-gold-deep: #7E6119;
    --c-gold-soft: rgba(176,138,46,0.12);
    --c-neg: #9C201A;
    --c-src-0: var(--c-gold);
    --c-src-1: #5C5850;
    --c-src-2: #918C82;
    --c-src-3: #7E6119;
    --c-src-4: #26231E;
    --c-src-5: #C9C4B8;
  }
  .c-src-0 { color: var(--c-src-0); background: var(--c-src-0); }
  .c-src-1 { color: var(--c-src-1); background: var(--c-src-1); }
  .c-src-2 { color: var(--c-src-2); background: var(--c-src-2); }
  .c-src-3 { color: var(--c-src-3); background: var(--c-src-3); }
  .c-src-4 { color: var(--c-src-4); background: var(--c-src-4); }
  .c-src-5 { color: var(--c-src-5); background: var(--c-src-5); }
  .c-exhibit { margin: 30px 0 6px; }
  .c-exhibit-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 14px; }
  .c-exhibit-no { font-size: 11.5px; font-weight: 800; letter-spacing: 0.14em;
                  color: var(--c-gold-deep); white-space: nowrap; }
  .c-exhibit-t { font-size: 14px; font-weight: 600; }
  .c-exhibit-src { font-size: 11.5px; opacity: 0.65; margin-top: 10px; }
  .c-finding { display: grid; grid-template-columns: 64px 1fr; gap: 20px;
               padding: 18px 0; border-bottom: 1px solid rgba(128,128,128,0.25); }
  .c-finding-no { font-size: 30px; font-weight: 800; color: var(--c-gold); line-height: 1.2; }
  .c-finding-head { font-size: 19px; font-weight: 700; line-height: 1.6; }
  .c-neg-num { color: var(--c-neg); }
  .c-sec-title { font-size: 23px; font-weight: 800; line-height: 1.5; max-width: 30em; }
  .c-kicker { font-size: 12.5px; letter-spacing: 0.22em; color: var(--c-gold-deep); font-weight: 700; }
  .c-source-cards { display: flex; gap: 12px; flex-wrap: wrap; margin: 14px 0; }
  .c-source-card { border: 1px solid rgba(128,128,128,0.3); padding: 10px 14px;
                   font-size: 13px; min-width: 150px; }
  .c-source-card--absent { opacity: 0.55; border-style: dashed; }
  .c-share-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 12.5px; }
  .c-share-bar { display: flex; height: 14px; flex: 1; }
  .c-share-seg { height: 100%; }
  .c-h2h { display: grid; grid-template-columns: 1fr 1fr; gap: 0; border: 1px solid rgba(128,128,128,0.3); }
  .c-h2h > div { padding: 14px 18px; }
  .c-h2h .num { font-size: 22px; font-weight: 800; }
  .c-blindspot { border-left: 3px solid var(--c-gold); background: var(--c-gold-soft);
                 padding: 12px 16px; margin: 16px 0; color: inherit; }
  .c-blindspot-label { display: inline-block; font-size: 10.5px; font-weight: 800;
                        letter-spacing: 0.12em; text-transform: uppercase;
                        color: var(--c-gold-deep); background: rgba(176,138,46,0.18);
                        padding: 2px 8px; border-radius: 3px; margin-bottom: 6px; }
  .c-blindspot strong { display: block; font-size: 15px; margin: 4px 0 6px; }
  .c-blindspot-metric { font-size: 13.5px; font-variant-numeric: tabular-nums; }
  .c-blindspot-detail { font-size: 12.5px; opacity: 0.75; margin-top: 6px;
                         font-style: italic; }
  .c-leak-cards { display: flex; gap: 14px; flex-wrap: wrap; margin: 8px 0; }
  .c-leak-card { border: 1px solid rgba(128,128,128,0.3); padding: 14px 16px;
                 min-width: 220px; flex: 1 1 220px; }
  .c-leak-type { font-size: 12px; font-weight: 700; letter-spacing: 0.04em;
                 text-transform: uppercase; opacity: 0.75; }
  .c-leak-cost { font-size: 24px; font-weight: 800; color: var(--c-gold-deep);
                 font-variant-numeric: tabular-nums; margin: 4px 0; }
  .c-leak-meta { font-size: 12px; opacity: 0.7; }
  .c-leak-fix { font-size: 12.5px; border-top: 1px solid rgba(128,128,128,0.25);
                margin-top: 10px; padding-top: 8px; }
  .c-leak-fix span { font-weight: 700; }
  .c-trend-locked { font-size: 13px; opacity: 0.75; margin: 6px 0 0; }
  .c-trend-table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  .c-trend-table th, .c-trend-table td { text-align: right; padding: 6px 10px;
                     border-bottom: 1px solid rgba(128,128,128,0.25); font-size: 13px; }
  .c-trend-table th:first-child, .c-trend-table td:first-child { text-align: left; }
  .c-trend-table thead th { font-size: 11px; letter-spacing: 0.05em;
                     text-transform: uppercase; opacity: 0.7; }
  .c-spark { color: var(--c-gold); vertical-align: middle; }
  .c-secondary { font-size: 13px; margin-top: 18px; }
  .c-secondary h3 { font-size: 13px; letter-spacing: 0.06em; text-transform: uppercase;
                     opacity: 0.7; margin-bottom: 6px; }
  .c-secondary ul { margin: 0; padding-left: 20px; }
  .c-secondary li { margin: 4px 0; }
  .c-badge-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; margin-top: 14px; }
  .c-badge { border: 1px solid rgba(128,128,128,0.3); border-top: 3px solid #B08A2E; padding: 12px 14px; }
  .c-badge-name { font-weight: 700; font-size: 15px; color: #7E6119; }
  .c-badge-criteria { font-size: 12.5px; margin-top: 6px; }
  .c-badge-evidence { font-size: 11.5px; opacity: 0.65; margin-top: 8px; font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<main class="page">

<div class="letterhead">
  <div>
    <div class="mark">CC · User Autopsy · v1</div>
  </div>
  <div class="right">
    <b>$total_sessions</b> $letterhead_sessions_analyzed<br>
    $date_first → $date_last<br>
    $letterhead_facet_coverage <b>$facets_coverage%</b>
  </div>
</div>

$ledger_sections

$identity_block

$hero_block

$badges_section

$profile_section

$hr_activity_block

$how_to_read_section

$shipped_section

$artifacts_section

<nav class="toc">
  $toc_links
</nav>

$overview_section

$plain_intro_block

$diagnosis_block

$try_this_block

$case_study_block

$patterns_section

$trends_section

$evidence_section

$method_section

<footer>
  <div>cc-user-autopsy · <a href="https://github.com/Imbad0202/cc-user-autopsy">$footer_repo</a> · $footer_tagline</div>
</footer>

</main>

<script>
const I18N = $i18n_json;
const INK = '#1a1916';
const INK_SOFT = '#464239';
const MUTED = '#7a7363';
const RULE = '#c9bfa8';
const PAPER = '#f4efe6';
const PAPER_DEEP = '#ece5d5';
const ACCENT = '#a0431e';
const OCHRE = '#b28121';
const FOREST = '#2e5b3e';
const OXBLOOD = '#6b1b1b';
const PLUM = '#63355c';
const PAL = [ACCENT, FOREST, OCHRE, OXBLOOD, PLUM, '#516881', '#8a6f45', '#7a4f3e', '#4a6b5b', '#7b5f80', '#a06b45', '#5b6b7a'];
const FONT_SANS = '12px ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
const FONT_MONO = '11px ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace';
const FONT_MONO_SMALL = '10px ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace';
const renderers = [];

$chart_layout_js

function registerRenderer(fn) {
  renderers.push(fn);
}

function debounce(fn, wait) {
  let timer = null;
  return () => {
    clearTimeout(timer);
    timer = setTimeout(fn, wait);
  };
}

function setupCanvas(id) {
  const canvas = document.getElementById(id);
  if (!canvas) return null;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(280, Math.round(rect.width || canvas.parentElement.clientWidth || 280));
  const height = Math.max(200, Math.round(rect.height || canvas.parentElement.clientHeight || 200));
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.textBaseline = 'middle';
  return { canvas, ctx, width, height };
}

function drawNoData(ctx, width, height, text) {
  ctx.fillStyle = MUTED;
  ctx.font = FONT_MONO;
  ctx.textAlign = 'center';
  ctx.fillText(text !== undefined ? text : I18N.chart_no_data, width / 2, height / 2);
}

function niceMax(value) {
  if (!value || value <= 0) return 1;
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  const normalized = value / magnitude;
  if (normalized <= 1) return magnitude;
  if (normalized <= 2) return 2 * magnitude;
  if (normalized <= 5) return 5 * magnitude;
  return 10 * magnitude;
}

function ticksFor(maxValue, count = 4) {
  const safeMax = niceMax(maxValue);
  const step = safeMax / count;
  const ticks = [];
  for (let i = 0; i <= count; i += 1) ticks.push(step * i);
  return ticks;
}

function formatTick(value) {
  if (value >= 1000000) return (value / 1000000).toFixed(1) + 'M';
  if (value >= 1000) return (value / 1000).toFixed(1) + 'k';
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(1);
}

function labelStep(count) {
  return Math.max(1, Math.ceil(count / 8));
}

function drawLegend(ctx, items, x, y, width) {
  let cursorX = x;
  let cursorY = y;
  const box = 10;
  const rowHeight = 18;
  ctx.font = FONT_MONO_SMALL;
  ctx.textAlign = 'left';
  items.forEach((item) => {
    const textWidth = ctx.measureText(item.label).width;
    if (cursorX + box + 8 + textWidth > x + width) {
      cursorX = x;
      cursorY += rowHeight;
    }
    ctx.fillStyle = item.color;
    ctx.fillRect(cursorX, cursorY - box / 2, box, box);
    ctx.fillStyle = MUTED;
    ctx.fillText(item.label, cursorX + box + 6, cursorY);
    cursorX += box + 12 + textWidth;
  });
  return cursorY + 8;
}

function drawPlotFrame(ctx, plot, ticks, formatter, rightTicks = null, rightFormatter = null) {
  ctx.strokeStyle = RULE;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(plot.left, plot.top);
  ctx.lineTo(plot.left, plot.top + plot.height);
  ctx.lineTo(plot.left + plot.width, plot.top + plot.height);
  ctx.stroke();

  ctx.font = FONT_MONO_SMALL;
  ctx.textAlign = 'right';
  ctx.fillStyle = MUTED;
  ticks.forEach((tick) => {
    const y = plot.top + plot.height - (tick.value * plot.height);
    ctx.strokeStyle = 'rgba(0,0,0,0.04)';
    ctx.beginPath();
    ctx.moveTo(plot.left, y);
    ctx.lineTo(plot.left + plot.width, y);
    ctx.stroke();
    ctx.fillText(formatter(tick.raw), plot.left - 8, y);
  });

  if (rightTicks && rightFormatter) {
    ctx.textAlign = 'left';
    rightTicks.forEach((tick) => {
      const y = plot.top + plot.height - (tick.value * plot.height);
      ctx.fillText(rightFormatter(tick.raw), plot.left + plot.width + 8, y);
    });
  }
}

function drawXAxisLabels(ctx, labels, plot) {
  const step = labelStep(labels.length);
  const groupWidth = plot.width / Math.max(labels.length, 1);
  ctx.save();
  ctx.font = FONT_MONO_SMALL;
  ctx.fillStyle = MUTED;
  const measure = (s) => ctx.measureText(s).width;
  // Collect labels we'll actually render (after step filter) and check
  // whether they all fit horizontally within their group slot. If yes,
  // draw horizontally (cleaner). If no, fall back to -45deg rotation.
  const toDraw = [];
  for (let i = 0; i < labels.length; i += 1) {
    if (i % step !== 0 && i !== labels.length - 1) continue;
    toDraw.push(i);
  }
  const horizontalBudget = groupWidth * 0.9;
  let maxWidth = 0;
  for (const i of toDraw) {
    const w = measure(labels[i]);
    if (w > maxWidth) maxWidth = w;
  }
  const horizontal = maxWidth <= horizontalBudget;
  if (horizontal) {
    ctx.textAlign = 'center';
    for (const i of toDraw) {
      const x = slotCenterX(i, labels.length, plot);
      const y = plot.top + plot.height + 14;
      ctx.fillText(labels[i], x, y);
    }
  } else {
    ctx.textAlign = 'right';
    // Per-label budget along the rotated axis: at -45deg the label rises
    // into the gap between adjacent ticks, so width budget is
    // groupWidth / cos(45).
    const labelBudget = Math.max(40, (groupWidth / Math.SQRT1_2) * 0.95);
    for (const i of toDraw) {
      const x = slotCenterX(i, labels.length, plot);
      const y = plot.top + plot.height + 14;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(-Math.PI / 4);
      ctx.fillText(clipLabelToWidth(labels[i], labelBudget, measure), 0, 0);
      ctx.restore();
    }
  }
  ctx.restore();
}

function drawDonutChart(id, labels, values, colors) {
  registerRenderer(() => {
    const setup = setupCanvas(id);
    if (!setup) return;
    const { ctx, width, height } = setup;
    const total = values.reduce((sum, value) => sum + value, 0);
    if (!total) {
      drawNoData(ctx, width, height);
      return;
    }
    const cx = Math.min(width * 0.36, width - 180);
    const cy = height / 2;
    const radius = Math.min(width * 0.18, height * 0.34);
    const innerRadius = radius * 0.62;
    let angle = -Math.PI / 2;
    values.forEach((value, index) => {
      const next = angle + (Math.PI * 2 * value) / total;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, angle, next);
      ctx.arc(cx, cy, innerRadius, next, angle, true);
      ctx.closePath();
      ctx.fillStyle = colors[index % colors.length];
      ctx.fill();
      angle = next;
    });
    ctx.fillStyle = INK;
    ctx.font = '600 22px Georgia, serif';
    ctx.textAlign = 'center';
    ctx.fillText(String(total), cx, cy - 6);
    ctx.fillStyle = MUTED;
    ctx.font = FONT_MONO;
    ctx.fillText(I18N.chart_rated, cx, cy + 16);

    const SWATCH_D = 12;  // swatch circle diameter (was ~10px fillRect)
    const SWATCH_GAP = 8; // gap between swatch and label text
    ctx.textAlign = 'left';
    ctx.font = FONT_MONO_SMALL;
    const measure = (s) => ctx.measureText(s).width;
    // Build the full label strings to measure them accurately.
    const fullLabels = labels.map((label, i) => `${label} (${values[i]})`);
    const layout = computeLegendWidth(fullLabels, measure, SWATCH_D, SWATCH_GAP);
    // legendX: right of the donut + gap; never eat into the donut itself.
    const legendX = Math.max(cx + radius + 32, width * 0.54);
    // legendBudget: actual pixel space from legendX to canvas right edge,
    // minus the swatch + gap overhead. Use the measured label width as the
    // minimum so labels are never under-allocated.
    const legendBudget = Math.max(
      layout.labelWidth,
      width - legendX - SWATCH_D - SWATCH_GAP - 8,
    );
    let legendY = Math.max(SWATCH_D, cy - layout.totalHeight / 2) + layout.rowHeight * 0.7;
    fullLabels.forEach((full, index) => {
      // Draw swatch as a filled circle for better visual clarity.
      ctx.fillStyle = colors[index % colors.length];
      ctx.beginPath();
      ctx.arc(legendX + SWATCH_D / 2, legendY - SWATCH_D * 0.3, SWATCH_D / 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = INK_SOFT;
      ctx.fillText(clipLabelToWidth(full, legendBudget, measure), legendX + SWATCH_D + SWATCH_GAP, legendY);
      legendY += layout.rowHeight;
    });
  });
}

function drawGroupedBarChart(id, labels, datasets, colors, legendLabels) {
  registerRenderer(() => {
    const setup = setupCanvas(id);
    if (!setup) return;
    const { ctx, width, height } = setup;
    const maxValue = Math.max(0, ...datasets.flat());
    if (!maxValue) {
      drawNoData(ctx, width, height);
      return;
    }
    const legendBottom = drawLegend(
      ctx,
      legendLabels.map((label, index) => ({ label, color: colors[index % colors.length] })),
      18,
      18,
      width - 36,
    );
    ctx.save();
    ctx.font = FONT_MONO_SMALL;
    const measure = (s) => ctx.measureText(s).width;
    const yMax = niceMax(maxValue);
    const ticks = ticksFor(yMax).map((raw) => ({ raw, value: raw / yMax }));
    const yAxisMaxTickLabel = formatTick(yMax);
    const plot = computeBarPlot({
      width, height, legendBottom, labels, charWidth: measure, yAxisMaxTickLabel,
    });
    ctx.restore();
    drawPlotFrame(ctx, plot, ticks, formatTick);
    const groupWidth = plot.width / Math.max(labels.length, 1);
    const innerWidth = groupWidth * 0.72;
    const barWidth = (innerWidth / datasets.length) * 0.82;
    datasets.forEach((dataset, seriesIndex) => {
      dataset.forEach((value, index) => {
        const x = plot.left + groupWidth * index + (groupWidth - innerWidth) / 2 + seriesIndex * (innerWidth / datasets.length);
        const heightValue = (value / yMax) * plot.height;
        const y = plot.top + plot.height - heightValue;
        ctx.fillStyle = colors[seriesIndex % colors.length];
        ctx.fillRect(x, y, barWidth, heightValue);
      });
    });
    drawXAxisLabels(ctx, labels, plot);
  });
}

function drawHorizontalBarChart(id, labels, values, color) {
  registerRenderer(() => {
    const setup = setupCanvas(id);
    if (!setup) return;
    const { ctx, width, height } = setup;
    const maxValue = Math.max(0, ...values);
    if (!maxValue) {
      drawNoData(ctx, width, height);
      return;
    }
    const plot = { left: 170, top: 18, width: width - 196, height: height - 42 };
    const xMax = niceMax(maxValue);
    const ticks = ticksFor(xMax);
    ctx.strokeStyle = RULE;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(plot.left, plot.top);
    ctx.lineTo(plot.left, plot.top + plot.height);
    ctx.lineTo(plot.left + plot.width, plot.top + plot.height);
    ctx.stroke();
    ctx.font = FONT_MONO_SMALL;
    ctx.fillStyle = MUTED;
    ctx.textAlign = 'center';
    ticks.forEach((raw) => {
      const x = plot.left + (raw / xMax) * plot.width;
      ctx.strokeStyle = 'rgba(0,0,0,0.04)';
      ctx.beginPath();
      ctx.moveTo(x, plot.top);
      ctx.lineTo(x, plot.top + plot.height);
      ctx.stroke();
      ctx.fillText(formatTick(raw), x, plot.top + plot.height + 12);
    });
    const barHeight = (plot.height / labels.length) * 0.62;
    labels.forEach((label, index) => {
      const y = plot.top + (plot.height / labels.length) * index + (plot.height / labels.length) / 2;
      const widthValue = (values[index] / xMax) * plot.width;
      ctx.fillStyle = color;
      ctx.fillRect(plot.left, y - barHeight / 2, widthValue, barHeight);
      ctx.fillStyle = INK_SOFT;
      ctx.textAlign = 'right';
      ctx.fillText(label, plot.left - 10, y);
      ctx.textAlign = 'left';
      ctx.fillStyle = MUTED;
      ctx.fillText(formatTick(values[index]), plot.left + widthValue + 6, y);
    });
  });
}

function drawLinePath(ctx, points, color, dashed = false, fill = false) {
  if (!points.length) return;
  const runs = segmentsWithoutNulls(points);
  if (!runs.length) return;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.setLineDash(dashed ? [6, 4] : []);
  if (fill) {
    runs.forEach((run) => {
      ctx.beginPath();
      ctx.moveTo(run[0].x, run[0].baseY);
      run.forEach((point) => ctx.lineTo(point.x, point.y));
      ctx.lineTo(run[run.length - 1].x, run[run.length - 1].baseY);
      ctx.closePath();
      ctx.fillStyle = color + '22';
      ctx.fill();
    });
  }
  runs.forEach((run) => {
    ctx.beginPath();
    ctx.moveTo(run[0].x, run[0].y);
    run.forEach((point) => ctx.lineTo(point.x, point.y));
    ctx.stroke();
  });
  ctx.setLineDash([]);
  ctx.fillStyle = color;
  runs.forEach((run) => {
    run.forEach((point) => {
      ctx.beginPath();
      ctx.arc(point.x, point.y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    });
  });
  ctx.restore();
}

function drawLineChart(id, labels, series, options = {}) {
  registerRenderer(() => {
    const setup = setupCanvas(id);
    if (!setup) return;
    const { ctx, width, height } = setup;
    const allValues = series.flatMap((item) => item.data.filter((v) => v !== null && v !== undefined && !Number.isNaN(v)));
    const maxValue = options.maxValue !== undefined ? options.maxValue : Math.max(0, ...allValues);
    if (!maxValue) {
      drawNoData(ctx, width, height);
      return;
    }
    const legendBottom = drawLegend(ctx, series.map((item) => ({ label: item.label, color: item.color })), 18, 18, width - 36);
    const yMax = options.maxValue !== undefined ? options.maxValue : niceMax(maxValue);
    ctx.save();
    ctx.font = FONT_MONO_SMALL;
    const measure = (s) => ctx.measureText(s).width;
    const yAxisMaxTickLabel = (options.formatter || formatTick)(yMax);
    const plot = computeBarPlot({ width, height, legendBottom, labels, charWidth: measure, yAxisMaxTickLabel });
    ctx.restore();
    const ticks = ticksFor(yMax).map((raw) => ({ raw, value: raw / yMax }));
    drawPlotFrame(ctx, plot, ticks, options.formatter || formatTick);
    // uses centered slot math; same function used by drawXAxisLabels so points align with labels
    series.forEach((item) => {
      const points = item.data.map((value, index) => ({
        x: slotCenterX(index, labels.length, plot),
        y: plot.top + plot.height - (value / yMax) * plot.height,
        baseY: plot.top + plot.height,
      }));
      drawLinePath(ctx, points, item.color, item.dashed, item.fill);
    });
    drawXAxisLabels(ctx, labels, plot);
  });
}

function drawDualChart(id, labels, bars, line, options = {}) {
  registerRenderer(() => {
    const setup = setupCanvas(id);
    if (!setup) return;
    const { ctx, width, height } = setup;
    const leftMax = options.leftMax !== undefined ? options.leftMax : niceMax(Math.max(0, ...line.data.filter((v) => v !== null && v !== undefined && !Number.isNaN(v))));
    const rightMax = options.rightMax !== undefined ? options.rightMax : niceMax(Math.max(0, ...bars.data.filter((v) => v !== null && v !== undefined && !Number.isNaN(v))));
    if (!leftMax && !rightMax) {
      drawNoData(ctx, width, height);
      return;
    }
    const legendBottom = drawLegend(
      ctx,
      [{ label: bars.label, color: bars.color }, { label: line.label, color: line.color }],
      18,
      18,
      width - 36,
    );
    ctx.save();
    ctx.font = FONT_MONO_SMALL;
    const measure = (s) => ctx.measureText(s).width;
    // For dual-axis: pick whichever tick label is WIDER in pixels (not char count —
    // '%' and digits can have different widths in some fonts).
    const leftTickLabel = (options.leftFormatter || formatTick)(leftMax);
    const rightTickLabel = (options.rightFormatter || formatTick)(rightMax);
    const yAxisMaxTickLabel = measure(leftTickLabel) >= measure(rightTickLabel) ? leftTickLabel : rightTickLabel;
    const plot = computeBarPlot({ width, height, legendBottom, labels, charWidth: measure, yAxisMaxTickLabel });
    ctx.restore();
    const leftTicks = ticksFor(leftMax).map((raw) => ({ raw, value: raw / leftMax }));
    const rightTicks = ticksFor(rightMax).map((raw) => ({ raw, value: raw / rightMax }));
    drawPlotFrame(ctx, plot, leftTicks, options.leftFormatter || formatTick, rightTicks, options.rightFormatter || formatTick);
    const groupWidth = plot.width / Math.max(labels.length, 1);
    const barWidth = groupWidth * 0.42;
    bars.data.forEach((value, index) => {
      const x = plot.left + groupWidth * index + (groupWidth - barWidth) / 2;
      const heightValue = (value / rightMax) * plot.height;
      ctx.fillStyle = bars.color;
      ctx.fillRect(x, plot.top + plot.height - heightValue, barWidth, heightValue);
    });
    // uses centered slot math; same function used by drawXAxisLabels so points align with labels
    const points = line.data.map((value, index) => ({
      x: slotCenterX(index, labels.length, plot),
      y: plot.top + plot.height - (value / leftMax) * plot.height,
      baseY: plot.top + plot.height,
    }));
    drawLinePath(ctx, points, line.color, line.dashed, line.fill);
    drawXAxisLabels(ctx, labels, plot);
  });
}

function drawDualLineChart(id, labels, leftSeries, rightSeries, options = {}) {
  registerRenderer(() => {
    const setup = setupCanvas(id);
    if (!setup) return;
    const { ctx, width, height } = setup;
    const leftMax = options.leftMax !== undefined ? options.leftMax : niceMax(Math.max(0, ...leftSeries.data.filter((v) => v !== null && v !== undefined && !Number.isNaN(v))));
    const rightMax = options.rightMax !== undefined ? options.rightMax : niceMax(Math.max(0, ...rightSeries.data.filter((v) => v !== null && v !== undefined && !Number.isNaN(v))));
    if (!leftMax && !rightMax) {
      drawNoData(ctx, width, height);
      return;
    }
    const legendBottom = drawLegend(
      ctx,
      [{ label: leftSeries.label, color: leftSeries.color }, { label: rightSeries.label, color: rightSeries.color }],
      18,
      18,
      width - 36,
    );
    ctx.save();
    ctx.font = FONT_MONO_SMALL;
    const measure = (s) => ctx.measureText(s).width;
    // For dual-axis: pick whichever tick label is WIDER in pixels (not char count —
    // '%' and digits can have different widths in some fonts).
    const leftTickLabel = (options.leftFormatter || formatTick)(leftMax);
    const rightTickLabel = (options.rightFormatter || formatTick)(rightMax);
    const yAxisMaxTickLabel = measure(leftTickLabel) >= measure(rightTickLabel) ? leftTickLabel : rightTickLabel;
    const plot = computeBarPlot({ width, height, legendBottom, labels, charWidth: measure, yAxisMaxTickLabel });
    ctx.restore();
    const leftTicks = ticksFor(leftMax).map((raw) => ({ raw, value: raw / leftMax }));
    const rightTicks = ticksFor(rightMax).map((raw) => ({ raw, value: raw / rightMax }));
    drawPlotFrame(ctx, plot, leftTicks, options.leftFormatter || formatTick, rightTicks, options.rightFormatter || formatTick);
    // uses centered slot math; same function used by drawXAxisLabels so points align with labels
    const leftPoints = leftSeries.data.map((value, index) => ({
      x: slotCenterX(index, labels.length, plot),
      y: plot.top + plot.height - (value / leftMax) * plot.height,
      baseY: plot.top + plot.height,
    }));
    const rightPoints = rightSeries.data.map((value, index) => ({
      x: slotCenterX(index, labels.length, plot),
      y: plot.top + plot.height - (value / rightMax) * plot.height,
      baseY: plot.top + plot.height,
    }));
    drawLinePath(ctx, leftPoints, leftSeries.color, leftSeries.dashed, leftSeries.fill);
    drawLinePath(ctx, rightPoints, rightSeries.color, rightSeries.dashed, rightSeries.fill);
    drawXAxisLabels(ctx, labels, plot);
  });
}

function heatColor(value, maxValue) {
  if (!value) return 'rgba(201,191,168,0.25)';
  const ratio = value / maxValue;
  const r = Math.round(236 + (160 - 236) * ratio);
  const g = Math.round(229 + (67 - 229) * ratio);
  const b = Math.round(213 + (30 - 213) * ratio);
  return `rgb(${r},${g},${b})`;
}

function drawHeatmap(id, grid, rowLabels) {
  registerRenderer(() => {
    const setup = setupCanvas(id);
    if (!setup) return;
    const { ctx, width, height } = setup;
    const maxValue = Math.max(0, ...grid.flat());
    if (!maxValue) {
      drawNoData(ctx, width, height);
      return;
    }
    const plot = { left: 54, top: 18, width: width - 72, height: height - 48 };
    const cols = 24;
    const rows = rowLabels.length;
    const cellWidth = plot.width / cols;
    const cellHeight = plot.height / rows;
    ctx.strokeStyle = RULE;
    ctx.strokeRect(plot.left, plot.top, plot.width, plot.height);
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        ctx.fillStyle = heatColor(grid[row][col], maxValue);
        ctx.fillRect(plot.left + col * cellWidth, plot.top + row * cellHeight, cellWidth - 1, cellHeight - 1);
      }
    }
    ctx.font = FONT_MONO_SMALL;
    ctx.fillStyle = MUTED;
    ctx.textAlign = 'right';
    rowLabels.forEach((label, index) => {
      const y = plot.top + cellHeight * index + cellHeight / 2;
      ctx.fillText(label, plot.left - 8, y);
    });
    ctx.textAlign = 'center';
    for (let hour = 0; hour < cols; hour += 2) {
      const x = plot.left + cellWidth * hour + cellWidth / 2;
      ctx.fillText(`${hour}:00`, x, plot.top + plot.height + 12);
    }
  });
}

drawDonutChart('outcomeChart', $outcome_labels, $outcome_values, PAL);
drawDonutChart('stypeChart', $stype_labels, $stype_values, PAL);
drawGroupedBarChart('projChart', $proj_labels, [$proj_sessions, $proj_friction], [INK_SOFT, ACCENT], $proj_legend);
drawDualChart('plenChart', $plen_buckets, { label: I18N.series_session_count, data: $plen_n, color: INK_SOFT }, { label: I18N.series_good_rate_pct, data: $plen_good, color: FOREST, fill: false }, { leftMax: 100, leftFormatter: (value) => `${value}%` });
drawHorizontalBarChart('fricChart', $fric_labels, $fric_counts, OXBLOOD);
drawHorizontalBarChart('toolChart', $tool_labels, $tool_counts, INK);
drawHeatmap('heatChart', $heat_grid, $heat_labels);
drawGroupedBarChart('helpChart', $help_labels, [$help_values], PAL, [I18N.chart_count]);
drawLineChart('growthChart', $growth_labels, [
  { label: I18N.series_composite_score, data: $growth_composite, color: ACCENT, fill: true },
  { label: I18N.series_good_outcome_rate, data: $growth_good, color: FOREST, dashed: true },
  { label: I18N.series_task_agent_adoption, data: $growth_ta, color: PLUM, dashed: true },
], { maxValue: 100, formatter: (value) => `${value}%` });
drawLineChart('wkSessions', $wk_labels, [
  { label: I18N.series_sessions, data: $wk_sessions, color: INK, fill: true },
  { label: I18N.series_with_task_agent, data: $wk_ta, color: ACCENT, dashed: true },
]);
drawDualLineChart('wkTokens', $wk_labels, { label: I18N.series_tokens_m, data: $wk_tokens_m, color: OCHRE, fill: true }, { label: I18N.series_commits, data: $wk_commits, color: FOREST }, { leftFormatter: (value) => value.toFixed(1), rightFormatter: formatTick });
drawLineChart('wkGood', $wk_labels, [{ label: I18N.series_good_rate_pct, data: $wk_goodrate, color: FOREST, fill: true }], { maxValue: 100, formatter: (value) => `${value}%` });
drawGroupedBarChart('wkFric', $wk_labels, [$wk_friction], [OXBLOOD], [I18N.series_friction]);
drawLineChart('wkPlen', $wk_labels, [{ label: I18N.series_avg_prompt_length, data: $wk_plen, color: PLUM, fill: true }]);

function renderAll() {
  renderers.forEach((fn) => fn());
}

window.addEventListener('load', renderAll);
window.addEventListener('resize', debounce(renderAll, 120));
</script>
</body>
</html>
"""

def render(
    *,
    analysis: dict,
    samples_data: dict,
    peer_review_md: str,
    locale: str,
    audience: str,
    narrative,
    profile_info: dict = None,
    artifacts_list: list = None,
    public_set: set = None,
    category_map: dict = None,
    try_this_md: str = "",
    case_study_md: str = "",
    ledger_narration_md: str = "",
    history_entries: list = None,
) -> str:
    """Render the full HTML report and return it as a string.

    Parameters
    ----------
    analysis:       Loaded analysis-data.json dict.
    samples_data:   Loaded samples.json dict.
    peer_review_md: Peer-review markdown string (may be empty).
    locale:         Locale code, e.g. "en" or "zh_TW".
    audience:       "self" or "hr".
    narrative:      Narrative module loaded by the caller (_load_narrative).
    profile_info:   Optional identity info dict (from --profile JSON).
    artifacts_list: Optional public artifact list (from --artifacts JSON).
    public_set:     Optional set of allowlisted project names (from --public-projects).
    category_map:   Optional category override dict (from --public-projects).
    ledger_narration_md: Markdown with # opening / # output-ledger / # team-ledger
                    books (SELF only; written by the skill in Step 3).
    history_entries: Trend snapshots from read_history_snapshots() (SELF trend
                    ledger; ignored for HR).
    """
    pr_html = md_to_html(peer_review_md)

    # profile_info, artifacts_list, public_set, category_map provided by caller
    profile_info = profile_info or {}
    artifacts_list = artifacts_list or []
    public_set = public_set or set()
    category_map = category_map or {}
    redact = (audience == "hr")
    label_project = lambda name: display_project(name, redact, public_set, category_map, locale)
    is_public = lambda name: (not redact) or _matches_allowlist(name, public_set)
    badges_data = analysis.get("badges") or {}
    ledger_data = analysis.get("ledger") or {}

    meta = analysis["meta"]
    agg = analysis["aggregates"]
    scores = analysis["scores"]

    total = meta["total_sessions"]
    total_tok = agg["tokens"]["total"]
    commits_total = sum(p["commits"] for p in agg["projects"].values())
    duration_hr = int(sum(p["duration_min"] for p in agg["projects"].values()) / 60)
    profile_for_rates = agg.get("profile_summary", {})
    ta_rate = int(round(profile_for_rates.get("ta_pct", 0)))
    mcp_rate = int(round(profile_for_rates.get("mcp_pct", 0)))

    # Chart series
    weekly = agg["weekly"]
    # Use week_label (e.g. "W15") for display; fall back to full "week" key
    # for older aggregate files that pre-date the week_label field.
    w_labels = [w.get("week_label", w["week"]) for w in weekly]

    # heatmap
    grid = [[0] * 24 for _ in range(7)]
    for k, v in agg["heatmap"].items():
        wd, hr = [int(x) for x in k.split(",")]
        grid[wd][hr] = v

    fric_top = list(agg["friction"]["totals"].items())[:12]
    tool_top = list(agg["tools"]["totals"].items())[:15]

    if redact:
        bucketed = {}
        for key, v in agg["projects"].items():
            display = label_project(v.get("label", key))
            b = bucketed.setdefault(display, {"sessions": 0, "friction": 0, "label": display})
            b["sessions"] += v.get("sessions", 0)
            b["friction"] += v.get("friction", 0)
        proj_items = sorted(bucketed.items(), key=lambda kv: -kv[1]["sessions"])[:12]
    else:
        proj_items = list(agg["projects"].items())[:12]

    plen_buckets = ["<20", "20-50", "50-100", "100-300", ">=300"]
    plen_good_pct = []
    plen_n = []
    for b in plen_buckets:
        d = agg["prompt_len_vs_outcome"].get(b, {})
        tot = sum(d.values())
        good = d.get("fully_achieved", 0) + d.get("mostly_achieved", 0)
        plen_good_pct.append(round(100 * good / tot, 1) if tot else 0)
        plen_n.append(tot)

    # Score rows (SELF only — recruiter v1, spec §4, drops the scoring grid
    # entirely in favor of earned badges, so this is never consumed by the
    # HR branch's diagnosis_block).
    score_rows = ""
    if audience != "hr":
        dim_titles = {
            "D1_delegation": t(locale, "score_d1"),
            "D2_root_cause": t(locale, "score_d2"),
            "D3_prompt_quality": t(locale, "score_d3"),
            "D4_context_mgmt": t(locale, "score_d4"),
            "D5_interrupt_judgment": t(locale, "score_d5"),
            "D6_tool_breadth": t(locale, "score_d6"),
            "D7_writing_consistency": t(locale, "score_d7"),
            "D8_time_mgmt": t(locale, "score_d8"),
            "D9_token_efficiency": t(locale, "score_d9"),
        }
        for key, title in dim_titles.items():
            s = scores.get(key, {})
            sc = s.get("score")
            band = score_band(sc)
            display = f'<span class="num">{sc}</span><span class="out">/ 10</span>' if sc is not None else 'n/a'
            dim_label = f"{key.split('_', 1)[0]} · {key.split('_', 1)[1].replace('_', ' ')}"
            dim_key = key.split('_', 1)[0].lower()  # "D1_delegation" -> "d1"
            exp_fn = getattr(narrative, f"{dim_key}_explanation", None)
            pat_fn = getattr(narrative, f"{dim_key}_pattern", None)
            if exp_fn is None:
                raise AttributeError(
                    f"narrative module {narrative.__name__} missing {dim_key}_explanation"
                )
            if pat_fn is None:
                raise AttributeError(
                    f"narrative module {narrative.__name__} missing {dim_key}_pattern"
                )
            reason = exp_fn(s) if sc is not None else s.get("reason", "")
            pattern_html = ""
            if s.get("pattern_emit"):
                pattern_html = f'\n    <p class="pattern">{esc(pat_fn(s))}</p>'
            score_rows += f'''<div class="score-row {band}">
      <div class="dim">{esc(dim_label)}</div>
      <div class="body">
    <div class="h">{esc(title)}</div>
    <p class="exp">{esc(reason)}</p>{pattern_html}
      </div>
      <div class="score">{display}</div>
    </div>
    '''

    overall = scores.get("_overall", {})
    overall_avg = overall.get("avg")
    if overall_avg is not None:
        overall_line = (
            f'<b>{overall_avg} / 10</b> &nbsp;·&nbsp; '
            f'{overall["dimensions_scored"]} of {overall["dimensions_total"]} dimensions scored'
        )
    else:
        overall_line = t(locale, "score_overall_low_data")

    # Evidence — claim-indexed for SELF, hidden for HR (Codex v3 review).
    evidence_html = ""
    if audience == "hr":
        # HR: hide evidence library entirely. Redacted sid + redacted project
        # name yields zero signal, looks forensic. Section is fully suppressed
        # (see PAGE_TEMPLATE conditional below).
        evidence_html = ""
    else:
        # SELF: group sample sessions by the peer-review CLAIM they support.
        # This makes evidence traceback fast: each claim shows 2-3 examples,
        # not a 24-card archive.
        def _hour_of(sid_meta):
            ts = sid_meta.get("start", "")
            if not ts or len(ts) < 13:
                return None
            try:
                # ISO 8601 UTC → tz offset 8 (Asia/Taipei) per meta tz_offset_hours
                hour_utc = int(ts[11:13])
                return (hour_utc + 8) % 24
            except ValueError:
                return None

        samples_with_meta = []
        for sid, info in samples_data.items():
            m = info.get("meta", {})
            samples_with_meta.append({"sid": sid, **info, "_hour": _hour_of(m)})

        # Bucket sessions into claims. A session can match multiple claims;
        # we keep dedup so the same sid does not appear twice.
        seen = set()
        def _pick(predicate, limit=3):
            picked = []
            for s in samples_with_meta:
                if s["sid"] in seen:
                    continue
                if predicate(s):
                    picked.append(s)
                    seen.add(s["sid"])
                    if len(picked) >= limit:
                        break
            return picked

        # Claim 1: afternoon sessions degrade. V4: not just hour, also requires
        # actual degradation signal (friction or non-good outcome).
        def _has_friction(s):
            fc = s.get("meta", {}).get("friction_counts") or {}
            return sum(fc.values()) >= 1
        def _not_good(s):
            return s.get("meta", {}).get("outcome") not in (
                "fully_achieved", "mostly_achieved", ""
            )
        claim_afternoon = _pick(
            lambda s: (
                s.get("_hour") is not None and 13 <= s["_hour"] <= 15
                and (_has_friction(s) or _not_good(s))
            ),
            limit=3,
        )
        # Claim 2: delegation strength — long multi-task, Task agent, fully_achieved.
        claim_delegation = _pick(
            lambda s: (
                s.get("meta", {}).get("uses_task_agent") and
                s.get("meta", {}).get("outcome") == "fully_achieved" and
                s.get("meta", {}).get("git_commits", 0) >= 3
            ),
            limit=3,
        )
        # Claim 3: meander — long sessions with high tokens but zero commits.
        claim_meander = _pick(
            lambda s: (
                s.get("meta", {}).get("total_tokens", 0) >= 100_000 and
                s.get("meta", {}).get("git_commits", 0) == 0
            ),
            limit=3,
        )
        # Claim 4: interrupt-as-redirect. V4: must be interrupted AND have
        # reached a good outcome — otherwise it does not prove the redirect was
        # successful.
        claim_interrupt = _pick(
            lambda s: (
                s.get("meta", {}).get("interrupts", 0) >= 1 and
                s.get("meta", {}).get("outcome") in (
                    "fully_achieved", "mostly_achieved"
                )
            ),
            limit=3,
        )

        claim_groups = [
            ("claim_afternoon_h", "claim_afternoon_intro", claim_afternoon),
            ("claim_delegation_h", "claim_delegation_intro", claim_delegation),
            ("claim_meander_h", "claim_meander_intro", claim_meander),
            ("claim_interrupt_h", "claim_interrupt_intro", claim_interrupt),
        ]

        for h_key, intro_key, sess_list in claim_groups:
            # V4: hide empty claim groups entirely. An apologetic "no sessions
            # match" line is weaker than showing fewer claims.
            if not sess_list:
                continue
            evidence_html += f'<div class="claim-header"><h3>{t(locale, h_key)}</h3><p class="claim-intro">{t(locale, intro_key)}</p></div>\n'
            for s in sess_list:
                m = s.get("meta", {})
                fp = (m.get("first_prompt", "") or "")[:300]
                fric = json.dumps(m.get("friction_counts") or {}, ensure_ascii=False)
                summary = m.get("brief_summary", "") or "(no summary)"
                frictxt = m.get("friction_detail", "") or "(none)"
                proj = m.get('project', '?')
                raw_outcome = m.get('outcome', '')
                outcome = narrative.outcome_label(raw_outcome) if raw_outcome else narrative.no_facet_label()
                tok_str = fmt(m.get('total_tokens', 0))
                dur = m.get('duration_min', 0)
                tag = s.get("tag", "control_good")
                evidence_html += f'''<details class="evidence">
      <summary>
    <span class="tag {tag}">{esc(narrative.evidence_badge(tag))}</span>
    <span><span class="sid">{esc(s["sid"][:8])}</span> · <span class="proj">{esc(proj)}</span> · {esc(outcome)}</span>
    <span class="right">{esc(tok_str)} {t(locale, "evidence_tok_unit")} · {esc(dur)}{t(locale, "evidence_dur_unit")}</span>
      </summary>
      <p><strong>{t(locale, "evidence_summary")}</strong> · {esc(summary)}</p>
      <p><strong>{t(locale, "evidence_friction_detail")}</strong> · {esc(frictxt)}</p>
      <p><strong>{t(locale, "evidence_first_prompt")}</strong> · <code>{esc(fp)}</code></p>
      <p><strong>{t(locale, "evidence_friction_counts")}</strong> · <code>{esc(fric)}</code></p>
    </details>
    '''

    preliminary_warning = (
        f'<div class="preliminary">{t(locale, "preliminary_warning")}</div>'
        if meta.get("data_thin_warning") else ''
    )

    # -------- Identity block (both audiences) --------
    identity_block = ""
    if profile_info:
        name = profile_info.get("name", "").strip()
        role = profile_info.get("role", "").strip()
        location = profile_info.get("location", "").strip()
        tagline = profile_info.get("tagline", "").strip()
        contact = profile_info.get("contact", {}) or {}
        links = profile_info.get("links", []) or []

        if audience == "hr":
            # full letterhead
            contact_lines = []
            if contact.get("email"):
                email = str(contact["email"]).strip()
                contact_lines.append(f'<a rel="noopener noreferrer" href="{esc(sanitize_url(f"mailto:{email}", allow_mailto=True))}">{esc(email)}</a>')
            if contact.get("github"):
                gh = str(contact["github"]).strip().lstrip("@")
                contact_lines.append(f'<a rel="noopener noreferrer" href="{esc(sanitize_url(f"https://github.com/{gh}"))}">github.com/{esc(gh)}</a>')
            if contact.get("twitter"):
                tw = str(contact["twitter"]).strip().lstrip("@")
                contact_lines.append(f'<a rel="noopener noreferrer" href="{esc(sanitize_url(f"https://twitter.com/{tw}"))}">@{esc(tw)}</a>')
            if contact.get("website"):
                w = sanitize_url(str(contact["website"]).strip())
                contact_lines.append(f'<a rel="noopener noreferrer" href="{esc(w)}">{esc(display_url(w))}</a>')
            for ln in links:
                lbl = str(ln.get("label", "")).strip()
                url = sanitize_url(str(ln.get("url", "")).strip())
                contact_lines.append(f'<a rel="noopener noreferrer" href="{esc(url)}">{esc(lbl)}</a>')
            contact_html = "<br>".join(contact_lines) if contact_lines else ""

            parts = []
            if name:
                parts.append(f'<div class="name">{esc(name)}</div>')
            if role:
                parts.append(f'<div class="role">{esc(role)}</div>')
            if location:
                parts.append(f'<div class="loc">{esc(location)}</div>')
            if tagline:
                parts.append(f'<div class="tagline">"{esc(tagline)}"</div>')

            identity_block = f'''<header class="identity-header">
      <div>
    {"".join(parts)}
      </div>
      <div class="contact">
    {'<b>Contact</b>' if contact_html else ''}
    {contact_html}
      </div>
    </header>'''
        else:
            # self version — subtle single-line signature
            sig_parts = []
            if name:
                sig_parts.append(f"<b>{esc(name)}</b>")
            if role:
                sig_parts.append(esc(role))
            if location:
                sig_parts.append(esc(location))
            identity_block = f'<div class="identity-sig">Report subject &nbsp;·&nbsp; {" &nbsp;·&nbsp; ".join(sig_parts)}</div>'

    # -------- HR-facing blocks --------
    shipped = agg.get("shipped_artifacts", [])

    # Build hero + profile section depending on audience
    if audience == "hr":
        # Recruiter v1 (spec §4): identity letterhead -> hero -> earned
        # badges -> output ledger -> case study -> scope disclosure.
        # Everything else V4-HR (profile card, zone map, how-to-read,
        # candidate-memo peer review, 4-signal scoring + self-awareness
        # caveat, HR trends/growth charts, separate artifacts section) is
        # removed — see task-4-brief.md spec §4 v1 scope.
        hero_block = (
            f'<h1 class="title">{t(locale, "hero_hr_title_line1")}<br>'
            f'<em>{t(locale, "hero_hr_title_line2_em")}</em></h1>\n'
            f'<p class="dek">{t(locale, "hero_hr_dek")}</p>'
        )
        profile_section = ""
        how_to_read_section = ""
        badges_section = _build_badges_section(
            badges_data, ledger_data.get("window"), locale)
        shipped_section = _build_hr_output_ledger(
            ledger_data, shipped, artifacts_list, is_public, locale)
        artifacts_section = ""

        # TOC — recruiter v1 order: badges -> output ledger -> case study -> method
        badges_toc = (f'<a href="#badges">{t(locale, "toc_hr_badges")}</a>'
                      if badges_section else "")
        case_study_toc = (f'<a href="#case-study">{t(locale, "case_study_h")}</a>'
                          if case_study_md else "")
        toc_links = (
            badges_toc
            + f'<a href="#hr-output">{t(locale, "toc_hr_output")}</a>'
            + case_study_toc
            + f'<a href="#method">{t(locale, "hr_scope_h")}</a>'
        )
    else:
        # --- SELF audience (default, original layout) ---
        hero_block = (
            f'<h1 class="title">{t(locale, "hero_self_title_line1")}<br>'
            f'{t(locale, "hero_self_title_line2_pre")} '
            f'<em>{t(locale, "hero_self_title_line2_em")}</em> '
            f'{t(locale, "hero_self_title_line2_post")}</h1>\n'
            f'<p class="dek">{t(locale, "hero_self_dek")}</p>\n'
            f'<div class="intro-card">{t(locale, "hero_self_intro_card")}\n'
            f'  {preliminary_warning}\n'
            f'</div>'
        )
        badges_section = ""
        profile_section = ""
        shipped_section = ""
        artifacts_section = ""
        how_to_read_section = ""
        try_this_toc = (
            f'<a href="#try-this-week">{t(locale, "toc_self_try_this")}</a>'
            if try_this_md else ""
        )
        case_study_toc = (
            f'<a href="#case-study">{t(locale, "toc_self_case_study")}</a>'
            if case_study_md else ""
        )
        toc_links = (
            f'<a href="#overview">{t(locale, "toc_self_overview")}</a>'
            + f'<a href="#peer-review-section">{t(locale, "toc_self_peer_review")}</a>'
            + f'<a href="#scores">{t(locale, "toc_self_scores")}</a>'
            + try_this_toc
            + case_study_toc
            + f'<a href="#patterns">{t(locale, "toc_self_patterns")}</a>'
            + f'<a href="#trends">{t(locale, "toc_self_trends")}</a>'
            + f'<a href="#evidence">{t(locale, "toc_self_evidence")}</a>'
            + f'<a href="#method">{t(locale, "toc_self_method")}</a>'
        )

    # Growth curve chart section (both audiences but different placement)
    growth = agg.get("growth_curve", [])
    growth_labels = json_for_script([g.get("week_label", g["week"]) for g in growth])
    growth_composite = json_for_script([g["composite_score"] for g in growth])
    growth_ta = json_for_script([g["ta_rate"] for g in growth])
    growth_good = json_for_script([g["good_rate"] for g in growth])

    # HR version (recruiter v1) renders no Overview / activity-panel block
    # at all — spec §4 v1 scope is identity -> hero -> badges -> output
    # ledger -> case study -> scope disclosure only. Self audit keeps
    # Overview as the unfiltered raw-numbers view.
    activity_panel_html = _build_activity_panel(agg.get("activity", {}), locale=locale)
    if audience == "hr":
        overview_section = ""
        hr_activity_block = ""
    else:
        hr_activity_block = ""
        # SELF Usage Snapshot: merged overview + activity. Codex v2: the
        # 8-tile metric grid was redundant with activity_panel_html. Keep
        # only behavior-relevant metrics that the peer review actually
        # references (commits, interactive time, TA%, MCP%).
        behavior_strip = f'''<div class="metrics" style="margin-top:16px;margin-bottom:16px">
    <div class="metric"><div class="n">{commits_total}</div><div class="lbl">{t(locale, "tile_git_commits")}</div></div>
    <div class="metric"><div class="n">{duration_hr}h</div><div class="lbl">{t(locale, "tile_interactive_time")}</div></div>
    <div class="metric"><div class="n">{ta_rate}%</div><div class="lbl">{t(locale, "tile_used_task_agent")}</div></div>
    <div class="metric"><div class="n">{mcp_rate}%</div><div class="lbl">{t(locale, "tile_used_mcp")}</div></div>
      </div>'''
        overview_section = f'''<section id="overview">
      <h2 class="sec" data-num="§ 01">{t(locale, "self_snapshot_h")}</h2>
      <h2 class="sec-title">{t(locale, "self_snapshot_subtitle")}</h2>

      <p class="benchmark-caveat">{t(locale, "benchmark_caveat")}</p>

      {activity_panel_html}

      {behavior_strip}

      <div class="two-col">
    <div class="chart-box" data-fig="Fig. 01"><canvas id="outcomeChart"></canvas></div>
    <div class="chart-box" data-fig="Fig. 02"><canvas id="stypeChart"></canvas></div>
      </div>
      <div class="chart-box tall" data-fig="Fig. 03"><canvas id="projChart"></canvas></div>
    </section>'''

    # -------- Plain-language intro + 4-zone relationship (SELF only) --------
    # Recruiter v1 (spec §4) has no story-section / zone-map block at all.
    if audience == "hr":
        plain_intro_block = ""
    else:
        zone_visual_html = f'''<div class="reading-guide">
    <h3 class="reading-guide-h">{t(locale, "self_reading_guide_h")}</h3>
    <p>{t(locale, "self_reading_guide_body")}</p>
      </div>'''

        plain_intro_block = f'''<section id="story" class="story-section">
      <div class="plain-intro">
    <h3 class="plain-intro-h">{t(locale, "plain_intro_header")}</h3>
    {t(locale, "plain_intro_body")}
      </div>
      {zone_visual_html}
    </section>'''

    # -------- Try-this-week block (SELF only) --------
    # 3-5 concrete behaviors derived from peer review claims, hand-curated per user.
    # Sits between peer review and scoring grid so action items have momentum.
    # NOTE: try_this_md is loaded externally (analogous to peer_review_md) via build_html.py.
    if audience != "hr" and try_this_md:
        try_this_block = f'''<section id="try-this-week" class="try-this-section">
      <h2 class="sec" data-num="§ 04">{t(locale, "self_try_this_h")}</h2>
      <p class="method">{t(locale, "self_try_this_intro")}</p>
      <div class="try-this-body">
    {md_to_html(try_this_md)}
      </div>
    </section>'''
    else:
        try_this_block = ""

    # -------- Case study block (BOTH audiences) --------
    # The strongest single session, attached as evidence. SELF gets raw project name.
    # HR gets the redacted category label.
    # NOTE: case_study_md is loaded externally via build_html.py.
    if case_study_md:
        # Recruiter v1: case study is the 3rd of 5 blocks (badges, output
        # ledger, case study, method). SELF keeps try-this at §04 so case
        # study is §05.
        cs_num = "§ HR-03" if audience == "hr" else "§ 05"
        case_study_block = f'''<section id="case-study" class="case-study-section">
      <h2 class="sec" data-num="{cs_num}">{t(locale, "case_study_h")}</h2>
      <h2 class="sec-title">{t(locale, "case_study_subtitle")}</h2>
      <div class="case-study-body">
    {md_to_html(case_study_md)}
      </div>
    </section>'''
    else:
        case_study_block = ""

    # -------- Diagnosis block: peer review THEN scoring (SELF only) --------
    # Codex V2 review: story-first, quantification-after. The reader sees the
    # narrative before the grid so the grid reads as an index, not a verdict.
    # Recruiter v1 (spec §4) drops peer review + scoring entirely — badges
    # replace both with published-threshold claims.
    if audience == "hr":
        diagnosis_block = ""
    else:
        overall_strip_html = (
            f'<div class="overall-strip">{t(locale, "section_scoring_overall_label")} '
            f'&nbsp;·&nbsp; {overall_line}</div>'
        )
        score_disclaimer_html = f'<p class="score-disclaimer">{t(locale, "score_disclaimer")}</p>'

        diagnosis_block = f'''<section id="peer-review-section">
      <h2 class="sec" data-num="§ 02">{t(locale, "section_peer_review")}</h2>
      <h2 class="sec-title">{t(locale, "section_peer_review_subtitle")}</h2>
      <p class="method">{t(locale, "section_peer_review_method")}</p>
      <div id="peer-review">
    {pr_html}
      </div>
    </section>

    <section id="scores">
      <h2 class="sec" data-num="§ 03">{t(locale, "section_scoring")}</h2>
      <h2 class="sec-title">{t(locale, "section_scoring_subtitle")}</h2>
      <p class="method">{t(locale, "section_scoring_method")}</p>

      {overall_strip_html}

      {score_disclaimer_html}
      <div class="score-table">
    {score_rows}
      </div>
    </section>'''

    # -------- SELF-only AI work ledger sections (V5 direction C) --------
    # Opening band / output ledger / team ledger / leak ledger. HR must
    # never see any of this — cross-LLM session activity and blind-spot
    # findings are not for outside audiences. Builders themselves take only
    # counts/dates/minutes/tokens, never session IDs or prompt text (see
    # report_render docstrings above). exhibit_no is a single shared
    # itertools.count() so Exhibit numbers are pure order-of-appearance
    # across all four sections (Phase 2 refactor — Exhibit 1 is no longer
    # hard-coded to the output ledger).
    ledger_sections = ""
    if audience == "self":
        ledger_narration = _parse_ledger_narration(ledger_narration_md)
        ledger_block = analysis.get("ledger") or {}
        cross_block = analysis.get("cross_llm") or {}
        blind_spots = analysis.get("blind_spots") or {}
        exhibit_no = count(1)
        # include_leak_finding uses the SAME availability predicate
        # _build_leak_ledger itself checks (spec §10: whole section
        # suppressed when nothing passes a gate) to decide up front whether
        # that section will render anything — without calling the builder
        # itself, which would consume exhibit numbers out of
        # order-of-appearance (leak exhibits must come after output/team
        # exhibits in the shared counter, but the opening band renders
        # before all three). Fix: an opening band must not claim a leak
        # finding the leak section itself doesn't support. Shared via
        # _leak_section_available() rather than duplicated inline so the
        # two call sites can't drift (sunk_cost must be items-gated, not
        # bs2.gate_passed-gated — see that helper's docstring).
        include_leak_finding = _leak_section_available(blind_spots, ledger_block)
        trend_unlocked = len(history_entries or []) >= _TREND_MIN_SNAPSHOTS
        if ledger_block:
            ledger_sections += _build_opening_band(
                ledger_block, ledger_narration, locale,
                include_leak_finding=include_leak_finding,
                include_trend_finding=trend_unlocked)
            ledger_sections += _build_output_ledger(
                ledger_block, ledger_narration, locale, exhibit_no, blind_spots)
        if cross_block:
            ledger_sections += _build_team_ledger(
                cross_block, ledger_narration, locale, exhibit_no, blind_spots)
        if ledger_block:
            ledger_sections += _build_leak_ledger(
                ledger_block, blind_spots, ledger_narration, locale, exhibit_no)
            ledger_sections += _build_trend_ledger(
                analysis, history_entries, ledger_narration, locale,
                exhibit_no, blind_spots)

    # -------- Scope disclosure (HR method-footer, spec §4) --------
    hr_method = ""
    if audience == "hr":
        badge_items = badges_data.get("items") or []
        earned_count = sum(1 for b in badge_items
                           if isinstance(b, dict) and b.get("earned"))
        std_version = badges_data.get("standard_version", "v1")
        hr_method = (
            f'<section id="method" class="method-footer">'
            f'<h3 class="method-footer-h">{t(locale, "hr_scope_h")}</h3>'
            f'<p class="method-footer-body">'
            f'{t(locale, "hr_scope_body_template").format(version=esc(std_version), total=len(badge_items), earned=earned_count)}'
            f'</p></section>')

    # Assemble via string.Template to avoid CSS brace escaping
    subs = {
        "html_lang": t(locale, "html_lang"),
        "report_title": t(locale, "report_title"),
        "footer_repo": t(locale, "footer_repo"),
        "footer_tagline": t(locale, "footer_tagline"),
        "i18n_json": json_for_script({
            k: t(locale, k)
            for k in STRINGS[locale]
            if k.startswith(JS_KEY_PREFIXES)
        }),
        # projChart legend uses chart_count for both series (sessions & friction are both counts)
        "proj_legend": json_for_script([t(locale, "tile_sessions"), narrative.evidence_badge("high_friction")]),
        # Letterhead
        "letterhead_sessions_analyzed": t(locale, "letterhead_sessions_analyzed"),
        "letterhead_facet_coverage": t(locale, "letterhead_facet_coverage"),
        # Section headers §02-§07
        "section_scoring": t(locale, "section_scoring"),
        "section_scoring_subtitle": t(locale, "section_scoring_subtitle"),
        "section_scoring_method": t(locale, "section_scoring_method"),
        "section_scoring_overall_label": t(locale, "section_scoring_overall_label"),
        "section_peer_review": t(locale, "section_peer_review"),
        "section_peer_review_subtitle": t(locale, "section_peer_review_subtitle"),
        "section_peer_review_method": t(locale, "section_peer_review_method"),
        "section_patterns": t(locale, "section_patterns"),
        "section_patterns_subtitle": t(locale, "section_patterns_subtitle"),
        "section_trends": t(locale, "section_trends"),
        "section_evidence": t(locale, "section_evidence"),
        "section_evidence_subtitle": t(locale, "section_evidence_subtitle"),
        "section_evidence_method": t(locale, "section_evidence_method"),
        "section_method": t(locale, "section_method"),
        "section_method_subtitle": narrative.methodology_subtitle(),
        # §04 sub-headers
        "patterns_h_plen": t(locale, "patterns_h_plen"),
        "patterns_h_friction": t(locale, "patterns_h_friction"),
        "patterns_h_tools": t(locale, "patterns_h_tools"),
        "patterns_h_heatmap": t(locale, "patterns_h_heatmap"),
        "patterns_h_helpfulness": t(locale, "patterns_h_helpfulness"),
        "patterns_helpfulness_method": t(locale, "patterns_helpfulness_method"),
        # §05 sub-headers + method
        "trends_h_growth": t(locale, "trends_h_growth"),
        "trends_growth_method": t(locale, "trends_growth_method"),
        "trends_h_volume": t(locale, "trends_h_volume"),
        # §07 methodology body
        "method_h_sources": t(locale, "method_h_sources"),
        "method_src_session_meta": t(locale, "method_src_session_meta"),
        "method_src_facets": t(locale, "method_src_facets"),
        "method_src_transcripts": t(locale, "method_src_transcripts"),
        "method_h_sampling": t(locale, "method_h_sampling"),
        "method_sampling_body": narrative.methodology_sampling_body(),
        "method_h_caveats": t(locale, "method_h_caveats"),
        "method_caveats_body": narrative.methodology_caveats_body(),
        # Template blocks
        "chart_layout_js": _load_chart_layout_js(),
        "ledger_sections": ledger_sections,
        "identity_block": identity_block,
        "hero_block": hero_block,
        "badges_section": badges_section,
        "profile_section": profile_section,
        "hr_activity_block": hr_activity_block,
        "overview_section": overview_section,
        "plain_intro_block": plain_intro_block,
        "try_this_block": try_this_block,
        "case_study_block": case_study_block,
        "diagnosis_block": diagnosis_block,
        # SELF section numbering: 01 Overview / 02 Peer / 03 Scoring / 04 Try /
        # 05 Case Study / 06 Patterns / 07 Trends / 08 Evidence + Method footer.
        # HR section numbering: 02 Peer / 03 Scoring / 04 Case Study / 05 Trends + Method footer.
        # (HR drops Try-this and Evidence and Patterns; case study takes the 04 slot.)
        "evidence_section": (
            "" if audience == "hr" else
            f'<section id="evidence">'
            f'<h2 class="sec" data-num="§ 08">{t(locale, "section_evidence")}</h2>'
            f'<h2 class="sec-title">{t(locale, "section_evidence_subtitle")}</h2>'
            f'<p class="method">{t(locale, "section_evidence_method")}</p>'
            f'{evidence_html}'
            f'</section>'
        ),
        "patterns_section": (
            # HR: no pattern mining section at all. Outcome donut already lives
            # in trends_section. Heatmap/helpfulness/tool usage charts are
            # internal analytics with no hiring-manager signal.
            "" if audience == "hr" else
            f'<section id="patterns">'
            f'<h2 class="sec" data-num="§ 06">{t(locale, "section_patterns")}</h2>'
            f'<h2 class="sec-title">{t(locale, "section_patterns_subtitle")}</h2>'
            f'<h3>{t(locale, "patterns_h_plen")}</h3>'
            f'<div class="chart-box short" data-fig="Fig. 04"><canvas id="plenChart"></canvas></div>'
            f'<h3>{t(locale, "patterns_h_friction")}</h3>'
            f'<div class="chart-box" data-fig="Fig. 05"><canvas id="fricChart"></canvas></div>'
            f'<h3>{t(locale, "patterns_h_tools")}</h3>'
            f'<div class="chart-box tall" data-fig="Fig. 06"><canvas id="toolChart"></canvas></div>'
            f'<h3>{t(locale, "patterns_h_heatmap")}</h3>'
            f'<div class="chart-box tall" data-fig="Fig. 07"><canvas id="heatChart"></canvas></div>'
            f'<h3>{t(locale, "patterns_h_helpfulness")}</h3>'
            f'<p class="method">{t(locale, "patterns_helpfulness_method")}</p>'
            f'<div class="chart-box short" data-fig="Fig. 08"><canvas id="helpChart"></canvas></div>'
            f'</section>'
        ),
        "trends_section": (
            # Recruiter v1 (spec §4) has no trends/growth-curve section.
            "" if audience == "hr" else
            f'<section id="trends">'
            f'<h2 class="sec" data-num="§ 07">{t(locale, "section_trends")}</h2>'
            f'<h2 class="sec-title">{t(locale, "trends_subtitle_template").format(n=len(weekly))}</h2>'
            f'<h3>{t(locale, "trends_h_growth")}</h3>'
            f'<p class="method">{t(locale, "trends_growth_method")}</p>'
            f'<div class="chart-box" data-fig="Fig. 09"><canvas id="growthChart"></canvas></div>'
            f'<h3>{t(locale, "trends_h_volume")}</h3>'
            f'<div class="chart-box" data-fig="Fig. 10"><canvas id="wkSessions"></canvas></div>'
            f'<div class="chart-box" data-fig="Fig. 11"><canvas id="wkTokens"></canvas></div>'
            f'<div class="chart-box" data-fig="Fig. 12"><canvas id="wkGood"></canvas></div>'
            f'<div class="chart-box" data-fig="Fig. 13"><canvas id="wkFric"></canvas></div>'
            f'<div class="chart-box" data-fig="Fig. 14"><canvas id="wkPlen"></canvas></div>'
            f'</section>'
        ),
        "method_section": (
            hr_method
            if audience == "hr" else
            f'<section id="method" class="method-footer">'
            f'<h3 class="method-footer-h">{t(locale, "section_method")}</h3>'
            f'<div class="method-footer-body">'
            f'<h4>{t(locale, "method_h_sources")}</h4>'
            f'<ul>'
            f'<li>{t(locale, "method_src_session_meta")}</li>'
            f'<li>{t(locale, "method_src_facets")}</li>'
            f'<li>{t(locale, "method_src_transcripts")}</li>'
            f'</ul>'
            f'<h4>{t(locale, "method_h_sampling")}</h4>'
            f'<p>{narrative.methodology_sampling_body()}</p>'
            f'<h4>{t(locale, "method_h_caveats")}</h4>'
            f'<div class="caveat">{narrative.methodology_caveats_body()}</div>'
            f'</div>'
            f'</section>'
        ),
        "how_to_read_section": how_to_read_section,
        "shipped_section": shipped_section,
        "artifacts_section": artifacts_section,
        "toc_links": toc_links,
        "growth_labels": growth_labels,
        "growth_composite": growth_composite,
        "growth_good": growth_good,
        "growth_ta": growth_ta,
        "date_first": meta["date_range"]["first"][:10],
        "date_last": meta["date_range"]["last"][:10],
        "total_sessions": meta.get("total_sessions", 0),
        "facets_coverage": f'{meta.get("facets_coverage_pct", 0):.0f}',
        "preliminary_warning": preliminary_warning,
        "overall_line": overall_line,
        "score_disclaimer": t(locale, "score_disclaimer"),
        "score_rows": score_rows,
        "peer_review_html": pr_html,
        "weekly_count": len(weekly),
        "trends_subtitle": t(locale, "trends_subtitle_template").format(n=len(weekly)),
        "evidence_html": evidence_html,
        # Chart data
        "outcome_labels": json_for_script(list(agg["outcomes"].keys())),
        "outcome_values": json_for_script(list(agg["outcomes"].values())),
        "stype_labels": json_for_script(list(agg["session_types"].keys())),
        "stype_values": json_for_script(list(agg["session_types"].values())),
        "proj_labels": json_for_script([p[1].get("label", p[0])[:25] for p in proj_items]),
        "proj_sessions": json_for_script([p[1]["sessions"] for p in proj_items]),
        "proj_friction": json_for_script([p[1]["friction"] for p in proj_items]),
        "plen_buckets": json_for_script(plen_buckets),
        "plen_good": json_for_script(plen_good_pct),
        "plen_n": json_for_script(plen_n),
        "fric_labels": json_for_script([f[0] for f in fric_top]),
        "fric_counts": json_for_script([f[1] for f in fric_top]),
        "tool_labels": json_for_script([re.sub(r"mcp__[^_]+__", "", tt[0])[:28] for tt in tool_top]),
        "tool_counts": json_for_script([tt[1] for tt in tool_top]),
        "heat_grid": json_for_script(grid),
        "heat_labels": json_for_script(weekday_labels(locale)),
        "help_labels": json_for_script(list(agg["helpfulness"].keys())),
        "help_values": json_for_script(list(agg["helpfulness"].values())),
        "wk_labels": json_for_script(w_labels),
        "wk_sessions": json_for_script([w["sessions"] for w in weekly]),
        "wk_tokens_m": json_for_script([round(w["tokens"] / 1e6, 3) for w in weekly]),
        "wk_commits": json_for_script([w["commits"] for w in weekly]),
        "wk_goodrate": json_for_script([w["good_rate_pct"] for w in weekly]),
        "wk_friction": json_for_script([w["friction"] for w in weekly]),
        "wk_plen": json_for_script([w["avg_prompt_len"] for w in weekly]),
        "wk_ta": json_for_script([w["uses_task_agent"] for w in weekly]),
    }

    # string.Template allows $var and ${var}; literal $ needs $$
    # The CSS in template already uses only CSS vars via var(--x), so no clash.
    return string.Template(PAGE_TEMPLATE).safe_substitute(subs)
