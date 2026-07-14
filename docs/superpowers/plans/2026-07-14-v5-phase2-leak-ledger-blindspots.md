# V5 Phase 2 — Leak Ledger + Blind-Spot Engine + Praise-Word Lint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land Phase 2 of the AI-work-ledger redesign: the blind-spot engine (all 7 heuristics from spec §5, each with its sample gate and the counterexample guard), the SELF-only leak ledger section (top-3 leaks with estimated weekly cost + one concrete fix each), blind-spot openers injected into the existing output-ledger and team-ledger sections, and the praise-word lint (en + zh_TW word lists, hard test + build-time warning) deferred from Phase 1.

**Architecture:** All numbers stay in the deterministic pipeline: `aggregate.py` gains `compute_blind_spots()` (new additive top-level `blind_spots` block) and `compute_leaks()` (additive `ledger.leaks` field), fed by the existing pools plus one new scanner field (`token_accel` from `scan_transcripts.py`). `report_render.py` gains `_build_leak_ledger()` plus opener callouts in the two existing ledger builders, all SELF-only, direction-C styled. A new stdlib module `scripts/praise_lint.py` holds the shared word lists, consumed by unit tests (hard) and by `build_html.py` (stderr warning, never fatal). Demo data is extended so heuristics #1/#2/#4 pass their gates deterministically on synthetic data.

**Tech Stack:** Python 3.9+ stdlib only (pytest test-only), inline HTML/CSS in `report_render.py`, no new JS.

**Spec:** `docs/superpowers/specs/2026-07-14-ai-work-ledger-redesign.md` §2 (audit discipline), §3 (book structure), §5 (heuristics table + gates + guard), §8 (rendering + lint), §10 (suppression), §11 (testing), §13 (defaults).

---

## 決策點（白話，給用戶看的段落；其餘都是工程細節可跳過）

這些是本計畫替你選的預設值。每一條都可以改，改了不動架構，只動門檻或字面。

1. **漏水的「每週成本」怎麼估** — ①只算拿得出證據的部分：重複指令只算「重打的那段字」的 token、沉沒 session 只算那些失敗 session 實際燒掉的 token，換算成 API 等值美元。②推它是因為數字保守、每一塊錢都指得出出處，符合「先數字後形容詞」的紀律。③代價是數字會偏小，真實浪費（你的時間、重看的心力）沒被計入，報告會註明這是下限。
2. **「同一條指令重複出現」怎麼認定** — ①整句正規化（去大小寫、去標點、去多餘空白）後完全一樣才算同一條；太短的（不到 20 字元）不算，避免把「continue」「好」這種也抓進來。②推它是因為零誤報：抓到的一定真的是你每次都重打的那句。③代價是「意思一樣但寫法不同」的重複抓不到，抓到的量會偏少。
3. **習慣漂移（第 5 個盲點）這輪只算數字、不上報告版面** — ①引擎會算出來並存進資料檔，但報告上的「趨勢帳」版面是 Phase 3 的範圍，這輪先不畫。②推它是因為 spec 把趨勢帳排在 Phase 3，且趨勢要 3 次快照才解鎖，現在畫了也是空的。③代價是這輪報告看不到這個盲點，要等下一階段。
4. **每個漏水附的「一個具體修法」用固定句庫** — ①修法文字是照漏水類型從固定句庫挑的（中英各一套），不是 AI 每次自由發揮。②推它是因為和徽章同一個邏輯：建議要穩定、可翻譯、不會這次講東下次講西。③代價是修法比較通用，不會針對你那條指令客製（敘事區的 AI 文字仍可補充）。
5. **幾個 spec 沒寫死的門檻，v1 先取保守值** — 墳場的「實質寫檔」= 該 session 有 5 次以上檔案編輯；想做與做成落差需要至少 20 個已評分 session；反例防呆的「相近比率」= 1.5 倍以內視為不顯著。都會寫進公開的 rubric 檔標成 provisional v1，跑過真資料後再調。

---

## Global Constraints

