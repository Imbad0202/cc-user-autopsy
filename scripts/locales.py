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
        "section_scoring_subtitle": "Eight dimensions, each with its own rubric.",
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
        "section_evidence": "Evidence library",
        "section_evidence_subtitle": "The sessions that shaped every number above.",
        "section_evidence_method": (
            "Up to 24 sessions sampled across seven buckets. Expand any row to see the "
            "raw context the scoring and peer review were built from."
        ),
        "section_method": "Methodology",
        "section_method_subtitle": "What this report is, and what it is not.",
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
        "method_sampling_body": (
            "Up to 24 sessions across 7 buckets: 5 highest-friction, 5 top-tokens, 5 "
            "most-interrupts, 4 not_achieved, 3 partially_achieved, 4 control "
            "(fully_achieved + essential), 2 user_rejected. When facets are absent, "
            "fallback is by session duration."
        ),
        "method_h_caveats": "Caveats",
        "method_caveats_body": (
            "Facet labels come from an LLM and may be miscategorized. Above roughly 50% "
            "facet coverage, outcome-based rules are reliable; below 30%, some "
            "dimensions return n/a. Scoring thresholds are rules of thumb, not science. "
            "The peer review depends on there being enough data to say specific things; "
            "if your data is thin, the review should be short, not padded."
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
        "toc_self_peer_review": "Personalized peer review",
        "toc_self_patterns": "Pattern mining",
        "toc_self_trends": "Weekly trends",
        "toc_self_evidence": "Evidence library",
        "toc_self_method": "Methodology",
        # --- TOC nav links (HR audience) ---
        "toc_hr_shipped": "Shipped with Claude",
        "toc_hr_overview": "Raw numbers",
        "toc_hr_scores": "8-dim self-audit",
        "toc_hr_peer_review": "Peer review",
        "toc_hr_trends": "Growth curve &amp; trends",
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
        # --- Score dimensions (D1-D8) ---
        "score_d1": "Delegation (Task agent usage)",
        "score_d2": "Root-cause debugging",
        "score_d3": "Prompt quality",
        "score_d4": "Context management",
        "score_d5": "Interrupt judgment",
        "score_d6": "Tool breadth",
        "score_d7": "Writing consistency",
        "score_d8": "Time-of-day management",
        "score_overall_low_data": "Not enough data for an overall score.",
        # --- Evidence categories ---
        "ev_high_friction": "Highest friction",
        "ev_top_token": "Highest token count",
        "ev_top_interrupt": "Most interrupts",
        "ev_not_achieved": "Not achieved",
        "ev_partial": "Partially achieved",
        "ev_control_good": "Control · fully achieved + essential",
        "ev_user_rejected": "You rejected Claude's action",
        "ev_long_duration": "Longest duration · fallback",
        # --- Privacy / redaction ---
        "redacted_project": "Private project",
        # --- Footer ---
        "footer_repo": "repo",
        "footer_tagline": "rule-based + LLM-assisted · re-run the skill anytime",
    },
    "zh_TW": {
        # --- Document chrome ---
        "report_title": "Claude Code 使用診斷",
        "html_lang": "zh-Hant",
        # --- Section headers ---
        "section_overview": "概覽",
        "section_overview_subtitle": "詮釋之前的原始數字。",
        "section_scoring": "評分",
        "section_scoring_subtitle": "八個面向，各自有獨立量表。",
        "section_scoring_method": (
            "分數來自明確的門檻值（見 <code>references/scoring-rubric.md</code>）。"
            "高分或低分都不是評斷，是指標：對照解釋來判斷門檻是否合理。"
        ),
        "section_scoring_overall_label": "整體",
        "section_peer_review": "同行檢視",
        "section_peer_review_subtitle": "Claude 讀完你的資料後寫的回饋。",
        "section_peer_review_method": (
            "上面的分數是機械化的。這一段是詮釋：找出三件你做得好的、三件可改進的，"
            "外加一個中立觀察。每個論點都應引用你資料裡的數字或具體 session ID。"
        ),
        "section_patterns": "模式挖掘",
        "section_patterns_subtitle": "彙總數字看不到的、形狀透露的事。",
        "patterns_h_plen": "4.1 Prompt 長度 × 結果",
        "patterns_h_friction": "4.2 摩擦類型",
        "patterns_h_tools": "4.3 工具使用",
        "patterns_h_heatmap": "4.4 星期 × 小時熱力圖",
        "patterns_h_helpfulness": "4.5 Helpfulness 自評",
        "patterns_helpfulness_method": (
            "資料來自 <code>facets/</code>：Claude 自評每個 session 的有用程度。"
        ),
        "section_trends": "週趨勢",
        "trends_h_growth": "成長曲線，整體技能分數隨時間變化",
        "trends_growth_method": (
            "整體分數混合好結果率（0.4）、Task Agent 採用率（0.3）、"
            "反向摩擦率（0.3），按週計算。趨勢上升表示有進步，"
            "持平或下降表示停滯。"
        ),
        "trends_h_volume": "用量與採用率",
        "section_evidence": "證據庫",
        "section_evidence_subtitle": "形塑上述每個數字的 session。",
        "section_evidence_method": (
            "從七個分桶最多取 24 個 session。展開任何一列可看當初評分與同行檢視所依據的原始脈絡。"
        ),
        "section_method": "方法論",
        "section_method_subtitle": "這份報告是什麼，又不是什麼。",
        "method_h_sources": "資料來源",
        "method_src_session_meta": (
            "<code>~/.claude/usage-data/session-meta/*.json</code>：Claude Code 自動記錄。"
        ),
        "method_src_facets": (
            "<code>~/.claude/usage-data/facets/*.json</code>：由 <code>/insights</code> "
            "用 LLM 分類；非必要但建議備齊。"
        ),
        "method_src_transcripts": (
            "<code>~/.claude/projects/**/*.jsonl</code>：原始逐字稿，僅用於證據庫抽樣。"
        ),
        "method_h_sampling": "抽樣策略",
        "method_sampling_body": (
            "從七個分桶最多取 24 個 session：摩擦最高 5 筆、Token 用量最多 5 筆、"
            "中斷次數最多 5 筆、未達成 4 筆、部分達成 3 筆、對照組（完全達成+關鍵）4 筆、"
            "你否決動作 2 筆。若無 facet 資料，改以 session 持續時間為後備抽樣依據。"
        ),
        "method_h_caveats": "注意事項",
        "method_caveats_body": (
            "Facet 標籤由 LLM 產出，可能誤分類。Facet 覆蓋率約 50% 以上，"
            "outcome 規則才可靠；30% 以下，某些面向會回 n/a。"
            "評分門檻只是經驗法則，不是科學。"
            "同行檢視倚賴足夠資料才有具體結論；資料量薄時，回饋應該短，而不是被填滿。"
        ),
        # --- Letterhead ---
        "letterhead_sessions_analyzed": "個 session 已分析",
        "letterhead_facet_coverage": "Facet 覆蓋率",
        # --- Profile-card sub labels (HR view) ---
        "profile_sub_commits_per_hour": "次提交 / 互動小時",
        "profile_sub_task_agent_adoption": "Task Agent 採用率",
        "profile_sub_mcp_sessions": "使用 MCP 的 session",
        # --- TOC nav links (self audience) ---
        "toc_self_overview": "概覽",
        "toc_self_scores": "規則式評分",
        "toc_self_peer_review": "個人化同行檢視",
        "toc_self_patterns": "模式挖掘",
        "toc_self_trends": "週趨勢",
        "toc_self_evidence": "證據庫",
        "toc_self_method": "方法論",
        # --- TOC nav links (HR audience) ---
        "toc_hr_shipped": "用 Claude 交付的成果",
        "toc_hr_overview": "原始數字",
        "toc_hr_scores": "八面向自我審視",
        "toc_hr_peer_review": "同行檢視",
        "toc_hr_trends": "成長曲線與趨勢",
        "toc_hr_patterns": "模式挖掘",
        "toc_hr_evidence": "證據庫",
        "toc_hr_method": "方法論",
        # --- Chart series labels (JS) ---
        "series_session_count": "Session 數",
        "series_good_rate_pct": "好結果率 %",
        "series_composite_score": "整體分數",
        "series_good_outcome_rate": "好結果率",
        "series_task_agent_adoption": "Task Agent 採用率",
        "series_sessions": "Session 數",
        "series_with_task_agent": "含 Task Agent",
        "series_tokens_m": "Token（百萬）",
        "series_commits": "提交數",
        "series_friction": "摩擦",
        "series_avg_prompt_length": "Prompt 平均長度",
        # --- Activity panel tiles ---
        "tile_full_sessions": "完整 session（含逐字稿）",
        "tile_total_messages": "總訊息數",
        "tile_active_days": "活躍天數",
        "tile_current_streak": "當前連續天數",
        "tile_longest_streak": "最長連續天數",
        "tile_cache_read": "快取讀取 Token",
        "tile_cache_create": "快取建立 Token",
        "tile_api_equivalent": "API 計價估值（按用量）",
        "tile_favorite_model": "最常用模型",
        # --- Overview tiles ---
        "tile_sessions": "Session 數",
        "tile_total_tokens": "總 Token 數",
        "tile_git_commits": "Git 提交",
        "tile_interactive_time": "互動時間",
        "tile_used_task_agent": "使用 Task Agent",
        "tile_used_mcp": "使用 MCP",
        "tile_facet_coverage": "面向覆蓋率",
        "tile_median_think_time": "思考時間中位數",
        # --- Charts / legends ---
        "chart_models_label": "依模型的助理訊息分布",
        "chart_no_data": "尚無資料",
        "chart_count": "次數",
        "chart_rated": "已評",
        # --- Score dimensions (D1-D8) ---
        "score_d1": "委派（Task Agent 使用）",
        "score_d2": "根因除錯",
        "score_d3": "Prompt 品質",
        "score_d4": "脈絡管理",
        "score_d5": "中斷判斷",
        "score_d6": "工具廣度",
        "score_d7": "寫作一致性",
        "score_d8": "時段管理",
        "score_overall_low_data": "資料量不足，無法給整體分數。",
        # --- Evidence categories ---
        "ev_high_friction": "摩擦最高",
        "ev_top_token": "Token 用量最多",
        "ev_top_interrupt": "中斷次數最多",
        "ev_not_achieved": "未達成",
        "ev_partial": "部分達成",
        "ev_control_good": "對照組：完全達成且關鍵",
        "ev_user_rejected": "你否決了 Claude 的動作",
        "ev_long_duration": "持續最久（後備樣本）",
        # --- Privacy / redaction ---
        "redacted_project": "私人專案",
        # --- Footer ---
        "footer_repo": "原始碼",
        "footer_tagline": "規則為主、LLM 輔助；隨時可重新執行此 skill",
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
