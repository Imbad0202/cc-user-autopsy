# V5 Phase 3 — Trend Ledger UI + Badge Layer + Recruiter Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land Phase 3 of the AI-work-ledger redesign: the badge layer (6 threshold-based badges computed in the deterministic pipeline, bars published in the rubric), the SELF-only trend ledger book (reads `autopsy-history.jsonl` snapshots, unlocks at 3, habit-drift opener, this-run/last-run/~90-days-ago comparison with inline-SVG sparklines), and the external recruiter version rebuilt to spec §4 (identity card → earned badges → output ledger → case study → scope disclosure; the V4 profile-card/memo/4-signal-scores/trends HR layout is removed).

**Architecture:** All numbers stay in the deterministic pipeline: `aggregate.py` gains `compute_badges()` (new additive top-level `badges` block). `build_html.py` gains `read_history_snapshots()` (corrupt-line-tolerant, dedupe-by-date) and enriches `append_history_snapshot()` with earned badge ids + `overall_avg`. `report_render.py` gains `_build_trend_ledger()` (SELF, direction-C, Python-generated inline SVG sparklines — no new canvas charts, `js/chart_layout.js` untouched) and `_build_badges_section()` / `_build_hr_output_ledger()` for the HR rebuild. Badge wording is locale template text, never LLM prose (spec §2 rule 6).

**Tech Stack:** Python 3.9+ stdlib only (pytest test-only), inline HTML/CSS/SVG in `report_render.py`, no new JS.

**Spec:** `docs/superpowers/specs/2026-07-14-ai-work-ledger-redesign.md` §2 (two-layer model + audit discipline), §3 book 4 (trend ledger), §4 (badges + recruiter v1), §7 (schema/snapshot), §8 (rendering), §10 (suppression), §11 (testing), §13 (defaults: unlock at 3 snapshots).

---

## 決策點（白話，給用戶看的段落；其餘都是工程細節可跳過）

這些是本計畫替你選的預設值。每一條都可以改，改了不動架構。

1. **對外版（給招募方看的那份）整個換骨架** — ①舊版的「能力概況卡、AI 寫的候選人短評、四項評分、趨勢圖」全部拿掉，換成五塊：名片頭 → 拿到的徽章 → 產出帳（只列你允許公開的專案）→ 一個實例 → 方法揭露。②推它是因為已核准的兩層制：對外的可信度來自「標準是公開的、門檻是白紙黑字的、任何人可以重跑驗證」，不是來自自我描述；沒過門檻的徽章直接不出現，不解釋也不道歉。③代價是對外版變短、沒有敘事溫度；讀的人只看到過了門檻的硬主張，看不到「這個人怎麼工作」的故事。
2. **六個徽章的 v1 門檻值**（見下方表格）— ①門檻寫進公開的 rubric 檔、標 provisional v1；②推這組數值是因為它們對齊現有九維評分裡「8 分以上」那一段，等於「拿徽章＝該維度做到優良區」；③代價是門檻是先驗猜的，跑過真資料後可能要調（spec §13 本來就預留這步）。改任何一個門檻都只是改一個常數＋rubric 一行字。
3. **自用版看不到徽章區塊** — ①徽章明細只進資料檔和對外版；自用版的趨勢帳裡會有一行「拿到幾個徽章」的數字，但沒有徽章卡片。②推它是因為 spec 的定位：自用版是稽核文件（含失敗與漏水），徽章層是對外宣傳用的結果層，混在一起會讓自用版讀起來像自我表揚。③代價是你自己想看「我差哪個徽章、差多少」得去翻資料檔（之後想加可以再加一節，不動這次架構）。
4. **趨勢帳的三欄怎麼取** — ①「本次」用這次剛算出來的數字；「上次」用歷史檔最新一筆；「約三個月前」挑距離 90 天最近的那筆。同一天跑多次報告只留當天最後一筆，避免一天狂跑三次就「解鎖」出沒意義的趨勢。②推它是因為簡單、可解釋、欄位標題直接印日期不會誤導；③代價是「三個月前」那欄在歷史不足三個月時其實是「最早那筆」，欄位標題印實際日期讓讀者自己看得出來。
5. **趨勢小線圖用內嵌 SVG，不加新的 canvas 圖表** — ①五條趨勢（總分、commits、sessions、漏水金額、徽章數）各畫一條迷你折線，由 Python 直接產 SVG 塞進 HTML。②推它是因為零 JS 增量：不動 `js/chart_layout.js`，不多一套 node 測試面，離線自足規則自動滿足；③代價是沒有 hover tooltip，只有形狀（表格裡本來就有精確數字）。

---

## Global Constraints

- Python 3.9+ **standard library only** at runtime (pytest is test-only).
- Output HTML fully self-contained; all user-derived text through `esc()` / `inline_md()`; script-bound data through `json_for_script()` (enforced by `tests/smoke_test.py`).
- `locales.py`: en and zh_TW share the exact same key set; zh_TW values must not contain `—`; `t()` raises KeyError on miss (`tests/test_locales.py`). zh_TW is authored natively, not translated.
- All new analysis blocks are **additive**; document in `docs/SCHEMA-CHANGES.md` **in the same commit** as the code change (repo rule).
- **Two `ledger.leaks` shapes** (docs/SCHEMA-CHANGES.md 2026-07-14): `analysis-data.json` has a dict `{window_weeks, items:[...]}` whose items carry `evidence` sids; `autopsy-history.jsonl` snapshots have a **compact list** `[{type, weekly_cost_usd, weekly_tokens, occurrences}]` with NO evidence. The trend renderer must read each shape from its own source and never render sids from either.
- Trend/badge sections must not render session IDs or cross-LLM prompt text anywhere; HR output additionally must not contain non-allowlisted project names (`id="ledger-` sections stay SELF-only; the HR output-ledger section id must NOT start with `ledger-` — smoke asserts `'id="ledger-' not in hr_html`).
- Below-gate blocks are suppressed entirely — no apologetic placeholders (spec §10). The ONE exception is the trend ledger's locked state, which spec §3 explicitly defines as "unlocks after N more runs" one-liner.
- Badge wording is template text defined by the standard in `locales.py`, never LLM freestyle (spec §2 rule 6). Unearned badges are silently absent in HR — never rendered as "failed".
- Sample-gate/threshold literals are independent named constants with the Phase 1/2 comment idiom; bars mirrored in `references/scoring-rubric.md` in the same commit.
- Direction-C grammar: gold `#B08A2E` accent (`--c-gold`), negative red `#9C201A` (`--c-neg`) only for bad numbers, numbered Exhibits with source lines, action-title section heads.
- Conventional-commit subjects; per task run `python3 -m pytest tests/ -q`. `js/chart_layout.js` is NOT touched this phase — `node --test tests/chart_layout.test.mjs` only needs one confirmation run at the end. Known baseline: 2 pre-existing failures in `tests/test_build_html_additions.py` on clean main (`test_zh_tw_build_contains_localized_strings`, `test_disclaimer_placeholder_in_template`) — not yours to fix, do not add new failures.
- Never run `build_html.py` in a test without `--history-file <tmp path>` (Phase 1 lesson: default path pollutes real `~/.claude/usage-data/autopsy-history.jsonl`).
- Demo-data injections are **index-forced, never random-dependent**, and must be engineered to *actually pass* the gate they exercise, accounting for every cap/truncation on the path (Phase 2 round-21 lesson: a sentinel that never reaches the guarded path is worthless).
- Maintain an implementation-notes file (`docs/superpowers/plans/2026-07-15-v5-phase3-implementation-notes.md`, temporary, delete after merge) recording only substantive deviations: deviation point / conservative choice taken / reason.

## Provisional v1 badge bars (decided at plan time — recorded in `references/scoring-rubric.md` by Task 1)

| Badge id | Constants | Earned when | Min sample (`n`) |
|---|---|---|---|
| `delegation` | `_BADGE_DELEGATION_TA_RATE = 30.0`, `_BADGE_DELEGATION_GOOD_RATE = 70.0`, `_BADGE_DELEGATION_MIN_TA_RATED = 15` | D1 `metric_ta_rate_pct ≥ 30` AND `metric_good_rate_with_ta_pct ≥ 70` | ≥15 rated Task-agent sessions |
| `root_cause` | `_BADGE_ROOTCAUSE_MAX_ITER_BUGGY_PCT = 7.0`, `_BADGE_ROOTCAUSE_MIN_RATED = 30` | D2 scored AND `metric_iter_buggy_pct ≤ 7` | ≥30 rated sessions |
| `tool_breadth` | `_BADGE_BREADTH_MCP_RATE = 15.0`, `_BADGE_BREADTH_TOP3_SHARE = 55.0`, `_BADGE_BREADTH_MIN_SESSIONS = 30` | D6 `metric_mcp_rate_pct ≥ 15` AND `metric_top3_share_pct ≤ 55` | ≥30 sessions |
| `token_efficiency` | `_BADGE_EFFICIENCY_MAX_RATIO = 1.1`, `_BADGE_EFFICIENCY_MIN_CACHE_PCT = 80.0`, `_BADGE_EFFICIENCY_MIN_RATED = 30` | D9 scored AND `metric_ratio ≤ 1.1` AND `metric_cache_hit_pct ≥ 80` | ≥30 rated sessions |
| `shipping_cadence` | `_BADGE_SHIPPING_COMMITS_PER_WEEK = 5.0`, `_BADGE_SHIPPING_MIN_SESSIONS_WITH_COMMITS = 10`, `_BADGE_SHIPPING_MIN_WINDOW_DAYS = 14` | `ledger.output.git_commits / (window.days/7) ≥ 5` AND `sessions_with_commits ≥ 10` | window ≥14 days |
| `cross_tool_orchestration` | `_BADGE_ORCH_MIN_MULTI_HOURS = 10`, `_BADGE_ORCH_MIN_WINDOW_DAYS = 14` | ≥2 **full**-tier sources detected AND common window ≥14 days (not degraded) AND `parallel.hours_multi_source ≥ 10` | `n` = multi-source hours |

Alignment note (goes into the rubric): each bar equals the "score ≥ 8" band of the corresponding 9-dim rule where one exists (D1/D2/D6/D9), so "badge earned" reads as "this dimension is in its top band with enough sample". `shipping_cadence` and `cross_tool_orchestration` have no dimension analogue; their bars are pure priors.