- Python 3.9+ **standard library only** at runtime (pytest is test-only).
- Output HTML fully self-contained; all user-derived text through `esc()` / `inline_md()`; script-bound data through `json_for_script()` (enforced by `tests/smoke_test.py`).
- `locales.py`: en and zh_TW share the exact same key set; zh_TW values must not contain `—`; `t()` raises KeyError on miss (`tests/test_locales.py`).
- All new analysis blocks are **additive**; document in `docs/SCHEMA-CHANGES.md` **in the same commit** as the code change (repo rule).
- Cross-LLM rows never enter `scoring_metas`/`activity_metas` (spec §6). Blind spot #1 may read cross-LLM `first_prompt`; #3 may read cross-LLM activity windows; #2/#4/#5/#6/#7 are Claude-only (outcome labels exist only for Claude).
- New ledger/blind-spot/leak sections are **SELF-only**; HR output must not contain `id="ledger-` sections, session IDs, or cross-LLM prompt text (smoke-enforced, incl. the `GROK_PRIVATE_MARKER` sentinel).
- Below-gate blocks are suppressed entirely — no apologetic placeholders (spec §10). Follow the Phase 1 gating idiom: early-return `""` for whole blocks, named boolean gate variables for sub-blocks.
- Sample-gate literals get the Phase 1 comment idiom: scoring/gate thresholds are independent constants, never reuse `_PATTERN_MIN_SAMPLE` silently.
- Direction-C grammar: gold `#B08A2E` accent (`--c-gold`), negative red `#9C201A` (`--c-neg`) only for bad numbers, numbered Exhibits with source lines, action-title section heads.
- Conventional-commit subjects; per task run `python3 -m pytest tests/ -q` (and `node --test tests/chart_layout.test.mjs` when touching anything the smoke's JS check covers — this phase does not touch `js/chart_layout.js`). Known baseline: 2 pre-existing failures in `tests/test_build_html_additions.py` on clean main (`LocaleTests::test_zh_tw_build_contains_localized_strings`, `ScoreDisclaimerTests::test_disclaimer_placeholder_in_template`) — not yours to fix, do not add new failures.
- Never run `build_html.py` in a test without `--history-file <tmp path>` (Phase 1 lesson: default path pollutes real `~/.claude/usage-data/autopsy-history.jsonl`).
- Maintain an implementation-notes file (`docs/superpowers/plans/2026-07-14-v5-phase2-implementation-notes.md`, temporary, delete after merge) recording only substantive deviations: deviation point / conservative choice taken / reason.

## Provisional v1 thresholds (decided at plan time — all recorded in `references/scoring-rubric.md` by Task 6)

| Constant | Value | Meaning |
|---|---|---|
| `_BS_MIN_PATTERN_CHARS` | 20 | normalized prompt shorter than this can't form a repeated-instruction pattern or a sunk-cost pair |
| `_BS_REPEAT_MIN_OCC` / `_BS_REPEAT_MIN_WEEKS` | 5 / 3 | spec §5 gate for heuristic #1 |
| `_BS_SUNK_MIN_PAIRS` | 3 | spec §5 gate for #2 |
| `_BS_ACCEL_FLAG` | 1.5 | `token_accel` at/above this = "burning harder late in session" |
| `_BS_SIMILARITY_MIN` | 0.5 | token-set Jaccard for "similar prompt" (#2 pairing) |
| `_BS_RETRY_MAX_DURATION_SHARE` | 0.5 | retry must succeed in ≤ half the failed session's minutes |
| `_BS_SWITCH_MIN_PER_BUCKET` | 20 | spec §5 gate for #3 |
| `_BS_GRAVEYARD_MIN_WRITES` | 5 | Edit+Write+NotebookEdit tool calls ≥ this = substantive writes |
| `_BS_GRAVEYARD_HORIZON_DAYS` | 14 | spec §13 |
| `_BS_GRAVEYARD_MIN_ITEMS` | 2 | spec §5 gate for #4 |
| `_BS_DRIFT_MIN_WEEKS` | 8 | spec §5 gate for #5 (weeks with ≥ `GROWTH_MIN_RATED_PER_WEEK` rated sessions) |
| `_BS_DRIFT_LEN_DROP` | 0.75 | late median prompt length ≤ 75% of early = shortening |
| `_BS_DRIFT_GOOD_TOL_PP` | 5 | good-rate change within ±5pp counts as "flat" |
| `_BS_ASKSHIP_MIN_RATED` / `_BS_ASKSHIP_MIN_SHIPPED` | 20 / 5 | gate for #6 (spec left N open) |
| `_BS_GUARD_FACTOR` | 1.5 | counterexample guard: flagged-behavior rate in `fully_achieved` sessions within 1.5× of the flagged rate → suppress |
| `_BS_FAILED_BURN_MIN_SESSIONS` | 5 | gate for the failed-session-burn leak candidate |
| `_SCRATCH_PATH_MARKERS` | `("/tmp/", "/scratchpad", "/private/tmp/")` | graveyard path exclusions (spec §5 #4) |

**Counterexample-guard applicability** (spec §5 says "any pattern that occurs at a similar rate in fully_achieved sessions drops below gate"; per-heuristic reading, recorded in the rubric):

- #2 sunk-cost: guarded — if `token_accel ≥ 1.5` is about as common in `fully_achieved` as in `not_achieved` sessions, acceleration is not a failure signal for this user; suppress.
- #5 habit drift: guarded — if prompts got shorter but the good rate *improved* beyond tolerance, that is skill, not drift; suppress.
- #6 ask-vs-ship: guarded structurally — inherently non-shipping goal categories (`information_query`, `exploration`, `quick_question`) are excluded from mismatch flagging (asking questions is not a leak).
- #1 repeated-instruction tax: **not outcome-guarded by design** — a repeated instruction is a tax regardless of outcome (successful sessions still paid it); an outcome guard would always suppress it. Guarded instead by the 20-char floor.
- #3, #7: not guarded — they *are* symmetric comparisons (both buckets reported).
- #4 graveyard: not outcome-guarded — an achieved-but-never-shipped artifact is precisely the finding; guarded instead by the structural exclusions (scratch paths, `(unknown)` project, 14-day horizon).

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `scripts/aggregate.py` | modify | helpers (`normalize_prompt`, `prompt_similarity`, `week_key`), 7 `bs_*` heuristic functions, `compute_blind_spots()`, `compute_leaks()`, main() wiring |
| `scripts/scan_transcripts.py` | modify | new additive row field `token_accel` |
| `scripts/praise_lint.py` | create | word lists + `find_praise()` (single source of truth for both consumers) |
| `scripts/build_html.py` | modify | praise-lint warning path over all four LLM-authored markdown inputs |
| `scripts/report_render.py` | modify | exhibit-counter refactor, `_build_leak_ledger()`, graveyard/switch-tax openers, `# leak-ledger` narration book, opening-band third finding, CSS |
| `scripts/locales.py` | modify | all new chrome keys, both locales |
| `scripts/generate_demo_data.py` | modify | deterministic injections for heuristics #1/#2/#4 |
| `references/scoring-rubric.md` | modify | new "Blind-spot heuristics (v1)" + "Leak catalog (v1)" sections |
| `docs/SCHEMA-CHANGES.md` | modify | additive `blind_spots` block + `ledger.leaks` field |
| `SKILL.md` | modify | Step 3b `# leak-ledger` book, audience table rows, praise-lint note |
| `tests/test_blind_spots.py` | create | unit tests for all 7 heuristics + guard |
| `tests/test_leaks.py` | create | leak catalog + ranking + wiring tests |
| `tests/test_praise_lint.py` | create | word lists, both locales, warning path |
| `tests/test_ledger_render.py` | modify | leak section, openers, exhibit renumbering, HR absence |
| `tests/test_scan_transcripts.py` | modify | `token_accel` cases |
| `tests/test_demo_data.py` | modify | injected-fixture gate assertions |
| `tests/smoke_test.py` | modify | leak DOM in SELF / absent in HR, praise-lint warning fires, `# leak-ledger` narration |

Branch: create `v5-phase2-leak-blindspots` off `main`; work lands via PR (dual gate: `/codex review` + `/security-review`, both 0 P1/P2 before merge).

---

### Task 1: Shared helpers in `aggregate.py` — `normalize_prompt`, `prompt_similarity`, `week_key`

**Files:**
- Modify: `scripts/aggregate.py` (add helpers near `bucket_prompt_len`, ~line 244; refactor the two inline week-format call sites at `build_sessions` ~line 435 and the `compute_cross_llm` weekly loop ~line 1811)
- Test: `tests/test_blind_spots.py` (create; helper tests live here since the heuristics are the only consumers)

**Interfaces:**
- Produces: `normalize_prompt(text) -> str` (lowercased, punctuation → space, whitespace collapsed, truncated to 200 chars, `""` on non-str); `prompt_similarity(a_norm: str, b_norm: str) -> float` (token-set Jaccard in [0,1]); `week_key(dt: datetime) -> str` (`"YYYY-Www"`, ISO week). Later tasks (3, 4, 6) call all three by these exact names.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_blind_spots.py
import unittest
from datetime import datetime, timezone

from scripts.aggregate import normalize_prompt, prompt_similarity, week_key


class NormalizePromptTests(unittest.TestCase):
    def test_case_punct_whitespace_collapse(self):
        self.assertEqual(
            normalize_prompt("  Fix the FLAKY test!!  (again) "),
            "fix the flaky test again")

    def test_cjk_preserved(self):
        self.assertEqual(normalize_prompt("回覆一律用繁體中文，先跑測試"),
                         "回覆一律用繁體中文 先跑測試")

    def test_non_string_is_empty(self):
        self.assertEqual(normalize_prompt(None), "")
        self.assertEqual(normalize_prompt(42), "")

    def test_truncated_to_200_chars(self):
        self.assertEqual(len(normalize_prompt("a b " * 200)), 200)


class PromptSimilarityTests(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(prompt_similarity("fix the test", "fix the test"), 1.0)

    def test_disjoint(self):
        self.assertEqual(prompt_similarity("alpha beta", "gamma delta"), 0.0)

    def test_partial_overlap(self):
        # {fix,the,flaky,test} vs {fix,the,broken,test}: 3/5
        self.assertAlmostEqual(
            prompt_similarity("fix the flaky test", "fix the broken test"), 0.6)

    def test_empty_is_zero(self):
        self.assertEqual(prompt_similarity("", "anything"), 0.0)


class WeekKeyTests(unittest.TestCase):
    def test_iso_week_format(self):
        dt = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)  # ISO 2026-W23
        self.assertEqual(week_key(dt), "2026-W23")

    def test_year_boundary_uses_iso_year(self):
        dt = datetime(2025, 12, 29, tzinfo=timezone.utc)  # ISO 2026-W01
        self.assertEqual(week_key(dt), "2026-W01")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_blind_spots.py -q`
Expected: ImportError (`normalize_prompt` not defined).

- [ ] **Step 3: Implement**

Add near `bucket_prompt_len` (module already imports `re`; verify, else add):

```python
# --- Phase 2 shared helpers (blind-spot engine) ---

_NORM_KEEP_RE = re.compile(r"[^\w一-鿿]+")
_NORM_WS_RE = re.compile(r"\s+")


def normalize_prompt(text):
    """Normalize an instruction for exact-match repetition detection.

    Deliberately exact-match only (v1): lowercased, punctuation folded to
    spaces, whitespace collapsed, truncated. No fuzzy matching — zero false
    positives beats higher recall for a tax the user will be told to fix.
    """
    if not isinstance(text, str):
        return ""
    t = _NORM_KEEP_RE.sub(" ", text.lower())
    return _NORM_WS_RE.sub(" ", t).strip()[:200]


def prompt_similarity(a_norm, b_norm):
    """Token-set Jaccard between two normalize_prompt() outputs."""
    ta, tb = set(a_norm.split()), set(b_norm.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def week_key(dt):
    """ISO week label 'YYYY-Www' — the single week-bucketing helper.

    build_sessions and the cross_llm weekly loop previously inlined this
    format; a third copy for the blind-spot engine forced the factor-out.
    """
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"
```

Refactor the two existing inline call sites to call `week_key(local)` / `week_key(s)` — behavior identical (both already emit `YYYY-Www`).

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_blind_spots.py tests/test_cross_llm_aggregate.py -q` then the full suite `python3 -m pytest tests/ -q`
Expected: PASS (baseline 2 known failures only).

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_blind_spots.py
git commit -m "feat(blind-spots): prompt normalization, similarity, and shared week_key helpers"
```

---

### Task 2: `scan_transcripts.py` — additive `token_accel` row field

**Files:**
- Modify: `scripts/scan_transcripts.py` (accumulate per-assistant-message output tokens; emit `token_accel` in the row dict at the ~L309-338 assembly)
- Modify: `scripts/aggregate.py` (`build_sessions` carries `token_accel`; add `"token_accel"` to `_REDACTED_META_KEYS` ~L294-305)
- Test: `tests/test_scan_transcripts.py` (extend, matching its existing synthetic-fixture conventions)

**Interfaces:**
- Produces: row field `token_accel: float | None` = (sum of assistant `output_tokens` over the second half of assistant messages) / (sum over the first half). `None` when the session has fewer than 6 assistant messages or the first-half sum is 0. Session rows built by `build_sessions` expose it as `s["token_accel"]` (Task 4 consumes it).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scan_transcripts.py`, reusing its existing transcript-fixture builder (read the file first; it has helpers that write synthetic `.jsonl` transcripts — follow the same shapes; the assistant records carry `message.usage.output_tokens`):

```python
class TokenAccelTests(unittest.TestCase):
    def _scan_with_outputs(self, outputs):
        # build a synthetic transcript with len(outputs) assistant messages
        # whose usage.output_tokens follow `outputs`, using this file's
        # existing fixture helper, then scan_one() it.
        ...  # adapt to the module's existing helper — see note below

    def test_accelerating_session(self):
        row = self._scan_with_outputs([100, 100, 100, 300, 300, 300])
        self.assertAlmostEqual(row["token_accel"], 3.0)

    def test_flat_session(self):
        row = self._scan_with_outputs([200] * 6)
        self.assertAlmostEqual(row["token_accel"], 1.0)

    def test_too_few_messages_is_none(self):
        row = self._scan_with_outputs([100] * 5)
        self.assertIsNone(row["token_accel"])

    def test_zero_first_half_is_none(self):
        row = self._scan_with_outputs([0, 0, 0, 100, 100, 100])
        self.assertIsNone(row["token_accel"])
```

(The `...` is fixture plumbing, not implementation logic: copy the exact transcript-record shape already used by the module's existing tests. Odd message counts: first half = `outputs[:n//2]`, second half = `outputs[n - n//2:]` — the middle message of an odd-length session belongs to the second half.)

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_scan_transcripts.py -k token_accel -q`
Expected: KeyError/AssertionError (`token_accel` missing from row).

- [ ] **Step 3: Implement**

In `scan_one()`: where assistant `usage` is summed (~L207-211), also append each assistant message's `output_tokens` (default 0) to a local list `assistant_output_seq`. At row assembly:

```python
    # token_accel: output burn in the session's second half vs first half.
    # Proxy for "flailing": regenerating ever-larger responses late in a
    # session. Input tokens are excluded on purpose — context growth makes
    # input rise monotonically in every session, which would flag everything.
    token_accel = None
    n = len(assistant_output_seq)
    if n >= 6:
        first = sum(assistant_output_seq[: n // 2])
        second = sum(assistant_output_seq[n - n // 2:])
        if first > 0:
            token_accel = round(second / first, 2)
```

Add `"token_accel": token_accel,` to the row dict. In `aggregate.py` `build_sessions`, next to the other scanner extras (~L460-464): `"token_accel": m.get("token_accel"),`. Add `"token_accel"` to `_REDACTED_META_KEYS` (it is a dimensionless ratio — safe to travel in cross-machine redacted rows).

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_scan_transcripts.py tests/ -q`
Expected: PASS (baseline failures only).

- [ ] **Step 5: Commit**

```bash
git add scripts/scan_transcripts.py scripts/aggregate.py tests/test_scan_transcripts.py
git commit -m "feat(scan): token_accel row field (second-half vs first-half output burn)"
```

---

### Task 3: Heuristic #1 — `bs_repeated_instructions`

**Files:**
- Modify: `scripts/aggregate.py` (new "blind-spot engine" section before `main()`, after the cross-LLM section; add the constants table from the plan header as module constants here)
- Test: `tests/test_blind_spots.py` (extend)

**Interfaces:**
- Consumes: `normalize_prompt`, `week_key`, `_parse_dt` (existing).
- Produces: `bs_repeated_instructions(claude_rows: list[dict], cross_rows: list[dict]) -> dict`. Input rows are RAW activity/adapter dicts (fields `first_prompt`, `start_time`, `source` optional, `coverage` optional, `session_id`). Returns the standard heuristic shape all `bs_*` functions share:

```python
{"id": "repeated_instructions", "gate_passed": bool, "suppressed_by_guard": False,
 "n": int,                     # qualifying patterns
 "metrics": {"patterns": [    # sorted by occurrences desc, top 5
     {"exemplar": str,        # most common RAW first_prompt among occurrences, ≤120 chars
      "occurrences": int, "weeks": int, "sources": ["claude", "codex", ...],
      "est_wasted_tokens": int,   # (occurrences-1) * len(exemplar)//4, lower bound
      "evidence": [sid, sid, sid]}]},   # ≤3 session ids
 "reason": str | None}         # set when gate_passed is False
```

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_blind_spots.py
from datetime import timedelta
from scripts.aggregate import bs_repeated_instructions

BASE = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
INSTR = "Always reply in zh-TW and run the full pytest suite before you claim done"


def _prompt_row(sid, start, prompt, source=None, coverage=None):
    row = {"session_id": sid, "start_time": start.isoformat(),
           "first_prompt": prompt}
    if source:
        row["source"], row["coverage"] = source, coverage
    return row


class RepeatedInstructionTests(unittest.TestCase):
    def test_five_occurrences_three_weeks_passes_gate(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i % 3, days=i), INSTR)
                for i in range(5)]
        out = bs_repeated_instructions(rows, [])
        self.assertTrue(out["gate_passed"])
        p = out["metrics"]["patterns"][0]
        self.assertEqual(p["occurrences"], 5)
        self.assertGreaterEqual(p["weeks"], 3)
        self.assertEqual(p["est_wasted_tokens"], 4 * (len(INSTR) // 4))
        self.assertLessEqual(len(p["evidence"]), 3)

    def test_five_occurrences_two_weeks_fails_gate(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(days=i), INSTR)
                for i in range(5)]
        out = bs_repeated_instructions(rows, [])
        self.assertFalse(out["gate_passed"])
        self.assertIsNotNone(out["reason"])

    def test_cross_tool_occurrences_count(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i), INSTR)
                for i in range(3)]
        cross = [_prompt_row(f"x{i}", BASE + timedelta(weeks=i, hours=2), INSTR,
                             source="codex", coverage="full") for i in range(2)]
        out = bs_repeated_instructions(rows, cross)
        self.assertTrue(out["gate_passed"])
        self.assertIn("codex", out["metrics"]["patterns"][0]["sources"])

    def test_presence_only_rows_ignored(self):
        cross = [{"session_id": f"a{i}", "start_time": (BASE + timedelta(weeks=i)).isoformat(),
                  "first_prompt": None, "source": "antigravity",
                  "coverage": "presence_only"} for i in range(9)]
        out = bs_repeated_instructions([], cross)
        self.assertFalse(out["gate_passed"])

    def test_short_prompts_never_pattern(self):
        rows = [_prompt_row(f"c{i}", BASE + timedelta(weeks=i), "continue")
                for i in range(9)]
        out = bs_repeated_instructions(rows, [])
        self.assertFalse(out["gate_passed"])

    def test_normalization_merges_variants(self):
        rows = ([_prompt_row(f"c{i}", BASE + timedelta(weeks=i % 3, days=i),
                             INSTR) for i in range(3)]
                + [_prompt_row(f"d{i}", BASE + timedelta(weeks=i, days=2),
                               INSTR.upper() + "!!") for i in range(2)])
        out = bs_repeated_instructions(rows, [])
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["patterns"][0]["occurrences"], 5)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_blind_spots.py -k Repeated -q`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# --- Blind-spot engine (Phase 2, spec §5) -----------------------------
# Gate literals below are heuristic-eligibility thresholds: independent
# from _PATTERN_MIN_SAMPLE (the pattern-floor constant). Keep separate so
# future tuning of the pattern floor doesn't silently move these gates.
_BS_MIN_PATTERN_CHARS = 20
_BS_REPEAT_MIN_OCC = 5
_BS_REPEAT_MIN_WEEKS = 3


def _bs_result(id_, gate, metrics=None, n=0, reason=None, guarded=False):
    return {"id": id_, "gate_passed": bool(gate),
            "suppressed_by_guard": bool(guarded), "n": n,
            "metrics": metrics or {}, "reason": reason}


def bs_repeated_instructions(claude_rows, cross_rows):
    """Spec §5 #1 — repeated-instruction tax.

    Exact-match on normalize_prompt(first_prompt) across Claude + full/
    partial cross-LLM rows. Not outcome-guarded by design: a repeated
    instruction is a tax whether or not the sessions succeed (see rubric).
    Wasted-token estimate is a lower bound: only the retyped prompt text.
    """
    occ = {}
    for row in list(claude_rows) + list(cross_rows):
        if row.get("coverage") == "presence_only":
            continue
        norm = normalize_prompt(row.get("first_prompt"))
        if len(norm) < _BS_MIN_PATTERN_CHARS:
            continue
        dt = _parse_dt(row.get("start_time"))
        if dt is None:
            continue
        occ.setdefault(norm, []).append({
            "week": week_key(dt),
            "source": row.get("source") or "claude",
            "sid": row.get("session_id") or "",
            "raw": row.get("first_prompt") or ""})
    patterns = []
    for hits in occ.values():
        weeks = {h["week"] for h in hits}
        if len(hits) < _BS_REPEAT_MIN_OCC or len(weeks) < _BS_REPEAT_MIN_WEEKS:
            continue
        raw_counts = {}
        for h in hits:
            raw_counts[h["raw"]] = raw_counts.get(h["raw"], 0) + 1
        exemplar = max(raw_counts, key=raw_counts.get)[:120]
        patterns.append({
            "exemplar": exemplar,
            "occurrences": len(hits),
            "weeks": len(weeks),
            "sources": sorted({h["source"] for h in hits}),
            "est_wasted_tokens": (len(hits) - 1) * (len(exemplar) // 4),
            "evidence": [h["sid"] for h in hits[:3]]})
    patterns.sort(key=lambda p: -p["occurrences"])
    if not patterns:
        return _bs_result("repeated_instructions", False,
                          reason="no pattern with >=5 occurrences over >=3 weeks")
    return _bs_result("repeated_instructions", True,
                      metrics={"patterns": patterns[:5]}, n=len(patterns))
```

- [ ] **Step 4: Run tests** — `python3 -m pytest tests/test_blind_spots.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_blind_spots.py
git commit -m "feat(blind-spots): repeated-instruction tax heuristic (#1) with occurrence/week gate"
```

---

### Task 4: Heuristic #2 — `bs_sunk_cost` + counterexample guard helper

**Files:**
- Modify: `scripts/aggregate.py`
- Test: `tests/test_blind_spots.py` (extend)

**Interfaces:**
- Consumes: built session rows (from `build_sessions`) with `outcome`, `token_accel`, `first_prompt`, `duration_min`, `total_tokens`, `start`, `sid`; `is_good()`; `normalize_prompt`/`prompt_similarity`; `_parse_dt`.
- Produces: `bs_sunk_cost(rated: list[dict]) -> dict` (standard shape; `metrics = {"pairs": [{"failed_sid", "retry_sid", "failed_tokens", "failed_minutes", "retry_minutes", "similarity"}...], "accel_rate_not_achieved": float, "accel_rate_fully_achieved": float}`; `n` = confirmed pairs). Also produces the shared guard helper `counterexample_similar(rate_flagged: float, rate_good: float) -> bool` (True = guard trips) used again by Task 7's #5.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_blind_spots.py
from scripts.aggregate import bs_sunk_cost, counterexample_similar

FAIL_PROMPT = "refactor the payment reconciliation pipeline to stream batches"
RETRY_PROMPT = "refactor the payment reconciliation pipeline to stream batches cleanly"


def _sess(sid, start, outcome, prompt=FAIL_PROMPT, accel=None, dur=120,
          tokens=50000):
    return {"sid": sid, "start": start.isoformat(), "outcome": outcome,
            "first_prompt": prompt, "token_accel": accel,
            "duration_min": dur, "total_tokens": tokens,
            "input_tokens": tokens - 5000, "output_tokens": 5000,
            "cache_create_tokens": 0, "cache_read_tokens": 0,
            "model_counts": {"claude-opus-4-6": 10}}


def _pair(i):
    failed = _sess(f"f{i}", BASE + timedelta(days=2 * i), "not_achieved",
                   accel=2.0)
    retry = _sess(f"r{i}", BASE + timedelta(days=2 * i + 1), "fully_achieved",
                  prompt=RETRY_PROMPT, accel=1.0, dur=30, tokens=8000)
    return [failed, retry]


class SunkCostTests(unittest.TestCase):
    def test_three_pairs_pass_gate(self):
        rated = [s for i in range(3) for s in _pair(i)]
        # guard needs a fully_achieved population without acceleration
        rated += [_sess(f"g{i}", BASE + timedelta(days=40 + i),
                        "fully_achieved", prompt=f"unrelated task {i} entirely",
                        accel=1.0) for i in range(6)]
        out = bs_sunk_cost(rated)
        self.assertTrue(out["gate_passed"])
        self.assertFalse(out["suppressed_by_guard"])
        self.assertEqual(out["n"], 3)
        self.assertEqual(out["metrics"]["pairs"][0]["failed_sid"], "f0")

    def test_two_pairs_fail_gate(self):
        rated = [s for i in range(2) for s in _pair(i)]
        out = bs_sunk_cost(rated)
        self.assertFalse(out["gate_passed"])

    def test_retry_must_be_later_and_fast(self):
        failed = _sess("f0", BASE + timedelta(days=5), "not_achieved", accel=2.0)
        early_retry = _sess("r0", BASE, "fully_achieved", prompt=RETRY_PROMPT,
                            dur=30)
        slow_retry = _sess("r1", BASE + timedelta(days=6), "fully_achieved",
                           prompt=RETRY_PROMPT, dur=110)
        out = bs_sunk_cost([failed, early_retry, slow_retry] * 3)
        self.assertEqual(out["n"], 0)

    def test_guard_trips_when_accel_common_in_success(self):
        rated = [s for i in range(3) for s in _pair(i)]
        # fully_achieved sessions accelerate just as much -> not a failure signal
        rated += [_sess(f"g{i}", BASE + timedelta(days=40 + i),
                        "fully_achieved", prompt=f"unrelated task {i} entirely",
                        accel=2.0) for i in range(6)]
        out = bs_sunk_cost(rated)
        self.assertTrue(out["suppressed_by_guard"])
        self.assertFalse(out["gate_passed"])


class GuardHelperTests(unittest.TestCase):
    def test_similar_rates_trip(self):
        self.assertTrue(counterexample_similar(0.5, 0.4))

    def test_distinct_rates_pass(self):
        self.assertFalse(counterexample_similar(0.6, 0.1))

    def test_zero_flagged_rate_trips(self):
        self.assertTrue(counterexample_similar(0.0, 0.0))
```

- [ ] **Step 2: Run to verify failure** — `python3 -m pytest tests/test_blind_spots.py -k "SunkCost or GuardHelper" -q` → ImportError.

- [ ] **Step 3: Implement**

```python
_BS_SUNK_MIN_PAIRS = 3
_BS_ACCEL_FLAG = 1.5
_BS_SIMILARITY_MIN = 0.5
_BS_RETRY_MAX_DURATION_SHARE = 0.5
_BS_GUARD_FACTOR = 1.5


def counterexample_similar(rate_flagged, rate_good):
    """Spec §5 counterexample guard: True when the flagged behavior occurs
    at a similar rate in fully_achieved sessions (within _BS_GUARD_FACTOR),
    i.e. the pattern must NOT be reported as waste."""
    if rate_flagged <= 0:
        return True
    return rate_good * _BS_GUARD_FACTOR >= rate_flagged


def bs_sunk_cost(rated):
    """Spec §5 #2 — sunk-cost sessions.

    A confirmed pair = a not_achieved session with late-session output
    acceleration, followed by a later good-outcome session on a similar
    prompt finishing in <= half the minutes. Guard: if acceleration is
    about as common in fully_achieved sessions, suppress entirely.
    """
    def accel_flag(s):
        a = s.get("token_accel")
        return a is not None and a >= _BS_ACCEL_FLAG

    failed = [s for s in rated
              if s["outcome"] == "not_achieved" and accel_flag(s)]
    good = [s for s in rated if is_good(s["outcome"])]
    pairs = []
    for f in failed:
        fn = normalize_prompt(f.get("first_prompt"))
        if len(fn) < _BS_MIN_PATTERN_CHARS:
            continue
        f_dt = _parse_dt(f.get("start"))
        f_dur = f.get("duration_min") or 0
        if f_dt is None or f_dur <= 0:
            continue
        for g in good:
            g_dt = _parse_dt(g.get("start"))
            if g_dt is None or g_dt <= f_dt:
                continue
            sim = prompt_similarity(fn, normalize_prompt(g.get("first_prompt")))
            if sim < _BS_SIMILARITY_MIN:
                continue
            if (g.get("duration_min") or 0) > _BS_RETRY_MAX_DURATION_SHARE * f_dur:
                continue
            pairs.append({"failed_sid": f["sid"], "retry_sid": g["sid"],
                          "failed_tokens": f.get("total_tokens") or 0,
                          "failed_minutes": f_dur,
                          "retry_minutes": g.get("duration_min") or 0,
                          "similarity": round(sim, 2)})
            break
    fa = [s for s in rated if s["outcome"] == "fully_achieved"
          and s.get("token_accel") is not None]
    na = [s for s in rated if s["outcome"] == "not_achieved"
          and s.get("token_accel") is not None]
    rate_good = (sum(accel_flag(s) for s in fa) / len(fa)) if fa else 0.0
    rate_bad = (sum(accel_flag(s) for s in na) / len(na)) if na else 0.0
    metrics = {"pairs": pairs,
               "accel_rate_not_achieved": round(rate_bad, 2),
               "accel_rate_fully_achieved": round(rate_good, 2)}
    if pairs and counterexample_similar(rate_bad, rate_good):
        return _bs_result("sunk_cost", False, metrics=metrics, n=len(pairs),
                          reason="acceleration equally common in successful sessions",
                          guarded=True)
    if len(pairs) < _BS_SUNK_MIN_PAIRS:
        return _bs_result("sunk_cost", False, metrics=metrics, n=len(pairs),
                          reason="fewer than 3 confirmed pairs")
    return _bs_result("sunk_cost", True, metrics=metrics, n=len(pairs))
```

Note for the implementer: session rows store `start` as an ISO string — `_parse_dt` handles it. The `test_retry_must_be_later_and_fast` fixture has no `accel` on retries; `* 3` duplicates trigger no pairs because the early retry predates and the slow retry exceeds the duration share.

- [ ] **Step 4: Run tests** — `python3 -m pytest tests/test_blind_spots.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_blind_spots.py
git commit -m "feat(blind-spots): sunk-cost pair heuristic (#2) with counterexample guard"
```

---

### Task 5: Heuristics #3 + #7 — `bs_switch_tax`, `bs_interrupt_win_rate`

**Files:**
- Modify: `scripts/aggregate.py`
- Test: `tests/test_blind_spots.py` (extend)

**Interfaces:**
- Consumes: `_row_windows`, `_sweep_concurrent_intervals`, `_merge_intervals` (existing cross-LLM helpers — read their exact signatures at ~L1529-1671 before wiring); `is_good`; `_PATTERN_MIN_SAMPLE`.
- Produces:
  - `bs_switch_tax(rated: list[dict], activity_rows: list[dict], cross_rows: list[dict]) -> dict` — `metrics = {"multi": {"n", "good_rate", "friction_per_session", "interrupts_per_session"}, "single": {...same...}}`, buckets = rated Claude sessions whose `[start, start+duration]` overlaps any ≥2-source concurrent interval vs the rest.
  - `bs_interrupt_win_rate(rated: list[dict]) -> dict` — `metrics = {"interrupted": {"n", "good_rate"}, "baseline": {"n", "good_rate"}, "delta_pp": float}` (the D5 upgrade: both buckets reported symmetrically, delta in percentage points).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_blind_spots.py
from scripts.aggregate import bs_switch_tax, bs_interrupt_win_rate


def _rated(sid, start, outcome, dur=60, interrupts=0, friction=None):
    return {"sid": sid, "start": start.isoformat(), "outcome": outcome,
            "duration_min": dur, "interrupts": interrupts,
            "friction_counts": friction or {}, "first_prompt": "x",
            "token_accel": None, "total_tokens": 1000}


def _act_row(sid, start, dur=60):
    return {"session_id": sid, "project_path": "/p", "start_time": start.isoformat(),
            "duration_minutes": dur}


def _codex_act(sid, start, dur=60):
    r = _act_row(sid, start, dur)
    r["source"], r["coverage"] = "codex", "full"
    return r


class SwitchTaxTests(unittest.TestCase):
    def _fixture(self):
        rated, act, cross = [], [], []
        for i in range(20):  # multi-tool mornings: codex runs alongside
            t = BASE + timedelta(days=i)
            rated.append(_rated(f"m{i}", t, "not_achieved" if i % 2 else
                                "fully_achieved", friction={"buggy_code": 1}))
            act.append(_act_row(f"m{i}", t))
            cross.append(_codex_act(f"x{i}", t + timedelta(minutes=10)))
        for i in range(20):  # single-tool evenings
            t = BASE + timedelta(days=i, hours=10)
            rated.append(_rated(f"s{i}", t, "fully_achieved"))
            act.append(_act_row(f"s{i}", t))
        return rated, act, cross

    def test_buckets_and_gate(self):
        rated, act, cross = self._fixture()
        out = bs_switch_tax(rated, act, cross)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["multi"]["n"], 20)
        self.assertEqual(out["metrics"]["single"]["n"], 20)
        self.assertEqual(out["metrics"]["single"]["good_rate"], 100.0)
        self.assertLess(out["metrics"]["multi"]["good_rate"], 100.0)

    def test_below_bucket_floor_fails_gate(self):
        rated, act, cross = self._fixture()
        out = bs_switch_tax(rated[:25], act, cross)  # only 5 single-tool
        self.assertFalse(out["gate_passed"])

    def test_no_cross_rows_fails_gate(self):
        rated, act, _ = self._fixture()
        out = bs_switch_tax(rated, act, [])
        self.assertFalse(out["gate_passed"])


class InterruptWinRateTests(unittest.TestCase):
    def test_symmetric_rates_and_delta(self):
        rated = ([_rated(f"i{k}", BASE + timedelta(days=k), 
                         "fully_achieved" if k < 2 else "not_achieved",
                         interrupts=1) for k in range(5)]
                 + [_rated(f"b{k}", BASE + timedelta(days=k, hours=5),
                           "fully_achieved" if k < 4 else "not_achieved")
                    for k in range(5)])
        out = bs_interrupt_win_rate(rated)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["interrupted"]["good_rate"], 40.0)
        self.assertEqual(out["metrics"]["baseline"]["good_rate"], 80.0)
        self.assertEqual(out["metrics"]["delta_pp"], -40.0)

    def test_gate_needs_five_in_each_bucket(self):
        rated = [_rated(f"i{k}", BASE + timedelta(days=k), "fully_achieved",
                        interrupts=1) for k in range(5)]
        out = bs_interrupt_win_rate(rated)  # zero non-interrupted
        self.assertFalse(out["gate_passed"])
```

- [ ] **Step 2: Run to verify failure** — `python3 -m pytest tests/test_blind_spots.py -k "SwitchTax or InterruptWin" -q` → ImportError.

- [ ] **Step 3: Implement**

```python
_BS_SWITCH_MIN_PER_BUCKET = 20


def _multi_source_intervals(activity_rows, cross_rows):
    """Merged wall-clock intervals where >=2 sources were active.
    Reuses the cross_llm sweep helpers; presence-only rows excluded."""
    rows = []
    for r in activity_rows:
        rr = dict(r)
        rr.setdefault("source", "claude")
        rows.append(rr)
    rows += [r for r in cross_rows if r.get("coverage") != "presence_only"]
    # follow compute_cross_llm's exact call pattern for _row_windows /
    # _merge_intervals / _sweep_concurrent_intervals (read it first);
    # return [(start_dt, end_dt)] for sub-intervals with n_sources >= 2.
    ...


def bs_switch_tax(rated, activity_rows, cross_rows):
    """Spec §5 #3 — switch tax. Outcome labels exist only for Claude, so
    both buckets are Claude sessions; concurrency is measured against all
    full/partial sources. Symmetric comparison — no counterexample guard."""
    multi_iv = _multi_source_intervals(activity_rows, cross_rows)
    if not multi_iv:
        return _bs_result("switch_tax", False, reason="no multi-source windows")
    multi, single = [], []
    for s in rated:
        st = _parse_dt(s.get("start"))
        if st is None:
            continue
        en = st + timedelta(minutes=s.get("duration_min") or 0)
        hit = any(a < en and st < b for a, b in multi_iv)
        (multi if hit else single).append(s)
    if len(multi) < _BS_SWITCH_MIN_PER_BUCKET or len(single) < _BS_SWITCH_MIN_PER_BUCKET:
        return _bs_result("switch_tax", False,
                          n=min(len(multi), len(single)),
                          reason="fewer than 20 scored sessions in a bucket")

    def side(sessions):
        n = len(sessions)
        return {"n": n,
                "good_rate": round(100 * sum(is_good(s["outcome"]) for s in sessions) / n, 1),
                "friction_per_session": round(
                    sum(sum((s.get("friction_counts") or {}).values())
                        for s in sessions) / n, 2),
                "interrupts_per_session": round(
                    sum(s.get("interrupts") or 0 for s in sessions) / n, 2)}

    return _bs_result("switch_tax", True, n=len(multi) + len(single),
                      metrics={"multi": side(multi), "single": side(single)})


def bs_interrupt_win_rate(rated):
    """Spec §5 #7 — interrupt win-rate, the D5 upgrade: same buckets as
    score_d5_interrupt but symmetric (both rates + delta). Gate mirrors
    D5's literal 5 plus a baseline floor of the same size."""
    interrupted = [s for s in rated if (s.get("interrupts") or 0) > 0]
    baseline = [s for s in rated if not (s.get("interrupts") or 0)]
    if len(interrupted) < 5 or len(baseline) < 5:
        return _bs_result("interrupt_win_rate", False,
                          n=len(interrupted),
                          reason="fewer than 5 sessions in a bucket")

    def rate(ss):
        return round(100 * sum(is_good(s["outcome"]) for s in ss) / len(ss), 1)

    ri, rb = rate(interrupted), rate(baseline)
    return _bs_result("interrupt_win_rate", True, n=len(interrupted),
                      metrics={"interrupted": {"n": len(interrupted), "good_rate": ri},
                               "baseline": {"n": len(baseline), "good_rate": rb},
                               "delta_pp": round(ri - rb, 1)})
```

The `...` in `_multi_source_intervals` is the only adapt-to-existing-code point in this task: `compute_cross_llm` already builds windows and sweeps them (~L1621-1659); copy its exact invocation (windows dict keyed how it keys them) and filter the sweep output to `n_sources >= 2`, returning merged `(start, end)` tuples. Everything else above is complete.

- [ ] **Step 4: Run tests** — `python3 -m pytest tests/test_blind_spots.py tests/test_cross_llm_aggregate.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_blind_spots.py
git commit -m "feat(blind-spots): switch-tax (#3) and interrupt win-rate (#7) heuristics"
```

---

### Task 6: Heuristics #4 + #6 — `bs_graveyard`, `bs_ask_vs_ship`

**Files:**
- Modify: `scripts/aggregate.py`
- Test: `tests/test_blind_spots.py` (extend)

**Interfaces:**
- Consumes: `is_shippable_project_key` (existing, ~L174-192), `_parse_dt`, `project_key_of` (check the existing project-key derivation used in `build_sessions` ~L427-433 and reuse the same function for raw rows).
- Produces:
  - `bs_graveyard(activity_rows: list[dict], window_end: datetime) -> dict` — `metrics = {"items": [{"project_key", "last_active_date", "days_untouched", "writes", "evidence": [sid]}...]}` sorted by days_untouched desc.
  - `bs_ask_vs_ship(rated: list[dict]) -> dict` — `metrics = {"top_gap": {"category", "ask_share_pct", "ship_share_pct", "gap_pp"}, "shipped_sessions": int}`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_blind_spots.py
from scripts.aggregate import bs_graveyard, bs_ask_vs_ship

WINDOW_END = BASE + timedelta(days=60)


def _grave_row(sid, start, project, writes=6, commits=0):
    return {"session_id": sid, "project_path": project,
            "start_time": start.isoformat(), "duration_minutes": 60,
            "tool_counts": {"Edit": writes, "Read": 10},
            "git_commits": commits}


class GraveyardTests(unittest.TestCase):
    def test_two_items_pass_gate(self):
        rows = [_grave_row("g1", BASE, "/home/u/projects/legacy-migration"),
                _grave_row("g2", BASE + timedelta(days=3),
                           "/home/u/projects/docs-site")]
        out = bs_graveyard(rows, WINDOW_END)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(len(out["metrics"]["items"]), 2)
        self.assertGreaterEqual(out["metrics"]["items"][0]["days_untouched"], 14)

    def test_later_activity_disqualifies(self):
        rows = [_grave_row("g1", BASE, "/home/u/projects/legacy-migration"),
                _grave_row("g2", BASE + timedelta(days=50),
                           "/home/u/projects/legacy-migration", writes=0)]
        out = bs_graveyard(rows, WINDOW_END)
        self.assertFalse(out["gate_passed"])

    def test_commit_disqualifies(self):
        rows = [_grave_row("g1", BASE, "/home/u/projects/a", commits=1),
                _grave_row("g2", BASE, "/home/u/projects/b", commits=1)]
        out = bs_graveyard(rows, WINDOW_END)
        self.assertFalse(out["gate_passed"])

    def test_scratch_and_unknown_excluded(self):
        rows = [_grave_row("g1", BASE, "/tmp/throwaway"),
                _grave_row("g2", BASE, "(unknown)")]
        out = bs_graveyard(rows, WINDOW_END)
        self.assertFalse(out["gate_passed"])

    def test_recent_session_not_yet_graveyard(self):
        rows = [_grave_row("g1", WINDOW_END - timedelta(days=3),
                           "/home/u/projects/a"),
                _grave_row("g2", WINDOW_END - timedelta(days=2),
                           "/home/u/projects/b")]
        out = bs_graveyard(rows, WINDOW_END)
        self.assertFalse(out["gate_passed"])


def _goal_sess(sid, cats, commits=0):
    return {"sid": sid, "start": BASE.isoformat(), "outcome": "fully_achieved",
            "goal_cats": cats, "git_commits": commits,
            "project_key": "webapp", "first_prompt": "x",
            "duration_min": 30, "interrupts": 0, "friction_counts": {},
            "token_accel": None, "total_tokens": 100}


class AskVsShipTests(unittest.TestCase):
    def test_gap_detected(self):
        rated = ([_goal_sess(f"a{i}", {"feature_implementation": 1})
                  for i in range(10)]
                 + [_goal_sess(f"b{i}", {"documentation_update": 1},
                               commits=1) for i in range(10)])
        out = bs_ask_vs_ship(rated)
        self.assertTrue(out["gate_passed"])
        self.assertEqual(out["metrics"]["top_gap"]["category"],
                         "feature_implementation")
        self.assertEqual(out["metrics"]["top_gap"]["ship_share_pct"], 0.0)

    def test_nonshipping_categories_never_flagged(self):
        rated = ([_goal_sess(f"a{i}", {"information_query": 1})
                  for i in range(15)]
                 + [_goal_sess(f"b{i}", {"bug_fix": 1}, commits=1)
                    for i in range(10)])
        out = bs_ask_vs_ship(rated)
        if out["gate_passed"]:
            self.assertNotEqual(out["metrics"]["top_gap"]["category"],
                                "information_query")

    def test_gate_needs_shipped_sessions(self):
        rated = [_goal_sess(f"a{i}", {"bug_fix": 1}) for i in range(25)]
        out = bs_ask_vs_ship(rated)  # zero commits anywhere
        self.assertFalse(out["gate_passed"])
```

- [ ] **Step 2: Run to verify failure** — ImportError, as before.

- [ ] **Step 3: Implement**

```python
_BS_GRAVEYARD_MIN_WRITES = 5
_BS_GRAVEYARD_HORIZON_DAYS = 14   # spec §13
_BS_GRAVEYARD_MIN_ITEMS = 2
_SCRATCH_PATH_MARKERS = ("/tmp/", "/scratchpad", "/private/tmp/")
_WRITE_TOOLS = ("Edit", "Write", "NotebookEdit")
_BS_ASKSHIP_MIN_RATED = 20
_BS_ASKSHIP_MIN_SHIPPED = 5
_BS_NONSHIP_GOALS = {"information_query", "exploration", "quick_question"}


def bs_graveyard(activity_rows, window_end):
    """Spec §5 #4 — the graveyard: substantive writes, no commit, project
    untouched >= 14 days after. Structural guards (scratch paths, unknown
    project) replace the outcome guard: achieved-but-never-shipped is
    precisely the finding, not a counterexample."""
    by_project = {}
    for r in activity_rows:
        path = (r.get("project_path") or "").strip()
        key = path  # group by full path; derive display key below
        if not path or not is_shippable_project_key(path):
            continue
        if any(m in path.lower() for m in _SCRATCH_PATH_MARKERS):
            continue
        dt = _parse_dt(r.get("start_time"))
        if dt is None:
            continue
        by_project.setdefault(key, []).append((dt, r))
    items = []
    for path, entries in by_project.items():
        entries.sort(key=lambda e: e[0])
        last_dt, last_row = entries[-1]
        days_untouched = (window_end - last_dt).days
        if days_untouched < _BS_GRAVEYARD_HORIZON_DAYS:
            continue
        tc = last_row.get("tool_counts") or {}
        writes = sum(tc.get(t, 0) for t in _WRITE_TOOLS)
        if writes < _BS_GRAVEYARD_MIN_WRITES:
            continue
        if (last_row.get("git_commits") or 0) > 0:
            continue
        items.append({"project_key": path.rstrip("/").rsplit("/", 1)[-1],
                      "last_active_date": last_dt.date().isoformat(),
                      "days_untouched": days_untouched,
                      "writes": writes,
                      "evidence": [last_row.get("session_id") or ""]})
    items.sort(key=lambda i: -i["days_untouched"])
    if len(items) < _BS_GRAVEYARD_MIN_ITEMS:
        return _bs_result("graveyard", False, n=len(items),
                          reason="fewer than 2 qualifying items")
    return _bs_result("graveyard", True, metrics={"items": items[:8]},
                      n=len(items))


def bs_ask_vs_ship(rated):
    """Spec §5 #6 — goal-category share of asks vs share of sessions that
    shipped (git_commits > 0). Non-shipping categories are excluded from
    flagging: asking questions is not a leak (structural guard)."""
    if len(rated) < _BS_ASKSHIP_MIN_RATED:
        return _bs_result("ask_vs_ship", False, n=len(rated),
                          reason="fewer than 20 scored sessions")
    ask, ship = {}, {}
    shipped_sessions = 0
    for s in rated:
        cats = s.get("goal_cats") or {}
        shipped = (s.get("git_commits") or 0) > 0
        if shipped:
            shipped_sessions += 1
        for c, n in cats.items():
            ask[c] = ask.get(c, 0) + n
            if shipped:
                ship[c] = ship.get(c, 0) + n
    total_ask, total_ship = sum(ask.values()), sum(ship.values())
    if not total_ask or shipped_sessions < _BS_ASKSHIP_MIN_SHIPPED:
        return _bs_result("ask_vs_ship", False, n=len(rated),
                          reason="facets or shipped sessions below floor")
    gaps = []
    for c, n in ask.items():
        if c in _BS_NONSHIP_GOALS:
            continue
        a = 100 * n / total_ask
        p = 100 * ship.get(c, 0) / total_ship if total_ship else 0.0
        gaps.append((a - p, c, a, p))
    if not gaps:
        return _bs_result("ask_vs_ship", False, n=len(rated),
                          reason="no shippable goal categories present")
    gap_pp, cat, a, p = max(gaps)
    return _bs_result("ask_vs_ship", True, n=len(rated),
                      metrics={"top_gap": {"category": cat,
                                           "ask_share_pct": round(a, 1),
                                           "ship_share_pct": round(p, 1),
                                           "gap_pp": round(gap_pp, 1)},
                               "shipped_sessions": shipped_sessions})
```

Implementer note: check whether `is_shippable_project_key` expects a project KEY or a PATH (read ~L174-192); if it expects keys, derive the key the same way `build_sessions` does before calling it, and adjust the `(unknown)` test row accordingly.

- [ ] **Step 4: Run tests** — `python3 -m pytest tests/test_blind_spots.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py tests/test_blind_spots.py
git commit -m "feat(blind-spots): graveyard (#4) and ask-vs-ship (#6) heuristics"
```

---

### Task 7: Heuristic #5 + orchestrator — `bs_habit_drift`, `compute_blind_spots`, main() wiring, SCHEMA-CHANGES, rubric

**Files:**
- Modify: `scripts/aggregate.py` (heuristic, orchestrator, main() wiring after the cross_llm/ledger block ~L2184-2201)
- Modify: `docs/SCHEMA-CHANGES.md` (same commit — repo rule)
- Modify: `references/scoring-rubric.md` (new sections)
- Test: `tests/test_blind_spots.py` (extend, incl. a `MainWiringTests`-style subprocess test copied from `tests/test_cross_llm_aggregate.py`'s pattern)

**Interfaces:**
- Consumes: everything from Tasks 1-6; `GROWTH_MIN_RATED_PER_WEEK` (existing, =3); `week_key`.
- Produces:
  - `bs_habit_drift(rated: list[dict]) -> dict` — `metrics = {"weeks": int, "early_median_len", "late_median_len", "early_good_rate", "late_good_rate"}`; guarded (improved outcomes suppress).
  - `compute_blind_spots(sessions, rated, activity_rows, cross_rows, window_end) -> dict`:

```python
{"schema_version": 1,
 "repeated_instructions": {...}, "sunk_cost": {...}, "switch_tax": {...},
 "graveyard": {...}, "habit_drift": {...}, "ask_vs_ship": {...},
 "interrupt_win_rate": {...}}
```

  - main() attaches `final["blind_spots"]`. **Habit drift is computed and stored but NOT rendered in Phase 2** (trend-ledger UI is Phase 3 — decision #3 in the header).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_blind_spots.py
import json as _json
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.aggregate import bs_habit_drift, compute_blind_spots


def _week_sess(week_i, j, plen, good):
    start = BASE + timedelta(weeks=week_i, days=j % 5)
    return {"sid": f"w{week_i}s{j}", "start": start.isoformat(),
            "outcome": "fully_achieved" if good else "not_achieved",
            "first_prompt": "p" * plen, "first_prompt_len": plen,
            "duration_min": 30, "interrupts": 0, "friction_counts": {},
            "goal_cats": {}, "git_commits": 0, "token_accel": None,
            "total_tokens": 100}


class HabitDriftTests(unittest.TestCase):
    def _weeks(self, lens, good_rates):
        rated = []
        for w, (plen, gr) in enumerate(zip(lens, good_rates)):
            for j in range(4):  # 4 rated per week >= GROWTH_MIN_RATED_PER_WEEK
                rated.append(_week_sess(w, j, plen, good=(j / 4 < gr)))
        return rated

    def test_drift_detected(self):
        # prompts shrink 200 -> 80, good rate flat
        out = bs_habit_drift(self._weeks([200] * 4 + [80] * 4, [0.75] * 8))
        self.assertTrue(out["gate_passed"])
        self.assertLess(out["metrics"]["late_median_len"],
                        0.75 * out["metrics"]["early_median_len"])

    def test_guard_improved_outcomes_suppress(self):
        out = bs_habit_drift(self._weeks([200] * 4 + [80] * 4,
                                         [0.5] * 4 + [1.0] * 4))
        self.assertFalse(out["gate_passed"])
        self.assertTrue(out["suppressed_by_guard"])

    def test_gate_needs_eight_weeks(self):
        out = bs_habit_drift(self._weeks([200] * 3 + [80] * 3, [0.75] * 6))
        self.assertFalse(out["gate_passed"])
        self.assertFalse(out["suppressed_by_guard"])

    def test_stable_prompts_no_drift(self):
        out = bs_habit_drift(self._weeks([150] * 8, [0.75] * 8))
        self.assertFalse(out["gate_passed"])


class ComputeBlindSpotsTests(unittest.TestCase):
    def test_all_seven_keys_present(self):
        out = compute_blind_spots([], [], [], [], WINDOW_END)
        self.assertEqual(out["schema_version"], 1)
        for k in ("repeated_instructions", "sunk_cost", "switch_tax",
                  "graveyard", "habit_drift", "ask_vs_ship",
                  "interrupt_win_rate"):
            self.assertIn(k, out)
            self.assertFalse(out[k]["gate_passed"])   # empty inputs: all gated


class BlindSpotsWiringTests(unittest.TestCase):
    def test_main_emits_blind_spots_block(self):
        # mirror tests/test_cross_llm_aggregate.py::MainWiringTests: build a
        # tiny transcript-rows jsonl + empty meta dir, run aggregate.py as a
        # subprocess, assert the output JSON has a well-formed blind_spots
        # block. Copy that class's fixture code verbatim and extend the
        # assertions:
        #   data = _json.loads(out_path.read_text())
        #   self.assertIn("blind_spots", data)
        #   self.assertEqual(data["blind_spots"]["schema_version"], 1)
        ...
```

(The `...` is fixture plumbing copied from the existing `MainWiringTests` — same tempdir, same subprocess invocation, plus the two assertions shown.)

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement**

```python
_BS_DRIFT_MIN_WEEKS = 8
_BS_DRIFT_LEN_DROP = 0.75
_BS_DRIFT_GOOD_TOL_PP = 5


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return 0
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def bs_habit_drift(rated):
    """Spec §5 #5 — habit drift: prompt length falling while outcomes are
    not improving. Guard: shorter prompts WITH better outcomes = skill
    gained, suppress (the counterexample guard for this heuristic)."""
    weeks = {}
    for s in rated:
        dt = _parse_dt(s.get("start"))
        if dt is None:
            continue
        weeks.setdefault(week_key(dt), []).append(s)
    eligible = {w: ss for w, ss in weeks.items()
                if len(ss) >= GROWTH_MIN_RATED_PER_WEEK}
    if len(eligible) < _BS_DRIFT_MIN_WEEKS:
        return _bs_result("habit_drift", False, n=len(eligible),
                          reason="fewer than 8 weeks with enough rated sessions")
    ordered = [eligible[w] for w in sorted(eligible)]
    half = len(ordered) // 2
    early = [s for wk in ordered[:half] for s in wk]
    late = [s for wk in ordered[-half:] for s in wk]

    def med_len(ss):
        return _median([s.get("first_prompt_len") or
                        len(s.get("first_prompt") or "") for s in ss])

    def good_rate(ss):
        return 100 * sum(is_good(s["outcome"]) for s in ss) / len(ss)

    el, ll = med_len(early), med_len(late)
    eg, lg = good_rate(early), good_rate(late)
    metrics = {"weeks": len(eligible),
               "early_median_len": round(el), "late_median_len": round(ll),
               "early_good_rate": round(eg, 1), "late_good_rate": round(lg, 1)}
    shortening = el > 0 and ll <= _BS_DRIFT_LEN_DROP * el
    if shortening and lg > eg + _BS_DRIFT_GOOD_TOL_PP:
        return _bs_result("habit_drift", False, metrics=metrics,
                          n=len(eligible), guarded=True,
                          reason="outcomes improved while prompts shortened")
    if not shortening or lg < eg - _BS_DRIFT_GOOD_TOL_PP or lg <= eg + _BS_DRIFT_GOOD_TOL_PP:
        # drift = shortening AND good rate flat-or-worse
        if shortening:
            return _bs_result("habit_drift", True, metrics=metrics,
                              n=len(eligible))
    return _bs_result("habit_drift", False, metrics=metrics, n=len(eligible),
                      reason="no shortening trend")


def compute_blind_spots(sessions, rated, activity_rows, cross_rows, window_end):
    """Phase 2 blind-spot engine (spec §5). Additive analysis-data block;
    every heuristic self-gates and the whole entry ships regardless so the
    renderer (and later phases) can see WHY something was suppressed."""
    return {
        "schema_version": 1,
        "repeated_instructions": bs_repeated_instructions(activity_rows, cross_rows),
        "sunk_cost": bs_sunk_cost(rated),
        "switch_tax": bs_switch_tax(rated, activity_rows, cross_rows),
        "graveyard": bs_graveyard(activity_rows, window_end),
        "habit_drift": bs_habit_drift(rated),
        "ask_vs_ship": bs_ask_vs_ship(rated),
        "interrupt_win_rate": bs_interrupt_win_rate(rated),
    }
```

main() wiring — immediately after `final["ledger"] = compute_ledger(...)`:

```python
    # blind_spots: additive top-level block (Phase 2, spec §5/§7).
    # window_end anchors graveyard staleness to the newest activity seen.
    all_starts = [d for d in (_parse_dt(r.get("start_time"))
                              for r in activity_rows.values()) if d]
    window_end = max(all_starts) if all_starts else datetime.now().astimezone()
    final["blind_spots"] = compute_blind_spots(
        sessions, rated, list(activity_rows.values()), cross_rows, window_end)
```

`docs/SCHEMA-CHANGES.md` — append an entry following the file's existing format: additive top-level `blind_spots` block (schema_version 1, seven heuristic entries each `{id, gate_passed, suppressed_by_guard, n, metrics, reason}`), consumers must treat missing block as "engine not run".

`references/scoring-rubric.md` — append a `## Blind-spot heuristics (v1, provisional)` section following the file's per-dimension template (Rationale paragraph / `Let X = ...` formula / threshold table / insufficient-data sentence) with one subsection per heuristic, the counterexample-guard applicability list from this plan's header, and every constant from the "Provisional v1 thresholds" table marked **provisional v1**.

- [ ] **Step 4: Run tests** — `python3 -m pytest tests/ -q` → PASS (baseline only).

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py docs/SCHEMA-CHANGES.md references/scoring-rubric.md tests/test_blind_spots.py
git commit -m "feat(blind-spots): habit-drift heuristic (#5), engine orchestrator, blind_spots block"
```

---

### Task 8: Leak catalog — `compute_leaks` + `ledger.leaks`

**Files:**
- Modify: `scripts/aggregate.py`
- Modify: `docs/SCHEMA-CHANGES.md` (same commit)
- Test: `tests/test_leaks.py` (create)

**Interfaces:**
- Consumes: `compute_blind_spots` output; `compute_api_equivalent_cost(sessions)` (existing, ~L59-110); rated session rows.
- Produces: `compute_leaks(blind_spots: dict, rated: list[dict], window: dict) -> dict` attached by main() as `final["ledger"]["leaks"]`:

```python
{"window_weeks": float,          # max(window["days"]/7, 1), 1 decimal
 "items": [                      # sorted weekly_cost_usd desc, top 3
   {"type": "repeated_instructions" | "sunk_cost" | "failed_session_burn",
    "weekly_cost_usd": float,    # lower-bound estimate
    "weekly_tokens": int,
    "occurrences": int,          # patterns / pairs / sessions in window
    "evidence": [sid, ...]}]}    # ≤3
```

Catalog v1 (three candidates, each independently gated; "top-3" = all that pass, ranked):
1. `repeated_instructions` — from #1: `weekly_tokens = Σ est_wasted_tokens / weeks`; USD at the blended input rate of the rated pool (reuse `compute_api_equivalent_cost` on a synthetic single-field basis is wrong — instead compute `usd = weekly_tokens / 1e6 * rate` where `rate` = the input $/1M of the most-common model across `rated` `model_counts`, falling back to `_FALLBACK_PRICING["input"]`).
2. `sunk_cost` — from #2: the failed sessions of confirmed pairs; `usd = compute_api_equivalent_cost(failed_sessions) / weeks`.
3. `failed_session_burn` — all `not_achieved` rated sessions EXCLUDING sids already counted in sunk-cost pairs (no double counting); gate `>= _BS_FAILED_BURN_MIN_SESSIONS` (5); `usd = compute_api_equivalent_cost(those) / weeks`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_leaks.py
import unittest
from datetime import datetime, timedelta, timezone

from scripts.aggregate import compute_blind_spots, compute_leaks

BASE = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
WINDOW = {"start": "2026-06-01", "end": "2026-07-11", "days": 40}


def _sess(sid, days, outcome, tokens=40000, prompt="tune the ingestion retry logic"):
    return {"sid": sid, "start": (BASE + timedelta(days=days)).isoformat(),
            "outcome": outcome, "first_prompt": prompt,
            "first_prompt_len": len(prompt), "token_accel": None,
            "duration_min": 60, "total_tokens": tokens,
            "input_tokens": tokens - 4000, "output_tokens": 4000,
            "cache_create_tokens": 0, "cache_read_tokens": 0,
            "model_counts": {"claude-opus-4-6": 10}, "goal_cats": {},
            "git_commits": 0, "interrupts": 0, "friction_counts": {}}


class LeakCatalogTests(unittest.TestCase):
    def test_failed_burn_leak(self):
        rated = ([_sess(f"f{i}", i, "not_achieved") for i in range(6)]
                 + [_sess(f"g{i}", 10 + i, "fully_achieved") for i in range(6)])
        bs = compute_blind_spots(rated, rated, [], [], BASE + timedelta(days=40))
        leaks = compute_leaks(bs, rated, WINDOW)
        types = [i["type"] for i in leaks["items"]]
        self.assertIn("failed_session_burn", types)
        item = next(i for i in leaks["items"] if i["type"] == "failed_session_burn")
        self.assertGreater(item["weekly_cost_usd"], 0)
        self.assertEqual(item["occurrences"], 6)
        self.assertLessEqual(len(item["evidence"]), 3)

    def test_below_floor_no_failed_burn(self):
        rated = ([_sess(f"f{i}", i, "not_achieved") for i in range(4)]
                 + [_sess(f"g{i}", 10 + i, "fully_achieved") for i in range(20)])
        bs = compute_blind_spots(rated, rated, [], [], BASE + timedelta(days=40))
        leaks = compute_leaks(bs, rated, WINDOW)
        self.assertNotIn("failed_session_burn",
                         [i["type"] for i in leaks["items"]])

    def test_ranked_desc_and_max_three(self):
        rated = ([_sess(f"f{i}", i, "not_achieved") for i in range(6)]
                 + [_sess(f"g{i}", 10 + i, "fully_achieved") for i in range(6)])
        bs = compute_blind_spots(rated, rated, [], [], BASE + timedelta(days=40))
        leaks = compute_leaks(bs, rated, WINDOW)
        costs = [i["weekly_cost_usd"] for i in leaks["items"]]
        self.assertEqual(costs, sorted(costs, reverse=True))
        self.assertLessEqual(len(leaks["items"]), 3)

    def test_window_weeks_floor(self):
        leaks = compute_leaks(
            compute_blind_spots([], [], [], [], BASE), [],
            {"start": None, "end": None, "days": 3})
        self.assertEqual(leaks["window_weeks"], 1.0)
        self.assertEqual(leaks["items"], [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure** — ImportError on `compute_leaks`.

- [ ] **Step 3: Implement**

```python
_BS_FAILED_BURN_MIN_SESSIONS = 5


def _dominant_input_rate(rated):
    """Input $/1M of the most-used model across the rated pool; the
    conservative fallback over-reports (same policy as _FALLBACK_PRICING)."""
    counts = {}
    for s in rated:
        for m, n in (s.get("model_counts") or {}).items():
            counts[_normalize_model_id(m)] = counts.get(_normalize_model_id(m), 0) + n
    if counts:
        top = max(counts, key=counts.get)
        if top in PRICING:
            return PRICING[top]["input"]
    return _FALLBACK_PRICING["input"]


def compute_leaks(blind_spots, rated, window):
    """Leak catalog v1 (spec §3 book 3). Lower-bound accounting only:
    every dollar traces to tokens the evidence actually shows (audit
    discipline rule 4). Items are independently gated; 'top 3' is all
    passers ranked by weekly cost."""
    weeks = round(max((window.get("days") or 0) / 7.0, 1.0), 1)
    items = []

    bs1 = blind_spots.get("repeated_instructions") or {}
    if bs1.get("gate_passed"):
        pats = bs1["metrics"]["patterns"]
        tokens_week = int(sum(p["est_wasted_tokens"] for p in pats) / weeks)
        items.append({"type": "repeated_instructions",
                      "weekly_cost_usd": round(
                          tokens_week / 1e6 * _dominant_input_rate(rated), 2),
                      "weekly_tokens": tokens_week,
                      "occurrences": sum(p["occurrences"] for p in pats),
                      "evidence": pats[0]["evidence"]})

    sunk_sids = set()
    bs2 = blind_spots.get("sunk_cost") or {}
    if bs2.get("gate_passed"):
        pair_sids = [p["failed_sid"] for p in bs2["metrics"]["pairs"]]
        sunk_sids = set(pair_sids)
        failed = [s for s in rated if s["sid"] in sunk_sids]
        items.append({"type": "sunk_cost",
                      "weekly_cost_usd": round(
                          compute_api_equivalent_cost(failed) / weeks, 2),
                      "weekly_tokens": int(sum(s.get("total_tokens") or 0
                                               for s in failed) / weeks),
                      "occurrences": len(failed),
                      "evidence": pair_sids[:3]})

    burn = [s for s in rated
            if s["outcome"] == "not_achieved" and s["sid"] not in sunk_sids]
    if len(burn) >= _BS_FAILED_BURN_MIN_SESSIONS:
        items.append({"type": "failed_session_burn",
                      "weekly_cost_usd": round(
                          compute_api_equivalent_cost(burn) / weeks, 2),
                      "weekly_tokens": int(sum(s.get("total_tokens") or 0
                                               for s in burn) / weeks),
                      "occurrences": len(burn),
                      "evidence": [s["sid"] for s in burn[:3]]})

    items.sort(key=lambda i: -(i["weekly_cost_usd"] or 0))
    return {"window_weeks": weeks, "items": items[:3]}
```

main() wiring, right after the blind_spots attachment: `final["ledger"]["leaks"] = compute_leaks(final["blind_spots"], rated, final["ledger"]["window"])`. Note the snapshot hook in `build_html.py` serializes the whole `ledger` block — leaks therefore enter `autopsy-history.jsonl` automatically, which Phase 3's trend ledger wants; no build_html change needed.

`docs/SCHEMA-CHANGES.md`: extend the Phase 2 entry — additive `ledger.leaks` field, shape above, absent = engine not run.

- [ ] **Step 4: Run tests** — `python3 -m pytest tests/test_leaks.py tests/ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/aggregate.py docs/SCHEMA-CHANGES.md tests/test_leaks.py
git commit -m "feat(ledger): leak catalog v1 with lower-bound weekly cost (ledger.leaks)"
```

---

### Task 9: `scripts/praise_lint.py` + build-time warning

**Files:**
- Create: `scripts/praise_lint.py`
- Modify: `scripts/build_html.py` (warning pass over the four LLM-authored markdown inputs; standardize on the `"warning: ..."` stderr prefix)
- Test: `tests/test_praise_lint.py` (create)

**Interfaces:**
- Produces: `find_praise(text: str) -> list[dict]` — scans BOTH locales' word lists regardless of document language (mixed-language narration is common); returns `[{"word": str, "locale": "en"|"zh_TW", "count": int}]` sorted by count desc. Module constants `PRAISE_WORDS_EN: tuple[str]`, `PRAISE_WORDS_ZH: tuple[str]`. `build_html.py` calls `find_praise` on peer-review, ledger-narration, try-this and case-study markdown and prints one stderr line per offending document. Word lists are the single source of truth for the hard tests AND the warning path (spec §2 rule 1, §8).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_praise_lint.py
import unittest

from scripts.praise_lint import PRAISE_WORDS_EN, PRAISE_WORDS_ZH, find_praise


class WordListTests(unittest.TestCase):
    def test_lists_nonempty_and_lowercase(self):
        self.assertGreaterEqual(len(PRAISE_WORDS_EN), 10)
        self.assertGreaterEqual(len(PRAISE_WORDS_ZH), 10)
        for w in PRAISE_WORDS_EN:
            self.assertEqual(w, w.lower())

    def test_no_em_dash_in_zh_list(self):
        for w in PRAISE_WORDS_ZH:
            self.assertNotIn("—", w)


class FindPraiseTests(unittest.TestCase):
    def test_en_word_boundary(self):
        hits = find_praise("This result is impressive, truly world-class.")
        words = {h["word"] for h in hits}
        self.assertIn("impressive", words)
        self.assertIn("world-class", words)

    def test_en_substring_not_flagged(self):
        # "impressively" must not fire the "impressive" entry via substring
        self.assertEqual(
            [h for h in find_praise("compression ratio") if h["word"] == "impressive"],
            [])

    def test_zh_substring_match(self):
        hits = find_praise("這輪產出非常出色，維持水準")
        self.assertIn("非常出色", {h["word"] for h in hits})

    def test_clean_text_empty(self):
        clean = ("Commits per active week: 4.2, above the 3.0 bar. "
                 "本週提交 4.2 次，高於 3.0 的門檻。")
        self.assertEqual(find_praise(clean), [])

    def test_counts_and_ordering(self):
        hits = find_praise("excellent work. excellent choice. superb.")
        self.assertEqual(hits[0]["word"], "excellent")
        self.assertEqual(hits[0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure** — ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# scripts/praise_lint.py
"""Praise-word lint (spec §2 audit-discipline rule 1, §8).

One word list per locale, shared by two consumers: the hard test on demo
fixtures (tests/) and the build-time warning in build_html.py. The lint
flags cheerleading vocabulary — evaluative praise with no number behind
it. It is a WARNING on real builds (prose review stays a human/LLM job);
only the test path is hard.
"""
import re

PRAISE_WORDS_EN = (
    "impressive", "excellent", "amazing", "outstanding", "exceptional",
    "world-class", "stellar", "fantastic", "superb", "remarkable",
    "incredible", "phenomenal", "brilliant", "masterful", "elite",
)

PRAISE_WORDS_ZH = (
    "令人驚豔", "非常出色", "表現出色", "卓越", "頂尖", "亮眼",
    "出類拔萃", "優異", "驚人", "完美", "無可挑剔", "大師級",
    "世界級", "一流", "傑出",
)

_EN_RES = {w: re.compile(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])",
                         re.IGNORECASE)
           for w in PRAISE_WORDS_EN}


def find_praise(text):
    """Scan text against BOTH locales (mixed-language docs are normal).
    Returns [{"word", "locale", "count"}] sorted by count desc."""
    if not isinstance(text, str) or not text:
        return []
    hits = []
    for w, rx in _EN_RES.items():
        n = len(rx.findall(text))
        if n:
            hits.append({"word": w, "locale": "en", "count": n})
    for w in PRAISE_WORDS_ZH:
        n = text.count(w)
        if n:
            hits.append({"word": w, "locale": "zh_TW", "count": n})
    hits.sort(key=lambda h: -h["count"])
    return hits
```

`build_html.py` — after the four markdown inputs are loaded (peer-review ~existing load, `--ledger-narration` ~L181-185, try-this, case-study), add:

```python
    from praise_lint import find_praise  # same-dir import, matches sibling scripts
    for label, md in (("peer-review", peer_review_md),
                      ("ledger-narration", ledger_narration_md),
                      ("try-this", try_this_md),
                      ("case-study", case_study_md)):
        hits = find_praise(md)
        if hits:
            words = ", ".join(f"{h['word']}×{h['count']}" for h in hits[:5])
            print(f"warning: praise-word lint: {label} contains praise "
                  f"vocabulary ({words}) — audit discipline wants numbers "
                  f"before adjectives", file=sys.stderr)
```

(Adapt variable names to build_html.py's actual locals; the import mechanism must match how build_html.py already imports `report_render` — same directory, so `from praise_lint import find_praise` if it does `import report_render`, else mirror exactly. Non-fatal by design: never exit non-zero.)

Add a wiring test to `tests/test_praise_lint.py` if cheap (subprocess with a praise-seeded narration file, assert stderr contains `praise-word lint`), else defer that assertion to the smoke extension in Task 12 — it is covered there either way.

- [ ] **Step 4: Run tests** — `python3 -m pytest tests/test_praise_lint.py tests/ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/praise_lint.py scripts/build_html.py tests/test_praise_lint.py
git commit -m "feat(lint): praise-word lint (en+zh_TW lists) with build-time warning"
```

---

### Task 10: Locale keys for leak ledger + blind spots

**Files:**
- Modify: `scripts/locales.py` (both locale dicts)
- Test: `tests/test_ledger_render.py` (extend the `REQUIRED` key list in `LedgerLocaleKeyTests`)

**Interfaces:**
- Produces: the exact keys below in BOTH locales (Task 11's renderer calls `t(locale, key)` on every one; zh_TW: no em-dash; `_template` suffix = `.format()` placeholders as shown):

| Key | en | zh_TW |
|---|---|---|
| `ledger_leaks_title` | `Leak ledger` | `漏水帳` |
| `ledger_leaks_kicker` | `Where tokens and hours leak` | `token 與時間漏在哪` |
| `ledger_blindspot_label` | `Blind spot` | `盲點` |
| `blindspot_repeated_title` | `Repeated-instruction tax` | `重複指令稅` |
| `blindspot_repeated_template` | `The same instruction was retyped {n} times across {weeks} weeks ({sources})` | `同一條指令在 {weeks} 週內重打了 {n} 次（{sources}）` |
| `blindspot_sunk_title` | `Sunk-cost sessions` | `沉沒成本 session` |
| `blindspot_sunk_template` | `{n} failed sessions were later redone from scratch in under half the time` | `{n} 個失敗 session 後來重開新局，用不到一半時間就完成` |
| `blindspot_switch_title` | `Switch tax` | `切換稅` |
| `blindspot_switch_template` | `Good-outcome rate is {multi}% in multi-tool windows vs {single}% single-tool` | `多工具並行時的良好結果率 {multi}%，單工具時 {single}%` |
| `blindspot_graveyard_title` | `The graveyard` | `墳場` |
| `blindspot_graveyard_template` | `{n} projects received substantive writes, no commit, then went quiet` | `{n} 個專案寫了大量內容、沒有 commit，之後就沒再動過` |
| `blindspot_askship_title` | `Ask vs ship mismatch` | `想做與做成的落差` |
| `blindspot_askship_template` | `{cat} is {ask}% of asks but {ship}% of shipped sessions` | `{cat} 佔提問 {ask}%，但只佔有產出 session 的 {ship}%` |
| `blindspot_interrupt_title` | `Interrupt win rate` | `中斷勝率` |
| `blindspot_interrupt_template` | `Interrupted sessions succeed {i}% of the time vs {b}% baseline` | `被中斷的 session 成功率 {i}%，未中斷基準 {b}%` |
| `ledger_leak_weekly_cost_template` | `≈ ${cost}/week` | `每週約 ${cost}` |
| `ledger_leak_tokens_template` | `{tokens} tokens/week (lower bound)` | `每週 {tokens} tokens（下限值）` |
| `ledger_leak_occurrences_template` | `{n} occurrences in window` | `期間內 {n} 次` |
| `ledger_leak_fix_label` | `Fix` | `修法` |
| `leak_type_repeated_instructions` | `Repeated instructions` | `重複指令` |
| `leak_type_sunk_cost` | `Sunk-cost sessions` | `沉沒成本 session` |
| `leak_type_failed_session_burn` | `Failed-session burn` | `失敗 session 燒掉的量` |
| `leak_fix_repeated_instructions` | `Move this instruction into CLAUDE.md or memory so every session inherits it.` | `把這條指令搬進 CLAUDE.md 或 memory，讓每個 session 自動繼承。` |
| `leak_fix_sunk_cost` | `Set a bail-out rule: when a session stalls, restart with a tighter brief instead of pushing on.` | `訂一條停損規則：session 卡住就開新的，附上更明確的任務描述，不要硬撐。` |
| `leak_fix_failed_session_burn` | `Write the acceptance check into the first prompt so failure surfaces early, not after the burn.` | `把驗收條件寫進第一句 prompt，讓失敗早點浮出來，而不是燒完才發現。` |
| `ledger_graveyard_exhibit_title` | `Graveyard: written, never shipped` | `墳場：寫了，沒出貨` |
| `ledger_graveyard_untouched_template` | `untouched for {days} days` | `已 {days} 天沒動` |
| `ledger_graveyard_writes_template` | `{writes} file edits in final session` | `最後一個 session 改了 {writes} 次檔案` |
| `ledger_leaks_exhibit_title` | `Top leaks by estimated weekly cost` | `每週估計成本最高的漏水` |
| `ledger_secondary_findings` | `Secondary findings` | `次要發現` |
| `ledger_source_blind_spots` | `blind-spot engine, scoring pool` | `盲點引擎，計分池` |

- [ ] **Step 1: Write the failing test** — extend `LedgerLocaleKeyTests.REQUIRED` in `tests/test_ledger_render.py` with all 31 keys above.
- [ ] **Step 2: Run** — `python3 -m pytest tests/test_ledger_render.py -q` → FAIL (missing keys).
- [ ] **Step 3: Implement** — add all keys to both dicts in `scripts/locales.py`, grouped under a `# --- Phase 2: leak ledger + blind spots ---` comment in each locale, values exactly as tabled.
- [ ] **Step 4: Run** — `python3 -m pytest tests/test_ledger_render.py tests/test_locales.py -q` → PASS (key-set parity + em-dash ban included).
- [ ] **Step 5: Commit**

```bash
git add scripts/locales.py tests/test_ledger_render.py
git commit -m "feat(i18n): leak-ledger and blind-spot chrome strings (en + zh_TW)"
```

---

### Task 11: Renderer — leak ledger section, blind-spot openers, exhibit-counter refactor, narration book

**Files:**
- Modify: `scripts/report_render.py`
- Test: `tests/test_ledger_render.py` (extend)

**Interfaces:**
- Consumes: `analysis["blind_spots"]`, `analysis["ledger"]["leaks"]`, locale keys from Task 10, `_exhibit`/`esc`/`inline_md`/`t`, narration books.
- Produces:
  - `_parse_ledger_narration` books dict gains `"leak-ledger": ""` (the `# leak-ledger` heading).
  - `_build_output_ledger(ledger, narration, locale, exhibit_no, blind_spots=None)` — adds a graveyard opener callout + graveyard exhibit when `blind_spots["graveyard"]["gate_passed"]`.
  - `_build_team_ledger(cross_llm, narration, locale, exhibit_no, blind_spots=None)` — adds a switch-tax opener callout when gate passed.
  - `_build_leak_ledger(ledger, blind_spots, narration, locale, exhibit_no) -> str` — section `id="ledger-leaks"`; suppressed entirely (`""`) when `leaks["items"]` is empty AND neither opener blind spot passed.
  - **Exhibit-counter refactor**: `render()` owns `exhibit_no = count(1)`; `_build_output_ledger` takes it (Exhibit 1 stops being hard-coded); `_build_team_ledger` stops creating its own `count(2)`; `_build_leak_ledger` continues the sequence. Numbering is now purely order-of-appearance.
  - Opening band: findings list gains the leak-ledger book's opener line (third finding) when present.
  - New CSS under the direction-C block: `.c-blindspot` (gold left border, gold label chip, ink text), `.c-blindspot-metric` (tabular-nums; wrap negative values in the existing negative-red class), `.c-leak-card`, `.c-leak-cost` (gold number), `.c-leak-fix` (hairline-topped fix line), `.c-secondary` (smaller secondary-findings list).

Structure of `_build_leak_ledger` (complete — adapt only helper-call spellings to the file):

```python
def _build_leak_ledger(ledger, blind_spots, narration, locale, exhibit_no):
    """Leak ledger (spec §3 book 3), SELF only. Openers: repeated-instruction
    tax (#1) + sunk-cost (#2). Body: top-3 leak cards. Secondary findings:
    ask-vs-ship (#6) + interrupt win-rate (#7). Habit drift (#5) is computed
    but renders in Phase 3's trend ledger. Whole section suppressed when
    nothing passes a gate (spec §10 — no apologetic placeholders)."""
    bs = blind_spots or {}
    leaks = (ledger or {}).get("leaks") or {}
    items = leaks.get("items") or []
    bs1, bs2 = bs.get("repeated_instructions") or {}, bs.get("sunk_cost") or {}
    if not items and not bs1.get("gate_passed") and not bs2.get("gate_passed"):
        return ""
    title = _first_line(narration.get("leak-ledger", "")) or t(locale, "ledger_leaks_title")
    prose = _rest_lines(narration.get("leak-ledger", ""))
    out = [f'<section class="c-section" id="ledger-leaks">',
           f'<div class="c-kicker">{esc(t(locale, "ledger_leaks_kicker"))}</div>',
           f"<h2>{inline_md(title)}</h2>"]
    if prose:
        out.append(f'<div class="c-prose">{inline_md(prose)}</div>')
    # openers
    if bs1.get("gate_passed"):
        p = bs1["metrics"]["patterns"][0]
        out.append(_blindspot_callout(
            locale, "blindspot_repeated_title",
            t(locale, "blindspot_repeated_template").format(
                n=p["occurrences"], weeks=p["weeks"],
                sources=", ".join(p["sources"])),
            detail=esc(p["exemplar"])))
    if bs2.get("gate_passed"):
        out.append(_blindspot_callout(
            locale, "blindspot_sunk_title",
            t(locale, "blindspot_sunk_template").format(n=bs2["n"])))
    # leak cards exhibit
    if items:
        cards = []
        for it in items:
            cost = t(locale, "ledger_leak_weekly_cost_template").format(
                cost=f"{it['weekly_cost_usd']:.2f}")
            cards.append(
                '<div class="c-leak-card">'
                f'<div class="c-leak-type">{esc(t(locale, "leak_type_" + it["type"]))}</div>'
                f'<div class="c-leak-cost">{esc(cost)}</div>'
                f'<div class="c-leak-meta">{esc(t(locale, "ledger_leak_tokens_template").format(tokens=f"{it['weekly_tokens']:,}"))}'
                f' · {esc(t(locale, "ledger_leak_occurrences_template").format(n=it["occurrences"]))}</div>'
                f'<div class="c-leak-fix"><span>{esc(t(locale, "ledger_leak_fix_label"))}</span> '
                f'{esc(t(locale, "leak_fix_" + it["type"]))}</div></div>')
        out.append(_exhibit(next(exhibit_no),
                            t(locale, "ledger_leaks_exhibit_title"),
                            '<div class="c-leak-cards">' + "".join(cards) + "</div>",
                            t(locale, "ledger_source_blind_spots"), locale))
    # secondary findings (#6, #7)
    sec = []
    bs6, bs7 = bs.get("ask_vs_ship") or {}, bs.get("interrupt_win_rate") or {}
    if bs6.get("gate_passed"):
        g = bs6["metrics"]["top_gap"]
        sec.append(t(locale, "blindspot_askship_template").format(
            cat=g["category"], ask=g["ask_share_pct"], ship=g["ship_share_pct"]))
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


def _blindspot_callout(locale, title_key, sentence, detail=None):
    d = f'<div class="c-blindspot-detail">{detail}</div>' if detail else ""
    return ('<div class="c-blindspot">'
            f'<span class="c-blindspot-label">{esc(t(locale, "ledger_blindspot_label"))}</span>'
            f'<strong>{esc(t(locale, title_key))}</strong>'
            f'<div class="c-blindspot-metric">{esc(sentence)}</div>{d}</div>')
```

Graveyard opener + exhibit inside `_build_output_ledger` (when `blind_spots["graveyard"]["gate_passed"]`): callout via `_blindspot_callout(locale, "blindspot_graveyard_title", t(locale, "blindspot_graveyard_template").format(n=bs4["n"]))`, then an exhibit table — one row per `items[]` entry: `esc(project_key)` / `t(...untouched_template).format(days=...)` / `t(...writes_template).format(writes=...)`, title `ledger_graveyard_exhibit_title`, source `ledger_source_blind_spots`. Switch-tax opener inside `_build_team_ledger`: `_blindspot_callout(locale, "blindspot_switch_title", t(locale, "blindspot_switch_template").format(multi=..., single=...))` — wrap the worse rate in the negative-red class only when `multi < single`.

`render()` wiring (SELF branch, ~L3349-3363): create `exhibit_no = count(1)`, read `blind_spots = analysis.get("blind_spots") or {}`, thread both through the three builders, append `_build_leak_ledger(...)` after the team ledger.

- [ ] **Step 1: Write the failing tests** — extend `tests/test_ledger_render.py` following its existing `CROSS`/`LEDGER`/`NARR` fixture style:
  - `LeakLedgerRenderTests`: gate-passing `blind_spots` + `ledger.leaks` fixture → SELF html contains `id="ledger-leaks"`, the exemplar text escaped (`&lt;script&gt;` if the fixture exemplar carries an XSS marker — include one), a `c-leak-cost` with the formatted cost, the fix line, secondary-findings entries; all-gates-failed fixture → no `id="ledger-leaks"` anywhere.
  - `GraveyardOpenerTests`: gate-passing graveyard → output-ledger section contains the callout + exhibit rows; failed gate → absent.
  - `SwitchTaxOpenerTests`: same pattern on the team ledger.
  - `ExhibitNumberingTests`: with graveyard + leaks all present, exhibit numbers in document order are strictly consecutive starting at 1 (regex `Exhibit\s+(\d+)` over the html, or the locale-equivalent label — reuse how existing tests match exhibit labels).
  - `NarrationLeakBookTests`: `# leak-ledger` book's first line becomes the section h2 AND appears as a finding in the opening band; missing book → locale fallback title, no fabricated prose.
  - `HRAbsenceTests`: HR render of the same analysis → no `ledger-leaks`, no `c-blindspot`, no graveyard text.
- [ ] **Step 2: Run** — new tests FAIL.
- [ ] **Step 3: Implement** — code above + CSS + `_parse_ledger_narration` book + opening-band third finding + counter refactor; update any existing tests that asserted the old hard-coded exhibit numbers.
- [ ] **Step 4: Run** — `python3 -m pytest tests/test_ledger_render.py tests/ -q` → PASS (baseline only).
- [ ] **Step 5: Commit**

```bash
git add scripts/report_render.py tests/test_ledger_render.py
git commit -m "feat(render): leak ledger section, blind-spot openers, order-of-appearance exhibit numbering"
```

---

### Task 12: Demo data injections + smoke + SKILL.md

**Files:**
- Modify: `scripts/generate_demo_data.py`
- Modify: `tests/test_demo_data.py`, `tests/smoke_test.py`
- Modify: `SKILL.md`

**Interfaces / injections (deterministic — never rely on incidental randomness):**
1. **Repeated instruction (#1)**: module constant `DEMO_REPEATED_INSTRUCTION = "Reply in zh-TW, run the full pytest suite before claiming done, and never push without asking"`. Force it as `first_prompt` for 8 Claude sessions spread over ≥4 distinct weeks (pick by index, not random), 3 codex sessions and 2 grok sessions (append to their generators using their existing line formats).
2. **Sunk-cost pairs (#2)**: 3 engineered pairs — failed session: facet `outcome="not_achieved"`, transcript with ≥6 assistant messages whose `usage.output_tokens` triple in the second half (so scanned `token_accel ≥ 1.5`), duration 120, prompt `f"refactor the {name} export pipeline to stream batches"`; retry 1-2 days later: `fully_achieved`, similar prompt (append one word), duration ≤ 50, flat token curve. Both need session-meta + facets + transcripts so they enter the scoring pool.
3. **Graveyard (#4)**: 2 dedicated projects (`legacy-migration`, `internal-docs-site`) whose only sessions are 25-40 days old with `tool_counts={"Edit": 9, "Write": 3, ...}`, `git_commits=0`, facets optional; no newer sessions in those projects.
4. Leave #3/#5/#6/#7 to incidental data (their unit tests are deterministic; demo assertions for them check well-formedness only, to avoid flaky gates on unseeded randomness).

Tests to add in `tests/test_demo_data.py` (follow its existing structure — it runs against the generated tree; regenerate first): run the real pipeline pieces (`scan_transcripts` + `aggregate.compute_*` or a subprocess `aggregate.py` run) over the demo tree and assert `blind_spots["repeated_instructions"]["gate_passed"]`, `["sunk_cost"]["gate_passed"]`, `["graveyard"]["gate_passed"]` are all True and `ledger["leaks"]["items"]` is non-empty. This is the spec §11 "hard test on demo fixtures" for the engine.

Smoke extensions (`tests/smoke_test.py`):
- Write `# leak-ledger` book into the narration fixture (with an XSS payload line) → assert SELF html contains `id="ledger-leaks"` and never the raw `<script>` payload; assert HR html contains neither `ledger-leaks` nor `c-blindspot`.
- Seed one praise word (e.g. `impressive`) into the narration fixture → assert the SELF build's captured stderr contains `praise-word lint`.
- Keep the existing `GROK_PRIVATE_MARKER` both-outputs assertion untouched (the marker appears once, below the #1 gate, so it can never surface via the leak ledger).

SKILL.md edits:
- Step 3b: add `# leak-ledger` to the narration template + one instruction line ("opener claim states the single biggest leak with its weekly number; the audit-discipline rules above apply; the praise-word lint will warn on cheerleading vocabulary").
- Audience-conditional table: add rows `Leak ledger` (SELF rendered / HR absent) and `Blind-spot openers` (SELF rendered / HR absent).
- Step 4 (build) note: praise-lint stderr warnings are expected output to read and act on, not errors.

- [ ] **Step 1: Write failing tests** (demo-data gate assertions + smoke additions)
- [ ] **Step 2: Run** — `python3 scripts/generate_demo_data.py && python3 -m pytest tests/test_demo_data.py -q` → new tests FAIL.
- [ ] **Step 3: Implement injections + SKILL.md edits**
- [ ] **Step 4: Full verification**

Run: `python3 scripts/generate_demo_data.py && python3 -m pytest tests/ -q && python3 tests/smoke_test.py && node --test tests/chart_layout.test.mjs`
Expected: everything green except the 2 known baseline failures; smoke exits 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_demo_data.py tests/test_demo_data.py tests/smoke_test.py SKILL.md
git commit -m "feat(demo): deterministic blind-spot fixtures; smoke + SKILL.md for leak ledger"
```

---

## Completion workflow (after all tasks)

1. Run `/simplify` on the branch diff (repo rule), fold in fixes.
2. Feed the implementation-notes file into the maintainer's private review workflow: independent cross-model review + security review, both must reach zero critical/advisory findings before merge.
3. PR to `main` titled `feat: V5 Phase 2 — leak ledger, blind-spot engine, praise-word lint`; PR body lists deviations from this plan (from implementation-notes).
4. After merge: update private project notes — Phase 2 done, Phase 3 next (trend ledger UI + badges + recruiter rebuild); remove the temporary implementation-notes file.

## Out of scope for Phase 2 (do not do)

- Trend ledger UI, badges, recruiter version (Phase 3).
- Rendering habit drift (#5) — computed only.
- Fuzzy/near-duplicate prompt matching (v1 is exact-match by decision #2).
- Phase 1 deferred minors (`.c-src-N` palette >6 sources, example-output regeneration, team-ledger row-schema constants) — except the exhibit-counter refactor, which Task 11 needs and absorbs.
- Backfilling the missing D9 section in `references/scoring-rubric.md` (noted as a known gap; separate docs commit if wanted).
- Antigravity parsing, population comparisons, Windows paths (spec §12).

## Self-review record

- **Spec coverage**: §3 book 3 (leak ledger) → Tasks 8+11; §5 all 7 heuristics + gates + guard → Tasks 3-7; §5 placement (1-2 open leak book, 3 opens team, 4 opens output, 6-7 secondary in leak body) → Task 11; #5 opens trend book which is Phase 3 → computed Task 7, render deferred (decision #3); §2 rule 1 + §8 praise lint → Task 9; §7 additive schema + SCHEMA-CHANGES same-commit → Tasks 7-8; §10 suppression → gating idioms in Tasks 3-8, renderer early-returns Task 11; §11 testing lines (heuristic threshold + guard tests, praise lint both paths, locale parity, privacy assertions, smoke with cross-LLM present) → Tasks 3-12; §13 defaults (14-day horizon) → constants table.
- **Placeholder scan**: three `...` remain, all deliberately scoped to copy-exact-existing-code fixture/plumbing points with the copy source named (`_multi_source_intervals` sweep invocation; scan-transcripts fixture helper; MainWiringTests fixture). No TBD/TODO/handle-edge-cases language.
- **Type consistency**: heuristic return shape `_bs_result` defined Task 3, consumed Tasks 4-8 and 11 with matching keys; `compute_blind_spots(sessions, rated, activity_rows, cross_rows, window_end)` signature identical in Tasks 7 (def), 8 (tests) ; leak item keys (`type/weekly_cost_usd/weekly_tokens/occurrences/evidence`) match between Task 8 and Task 11's renderer; locale keys in Task 11's code all exist in Task 10's table (`ledger_leaks_title/kicker`, `ledger_blindspot_label`, `blindspot_*_title/template` ×6, `ledger_leak_*` ×4, `leak_type_*` ×3, `leak_fix_*` ×3, `ledger_graveyard_*` ×3, `ledger_leaks_exhibit_title`, `ledger_secondary_findings`, `ledger_source_blind_spots`).
