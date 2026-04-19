"""Single source of truth for every UI chrome string in cc-user-autopsy
reports. Two locales: en (canonical) and zh_TW.

Hard rules (enforced by tests/test_locales.py):
  - Both locales must share the exact same key set.
  - t(locale, key) raises KeyError on any miss — silent fallback to en
    would defeat the whole "no mixed-language reports" intent.
  - zh_TW values must not contain the AI em-dash (per
    feedback_writing_style.md). Use comma + clause continuation instead.

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
        "section_evidence": "Evidence",
        "section_evidence_subtitle": "The sessions that shaped every number above.",
        "section_method": "Method",
        "section_method_subtitle": "What this report is — and what it is not.",
        "section_growth": "Growth curve",
        "section_growth_subtitle": "What the aggregate hides; what the shape reveals.",
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
        "section_evidence": "證據",
        "section_evidence_subtitle": "形塑上述每個數字的 session。",
        "section_method": "方法",
        "section_method_subtitle": "這份報告是什麼，又不是什麼。",
        "section_growth": "成長曲線",
        "section_growth_subtitle": "彙總數字看不到的、形狀透露的事。",
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