Trend defaults: `_TREND_MIN_SNAPSHOTS = 3` (spec §13), reference column target = newest snapshot date − 90 days, snapshots deduped by `date` (last line per date wins).

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `scripts/aggregate.py` | modify | badge constants, `_badge()`, `compute_badges()`, main() wiring |
| `scripts/build_html.py` | modify | snapshot enrichment (badges + overall_avg), `read_history_snapshots()`, pass `history_entries` into render |
| `scripts/report_render.py` | modify | `_sparkline_svg()`, `_build_trend_ledger()`, `trend-ledger` narration book + opening-band 4th finding, `_build_badges_section()`, `_build_hr_output_ledger()`, HR layout demolition + scope disclosure, `$badges_section` template slot, CSS |
| `scripts/locales.py` | modify | trend/drift/badge/HR-rebuild keys added; dead HR keys removed (both locales) |
| `scripts/generate_demo_data.py` | modify | `random.seed()` for determinism, `gen_history_snapshots(now)` |
| `references/scoring-rubric.md` | modify | new "## Badges (v1, provisional)" section |
| `docs/SCHEMA-CHANGES.md` | modify | additive `badges` block; snapshot `overall_avg` + badges-now-populated note |
| `SKILL.md` | modify | description, layout list, Step 3b trend book, Step 4 commands, HR steps, audience table, Files |
| `tests/test_badges.py` | create | compute_badges unit tests (earn / miss / below-sample per badge) + rubric-sync check |
| `tests/test_history_snapshot.py` | modify | badges + overall_avg in snapshot; `read_history_snapshots` reader tests |
| `tests/test_trend_render.py` | create | locked/unlocked gating, column pick, both leak shapes, sparkline, narration book, opening-band claim |
| `tests/test_hr_recruiter.py` | create | HR five-block layout, earned-only badges, scope disclosure, demolition assertions, privacy |
| `tests/test_ledger_render.py` | modify | `_parse_ledger_narration` equality test gains `trend-ledger` key |
| `tests/test_demo_data.py` | modify | demo history snapshots + deterministic badge assertions |
| `tests/smoke_test.py` | modify | seed history → trend section in SELF; HR rebuild invariants |

Branch: create `v5-phase3-trend-badges-recruiter` off `main`; work lands via PR (dual gate: `/codex review` + `/security-review`, both 0 P1/P2 before merge).

---

### Task 1: `compute_badges()` in `aggregate.py` + rubric + schema doc

**Files:**
- Modify: `scripts/aggregate.py` (constants + `_badge()` + `compute_badges()` after `compute_ledger()` ~line 2086; wiring in `main()` after the `final["ledger"]["leaks"] = ...` line ~3177)
- Modify: `references/scoring-rubric.md` (append "## Badges (v1, provisional)" section at end)
- Modify: `docs/SCHEMA-CHANGES.md` (additive `badges` block entry)
- Test: `tests/test_badges.py` (create)

**Interfaces:**
- Produces: `compute_badges(scores: dict, ledger: dict, cross_llm: dict, sessions: list, rated: list) -> dict` returning `{"schema_version": 1, "standard_version": "v1", "items": [<6 dicts in fixed order>]}`; each item is `{"id": str, "earned": bool, "n": int, "metrics": dict, "thresholds": dict}` plus optional `"reason": str` when not evaluable. Item ids in order: `delegation`, `root_cause`, `tool_breadth`, `token_efficiency`, `shipping_cadence`, `cross_tool_orchestration`. Tasks 2 (snapshot), 3 (trend row), 4 (HR renderer), 5 (demo) all consume exactly this shape.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_badges.py
"""compute_badges(): threshold-based badge layer (spec §4, bars provisional v1).

Every badge: one earn case, one miss case, one below-sample case.
Fixture dicts mirror the exact metric field names the D-scorers emit.
"""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from aggregate import compute_badges  # noqa: E402


def _scores(**over):
    base = {
        "D1_delegation": {"score": 8, "metric_ta_rate_pct": 45.0,
                          "metric_good_rate_with_ta_pct": 75.0},
        "D2_root_cause": {"score": 9, "metric_iter_buggy_pct": 3.0},
        "D6_tool_breadth": {"score": 8, "metric_mcp_rate_pct": 20.0,
                            "metric_top3_share_pct": 50.0},
        "D9_token_efficiency": {"score": 8, "metric_ratio": 1.0,
                                "metric_cache_hit_pct": 90.0},
    }
    base.update(over)
    return base


def _ledger(days=28, commits=40, with_commits=12):
    return {"window": {"start": "2026-06-01", "end": "2026-06-29", "days": days},
            "output": {"git_commits": commits, "git_pushes": 10,
                       "sessions_with_commits": with_commits}}


def _cross(full_sources=("claude", "codex"), win_days=28, degraded=False,
           multi_hours=15):
    return {
        "sources": [{"source": s, "coverage": "full", "detected": True}
                    for s in full_sources] +
                   [{"source": "grok", "coverage": "partial", "detected": True}],
        "common_window": {"start": "2026-06-01", "end": "2026-06-29",
                          "days": win_days, "degraded": degraded},
        "parallel": {"hours_multi_source": multi_hours,
                     "hours_single_source": 100},
    }


def _sessions(n):
    return [{"uses_task_agent": i % 2 == 0, "outcome": "fully_achieved"}
            for i in range(n)]


class BadgeShapeTests(unittest.TestCase):
    def test_six_items_fixed_order_and_shape(self):
        out = compute_badges(_scores(), _ledger(), _cross(),
                             _sessions(60), _sessions(40))
        self.assertEqual(out["schema_version"], 1)
        self.assertEqual(out["standard_version"], "v1")
        self.assertEqual(
            [b["id"] for b in out["items"]],
            ["delegation", "root_cause", "tool_breadth", "token_efficiency",
             "shipping_cadence", "cross_tool_orchestration"])
        for b in out["items"]:
            self.assertIn("earned", b)
            self.assertIn("n", b)
            self.assertIn("metrics", b)
            self.assertIn("thresholds", b)

    def test_all_earned_on_strong_fixture(self):
        out = compute_badges(_scores(), _ledger(), _cross(),
                             _sessions(60), _sessions(40))
        self.assertTrue(all(b["earned"] for b in out["items"]))


class DelegationBadgeTests(unittest.TestCase):
    def test_miss_when_good_rate_below_bar(self):
        sc = _scores(D1_delegation={"score": 7, "metric_ta_rate_pct": 45.0,
                                    "metric_good_rate_with_ta_pct": 60.0})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        self.assertFalse(out["items"][0]["earned"])

    def test_below_sample_not_earned_with_reason(self):
        # only 10 rated TA sessions < 15 floor
        rated = [{"uses_task_agent": i < 10, "outcome": "fully_achieved"}
                 for i in range(40)]
        out = compute_badges(_scores(), _ledger(), _cross(), _sessions(60), rated)
        b = out["items"][0]
        self.assertFalse(b["earned"])
        self.assertEqual(b["n"], 10)
        self.assertIn("reason", b)


class RootCauseBadgeTests(unittest.TestCase):
    def test_miss_when_iter_buggy_above_bar(self):
        sc = _scores(D2_root_cause={"score": 7, "metric_iter_buggy_pct": 9.0})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        self.assertFalse(out["items"][1]["earned"])

    def test_unscored_d2_not_earned(self):
        sc = _scores(D2_root_cause={"score": None,
                                    "reason": "insufficient facet coverage"})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        b = out["items"][1]
        self.assertFalse(b["earned"])
        self.assertIn("reason", b)

    def test_below_sample(self):
        out = compute_badges(_scores(), _ledger(), _cross(),
                             _sessions(60), _sessions(20))
        self.assertFalse(out["items"][1]["earned"])


class ToolBreadthBadgeTests(unittest.TestCase):
    def test_miss_when_top3_share_too_high(self):
        sc = _scores(D6_tool_breadth={"score": 7, "metric_mcp_rate_pct": 20.0,
                                      "metric_top3_share_pct": 70.0})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        self.assertFalse(out["items"][2]["earned"])

    def test_below_sample(self):
        out = compute_badges(_scores(), _ledger(), _cross(),
                             _sessions(20), _sessions(40))
        self.assertFalse(out["items"][2]["earned"])


class TokenEfficiencyBadgeTests(unittest.TestCase):
    def test_miss_when_cache_below_bar(self):
        sc = _scores(D9_token_efficiency={"score": 6, "metric_ratio": 1.0,
                                          "metric_cache_hit_pct": 50.0})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        self.assertFalse(out["items"][3]["earned"])

    def test_none_cache_not_earned(self):
        sc = _scores(D9_token_efficiency={"score": 8, "metric_ratio": 1.0,
                                          "metric_cache_hit_pct": None})
        out = compute_badges(sc, _ledger(), _cross(), _sessions(60), _sessions(40))
        self.assertFalse(out["items"][3]["earned"])


class ShippingCadenceBadgeTests(unittest.TestCase):
    def test_miss_when_commits_per_week_below_bar(self):
        out = compute_badges(_scores(), _ledger(commits=10), _cross(),
                             _sessions(60), _sessions(40))
        self.assertFalse(out["items"][4]["earned"])

    def test_window_too_short_not_earned(self):
        out = compute_badges(_scores(), _ledger(days=7), _cross(),
                             _sessions(60), _sessions(40))
        b = out["items"][4]
        self.assertFalse(b["earned"])
        self.assertIn("reason", b)

    def test_metrics_carry_commits_per_week(self):
        out = compute_badges(_scores(), _ledger(days=28, commits=40), _cross(),
                             _sessions(60), _sessions(40))
        self.assertAlmostEqual(out["items"][4]["metrics"]["commits_per_week"],
                               10.0, places=1)


class OrchestrationBadgeTests(unittest.TestCase):
    def test_miss_with_one_full_source(self):
        out = compute_badges(_scores(), _ledger(), _cross(full_sources=("claude",)),
                             _sessions(60), _sessions(40))
        b = out["items"][5]
        self.assertFalse(b["earned"])
        self.assertIn("reason", b)

    def test_miss_when_window_degraded(self):
        out = compute_badges(_scores(), _ledger(), _cross(degraded=True),
                             _sessions(60), _sessions(40))
        self.assertFalse(out["items"][5]["earned"])

    def test_miss_when_hours_below_bar(self):
        out = compute_badges(_scores(), _ledger(), _cross(multi_hours=4),
                             _sessions(60), _sessions(40))
        self.assertFalse(out["items"][5]["earned"])

    def test_no_common_window_not_earned(self):
        cross = _cross()
        cross["common_window"] = None
        out = compute_badges(_scores(), _ledger(), cross,
                             _sessions(60), _sessions(40))
        self.assertFalse(out["items"][5]["earned"])


class RubricSyncTests(unittest.TestCase):
    """Cheap table-integrity check in the spirit of test_cost_estimate:
    every badge id must appear in the rubric's Badges section."""
    def test_rubric_mentions_every_badge_id(self):
        rubric = (SKILL_DIR / "references" / "scoring-rubric.md").read_text()
        self.assertIn("## Badges", rubric)
        for bid in ("delegation", "root_cause", "tool_breadth",
                    "token_efficiency", "shipping_cadence",
                    "cross_tool_orchestration"):
            self.assertIn(f"`{bid}`", rubric)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_badges.py -q`
Expected: FAIL / ERROR with `ImportError: cannot import name 'compute_badges'`

- [ ] **Step 3: Implement `compute_badges()`**

Insert after `compute_ledger()` (directly above the `# --- Blind-spot engine` banner, ~line 2087):

