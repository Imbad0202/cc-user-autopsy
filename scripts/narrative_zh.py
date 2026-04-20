"""中文敘事模組，給 cc-user-autopsy 報告使用。

跟 narrative_en.py 是兩個平行的敘事模組，不是互為翻譯。每個 dimension
function 讀 aggregate.py 產出的 metrics dict，回傳該面向的 explanation
或 pattern 句子。

Parity 規則（由 tests/test_narrative_parity.py 強制）：
- 讀 metrics 只能用 metrics["<literal_key>"] 或 metrics.get("<literal_key>", ...)。
  禁用動態 key，禁用 **metrics unpacking。
- narrative_en.py 必須 export 同一組 public function。每對 function 必須
  引用同一組 metric keys。

風格規則（narrative-parity-brief.md）：
- 禁用建議語氣：不准「建議」「應該」「可以考慮」「嘗試」「不妨」。
- 禁用價值判斷：不准「好習慣」「壞習慣」「最佳實踐」。
- 禁用 em-dash（repo enforced test_zh_tw_strings_have_no_em_dash）。
- 沿用 locales.py 既有 zh_TW 術語：Task Agent、session、prompt、Token、rated。
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# 面向 explanation（永遠 emit）
# ---------------------------------------------------------------------------

def d1_explanation(metrics: dict) -> str:
    ta_rate = metrics["metric_ta_rate_pct"]
    good_rate = metrics["metric_good_rate_with_ta_pct"]
    return (
        f"{ta_rate:.0f}% 的 session 用了 Task Agent；用 Task Agent 的 "
        f"session 達成率 {good_rate:.0f}%。"
    )


def d2_explanation(metrics: dict) -> str:
    count = metrics["metric_iter_buggy_count"]
    pct = metrics["metric_iter_buggy_pct"]
    return (
        f"{count} 個 session（{pct:.0f}%）是反覆修改 + buggy_code，這是在症狀"
        f"層打補丁的徵兆。"
    )


def d3_explanation(metrics: dict) -> str:
    rate_100 = metrics["metric_pct_prompts_ge_100_chars"]
    best_bucket = metrics["metric_most_efficient_bucket"]
    return (
        f"{rate_100:.0f}% 的 session 用了 100 字以上的 prompt。"
        f"tokens/commit 最有效率的區間：{best_bucket}。"
    )


def d4_explanation(metrics: dict) -> str:
    otl = metrics["metric_output_token_limit_sessions"]
    enc = metrics["metric_effort_no_commit_pct"]
    enc_n = metrics.get("metric_effort_no_commit_sample")
    long_intr = metrics["metric_long_session_interrupt_rate_pct"]
    n_suffix = f"（n={enc_n}）" if enc_n else ""
    return (
        f"{otl} 個 session 撞到 output-token-limit。超過 20 分鐘的 session "
        f"裡有 {enc:.0f}% 是零 commit{n_suffix}。長 session 的中斷率：{long_intr:.0f}%。"
    )


def d5_explanation(metrics: dict) -> str:
    recovery = metrics["metric_interrupt_recovery_pct"]
    n_interrupted = metrics["metric_interrupted_sessions"]
    return (
        f"被中斷的 session 有 {recovery:.0f}% 仍然達成（樣本：{n_interrupted} "
        f"個被中斷的 session）。"
    )


def d6_explanation(metrics: dict) -> str:
    mcp = metrics["metric_mcp_rate_pct"]
    top3 = metrics["metric_top3_share_pct"]
    return (
        f"{mcp:.0f}% 的 session 用了任一 MCP 工具；Bash/Read/Edit 前三名"
        f"吃掉 {top3:.0f}% 的工具呼叫。"
    )


def d7_explanation(metrics: dict) -> str:
    n = metrics["metric_writing_sessions"]
    avg = metrics["metric_misunderstood_per_writing_session"]
    return (
        f"{n} 個寫作類 session 裡，平均每個 session 出現 {avg:.2f} 次"
        f"misunderstood_request。"
    )


def d8_explanation(metrics: dict) -> str:
    worst = metrics["metric_worst_hour"]
    best = metrics["metric_best_hour"]
    ratio = metrics["metric_friction_ratio_hi_lo"]
    return (
        f"最差時段（{worst['hour']:02d}:00）的摩擦率是最佳時段"
        f"（{best['hour']:02d}:00）的 {ratio:.1f} 倍。"
    )


def d9_explanation(metrics: dict) -> str:
    good = metrics["metric_tokens_per_good"]
    not_good = metrics["metric_tokens_per_not_good"]
    ratio = metrics["metric_ratio"]
    cache = metrics.get("metric_cache_hit_pct")
    cache_frag = f" Cache 命中率 {cache:.0f}%。" if cache is not None else ""
    return (
        f"未達成的 session 平均 {not_good:,.0f} Token，達成組平均 "
        f"{good:,.0f}（{ratio:.2f} 倍）。{cache_frag}"
    )


# ---------------------------------------------------------------------------
# 面向 pattern（metrics["pattern_emit"] 為 True 才 emit）
# ---------------------------------------------------------------------------

def d1_pattern(metrics: dict) -> str:
    ta_rate = metrics["metric_ta_rate_pct"]
    good_rate = metrics["metric_good_rate_with_ta_pct"]
    return (
        f"用 Task Agent 的 session 達成率 {good_rate:.0f}%；"
        f"Task Agent 在所有 session 的採用率 {ta_rate:.0f}%。"
    )


def d2_pattern(metrics: dict) -> str:
    count = metrics["metric_iter_buggy_count"]
    pct = metrics["metric_iter_buggy_pct"]
    return (
        f"{count} 個 session（{pct:.0f}%）把反覆修改跟 buggy_code 綁在一起。"
        f"改做根因除錯能壓低這個比例。"
    )


def d3_pattern(metrics: dict) -> str:
    rate_100 = metrics["metric_pct_prompts_ge_100_chars"]
    best_bucket = metrics["metric_most_efficient_bucket"]
    return (
        f"長 prompt 佔 {rate_100:.0f}% 的 session；"
        f"{best_bucket} 區間的 tokens/commit 最低。"
    )


def d4_pattern(metrics: dict) -> str:
    otl = metrics["metric_output_token_limit_sessions"]
    enc = metrics["metric_effort_no_commit_pct"]
    return (
        f"{otl} 個 session 撞到 output-token-limit；長 session 裡有 "
        f"{enc:.0f}% 零 commit，力氣花了沒交出結果。"
    )


def d5_pattern(metrics: dict) -> str:
    recovery = metrics["metric_interrupt_recovery_pct"]
    n = metrics["metric_interrupted_sessions"]
    return (
        f"{n} 個被中斷的 session 中有 {recovery:.0f}% 仍然達成，"
        f"顯示中斷多半是修正方向而不是脫軌。"
    )


def d6_pattern(metrics: dict) -> str:
    mcp = metrics["metric_mcp_rate_pct"]
    top3 = metrics["metric_top3_share_pct"]
    return (
        f"MCP 工具出現在 {mcp:.0f}% 的 session；"
        f"Bash/Read/Edit 吃掉 {top3:.0f}% 的工具呼叫。"
    )


def d7_pattern(metrics: dict) -> str:
    n = metrics["metric_writing_sessions"]
    avg = metrics["metric_misunderstood_per_writing_session"]
    return (
        f"{n} 個寫作 session 的平均 misunderstood_request 是 {avg:.2f} 次。"
    )


def d8_pattern(metrics: dict) -> str:
    worst = metrics["metric_worst_hour"]
    best = metrics["metric_best_hour"]
    ratio = metrics["metric_friction_ratio_hi_lo"]
    return (
        f"{worst['hour']:02d}:00 的摩擦率是 {best['hour']:02d}:00 的 "
        f"{ratio:.1f} 倍。"
    )


def d9_pattern(metrics: dict) -> str:
    good = metrics["metric_tokens_per_good"]
    not_good = metrics["metric_tokens_per_not_good"]
    ratio = metrics["metric_ratio"]
    return (
        f"達成組平均 {good:,.0f} Token；未達成組平均 {not_good:,.0f}"
        f"（{ratio:.2f} 倍）。"
    )


# ---------------------------------------------------------------------------
# 單一值對照
# ---------------------------------------------------------------------------

_OUTCOME_LABELS = {
    "fully_achieved": "完全達成",
    "mostly_achieved": "大致達成",
    "partially_achieved": "部分達成",
    "not_achieved": "未達成",
    "unclear_from_transcript": "逐字稿難判斷",
}

_EVIDENCE_BADGES = {
    "high_friction": "摩擦最高",
    "top_token": "Token 用量最多",
    "top_interrupt": "中斷次數最多",
    "not_achieved": "未達成",
    "partial": "部分達成",
    "control_good": "對照組",
    "user_rejected": "你否決動作",
    "long_duration": "持續最久",
}


def outcome_label(outcome: str) -> str:
    """回傳 outcome 的顯示標籤，未知值原樣回傳。"""
    return _OUTCOME_LABELS.get(outcome, outcome)


def evidence_badge(tag: str) -> str:
    """回傳 evidence tag 的顯示標籤，未知值原樣回傳。"""
    return _EVIDENCE_BADGES.get(tag, tag)


def no_facet_label() -> str:
    return "（無 facet）"


# ---------------------------------------------------------------------------
# 方法論段落（靜態文案）
# ---------------------------------------------------------------------------

def methodology_subtitle() -> str:
    return "報告限制。"


def methodology_sampling_body() -> str:
    return (
        "最多抽 24 個 session 進證據庫，分七類：摩擦最高 5 筆、Token 用量"
        "最多 5 筆、中斷次數最多 5 筆、未達成 4 筆、部分達成 3 筆、對照組"
        "（完全達成＋關鍵任務）4 筆、你否決 Claude 動作 2 筆。"
        "沒有 facet 資料時改看 session 長度。"
    )


def methodology_caveats_body() -> str:
    return (
        "Facet 標籤是 LLM 分類出來的，會有誤判。"
        "Facet 覆蓋率要超過 50%，outcome 相關規則才站得住；"
        "低於 30% 時部分面向會顯示 n/a。"
        "評分門檻是經驗值，不是科學公式。"
        "同行檢視要有足夠資料才做得出具體判斷；"
        "資料量薄的時候，回饋要精簡，不是硬湊滿版。"
    )
