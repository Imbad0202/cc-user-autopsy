"""Single source of truth for every UI chrome string in cc-user-autopsy
reports. Two locales: en (canonical) and zh_TW.

Hard rules (enforced by tests/test_locales.py):
  - Both locales must share the exact same key set.
  - t(locale, key) raises KeyError on any miss — silent fallback to en
    would defeat the whole "no mixed-language reports" intent.
  - zh_TW values must not use em-dash (— or ——). Use comma + clause
    continuation instead. Single — leaks from copy-pasted English source;
    double —— is the AI public-relations tic the user explicitly bans.

When adding a new chrome string:
  1. Add the key to BOTH dicts in this file.
  2. Reference it via t(args.locale, "your_key") in build_html.py.
  3. Run `python3 -m unittest tests.test_locales` — keyset mismatch fails
     loud.
"""

STRINGS = {
    "en": {
        # --- Document chrome ---
        "report_title": "Claude Code — User Autopsy",
        "html_lang": "en",
        # --- Section headers ---
        "section_overview": "Overview",
        "section_overview_subtitle": "The raw numbers, before interpretation.",
        "section_scoring": "Scoring",
        "section_scoring_subtitle": "Nine dimensions, each with its own rubric.",
        "section_scoring_method": (
            "Scores are derived from explicit thresholds (see "
            "<code>references/scoring-rubric.md</code>). A high or low score is not a "
            "judgment; it is a pointer. Compare against the explanation to decide if "
            "the threshold is fair."
        ),
        "section_scoring_overall_label": "Overall",
        "section_peer_review": "Peer review",
        "section_peer_review_subtitle": "Written by Claude after reading your data.",
        "section_peer_review_method": (
            "Scores above are mechanical. This section is interpretive: an attempt to "
            "identify three things you do well, three specific improvements, and one "
            "neutral observation. Every claim is meant to cite a number from your "
            "aggregate data or a specific session ID."
        ),
        "section_patterns": "Pattern mining",
        "section_patterns_subtitle": "What the aggregate hides; what the shape reveals.",
        "patterns_h_plen": "4.1 Prompt length × outcome",
        "patterns_h_friction": "4.2 Friction categories",
        "patterns_h_tools": "4.3 Tool usage",
        "patterns_h_heatmap": "4.4 Weekday × hour heatmap",
        "patterns_h_helpfulness": "4.5 Helpfulness self-rating",
        "patterns_helpfulness_method": (
            "From <code>facets/</code>: Claude's own rating of how helpful it was per session."
        ),
        "section_trends": "Weekly trends",
        "trends_h_growth": "Growth curve, composite skill score over time",
        "trends_growth_method": (
            "Composite blends good-outcome rate (0.4), Task agent adoption (0.3), and "
            "inverse friction rate (0.3) per week. Rising trend suggests the user is "
            "improving; flat or falling trend suggests plateau."
        ),
        "trends_h_volume": "Volume &amp; adoption",
        "trends_subtitle_template": "{n} weeks on the record.",
        "section_evidence": "Evidence library",
        "section_evidence_subtitle": "The sessions that shaped every number above.",
        "section_evidence_method": (
            "Up to 24 sessions sampled across seven buckets. Expand any row to see the "
            "raw context the scoring and peer review were built from."
        ),
        "section_method": "Methodology",
        "method_h_sources": "Data sources",
        "method_src_session_meta": (
            "<code>~/.claude/usage-data/session-meta/*.json</code>: auto-recorded by Claude Code."
        ),
        "method_src_facets": (
            "<code>~/.claude/usage-data/facets/*.json</code>: LLM-classified by "
            "<code>/insights</code>; optional but recommended."
        ),
        "method_src_transcripts": (
            "<code>~/.claude/projects/**/*.jsonl</code>: raw transcripts, sampled for "
            "the evidence library only."
        ),
        "method_h_sampling": "Sampling strategy",
        "method_h_caveats": "Caveats",
        # --- Hero block (self audience) ---
        "hero_self_title_line1": "A diagnostic letter",
        "hero_self_title_line2_pre": "on",
        "hero_self_title_line2_em": "your",
        "hero_self_title_line2_post": "Claude Code practice",
        "hero_self_dek": (
            "This report is the output of a skill that reads your local usage data and "
            "gives you a direct, evidence-backed peer review of your workflow. Nine "
            "rule-based scores, thirteen figures, twenty-four session citations. No sandwiching."
        ),
        "hero_self_intro_card": (
            "The built-in <code>/insights</code> report is helpful but tends to celebrate. "
            "This one tries to be honest. Every score below has a threshold you can audit, "
            "and every claim in the peer review cites a number from your own data. "
            "If a dimension lacks data, it says so."
        ),
        # --- Hero block (HR audience) ---
        "hero_hr_title_line1": "Claude Code",
        "hero_hr_title_line2_em": "practice summary",
        "hero_hr_dek": (
            "An automated, evidence-backed summary of how this user works with "
            "Claude Code, generated from their local session data, not self-reported. "
            "Structured for hiring managers reviewing AI-native engineering candidates."
        ),
        # --- Letterhead ---
        "letterhead_sessions_analyzed": "sessions analyzed",
        "letterhead_facet_coverage": "Facet coverage",
        # --- Profile-card sub labels (HR view) ---
        "profile_sub_commits_per_hour": "commits / interactive hour",
        "profile_sub_task_agent_adoption": "Task agent adoption",
        "profile_sub_mcp_sessions": "MCP-using sessions",
        # --- TOC nav links (self audience) ---
        "toc_self_overview": "Overview",
        "toc_self_scores": "Rule-based scores",
        "toc_self_peer_review": "Peer review",
        "toc_self_try_this": "This week",
        "toc_self_case_study": "Case study",
        "toc_self_patterns": "Pattern mining",
        "toc_self_trends": "Weekly trends",
        "toc_self_evidence": "Evidence library",
        "toc_self_method": "Methodology",
        # --- TOC nav links (HR audience) ---
        "toc_hr_shipped": "Shipped with Claude",
        "toc_hr_overview": "Raw numbers",
        "toc_hr_scores": "Hiring signals",
        "toc_hr_peer_review": "Peer review",
        "toc_hr_case_study": "Case study",
        "toc_hr_trends": "Growth curve",
        "toc_hr_patterns": "Pattern mining",
        "toc_hr_evidence": "Evidence library",
        "toc_hr_method": "Methodology",
        # --- Chart series labels (JS) ---
        "series_session_count": "Session count",
        "series_good_rate_pct": "Good rate %",
        "series_composite_score": "Composite score",
        "series_good_outcome_rate": "Good-outcome rate",
        "series_task_agent_adoption": "Task agent adoption",
        "series_sessions": "Sessions",
        "series_with_task_agent": "With Task agent",
        "series_tokens_m": "Tokens (M)",
        "series_commits": "Commits",
        "series_friction": "Friction",
        "series_avg_prompt_length": "Avg prompt length",
        # --- Activity panel tiles ---
        "tile_full_sessions": "Full sessions (transcripts)",
        "tile_total_messages": "Total messages",
        "tile_active_days": "Active days",
        "tile_current_streak": "Current streak",
        "tile_longest_streak": "Longest streak",
        "tile_cache_read": "Cache-read tokens",
        "tile_cache_create": "Cache-create tokens",
        "tile_api_equivalent": "API-equivalent (pay-per-use)",
        "tile_favorite_model": "Favorite model",
        # --- Overview tiles ---
        "tile_sessions": "Sessions",
        "tile_total_tokens": "Total tokens",
        "tile_git_commits": "Git commits",
        "tile_interactive_time": "Interactive time",
        "tile_used_task_agent": "Used Task agent",
        "tile_used_mcp": "Used MCP",
        "tile_facet_coverage": "Facet coverage",
        "tile_median_think_time": "Median think time",
        # --- Charts / legends ---
        "chart_models_label": "Assistant messages by model",
        "chart_no_data": "No data",
        "chart_count": "Count",
        "chart_rated": "rated",
        # --- Score dimensions (D1-D9) ---
        "score_d1": "Delegation (Task agent usage)",
        "score_d2": "Root-cause debugging",
        "score_d3": "Prompt quality",
        "score_d4": "Context management",
        "score_d5": "Interrupt judgment",
        "score_d6": "Tool breadth",
        "score_d7": "Writing consistency",
        "score_d8": "Time-of-day management",
        "score_d9": "Token efficiency",
        "d9_how_it_works": (
            "Compares average tokens spent on good-outcome sessions versus "
            "other rated sessions. Heavy spending on sessions that didn't "
            "reach a good outcome suggests tokens are being burned without "
            "landing results. Cache hit ratio adjusts the score by ±1 to "
            "reflect prompt reuse."
        ),
        "d9_band_10": "Not-good sessions cost ≤0.9× of good ones — very efficient",
        "d9_band_8": "Not-good sessions cost 0.9–1.1× of good ones",
        "d9_band_6": "Not-good sessions cost 1.1–1.5× of good ones",
        "d9_band_4": "Not-good sessions cost 1.5–2.0× of good ones",
        "d9_band_2": "Not-good sessions cost >2.0× of good ones — tokens burning without results",
        "d9_insufficient": "Not enough rated good/not-good sessions to compare (need ≥5 of each).",
        "score_overall_low_data": "Not enough data for an overall score.",
        # --- Privacy / redaction ---
        "redacted_project": "Private project",
        # --- Footer ---
        "footer_repo": "repo",
        "footer_tagline": "rule-based + LLM-assisted · re-run the skill anytime",
        # --- Usage rubric (Task 12) ---
        "score_disclaimer": "These are independent characteristics, not a breakdown — scores do not sum.",
        "score_disclaimer_long": (
            "Each dimension is scored from the sessions that apply to it. A session can "
            "contribute to multiple dimensions, so the nine scores describe independent "
            "slices, not shares of a whole."
        ),
        "how_to_read_key_relate": "HOW SCORES RELATE",
        "how_to_read_val_relate": (
            "Each dimension scores a different aspect of sessions. A session can score "
            "high on Delegation but low on Time-of-day; they are independent "
            "characteristics, not shares of a total."
        ),
        "usage_char_header": "Usage characteristics",
        "usage_char_note_template": (
            "Across {n_sessions} sessions from {since} to {until}, local only."
        ),
        # --- Evidence card labels ---
        "evidence_summary": "Summary",
        "evidence_friction_detail": "Friction detail",
        "evidence_first_prompt": "First prompt",
        "evidence_friction_counts": "Friction counts",
        "evidence_tok_unit": "tok",
        "evidence_dur_unit": "m",
        # --- Weekday labels ---
        "wd_mon": "Mon",
        "wd_tue": "Tue",
        "wd_wed": "Wed",
        "wd_thu": "Thu",
        "wd_fri": "Fri",
        "wd_sat": "Sat",
        "wd_sun": "Sun",
        # --- Plain-language intro ---
        "plain_intro_header": "What this report is",
        "plain_intro_body": (
            "<p>This report reads your local Claude Code data and gives you "
            "an evidence-backed peer review of how you work with the AI agent. "
            "It is not a leaderboard, not a celebration, and not designed to make you feel good. "
            "Instead it tries to tell you, with numbers, what is working and what is leaking value.</p>"
            "<p>Think of it as four questions about your AI usage:</p>"
            "<ul><li><b>WHEN</b> do you get the most out of the AI? (time-of-day)</li>"
            "<li><b>HOW</b> do you direct it? (delegation, prompts, tools)</li>"
            "<li><b>WHAT</b> tends to go wrong? (context drift, debugging style, mid-flight corrections)</li>"
            "<li><b>AT WHAT COST</b>? (tokens spent vs. results shipped)</li></ul>"
            "<p>The peer review below tells the story; the dimensions further down show the receipts.</p>"
        ),
        "plain_zone_when": "WHEN you work",
        "plain_zone_how": "HOW you direct it",
        "plain_zone_what": "WHAT goes wrong",
        "plain_zone_cost": "AT WHAT COST",
        "plain_zone_when_desc": "Time-of-day patterns",
        "plain_zone_how_desc": "Delegation, prompts, tool breadth",
        "plain_zone_what_desc": "Debugging style, context drift, interrupt judgment",
        "plain_zone_cost_desc": "Token efficiency, writing consistency",
        "plain_zone_when_dims": "D8 Time-of-day management",
        "plain_zone_how_dims": "D1 Delegation · D3 Prompt quality · D6 Tool breadth",
        "plain_zone_what_dims": "D2 Root-cause debugging · D4 Context management · D5 Interrupt judgment",
        "plain_zone_cost_dims": "D9 Token efficiency · D7 Writing consistency",
        "section_relationships": "How the dimensions relate",
        "section_relationships_subtitle": "A map of the nine scores, grouped into four zones.",
        "relationships_flow_caption": (
            "<b>WHEN</b> and <b>HOW</b> are the input conditions; <b>WHAT</b> goes wrong is the "
            "output friction; <b>COST</b> is the price tag of the whole loop. Improving an "
            "upstream zone usually pulls downstream zones with it."
        ),
        # --- HR shipped section ---
        "hr_shipped_outcome_template": "Outcome: fully achieved across {n} sessions. Details withheld; {label}.",
        "hr_shipped_proj_sub_template": "{sessions} sessions · {hours}h",
        "hr_shipped_commits_label": "commits",
        "hr_shipped_sessions_label": "sessions",
        # --- Preliminary warning ---
        "preliminary_warning": "⚠ Preliminary report — fewer than 20 rated sessions. Scores directional.",
        # --- Identity letterhead ---
        "letterhead_contact": "Contact",
        # --- HR Shipped section ---
        "hr_shipped_h": "Shipped with Claude",
        "hr_shipped_subtitle": "Representative outcomes — fully achieved, essential-tier sessions, grouped by project.",
        "hr_shipped_method": (
            "Extracted from session facets where <code>outcome = fully_achieved</code> and "
            "<code>helpfulness ∈ (essential, very_helpful)</code>. One representative per project, "
            "ranked by total time invested."
        ),
        "hr_shipped_top_session_tok": "tok / top session",
        "hr_shipped_privacy_note_allowlist": (
            " Allowlisted public projects appear by name; everything else is shown as a generic category label."
        ),
        "hr_shipped_privacy_note_anonymised": (
            " All project names are anonymised; no public-projects allowlist was supplied. "
            "Pass <code>--public-projects</code> to show specific repos by name."
        ),
        # --- HR Artifacts section ---
        "hr_artifacts_h": "Public artifacts",
        "hr_artifacts_subtitle": "Links the user chose to surface.",
        "hr_artifacts_method": "Self-reported. Not auto-extracted.",
        # --- How to read (HR) ---
        "how_to_read_summary": "How to read this report (30-second primer)",
        "how_to_read_intro": (
            "This report is generated by <code>cc-user-autopsy</code>, a skill that reads "
            "a user's local Claude Code usage data. It combines deterministic rule-based "
            "scoring with an LLM-written peer review."
        ),
        "how_to_read_dt_session": "Session",
        "how_to_read_dd_session": (
            "One continuous Claude Code conversation, bounded by either a fresh start or "
            "a <code>/clear</code>. A typical heavy user has hundreds per quarter."
        ),
        "how_to_read_dt_subagent": "Task agent / Subagent",
        "how_to_read_dd_subagent": (
            "Claude Code lets you spawn isolated child agents to run a subtask in parallel. "
            "Heavy adoption signals fluency with agentic workflows."
        ),
        "how_to_read_dt_mcp": "MCP (Model Context Protocol)",
        "how_to_read_dd_mcp": (
            "A standard for connecting Claude to external tools (Playwright, Supabase, "
            "GitHub, etc). MCP adoption rate correlates with tool breadth."
        ),
        "how_to_read_dt_facet": "Facet",
        "how_to_read_dd_facet": (
            "LLM-classified outcome / friction labels per session, produced by the built-in "
            "<code>/insights</code> command. Coverage &lt; 100% is normal."
        ),
        "how_to_read_dt_interrupt": "Interrupt recovery rate",
        "how_to_read_dd_interrupt": (
            "Of sessions where the user interrupted Claude's action, what fraction still "
            "reached a \"good\" outcome. High = good judgment about when to stop Claude."
        ),
        # --- HR Profile card sub labels ---
        "hr_profile_scale_label": "Scale",
        "hr_profile_velocity_label": "Velocity",
        "hr_profile_parallel_label": "Parallel work",
        "hr_profile_tool_breadth_label": "Tool breadth",
        "hr_profile_self_audit_label": "Self-audit",
        "hr_profile_focus_label": "Focus",
        "hr_profile_sessions_unit": "sessions",
        "hr_profile_top_project_share": "{pct}% on top project",
        # --- v3: Benchmark caveat (BOTH audiences) ---
        "benchmark_caveat": (
            "Unbenchmarked individual data. The numbers below describe one user's "
            "local Claude Code traces; they cannot be compared to other users without a cohort."
        ),
        # --- v3: SELF zone-map reading guide (replaces visual zone-map) ---
        "self_reading_guide_h": "Reading guide",
        "self_reading_guide_body": (
            "The peer review below tells the story in four parts: when you work, "
            "how you direct the AI, where you get stuck, and what it costs. "
            "If you want to verify a claim, the scoring grid and evidence library further down "
            "trace each finding back to the data."
        ),
        # --- v3: "This week try this" block (SELF) ---
        "self_try_this_h": "This week, try this",
        "self_try_this_intro": (
            "Concrete behaviors derived from the peer review above. "
            "Three to five things you can run for the next 7 days."
        ),
        # --- v3: Case study block (BOTH) ---
        "case_study_h": "Strongest single session",
        "case_study_subtitle": (
            "One representative session, in detail. More signal than aggregate charts."
        ),
        "case_study_problem_label": "The problem",
        "case_study_built_label": "What was built",
        "case_study_claude_role_label": "Claude's role",
        "case_study_user_role_label": "User's role",
        "case_study_outcome_label": "Outcome",
        # --- v3: HR Why-interview block ---
        "hr_why_interview_h": "Why interview this person",
        "hr_why_interview_subtitle": (
            "Specific roles this trace argues for, with the concrete signal that supports each."
        ),
        # --- v3: HR Self-awareness caveat (collapsed dimensions) ---
        # V4: Codex round 2 said naming hidden weak dims is weasel-worded —
        # draws the reader's eye to weaknesses then spins. Now: just say a
        # larger private audit exists, do not enumerate the weak dimensions.
        "hr_self_awareness_caveat": (
            "Private audit covers additional self-improvement dimensions; "
            "this portfolio excerpt shows the four most hiring-relevant signals."
        ),
        # --- v3: Usage snapshot header (SELF, merged overview+activity) ---
        "self_snapshot_h": "Usage snapshot",
        "self_snapshot_subtitle": (
            "The numbers behind this report, before interpretation."
        ),
        # --- v3: Claim-indexed evidence headers (SELF) ---
        "claim_afternoon_h": "Claim 1 — Afternoon sessions degrade",
        "claim_afternoon_intro": "Sessions starting between 13:00–15:00 reach high friction more often. Examples:",
        "claim_delegation_h": "Claim 2 — Delegation is operational, not vocabulary",
        "claim_delegation_intro": "Long, multi-task sessions with Task agent show clean shipping. Examples:",
        "claim_meander_h": "Claim 3 — Long sessions meander, not hit limits",
        "claim_meander_intro": "Sessions over 100k tokens with zero commits. The tokens were not blocked by a ceiling. Examples:",
        "claim_interrupt_h": "Claim 4 — Interrupt is treated as redirect",
        "claim_interrupt_intro": "Sessions where you cut Claude off and steered, with the outcome that followed. Examples:",
        "claim_no_evidence": "No sessions in the current sample match this claim. Expected because samples cap at 24.",
        # --- v4: HR scoring section (4 hiring signals, not 9-dim) ---
        "hr_section_scoring_h": "Hiring signals",
        "hr_section_scoring_subtitle": (
            "Four dimensions most relevant to AI-native engineering hiring."
        ),
        "hr_section_scoring_method": (
            "Scored from this user's local Claude Code traces using explicit thresholds. "
            "Higher is better. The four shown here are selected from a larger private audit."
        ),
        # --- v3: HR Methodology disclosure note ---
        "hr_method_disclosure_h": "How this was generated",
        "hr_method_disclosure_body": (
            "Compiled by <code>cc-user-autopsy</code> from this user's local Claude Code "
            "session traces. Project names not on the public allowlist are anonymised. "
            "Session IDs are not exposed. Do not infer relative ranking against other users; "
            "no cohort baseline exists."
        ),
        # --- V5 ledger ---
        "ledger_exhibit_label": "EXHIBIT",
        "ledger_source_prefix": "Source:",
        "ledger_opening_kicker": "AI WORK LEDGER",
        "ledger_output_title": "Output ledger",
        "ledger_team_title": "Team ledger",
        "ledger_source_card_full": "full data",
        "ledger_source_card_partial": "partial data",
        "ledger_source_card_presence": "presence only",
        "ledger_not_detected": "not detected",
        "ledger_degraded_note": (
            "Overlap between sources is under 14 days; sources are shown "
            "separately instead of compared."
        ),
        "ledger_common_window_note_template": (
            "Cross-tool comparisons cover the common window {start} to "
            "{end} ({days} days)."
        ),
        "ledger_weekly_share_title": "Weekly active minutes by tool",
        "ledger_parallel_title": "Multi-tool parallel hours (weekday x hour)",
        "ledger_matrix_title": "Projects by tool",
        "ledger_h2h_title": "Claude vs Codex, common window",
        "ledger_h2h_sessions": "sessions",
        "ledger_h2h_active_days": "active days",
        "ledger_h2h_tokens": "total tokens",
        "ledger_h2h_median_dur": "median session length (min)",
        "ledger_output_commits": "git commits",
        "ledger_output_pushes": "git pushes",
        "ledger_output_sessions_with_commits": "sessions that shipped commits",
        "ledger_parse_errors_template": "{n} unparseable lines skipped",
        "ledger_unknown_parse_errors_template": (
            "{n} lines from unrecognized sources skipped"
        ),
        # --- Phase 2: leak ledger + blind spots ---
        "ledger_leaks_title": "Leak ledger",
        "ledger_leaks_kicker": "Where tokens and hours leak",
        "ledger_blindspot_label": "Blind spot",
        "blindspot_repeated_title": "Repeated-instruction tax",
        "blindspot_repeated_template": (
            "The same instruction was retyped {n} times across {weeks} "
            "weeks ({sources})"
        ),
        "blindspot_sunk_title": "Sunk-cost sessions",
        "blindspot_sunk_template": (
            "{n} failed sessions were later redone from scratch in under "
            "half the time"
        ),
        "blindspot_switch_title": "Switch tax",
        "blindspot_switch_template": (
            "Good-outcome rate is {multi}% in multi-tool windows vs "
            "{single}% single-tool"
        ),
        "blindspot_graveyard_title": "The graveyard",
        "blindspot_graveyard_template": (
            "{n} projects received substantive writes, no commit, then "
            "went quiet"
        ),
        "blindspot_askship_title": "Ask vs ship mismatch",
        "blindspot_askship_template": (
            "{cat} is {ask}% of asks but {ship}% of shipped sessions"
        ),
        "blindspot_interrupt_title": "Interrupt win rate",
        "blindspot_interrupt_template": (
            "Interrupted sessions succeed {i}% of the time vs {b}% baseline"
        ),
        "ledger_leak_weekly_cost_template": "≈ ${cost}/week",
        "ledger_leak_tokens_template": "{tokens} tokens/week (lower bound)",
        "ledger_leak_occurrences_template": "{n} occurrences in window",
        "ledger_leak_fix_label": "Fix",
        "leak_type_repeated_instructions": "Repeated instructions",
        "leak_type_sunk_cost": "Sunk-cost sessions",
        "leak_type_failed_session_burn": "Failed-session burn",
        "leak_fix_repeated_instructions": (
            "Move this instruction into CLAUDE.md or memory so every "
            "session inherits it."
        ),
        "leak_fix_repeated_instructions_cross": (
            "Put this instruction in each tool's shared config (CLAUDE.md "
            "for Claude Code, AGENTS.md or the equivalent for other tools) "
            "so every session inherits it."
        ),
        "leak_fix_sunk_cost": (
            "Set a bail-out rule: when a session stalls, restart with a "
            "tighter brief instead of pushing on."
        ),
        "leak_fix_failed_session_burn": (
            "Write the acceptance check into the first prompt so failure "
            "surfaces early, not after the burn."
        ),
        "ledger_graveyard_exhibit_title": "Graveyard: written, never shipped",
        "ledger_graveyard_untouched_template": "untouched for {days} days",
        "ledger_graveyard_writes_template": (
            "{writes} file edits in final session"
        ),
        "ledger_leaks_exhibit_title": "Top leaks by estimated weekly cost",
        "ledger_secondary_findings": "Secondary findings",
        "ledger_source_blind_spots": "blind-spot engine, scoring pool",
    },
    "zh_TW": {
        # --- Document chrome ---
        "report_title": "Claude Code 使用診斷",
        "html_lang": "zh-Hant",
        # --- Section headers ---
        "section_overview": "概覽",
        "section_overview_subtitle": "詮釋之前的原始數字。",
        "section_scoring": "九面向評分",
        "section_scoring_subtitle": "九個彼此獨立的觀察面向，各自有量表。",
        "section_scoring_method": (
            "分數依明確門檻值計算，技術細節見 <code>references/scoring-rubric.md</code>。"
            "高分或低分都不是評斷，是指標；對照解釋判斷門檻是否合理。"
        ),
        "section_scoring_overall_label": "整體",
        "section_peer_review": "同行回饋",
        "section_peer_review_subtitle": "AI 讀完你的資料後寫的回饋。",
        "section_peer_review_method": (
            "上面的分數是機械化的。這段是詮釋：用故事的方式說「你做得好的」、"
            "「可改進的」、「值得反思的」。每個論點都會引用你資料裡的數字或具體對話 ID。"
        ),
        "section_patterns": "深入模式",
        "section_patterns_subtitle": "彙總數字看不到的、形狀才透露的事。",
        "patterns_h_plen": "4.1 提問字數（Prompt 長度）× 結果",
        "patterns_h_friction": "4.2 摩擦類型（哪些事卡住）",
        "patterns_h_tools": "4.3 工具使用",
        "patterns_h_heatmap": "4.4 星期 × 小時 熱力圖",
        "patterns_h_helpfulness": "4.5 AI 自評有用程度",
        "patterns_helpfulness_method": (
            "資料來自 <code>facets/</code>：AI 自己對每段對話打的有用程度標籤。"
        ),
        "section_trends": "週趨勢",
        "trends_h_growth": "成長曲線：整體技能分數隨時間變化",
        "trends_growth_method": (
            "整體分數混合三件事：好結果率（佔 40%）、委派採用率（佔 30%）、"
            "反向摩擦率（佔 30%），按週計算。趨勢上升表示有進步，"
            "持平或下降表示停滯。"
        ),
        "trends_h_volume": "工作量與工具採用率",
        "trends_subtitle_template": "資料涵蓋 {n} 週。",
        "section_evidence": "對話舉證",
        "section_evidence_subtitle": "形塑上述每個數字的對話樣本。",
        "section_evidence_method": (
            "從七個分類最多取 24 段對話。展開任何一列可看當初評分與同行回饋所依據的原始脈絡。"
        ),
        "section_method": "方法說明",
        "method_h_sources": "資料來源",
        "method_src_session_meta": (
            "<code>~/.claude/usage-data/session-meta/*.json</code>：Claude Code 自動記錄的對話資訊。"
        ),
        "method_src_facets": (
            "<code>~/.claude/usage-data/facets/*.json</code>：由 <code>/insights</code> "
            "用 AI 分類產出；非必要但建議備齊，沒有的話無法做進階分析。"
        ),
        "method_src_transcripts": (
            "<code>~/.claude/projects/**/*.jsonl</code>：原始逐字稿，僅用於對話舉證抽樣。"
        ),
        "method_h_sampling": "抽樣策略",
        "method_h_caveats": "注意事項",
        # --- Hero block (self audience) ---
        "hero_self_title_line1": "一份診斷信",
        "hero_self_title_line2_pre": "寫給",
        "hero_self_title_line2_em": "你",
        "hero_self_title_line2_post": "的 AI 工作流",
        "hero_self_dek": (
            "這份報告自動讀取你本機的 Claude Code 使用紀錄，"
            "給你一份有實據、不打高空的同行回饋。九個面向分數、十多張圖、"
            "二十多段對話舉證。不三明治、不灌水。"
        ),
        "hero_self_intro_card": (
            "內建的 <code>/insights</code> 報告偏向稱讚，這份試圖說實話。"
            "下面每個分數都有可審視的門檻；同行回饋裡的每個論點都會引用你資料裡的數字。"
            "若某個面向資料不足，會明說。"
        ),
        # --- Hero block (HR audience) ---
        "hero_hr_title_line1": "Claude Code",
        "hero_hr_title_line2_em": "工作實況摘要",
        "hero_hr_dek": (
            "這份摘要由系統自動產出，從本機對話紀錄還原這位使用者實際"
            "如何用 Claude Code，並非自述。設計給審視 AI 原生工程候選人的招募主管使用。"
        ),
        # --- Letterhead ---
        "letterhead_sessions_analyzed": "段對話已分析",
        "letterhead_facet_coverage": "標籤覆蓋率",
        # --- Profile-card sub labels (HR view) ---
        "profile_sub_commits_per_hour": "次提交 / 每小時",
        "profile_sub_task_agent_adoption": "委派採用率",
        "profile_sub_mcp_sessions": "使用外部工具的對話",
        # --- TOC nav links (self audience) ---
        "toc_self_overview": "概覽",
        "toc_self_scores": "九面向評分",
        "toc_self_peer_review": "同行回饋",
        "toc_self_try_this": "這週試試看",
        "toc_self_case_study": "代表性對話",
        "toc_self_patterns": "深入模式",
        "toc_self_trends": "週趨勢",
        "toc_self_evidence": "對話舉證",
        "toc_self_method": "方法說明",
        # --- TOC nav links (HR audience) ---
        "toc_hr_shipped": "用 Claude 交付的成果",
        "toc_hr_overview": "原始數字",
        "toc_hr_scores": "招募訊號",
        "toc_hr_peer_review": "同行回饋",
        "toc_hr_case_study": "代表性對話",
        "toc_hr_trends": "成長曲線",
        "toc_hr_patterns": "深入模式",
        "toc_hr_evidence": "對話舉證",
        "toc_hr_method": "方法說明",
        # --- Chart series labels (JS) ---
        "series_session_count": "對話數",
        "series_good_rate_pct": "好結果率 %",
        "series_composite_score": "整體分數",
        "series_good_outcome_rate": "好結果率",
        "series_task_agent_adoption": "委派採用率",
        "series_sessions": "對話數",
        "series_with_task_agent": "有委派",
        "series_tokens_m": "字元量（百萬）",
        "series_commits": "提交數",
        "series_friction": "摩擦",
        "series_avg_prompt_length": "提問平均字數",
        # --- Activity panel tiles ---
        "tile_full_sessions": "完整對話（含逐字稿）",
        "tile_total_messages": "總訊息數",
        "tile_active_days": "活躍天數",
        "tile_current_streak": "當前連續天數",
        "tile_longest_streak": "最長連續天數",
        "tile_cache_read": "重複讀取字元量",
        "tile_cache_create": "新建快取字元量",
        "tile_api_equivalent": "若按 API 計價（估）",
        "tile_favorite_model": "最常用模型",
        # --- Overview tiles ---
        "tile_sessions": "對話數",
        "tile_total_tokens": "總字元量",
        "tile_git_commits": "程式碼提交",
        "tile_interactive_time": "互動時間",
        "tile_used_task_agent": "用過委派",
        "tile_used_mcp": "用過外部工具",
        "tile_facet_coverage": "標籤覆蓋率",
        "tile_median_think_time": "思考時間中位數",
        # --- Charts / legends ---
        "chart_models_label": "依模型分布的回應次數",
        "chart_no_data": "尚無資料",
        "chart_count": "次數",
        "chart_rated": "已評",
        # --- Score dimensions (D1-D9) ---
        "score_d1": "委派（請 AI 派子任務）",
        "score_d2": "根因除錯",
        "score_d3": "提問品質",
        "score_d4": "對話脈絡管理",
        "score_d5": "中斷與重新導向",
        "score_d6": "工具廣度",
        "score_d7": "寫作一致性",
        "score_d8": "時段管理",
        "score_d9": "字元量效率",
        "d9_how_it_works": (
            "比較有達成結果的對話與其他對話的平均字元量消耗。"
            "若沒達成的對話反而燒更多字元，代表時間和費用花在沒結果的對話上。"
            "重複使用相同脈絡的比例會再加減 1 分。"
        ),
        "d9_band_10": "沒達成的對話 ≤ 達成組的 0.9 倍字元量，非常有效率",
        "d9_band_8": "沒達成的對話為達成組的 0.9–1.1 倍字元量",
        "d9_band_6": "沒達成的對話為達成組的 1.1–1.5 倍字元量",
        "d9_band_4": "沒達成的對話為達成組的 1.5–2.0 倍字元量",
        "d9_band_2": "沒達成的對話超過達成組 2 倍字元量，字元在沒結果的地方燒掉",
        "d9_insufficient": "達成與未達成的對話樣本不足（各需至少 5 筆）。",
        "score_overall_low_data": "資料量不足，無法給整體分數。",
        # --- Privacy / redaction ---
        "redacted_project": "私人專案",
        # --- Footer ---
        "footer_repo": "原始碼",
        "footer_tagline": "規則為主、AI 輔助；隨時可重新執行此工具",
        # --- Usage rubric (Task 12) ---
        "score_disclaimer": "各面向是彼此獨立的特徵，不是拆分比例，分數不會相加。",
        "score_disclaimer_long": "每個面向都從適用的對話各自計分。",
        "how_to_read_key_relate": "分數彼此獨立",
        "how_to_read_val_relate": "每個面向看的是對話的不同切面。",
        "usage_char_header": "使用特徵",
        "usage_char_note_template": "取樣範圍：{since} 至 {until}，共 {n_sessions} 段對話，僅本機。",
        # --- Evidence card labels ---
        "evidence_summary": "摘要",
        "evidence_friction_detail": "摩擦細節",
        "evidence_first_prompt": "起始提問",
        "evidence_friction_counts": "摩擦計數",
        "evidence_tok_unit": "字元",
        "evidence_dur_unit": "分",
        # --- Weekday labels ---
        "wd_mon": "週一",
        "wd_tue": "週二",
        "wd_wed": "週三",
        "wd_thu": "週四",
        "wd_fri": "週五",
        "wd_sat": "週六",
        "wd_sun": "週日",
        # --- Plain-language intro ---
        "plain_intro_header": "這份報告是什麼",
        "plain_intro_body": (
            "<p>這份報告自動讀取你本機的 Claude Code 使用紀錄，"
            "用數字回答一個問題：你跟 AI 助手共事的方式，哪些在發揮價值、哪些在漏水。</p>"
            "<p>把它想成對你 AI 使用習慣的四個問題：</p>"
            "<ul><li><b>什麼時間</b>跟 AI 一起工作效果最好？（時段）</li>"
            "<li><b>怎麼指揮</b>它？（委派、提問、工具）</li>"
            "<li><b>哪裡容易卡住</b>？（脈絡漂移、除錯方式、中途修正）</li>"
            "<li><b>付出多少成本</b>換到結果？（字元量 vs 實際產出）</li></ul>"
            "<p>下方的「同行回饋」用故事說明這四件事如何串連；再下方的九個面向給你看背後的證據。</p>"
        ),
        "plain_zone_when": "什麼時間",
        "plain_zone_how": "怎麼指揮",
        "plain_zone_what": "哪裡卡住",
        "plain_zone_cost": "付出代價",
        "plain_zone_when_desc": "一天中哪些時段跟 AI 合作效果最好",
        "plain_zone_how_desc": "委派子任務、提問清晰度、工具廣度",
        "plain_zone_what_desc": "除錯方式、長對話的脈絡管理、被打斷後的恢復",
        "plain_zone_cost_desc": "字元量效率、寫作一致性",
        "plain_zone_when_dims": "D8 時段管理",
        "plain_zone_how_dims": "D1 委派 · D3 提問品質 · D6 工具廣度",
        "plain_zone_what_dims": "D2 根因除錯 · D4 對話脈絡管理 · D5 中斷判斷",
        "plain_zone_cost_dims": "D9 字元量效率 · D7 寫作一致性",
        "section_relationships": "九個面向怎麼串連",
        "section_relationships_subtitle": "九個分數分成四個故事區塊：什麼時間、怎麼指揮、哪裡卡住、付出多少代價。",
        "relationships_flow_caption": (
            "<b>什麼時間</b>跟<b>怎麼指揮</b>是輸入條件，"
            "<b>哪裡卡住</b>是過程中跑出來的摩擦，"
            "<b>付出代價</b>是整個迴圈的價格。"
            "改善上游區塊，通常會把下游區塊一起拉起來。"
        ),
        # --- HR shipped section ---
        "hr_shipped_outcome_template": "結果：在 {n} 段對話中完全達成。細節未揭露：{label}。",
        "hr_shipped_proj_sub_template": "{sessions} 段對話，共 {hours} 小時",
        "hr_shipped_commits_label": "次提交",
        "hr_shipped_sessions_label": "段對話",
        # --- Preliminary warning ---
        "preliminary_warning": "⚠ 初步報告：已評對話少於 20 筆，分數僅作參考方向。",
        # --- Identity letterhead ---
        "letterhead_contact": "聯絡",
        # --- HR Shipped section ---
        "hr_shipped_h": "用 Claude 交付的成果",
        "hr_shipped_subtitle": "代表性成果：完全達成、被評為「不可或缺」等級的對話，依專案分組。",
        "hr_shipped_method": (
            "從對話標籤中篩選 <code>outcome = fully_achieved</code> 且 "
            "<code>helpfulness</code> 屬於「不可或缺 / 很有用」的對話。每個專案取一段代表，"
            "依總投入時間排序。"
        ),
        "hr_shipped_top_session_tok": "字元（最高單段對話）",
        "hr_shipped_privacy_note_allowlist": (
            "公開白名單內的專案顯示原名，其餘以類別標籤代替。"
        ),
        "hr_shipped_privacy_note_anonymised": (
            "所有專案名稱已匿名化；未提供公開白名單。"
            "傳入 <code>--public-projects</code> 可指定哪些 repo 顯示原名。"
        ),
        # --- HR Artifacts section ---
        "hr_artifacts_h": "公開作品",
        "hr_artifacts_subtitle": "使用者選擇公開的連結。",
        "hr_artifacts_method": "由使用者主動指定，並非自動擷取。",
        # --- How to read (HR) ---
        "how_to_read_summary": "怎麼讀這份報告（30 秒入門）",
        "how_to_read_intro": (
            "這份報告由 <code>cc-user-autopsy</code> 工具自動產出，"
            "讀取使用者本機的 Claude Code 對話紀錄，"
            "結合機械式的規則評分與 AI 寫的同行回饋。"
        ),
        "how_to_read_dt_session": "對話 (Session)",
        "how_to_read_dd_session": (
            "一段連續的 Claude Code 對話，由開啟或 <code>/clear</code> 為界。"
            "重度使用者一季通常有幾百段。"
        ),
        "how_to_read_dt_subagent": "委派 / 子任務 (Task agent / Subagent)",
        "how_to_read_dd_subagent": (
            "Claude Code 可以派出獨立的子任務並行處理。"
            "高採用率代表熟悉「讓 AI 分身做事」的工作流。"
        ),
        "how_to_read_dt_mcp": "外部工具 (MCP, Model Context Protocol)",
        "how_to_read_dd_mcp": (
            "讓 Claude 連接外部工具的標準介面（Playwright、Supabase、GitHub 等）。"
            "MCP 採用率與工具廣度相關。"
        ),
        "how_to_read_dt_facet": "標籤 (Facet)",
        "how_to_read_dd_facet": (
            "由內建 <code>/insights</code> 工具用 AI 為每段對話打上的結果與摩擦標籤。"
            "覆蓋率小於 100% 是正常的。"
        ),
        "how_to_read_dt_interrupt": "中斷後恢復率",
        "how_to_read_dd_interrupt": (
            "在使用者中途打斷 Claude 動作的對話中，仍有多少比例最後達成好結果。"
            "高表示使用者對「何時該打斷」判斷得宜。"
        ),
        # --- HR Profile card sub labels ---
        "hr_profile_scale_label": "規模",
        "hr_profile_velocity_label": "速度",
        "hr_profile_parallel_label": "平行工作",
        "hr_profile_tool_breadth_label": "工具廣度",
        "hr_profile_self_audit_label": "自評",
        "hr_profile_focus_label": "焦點",
        "hr_profile_sessions_unit": "段對話",
        "hr_profile_top_project_share": "{pct}% 集中於主要專案",
        # --- v3: Benchmark caveat ---
        "benchmark_caveat": (
            "未經 benchmark 的個人資料。下方數字描述的是一位使用者的本機 Claude Code 紀錄，"
            "在沒有 cohort 比較組的情況下，不能用來推論相對於其他使用者的位置。"
        ),
        # --- v3: SELF zone-map reading guide ---
        "self_reading_guide_h": "閱讀指引",
        "self_reading_guide_body": (
            "下方的同行回饋會用四段故事串起：什麼時間工作、怎麼指揮 AI、哪裡卡住、付出多少代價。"
            "如果想驗證某個論點，再往下的九面向評分跟對話舉證會把每個發現追回原始資料。"
        ),
        # --- v3: "This week try this" block ---
        "self_try_this_h": "這週試試看",
        "self_try_this_intro": (
            "從同行回饋直接推導出來的具體行為。接下來 7 天可以實際跑的 3-5 件事。"
        ),
        # --- v3: Case study block ---
        "case_study_h": "最強單一對話",
        "case_study_subtitle": (
            "一段有代表性的對話，攤開細節。比彙總圖表更有訊號。"
        ),
        "case_study_problem_label": "問題",
        "case_study_built_label": "做出什麼",
        "case_study_claude_role_label": "Claude 的角色",
        "case_study_user_role_label": "使用者的角色",
        "case_study_outcome_label": "結果",
        # --- v3: HR Why-interview block ---
        "hr_why_interview_h": "適合面試這個人去做什麼",
        "hr_why_interview_subtitle": (
            "從這份報告可以論證的幾種角色，每條附上對應的具體訊號。"
        ),
        # --- v3: HR Self-awareness caveat ---
        # V4: 不再點名 5 個低分面向。
        "hr_self_awareness_caveat": (
            "完整的私人審視涵蓋更多自我改善面向；"
            "這份對外摘要只列出對招募 context 最相關的四個訊號。"
        ),
        # --- v3: Usage snapshot header (SELF) ---
        "self_snapshot_h": "用量快照",
        "self_snapshot_subtitle": "詮釋之前的原始數字。",
        # --- v3: Claim-indexed evidence headers (SELF) ---
        "claim_afternoon_h": "Claim 1：下午時段表現會掉",
        "claim_afternoon_intro": "13:00–15:00 之間開始的對話，摩擦事件較多。下列為樣本：",
        "claim_delegation_h": "Claim 2：委派是操作層面的習慣",
        "claim_delegation_intro": "長的多任務對話、有用 Task agent、收尾乾淨。下列為樣本：",
        "claim_meander_h": "Claim 3：長對話是漫遊不是撞牆",
        "claim_meander_intro": "超過 10 萬字元、零 commit 的對話。這些對話不是被技術限制堵住的。下列為樣本：",
        "claim_interrupt_h": "Claim 4：中斷被當成「重新導向」",
        "claim_interrupt_intro": "你中途切掉 Claude 並修正方向的對話，附上後續結果。下列為樣本：",
        "claim_no_evidence": "目前抽樣中沒有符合這項 claim 的對話。樣本上限 24，這是預期內的。",
        # --- v4: HR scoring section (4 hiring signals, not 9-dim) ---
        "hr_section_scoring_h": "招募訊號",
        "hr_section_scoring_subtitle": "四個對 AI 原生工程招募最相關的面向。",
        "hr_section_scoring_method": (
            "從這位使用者的本機 Claude Code 紀錄按明確門檻值計算。分數越高越好。"
            "下方四項是從完整私人審視中為招募 context 挑出來的。"
        ),
        # --- v3: HR Methodology disclosure note ---
        "hr_method_disclosure_h": "報告產生方式",
        "hr_method_disclosure_body": (
            "由 <code>cc-user-autopsy</code> 工具自動從本機 Claude Code 對話紀錄編譯。"
            "非白名單上的專案名稱已匿名化，對話 ID 不對外揭露。"
            "請勿據此推論相對於其他使用者的位置：沒有 cohort 比較組。"
        ),
        # --- V5 ledger ---
        "ledger_exhibit_label": "圖表",
        "ledger_source_prefix": "資料來源:",
        "ledger_opening_kicker": "AI 工作總帳",
        "ledger_output_title": "產出帳",
        "ledger_team_title": "團隊帳",
        "ledger_source_card_full": "完整資料",
        "ledger_source_card_partial": "部分資料",
        "ledger_source_card_presence": "僅偵測到活動",
        "ledger_not_detected": "未偵測到",
        "ledger_degraded_note": (
            "工具間資料重疊期不足 14 天, 改為分開呈現不做比較。"
        ),
        "ledger_common_window_note_template": (
            "跨工具比較僅涵蓋共同期間 {start} 至 {end}, 共 {days} 天。"
        ),
        "ledger_weekly_share_title": "各工具每週活躍分鐘數",
        "ledger_parallel_title": "多工具並行時段 (星期 x 小時)",
        "ledger_matrix_title": "專案 x 工具分佈",
        "ledger_h2h_title": "Claude 與 Codex 共同期間對照",
        "ledger_h2h_sessions": "場次",
        "ledger_h2h_active_days": "活躍天數",
        "ledger_h2h_tokens": "token 總量",
        "ledger_h2h_median_dur": "session 長度中位數 (分)",
        "ledger_output_commits": "git commit 數",
        "ledger_output_pushes": "git push 數",
        "ledger_output_sessions_with_commits": "有 commit 產出的 session 數",
        "ledger_parse_errors_template": "略過 {n} 行無法解析",
        "ledger_unknown_parse_errors_template": "另有 {n} 行來源無法辨識, 已略過",
        # --- Phase 2: leak ledger + blind spots ---
        "ledger_leaks_title": "漏水帳",
        "ledger_leaks_kicker": "token 與時間漏在哪",
        "ledger_blindspot_label": "盲點",
        "blindspot_repeated_title": "重複指令稅",
        "blindspot_repeated_template": (
            "同一條指令在 {weeks} 週內重打了 {n} 次（{sources}）"
        ),
        "blindspot_sunk_title": "沉沒成本 session",
        "blindspot_sunk_template": (
            "{n} 個失敗 session 後來重開新局，用不到一半時間就完成"
        ),
        "blindspot_switch_title": "切換稅",
        "blindspot_switch_template": (
            "多工具並行時的良好結果率 {multi}%，單工具時 {single}%"
        ),
        "blindspot_graveyard_title": "墳場",
        "blindspot_graveyard_template": (
            "{n} 個專案寫了大量內容、沒有 commit，之後就沒再動過"
        ),
        "blindspot_askship_title": "想做與做成的落差",
        "blindspot_askship_template": (
            "{cat} 佔提問 {ask}%，但只佔有產出 session 的 {ship}%"
        ),
        "blindspot_interrupt_title": "中斷勝率",
        "blindspot_interrupt_template": (
            "被中斷的 session 成功率 {i}%，未中斷基準 {b}%"
        ),
        "ledger_leak_weekly_cost_template": "每週約 ${cost}",
        "ledger_leak_tokens_template": "每週 {tokens} tokens（下限值）",
        "ledger_leak_occurrences_template": "期間內 {n} 次",
        "ledger_leak_fix_label": "修法",
        "leak_type_repeated_instructions": "重複指令",
        "leak_type_sunk_cost": "沉沒成本 session",
        "leak_type_failed_session_burn": "失敗 session 燒掉的量",
        "leak_fix_repeated_instructions": (
            "把這條指令搬進 CLAUDE.md 或 memory，讓每個 session 自動繼承。"
        ),
        "leak_fix_repeated_instructions_cross": (
            "把這條指令放進各工具的共用設定，Claude Code 用 CLAUDE.md，"
            "其他工具用 AGENTS.md 或對應檔案，讓每個 session 自動繼承。"
        ),
        "leak_fix_sunk_cost": (
            "訂一條停損規則：session 卡住就開新的，附上更明確的任務描述，"
            "不要硬撐。"
        ),
        "leak_fix_failed_session_burn": (
            "把驗收條件寫進第一句 prompt，讓失敗早點浮出來，"
            "而不是燒完才發現。"
        ),
        "ledger_graveyard_exhibit_title": "墳場：寫了，沒出貨",
        "ledger_graveyard_untouched_template": "已 {days} 天沒動",
        "ledger_graveyard_writes_template": "最後一個 session 改了 {writes} 次檔案",
        "ledger_leaks_exhibit_title": "每週估計成本最高的漏水",
        "ledger_secondary_findings": "次要發現",
        "ledger_source_blind_spots": "盲點引擎，計分池",
    },
}


def t(locale: str, key: str) -> str:
    """Return the localized string for `key` in `locale`.

    Raises KeyError on any miss — both for unknown locales and for keys
    not present in the chosen locale's dict. Silent fallback would let
    half-translated reports ship; we'd rather fail the build.
    """
    if locale not in STRINGS:
        raise KeyError(
            f"unknown locale {locale!r}; supported: {sorted(STRINGS)}"
        )
    if key not in STRINGS[locale]:
        raise KeyError(f"missing key {key!r} for locale {locale!r}")
    return STRINGS[locale][key]
