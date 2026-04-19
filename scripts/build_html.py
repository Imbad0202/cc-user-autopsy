"""
cc-user-autopsy Step 4: render final HTML report.
Editorial-clinical design: paper-tone background, Fraunces serif + JetBrains Mono,
diagnostic-note chrome. Not a dashboard — a typeset diagnostic letter.
"""
import argparse
import html
import json
import re
import string
import sys
from pathlib import Path
from urllib.parse import urlparse

from locales import STRINGS, t

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Keys whose name starts with one of these prefixes are exposed to inline JS
# via the `I18N` const. Naming convention is the contract: name a chart-side
# key `chart_*` or `series_*` and it flows through automatically.
JS_KEY_PREFIXES = ("chart_", "series_")


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
    fav_short = fav.replace("claude-", "").replace("-20251001", "").replace("-20250929", "").replace("-20251101", "")

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
        short = m.replace("claude-", "").replace("-20251001", "").replace("-20250929", "").replace("-20251101", "")
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
    --serif: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
    --sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
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
       consumer; .profile-card currently uses primitives directly. --- */
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
  .profile-card {
    margin: var(--space-12) 0 48px 0;
    padding: var(--space-15) 34px 34px 34px;
    background: linear-gradient(135deg, rgba(255,250,240,0.8) 0%, rgba(236,229,213,0.4) 100%);
    border: 1px solid var(--rule);
    border-left: 4px solid var(--accent);
    position: relative;
  }
  .profile-card::before {
    content: "AT A GLANCE";
    position: absolute;
    top: -10px; left: var(--space-15);
    background: var(--paper);
    padding: 0 var(--space-5);
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: 0.26em;
    color: var(--accent);
  }
  .profile-lede {
    font-family: var(--serif);
    font-variation-settings: "opsz" 36, "wght" 400;
    font-size: 22px;
    line-height: 1.42;
    letter-spacing: -0.012em;
    color: var(--ink);
    margin: 0 0 var(--space-11) 0;
  }
  .profile-lede em {
    color: var(--accent);
    font-style: italic;
    font-weight: 500;
  }
  .profile-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
    margin-top: var(--space-10);
    border-top: 1px solid var(--rule);
    border-left: 1px solid var(--rule);
  }
  @media (max-width: 640px) { .profile-grid { grid-template-columns: repeat(2, 1fr); } }
  .profile-cell {
    border-right: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    padding: var(--space-7) var(--space-8) var(--space-8) var(--space-8);
  }
  .profile-cell .k {
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--ink-muted);
    margin-bottom: var(--space-3);
  }
  .profile-cell .v {
    font-family: var(--serif);
    font-variation-settings: "opsz" 72, "wght" 400;
    font-size: var(--text-2xl);
    line-height: 1.1;
    letter-spacing: -0.02em;
    color: var(--ink);
  }
  .profile-cell .sub {
    font-family: var(--sans);
    font-size: 12px;
    color: var(--ink-muted);
    margin-top: var(--space-1);
  }

  /* How to read */
  details.how-to-read {
    margin: 0 0 40px 0;
    border: 1px dashed var(--rule);
    padding: 12px 18px;
    background: transparent;
  }
  details.how-to-read summary {
    cursor: pointer;
    font-family: var(--mono);
    font-size: 11.5px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--ink-muted);
    list-style: none;
  }
  details.how-to-read summary::-webkit-details-marker { display: none; }
  details.how-to-read summary::before {
    content: "+ ";
    color: var(--accent);
  }
  details.how-to-read[open] summary::before { content: "− "; }
  details.how-to-read[open] { padding-bottom: 18px; }
  details.how-to-read .how-body {
    margin-top: 14px;
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.6;
    color: var(--ink-soft);
  }
  details.how-to-read dl { margin: 10px 0; }
  details.how-to-read dt {
    font-family: var(--mono);
    font-size: 11.5px;
    letter-spacing: 0.06em;
    color: var(--accent);
    margin-top: 10px;
  }
  details.how-to-read dd { margin: 2px 0 0 0; }

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

$identity_block

$hero_block

