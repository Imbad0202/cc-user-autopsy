"""
cc-user-autopsy Step 4: render final HTML report.
Editorial-clinical design: paper-tone background, Fraunces serif + JetBrains Mono,
diagnostic-note chrome. Not a dashboard — a typeset diagnostic letter.
"""
import argparse
import json
import re
import string
import sys
from pathlib import Path

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt(n):
    if n is None:
        return "—"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    if n == int(n):
        return str(int(n))
    return f"{n:.1f}"


def md_to_html(md: str) -> str:
    """Minimal markdown → HTML."""
    if not md:
        return "<p class='muted'><em>(no peer review written for this run)</em></p>"
    out_lines = []
    in_list = False
    list_tag = "ol"
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            if in_list:
                out_lines.append(f"</{list_tag}>")
                in_list = False
            out_lines.append("")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            if in_list:
                out_lines.append(f"</{list_tag}>")
                in_list = False
            level = len(m.group(1))
            out_lines.append(f"<h{level+2}>{m.group(2)}</h{level+2}>")
            continue

        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            if not in_list:
                out_lines.append("<ol>")
                in_list = True
                list_tag = "ol"
            out_lines.append(f"<li>{inline_md(m.group(2))}</li>")
            continue

        if line.startswith("- ") or line.startswith("* "):
            if not in_list:
                out_lines.append("<ul>")
                in_list = True
                list_tag = "ul"
            out_lines.append(f"<li>{inline_md(line[2:])}</li>")
            continue

        if in_list:
            out_lines.append(f"</{list_tag}>")
            in_list = False
        out_lines.append(f"<p>{inline_md(line)}</p>")

    if in_list:
        out_lines.append(f"</{list_tag}>")
    return "\n".join(out_lines)


def inline_md(text: str) -> str:
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def score_band(sc):
    """Return tone class name for a 1-10 score."""
    if sc is None:
        return "na"
    if sc >= 7:
        return "strong"
    if sc >= 5:
        return "mixed"
    return "weak"