```python
# --- Badge layer (Phase 3, spec §4) -----------------------------------
# Bars are PROVISIONAL v1 (spec §13) and mirrored in
# references/scoring-rubric.md "## Badges (v1, provisional)" — keep the
# two in sync (tests/test_badges.py checks ids; numbers are hand-synced).
# Where a 9-dim analogue exists (D1/D2/D6/D9) each bar equals that
# dimension's "score >= 8" band, so earning a badge reads as "top band
# with enough sample". Threshold constants are independent from the
# scorers' literals on purpose — retuning a score curve must not silently
# move a published badge bar.
_BADGE_STANDARD_VERSION = "v1"
_BADGE_DELEGATION_MIN_TA_RATED = 15
_BADGE_DELEGATION_TA_RATE = 30.0
_BADGE_DELEGATION_GOOD_RATE = 70.0
_BADGE_ROOTCAUSE_MIN_RATED = 30
_BADGE_ROOTCAUSE_MAX_ITER_BUGGY_PCT = 7.0
_BADGE_BREADTH_MIN_SESSIONS = 30
_BADGE_BREADTH_MCP_RATE = 15.0
_BADGE_BREADTH_TOP3_SHARE = 55.0
_BADGE_EFFICIENCY_MIN_RATED = 30
_BADGE_EFFICIENCY_MAX_RATIO = 1.1
_BADGE_EFFICIENCY_MIN_CACHE_PCT = 80.0
_BADGE_SHIPPING_MIN_WINDOW_DAYS = 14
_BADGE_SHIPPING_COMMITS_PER_WEEK = 5.0
_BADGE_SHIPPING_MIN_SESSIONS_WITH_COMMITS = 10
_BADGE_ORCH_MIN_WINDOW_DAYS = 14
_BADGE_ORCH_MIN_MULTI_HOURS = 10


def _badge(id_, earned, n, metrics, thresholds, reason=None):
    item = {"id": id_, "earned": bool(earned), "n": int(n),
            "metrics": metrics or {}, "thresholds": thresholds}
    if reason:
        item["reason"] = reason
    return item


def compute_badges(scores, ledger, cross_llm, sessions, rated):
    """Threshold-based badge layer (spec §4). Self-referential only —
    every bar is an absolute published threshold, never a percentile.
    Missing/unscored inputs mean "not earned" with a reason, never a
    crash and never an imputed value. Renders earned-only in external
    versions; the full item list (incl. unearned) ships in
    analysis-data.json so the standard is auditable."""
    items = []

    # 1. delegation — D1 metrics over rated Task-agent sessions
    d1 = scores.get("D1_delegation") or {}
    ta_rated_n = sum(1 for s in rated if s.get("uses_task_agent"))
    ta_rate = d1.get("metric_ta_rate_pct")
    good_ta = d1.get("metric_good_rate_with_ta_pct")
    thr = {"min_ta_rated": _BADGE_DELEGATION_MIN_TA_RATED,
           "ta_rate_pct": _BADGE_DELEGATION_TA_RATE,
           "good_rate_with_ta_pct": _BADGE_DELEGATION_GOOD_RATE}
    met = {"ta_rate_pct": ta_rate, "good_rate_with_ta_pct": good_ta}
    if ta_rated_n < _BADGE_DELEGATION_MIN_TA_RATED:
        items.append(_badge("delegation", False, ta_rated_n, met, thr,
                            reason="below minimum sample"))
    elif ta_rate is None or good_ta is None:
        items.append(_badge("delegation", False, ta_rated_n, met, thr,
                            reason="dimension not scored"))
    else:
        items.append(_badge(
            "delegation",
            ta_rate >= _BADGE_DELEGATION_TA_RATE
            and good_ta >= _BADGE_DELEGATION_GOOD_RATE,
            ta_rated_n, met, thr))

    # 2. root_cause — D2 iterative-buggy co-occurrence over rated pool
    d2 = scores.get("D2_root_cause") or {}
    iter_buggy = d2.get("metric_iter_buggy_pct")
    thr = {"min_rated": _BADGE_ROOTCAUSE_MIN_RATED,
           "max_iter_buggy_pct": _BADGE_ROOTCAUSE_MAX_ITER_BUGGY_PCT}
    met = {"iter_buggy_pct": iter_buggy}
    if len(rated) < _BADGE_ROOTCAUSE_MIN_RATED:
        items.append(_badge("root_cause", False, len(rated), met, thr,
                            reason="below minimum sample"))
    elif d2.get("score") is None or iter_buggy is None:
        items.append(_badge("root_cause", False, len(rated), met, thr,
                            reason="dimension not scored"))
    else:
        items.append(_badge(
            "root_cause", iter_buggy <= _BADGE_ROOTCAUSE_MAX_ITER_BUGGY_PCT,
            len(rated), met, thr))

    # 3. tool_breadth — D6 metrics over the full session pool
    d6 = scores.get("D6_tool_breadth") or {}
    mcp = d6.get("metric_mcp_rate_pct")
    top3 = d6.get("metric_top3_share_pct")
    thr = {"min_sessions": _BADGE_BREADTH_MIN_SESSIONS,
           "mcp_rate_pct": _BADGE_BREADTH_MCP_RATE,
           "max_top3_share_pct": _BADGE_BREADTH_TOP3_SHARE}
    met = {"mcp_rate_pct": mcp, "top3_share_pct": top3}
    if len(sessions) < _BADGE_BREADTH_MIN_SESSIONS:
        items.append(_badge("tool_breadth", False, len(sessions), met, thr,
                            reason="below minimum sample"))
    elif mcp is None or top3 is None:
        items.append(_badge("tool_breadth", False, len(sessions), met, thr,
                            reason="dimension not scored"))
    else:
        items.append(_badge(
            "tool_breadth",
            mcp >= _BADGE_BREADTH_MCP_RATE and top3 <= _BADGE_BREADTH_TOP3_SHARE,
            len(sessions), met, thr))

    # 4. token_efficiency — D9 ratio + cache hit
    d9 = scores.get("D9_token_efficiency") or {}
    ratio = d9.get("metric_ratio")
    cache = d9.get("metric_cache_hit_pct")
    thr = {"min_rated": _BADGE_EFFICIENCY_MIN_RATED,
           "max_ratio": _BADGE_EFFICIENCY_MAX_RATIO,
           "min_cache_hit_pct": _BADGE_EFFICIENCY_MIN_CACHE_PCT}
    met = {"ratio": ratio, "cache_hit_pct": cache}
    if len(rated) < _BADGE_EFFICIENCY_MIN_RATED:
        items.append(_badge("token_efficiency", False, len(rated), met, thr,
                            reason="below minimum sample"))
    elif d9.get("score") is None or ratio is None or cache is None:
        items.append(_badge("token_efficiency", False, len(rated), met, thr,
                            reason="dimension not scored"))
    else:
        items.append(_badge(
            "token_efficiency",
            ratio <= _BADGE_EFFICIENCY_MAX_RATIO
            and cache >= _BADGE_EFFICIENCY_MIN_CACHE_PCT,
            len(rated), met, thr))

    # 5. shipping_cadence — evidence-backed commits per active week
    win = (ledger or {}).get("window") or {}
    out = (ledger or {}).get("output") or {}
    days = win.get("days") or 0
    commits = out.get("git_commits") or 0
    with_commits = out.get("sessions_with_commits") or 0
    weeks = days / 7 if days else 0
    per_week = round(commits / weeks, 1) if weeks else None
    thr = {"min_window_days": _BADGE_SHIPPING_MIN_WINDOW_DAYS,
           "commits_per_week": _BADGE_SHIPPING_COMMITS_PER_WEEK,
           "min_sessions_with_commits": _BADGE_SHIPPING_MIN_SESSIONS_WITH_COMMITS}
    met = {"commits_per_week": per_week, "git_commits": commits,
           "window_days": days, "sessions_with_commits": with_commits}
    if days < _BADGE_SHIPPING_MIN_WINDOW_DAYS:
        items.append(_badge("shipping_cadence", False, with_commits, met, thr,
                            reason="window shorter than 14 days"))
    else:
        items.append(_badge(
            "shipping_cadence",
            per_week is not None
            and per_week >= _BADGE_SHIPPING_COMMITS_PER_WEEK
            and with_commits >= _BADGE_SHIPPING_MIN_SESSIONS_WITH_COMMITS,
            with_commits, met, thr))

    # 6. cross_tool_orchestration — sustained multi-source parallel work.
    # "detected" fallback mirrors compute_ledger's sources_detected logic
    # for pre-"detected"-field JSON.
    full_tier = [
        s["source"] for s in (cross_llm or {}).get("sources") or []
        if s.get("coverage") == "full"
        and (s.get("detected", True) or (s.get("session_count") or 0) > 0)
    ]
    cwin = (cross_llm or {}).get("common_window")
    multi_hours = (((cross_llm or {}).get("parallel") or {})
                   .get("hours_multi_source") or 0)
    thr = {"min_full_tier_sources": 2,
           "min_window_days": _BADGE_ORCH_MIN_WINDOW_DAYS,
           "min_multi_hours": _BADGE_ORCH_MIN_MULTI_HOURS}
    met = {"full_tier_sources": sorted(full_tier),
           "hours_multi_source": multi_hours,
           "common_window_days": (cwin or {}).get("days")}
    if len(full_tier) < 2:
        items.append(_badge("cross_tool_orchestration", False, multi_hours,
                            met, thr, reason="fewer than 2 full-tier sources"))
    elif not cwin or cwin.get("degraded") or (cwin.get("days") or 0) < _BADGE_ORCH_MIN_WINDOW_DAYS:
        items.append(_badge("cross_tool_orchestration", False, multi_hours,
                            met, thr, reason="common window shorter than 14 days"))
    else:
        items.append(_badge(
            "cross_tool_orchestration",
            multi_hours >= _BADGE_ORCH_MIN_MULTI_HOURS,
            multi_hours, met, thr))

    return {"schema_version": 1,
            "standard_version": _BADGE_STANDARD_VERSION,
            "items": items}
```

Wire into `main()` — directly after `final["ledger"]["leaks"] = compute_leaks(...)` (~line 3177):

```python
    # badges: additive top-level block (Phase 3, spec §4). Reads the
    # already-computed scores/ledger/cross_llm; never mutates them.
    final["badges"] = compute_badges(
        final["scores"], final["ledger"], cross_llm, sessions, rated)
```

- [ ] **Step 4: Append the rubric section**

Append to `references/scoring-rubric.md`:

```markdown
## Badges (v1, provisional)

The badge layer (spec §4) publishes absolute thresholds; claims that clear
them may be displayed affirmatively in external report versions. Badges are
threshold-based, never percentile-based; unearned badges are silently absent
in external versions (never shown as "failed"). Bars are **provisional v1**
(spec §13) — revisit after the first real runs. Where a 9-dim analogue
exists, each bar equals that dimension's "score ≥ 8" band. Badge wording in
reports is fixed template text in `scripts/locales.py`, not LLM prose.
Computed by `compute_badges()` in `scripts/aggregate.py`; the full item list
(earned and unearned, with metrics and thresholds) ships in
`analysis-data.json` under the top-level `badges` block.

| Badge | Earned when | Minimum sample |
|---|---|---|
| `delegation` | Task-agent adoption ≥ 30% of sessions AND good-outcome rate on Task-agent sessions ≥ 70% | ≥ 15 rated Task-agent sessions |
| `root_cause` | D2 scored AND iterative-refinement-with-buggy-code co-occurrence ≤ 7% of rated sessions | ≥ 30 rated sessions |
| `tool_breadth` | MCP used in ≥ 15% of sessions AND top-3 built-in tools (Bash/Read/Edit) ≤ 55% of all tool calls | ≥ 30 sessions |
| `token_efficiency` | not-good/good token ratio ≤ 1.1 AND cache hit ≥ 80% | ≥ 30 rated sessions |
| `shipping_cadence` | git commits per active week ≥ 5 (evidence-backed ledger count) AND ≥ 10 sessions with commits | ledger window ≥ 14 days |
| `cross_tool_orchestration` | ≥ 2 full-tier sources detected AND common window ≥ 14 days (not degraded) AND ≥ 10 hours of multi-source parallel work | n = multi-source hours |
```