$profile_section

$hr_activity_block

$how_to_read_section

$shipped_section

$artifacts_section

<nav class="toc">
  $toc_links
</nav>

$overview_section

<section id="scores">
  <h2 class="sec" data-num="§ 02">$section_scoring</h2>
  <h2 class="sec-title">$section_scoring_subtitle</h2>
  <p class="method">$section_scoring_method</p>

  <div class="overall-strip">$section_scoring_overall_label &nbsp;·&nbsp; $overall_line</div>

  <p class="score-disclaimer">$score_disclaimer</p>
  <div class="score-table">
    $score_rows
  </div>
</section>

<section id="peer-review-section">
  <h2 class="sec" data-num="§ 03">$section_peer_review</h2>
  <h2 class="sec-title">$section_peer_review_subtitle</h2>
  <p class="method">$section_peer_review_method</p>
  <div id="peer-review">
$peer_review_html
  </div>
</section>

<section id="patterns">
  <h2 class="sec" data-num="§ 04">$section_patterns</h2>
  <h2 class="sec-title">$section_patterns_subtitle</h2>

  <h3>$patterns_h_plen</h3>
  <div class="chart-box short" data-fig="Fig. 04"><canvas id="plenChart"></canvas></div>

  <h3>$patterns_h_friction</h3>
  <div class="chart-box" data-fig="Fig. 05"><canvas id="fricChart"></canvas></div>

  <h3>$patterns_h_tools</h3>
  <div class="chart-box tall" data-fig="Fig. 06"><canvas id="toolChart"></canvas></div>

  <h3>$patterns_h_heatmap</h3>
  <div class="chart-box tall" data-fig="Fig. 07"><canvas id="heatChart"></canvas></div>

  <h3>$patterns_h_helpfulness</h3>
  <p class="method">$patterns_helpfulness_method</p>
  <div class="chart-box short" data-fig="Fig. 08"><canvas id="helpChart"></canvas></div>
</section>

<section id="trends">
  <h2 class="sec" data-num="§ 05">$section_trends</h2>
  <h2 class="sec-title">$weekly_count weeks on the record.</h2>

  <h3>$trends_h_growth</h3>
  <p class="method">$trends_growth_method</p>
  <div class="chart-box" data-fig="Fig. 09"><canvas id="growthChart"></canvas></div>

  <h3>$trends_h_volume</h3>
  <div class="chart-box" data-fig="Fig. 10"><canvas id="wkSessions"></canvas></div>
  <div class="chart-box" data-fig="Fig. 11"><canvas id="wkTokens"></canvas></div>
  <div class="chart-box" data-fig="Fig. 12"><canvas id="wkGood"></canvas></div>
  <div class="chart-box" data-fig="Fig. 13"><canvas id="wkFric"></canvas></div>
  <div class="chart-box" data-fig="Fig. 14"><canvas id="wkPlen"></canvas></div>
</section>

<section id="evidence">
  <h2 class="sec" data-num="§ 06">$section_evidence</h2>
  <h2 class="sec-title">$section_evidence_subtitle</h2>
  <p class="method">$section_evidence_method</p>
  $evidence_html
</section>

<section id="method">
  <h2 class="sec" data-num="§ 07">$section_method</h2>
  <h2 class="sec-title">$section_method_subtitle</h2>

  <div class="method">
  <h4>$method_h_sources</h4>
  <ul>
    <li>$method_src_session_meta</li>
    <li>$method_src_facets</li>
    <li>$method_src_transcripts</li>
  </ul>

  <h4>$method_h_sampling</h4>
  <p>$method_sampling_body</p>

  <h4>$method_h_caveats</h4>
  <div class="caveat">$method_caveats_body</div>
  </div>
