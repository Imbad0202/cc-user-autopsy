# i18n explanations + narrative module separation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split locale-specific evidence prose out of `scripts/aggregate.py` and `scripts/locales.py` into two independent narrative modules (`narrative_en.py`, `narrative_zh.py`) that share the same `metrics` dict contract but are authored independently, with an AST parity test guaranteeing both locales cite the same metric keys.

**Architecture:** `aggregate.py` becomes pure data (returns metric dicts + `pattern_emit` bool, retains deprecated `explanation`/`pattern` JSON fields for 2 releases). New `scripts/report_render.py` owns HTML/CSS/chart chrome. New `scripts/narrative_en.py` + `scripts/narrative_zh.py` each export 24 public functions (18 per-dim + outcome/badge lookups + methodology). `scripts/build_html.py` shrinks to a thin orchestrator that picks a narrative by `--locale` and hands its output to the render layer.

**Tech Stack:** Python 3, pytest, Node test runner (chart tests must stay green). Branch `feat/i18n-explanations`, stacked on `fix/zh-tw-locale` (PR #16), itself stacked on `feat/d9-token-efficiency` (PR #15).

**Spec:** `docs/superpowers/specs/2026-04-20-i18n-explanations-design.md`
**Parity brief:** `docs/superpowers/specs/narrative-parity-brief.md`
**Schema changes log:** `docs/SCHEMA-CHANGES.md`

**Metric-key inventory (from `scripts/aggregate.py`) — narrative functions must cite these:**

| Dim | Function | Metric keys |
|---|---|---|
| D1 | `score_d1_delegation` | `metric_ta_rate_pct`, `metric_good_rate_with_ta_pct` |
| D2 | `score_d2_rootcause` | `metric_iter_buggy_pct`, `metric_iter_buggy_count` |
| D3 | `score_d3_prompt_quality` | `metric_pct_prompts_ge_100_chars`, `metric_most_efficient_bucket`, `metric_bucket_median_tokens_per_commit` |
| D4 | `score_d4_context_mgmt` | `metric_output_token_limit_sessions`, `metric_effort_no_commit_pct`, `metric_long_session_interrupt_rate_pct` |
| D5 | `score_d5_interrupt` | `metric_interrupt_recovery_pct`, `metric_interrupted_sessions` |
| D6 | `score_d6_tool_breadth` | `metric_mcp_rate_pct`, `metric_top3_share_pct` |
| D7 | `score_d7_writing` | `metric_misunderstood_per_writing_session`, `metric_writing_sessions` |
| D8 | `score_d8_time_mgmt` | `metric_worst_hour`, `metric_best_hour`, `metric_friction_ratio_hi_lo` |
| D9 | `score_d9_token_efficiency` | `metric_tokens_per_good`, `metric_tokens_per_not_good`, `metric_ratio`, `metric_cache_hit_pct` |

---

## Task 1: Set up parity test scaffolding (expect red)

**Files:**
- Create: `tests/test_narrative_parity.py`

TDD seed. The test references narrative modules that do not exist yet, so it must fail initially with `FileNotFoundError` or `ModuleNotFoundError`. Task 2 makes it pass by creating stub modules.

- [ ] **Step 1: Write the parity test file**

Create `/Users/imbad/Projects/cc-user-autopsy/tests/test_narrative_parity.py`:

```python
"""AST-based parity test for narrative_en.py and narrative_zh.py.

Ensures both locale narrative modules expose the same public function set
and that each dimension function cites the same set of metric keys via
metrics["<key>"] or metrics.get("<key>", ...). See
docs/superpowers/specs/2026-04-20-i18n-explanations-design.md Section 4.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

NARRATIVE_ROOT = Path(__file__).parent.parent / "scripts"
EN_PATH = NARRATIVE_ROOT / "narrative_en.py"
ZH_PATH = NARRATIVE_ROOT / "narrative_zh.py"

DIM_FUNCTION_NAMES = [
    f"d{d}_{kind}" for d in range(1, 10) for kind in ("explanation", "pattern")
]  # 18 functions total


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found in module")


def _extract_metrics_keys(func: ast.FunctionDef) -> set[str]:
    keys: set[str] = set()
    for sub in ast.walk(func):
        # metrics["foo"] subscript
        if (
            isinstance(sub, ast.Subscript)
            and isinstance(sub.value, ast.Name)
            and sub.value.id == "metrics"
            and isinstance(sub.slice, ast.Constant)
            and isinstance(sub.slice.value, str)
        ):
            keys.add(sub.slice.value)
        # metrics.get("foo", ...)
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "get"
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "metrics"
            and sub.args
            and isinstance(sub.args[0], ast.Constant)
            and isinstance(sub.args[0].value, str)
        ):
            keys.add(sub.args[0].value)
    return keys


def _public_function_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }


@pytest.fixture(scope="module")
def en_tree() -> ast.Module:
    return _parse(EN_PATH)


@pytest.fixture(scope="module")
def zh_tree() -> ast.Module:
    return _parse(ZH_PATH)


def test_public_function_set_is_identical(en_tree, zh_tree):
    en = _public_function_names(en_tree)
    zh = _public_function_names(zh_tree)
    assert en == zh, (
        f"Public function set differs.\n"
        f"  en-only: {en - zh}\n"
        f"  zh-only: {zh - en}"
    )


@pytest.mark.parametrize("func_name", DIM_FUNCTION_NAMES)
def test_metric_key_parity(func_name, en_tree, zh_tree):
    en_keys = _extract_metrics_keys(_function_node(en_tree, func_name))
    zh_keys = _extract_metrics_keys(_function_node(zh_tree, func_name))
    assert en_keys == zh_keys, (
        f"{func_name}: metric keys diverge.\n"
        f"  en-only: {en_keys - zh_keys}\n"
        f"  zh-only: {zh_keys - en_keys}"
    )


def test_no_dynamic_metrics_access_in_en(en_tree):
    _assert_no_dynamic_metrics(en_tree, EN_PATH.name)


def test_no_dynamic_metrics_access_in_zh(zh_tree):
    _assert_no_dynamic_metrics(zh_tree, ZH_PATH.name)


def _assert_no_dynamic_metrics(tree: ast.Module, filename: str) -> None:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "metrics"
            and not (isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str))
        ):
            raise AssertionError(
                f"{filename}: dynamic metrics[...] access at line {node.lineno}. "
                "Narrative functions must use string-literal keys so parity scan stays valid."
            )
```

- [ ] **Step 2: Run the test — expect failure**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest tests/test_narrative_parity.py -v 2>&1 | tail -20
```

Expected: fail at fixture setup (`FileNotFoundError` on `narrative_en.py`).

- [ ] **Step 3: Commit**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
git add tests/test_narrative_parity.py
git commit -m "test(narrative): add parity test scaffolding (red)

AST-based check that narrative_en and narrative_zh expose the same
function set and cite the same metric keys per dimension function.
Fails until Task 2 creates the stub modules."
```

---

## Task 2: Create narrative module stubs (make parity test green)

**Files:**
- Create: `scripts/narrative_en.py`
- Create: `scripts/narrative_zh.py`

Both modules export all 24 required functions as stubs returning placeholder strings. Each `dX_explanation` / `dX_pattern` function must access the same metric keys listed in the inventory above so the parity test passes immediately.

- [ ] **Step 1: Write narrative_en.py stub**

Create `/Users/imbad/Projects/cc-user-autopsy/scripts/narrative_en.py`:

```python
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
    long_intr = metrics["metric_long_session_interrupt_rate_pct"]
    return (
        f"{otl} sessions hit output-token-limit. {enc:.0f}% of sessions over "
        f"20 minutes had zero commits. Long-session interrupt rate: "
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
```

- [ ] **Step 2: Write narrative_zh.py stub**

Create `/Users/imbad/Projects/cc-user-autopsy/scripts/narrative_zh.py`:

```python
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
    long_intr = metrics["metric_long_session_interrupt_rate_pct"]
    return (
        f"{otl} 個 session 撞到 output-token-limit。超過 20 分鐘的 session "
        f"裡有 {enc:.0f}% 是零 commit。長 session 的中斷率：{long_intr:.0f}%。"
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
```

- [ ] **Step 3: Run the parity test — expect pass**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest tests/test_narrative_parity.py -v 2>&1 | tail -25
```

Expected: all 21 tests pass (`test_public_function_set_is_identical`, 18 × `test_metric_key_parity`, 2 × `test_no_dynamic_metrics_access`).

- [ ] **Step 4: Confirm the rest of the suite is still green**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest 2>&1 | tail -10
```

Expected: 149 passed, 0 skipped (the existing count post PR #16); 21 extra parity tests added → 170 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
git add scripts/narrative_en.py scripts/narrative_zh.py
git commit -m "feat(narrative): add narrative_en.py + narrative_zh.py

Two parallel narrative modules (not i18n of each other). Each exports
24 public functions: 9 dX_explanation + 9 dX_pattern + outcome_label
+ evidence_badge + no_facet_label + 3 methodology functions.

English narrative is lifted from current aggregate.py f-strings so
the existing report output stays byte-identical until the render
layer switches over (later task).

Chinese narrative is authored fresh following the parity brief;
cites the same metric keys as English (AST-verified) but owns its
own sentence structure.

tests/test_narrative_parity.py now passes."
```

---

## Task 3: Add behavioral tests for narrative modules

**Files:**
- Create: `tests/test_narrative_en.py`
- Create: `tests/test_narrative_zh.py`

Per-function behavior tests. The parity test only verifies metric-key sets; these tests ensure each function produces a non-empty string with the expected metric values substituted.

- [ ] **Step 1: Write the shared fixture module**

Create `/Users/imbad/Projects/cc-user-autopsy/tests/_narrative_fixtures.py`:

```python
"""Shared fixtures for narrative tests. Each fixture returns a complete
metrics dict for one dimension, with pattern_emit=True so pattern
functions can be tested too."""
from __future__ import annotations


def d1_fixture() -> dict:
    return {
        "score": 9,
        "metric_ta_rate_pct": 97.0,
        "metric_good_rate_with_ta_pct": 70.0,
        "pattern_emit": True,
    }


def d2_fixture() -> dict:
    return {
        "score": 6,
        "metric_iter_buggy_count": 9,
        "metric_iter_buggy_pct": 6.0,
        "pattern_emit": True,
    }


def d3_fixture() -> dict:
    return {
        "score": 5,
        "metric_pct_prompts_ge_100_chars": 20.0,
        "metric_pct_prompts_lt_20_chars": 15.0,
        "metric_bucket_median_tokens_per_commit": {"50-100": 8000},
        "metric_most_efficient_bucket": "50-100",
        "pattern_emit": True,
    }


def d4_fixture() -> dict:
    return {
        "score": 5,
        "metric_output_token_limit_sessions": 2,
        "metric_effort_no_commit_pct": 54.0,
        "metric_long_session_interrupt_rate_pct": 33.0,
        "metric_max_otl_in_one_project": 2,
        "pattern_emit": True,
    }


def d5_fixture() -> dict:
    return {
        "score": 8,
        "metric_interrupt_recovery_pct": 70.0,
        "metric_interrupted_sessions": 37,
        "pattern_emit": True,
    }


def d6_fixture() -> dict:
    return {
        "score": 7,
        "metric_mcp_rate_pct": 16.0,
        "metric_top3_share_pct": 63.0,
        "metric_top_tools": {"Bash": 100},
        "pattern_emit": True,
    }


def d7_fixture() -> dict:
    return {
        "score": 8,
        "metric_misunderstood_per_writing_session": 0.16,
        "metric_writing_sessions": 50,
        "pattern_emit": True,
    }


def d8_fixture() -> dict:
    return {
        "score": 3,
        "metric_friction_ratio_hi_lo": 39.0,
        "metric_worst_hour": {"hour": 0, "friction_per_session": 8.0},
        "metric_best_hour": {"hour": 19, "friction_per_session": 0.2},
        "pattern_emit": True,
    }


def d9_fixture() -> dict:
    return {
        "score": 10,
        "metric_tokens_per_good": 19331,
        "metric_tokens_per_not_good": 15019,
        "metric_ratio": 0.78,
        "metric_cache_hit_pct": 96.0,
        "pattern_emit": True,
    }


def d9_fixture_no_cache() -> dict:
    d = d9_fixture()
    d["metric_cache_hit_pct"] = None
    return d


ALL_DIM_FIXTURES = {
    "d1": d1_fixture,
    "d2": d2_fixture,
    "d3": d3_fixture,
    "d4": d4_fixture,
    "d5": d5_fixture,
    "d6": d6_fixture,
    "d7": d7_fixture,
    "d8": d8_fixture,
    "d9": d9_fixture,
}
```

- [ ] **Step 2: Write test_narrative_en.py**

Create `/Users/imbad/Projects/cc-user-autopsy/tests/test_narrative_en.py`:

```python
"""Behavioral tests for scripts/narrative_en.py. Each function must
return a non-empty string containing the key metrics from its fixture."""
from __future__ import annotations

import pytest

from scripts import narrative_en as N
from tests._narrative_fixtures import ALL_DIM_FIXTURES, d9_fixture_no_cache


@pytest.mark.parametrize("dim", sorted(ALL_DIM_FIXTURES.keys()))
def test_explanation_returns_non_empty_string(dim):
    fn = getattr(N, f"{dim}_explanation")
    out = fn(ALL_DIM_FIXTURES[dim]())
    assert isinstance(out, str) and out.strip(), f"{dim}_explanation returned empty"


@pytest.mark.parametrize("dim", sorted(ALL_DIM_FIXTURES.keys()))
def test_pattern_returns_non_empty_string(dim):
    fn = getattr(N, f"{dim}_pattern")
    out = fn(ALL_DIM_FIXTURES[dim]())
    assert isinstance(out, str) and out.strip(), f"{dim}_pattern returned empty"


def test_d1_explanation_cites_both_numbers():
    out = N.d1_explanation(ALL_DIM_FIXTURES["d1"]())
    assert "97%" in out
    assert "70%" in out


def test_d9_explanation_omits_cache_when_none():
    out = N.d9_explanation(d9_fixture_no_cache())
    assert "Cache" not in out


def test_d9_explanation_includes_cache_when_present():
    out = N.d9_explanation(ALL_DIM_FIXTURES["d9"]())
    assert "Cache hit ratio" in out
    assert "96%" in out


def test_outcome_label_known_values():
    assert N.outcome_label("fully_achieved") == "Fully achieved"
    assert N.outcome_label("partially_achieved") == "Partially achieved"


def test_outcome_label_unknown_falls_through():
    assert N.outcome_label("some_new_category") == "some_new_category"


def test_evidence_badge_known_values():
    assert N.evidence_badge("high_friction") == "High friction"
    assert N.evidence_badge("top_token") == "Top token"


def test_evidence_badge_unknown_falls_through():
    assert N.evidence_badge("mystery_tag") == "mystery_tag"


def test_no_facet_label():
    assert N.no_facet_label() == "(no facet)"


def test_methodology_functions_return_non_empty():
    assert N.methodology_subtitle().strip()
    assert N.methodology_sampling_body().strip()
    assert N.methodology_caveats_body().strip()
```

- [ ] **Step 3: Write test_narrative_zh.py**

Create `/Users/imbad/Projects/cc-user-autopsy/tests/test_narrative_zh.py`:

```python
"""Behavioral tests for scripts/narrative_zh.py. Mirrors test_narrative_en.py
but also enforces the no-em-dash rule on runtime output (narrative modules
produce prose strings that flow into the HTML report)."""
from __future__ import annotations

import pytest

from scripts import narrative_zh as N
from tests._narrative_fixtures import ALL_DIM_FIXTURES, d9_fixture_no_cache


@pytest.mark.parametrize("dim", sorted(ALL_DIM_FIXTURES.keys()))
def test_explanation_returns_non_empty_string(dim):
    fn = getattr(N, f"{dim}_explanation")
    out = fn(ALL_DIM_FIXTURES[dim]())
    assert isinstance(out, str) and out.strip(), f"{dim}_explanation returned empty"
    assert "—" not in out, f"{dim}_explanation contains em-dash"


@pytest.mark.parametrize("dim", sorted(ALL_DIM_FIXTURES.keys()))
def test_pattern_returns_non_empty_string(dim):
    fn = getattr(N, f"{dim}_pattern")
    out = fn(ALL_DIM_FIXTURES[dim]())
    assert isinstance(out, str) and out.strip(), f"{dim}_pattern returned empty"
    assert "—" not in out, f"{dim}_pattern contains em-dash"


def test_d1_explanation_cites_both_numbers():
    out = N.d1_explanation(ALL_DIM_FIXTURES["d1"]())
    assert "97%" in out
    assert "70%" in out


def test_d9_explanation_omits_cache_when_none():
    out = N.d9_explanation(d9_fixture_no_cache())
    assert "Cache" not in out


def test_d9_explanation_includes_cache_when_present():
    out = N.d9_explanation(ALL_DIM_FIXTURES["d9"]())
    assert "Cache 命中率" in out
    assert "96%" in out


def test_outcome_label_known_values():
    assert N.outcome_label("fully_achieved") == "完全達成"
    assert N.outcome_label("partially_achieved") == "部分達成"


def test_outcome_label_unknown_falls_through():
    assert N.outcome_label("some_new_category") == "some_new_category"


def test_evidence_badge_known_values():
    assert N.evidence_badge("high_friction") == "摩擦最高"
    assert N.evidence_badge("top_token") == "Token 用量最多"


def test_evidence_badge_unknown_falls_through():
    assert N.evidence_badge("mystery_tag") == "mystery_tag"


def test_no_facet_label():
    assert N.no_facet_label() == "（無 facet）"


def test_methodology_functions_return_non_empty():
    assert N.methodology_subtitle().strip()
    assert N.methodology_sampling_body().strip()
    assert N.methodology_caveats_body().strip()


def test_zh_narrative_contains_no_em_dash_in_static_methodology():
    for fn in (N.methodology_subtitle, N.methodology_sampling_body, N.methodology_caveats_body):
        assert "—" not in fn(), f"{fn.__name__} contains em-dash"
```

- [ ] **Step 4: Run the new tests — expect green**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest tests/test_narrative_en.py tests/test_narrative_zh.py -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest 2>&1 | tail -5
```

Expected: no regressions; total test count increased appropriately.

- [ ] **Step 6: Commit**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
git add tests/_narrative_fixtures.py tests/test_narrative_en.py tests/test_narrative_zh.py
git commit -m "test(narrative): behavioral tests for en + zh narrative modules

Covers the 9 explanation/pattern function pairs, outcome_label,
evidence_badge, no_facet_label, and methodology trio. Verifies
numeric substitution, conditional fragments (D9 cache), fallback
behavior for unknown outcome/badge keys, and the no-em-dash rule
on zh runtime output."
```

---

## Task 4: Update aggregate.py to emit pattern_emit

**Files:**
- Modify: `scripts/aggregate.py` (9 scoring functions around lines 340-800)

Add a `pattern_emit: bool` field to each scoring function's return dict. Preserve existing `explanation` and `pattern` fields unchanged (deprecated but still populated so external consumers don't break).

The `pattern_emit` value is the same condition the function currently uses to decide whether to compute a non-None `pattern` string. Extract that boolean into its own named variable, assign it to the dict, and leave the rest of the logic untouched.

- [ ] **Step 1: Audit current pattern-decision points**

Run:
```bash
cd /Users/imbad/Projects/cc-user-autopsy
grep -n "pattern = None\|pattern = (\|if len(.*) >= _PATTERN_MIN_SAMPLE" scripts/aggregate.py | head -30
```

Each scoring function has one site where pattern is decided. Note the line numbers; you'll modify each in the next step.

- [ ] **Step 2: Modify score_d1_delegation**

In `/Users/imbad/Projects/cc-user-autopsy/scripts/aggregate.py`, find the `score_d1_delegation` function. The current shape ends with:

```python
    # Pattern string (descriptive contrast). None when TA sample < _PATTERN_MIN_SAMPLE.
    if len(ta_rated) >= _PATTERN_MIN_SAMPLE:
        pattern = (
            f"Sessions that used Task agent had a {good_rate_ta:.0f}% "
            f"good-outcome rate, versus {_overall_good_rate(rated):.0f}% overall."
        )
    else:
        pattern = None
    return {
        "score": score,
        "metric_ta_rate_pct": round(ta_rate, 1),
        "metric_good_rate_with_ta_pct": round(good_rate_ta, 1),
        "explanation": f"{ta_rate:.0f}% of sessions used Task agent; good-outcome rate with Task agent was {good_rate_ta:.0f}%.",
        "pattern": pattern,
    }
```

Change to:

```python
    # Pattern string (descriptive contrast). None when TA sample < _PATTERN_MIN_SAMPLE.
    pattern_emit = len(ta_rated) >= _PATTERN_MIN_SAMPLE
    if pattern_emit:
        pattern = (
            f"Sessions that used Task agent had a {good_rate_ta:.0f}% "
            f"good-outcome rate, versus {_overall_good_rate(rated):.0f}% overall."
        )
    else:
        pattern = None
    return {
        "score": score,
        "metric_ta_rate_pct": round(ta_rate, 1),
        "metric_good_rate_with_ta_pct": round(good_rate_ta, 1),
        "pattern_emit": pattern_emit,
        # DEPRECATED (see docs/SCHEMA-CHANGES.md): prose fields retained
        # for 2 releases so external JSON consumers don't break. The render
        # layer reads narrative modules instead.
        "explanation": f"{ta_rate:.0f}% of sessions used Task agent; good-outcome rate with Task agent was {good_rate_ta:.0f}%.",
        "pattern": pattern,
    }
```

The only change: extract `pattern_emit` into a named variable, add it to the return dict, add a comment on the deprecated fields. The `explanation` and `pattern` strings themselves do not change.

- [ ] **Step 3: Apply the same pattern to D2 through D9**

For each remaining scoring function (`score_d2_rootcause`, `score_d3_prompt_quality`, `score_d4_context_mgmt`, `score_d5_interrupt`, `score_d6_tool_breadth`, `score_d7_writing`, `score_d8_time_mgmt`, `score_d9_token_efficiency`):

1. Find the line where `pattern` is assigned to a non-None string. The surrounding `if` condition becomes the value of `pattern_emit`.
2. Hoist the condition into `pattern_emit = <condition>`.
3. Replace the `if <condition>:` line with `if pattern_emit:`.
4. Add `"pattern_emit": pattern_emit,` above the deprecated `"explanation":` line in the return dict.
5. Add the DEPRECATED comment on the line above `"explanation":`.

For scorers that short-circuit with `return {"score": None, ..., "pattern": None}`, also add `"pattern_emit": False` to that dict. Example for D2:

```python
def score_d2_rootcause(sessions, rated, facets_coverage):
    if facets_coverage < 30:
        return {"score": None, "reason": "insufficient facet coverage", "pattern_emit": False, "pattern": None}
    ...
```

The short-circuit return for D1 at line 343 should also get `"pattern_emit": False`.

For D9 specifically (the function added in PR #15), `pattern_emit = True` whenever the function reaches the non-short-circuit return path. Assign it just before the return:

```python
    ...
    return {
        "score": score,
        "metric_tokens_per_good": round(tokens_per_good),
        "metric_tokens_per_not_good": round(tokens_per_not_good),
        "metric_ratio": round(ratio, 2),
        "metric_cache_hit_pct": round(cache_hit * 100, 1) if cache_hit is not None else None,
        "pattern_emit": True,   # D9 emits pattern whenever it reaches this return
        # DEPRECATED (see docs/SCHEMA-CHANGES.md)
        "explanation": explanation,
        "pattern": pattern,
    }
```

The short-circuit D9 returns (insufficient sample, zero-token good sessions) also get `"pattern_emit": False`.

- [ ] **Step 4: Run all scoring tests**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest tests/test_d9_token_efficiency.py tests/test_narrative_parity.py tests/test_narrative_en.py tests/test_narrative_zh.py -v 2>&1 | tail -30
```

Expected: all still green (existing tests only checked `score`, `explanation`, `pattern`, `reason`; `pattern_emit` is additive).

- [ ] **Step 5: Verify aggregate tests**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest tests/test_aggregate.py 2>&1 | tail -15
```

If `tests/test_aggregate.py` doesn't exist, skip this step. If it does and any test references `.pattern_emit`, confirm the new field flows through.

- [ ] **Step 6: Run full suite**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest 2>&1 | tail -5
```

Expected: zero regressions.

- [ ] **Step 7: Commit**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
git add scripts/aggregate.py
git commit -m "feat(aggregate): emit pattern_emit bool alongside deprecated prose fields

Each score_dX_* function now returns a pattern_emit: bool field whose
value equals the condition currently used to decide whether to produce
a non-None pattern string. Downstream consumers use pattern_emit as
the canonical signal.

The existing explanation and pattern JSON fields are retained unchanged
for two releases; see docs/SCHEMA-CHANGES.md. Render layer will switch
to reading narrative modules in a later task."
```

---

## Task 5: Write locale-switch orchestrator in build_html.py

**Files:**
- Modify: `scripts/build_html.py` around lines 2155-2175 (score-row render) + scattered sites for outcome, badge, methodology

This task threads narrative modules through the render path. It does not yet extract `report_render.py`; that's Task 6. This task keeps `build_html.py` as one file but switches its prose source from `locales.py` / `aggregate.py` strings to the narrative module picked by `--locale`.

- [ ] **Step 1: Import the narrative module conditionally**

Near the top of `/Users/imbad/Projects/cc-user-autopsy/scripts/build_html.py`, find the existing import block (around lines 1-30, the `from scripts.locales import ...` is the anchor). Add:

```python
def _load_narrative(locale: str):
    """Return the narrative module for the given locale."""
    if locale == "zh_TW":
        from scripts import narrative_zh as narrative
    else:
        from scripts import narrative_en as narrative
    return narrative
```

Place this helper just after the existing imports.

- [ ] **Step 2: Thread narrative through the score-row render loop**

Find the block around line 2155-2170 that currently reads:

```python
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
```

Change to:

```python
    narrative = _load_narrative(args.locale)
    score_rows = ""
    for key, title in dim_titles.items():
        s = scores.get(key, {})
        sc = s.get("score")
        band = score_band(sc)
        display = f'<span class="num">{sc}</span><span class="out">/ 10</span>' if sc is not None else 'n/a'
        dim_label = f"{key.split('_', 1)[0]} · {key.split('_', 1)[1].replace('_', ' ')}"
        dim_key = key.split('_', 1)[0].lower()  # "D1_delegation" -> "d1"
        exp_fn = getattr(narrative, f"{dim_key}_explanation", None)
        pat_fn = getattr(narrative, f"{dim_key}_pattern", None)
        if exp_fn and sc is not None:
            reason = exp_fn(s)
        else:
            reason = s.get("reason", "")
        pattern_html = ""
        if pat_fn and s.get("pattern_emit"):
            pattern_html = f'\n    <p class="pattern">{esc(pat_fn(s))}</p>'
```

Logic change:
- `reason` comes from `narrative.dX_explanation(s)` when `score is not None`, falling back to `s.get("reason")` for the insufficient-data case.
- `pattern_html` uses `narrative.dX_pattern(s)` when `s["pattern_emit"]` is truthy. Old `s.get("pattern")` path is abandoned.

- [ ] **Step 3: Thread outcome_label + no_facet_label into evidence render**

Find the block around line 2220-2230 that reads:

```python
                outcome = m.get('outcome', '') or '(no facet)'
```

Change to:

```python
                raw_outcome = m.get('outcome', '')
                outcome = narrative.outcome_label(raw_outcome) if raw_outcome else narrative.no_facet_label()
```

- [ ] **Step 4: Thread evidence_badge into badge render**

Find the line around line 2226 that reads:

```python
    <span class="tag {tag}">{esc(tag.replace('_', ' '))}</span>
```

Change to:

```python
    <span class="tag {tag}">{esc(narrative.evidence_badge(tag))}</span>
```

CSS still styles `.tag.high_friction` etc. via the class name (unchanged); only the display text now comes from the narrative module.

- [ ] **Step 5: Thread methodology functions**

Find the render site for the Methodology section (grep `method_h_sources\|section_method_subtitle\|method_sampling_body\|method_caveats_body`).

For each of the three body locale-key lookups (`method_sampling_body`, `method_caveats_body`) and the subtitle (`section_method_subtitle`), replace the `t(args.locale, "method_...")` call with the narrative function:

Before:
```python
    subtitle = t(args.locale, "section_method_subtitle")
    sampling_body = t(args.locale, "method_sampling_body")
    caveats_body = t(args.locale, "method_caveats_body")
```

After:
```python
    subtitle = narrative.methodology_subtitle()
    sampling_body = narrative.methodology_sampling_body()
    caveats_body = narrative.methodology_caveats_body()
```

If these are referenced in multiple places, change every site.

- [ ] **Step 6: Run the full test suite**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest 2>&1 | tail -10
```

Expected: all still green.

- [ ] **Step 7: Regenerate both locale reports and spot-check visually**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python3 scripts/build_html.py \
  --input /tmp/cc-autopsy-demo/analysis-data.json \
  --samples /tmp/cc-autopsy-demo/samples.json \
  --peer-review /tmp/cc-autopsy-demo/peer-review.md \
  --output /tmp/cc-autopsy-demo/report.html
python3 scripts/build_html.py \
  --input /tmp/cc-autopsy-demo/analysis-data.json \
  --samples /tmp/cc-autopsy-demo/samples.json \
  --peer-review /tmp/cc-autopsy-demo/peer-review.md \
  --output /tmp/cc-autopsy-demo/report-zh.html \
  --locale zh_TW
```

Manually compare the English and Chinese reports:
- Both reports should show D1-D9 score rows with explanation + pattern prose.
- English report prose should match what it previously said (byte-comparable for most paragraphs).
- Chinese report prose should now show Chinese explanations/patterns/methodology instead of the English residue.

- [ ] **Step 8: Commit**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
git add scripts/build_html.py
git commit -m "feat(build_html): switch prose source from aggregate/locales to narrative

Score-row explanation/pattern, outcome labels, evidence badges, and
methodology block now resolve via narrative_en.py or narrative_zh.py
(picked by --locale). Deprecated aggregate.py explanation/pattern
fields are no longer read; they remain in analysis-data.json for
external consumers.

zh_TW report evidence paragraphs now render in Chinese, not English."
```

---

## Task 6: Drop migrated locale keys from locales.py

**Files:**
- Modify: `scripts/locales.py`
- Modify: `tests/test_locales.py` (update REQUIRED_KEYS)

Now that narrative modules own methodology + evidence labels, the corresponding `locales.py` keys become dead code. Remove them and shrink the `REQUIRED_KEYS` set in the locale test.

- [ ] **Step 1: List keys to remove**

The following keys migrate out of `scripts/locales.py` and into narrative modules:

- `section_method_subtitle`
- `method_sampling_body`
- `method_caveats_body`
- `ev_high_friction`
- `ev_top_token`
- `ev_top_interrupt`
- `ev_not_achieved`
- `ev_partial`
- `ev_control_good`
- `ev_user_rejected`
- `ev_long_duration`

The following `method_*` keys remain in locales because they're chrome (section subheader labels, not narrative body):

- `method_h_sources`
- `method_src_session_meta`
- `method_src_facets`
- `method_src_transcripts`
- `method_h_sampling`
- `method_h_caveats`

**Double-check by grepping build_html.py for each removed key — if it still appears, Task 5 missed a site.**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
for k in section_method_subtitle method_sampling_body method_caveats_body \
         ev_high_friction ev_top_token ev_top_interrupt ev_not_achieved \
         ev_partial ev_control_good ev_user_rejected ev_long_duration; do
  echo "=== $k ==="
  grep -n "\"$k\"" scripts/build_html.py || echo "(unused in build_html.py — safe to remove)"
done
```

Every key must show `(unused in build_html.py — safe to remove)`. If any still appears, stop, go back to Task 5, and thread it through the narrative module.

- [ ] **Step 2: Remove keys from en block**

Edit `/Users/imbad/Projects/cc-user-autopsy/scripts/locales.py`. Find the en dict (around lines 25-225). Delete the 11 entries listed above from the en block.

- [ ] **Step 3: Remove keys from zh_TW block**

Same 11 keys, from the zh_TW block (around lines 240-445).

- [ ] **Step 4: Update REQUIRED_KEYS in test_locales.py**

`/Users/imbad/Projects/cc-user-autopsy/tests/test_locales.py` has a `REQUIRED_KEYS` set that is asserted against both locale blocks. Remove the 11 removed keys from that set.

Run:
```bash
cd /Users/imbad/Projects/cc-user-autopsy
grep -n "REQUIRED_KEYS" tests/test_locales.py
```

Locate the set definition and remove the migrated keys. If any of the 11 is not in the set (possible — REQUIRED_KEYS may only cover usage-rubric keys), that's fine; skip those in this step.

- [ ] **Step 5: Run locale tests**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest tests/test_locales.py -v 2>&1 | tail -20
```

Expected: pass. `test_locale_keysets_match` confirms en and zh still have identical key sets (symmetric removal); `test_all_usage_rubric_keys_present_in_*` pass because REQUIRED_KEYS matches what remains.

- [ ] **Step 6: Run full suite**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest 2>&1 | tail -5
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
git add scripts/locales.py tests/test_locales.py
git commit -m "refactor(locales): drop keys migrated to narrative modules

Removes 11 keys (3 methodology body, 8 evidence labels) from both
en and zh_TW blocks. They now live in scripts/narrative_en.py and
scripts/narrative_zh.py respectively.

Remaining locale keys are chrome only: tile labels, section titles,
chart legends, audience variants. The chrome-vs-narrative split is
formalized in docs/superpowers/specs/2026-04-20-i18n-explanations-design.md."
```

---

## Task 7: Extract report_render.py for cleanliness

**Files:**
- Create: `scripts/report_render.py`
- Modify: `scripts/build_html.py` (shrink to orchestrator)

Optional code-hygiene task. If `build_html.py` still looks maintainable after Task 5 + 6 and you're running low on time/tokens, skip this task — the contract works either way. The benefit of the split is that `report_render.py` has no narrative dependency and can be unit-tested against synthetic inputs.

If you skip, note it in the PR description.

- [ ] **Step 1: Inventory what to extract**

`build_html.py` currently contains:
- CLI arg parsing + file loading (**keep here**)
- Narrative module selection (**keep here**)
- Large HTML + CSS template strings (**extract**)
- Chart renderer JS string (**extract**)
- Helper functions like `score_band`, `fmt`, `esc` (**extract**)
- Main HTML assembly (**extract as `render()`**)

- [ ] **Step 2: Create report_render.py as a lift**

Create `/Users/imbad/Projects/cc-user-autopsy/scripts/report_render.py` and move everything from the "extract" list. Expose a single `render(ctx: dict) -> str` entry point. `ctx` contains:

- `analysis_data`: the loaded JSON
- `samples`: samples dict
- `peer_review`: markdown string
- `locale`: "en" or "zh_TW"
- `audience`: "self" or "hr"
- `narrative`: the loaded narrative module
- `chrome`: dict-of-dicts holding pre-resolved `t(locale, key)` chrome lookups (pre-computed in build_html.py)

`render()` returns the HTML string.

If extraction is mechanically invasive (many intermediate variables), defer this task — see the preamble note. An imperfectly-split `build_html.py` is acceptable.

- [ ] **Step 3: Run the full suite and regenerate reports**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest 2>&1 | tail -5
python3 scripts/build_html.py --input /tmp/cc-autopsy-demo/analysis-data.json --samples /tmp/cc-autopsy-demo/samples.json --peer-review /tmp/cc-autopsy-demo/peer-review.md --output /tmp/cc-autopsy-demo/report.html
python3 scripts/build_html.py --input /tmp/cc-autopsy-demo/analysis-data.json --samples /tmp/cc-autopsy-demo/samples.json --peer-review /tmp/cc-autopsy-demo/peer-review.md --output /tmp/cc-autopsy-demo/report-zh.html --locale zh_TW
diff <(cat /tmp/cc-autopsy-demo/report.html) <(git stash; python3 scripts/build_html.py --input /tmp/cc-autopsy-demo/analysis-data.json --samples /tmp/cc-autopsy-demo/samples.json --peer-review /tmp/cc-autopsy-demo/peer-review.md --output /tmp/cc-autopsy-demo/report-old.html && cat /tmp/cc-autopsy-demo/report-old.html; git stash pop) | head -40
```

Expected: output bytes for the en report match closely (allowing for whitespace changes from the refactor). If large diffs appear, the extraction introduced a regression — revert Task 7 and ship without it.

- [ ] **Step 4: Commit**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
git add scripts/report_render.py scripts/build_html.py
git commit -m "refactor(render): extract report_render.py from build_html.py

Pure render layer consumes pre-resolved chrome and narrative strings
and returns the final HTML. build_html.py stays as the CLI entry
that parses args, loads JSON, picks the narrative module, and
delegates."
```

---

## Task 8: Regression-verify end-to-end and open PR

- [ ] **Step 1: Full test matrix**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python -m pytest 2>&1 | tail -5
node --test tests/chart_layout.test.mjs 2>&1 | tail -5
```

Both must pass clean.

- [ ] **Step 2: Regenerate and visually verify both locale reports**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
python3 scripts/generate_demo_data.py
python3 scripts/aggregate.py --data-dir /tmp/cc-autopsy-demo/usage-data --output /tmp/cc-autopsy-demo/analysis-data.json
python3 scripts/sample_sessions.py --input /tmp/cc-autopsy-demo/analysis-data.json --output /tmp/cc-autopsy-demo/samples.json --projects-dir /tmp/cc-autopsy-demo/projects
python3 scripts/build_html.py --input /tmp/cc-autopsy-demo/analysis-data.json --samples /tmp/cc-autopsy-demo/samples.json --peer-review /tmp/cc-autopsy-demo/peer-review.md --output /tmp/cc-autopsy-demo/report.html
python3 scripts/build_html.py --input /tmp/cc-autopsy-demo/analysis-data.json --samples /tmp/cc-autopsy-demo/samples.json --peer-review /tmp/cc-autopsy-demo/peer-review.md --output /tmp/cc-autopsy-demo/report-zh.html --locale zh_TW
open /tmp/cc-autopsy-demo/report.html
open /tmp/cc-autopsy-demo/report-zh.html
```

Pause and ask the user to confirm visually:
- English report reads the same as before
- Chinese report: D1-D9 explanation + pattern are in Chinese, outcome labels are 完全達成 / 部分達成 / 未達成, badges are 摩擦最高 / Token 用量最多 / 中斷次數最多, methodology reads naturally

- [ ] **Step 3: Diff summary**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
git log --oneline fix/zh-tw-locale..HEAD
git diff fix/zh-tw-locale..HEAD --stat
```

Capture the stat for the PR description.

- [ ] **Step 4: Push and open PR**

```bash
cd /Users/imbad/Projects/cc-user-autopsy
git push -u origin feat/i18n-explanations
gh pr create --base fix/zh-tw-locale \
  --title "feat(i18n): split narrative from aggregator, zh report fully Chinese" \
  --body "$(cat <<'EOF'
## Summary

Replaces the locale-in-strings i18n approach with two independent narrative modules. Chinese report now reads as a report written in Chinese, not as a translation of the English one, while an AST parity test guarantees both locales cite identical metric keys.

**Stacked PR:** base is \`fix/zh-tw-locale\` (PR #16). After #16 merges, this PR rebases to main.

## Architecture

- \`scripts/narrative_en.py\` + \`scripts/narrative_zh.py\` — 24 public functions each (9 dX_explanation + 9 dX_pattern + outcome_label + evidence_badge + no_facet_label + 3 methodology)
- \`scripts/aggregate.py\` — gains \`pattern_emit: bool\`, retains deprecated \`explanation\`/\`pattern\` JSON fields for 2 releases
- \`scripts/build_html.py\` — picks narrative module by \`--locale\`, drops reads of deprecated aggregator prose fields
- \`scripts/locales.py\` — loses 11 migrated keys, keeps chrome only

## Parity guard

\`tests/test_narrative_parity.py\` AST-scans both narrative modules, asserts both expose the same public function set and each dX function cites the same \`metrics[...]\` keys. Blocks drift.

## Docs

- \`docs/superpowers/specs/2026-04-20-i18n-explanations-design.md\` — full spec
- \`docs/superpowers/specs/narrative-parity-brief.md\` — per-dim writing checklist
- \`docs/SCHEMA-CHANGES.md\` — deprecation schedule for JSON fields

## Test plan

- [x] \`pytest\` — all green, including 21 new parity tests + 24+ new narrative behavioral tests
- [x] \`node --test tests/chart_layout.test.mjs\` — 23/23 pass
- [x] en + zh demo reports regenerated; user visually confirmed zh report is fully Chinese

## Non-goals / deferred

- No font-size floor policy (≥14px zh / ≥12px en) — separate \`feat/type-scale-floors\` branch
- Deprecated JSON fields removed in a later release; consumers have 2-release window

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: Notify user on Telegram**

Send the PR URL to Telegram with a one-sentence summary of what to visually verify on the zh report.

---

## Self-Review

**1. Spec coverage.**

| Spec section / requirement | Task covering it |
|---|---|
| Section 1 narrative API (24 functions) | Task 2 |
| Parity test via AST | Task 1 |
| Public function set parity | Task 1 Step 1 (test_public_function_set_is_identical) |
| No dynamic metrics[] access | Task 1 Step 1 (test_no_dynamic_metrics_access_in_{en,zh}) |
| Section 2 aggregate contract (pattern_emit + deprecated prose retained) | Task 4 |
| Section 3 report_render extraction | Task 7 |
| Section 4 AST parity test full implementation | Task 1 |
| Section 5 narrative brief | Already written alongside spec (prior commit) |
| Section 6 files touched + non-goals | Covered in Tasks 2, 4, 5, 6, 7 |
| Section 7 implementation order | This plan follows it |
| outcome_label fallback (unknown returns raw) | Task 2 + test Task 3 |
| evidence_badge fallback | Task 2 + test Task 3 |
| Insufficient-sample explanation handling | Task 5 Step 2 (falls back to `s.get("reason")`) |
| Deprecated field retention 2 releases | Task 4 comments + docs/SCHEMA-CHANGES.md (prior commit) |

**2. Placeholder scan.**

No "TBD", "TODO", or "similar to Task N" references. Task 7 explicitly marked optional with clear skip criteria (not a placeholder — an explicit decision point).

**3. Type consistency.**

- `pattern_emit: bool` used consistently in Task 4, Task 5, narrative test fixtures.
- `narrative` module name used consistently across Tasks 2, 3, 5, 7.
- Function-name convention `dX_explanation` / `dX_pattern` consistent across narrative modules, parity test, and render orchestrator.
- `metrics` parameter name matches across narrative modules and parity test scanner.