- [ ] **Step 5: Document the schema addition**

Append to `docs/SCHEMA-CHANGES.md` (above the maintenance footer):

```markdown
## 2026-07-15 — additive: `badges` top-level block (V5 Phase 3)

- `badges`: `{schema_version: 1, standard_version: "v1", items: [...]}` —
  six threshold-based badge entries in fixed order (`delegation`,
  `root_cause`, `tool_breadth`, `token_efficiency`, `shipping_cadence`,
  `cross_tool_orchestration`), each
  `{id, earned, n, metrics, thresholds}` plus optional `reason` when the
  badge could not be evaluated (below sample / dimension unscored /
  window too short). Bars live in `references/scoring-rubric.md`
  "## Badges (v1, provisional)". External report versions render
  earned-only; the JSON keeps unearned items so the standard is auditable.
- No existing fields changed or removed.
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/test_badges.py -q`
Expected: PASS (all)

Run: `python3 -m pytest tests/ -q`
Expected: only the 2 known-baseline failures in `tests/test_build_html_additions.py`

- [ ] **Step 7: Commit**

```bash
git add scripts/aggregate.py references/scoring-rubric.md docs/SCHEMA-CHANGES.md tests/test_badges.py
git commit -m "feat(aggregate): badge layer — compute_badges with provisional v1 bars"
```

---

### Task 2: history snapshot enrichment + `read_history_snapshots()`

**Files:**
- Modify: `scripts/build_html.py` (`append_history_snapshot()` ~line 55; new `read_history_snapshots()`; `main()` reads history and passes `history_entries` into `report_render.render()`)
- Modify: `scripts/report_render.py` (only the `render()` signature: new keyword param `history_entries: list = None` — consumed by Task 3)
- Modify: `docs/SCHEMA-CHANGES.md`
- Test: `tests/test_history_snapshot.py` (extend)

**Interfaces:**
- Consumes: `analysis["badges"]["items"]` from Task 1.
- Produces: `read_history_snapshots(history_path) -> list[dict]` — sorted ascending by `date`, corrupt/dateless lines skipped, deduped by date (last line per date wins), entries with unparseable dates skipped. Snapshot lines gain two additive fields: `overall_avg` (float or None) and `badges` now populated with earned badge ids (was always `[]`). Task 3's renderer consumes exactly this list.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_history_snapshot.py`)

```python
from build_html import read_history_snapshots  # add to imports at top

ANALYSIS_WITH_BADGES = {
    "meta": {"total_sessions": 12},
    "scores": {"D1_delegation": {"score": 7},
               "_overall": {"avg": 6.1, "dimensions_scored": 9,
                            "dimensions_total": 9}},
    "ledger": {"schema_version": 1,
               "output": {"git_commits": 9, "git_pushes": 4,
                          "sessions_with_commits": 5},
               "sources_detected": ["claude"]},
    "badges": {"schema_version": 1, "standard_version": "v1",
               "items": [
                   {"id": "delegation", "earned": True, "n": 20,
                    "metrics": {}, "thresholds": {}},
                   {"id": "root_cause", "earned": False, "n": 40,
                    "metrics": {}, "thresholds": {}},
               ]},
}


class SnapshotBadgeTests(unittest.TestCase):
    def test_snapshot_records_earned_badge_ids_and_overall(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "h.jsonl"
            append_history_snapshot(hist, ANALYSIS_WITH_BADGES, "self")
            entry = json.loads(hist.read_text().strip())
            self.assertEqual(entry["badges"], ["delegation"])
            self.assertEqual(entry["overall_avg"], 6.1)

    def test_snapshot_without_badges_block_is_empty_list(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "h.jsonl"
            append_history_snapshot(hist, ANALYSIS, "self")
            entry = json.loads(hist.read_text().strip())
            self.assertEqual(entry["badges"], [])


class ReadHistoryTests(unittest.TestCase):
    def test_reads_sorted_skips_corrupt_dedupes_by_date(self):
        with tempfile.TemporaryDirectory() as td:
            hist = Path(td) / "h.jsonl"
            lines = [
                json.dumps({"date": "2026-07-01", "schema_version": 1,
                            "ledger": {"git_commits": 1}}),
                "{not json",
                json.dumps({"no_date_key": True}),
                json.dumps({"date": "2026-05-01", "schema_version": 1}),
                json.dumps({"date": "not-a-date", "schema_version": 1}),
                # same-date rerun: last line must win
                json.dumps({"date": "2026-07-01", "schema_version": 1,
                            "ledger": {"git_commits": 2}}),
            ]
            hist.write_text("\n".join(lines) + "\n")
            entries = read_history_snapshots(hist)
            self.assertEqual([e["date"] for e in entries],
                             ["2026-05-01", "2026-07-01"])
            self.assertEqual(entries[1]["ledger"]["git_commits"], 2)

    def test_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                read_history_snapshots(Path(td) / "nope.jsonl"), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_history_snapshot.py -q`
Expected: FAIL with `ImportError: cannot import name 'read_history_snapshots'`

- [ ] **Step 3: Implement**

In `scripts/build_html.py`, add `from datetime import date` is already imported; extend `append_history_snapshot()` — replace the `entry = {...}` block:

```python
        badges_block = analysis.get("badges") or {}
        earned = [b.get("id") for b in (badges_block.get("items") or [])
                  if isinstance(b, dict) and b.get("earned") and b.get("id")]
        overall_avg = ((analysis.get("scores") or {}).get("_overall") or {}).get("avg")
        entry = {
            "date": date.today().isoformat(),
            "schema_version": 1,
            "scores": scores,
            # additive since Phase 3: mean of scored dims at snapshot time —
            # older lines lack it; readers fall back to mean(scores.values()).
            "overall_avg": overall_avg,
            "badges": earned,
            "ledger": {
                "git_commits": (ledger.get("output") or {}).get("git_commits"),
                "sessions": (analysis.get("meta") or {}).get("total_sessions"),
                "sources_detected": ledger.get("sources_detected") or [],
                "leaks": leaks,
            },
        }
```

Add the reader (below `append_history_snapshot`):

```python
def read_history_snapshots(history_path):
    """Load trend snapshots for the trend ledger (Phase 3).

    Tolerates corrupt lines (spec §7: skip on read). Entries are deduped
    by date — the LAST line for a given date wins, so re-running a report
    the same day doesn't fake trend progress — and returned sorted
    ascending by date. Entries without a parseable ISO date are skipped.
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
        by_date[d] = entry
    return [by_date[d] for d in sorted(by_date)]
```

In `main()`, before the `report_render.render(` call:

```python
    history_entries = read_history_snapshots(Path(args.history_file))
```

and pass `history_entries=history_entries,` into `render(...)` (after `ledger_narration_md=...`). Note the read happens before `append_history_snapshot()` runs at the end of `main()`, so "last run" in the report is genuinely the previous build, not this one.

In `scripts/report_render.py`, extend the `render()` signature (~line 2869) with `history_entries: list = None,` and add to the docstring: `history_entries: Trend snapshots from read_history_snapshots() (SELF trend ledger; ignored for HR).` The parameter is unused until Task 3 — that's fine, it keeps this task's diff shippable.

- [ ] **Step 4: Document the snapshot change**

Append to `docs/SCHEMA-CHANGES.md`:

```markdown
## 2026-07-15 — additive: snapshot `overall_avg` + populated `badges` (V5 Phase 3)

- `autopsy-history.jsonl` snapshot lines gain `overall_avg` (float or null:
  `scores._overall.avg` at snapshot time). Lines from before this change
  lack the key — readers fall back to the mean of the per-dim `scores` map.
- The snapshot `badges` field (present since Phase 1, always `[]`) is now
  populated with **earned badge ids** (list of strings). Shape unchanged.
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_history_snapshot.py tests/smoke_test.py -q`
Expected: PASS (smoke still writes exactly 1 snapshot line)

- [ ] **Step 6: Commit**

```bash
git add scripts/build_html.py scripts/report_render.py docs/SCHEMA-CHANGES.md tests/test_history_snapshot.py
git commit -m "feat(build): snapshot badges/overall_avg + corrupt-tolerant history reader"
```

---

### Task 3: trend ledger renderer (SELF book 4)

**Files:**
- Modify: `scripts/report_render.py` (`_TREND_MIN_SNAPSHOTS`, `_sparkline_svg()`, `_entry_overall()`, `_entry_leak_cost()`, `_current_trend_values()`, `_pick_reference()`, `_build_trend_ledger()`; `_parse_ledger_narration` gains `trend-ledger` book; `_build_opening_band` gains `include_trend_finding`; `render()` builds the section; CSS)
- Modify: `scripts/locales.py` (trend + habit-drift keys, both locales)
- Modify: `tests/test_ledger_render.py` (narration equality test gains the new key)
- Test: `tests/test_trend_render.py` (create)