</section>

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
  ctx.textAlign = 'right';
  // Per-label budget along the rotated axis: at -45deg the label rises into
  // the gap between adjacent ticks, so width budget is groupWidth / cos(45).
  const measure = (s) => ctx.measureText(s).width;
  const labelBudget = Math.max(40, (groupWidth / Math.SQRT1_2) * 0.95);
  for (let i = 0; i < labels.length; i += 1) {
    if (i % step !== 0 && i !== labels.length - 1) continue;
    const x = slotCenterX(i, labels.length, plot);
    const y = plot.top + plot.height + 14;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(-Math.PI / 4);
    ctx.fillText(clipLabelToWidth(labels[i], labelBudget, measure), 0, 0);
    ctx.restore();
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

    const legendX = Math.max(cx + radius + 32, width * 0.54);
    let legendY = Math.max(32, cy - (labels.length * 18) / 2);
    ctx.textAlign = 'left';
    ctx.font = FONT_MONO_SMALL;
    const legendBudget = Math.max(40, width - legendX - 16 - 8);
    const measure = (s) => ctx.measureText(s).width;
    labels.forEach((label, index) => {
      ctx.fillStyle = colors[index % colors.length];
      ctx.fillRect(legendX, legendY - 5, 10, 10);
      ctx.fillStyle = INK_SOFT;
      const full = `${label} (${values[index]})`;
      ctx.fillText(clipLabelToWidth(full, legendBudget, measure), legendX + 16, legendY);
      legendY += 18;
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
    // For dual-axis: pick the formatter/max that yields the longer tick label for the left margin.
    const leftTickLabel = (options.leftFormatter || formatTick)(leftMax);
    const rightTickLabel = (options.rightFormatter || formatTick)(rightMax);
    const yAxisMaxTickLabel = leftTickLabel.length >= rightTickLabel.length ? leftTickLabel : rightTickLabel;
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
    // For dual-axis: pick the formatter/max that yields the longer tick label for the left margin.
    const leftTickLabel = (options.leftFormatter || formatTick)(leftMax);
    const rightTickLabel = (options.rightFormatter || formatTick)(rightMax);
    const yAxisMaxTickLabel = leftTickLabel.length >= rightTickLabel.length ? leftTickLabel : rightTickLabel;
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
    pr_html = md_to_html(pr_md)

    artifacts_list = load_json_or_warn(args.artifacts, "artifacts", [])
    profile_info = load_json_or_warn(args.profile, "profile", {})
    allowlist = load_json_or_warn(args.public_projects, "public-projects", {})
    public_set = set(allowlist.get("public_projects", []))
    category_map = allowlist.get("category_overrides", {}) or {}
    redact = (args.audience == "hr")
    label_project = lambda name: display_project(name, redact, public_set, category_map, args.locale)
    is_public = lambda name: (not redact) or _matches_allowlist(name, public_set)

    meta = data["meta"]
    agg = data["aggregates"]
    scores = data["scores"]

    total = meta["total_sessions"]
    total_tok = agg["tokens"]["total"]
    commits_total = sum(p["commits"] for p in agg["projects"].values())
    duration_hr = int(sum(p["duration_min"] for p in agg["projects"].values()) / 60)
    profile_for_rates = agg.get("profile_summary", {})
    ta_rate = int(round(profile_for_rates.get("ta_pct", 0)))
    mcp_rate = int(round(profile_for_rates.get("mcp_pct", 0)))

    # Chart series
    weekly = agg["weekly"]
    w_labels = [w["week"] for w in weekly]

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

    # Score rows
    dim_titles = {
        "D1_delegation": t(args.locale, "score_d1"),
        "D2_root_cause": t(args.locale, "score_d2"),
        "D3_prompt_quality": t(args.locale, "score_d3"),
        "D4_context_mgmt": t(args.locale, "score_d4"),
        "D5_interrupt_judgment": t(args.locale, "score_d5"),
        "D6_tool_breadth": t(args.locale, "score_d6"),
        "D7_writing_consistency": t(args.locale, "score_d7"),
        "D8_time_mgmt": t(args.locale, "score_d8"),
    }
    score_rows = ""
    for key, title in dim_titles.items():
        s = scores.get(key, {})
        sc = s.get("score")
        band = score_band(sc)
        display = f'<span class="num">{sc}</span><span class="out">/ 10</span>' if sc is not None else 'n/a'
        dim_label = f"{key.split('_', 1)[0]} · {key.split('_', 1)[1].replace('_', ' ')}"
        reason = s.get("explanation") or s.get("reason", "")
        pattern_html = ""
        pattern_val = s.get("pattern")
        if pattern_val:
            pattern_html = f'\n    <p class="pattern">{esc(pattern_val)}</p>'
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
        overall_line = t(args.locale, "score_overall_low_data")

    # Evidence
    tag_labels = {
        "high_friction": t(args.locale, "ev_high_friction"),
        "top_token": t(args.locale, "ev_top_token"),
        "top_interrupt": t(args.locale, "ev_top_interrupt"),
        "not_achieved": t(args.locale, "ev_not_achieved"),
        "partial": t(args.locale, "ev_partial"),
        "control_good": t(args.locale, "ev_control_good"),
        "user_rejected": t(args.locale, "ev_user_rejected"),
        "long_duration": t(args.locale, "ev_long_duration"),
    }
    by_tag = {}
    for sid, info in samples.items():
        by_tag.setdefault(info["tag"], []).append({"sid": sid, **info})
    evidence_html = ""
    if args.audience == "hr":
        # Evidence library leaks sid + project + first-prompt + friction detail.
        # Not appropriate for a public-facing report. Hidden entirely in HR mode.
        evidence_html = (
            '<p class="method">Evidence library with per-session citations is '
            'available in the self-audit version of this report. It is hidden '
            'here to protect private project details.</p>'
        )
    else:
        for tag, label in tag_labels.items():
            sess_list = by_tag.get(tag, [])
            if not sess_list:
                continue
            evidence_html += f'<div class="evidence-header">{label}</div>\n'
            for s in sess_list:
                m = s.get("meta", {})
                fp = (m.get("first_prompt", "") or "")[:300]
                fric = json.dumps(m.get("friction_counts") or {}, ensure_ascii=False)
                summary = m.get("brief_summary", "") or "(no summary)"
                frictxt = m.get("friction_detail", "") or "(none)"
                proj = m.get('project', '?')
                outcome = m.get('outcome', '') or '(no facet)'
                tok_str = fmt(m.get('total_tokens', 0))
                dur = m.get('duration_min', 0)
                evidence_html += f'''<details class="evidence">
  <summary>
    <span class="tag {tag}">{esc(tag.replace('_', ' '))}</span>
    <span><span class="sid">{esc(s["sid"][:8])}</span> · <span class="proj">{esc(proj)}</span> · {esc(outcome)}</span>
    <span class="right">{esc(tok_str)} tok · {esc(dur)}m</span>
  </summary>
  <p><strong>Summary</strong> · {esc(summary)}</p>
  <p><strong>Friction detail</strong> · {esc(frictxt)}</p>
  <p><strong>First prompt</strong> · <code>{esc(fp)}</code></p>
  <p><strong>Friction counts</strong> · <code>{esc(fric)}</code></p>
</details>
'''

    preliminary_warning = (
        '<div class="preliminary">⚠ Preliminary report — fewer than 20 rated sessions. Scores directional.</div>'
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

        if args.audience == "hr":
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
    profile = agg.get("profile_summary", {})
    shipped = agg.get("shipped_artifacts", [])
    efficiency = agg.get("efficiency", {})
    scores_overall = scores.get("_overall", {}).get("avg")

    # weakest dimension (excluding _overall and nulls)
    weakest = None
    for k, v in scores.items():
        if k.startswith("_"):
            continue
        sc = v.get("score")
        if sc is None:
            continue
        if weakest is None or sc < weakest[1]:
            weakest = (k, sc, v.get("explanation", ""))

    # Generate profile lede (auto, plain English)
    if profile:
        lede_parts = [
            f"<em>{profile['scale_tier'].capitalize()}</em> Claude Code user — "
            f"<strong>{profile['total_sessions']}</strong> sessions totalling "
            f"<strong>{profile['total_duration_hr']:.0f} hours</strong> across "
            f"<strong>{profile['project_count_active']} active projects</strong> "
            f"over {profile['date_span_days']} days."
        ]
        if profile["ta_pct"] >= 30:
            lede_parts.append(
                f" Strongest pattern: parallel work through Task agent "
                f"(<strong>{profile['ta_pct']:.0f}%</strong> of sessions)."
            )
        if weakest and weakest[1] < 6:
            weakest_title = weakest[0].split("_", 1)[1].replace("_", " ")
            lede_parts.append(
                f" Honest weakest area: <em>{esc(weakest_title)}</em> ({weakest[1]}/10)."
            )
        if profile["specialty"]:
            lede_parts.append(f" Specialty: {esc(profile['specialty'])}.")
        profile_lede_html = "".join(lede_parts)
    else:
        profile_lede_html = ""

    # Build hero + profile section depending on audience
    if args.audience == "hr":
        hero_block = (
            f'<h1 class="title">{t(args.locale, "hero_hr_title_line1")}<br>'
            f'<em>{t(args.locale, "hero_hr_title_line2_em")}</em></h1>\n'
            f'<p class="dek">{t(args.locale, "hero_hr_dek")}</p>'
        )
        profile_section = f'''<div class="profile-card">
  <div class="profile-lede">{profile_lede_html}</div>
  <div class="profile-grid">
    <div class="profile-cell">
      <div class="k">Scale</div>
      <div class="v">{fmt(profile.get("total_duration_hr", 0))}h</div>
      <div class="sub">{profile.get("total_sessions", 0)} sessions</div>
    </div>
    <div class="profile-cell">
      <div class="k">Velocity</div>
      <div class="v">{efficiency.get("commits_per_hour", 0)}</div>
      <div class="sub">{t(args.locale, "profile_sub_commits_per_hour")}</div>
    </div>
    <div class="profile-cell">
      <div class="k">Parallel work</div>
      <div class="v">{profile.get("ta_pct", 0):.0f}%</div>
      <div class="sub">{t(args.locale, "profile_sub_task_agent_adoption")}</div>
    </div>
    <div class="profile-cell">
      <div class="k">Tool breadth</div>
      <div class="v">{profile.get("mcp_pct", 0):.0f}%</div>
      <div class="sub">{t(args.locale, "profile_sub_mcp_sessions")}</div>
    </div>
    <div class="profile-cell">
      <div class="k">Self-audit</div>
      <div class="v">{scores_overall if scores_overall else "n/a"}<span style="font-size:14px;color:var(--ink-muted);"> / 10</span></div>
      <div class="sub">8-dim rule-based</div>
    </div>
    <div class="profile-cell">
      <div class="k">Focus</div>
      <div class="v" style="font-size:14.5px;line-height:1.3;">{esc(profile.get("specialty", "—"))}</div>
      <div class="sub">{profile.get("top_project_share_pct", 0):.0f}% on top project</div>
    </div>
  </div>
</div>'''

        # Shipped artifacts section — redact non-public projects
        if shipped:
            shipped_items = ""
            for item in shipped[:6]:
                raw_proj = item["project"]
                dur_hr = item["project_duration_min"] / 60
                if is_public(raw_proj):
                    proj_display = raw_proj
                    summary_display = item["summary"]
                else:
                    proj_display = label_project(raw_proj)
                    summary_display = (
                        f"Outcome: fully achieved across {item['project_sessions']} "
                        f"sessions. Details withheld — {t(args.locale, 'redacted_project').lower()}."
                    )
                shipped_items += f'''<div class="shipped-item">
  <div>
    <div class="proj">{esc(proj_display)}</div>
    <div class="proj-sub">{item["project_sessions"]} sessions · {dur_hr:.0f}h</div>
  </div>
  <div class="desc">{esc(summary_display)}</div>
  <div class="stats">
    {item["project_commits"]} commits<br>
    {fmt(item["total_tokens"])} tok / top session
  </div>
</div>'''
            privacy_note = ""
            if public_set:
                privacy_note = (
                    ' Allowlisted public projects appear by name; everything else is '
                    'shown as a generic category label.'
                )
            else:
                privacy_note = (
                    ' All project names are anonymised — no public-projects allowlist '
                    'was supplied. Pass <code>--public-projects</code> to show specific '
                    'repos by name.'
                )
            shipped_section = f'''<section id="shipped">
  <h2 class="sec" data-num="§ HR-02">Shipped with Claude</h2>
  <h2 class="sec-title">Representative outcomes — fully achieved, essential-tier sessions, grouped by project.</h2>
  <p class="method">Extracted from session facets where <code>outcome = fully_achieved</code> and <code>helpfulness ∈ (essential, very_helpful)</code>. One representative per project, ranked by total time invested.{privacy_note}</p>
  <div class="shipped-list">{shipped_items}</div>
</section>'''
        else:
            shipped_section = ""

        # Public artifacts (from --artifacts JSON)
        if artifacts_list:
            artifact_rows = ""
            for a in artifacts_list:
                safe_url = sanitize_url(str(a.get("url", "")).strip())
                artifact_rows += f'''<div class="artifact-row">
  <div>
    <div class="name">{esc(a.get("name", "(unnamed)"))}</div>
    <div class="desc">{esc(a.get("description", ""))}</div>
  </div>
  <div class="link"><a rel="noopener noreferrer" href="{esc(safe_url)}">{esc(display_url(safe_url))}</a></div>
</div>'''
            artifacts_section = f'''<section id="artifacts">
  <h2 class="sec" data-num="§ HR-03">Public artifacts</h2>
  <h2 class="sec-title">Links the user chose to surface.</h2>
  <p class="method">Self-reported. Not auto-extracted.</p>
  {artifact_rows}
</section>'''
        else:
            artifacts_section = ""

        # How-to-read for HR
        how_to_read_section = f'''<details class="how-to-read" open>
<summary>How to read this report (30-second primer)</summary>
<div class="how-body">
<p>This report is generated by <code>cc-user-autopsy</code>, a skill that reads a user's local Claude Code usage data. It combines deterministic rule-based scoring with an LLM-written peer review.</p>
<dl>
<dt>Session</dt>
<dd>One continuous Claude Code conversation, bounded by either a fresh start or a <code>/clear</code>. A typical heavy user has hundreds per quarter.</dd>
<dt>Task agent / Subagent</dt>
<dd>Claude Code lets you spawn isolated child agents to run a subtask in parallel. Heavy adoption signals fluency with agentic workflows.</dd>
<dt>MCP (Model Context Protocol)</dt>
<dd>A standard for connecting Claude to external tools (Playwright, Supabase, GitHub, etc). MCP adoption rate correlates with tool breadth.</dd>
<dt>Facet</dt>
<dd>LLM-classified outcome / friction labels per session, produced by the built-in <code>/insights</code> command. Coverage &lt; 100% is normal.</dd>
<dt>Interrupt recovery rate</dt>
<dd>Of sessions where the user interrupted Claude's action, what fraction still reached a "good" outcome. High = good judgment about when to stop Claude.</dd>
<dt>{t(args.locale, "how_to_read_key_relate")}</dt>
<dd>{t(args.locale, "how_to_read_val_relate")}</dd>
</dl>
</div>
</details>'''

        # TOC — HR-ordered
        toc_links = (
            f'<a href="#shipped">{t(args.locale, "toc_hr_shipped")}</a>'
            f'<a href="#overview">{t(args.locale, "toc_hr_overview")}</a>'
            f'<a href="#scores">{t(args.locale, "toc_hr_scores")}</a>'
            f'<a href="#peer-review-section">{t(args.locale, "toc_hr_peer_review")}</a>'
            f'<a href="#trends">{t(args.locale, "toc_hr_trends")}</a>'
            f'<a href="#patterns">{t(args.locale, "toc_hr_patterns")}</a>'
            f'<a href="#evidence">{t(args.locale, "toc_hr_evidence")}</a>'
            f'<a href="#method">{t(args.locale, "toc_hr_method")}</a>'
        )
    else:
        # --- SELF audience (default, original layout) ---
        hero_block = (
            f'<h1 class="title">{t(args.locale, "hero_self_title_line1")}<br>'
            f'{t(args.locale, "hero_self_title_line2_pre")} '
            f'<em>{t(args.locale, "hero_self_title_line2_em")}</em> '
            f'{t(args.locale, "hero_self_title_line2_post")}</h1>\n'
            f'<p class="dek">{t(args.locale, "hero_self_dek")}</p>\n'
            f'<div class="intro-card">{t(args.locale, "hero_self_intro_card")}\n'
            f'  {preliminary_warning}\n'
            f'</div>'
        )
        profile_section = ""
        shipped_section = ""
        artifacts_section = ""
        how_to_read_section = ""
        toc_links = (
            f'<a href="#overview">{t(args.locale, "toc_self_overview")}</a>'
            f'<a href="#scores">{t(args.locale, "toc_self_scores")}</a>'
            f'<a href="#peer-review-section">{t(args.locale, "toc_self_peer_review")}</a>'
            f'<a href="#patterns">{t(args.locale, "toc_self_patterns")}</a>'
            f'<a href="#trends">{t(args.locale, "toc_self_trends")}</a>'
            f'<a href="#evidence">{t(args.locale, "toc_self_evidence")}</a>'
            f'<a href="#method">{t(args.locale, "toc_self_method")}</a>'
        )

    # Growth curve chart section (both audiences but different placement)
    growth = agg.get("growth_curve", [])
    growth_labels = json_for_script([g["week"] for g in growth])
    growth_composite = json_for_script([g["composite_score"] for g in growth])
    growth_ta = json_for_script([g["ta_rate"] for g in growth])
    growth_good = json_for_script([g["good_rate"] for g in growth])

    # HR version hides Overview (§ 01) entirely — profile-card + activity
    # panel cover the same ground without duplicating 8 more tiles and 3
    # charts. Self audit keeps Overview as the unfiltered raw-numbers view.
    activity_panel_html = _build_activity_panel(agg.get("activity", {}), locale=args.locale)
    if args.audience == "hr":
        overview_section = ""
        # Drop the activity panel directly under the profile card so readers
        # still see cache/models/cost — the most compelling scale evidence.
        hr_activity_block = (
            f'<div style="margin-top:28px">{activity_panel_html}</div>'
            if activity_panel_html else ""
        )
    else:
        hr_activity_block = ""
        overview_section = f'''<section id="overview">
  <h2 class="sec" data-num="§ 01">{t(args.locale, "section_overview")}</h2>
  <h2 class="sec-title">{t(args.locale, "section_overview_subtitle")}</h2>

  {activity_panel_html}

  <div class="metrics">
    <div class="metric"><div class="n">{total}</div><div class="lbl">{t(args.locale, "tile_sessions")}</div></div>
    <div class="metric"><div class="n">{fmt(total_tok)}</div><div class="lbl">{t(args.locale, "tile_total_tokens")}</div></div>
    <div class="metric"><div class="n">{commits_total}</div><div class="lbl">{t(args.locale, "tile_git_commits")}</div></div>
    <div class="metric"><div class="n">{duration_hr}h</div><div class="lbl">{t(args.locale, "tile_interactive_time")}</div></div>
    <div class="metric"><div class="n">{ta_rate}%</div><div class="lbl">{t(args.locale, "tile_used_task_agent")}</div></div>
    <div class="metric"><div class="n">{mcp_rate}%</div><div class="lbl">{t(args.locale, "tile_used_mcp")}</div></div>
    <div class="metric"><div class="n">{meta["facets_coverage_pct"]}%</div><div class="lbl">{t(args.locale, "tile_facet_coverage")}</div></div>
    <div class="metric"><div class="n">{int(agg["response_times"]["median_seconds"])}s</div><div class="lbl">{t(args.locale, "tile_median_think_time")}</div></div>
  </div>

  <div class="two-col">
    <div class="chart-box" data-fig="Fig. 01"><canvas id="outcomeChart"></canvas></div>
    <div class="chart-box" data-fig="Fig. 02"><canvas id="stypeChart"></canvas></div>
  </div>
  <div class="chart-box tall" data-fig="Fig. 03"><canvas id="projChart"></canvas></div>
</section>'''

    # Assemble via string.Template to avoid CSS brace escaping
    subs = {
        "html_lang": t(args.locale, "html_lang"),
        "report_title": t(args.locale, "report_title"),
        "footer_repo": t(args.locale, "footer_repo"),
        "footer_tagline": t(args.locale, "footer_tagline"),
        "i18n_json": json_for_script({
            k: t(args.locale, k)
            for k in STRINGS[args.locale]
            if k.startswith(JS_KEY_PREFIXES)
        }),
        # projChart legend uses chart_count for both series (sessions & friction are both counts)
        "proj_legend": json_for_script([t(args.locale, "tile_sessions"), t(args.locale, "ev_high_friction")]),
        # Letterhead
        "letterhead_sessions_analyzed": t(args.locale, "letterhead_sessions_analyzed"),
        "letterhead_facet_coverage": t(args.locale, "letterhead_facet_coverage"),
        # Section headers §02-§07
        "section_scoring": t(args.locale, "section_scoring"),
        "section_scoring_subtitle": t(args.locale, "section_scoring_subtitle"),
        "section_scoring_method": t(args.locale, "section_scoring_method"),
        "section_scoring_overall_label": t(args.locale, "section_scoring_overall_label"),
        "section_peer_review": t(args.locale, "section_peer_review"),
        "section_peer_review_subtitle": t(args.locale, "section_peer_review_subtitle"),
        "section_peer_review_method": t(args.locale, "section_peer_review_method"),
        "section_patterns": t(args.locale, "section_patterns"),
        "section_patterns_subtitle": t(args.locale, "section_patterns_subtitle"),
        "section_trends": t(args.locale, "section_trends"),
        "section_evidence": t(args.locale, "section_evidence"),
        "section_evidence_subtitle": t(args.locale, "section_evidence_subtitle"),
        "section_evidence_method": t(args.locale, "section_evidence_method"),
        "section_method": t(args.locale, "section_method"),
        "section_method_subtitle": t(args.locale, "section_method_subtitle"),
        # §04 sub-headers
        "patterns_h_plen": t(args.locale, "patterns_h_plen"),
        "patterns_h_friction": t(args.locale, "patterns_h_friction"),
        "patterns_h_tools": t(args.locale, "patterns_h_tools"),
        "patterns_h_heatmap": t(args.locale, "patterns_h_heatmap"),
        "patterns_h_helpfulness": t(args.locale, "patterns_h_helpfulness"),
        "patterns_helpfulness_method": t(args.locale, "patterns_helpfulness_method"),
        # §05 sub-headers + method
        "trends_h_growth": t(args.locale, "trends_h_growth"),
        "trends_growth_method": t(args.locale, "trends_growth_method"),
        "trends_h_volume": t(args.locale, "trends_h_volume"),
        # §07 methodology body
        "method_h_sources": t(args.locale, "method_h_sources"),
        "method_src_session_meta": t(args.locale, "method_src_session_meta"),
        "method_src_facets": t(args.locale, "method_src_facets"),
        "method_src_transcripts": t(args.locale, "method_src_transcripts"),
        "method_h_sampling": t(args.locale, "method_h_sampling"),
        "method_sampling_body": t(args.locale, "method_sampling_body"),
        "method_h_caveats": t(args.locale, "method_h_caveats"),
        "method_caveats_body": t(args.locale, "method_caveats_body"),
        # Template blocks
        "chart_layout_js": _load_chart_layout_js(),
        "identity_block": identity_block,
        "hero_block": hero_block,
        "profile_section": profile_section,
        "hr_activity_block": hr_activity_block,
        "overview_section": overview_section,
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
        "score_disclaimer": t(args.locale, "score_disclaimer"),
        "score_rows": score_rows,
        "peer_review_html": pr_html,
        "weekly_count": len(weekly),
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
        "heat_labels": json_for_script(WEEKDAY_LABELS),
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
    html = string.Template(PAGE_TEMPLATE).safe_substitute(subs)

    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"wrote {out} ({out.stat().st_size} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
