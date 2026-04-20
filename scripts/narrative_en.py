"""English narrative for cc-user-autopsy reports.

One of two narrative modules (see narrative_zh.py). Each dimension function
reads a metrics dict produced by scripts/aggregate.py and returns the
explanation or pattern sentence for that dimension, in English.

Parity rules (enforced by tests/test_narrative_parity.py):
- Must access metrics only via metrics["<literal_key>"] or
  metrics.get("<literal_key>", ...). No dynamic keys, no **metrics
  unpacking.
- The sibling module narrative_zh.py must expose the same public function
  set and each function pair must cite the same set of metric keys.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Dimension explanations (always emitted)
# ---------------------------------------------------------------------------

def d1_explanation(metrics: dict) -> str:
    ta_rate = metrics["metric_ta_rate_pct"]
    good_rate = metrics["metric_good_rate_with_ta_pct"]
    return (
        f"{ta_rate:.0f}% of sessions used Task agent; good-outcome rate "
        f"with Task agent was {good_rate:.0f}%."
    )


def d2_explanation(metrics: dict) -> str:
    count = metrics["metric_iter_buggy_count"]
    pct = metrics["metric_iter_buggy_pct"]
    return (
        f"{count} sessions ({pct:.0f}%) were iterative_refinement with "
        f"buggy_code friction, a marker for symptom-level patching."
    )


def d3_explanation(metrics: dict) -> str:
    rate_100 = metrics["metric_pct_prompts_ge_100_chars"]
    best_bucket = metrics["metric_most_efficient_bucket"]
    return (
        f"{rate_100:.0f}% of sessions used prompts of 100 or more characters. "
        f"Most efficient prompt-length bucket for tokens/commit: {best_bucket}."
    )


def d4_explanation(metrics: dict) -> str:
    otl = metrics["metric_output_token_limit_sessions"]
    enc = metrics["metric_effort_no_commit_pct"]
    enc_n = metrics.get("metric_effort_no_commit_sample")
    long_intr = metrics["metric_long_session_interrupt_rate_pct"]
    n_suffix = f" (n={enc_n})" if enc_n else ""
    return (
        f"{otl} sessions hit output-token-limit. {enc:.0f}% of sessions over "
        f"20 minutes had zero commits{n_suffix}. Long-session interrupt rate: "
        f"{long_intr:.0f}%."
    )


def d5_explanation(metrics: dict) -> str:
    recovery = metrics["metric_interrupt_recovery_pct"]
    n_interrupted = metrics["metric_interrupted_sessions"]
    return (
        f"{recovery:.0f}% of interrupted sessions still reached a good outcome "
        f"(sample: {n_interrupted} interrupted sessions)."
    )


def d6_explanation(metrics: dict) -> str:
    mcp = metrics["metric_mcp_rate_pct"]
    top3 = metrics["metric_top3_share_pct"]
    return (
        f"{mcp:.0f}% of sessions used any MCP tool; the top three tools "
        f"(Bash/Read/Edit) account for {top3:.0f}% of all tool calls."
    )


def d7_explanation(metrics: dict) -> str:
    n = metrics["metric_writing_sessions"]
    avg = metrics["metric_misunderstood_per_writing_session"]
    return (
        f"Across {n} writing-related sessions, average misunderstood_request "
        f"per session was {avg:.2f}."
    )


def d8_explanation(metrics: dict) -> str:
    worst = metrics["metric_worst_hour"]
    best = metrics["metric_best_hour"]
    ratio = metrics["metric_friction_ratio_hi_lo"]
    return (
        f"Worst hour ({worst['hour']:02d}:00) has {ratio:.1f}x the friction "
        f"rate of the best hour ({best['hour']:02d}:00)."
    )


def d9_explanation(metrics: dict) -> str:
    good = metrics["metric_tokens_per_good"]
    not_good = metrics["metric_tokens_per_not_good"]
    ratio = metrics["metric_ratio"]
    cache = metrics.get("metric_cache_hit_pct")
    cache_frag = f" Cache hit ratio {cache:.0f}%." if cache is not None else ""
    return (
        f"Other rated sessions averaged {not_good:,.0f} tokens versus "
        f"{good:,.0f} for good outcomes ({ratio:.2f}x more).{cache_frag}"
    )


# ---------------------------------------------------------------------------
# Dimension patterns (emit only when metrics["pattern_emit"] is True)
# ---------------------------------------------------------------------------

def d1_pattern(metrics: dict) -> str:
    ta_rate = metrics["metric_ta_rate_pct"]
    good_rate = metrics["metric_good_rate_with_ta_pct"]
    return (
        f"Sessions that used Task agent had a {good_rate:.0f}% good-outcome "
        f"rate; Task agent adoption across sessions was {ta_rate:.0f}%."
    )


def d2_pattern(metrics: dict) -> str:
    count = metrics["metric_iter_buggy_count"]
    pct = metrics["metric_iter_buggy_pct"]
    return (
        f"{count} sessions ({pct:.0f}%) paired iterative_refinement with "
        f"buggy_code. Root-cause debugging would compress this."
    )


def d3_pattern(metrics: dict) -> str:
    rate_100 = metrics["metric_pct_prompts_ge_100_chars"]
    best_bucket = metrics["metric_most_efficient_bucket"]
    return (
        f"Long prompts appeared in {rate_100:.0f}% of sessions; "
        f"bucket {best_bucket} had the lowest tokens-per-commit."
    )


def d4_pattern(metrics: dict) -> str:
    otl = metrics["metric_output_token_limit_sessions"]
    enc = metrics["metric_effort_no_commit_pct"]
    return (
        f"{otl} sessions hit output-token-limit; {enc:.0f}% of long sessions "
        f"had zero commits, suggesting effort without landing results."
    )


def d5_pattern(metrics: dict) -> str:
    recovery = metrics["metric_interrupt_recovery_pct"]
    n = metrics["metric_interrupted_sessions"]
    return (
        f"{recovery:.0f}% of interrupted sessions ({n} total) still reached a "
        f"good outcome, suggesting interrupts correct course rather than derail."
    )


def d6_pattern(metrics: dict) -> str:
    mcp = metrics["metric_mcp_rate_pct"]
    top3 = metrics["metric_top3_share_pct"]
    return (
        f"MCP tools appeared in {mcp:.0f}% of sessions; Bash/Read/Edit "
        f"consumed {top3:.0f}% of all tool calls."
    )


def d7_pattern(metrics: dict) -> str:
    n = metrics["metric_writing_sessions"]
    avg = metrics["metric_misunderstood_per_writing_session"]
    return (
        f"Over {n} writing sessions, average misunderstood_request was "
        f"{avg:.2f} per session."
    )


def d8_pattern(metrics: dict) -> str:
    worst = metrics["metric_worst_hour"]
    best = metrics["metric_best_hour"]
    ratio = metrics["metric_friction_ratio_hi_lo"]
    return (
        f"{worst['hour']:02d}:00 has {ratio:.1f}x the friction rate of "
        f"{best['hour']:02d}:00."
    )


def d9_pattern(metrics: dict) -> str:
    good = metrics["metric_tokens_per_good"]
    not_good = metrics["metric_tokens_per_not_good"]
    ratio = metrics["metric_ratio"]
    return (
        f"Good-outcome sessions averaged {good:,.0f} tokens; other rated "
        f"sessions averaged {not_good:,.0f} ({ratio:.2f}x more)."
    )


# ---------------------------------------------------------------------------
# Single-value lookups
# ---------------------------------------------------------------------------

_OUTCOME_LABELS = {
    "fully_achieved": "Fully achieved",
    "mostly_achieved": "Mostly achieved",
    "partially_achieved": "Partially achieved",
    "not_achieved": "Not achieved",
    "unclear_from_transcript": "Unclear from transcript",
}

_EVIDENCE_BADGES = {
    "high_friction": "High friction",
    "top_token": "Top token",
    "top_interrupt": "Top interrupt",
    "not_achieved": "Not achieved",
    "partial": "Partial",
    "control_good": "Control good",
    "user_rejected": "User rejected",
    "long_duration": "Long duration",
}


def outcome_label(outcome: str) -> str:
    """Return display label for an outcome value, or the raw string if unknown."""
    return _OUTCOME_LABELS.get(outcome, outcome)


def evidence_badge(tag: str) -> str:
    """Return display label for an evidence tag, or the raw string if unknown."""
    return _EVIDENCE_BADGES.get(tag, tag)


def no_facet_label() -> str:
    return "(no facet)"


# ---------------------------------------------------------------------------
# Methodology block (static prose)
# ---------------------------------------------------------------------------

def methodology_subtitle() -> str:
    return "What this report shows, and what it cannot."


def methodology_sampling_body() -> str:
    return (
        "Up to 24 sessions are drawn into the evidence library, across seven "
        "buckets: highest friction (5), highest token count (5), most "
        "interrupts (5), not achieved (4), partially achieved (3), control "
        "group of fully achieved plus essential outcomes (4), and sessions "
        "where you rejected Claude's action (2). When facet data is missing, "
        "session duration substitutes as the sampling key."
    )


def methodology_caveats_body() -> str:
    return (
        "Facet labels come from an LLM classifier and can misclassify. "
        "Facet coverage must reach about 50% for outcome-based rules to be "
        "reliable; below 30%, some dimensions return n/a. Score thresholds "
        "are heuristics, not formulas. Peer review needs enough data to draw "
        "a concrete conclusion; when data is thin, feedback should be short, "
        "not padded."
    )