**Interfaces:**
- Consumes: `history_entries` list from Task 2; `analysis["badges"]` from Task 1; `blind_spots["habit_drift"]` (`{gate_passed, metrics: {weeks, early_median_len, late_median_len, early_good_rate, late_good_rate}}`, Phase 2).
- Produces: `_build_trend_ledger(analysis, history_entries, narration, locale, exhibit_no, blind_spots) -> str` (section `id="ledger-trend"`); `_sparkline_svg(values, width=120, height=28) -> str`; narration book key `"trend-ledger"`; `_build_opening_band(..., include_trend_finding=False)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trend_render.py
"""Trend ledger (spec §3 book 4): locked below 3 snapshots, comparison
table + sparklines when unlocked, habit-drift opener, narration book."""
import re
import sys
import unittest
from itertools import count
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from report_render import (  # noqa: E402
    _build_opening_band, _build_trend_ledger, _parse_ledger_narration,
    _sparkline_svg)


def _entry(d, commits=5, sessions=50, overall=6.0, badges=("delegation",),
           leaks=None):
    return {"date": d, "schema_version": 1,
            "scores": {"D1_delegation": 7},
            "overall_avg": overall,
            "badges": list(badges),
            "ledger": {"git_commits": commits, "sessions": sessions,
                       "sources_detected": ["claude"],
                       "leaks": leaks if leaks is not None else [
                           {"type": "repeated_instructions",
                            "weekly_cost_usd": 1.5, "weekly_tokens": 40000,
                            "occurrences": 6}]}}


ANALYSIS = {
    "meta": {"total_sessions": 61},
    "scores": {"_overall": {"avg": 6.4, "dimensions_scored": 9,
                            "dimensions_total": 9}},
    "ledger": {"window": {"start": "2026-06-01", "end": "2026-07-10",
                          "days": 39},
               "output": {"git_commits": 44, "git_pushes": 12,
                          "sessions_with_commits": 18},
               "leaks": {"window_weeks": 5.6, "items": [
                   {"type": "sunk_cost", "weekly_cost_usd": 2.25,
                    "weekly_tokens": 60000, "occurrences": 3,
                    "evidence": ["sid-secret-1"]}]}},
    "badges": {"schema_version": 1, "standard_version": "v1", "items": [
        {"id": "delegation", "earned": True, "n": 20, "metrics": {},
         "thresholds": {}},
        {"id": "root_cause", "earned": False, "n": 40, "metrics": {},
         "thresholds": {}}]},
}

DRIFT_PASSED = {"habit_drift": {
    "id": "habit_drift", "gate_passed": True, "suppressed_by_guard": False,
    "n": 10, "metrics": {"weeks": 10, "early_median_len": 180,
                         "late_median_len": 90, "early_good_rate": 68.0,
                         "late_good_rate": 61.0}, "reason": None}}
DRIFT_GATED = {"habit_drift": {
    "id": "habit_drift", "gate_passed": False, "suppressed_by_guard": False,
    "n": 3, "metrics": {}, "reason": "fewer than 8 weeks"}}

ENTRIES_3 = [_entry("2026-04-05", commits=20, overall=5.5),
             _entry("2026-05-20", commits=30, overall=5.9),
             _entry("2026-07-01", commits=38, overall=6.2)]


def build(entries, blind_spots=DRIFT_GATED, narration="", locale="en"):
    return _build_trend_ledger(ANALYSIS, entries,
                               _parse_ledger_narration(narration),
                               locale, count(7), blind_spots)


class LockedStateTests(unittest.TestCase):
    def test_locked_below_three_snapshots(self):
        html = build(ENTRIES_3[:2])
        self.assertIn('id="ledger-trend"', html)
        # "unlocks after 1 more run" — no table, no exhibit
        self.assertIn("1", html)
        self.assertNotIn("c-exhibit", html)
        self.assertNotIn("<table", html)

    def test_locked_message_counts_remaining_runs(self):
        html = build([])
        self.assertIn("3", html)


class UnlockedTests(unittest.TestCase):
    def test_three_snapshots_render_table_and_sparklines(self):
        html = build(ENTRIES_3)
        self.assertIn("c-exhibit", html)
        self.assertIn("<svg", html)
        # this-run values from live analysis
        self.assertIn("44", html)     # commits this run
        self.assertIn("6.4", html)    # overall this run
        # last-run column from newest snapshot
        self.assertIn("2026-07-01", html)

    def test_reference_column_picks_entry_closest_to_90_days(self):
        html = build(ENTRIES_3)
        # newest 2026-07-01 − 90d = 2026-04-02 → 2026-04-05 wins over 2026-05-20
        self.assertIn("2026-04-05", html)

    def test_history_leak_cost_read_from_compact_list_shape(self):
        html = build(ENTRIES_3)
        self.assertIn("1.50", html)   # history compact-list sum
        self.assertIn("2.25", html)   # this-run dict-shape sum

    def test_no_session_ids_leak(self):
        self.assertNotIn("sid-secret-1", build(ENTRIES_3))

    def test_drift_opener_when_gate_passed(self):
        html = build(ENTRIES_3, blind_spots=DRIFT_PASSED)
        self.assertIn("c-blindspot", html)
        self.assertIn("180", html)
        self.assertIn("90", html)

    def test_no_drift_opener_when_gated(self):
        self.assertNotIn("c-blindspot", build(ENTRIES_3, blind_spots=DRIFT_GATED))

    def test_narration_title_and_prose(self):
        md = "# trend-ledger\nCommits per run rose 2.2x over three months.\n\nBody prose."
        html = build(ENTRIES_3, narration=md)
        self.assertIn("Commits per run rose 2.2x over three months.", html)
        self.assertIn("Body prose.", html)

    def test_zh_locale_renders(self):
        html = build(ENTRIES_3, locale="zh_TW")
        self.assertIn('id="ledger-trend"', html)
        self.assertNotIn("—", html)


class NarrationBookTests(unittest.TestCase):
    def test_trend_book_parsed(self):
        d = _parse_ledger_narration("# trend-ledger\nClaim T.\n")
        self.assertEqual(d["trend-ledger"], "Claim T.")


class OpeningBandTrendTests(unittest.TestCase):
    LEDGER = {"window": {"start": "2026-06-01", "end": "2026-07-10",
                         "days": 39},
              "output": {"git_commits": 44, "git_pushes": 12,
                         "sessions_with_commits": 18}}
    NARR = _parse_ledger_narration(
        "# output-ledger\nO claim.\n# trend-ledger\nT claim.\n")

    def test_trend_claim_included_when_flag_true(self):
        html = _build_opening_band(self.LEDGER, self.NARR, "en",
                                   include_trend_finding=True)
        self.assertIn("T claim.", html)

    def test_trend_claim_suppressed_by_default(self):
        html = _build_opening_band(self.LEDGER, self.NARR, "en")
        self.assertNotIn("T claim.", html)


class SparklineTests(unittest.TestCase):
    def test_polyline_with_points(self):
        svg = _sparkline_svg([1, 2, 3])
        self.assertIn("<svg", svg)
        self.assertIn("polyline", svg)

    def test_fewer_than_two_numbers_empty(self):
        self.assertEqual(_sparkline_svg([5]), "")
        self.assertEqual(_sparkline_svg([None, None]), "")

    def test_none_values_skipped_not_crash(self):
        svg = _sparkline_svg([1, None, 3])
        self.assertIn("polyline", svg)

    def test_flat_series_no_zero_division(self):
        self.assertIn("polyline", _sparkline_svg([2, 2, 2]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_trend_render.py -q`
Expected: FAIL with `ImportError: cannot import name '_build_trend_ledger'`

- [ ] **Step 3: Add locale keys** (`scripts/locales.py`, BOTH dicts; zh_TW natively authored, no em-dash)

en additions (place after the Phase 2 leak-ledger key block):

```python
        # --- Phase 3: trend ledger (SELF book 4) ---
        "ledger_trend_kicker": "Trend ledger",
        "ledger_trend_title": "Key ledger numbers, this run against your own history",
        "ledger_trend_locked_template": "The trend ledger unlocks after {n} more report run(s). Each successful self-report appends one snapshot to autopsy-history.jsonl; three snapshots are needed before trends mean anything.",
        "ledger_trend_exhibit_title": "This run vs last run vs ~3 months ago",
        "ledger_source_trend": "autopsy-history.jsonl snapshots + this run's analysis-data.json",
        "ledger_trend_col_metric": "Metric",
        "ledger_trend_col_this": "This run",
        "ledger_trend_col_prev_template": "Last run ({date})",
        "ledger_trend_col_ref_template": "{date}",
        "ledger_trend_col_spark": "All snapshots",
        "ledger_trend_row_overall": "Overall score (avg of scored dims)",
        "ledger_trend_row_commits": "Git commits in window",
        "ledger_trend_row_sessions": "Sessions analyzed",
        "ledger_trend_row_leak_cost": "Leak cost, USD per week (lower-bound)",
        "ledger_trend_row_badges": "Badges earned",
        "ledger_trend_na": "n/a",
        "blindspot_drift_title": "Habit drift",
        "blindspot_drift_template": "Across {weeks} plottable weeks, your median first-prompt length fell from {early} to {late} characters while the good-outcome rate went from {early_rate}% to {late_rate}%. Shorter instructions are not being paid back with equal outcomes.",
```

zh_TW additions:

```python
        # --- Phase 3: 趨勢帳（SELF 第 4 本帳） ---
        "ledger_trend_kicker": "趨勢帳",
        "ledger_trend_title": "關鍵帳面數字，這一次對照你自己的歷史",
        "ledger_trend_locked_template": "趨勢帳還需要 {n} 次報告執行才會解鎖。每次成功產出自用版報告會在 autopsy-history.jsonl 追加一筆快照，累積三筆之後趨勢才有意義。",
        "ledger_trend_exhibit_title": "本次、上次、約三個月前的對照",
        "ledger_source_trend": "autopsy-history.jsonl 快照＋本次 analysis-data.json",
        "ledger_trend_col_metric": "指標",
        "ledger_trend_col_this": "本次",
        "ledger_trend_col_prev_template": "上次（{date}）",
        "ledger_trend_col_ref_template": "{date}",
        "ledger_trend_col_spark": "全部快照",
        "ledger_trend_row_overall": "總分（已評分維度平均）",
        "ledger_trend_row_commits": "視窗內 git commits",
        "ledger_trend_row_sessions": "分析的 session 數",
        "ledger_trend_row_leak_cost": "漏水成本，每週美元（下限值）",
        "ledger_trend_row_badges": "拿到的徽章數",
        "ledger_trend_na": "n/a",
        "blindspot_drift_title": "習慣漂移",
        "blindspot_drift_template": "在 {weeks} 個可繪週裡，你的首則指令中位長度從 {early} 字元縮到 {late} 字元，良好結果率從 {early_rate}% 變成 {late_rate}%。指令變短並沒有換到等值的結果。",
```

- [ ] **Step 4: Implement the renderer**

In `scripts/report_render.py`:

(a) `_parse_ledger_narration` (~line 306): add `"trend-ledger": ""` to the `books` dict and mention it in the docstring. Update `tests/test_ledger_render.py::NarrationParseTests::test_missing_sections_empty` expected dict to include `"trend-ledger": ""`.

(b) `_build_opening_band` (~line 349): add keyword param `include_trend_finding=False`; extend the book loop:

```python
    for book in ("output-ledger", "team-ledger", "leak-ledger", "trend-ledger"):
        if book == "leak-ledger" and not include_leak_finding:
            continue
        if book == "trend-ledger" and not include_trend_finding:
            continue
```

and extend its docstring: the trend claim renders only when the trend section itself is unlocked (same never-fabricate rule as the leak flag).

(c) New helpers + builder (place after `_build_leak_ledger`):

```python
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
```

Imports: `report_render.py` must import `date` and `timedelta` from `datetime` (check the existing import line and extend it).

(d) Wire into `render()` — inside the `if audience == "self":` ledger block (~line 3650), after the leak-ledger call:

```python
        trend_unlocked = len(history_entries or []) >= _TREND_MIN_SNAPSHOTS
```

Pass `include_trend_finding=trend_unlocked` into the `_build_opening_band(...)` call, and after `_build_leak_ledger(...)`:

```python
        if ledger_block:
            ledger_sections += _build_trend_ledger(
                analysis, history_entries, ledger_narration, locale,
                exhibit_no, blind_spots)
```

(e) CSS — add next to the Phase 2 `.c-leak-*` rules (~line 2195):

```css
  .c-trend-locked { font-size: 13px; opacity: 0.75; margin: 6px 0 0; }
  .c-trend-table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  .c-trend-table th, .c-trend-table td { text-align: right; padding: 6px 10px;
                     border-bottom: 1px solid rgba(128,128,128,0.25); font-size: 13px; }
  .c-trend-table th:first-child, .c-trend-table td:first-child { text-align: left; }
  .c-trend-table thead th { font-size: 11px; letter-spacing: 0.05em;
                     text-transform: uppercase; opacity: 0.7; }
  .c-neg-num { color: #9C201A; }
  .c-spark { color: #B08A2E; vertical-align: middle; }
```