# ---- Big HTML template as a module-level string.
# Uses string.Template's $placeholder style so CSS/JS braces don't need escaping.
PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Code — User Autopsy</title>

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,500;0,9..144,700;1,9..144,400&family=JetBrains+Mono:wght@400;500;700&family=Inter+Tight:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

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
    --serif: "Fraunces", "Iowan Old Style", "Apple Garamond", Georgia, serif;
    --sans: "Inter Tight", "Söhne", -apple-system, BlinkMacSystemFont, Helvetica, sans-serif;
    --mono: "JetBrains Mono", "SF Mono", Menlo, monospace;
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
    font-size: 15px;
    line-height: 1.55;
    color: var(--ink-soft);
    max-width: 56ch;
    margin: 0 0 30px 0;
  }

  .intro-card {
    border: 1px solid var(--rule);
    background: rgba(255,250,240,0.5);
    padding: 22px 26px;
    margin: 0 0 60px 0;
    font-size: 15.5px;
    line-height: 1.6;
    position: relative;
  }
  .intro-card::before {
    content: "NOTE";
    position: absolute;
    top: -9px; left: 22px;
    background: var(--paper);
    padding: 0 8px;
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
    margin: 30px 0 20px 0;
    border-top: 1px solid var(--rule);
    border-left: 1px solid var(--rule);
  }
  .metrics > .metric {
    border-right: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    padding: 16px 18px 18px 18px;
    background: rgba(255,250,240,0.35);
  }
  @media (max-width: 640px) {
    .metrics { grid-template-columns: repeat(2, 1fr); }
  }
  .metric .n {
    font-family: var(--serif);
    font-variation-settings: "opsz" 72, "wght" 400;
    font-size: 32px;
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
    margin-top: 8px;
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
    margin: 24px 0 48px 0;
    padding: 30px 34px 34px 34px;
    background: linear-gradient(135deg, rgba(255,250,240,0.8) 0%, rgba(236,229,213,0.4) 100%);
    border: 1px solid var(--rule);
    border-left: 4px solid var(--accent);
    position: relative;
  }
  .profile-card::before {
    content: "AT A GLANCE";
    position: absolute;
    top: -10px; left: 30px;
    background: var(--paper);
    padding: 0 10px;
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
    margin: 0 0 22px 0;
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
    margin-top: 20px;
    border-top: 1px solid var(--rule);
    border-left: 1px solid var(--rule);
  }
  @media (max-width: 640px) { .profile-grid { grid-template-columns: repeat(2, 1fr); } }
  .profile-cell {
    border-right: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    padding: 14px 16px 16px 16px;
  }
  .profile-cell .k {
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--ink-muted);
    margin-bottom: 6px;
  }
  .profile-cell .v {
    font-family: var(--serif);
    font-variation-settings: "opsz" 72, "wght" 400;
    font-size: 24px;
    line-height: 1.1;
    letter-spacing: -0.02em;
    color: var(--ink);
  }
  .profile-cell .sub {
    font-family: var(--sans);
    font-size: 12px;
    color: var(--ink-muted);
    margin-top: 3px;
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

  /* Peer review block */
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
    padding: 18px 20px 14px 20px;
    margin: 20px 0;
    height: 340px;
    position: relative;
  }
  .chart-box.tall { height: 420px; }
  .chart-box.short { height: 260px; }
  .chart-box::after {
    content: attr(data-fig);
    position: absolute;
    top: -8px; right: 18px;
    background: var(--paper);
    padding: 0 8px;
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.2em;
    color: var(--ink-muted);
    text-transform: uppercase;
  }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  @media (max-width: 700px) { .two-col { grid-template-columns: 1fr; } }

  /* Evidence library */
  details.evidence {
    border-top: 1px solid var(--rule);
    padding: 14px 0;
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
    grid-template-columns: 90px 1fr 80px;
    gap: 16px;
    align-items: center;
  }
  details.evidence summary::-webkit-details-marker { display: none; }
  details.evidence summary .tag {
    font-family: var(--mono);
    font-size: 9.5px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink-muted);
    padding: 3px 8px;
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
    font-size: 13px;
    color: var(--ink-soft);
  }
  details.evidence summary .proj { color: var(--ink); }
  details.evidence summary .right {
    text-align: right;
    font-family: var(--mono);
    font-size: 11.5px;
    color: var(--ink-muted);
  }
  details.evidence[open] summary { margin-bottom: 14px; }
  details.evidence[open] summary .sid { color: var(--accent); }
  details.evidence p {
    font-family: var(--sans);
    font-size: 14px;
    line-height: 1.55;
    margin: 6px 0;
    padding-left: 106px;
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
    margin: 34px 0 8px 0;
    padding-bottom: 6px;
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

  /* Methodology */
  .method {
    font-family: var(--sans);
    font-size: 14.5px;
    line-height: 1.6;
  }
  .method ul { padding-left: 20px; margin: 8px 0 14px 0; }
  .method li { margin: 4px 0; }
  .caveat {
    background: rgba(160, 67, 30, 0.06);
    border: 1px solid rgba(160, 67, 30, 0.2);
    border-left: 3px solid var(--accent);
    padding: 14px 20px;
    margin: 16px 0;
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
    <b>$total_sessions</b> sessions analyzed<br>
    $date_first → $date_last<br>
    Facet coverage <b>$facets_coverage%</b>
  </div>
</div>

$identity_block

$hero_block

$profile_section

$how_to_read_section

$shipped_section

$artifacts_section

<nav class="toc">
  $toc_links
</nav>

<section id="overview">
  <h2 class="sec" data-num="§ 01">Overview</h2>
  <h2 class="sec-title">The raw numbers, before interpretation.</h2>

  <div class="metrics">
    <div class="metric"><div class="n">$total_sessions</div><div class="lbl">Sessions</div></div>
    <div class="metric"><div class="n">$total_tokens</div><div class="lbl">Total tokens</div></div>
    <div class="metric"><div class="n">$commits_total</div><div class="lbl">Git commits</div></div>
    <div class="metric"><div class="n">${duration_hr}h</div><div class="lbl">Interactive time</div></div>
    <div class="metric"><div class="n">${ta_rate}%</div><div class="lbl">Used Task agent</div></div>
    <div class="metric"><div class="n">${mcp_rate}%</div><div class="lbl">Used MCP</div></div>
    <div class="metric"><div class="n">$facets_coverage%</div><div class="lbl">Facet coverage</div></div>
    <div class="metric"><div class="n">${resp_median}s</div><div class="lbl">Median think time</div></div>
  </div>

  <div class="two-col">
    <div class="chart-box" data-fig="Fig. 01"><canvas id="outcomeChart"></canvas></div>
    <div class="chart-box" data-fig="Fig. 02"><canvas id="stypeChart"></canvas></div>
  </div>
  <div class="chart-box tall" data-fig="Fig. 03"><canvas id="projChart"></canvas></div>
</section>

<section id="scores">
  <h2 class="sec" data-num="§ 02">Scoring</h2>
  <h2 class="sec-title">Eight dimensions, each with its own rubric.</h2>
  <p class="method">
    Scores are derived from explicit thresholds (see
    <code>references/scoring-rubric.md</code>). A high or low score is not a judgment;
    it is a pointer. Compare against the explanation to decide if the threshold is fair.
  </p>

  <div class="overall-strip">Overall &nbsp;·&nbsp; $overall_line</div>

  <div class="score-table">
    $score_rows
  </div>
</section>

<section id="peer-review-section">
  <h2 class="sec" data-num="§ 03">Peer review</h2>
  <h2 class="sec-title">Written by Claude after reading your data.</h2>
  <p class="method">
    Scores above are mechanical. This section is interpretive — an attempt to identify
    three things you do well, three specific improvements, and one neutral observation.
    Every claim is meant to cite a number from your aggregate data or a specific session ID.
  </p>
  <div id="peer-review">
$peer_review_html
  </div>
</section>

<section id="patterns">
  <h2 class="sec" data-num="§ 04">Pattern mining</h2>
  <h2 class="sec-title">What the aggregate hides; what the shape reveals.</h2>

  <h3>4.1 Prompt length × outcome</h3>
  <div class="chart-box short" data-fig="Fig. 04"><canvas id="plenChart"></canvas></div>

  <h3>4.2 Friction categories</h3>
  <div class="chart-box" data-fig="Fig. 05"><canvas id="fricChart"></canvas></div>

  <h3>4.3 Tool usage</h3>
  <div class="chart-box tall" data-fig="Fig. 06"><canvas id="toolChart"></canvas></div>

  <h3>4.4 Weekday × hour heatmap</h3>
  <div class="chart-box tall" data-fig="Fig. 07"><canvas id="heatChart"></canvas></div>

  <h3>4.5 Helpfulness self-rating</h3>
  <p class="method">From <code>facets/</code> — Claude's own rating of how helpful it was per session.</p>
  <div class="chart-box short" data-fig="Fig. 08"><canvas id="helpChart"></canvas></div>
</section>

<section id="trends">
  <h2 class="sec" data-num="§ 05">Weekly trends</h2>
  <h2 class="sec-title">$weekly_count weeks on the record.</h2>

  <h3>Growth curve — composite skill score over time</h3>
  <p class="method">Composite blends good-outcome rate (0.4), Task agent adoption (0.3), and inverse friction rate (0.3) per week. Rising trend suggests the user is improving; flat or falling trend suggests plateau.</p>
  <div class="chart-box" data-fig="Fig. 09"><canvas id="growthChart"></canvas></div>

  <h3>Volume &amp; adoption</h3>
  <div class="chart-box" data-fig="Fig. 10"><canvas id="wkSessions"></canvas></div>
  <div class="chart-box" data-fig="Fig. 11"><canvas id="wkTokens"></canvas></div>
  <div class="chart-box" data-fig="Fig. 12"><canvas id="wkGood"></canvas></div>
  <div class="chart-box" data-fig="Fig. 13"><canvas id="wkFric"></canvas></div>
  <div class="chart-box" data-fig="Fig. 14"><canvas id="wkPlen"></canvas></div>
</section>

<section id="evidence">
  <h2 class="sec" data-num="§ 06">Evidence library</h2>
  <h2 class="sec-title">The sessions that shaped every number above.</h2>
  <p class="method">
    Up to 24 sessions sampled across seven buckets. Expand any row to see the raw
    context the scoring and peer review were built from.
  </p>
  $evidence_html
</section>

<section id="method">
  <h2 class="sec" data-num="§ 07">Methodology</h2>
  <h2 class="sec-title">What this report is — and what it is not.</h2>

  <div class="method">
  <h4>Data sources</h4>
  <ul>
    <li><code>~/.claude/usage-data/session-meta/*.json</code> — auto-recorded by Claude Code.</li>
    <li><code>~/.claude/usage-data/facets/*.json</code> — LLM-classified by <code>/insights</code>; optional but recommended.</li>
    <li><code>~/.claude/projects/**/*.jsonl</code> — raw transcripts, sampled for the evidence library only.</li>
  </ul>

  <h4>Sampling strategy</h4>
  <p>Up to 24 sessions across 7 buckets: 5 highest-friction, 5 top-tokens, 5 most-interrupts, 4 not_achieved, 3 partially_achieved, 4 control (fully_achieved + essential), 2 user_rejected. When facets are absent, fallback is by session duration.</p>

  <h4>Caveats</h4>
  <div class="caveat">
  Facet labels come from an LLM and may be miscategorized. Above roughly 50% facet coverage, outcome-based rules are reliable; below 30%, some dimensions return n/a. Scoring thresholds are rules of thumb, not science. The peer review depends on there being enough data to say specific things — if your data is thin, the review should be short, not padded.
  </div>
  </div>
</section>

<footer>
  <div>cc-user-autopsy · <a href="https://github.com/Imbad0202/cc-user-autopsy">repo</a> · rule-based + LLM-assisted · re-run the skill anytime</div>
</footer>

</main>

<script>
/* Chart.js — editorial palette, minimal chrome */
const INK = '#1a1916', INK_SOFT = '#464239', MUTED = '#7a7363', RULE = '#c9bfa8';
const ACCENT = '#a0431e', OCHRE = '#b28121', FOREST = '#2e5b3e', OXBLOOD = '#6b1b1b', PLUM = '#63355c';
const PAL = [ACCENT, FOREST, OCHRE, OXBLOOD, PLUM, '#516881', '#8a6f45', '#7a4f3e', '#4a6b5b', '#7b5f80', '#a06b45', '#5b6b7a'];

Chart.defaults.font.family = '"Inter Tight", -apple-system, sans-serif';
Chart.defaults.font.size = 11;
Chart.defaults.color = INK_SOFT;
Chart.defaults.borderColor = RULE;

const commonOpts = {
  responsive: true, maintainAspectRatio: false,
  plugins: {
    legend: {
      labels: {
        color: INK_SOFT,
        font: { family: '"JetBrains Mono", monospace', size: 10 },
        usePointStyle: true, boxWidth: 8, padding: 14
      }
    },
    tooltip: {
      backgroundColor: '#1a1916',
      titleColor: '#f4efe6', bodyColor: '#f4efe6',
      titleFont: { family: 'JetBrains Mono', size: 11 },
      bodyFont: { family: 'Inter Tight', size: 12 },
      padding: 10, cornerRadius: 0,
      displayColors: false
    },
    title: {
      display: true,
      color: INK,
      font: { family: '"Fraunces", serif', size: 13, weight: '500' },
      padding: { top: 2, bottom: 14 },
      align: 'start'
    }
  },
  scales: {
    x: { ticks: { color: MUTED, font: { family: 'JetBrains Mono', size: 10 } },
         grid: { color: 'rgba(0,0,0,0.04)', drawBorder: false },
         border: { color: RULE } },
    y: { ticks: { color: MUTED, font: { family: 'JetBrains Mono', size: 10 } },
         grid: { color: 'rgba(0,0,0,0.04)', drawBorder: false },
         border: { color: RULE } }
  }
};

/* ---- Overview charts ---- */
new Chart(document.getElementById('outcomeChart'), {
  type: 'doughnut',
  data: {
    labels: $outcome_labels,
    datasets: [{ data: $outcome_values, backgroundColor: PAL, borderColor: '#f4efe6', borderWidth: 3 }]
  },
  options: { ...commonOpts,
    plugins: { ...commonOpts.plugins, title: { ...commonOpts.plugins.title, text: 'Outcomes · rated sessions' } },
    scales: {}, cutout: '62%' }
});
new Chart(document.getElementById('stypeChart'), {
  type: 'doughnut',
  data: {
    labels: $stype_labels,
    datasets: [{ data: $stype_values, backgroundColor: PAL, borderColor: '#f4efe6', borderWidth: 3 }]
  },
  options: { ...commonOpts,
    plugins: { ...commonOpts.plugins, title: { ...commonOpts.plugins.title, text: 'Session types' } },
    scales: {}, cutout: '62%' }
});

new Chart(document.getElementById('projChart'), {
  type: 'bar',
  data: {
    labels: $proj_labels,
    datasets: [
      { label: 'Sessions', data: $proj_sessions, backgroundColor: INK_SOFT, borderWidth: 0, borderRadius: 0, barPercentage: 0.62, categoryPercentage: 0.9 },
      { label: 'Friction', data: $proj_friction, backgroundColor: ACCENT, borderWidth: 0, borderRadius: 0, barPercentage: 0.62, categoryPercentage: 0.9 }
    ]
  },
  options: { ...commonOpts, plugins: { ...commonOpts.plugins, title: { ...commonOpts.plugins.title, text: 'Top projects · sessions vs friction' } } }
});

/* ---- Prompt length ---- */
new Chart(document.getElementById('plenChart'), {
  type: 'bar',
  data: {
    labels: $plen_buckets,
    datasets: [
      { label: 'Good rate % (full+mostly)', data: $plen_good, backgroundColor: FOREST, borderRadius: 0 },
      { label: 'Session count', data: $plen_n, backgroundColor: INK_SOFT, borderRadius: 0, yAxisID: 'y1' }
    ]
  },
  options: { ...commonOpts,
    plugins: { ...commonOpts.plugins, title: { ...commonOpts.plugins.title, text: 'Prompt length × outcome' } },
    scales: {
      x: commonOpts.scales.x,
      y: { ...commonOpts.scales.y, position: 'left', title: { display: true, text: '%', color: MUTED, font: { family: 'JetBrains Mono', size: 10 } } },
      y1: { position: 'right', grid: { display: false }, ticks: { color: MUTED, font: { family: 'JetBrains Mono', size: 10 } }, title: { display: true, text: 'n', color: MUTED, font: { family: 'JetBrains Mono', size: 10 } } }
    }
  }
});

/* ---- Friction ---- */
new Chart(document.getElementById('fricChart'), {
  type: 'bar',
  data: { labels: $fric_labels, datasets: [{ label: 'count', data: $fric_counts, backgroundColor: OXBLOOD, borderRadius: 0 }] },
  options: { ...commonOpts, indexAxis: 'y', plugins: { ...commonOpts.plugins, legend: { display: false }, title: { ...commonOpts.plugins.title, text: 'Top 12 friction types' } } }
});

/* ---- Tools ---- */
new Chart(document.getElementById('toolChart'), {
  type: 'bar',
  data: { labels: $tool_labels, datasets: [{ label: 'calls', data: $tool_counts, backgroundColor: INK, borderRadius: 0 }] },
  options: { ...commonOpts, indexAxis: 'y', plugins: { ...commonOpts.plugins, legend: { display: false }, title: { ...commonOpts.plugins.title, text: 'Top 15 tool calls' } } }
});

/* ---- Heatmap (scatter proxy) ---- */
const heatGrid = $heat_grid;
const heatMax = Math.max(1, ...heatGrid.flat());
const heatLabels = $heat_labels;
const heatData = [];
for (let wd = 0; wd < 7; wd++) for (let hr = 0; hr < 24; hr++) {
  heatData.push({ x: hr, y: 6 - wd, v: heatGrid[wd][hr] });
}
new Chart(document.getElementById('heatChart'), {
  type: 'scatter',
  data: { datasets: [{
    data: heatData,
    backgroundColor: (ctx) => {
      const v = ctx.raw.v; if (v === 0) return 'rgba(201,191,168,0.25)';
      const t = v / heatMax;
      /* blend from paper-deep to accent */
      const r = Math.round(236 + (160 - 236) * t);
      const g = Math.round(229 + (67 - 229) * t);
      const b = Math.round(213 + (30 - 213) * t);
      return `rgb(${r},${g},${b})`;
    },
    pointRadius: 11, pointStyle: 'rectRounded', pointBorderWidth: 0
  }] },
  options: { ...commonOpts,
    plugins: { ...commonOpts.plugins, legend: { display: false },
      title: { ...commonOpts.plugins.title, text: 'Weekday × hour · session density' },
      tooltip: { ...commonOpts.plugins.tooltip, callbacks: { label: (ctx) => `${heatLabels[6 - ctx.raw.y]} ${ctx.raw.x}:00 → ${ctx.raw.v} sessions`, title: () => '' } } },
    scales: {
      x: { min: -0.5, max: 23.5, ticks: { stepSize: 2, color: MUTED, font: { family: 'JetBrains Mono', size: 10 }, callback: (v) => v + ':00' }, grid: { color: 'rgba(0,0,0,0.04)', drawBorder: false }, border: { color: RULE } },
      y: { min: -0.5, max: 6.5, ticks: { stepSize: 1, color: MUTED, font: { family: 'JetBrains Mono', size: 10 }, callback: (v) => heatLabels[6 - v] || '' }, grid: { color: 'rgba(0,0,0,0.04)', drawBorder: false }, border: { color: RULE } }
    }
  }
});

/* ---- Helpfulness ---- */
new Chart(document.getElementById('helpChart'), {
  type: 'bar',
  data: { labels: $help_labels, datasets: [{ label: 'count', data: $help_values, backgroundColor: PAL, borderRadius: 0 }] },
  options: { ...commonOpts, plugins: { ...commonOpts.plugins, legend: { display: false }, title: { ...commonOpts.plugins.title, text: "Claude's self-rated helpfulness" } } }
});

/* ---- Growth curve ---- */
new Chart(document.getElementById('growthChart'), {
  type: 'line',
  data: { labels: $growth_labels, datasets: [
    { label: 'Composite score', data: $growth_composite, borderColor: ACCENT, backgroundColor: 'rgba(160,67,30,0.12)', borderWidth: 2, tension: 0.25, fill: true, pointRadius: 3, pointBackgroundColor: ACCENT },
    { label: 'Good-outcome rate', data: $growth_good, borderColor: FOREST, borderWidth: 1.5, tension: 0.25, pointRadius: 2, borderDash: [3, 3] },
    { label: 'Task agent adoption', data: $growth_ta, borderColor: PLUM, borderWidth: 1.5, tension: 0.25, pointRadius: 2, borderDash: [3, 3] }
  ] },
  options: { ...commonOpts, plugins: { ...commonOpts.plugins, title: { ...commonOpts.plugins.title, text: 'Composite skill curve (0-100)' } },
    scales: { x: commonOpts.scales.x, y: { ...commonOpts.scales.y, min: 0, max: 100 } } }
});

/* ---- Weekly series ---- */
const wL = $wk_labels;
new Chart(document.getElementById('wkSessions'), {
  type: 'line',
  data: { labels: wL, datasets: [
    { label: 'Sessions', data: $wk_sessions, borderColor: INK, backgroundColor: 'rgba(26,25,22,0.08)', borderWidth: 1.5, tension: 0.2, fill: true, pointRadius: 2, pointBackgroundColor: INK },
    { label: 'With Task agent', data: $wk_ta, borderColor: ACCENT, borderWidth: 1.5, tension: 0.2, pointRadius: 2, pointBackgroundColor: ACCENT, borderDash: [4, 3] }
  ] },
  options: { ...commonOpts, plugins: { ...commonOpts.plugins, title: { ...commonOpts.plugins.title, text: 'Weekly sessions · Task agent adoption' } } }
});
new Chart(document.getElementById('wkTokens'), {
  type: 'line',
  data: { labels: wL, datasets: [
    { label: 'Tokens (M)', data: $wk_tokens_m, borderColor: OCHRE, backgroundColor: 'rgba(178,129,33,0.1)', borderWidth: 1.5, tension: 0.2, fill: true, pointRadius: 2, pointBackgroundColor: OCHRE, yAxisID: 'y' },
    { label: 'Commits', data: $wk_commits, borderColor: FOREST, borderWidth: 1.5, tension: 0.2, pointRadius: 2, pointBackgroundColor: FOREST, yAxisID: 'y1' }
  ] },
  options: { ...commonOpts,
    plugins: { ...commonOpts.plugins, title: { ...commonOpts.plugins.title, text: 'Weekly tokens × commits' } },
    scales: { x: commonOpts.scales.x, y: { ...commonOpts.scales.y, position: 'left', title: { display: true, text: 'M tokens', color: MUTED, font: { family: 'JetBrains Mono', size: 10 } } },
      y1: { position: 'right', grid: { display: false }, ticks: { color: MUTED, font: { family: 'JetBrains Mono', size: 10 } }, title: { display: true, text: 'commits', color: MUTED, font: { family: 'JetBrains Mono', size: 10 } } }
    } }
});
new Chart(document.getElementById('wkGood'), {
  type: 'line',
  data: { labels: wL, datasets: [
    { label: 'Good rate %', data: $wk_goodrate, borderColor: FOREST, backgroundColor: 'rgba(46,91,62,0.12)', borderWidth: 1.5, tension: 0.2, fill: true, pointRadius: 2, pointBackgroundColor: FOREST }
  ] },
  options: { ...commonOpts, plugins: { ...commonOpts.plugins, title: { ...commonOpts.plugins.title, text: 'Weekly good-outcome rate %' } },
    scales: { x: commonOpts.scales.x, y: { ...commonOpts.scales.y, min: 0, max: 100 } } }
});
new Chart(document.getElementById('wkFric'), {
  type: 'bar',
  data: { labels: wL, datasets: [{ label: 'Friction count', data: $wk_friction, backgroundColor: OXBLOOD, borderRadius: 0 }] },
  options: { ...commonOpts, plugins: { ...commonOpts.plugins, legend: { display: false }, title: { ...commonOpts.plugins.title, text: 'Weekly friction totals' } } }
});
new Chart(document.getElementById('wkPlen'), {
  type: 'line',
  data: { labels: wL, datasets: [
    { label: 'Avg prompt length (chars)', data: $wk_plen, borderColor: PLUM, backgroundColor: 'rgba(99,53,92,0.1)', borderWidth: 1.5, tension: 0.2, fill: true, pointRadius: 2, pointBackgroundColor: PLUM }
  ] },
  options: { ...commonOpts, plugins: { ...commonOpts.plugins, title: { ...commonOpts.plugins.title, text: 'Weekly avg prompt length' } } }
});
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
    ap.add_argument("--profile", default=None,
                    help="Optional JSON file with identity info to put in the header. "
                    "Schema: {name, role, location, tagline, contact: {email, github, "
                    "twitter, website}, links: [{label, url}]}. HR version shows a full "
                    "letterhead; self version shows a subtle signature.")
    args = ap.parse_args()

    data = json.loads(Path(args.input).expanduser().read_text())
    samples = json.loads(Path(args.samples).expanduser().read_text())
    pr_md = ""
    if args.peer_review:
        p = Path(args.peer_review).expanduser()
        if p.exists():
            pr_md = p.read_text()
    pr_html = md_to_html(pr_md)

    artifacts_list = []
    if args.artifacts:
        p = Path(args.artifacts).expanduser()
        if p.exists():
            try:
                artifacts_list = json.loads(p.read_text())
            except Exception as e:
                print(f"warn: failed to parse artifacts file: {e}", file=sys.stderr)

    profile_info = {}
    if args.profile:
        p = Path(args.profile).expanduser()
        if p.exists():
            try:
                profile_info = json.loads(p.read_text())
            except Exception as e:
                print(f"warn: failed to parse profile file: {e}", file=sys.stderr)

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
        "D1_delegation": "Delegation (Task agent usage)",
        "D2_root_cause": "Root-cause debugging",
        "D3_prompt_quality": "Prompt quality",
        "D4_context_mgmt": "Context management",
        "D5_interrupt_judgment": "Interrupt judgment",
        "D6_tool_breadth": "Tool breadth",
        "D7_writing_consistency": "Writing consistency",
        "D8_time_mgmt": "Time-of-day management",
    }
    score_rows = ""
    for key, title in dim_titles.items():
        s = scores.get(key, {})
        sc = s.get("score")
        band = score_band(sc)
        display = f'<span class="num">{sc}</span><span class="out">/ 10</span>' if sc is not None else 'n/a'
        dim_label = f"{key.split('_', 1)[0]} · {key.split('_', 1)[1].replace('_', ' ')}"
        reason = s.get("explanation") or s.get("reason", "")
        score_rows += f'''<div class="score-row {band}">
  <div class="dim">{dim_label}</div>
  <div class="body">
    <div class="h">{title}</div>
    <p class="exp">{reason}</p>
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
        overall_line = "Not enough data for an overall score."

    # Evidence
    tag_labels = {
        "high_friction": "Highest friction",
        "top_token": "Highest token count",
        "top_interrupt": "Most interrupts",
        "not_achieved": "Not achieved",
        "partial": "Partially achieved",
        "control_good": "Control · fully achieved + essential",
        "user_rejected": "You rejected Claude's action",
        "long_duration": "Longest duration · fallback",
    }
    by_tag = {}
    for sid, info in samples.items():
        by_tag.setdefault(info["tag"], []).append({"sid": sid, **info})
    evidence_html = ""
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
    <span class="tag {tag}">{tag.replace('_', ' ')}</span>
    <span><span class="sid">{s["sid"][:8]}</span> · <span class="proj">{proj}</span> · {outcome}</span>
    <span class="right">{tok_str} tok · {dur}m</span>
  </summary>
  <p><strong>Summary</strong> · {summary}</p>
  <p><strong>Friction detail</strong> · {frictxt}</p>
  <p><strong>First prompt</strong> · <code>{fp}</code></p>
  <p><strong>Friction counts</strong> · <code>{fric}</code></p>
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
                contact_lines.append(f'<a href="mailto:{contact["email"]}">{contact["email"]}</a>')
            if contact.get("github"):
                gh = contact["github"].lstrip("@")
                contact_lines.append(f'<a href="https://github.com/{gh}">github.com/{gh}</a>')
            if contact.get("twitter"):
                tw = contact["twitter"].lstrip("@")
                contact_lines.append(f'<a href="https://twitter.com/{tw}">@{tw}</a>')
            if contact.get("website"):
                w = contact["website"]
                display_w = w.replace("https://", "").replace("http://", "").rstrip("/")
                contact_lines.append(f'<a href="{w}">{display_w}</a>')
            for ln in links:
                lbl = ln.get("label", "")
                url = ln.get("url", "")
                contact_lines.append(f'<a href="{url}">{lbl}</a>')
            contact_html = "<br>".join(contact_lines) if contact_lines else ""

            parts = []
            if name:
                parts.append(f'<div class="name">{name}</div>')
            if role:
                parts.append(f'<div class="role">{role}</div>')
            if location:
                parts.append(f'<div class="loc">{location}</div>')
            if tagline:
                parts.append(f'<div class="tagline">"{tagline}"</div>')

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
                sig_parts.append(f"<b>{name}</b>")
            if role:
                sig_parts.append(role)
            if location:
                sig_parts.append(location)
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
                f" Honest weakest area: <em>{weakest_title}</em> ({weakest[1]}/10)."
            )
        if profile["specialty"]:
            lede_parts.append(f" Specialty: {profile['specialty']}.")
        profile_lede_html = "".join(lede_parts)
    else:
        profile_lede_html = ""

    # Build hero + profile section depending on audience
    if args.audience == "hr":
        hero_block = f'''<h1 class="title">Claude Code<br><em>practice summary</em></h1>
<p class="dek">
  An automated, evidence-backed summary of how this user works with Claude Code —
  generated from their local session data, not self-reported. Structured for
  hiring managers reviewing AI-native engineering candidates.
</p>'''
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
      <div class="sub">commits / interactive hour</div>
    </div>
    <div class="profile-cell">
      <div class="k">Parallel work</div>
      <div class="v">{profile.get("ta_pct", 0):.0f}%</div>
      <div class="sub">Task agent adoption</div>
    </div>
    <div class="profile-cell">
      <div class="k">Tool breadth</div>
      <div class="v">{profile.get("mcp_pct", 0):.0f}%</div>
      <div class="sub">MCP-using sessions</div>
    </div>
    <div class="profile-cell">
      <div class="k">Self-audit</div>
      <div class="v">{scores_overall if scores_overall else "n/a"}<span style="font-size:14px;color:var(--ink-muted);"> / 10</span></div>
      <div class="sub">8-dim rule-based</div>
    </div>
    <div class="profile-cell">
      <div class="k">Focus</div>
      <div class="v" style="font-size:14.5px;line-height:1.3;">{profile.get("specialty", "—")}</div>
      <div class="sub">{profile.get("top_project_share_pct", 0):.0f}% on top project</div>
    </div>
  </div>
</div>'''

        # Shipped artifacts section
        if shipped:
            shipped_items = ""
            for item in shipped[:6]:
                dur_hr = item["project_duration_min"] / 60
                shipped_items += f'''<div class="shipped-item">
  <div>
    <div class="proj">{item["project"]}</div>
    <div class="proj-sub">{item["project_sessions"]} sessions · {dur_hr:.0f}h</div>
  </div>
  <div class="desc">{item["summary"]}</div>
  <div class="stats">
    {item["project_commits"]} commits<br>
    {fmt(item["total_tokens"])} tok / top session
  </div>
</div>'''
            shipped_section = f'''<section id="shipped">
  <h2 class="sec" data-num="§ HR-02">Shipped with Claude</h2>
  <h2 class="sec-title">Representative outcomes — fully achieved, essential-tier sessions, grouped by project.</h2>
  <p class="method">Extracted from session facets where <code>outcome = fully_achieved</code> and <code>helpfulness ∈ (essential, very_helpful)</code>. One representative per project, ranked by total time invested.</p>
  <div class="shipped-list">{shipped_items}</div>
</section>'''
        else:
            shipped_section = ""

        # Public artifacts (from --artifacts JSON)
        if artifacts_list:
            artifact_rows = ""
            for a in artifacts_list:
                artifact_rows += f'''<div class="artifact-row">
  <div>
    <div class="name">{a.get("name", "(unnamed)")}</div>
    <div class="desc">{a.get("description", "")}</div>
  </div>
  <div class="link"><a href="{a.get("url", "#")}">{a.get("url", "").replace("https://", "")}</a></div>
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
        how_to_read_section = '''<details class="how-to-read" open>
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
</dl>
</div>
</details>'''

        # TOC — HR-ordered
        toc_links = (
            '<a href="#shipped">Shipped with Claude</a>'
            '<a href="#overview">Raw numbers</a>'
            '<a href="#scores">8-dim self-audit</a>'
            '<a href="#peer-review-section">Peer review</a>'
            '<a href="#trends">Growth curve & trends</a>'
            '<a href="#patterns">Pattern mining</a>'
            '<a href="#evidence">Evidence library</a>'
            '<a href="#method">Methodology</a>'
        )
    else:
        # --- SELF audience (default, original layout) ---
        hero_block = f'''<h1 class="title">A diagnostic letter<br>on <em>your</em> Claude Code practice</h1>
<p class="dek">
  This report is the output of a skill that reads your local usage data and gives you
  a direct, evidence-backed peer review of your workflow. Eight rule-based scores,
  thirteen figures, twenty-four session citations. No sandwiching.
</p>
<div class="intro-card">
  The built-in <code>/insights</code> report is helpful but tends to celebrate. This one tries
  to be honest. Every score below has a threshold you can audit, and every claim in
  the peer review cites a number from your own data. If a dimension lacks data, it says so.
  {preliminary_warning}
</div>'''
        profile_section = ""
        shipped_section = ""
        artifacts_section = ""
        how_to_read_section = ""
        toc_links = (
            '<a href="#overview">Overview</a>'
            '<a href="#scores">Rule-based Scores</a>'
            '<a href="#peer-review-section">Personalized Peer Review</a>'
            '<a href="#patterns">Pattern Mining</a>'
            '<a href="#trends">Weekly Trends</a>'
            '<a href="#evidence">Evidence Library</a>'
            '<a href="#method">Methodology</a>'
        )

    # Growth curve chart section (both audiences but different placement)
    growth = agg.get("growth_curve", [])
    growth_labels = json.dumps([g["week"] for g in growth])
    growth_composite = json.dumps([g["composite_score"] for g in growth])
    growth_ta = json.dumps([g["ta_rate"] for g in growth])
    growth_good = json.dumps([g["good_rate"] for g in growth])

    # Assemble via string.Template to avoid CSS brace escaping
    subs = {
        "identity_block": identity_block,
        "hero_block": hero_block,
        "profile_section": profile_section,
        "how_to_read_section": how_to_read_section,
        "shipped_section": shipped_section,
        "artifacts_section": artifacts_section,
        "toc_links": toc_links,
        "growth_labels": growth_labels,
        "growth_composite": growth_composite,
        "growth_good": growth_good,
        "growth_ta": growth_ta,
        "total_sessions": total,
        "total_tokens": fmt(total_tok),
        "commits_total": commits_total,
        "duration_hr": duration_hr,
        "ta_rate": ta_rate,
        "mcp_rate": mcp_rate,
        "facets_coverage": meta["facets_coverage_pct"],
        "resp_median": int(agg["response_times"]["median_seconds"]),
        "date_first": meta["date_range"]["first"][:10],
        "date_last": meta["date_range"]["last"][:10],
        "preliminary_warning": preliminary_warning,
        "overall_line": overall_line,
        "score_rows": score_rows,
        "peer_review_html": pr_html,
        "weekly_count": len(weekly),
        "evidence_html": evidence_html,
        # Chart data
        "outcome_labels": json.dumps(list(agg["outcomes"].keys())),
        "outcome_values": json.dumps(list(agg["outcomes"].values())),
        "stype_labels": json.dumps(list(agg["session_types"].keys())),
        "stype_values": json.dumps(list(agg["session_types"].values())),
        "proj_labels": json.dumps([p[0][:25] for p in proj_items]),
        "proj_sessions": json.dumps([p[1]["sessions"] for p in proj_items]),
        "proj_friction": json.dumps([p[1]["friction"] for p in proj_items]),
        "plen_buckets": json.dumps(plen_buckets),
        "plen_good": json.dumps(plen_good_pct),
        "plen_n": json.dumps(plen_n),
        "fric_labels": json.dumps([f[0] for f in fric_top]),
        "fric_counts": json.dumps([f[1] for f in fric_top]),
        "tool_labels": json.dumps([re.sub(r"mcp__[^_]+__", "", t[0])[:28] for t in tool_top]),
        "tool_counts": json.dumps([t[1] for t in tool_top]),
        "heat_grid": json.dumps(grid),
        "heat_labels": json.dumps(WEEKDAY_LABELS),
        "help_labels": json.dumps(list(agg["helpfulness"].keys())),
        "help_values": json.dumps(list(agg["helpfulness"].values())),
        "wk_labels": json.dumps(w_labels),
        "wk_sessions": json.dumps([w["sessions"] for w in weekly]),
        "wk_tokens_m": json.dumps([round(w["tokens"] / 1e6, 3) for w in weekly]),
        "wk_commits": json.dumps([w["commits"] for w in weekly]),
        "wk_goodrate": json.dumps([w["good_rate_pct"] for w in weekly]),
        "wk_friction": json.dumps([w["friction"] for w in weekly]),
        "wk_plen": json.dumps([w["avg_prompt_len"] for w in weekly]),
        "wk_ta": json.dumps([w["uses_task_agent"] for w in weekly]),
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