(If the direction-C block defines `--c-gold` / `--c-neg` CSS vars, use `var(--c-gold)` / `var(--c-neg)` instead of the literals — match whichever idiom `.c-leak-*` uses.)

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_trend_render.py tests/test_ledger_render.py tests/test_locales.py -q`
Expected: PASS

Run: `python3 -m pytest tests/ -q`
Expected: only the 2 known-baseline failures

- [ ] **Step 6: Commit**

```bash
git add scripts/report_render.py scripts/locales.py tests/test_trend_render.py tests/test_ledger_render.py
git commit -m "feat(render): trend ledger book — unlock gate, comparison exhibit, SVG sparklines, drift opener"
```

---

### Task 4: badge section + recruiter version rebuild (HR)

**Files:**
- Modify: `scripts/report_render.py` (`_build_badges_section()`, `_build_hr_output_ledger()`, HR branch demolition in `render()`, `$badges_section` template slot, scope-disclosure method footer, HR TOC, case-study numbering, CSS)
- Modify: `scripts/locales.py` (badge/HR keys added; dead keys removed from BOTH locales)
- Modify: `tests/smoke_test.py` (HR invariants updated)
- Test: `tests/test_hr_recruiter.py` (create)

**Interfaces:**
- Consumes: `analysis["badges"]` (Task 1 shape).
- Produces: `_build_badges_section(badges: dict, window: dict, locale) -> str` (earned-only; `""` when nothing earned; section `id="badges"`); `_build_hr_output_ledger(ledger, shipped, artifacts_list, is_public, locale) -> str` (section `id="hr-output"`). HR layout = identity card → hero → badges → output ledger → case study → scope disclosure. NOTHING ELSE (spec §4 v1 scope).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hr_recruiter.py
"""Recruiter version v1 (spec §4): identity -> earned badges -> output
ledger (allowlist-filtered) -> case study -> scope disclosure. The V4 HR
blocks (profile card, memo peer review, 4-signal scores, trends, zone map,
self-awareness caveat) must be gone. Privacy: earned-only badges, no sids,
no non-allowlisted project names."""
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import narrative_en  # noqa: E402
from report_render import render, _build_badges_section  # noqa: E402


def _analysis(badges_items):
    return {
        "meta": {"total_sessions": 61, "facets_coverage_pct": 80.0,
                 "date_range": {"first": "2026-06-01T00:00:00Z",
                                "last": "2026-07-10T00:00:00Z"}},
        "aggregates": {
            "tokens": {"total": 1_000_000},
            "projects": {"public-repo": {"sessions": 30, "friction": 2,
                                         "commits": 25, "duration_min": 900,
                                         "label": "public-repo"},
                         "secret-client": {"sessions": 31, "friction": 3,
                                           "commits": 19, "duration_min": 800,
                                           "label": "secret-client"}},
            "weekly": [], "heatmap": {}, "outcomes": {}, "session_types": {},
            "friction": {"totals": {}}, "tools": {"totals": {}},
            "prompt_len_vs_outcome": {}, "helpfulness": {},
            "growth_curve": [], "activity": {},
            "profile_summary": {"scale_tier": "heavy", "total_sessions": 61,
                                "total_duration_hr": 28.0,
                                "project_count_active": 2,
                                "date_span_days": 40, "ta_pct": 40.0,
                                "mcp_pct": 20.0, "specialty": "",
                                "top_project_share_pct": 50.0},
            "shipped_artifacts": [
                {"project": "public-repo", "summary": "Shipped a CLI tool",
                 "project_sessions": 30, "project_duration_min": 900,
                 "project_commits": 25, "total_tokens": 500_000},
                {"project": "secret-client", "summary": "SECRET-WORK-SUMMARY",
                 "project_sessions": 31, "project_duration_min": 800,
                 "project_commits": 19, "total_tokens": 400_000},
            ],
            "efficiency": {"commits_per_hour": 1.5},
        },
        "scores": {"_overall": {"avg": 6.4, "dimensions_scored": 9,
                                "dimensions_total": 9}},
        "ledger": {"window": {"start": "2026-06-01", "end": "2026-07-10",
                              "days": 39},
                   "output": {"git_commits": 44, "git_pushes": 12,
                              "sessions_with_commits": 18}},
        "badges": {"schema_version": 1, "standard_version": "v1",
                   "items": badges_items},
    }


EARNED = {"id": "delegation", "earned": True, "n": 20,
          "metrics": {"ta_rate_pct": 45.0, "good_rate_with_ta_pct": 75.0},
          "thresholds": {"min_ta_rated": 15, "ta_rate_pct": 30.0,
                         "good_rate_with_ta_pct": 70.0}}
UNEARNED = {"id": "root_cause", "earned": False, "n": 40,
            "metrics": {"iter_buggy_pct": 12.0},
            "thresholds": {"min_rated": 30, "max_iter_buggy_pct": 7.0}}


def _render_hr(badges_items, **kw):
    return render(
        analysis=_analysis(badges_items), samples_data={},
        peer_review_md="MEMO-BODY-MUST-NOT-RENDER", locale="en",
        audience="hr", narrative=narrative_en,
        profile_info={"name": "Jane Doe", "role": "QA lead"},
        public_set={"public-repo"}, category_map={},
        case_study_md="## Case\nA redacted case study.", **kw)


class HrLayoutTests(unittest.TestCase):
    def test_five_block_layout_present(self):
        html = _render_hr([EARNED, UNEARNED])
        self.assertIn('id="badges"', html)
        self.assertIn('id="hr-output"', html)
        self.assertIn('id="case-study"', html)
        self.assertIn('id="method"', html)
        self.assertIn("Jane Doe", html)

    def test_v4_blocks_demolished(self):
        html = _render_hr([EARNED])
        self.assertNotIn('id="scores"', html)
        self.assertNotIn('id="peer-review-section"', html)
        self.assertNotIn('id="trends"', html)
        self.assertNotIn("profile-card", html)
        self.assertNotIn("zone-map", html)
        self.assertNotIn("MEMO-BODY-MUST-NOT-RENDER", html)

    def test_no_ledger_sections_in_hr(self):
        self.assertNotIn('id="ledger-', _render_hr([EARNED]))


class BadgeRenderTests(unittest.TestCase):
    def test_earned_only(self):
        html = _render_hr([EARNED, UNEARNED])
        self.assertIn("Delegation", html)
        self.assertNotIn("Root-cause", html)
        # never render "failed"/unearned wording
        self.assertNotIn("not earned", html.lower())

    def test_zero_earned_suppresses_section(self):
        html = _render_hr([UNEARNED])
        self.assertNotIn('id="badges"', html)

    def test_criteria_line_carries_numbers(self):
        html = _render_hr([EARNED])
        self.assertIn("45", html)   # metric
        self.assertIn("30", html)   # bar
        self.assertIn("20", html)   # n

    def test_builder_empty_on_no_badges_block(self):
        self.assertEqual(_build_badges_section({}, {}, "en"), "")


class HrOutputLedgerTests(unittest.TestCase):
    def test_allowlist_filtering(self):
        html = _render_hr([EARNED])
        self.assertIn("public-repo", html)
        self.assertNotIn("secret-client", html)
        self.assertNotIn("SECRET-WORK-SUMMARY", html)

    def test_output_counters_render(self):
        html = _render_hr([EARNED])
        self.assertIn("44", html)


class ScopeDisclosureTests(unittest.TestCase):
    def test_scope_disclosure_names_standard_and_repro(self):
        html = _render_hr([EARNED, UNEARNED])
        self.assertIn("v1", html)
        self.assertIn("scoring-rubric.md", html)

    def test_self_awareness_caveat_gone(self):
        from locales import STRINGS
        self.assertNotIn("hr_self_awareness_caveat", STRINGS["en"])


class SelfUnaffectedTests(unittest.TestCase):
    def test_self_never_renders_badge_section(self):
        html = render(
            analysis=_analysis([EARNED]), samples_data={},
            peer_review_md="", locale="en", audience="self",
            narrative=narrative_en)
        self.assertNotIn('id="badges"', html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_hr_recruiter.py -q`
Expected: FAIL with `ImportError: cannot import name '_build_badges_section'`

- [ ] **Step 3: Add locale keys** (BOTH locales)

en:

```python
        # --- Phase 3: badge layer (external versions) ---
        "hr_badges_h": "§ HR-01 · Earned badges",
        "hr_badges_subtitle": "Claims that cleared published thresholds",
        "hr_badges_method": "Each badge is an absolute, published threshold from the cc-user-autopsy standard (references/scoring-rubric.md). Badges below their bar or below minimum sample are simply absent. No percentile or population claim is made.",
        "badge_evidence_template": "n = {n} · window {start} → {end}",
        "badge_delegation_name": "Delegation",
        "badge_delegation_criteria": "Task-agent adoption {ta}% (bar ≥ {bar_ta}%) · good-outcome rate on delegated sessions {good}% (bar ≥ {bar_good}%)",
        "badge_root_cause_name": "Root-cause debugging",
        "badge_root_cause_criteria": "Iterative-refinement-with-buggy-code sessions {pct}% of rated pool (bar ≤ {bar}%)",
        "badge_tool_breadth_name": "Tool breadth",
        "badge_tool_breadth_criteria": "MCP used in {mcp}% of sessions (bar ≥ {bar_mcp}%) · top-3 built-in tools {top3}% of calls (bar ≤ {bar_top3}%)",
        "badge_token_efficiency_name": "Token efficiency",
        "badge_token_efficiency_criteria": "Failed-vs-good token ratio {ratio}× (bar ≤ {bar_ratio}×) · cache hit {cache}% (bar ≥ {bar_cache}%)",
        "badge_shipping_cadence_name": "Shipping cadence",
        "badge_shipping_cadence_criteria": "{per_week} git commits per active week (bar ≥ {bar}) · {n} sessions with commits",
        "badge_cross_tool_orchestration_name": "Cross-tool orchestration",
        "badge_cross_tool_orchestration_criteria": "{hours} hours of multi-source parallel work in a {days}-day common window (bar ≥ {bar} h, ≥ 2 full-tier sources)",
        # --- Phase 3: HR output ledger + scope disclosure ---
        "hr_output_h": "§ HR-02 · Output ledger",
        "hr_output_subtitle": "Evidence-backed deliverables, allowlisted projects only",
        "hr_output_method": "Counts come from the local transcript pool; only projects the subject explicitly allowlisted appear by name. Everything else is excluded from this version entirely.",
        "hr_output_commits": "git commits in window",
        "hr_output_pushes": "git pushes",
        "hr_output_sessions_with_commits": "sessions with ≥1 commit",
        "toc_hr_badges": "Badges",
        "toc_hr_output": "Output ledger",
        "hr_scope_h": "Methodology & scope",
        "hr_scope_body_template": "Produced by the public cc-user-autopsy standard, version {version}. {total} badge criteria were assessed against the subject's local Claude Code data; {earned} cleared their published thresholds and are shown above — badges not shown were not earned or lacked sample. Criteria and minimum sample sizes are published in references/scoring-rubric.md in the same repository; anyone can run the same skill on their own data to reproduce this assessment. Session identifiers and non-allowlisted project names are excluded by a default-deny privacy model.",
```

zh_TW（natively authored；不用破折號）:

```python
        # --- Phase 3: 徽章層（對外版） ---
        "hr_badges_h": "§ HR-01 · 取得的徽章",
        "hr_badges_subtitle": "通過公開門檻的主張",
        "hr_badges_method": "每一枚徽章都是 cc-user-autopsy 標準（references/scoring-rubric.md）裡白紙黑字的絕對門檻。沒過門檻或樣本不足的徽章直接不出現。本報告不做任何百分位或母體比較宣稱。",
        "badge_evidence_template": "n = {n} · 資料窗 {start} → {end}",
        "badge_delegation_name": "分派委任",
        "badge_delegation_criteria": "Task agent 使用率 {ta}%（門檻 ≥ {bar_ta}%）· 委任 session 良好結果率 {good}%（門檻 ≥ {bar_good}%）",
        "badge_root_cause_name": "根因除錯",
        "badge_root_cause_criteria": "迭代修補且帶 buggy code 摩擦的 session 佔已評分 {pct}%（門檻 ≤ {bar}%）",
        "badge_tool_breadth_name": "工具廣度",
        "badge_tool_breadth_criteria": "{mcp}% 的 session 用了 MCP（門檻 ≥ {bar_mcp}%）· 前三大內建工具佔 {top3}% 呼叫（門檻 ≤ {bar_top3}%）",
        "badge_token_efficiency_name": "Token 效率",
        "badge_token_efficiency_criteria": "失敗對良好 token 比 {ratio} 倍（門檻 ≤ {bar_ratio} 倍）· 快取命中 {cache}%（門檻 ≥ {bar_cache}%）",
        "badge_shipping_cadence_name": "出貨節奏",
        "badge_shipping_cadence_criteria": "每活躍週 {per_week} 個 git commits（門檻 ≥ {bar}）· {n} 個 session 有 commit",
        "badge_cross_tool_orchestration_name": "跨工具並行",
        "badge_cross_tool_orchestration_criteria": "共同資料窗 {days} 天內 {hours} 小時多來源並行（門檻 ≥ {bar} 小時，且 ≥ 2 個完整層級來源）",
        # --- Phase 3: HR 產出帳＋方法揭露 ---
        "hr_output_h": "§ HR-02 · 產出帳",
        "hr_output_subtitle": "有證據支持的交付物，只列允許公開的專案",
        "hr_output_method": "計數來自本機 transcript 資料池；只有當事人明確允許公開的專案會以名稱出現，其餘一律不進這個版本。",
        "hr_output_commits": "資料窗內 git commits",
        "hr_output_pushes": "git pushes",
        "hr_output_sessions_with_commits": "有 commit 的 session 數",
        "toc_hr_badges": "徽章",
        "toc_hr_output": "產出帳",
        "hr_scope_h": "方法與範圍",
        "hr_scope_body_template": "本報告由公開的 cc-user-autopsy 標準（版本 {version}）產出。共評估 {total} 項徽章準則，其中 {earned} 項通過公開門檻並顯示於上方；未顯示的徽章即未通過或樣本不足。準則與最低樣本數公開在同一 repo 的 references/scoring-rubric.md，任何人都能用同一套 skill 對自己的資料重跑驗證。Session 識別碼與未列入允許清單的專案名稱依預設拒絕的隱私模型一律排除。",
```

Dead-key removal — for EACH candidate below, first `grep -rn "<key>" scripts/ tests/ SKILL.md` ; remove from BOTH locale dicts only if the renderer reference disappears in this task, and update any test that asserted it (the 2 known-baseline failures in `test_build_html_additions.py` stay failing — do not fix, do not worsen). Candidates: `hr_self_awareness_caveat`, `hr_profile_scale_label`, `hr_profile_velocity_label`, `hr_profile_parallel_label`, `hr_profile_tool_breadth_label`, `hr_profile_self_audit_label`, `hr_profile_focus_label`, `hr_profile_top_project_share`, `hr_profile_sessions_unit`, `profile_sub_commits_per_hour`, `profile_sub_task_agent_adoption`, `profile_sub_mcp_sessions`, `hr_section_scoring_h`, `hr_section_scoring_subtitle`, `hr_section_scoring_method`, `toc_hr_peer_review`, `toc_hr_scores`, `toc_hr_trends`, `toc_hr_method`, `hr_method_disclosure_h`, `hr_method_disclosure_body`, `plain_zone_when`, `plain_zone_when_desc`, `plain_zone_when_dims`, `plain_zone_how`, `plain_zone_how_desc`, `plain_zone_how_dims`, `plain_zone_what`, `plain_zone_what_desc`, `plain_zone_what_dims`, `plain_zone_cost`, `plain_zone_cost_desc`, `plain_zone_cost_dims`, `section_relationships`, `section_relationships_subtitle`, `relationships_flow_caption`, `how_to_read_summary` + every `how_to_read_*` key, `hr_shipped_h`, `hr_shipped_subtitle`, `hr_shipped_method`, `hr_shipped_privacy_note_allowlist`, `hr_shipped_privacy_note_anonymised`, `hr_shipped_proj_sub_template`, `hr_shipped_commits_label`, `hr_shipped_top_session_tok`, `toc_hr_shipped`, `toc_hr_case_study`. Keys still referenced by surviving code (e.g. `hr_artifacts_*` if reused inside the new output ledger, `hero_hr_*`, `benchmark_caveat`, `case_study_*`) are KEPT. When in doubt, keep the key and note it in implementation-notes rather than breaking a reference.

- [ ] **Step 4: Implement the builders** (place after `_build_trend_ledger`)

```python
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


def _build_badges_section(badges, window, locale):
    """Earned badges for external versions. Evidence pointer is
    privacy-safe by construction: sample size + window dates only."""
    items = [b for b in ((badges or {}).get("items") or [])
             if isinstance(b, dict) and b.get("earned")]
    if not items:
        return ""
    win = window or {}
    evidence_suffix = ""
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
    return ('<section id="badges">'
            f'<h2 class="sec" data-num="">{t(locale, "hr_badges_h")}</h2>'
            f'<h2 class="sec-title">{t(locale, "hr_badges_subtitle")}</h2>'
            f'<p class="method">{t(locale, "hr_badges_method")}</p>'
            f'<div class="c-badge-grid">{"".join(cards)}</div>'
            '</section>')


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

    shipped_items = ""
    for item in [s for s in (shipped or []) if is_public(s["project"])][:3]:
        dur_hr = item["project_duration_min"] / 60
        shipped_items += (
            '<div class="shipped-item"><div>'
            f'<div class="proj">{esc(item["project"])}</div>'
            f'<div class="proj-sub">{item["project_sessions"]} sessions · {dur_hr:.0f}h</div>'
            '</div>'
            f'<div class="desc">{esc(item["summary"])}</div>'
            f'<div class="stats">{item["project_commits"]} commits<br>'
            f'{fmt(item["total_tokens"])} tok</div></div>')
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

    return ('<section id="hr-output">'
            f'<h2 class="sec" data-num="">{t(locale, "hr_output_h")}</h2>'
            f'<h2 class="sec-title">{t(locale, "hr_output_subtitle")}</h2>'
            f'<p class="method">{t(locale, "hr_output_method")}</p>'
            f'{counters}{shipped_html}{artifact_rows}'
            '</section>')
```

Note: the shipped-item sub-line above inlines "sessions · h / commits / tok" chrome; reuse the existing `hr_shipped_proj_sub_template`, `hr_shipped_commits_label`, `hr_shipped_top_session_tok` keys instead if you keep them — pick ONE approach and make the locale-key removal list consistent with it.

- [ ] **Step 5: Rebuild the HR branch of `render()`**

In `render()`:

(a) Add near the top of the audience-conditional region:

```python
    badges_section = ""
    if audience == "hr":
        badges_section = _build_badges_section(
            analysis.get("badges"), (analysis.get("ledger") or {}).get("window"),
            locale)
```

(b) In the `if audience == "hr":` branch: keep `hero_block` (existing `hero_hr_*` keys) and the identity letterhead; set `profile_section = ""`, `hr_activity_block = ""`, `how_to_read_section = ""`; replace the shipped/artifacts builders with:

```python
        shipped_section = _build_hr_output_ledger(
            analysis.get("ledger"), shipped, artifacts_list, is_public, locale)
        artifacts_section = ""
```

TOC becomes:

```python
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
```

(c) HR must not render peer review, scores, zone map, patterns, trends:

- `diagnosis_block`: wrap the existing assembly in `if audience == "hr": diagnosis_block = ""` `else: <current f-string>`. Delete the `self_awareness_caveat_html` variable and the whole `if audience == "hr": scoring_h = ...` chrome branch (its keys are in the removal list).
- `plain_intro_block`: `"" if audience == "hr" else <current self reading-guide variant>` — delete the HR zone-map branch.
- `trends_section` subs entry: `"" if audience == "hr" else <current self variant>` — delete the HR growth-curve variant.
- `case_study_block`: change `cs_num = "§ HR-03" if audience == "hr" else "§ 05"`.
- `method_section` HR variant becomes the scope disclosure:

```python
        badge_items = (analysis.get("badges") or {}).get("items") or []
        earned_count = sum(1 for b in badge_items
                           if isinstance(b, dict) and b.get("earned"))
        std_version = (analysis.get("badges") or {}).get("standard_version", "v1")
        hr_method = (
            f'<section id="method" class="method-footer">'
            f'<h3 class="method-footer-h">{t(locale, "hr_scope_h")}</h3>'
            f'<p class="method-footer-body">'
            f'{t(locale, "hr_scope_body_template").format(version=esc(std_version), total=len(badge_items), earned=earned_count)}'
            f'</p></section>')
```

(d) Template: add `$badges_section` to `PAGE_TEMPLATE` on its own line directly after `$hero_block` (~line 2224), and add `"badges_section": badges_section,` to `subs`.

(e) Also delete now-dead HR code paths this demolition orphans (`profile_lede_html` / `weakest` computation if nothing else consumes them; the HR growth-curve/outcome-donut duplication) and run the Step 3 dead-key grep afterwards.

(f) CSS for badges (next to the trend CSS):

```css
  .c-badge-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; margin-top: 14px; }
  .c-badge { border: 1px solid rgba(128,128,128,0.3); border-top: 3px solid #B08A2E; padding: 12px 14px; }
  .c-badge-name { font-weight: 700; font-size: 15px; color: #7E6119; }
  .c-badge-criteria { font-size: 12.5px; margin-top: 6px; }
  .c-badge-evidence { font-size: 11.5px; opacity: 0.65; margin-top: 8px; font-variant-numeric: tabular-nums; }
```

- [ ] **Step 6: Update `tests/smoke_test.py` HR assertions**

Replace the stale HR assertions (`"Private project" in hr_html` and any that assume scores/peer-review/trends exist in HR) with:

```python
    # --- Phase 3 recruiter rebuild invariants ---
    assert 'id="hr-output"' in hr_html, "HR build missing output ledger"
    assert 'id="scores"' not in hr_html, "HR must not render the scoring grid"
    assert 'id="peer-review-section"' not in hr_html, "HR must not render peer review"
    assert 'id="trends"' not in hr_html, "HR must not render trend charts"
    assert "legacy-migration" not in hr_html, (
        "non-allowlisted demo project name leaked into HR output")
```

(`legacy-migration` is a `DEMO_GRAVEYARD_PROJECTS` name never allowlisted by the smoke's `--public-projects` fixture — verify what the smoke actually allowlists and pick a demo project name guaranteed outside it; if smoke passes no allowlist, assert on any `PROJECTS` name instead, since no-allowlist HR mode excludes every project name.) Badge presence in HR smoke is asserted conditionally in Task 5 after demo badges are made deterministic.

- [ ] **Step 7: Run tests**

Run: `python3 -m pytest tests/test_hr_recruiter.py tests/test_locales.py tests/smoke_test.py -q`
Expected: PASS

Run: `python3 -m pytest tests/ -q`
Expected: only the 2 known-baseline failures (re-check they are the SAME 2 — this task touches HR chrome those tests exercise; if one of them now fails differently, fix your regression, not their stale expectation)

- [ ] **Step 8: Commit**

```bash
git add scripts/report_render.py scripts/locales.py tests/test_hr_recruiter.py tests/smoke_test.py
git commit -m "feat(render): recruiter v1 rebuild — earned badges, output ledger, scope disclosure; V4 HR layout removed"
```

---

### Task 5: demo data + smoke trend/badge coverage + SKILL.md + docs

**Files:**
- Modify: `scripts/generate_demo_data.py` (`random.seed`, `gen_history_snapshots(now)`)
- Modify: `tests/test_demo_data.py` (history fixture + deterministic badge assertions)
- Modify: `tests/smoke_test.py` (seed history before SELF build; trend + badge assertions)
- Modify: `SKILL.md` (see step 5)

**Interfaces:**
- Consumes: everything above.
- Produces: `OUT_DIR / "autopsy-history.jsonl"` with 3 synthetic snapshots; deterministic demo (`random.seed`).

- [ ] **Step 1: Make the demo deterministic and add history snapshots**

At the top of `generate_demo_data.main()` add `random.seed(20260715)` (index-forced injections stay index-forced; the seed just freezes the random background so badge outcomes stop drifting run-to-run).

Add above `main()`:

```python
def gen_history_snapshots(now):
    """3 synthetic trend snapshots (~90/55/25 days before `now`) so the
    trend ledger unlocks on demo data. Compact-list leaks shape — the
    HISTORY shape, not analysis-data.json's dict shape."""
    entries = []
    for days_ago, commits, sessions, overall, badges, cost in (
            (90, 18, 190, 5.4, [], 2.10),
            (55, 26, 220, 5.8, ["shipping_cadence"], 1.70),
            (25, 33, 255, 6.1, ["shipping_cadence", "delegation"], 1.40)):
        d = (now - timedelta(days=days_ago)).date().isoformat()
        entries.append({
            "date": d, "schema_version": 1,
            "scores": {"D1_delegation": 7, "D2_root_cause": 6},
            "overall_avg": overall, "badges": badges,
            "ledger": {"git_commits": commits, "sessions": sessions,
                       "sources_detected": ["claude", "codex"],
                       "leaks": [{"type": "repeated_instructions",
                                  "weekly_cost_usd": cost,
                                  "weekly_tokens": int(cost * 25000),
                                  "occurrences": 6}]}})
    path = OUT_DIR / "autopsy-history.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path
```

Call `gen_history_snapshots(now)` at the end of `main()` (next to `gen_codex_sessions(now)`) and add the path to the final `print`.

- [ ] **Step 2: Extend `tests/test_demo_data.py`**

Add (following that file's existing pipeline-fixture conventions — reuse however it already runs `aggregate.py` over the demo dir):

```python
    def test_history_snapshots_written_and_readable(self):
        hist = OUT_DIR / "autopsy-history.jsonl"
        self.assertTrue(hist.exists())
        from build_html import read_history_snapshots
        entries = read_history_snapshots(hist)
        self.assertEqual(len(entries), 3)
        self.assertEqual([e["date"] for e in entries], sorted(e["date"] for e in entries))

    def test_badges_block_present_with_six_items(self):
        # analysis fixture produced by this file's existing aggregate run
        badges = self.analysis["badges"]
        self.assertEqual(len(badges["items"]), 6)
        self.assertEqual(badges["standard_version"], "v1")

    def test_at_least_one_badge_earned_deterministically(self):
        # Phase 2 lesson: a badge path nobody reaches is a fake sentinel.
        # With random.seed frozen this either always passes or always
        # fails — if it fails, raise the demo's commit density (gen_session)
        # until shipping_cadence clears its bar, don't loosen the bar.
        earned = [b["id"] for b in self.analysis["badges"]["items"] if b["earned"]]
        self.assertTrue(earned, "demo data earns zero badges — engineer the fixture")
```

Run the demo generator + pipeline once (`python3 scripts/generate_demo_data.py` then the aggregate step exactly as `tests/test_demo_data.py` does) and record WHICH badges the seeded demo earns. If none: bump demo commit counts (`gen_session`'s `git_commits` distribution or the engineered sessions) until `shipping_cadence` clears `≥5/week + ≥10 committing sessions` deterministically. Write the earned set into the test as an exact assertion once known.

- [ ] **Step 3: Extend `tests/smoke_test.py`**

Before the SELF `run_build`, seed history so the trend book unlocks (3 demo snapshots + this build's append = 4 lines after):

```python
    shutil.copy(DEMO_ROOT / "autopsy-history.jsonl", history_path)
```

(`DEMO_ROOT` here = the demo output dir the smoke already regenerates; add `import shutil` if missing.) Update the final snapshot-count assertion from `== 1` to `== 4`, and add:

```python
    assert 'id="ledger-trend"' in self_html, "SELF build missing trend ledger"
    assert '<svg class="c-spark"' in self_html, "trend sparklines missing"
    assert 'id="ledger-trend"' not in hr_html, "HR must not render the trend ledger"
    # badge section in HR: earned-only. Demo earns >=1 badge (test_demo_data
    # pins the exact set), so the section must be present.
    assert 'id="badges"' in hr_html, "HR build missing earned badges section"
    assert 'id="badges"' not in self_html, "badge cards are external-only"
```

- [ ] **Step 4: Run the full suites**

Run: `python3 -m pytest tests/ -q`
Expected: only the 2 known-baseline failures

Run: `node --test tests/chart_layout.test.mjs`
Expected: PASS (file untouched — confirmation run)

- [ ] **Step 5: Update `SKILL.md`**

1. **Frontmatter description**: replace the tail from "The HTML report is laid out story-first..." with:
   > The HTML report is laid out ledger-first for SELF (opening band, output/team/leak/trend ledgers, then peer review, 9-dim scoring, try-this-week, case study, claim-indexed evidence). The HR variant is a recruiter version v1: identity card, earned badges (threshold-based, earned-only), allowlist-filtered output ledger, one case study, and a methodology & scope disclosure — no scores, no peer-review memo, no charts.
2. **"What you get" list**: item 0 gains "trend ledger (unlocks at 3 snapshots)"; replace the "HR / portfolio layout differs:" list with the five-block description above.
3. **Pipeline diagram (Step overview)**: Step 3 line drops the HR memo; add under Step 3b: `(SELF only; books: opening/output-ledger/team-ledger/leak-ledger/trend-ledger — write the trend-ledger book ONLY if ~/.claude/usage-data/autopsy-history.jsonl has ≥3 snapshot lines; check with wc -l)`. Step 4 line: `(SELF adds --ledger-narration; both audiences take --history-file)`.
4. **Step 3 HR section**: delete the "HR audience format (candidate memo)" subsection entirely; add one line: "HR needs no peer-review file — the recruiter version renders badges + output ledger + case study only. Write only `case-study.hr.{locale}.md`."
5. **Step 3b**: document the fifth book `# trend-ledger` (opener claim = one sentence comparing a key ledger number across snapshots, e.g. "Commits per run rose from 20 to 44 across three runs"; audit-discipline rules apply).
6. **Step 4 HR command**: drop `--peer-review`; the rest unchanged.
7. **Audience-conditional table**: replace wholesale with:

```markdown
| Aspect | SELF | HR (recruiter v1) |
|---|---|---|
| Opening band / output / team / leak ledgers | rendered | absent |
| Trend ledger | rendered (locked note below 3 snapshots) | absent |
| Badges section | absent (badge data still in analysis-data.json + snapshots) | earned-only cards, criteria + n + window; zero earned → section absent |
| Hero block | Diagnostic letter framing | Practice summary framing |
| Identity | subtle signature | full letterhead |
| Peer review | Story format (4 zones + connect-back) | absent |
| Scoring grid | 9 dimensions, overall average, full disclaimer | absent |
| Output ledger (HR) | n/a (SELF has ledger books) | counters + top-3 allowlisted shipped + artifact links; non-public items excluded entirely |
| Try-this-week | §04 | absent |
| Case study | §05, raw project name + sid | § HR-03, redacted label, NO sid |
| Pattern mining / weekly trends / evidence library | rendered | absent |
| Methodology | full footer | scope disclosure: standard version, earned/total badges, rubric location, reproducibility, privacy model |
| sid8 prefixes | shown | never |
```

8. **Files section**: extend the `aggregate.py` line with "+ `badges` block (compute_badges, bars in scoring-rubric.md)"; `build_html.py` line with "`read_history_snapshots()`"; `report_render.py` line with "`_build_trend_ledger`, `_build_badges_section`, `_build_hr_output_ledger`".

- [ ] **Step 6: Full verification + commit**

Run: `python3 -m pytest tests/ -q` — only the 2 known-baseline failures.

```bash
git add scripts/generate_demo_data.py tests/test_demo_data.py tests/smoke_test.py SKILL.md
git commit -m "feat(demo,skill): deterministic demo history + badges; SKILL.md phase-3 docs"
```

---

## Self-Review (done at plan time)

- **Spec coverage:** §3 book 4 → Task 3; §4 badges → Task 1, recruiter v1 → Task 4; §7 snapshot → Task 2; §8 charts (trend sparklines) → Task 3 (SVG variant, decision #5); §10 suppression → locked-note exception documented; §11 privacy/testing → Tasks 3–5 tests; §13 defaults (3 snapshots) → `_TREND_MIN_SNAPSHOTS`. Deferred by spec §12 (peer/manager versions, follow-through loop) — out.
- **Type consistency:** `compute_badges` item shape consumed identically in Tasks 2/3/4/5; `read_history_snapshots` list shape consumed in Task 3; `_build_trend_ledger(analysis, history_entries, narration, locale, exhibit_no, blind_spots)` signature consistent between Task 3 code and render() wiring.
- **Known risks flagged inline:** locale-key removal needs per-key grep (Task 4 Step 3); smoke "Private project" assertion replacement needs allowlist verification (Task 4 Step 6); demo badge determinism verified empirically then pinned (Task 5 Step 2).

## 完成後（收尾清單，不屬於任何 task）

1. `/simplify` code review，然後 dual gate：`/codex review` + `/security-review` 並行，兩者 0 P1/P2 才 merge（codex pin `-c 'model="gpt-5.6-sol"' -c 'model_reasoning_effort="xhigh"'`，timeout ≥600s）。
2. Implementation-notes 餵進 review 後，merge 完刪除。
3. 更新 project memory（`project_v5_work_ledger_redesign.md`：Phase 3 done、badge bars 待真資料回校）。
