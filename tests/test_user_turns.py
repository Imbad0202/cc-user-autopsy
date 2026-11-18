"""User-turn capture (findings-first Phase 1): every prompt the user typed
is written to a working file, and that text reaches no other output."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts import scan_codex, scan_grok, scan_transcripts  # noqa: E402
from scripts.cross_llm_common import (  # noqa: E402
    ASSISTANT_TAIL_CAP, TURN_TEXT_CAP, make_user_turn, write_private_text)
from scripts.report_render import _source_card_html  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"
DEMO = Path("/tmp/cc-autopsy-demo")


def _user(content, ts, **extra):
    return {"type": "user", "timestamp": ts,
            "message": {"role": "user", "content": content}, **extra}


def _asst(content, ts):
    return {"type": "assistant", "timestamp": ts,
            "message": {"role": "assistant", "model": "m", "content": content,
                        "usage": {"input_tokens": 1, "output_tokens": 1}}}


def _write_transcript(td, records, sid=SID):
    d = Path(td) / "-home-user-projects-demo"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n",
                 encoding="utf-8")
    return p


def _ts(n):
    return f"2026-04-01T10:{n:02d}:00.000Z"


class MakeUserTurnTests(unittest.TestCase):
    def test_long_text_keeps_both_ends_and_its_true_length(self):
        long = "HEAD " + "x" * (TURN_TEXT_CAP + 50) + " fix the last one TAIL"
        t = make_user_turn("codex", "s", "/p", "ts", 0, long,
                           prev_assistant="y" * (ASSISTANT_TAIL_CAP + 50) + "END")
        self.assertTrue(t["text"].startswith("HEAD "))
        self.assertTrue(t["text"].endswith("fix the last one TAIL"))
        self.assertIn("characters omitted", t["text"])
        self.assertLess(len(t["text"]), TURN_TEXT_CAP + 60)
        self.assertEqual(t["text_len"], len(long))
        short = make_user_turn("codex", "s", "/p", "ts", 0, "x" * TURN_TEXT_CAP)
        self.assertEqual(short["text"], "x" * TURN_TEXT_CAP)
        self.assertEqual(len(t["prev_assistant_tail"]), ASSISTANT_TAIL_CAP)
        self.assertTrue(t["prev_assistant_tail"].endswith("END"))

    def test_blank_assistant_gives_no_tail(self):
        self.assertIsNone(
            make_user_turn("grok", "s", "/p", "ts", 0, "hi",
                           prev_assistant="  ")["prev_assistant_tail"])


class PrivateFileTests(unittest.TestCase):
    def test_new_file_is_owner_only_whatever_the_umask(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "sub" / "turns.jsonl"
            old = os.umask(0o022)
            try:
                write_private_text("x\n", out)
            finally:
                os.umask(old)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)

    def test_existing_loose_file_is_tightened(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "turns.jsonl"
            out.write_text("old")
            os.chmod(out, 0o644)
            write_private_text("new", out)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
            self.assertEqual(out.read_text(encoding="utf-8"), "new")


class ClaudeTurnTests(unittest.TestCase):
    def scan(self, records):
        with tempfile.TemporaryDirectory() as td:
            return scan_transcripts.scan_one(_write_transcript(td, records))

    def test_only_typed_prompts_become_turns(self):
        row = self.scan([
            _user("first ask", _ts(0)),
            _user("<system-reminder>injected</system-reminder>", _ts(1)),
            _user("<command-name>/model</command-name>", _ts(1)),
            _user("<local-command-stdout>ok</local-command-stdout>", _ts(1)),
            _user("<some-future-tag>added by a later harness</some-future-tag>",
                  _ts(1)),
            _user("meta note", _ts(1), isMeta=True),
            _user("side", _ts(1), isSidechain=True),
            _user("This session is being continued from a previous conversation…",
                  _ts(1)),
            _user([{"type": "tool_result", "tool_use_id": "t", "content": "out"}],
                  _ts(2)),
            _asst([{"type": "text", "text": "Which file?"}], _ts(3)),
            _user([{"type": "text", "text": "<system-reminder>r</system-reminder>"},
                   {"type": "text", "text": "the parser"}], _ts(4)),
        ])
        turns = row["_user_turns"]
        self.assertEqual([t["text"] for t in turns], ["first ask", "the parser"])
        self.assertEqual([t["turn_index"] for t in turns], [0, 1])
        self.assertIsNone(turns[0]["prev_assistant_tail"])
        self.assertEqual(turns[1]["prev_assistant_tail"], "Which file?")
        self.assertTrue(row["multi_turn"])

    def test_pasted_html_is_still_the_users_text(self):
        kept = ["<div>why is this centered?</div>", "<b>bold</b> or not",
                "<my-widget> does not render, why?",
                "<my-widget>x</my-widget> shows nothing"]
        row = self.scan([_user(t, _ts(i)) for i, t in enumerate(kept)])
        self.assertEqual([t["text"] for t in row["_user_turns"]], kept)

    def test_block_wholly_wrapped_in_hyphenated_tags_is_injected(self):
        row = self.scan([
            _user("<command-message>x</command-message>\n"
                  "<command-name>/x</command-name>", _ts(0)),
            _user("<new-harness-tag attr='1'>later addition</new-harness-tag>",
                  _ts(1))])
        self.assertEqual(row["_user_turns"], [])

    def test_a_tool_call_alone_is_not_a_reply(self):
        row = self.scan([
            _user("go", _ts(0)),
            _asst([{"type": "tool_use", "id": "1", "name": "Bash",
                    "input": {"command": "ls"}}], _ts(1)),
            _user("and then?", _ts(2))])
        self.assertEqual(len(row["_user_turns"]), 2)
        self.assertFalse(row["multi_turn"])

    def test_records_without_a_message_object_do_not_stop_the_scan(self):
        row = self.scan([
            {"type": "user", "timestamp": _ts(0), "message": None},
            {"type": "assistant", "timestamp": _ts(1), "message": "broken"},
            {"type": "user", "timestamp": _ts(2)},
            _user("still here", _ts(3))])
        self.assertEqual([t["text"] for t in row["_user_turns"]], ["still here"])

    def test_two_prompts_with_no_reply_between_is_not_multi_turn(self):
        row = self.scan([_user("a", _ts(0)), _user("b", _ts(1)),
                         _asst([{"type": "text", "text": "ok"}], _ts(2))])
        self.assertEqual(len(row["_user_turns"]), 2)
        self.assertFalse(row["multi_turn"])

    def test_after_interrupt_flags_the_next_typed_turn_only(self):
        row = self.scan([
            _user("go", _ts(0)),
            _asst([{"type": "text", "text": "working"}], _ts(1)),
            _user("[Request interrupted by user]", _ts(2)),
            _user("stop, wrong file", _ts(3)),
            _asst([{"type": "text", "text": "ok"}], _ts(4)),
            _user("thanks", _ts(5)),
        ])
        turns = row["_user_turns"]
        self.assertEqual([t["text"] for t in turns],
                         ["go", "stop, wrong file", "thanks"])
        self.assertEqual([t["after_interrupt"] for t in turns],
                         [False, True, False])

    def test_bash_calls_to_other_clis_are_recorded(self):
        row = self.scan([
            _user("review", _ts(0)),
            _asst([{"type": "tool_use", "id": "1", "name": "Bash",
                    "input": {"command": 'codex exec "review"'}},
                   {"type": "tool_use", "id": "2", "name": "Bash",
                    "input": {"command": "cat codex-notes.md"}},
                   {"type": "tool_use", "id": "3", "name": "Read",
                    "input": {"command": "grok -p x"}}], _ts(1)),
        ])
        self.assertEqual(row["cli_launches"],
                         [{"target": "codex", "ts": _ts(1), "until": None}])

    def test_launch_records_when_its_result_came_back(self):
        row = self.scan([
            _user("review", _ts(0)),
            _asst([{"type": "tool_use", "id": "call-1", "name": "Bash",
                    "input": {"command": "codex review"}},
                   {"type": "tool_use", "id": "call-2", "name": "Bash",
                    "input": {"command": "ls"}}], _ts(1)),
            _user([{"type": "tool_result", "tool_use_id": "call-2",
                    "content": "files"}], _ts(2)),
            _user([{"type": "tool_result", "tool_use_id": "call-1",
                    "content": "review text"}], _ts(7)),
        ])
        self.assertEqual(row["cli_launches"],
                         [{"target": "codex", "ts": _ts(1), "until": _ts(7)}])

    def test_sidechain_shell_calls_count_but_sidechain_text_does_not(self):
        side = _asst([{"type": "text", "text": "side thread reply"},
                      {"type": "tool_use", "id": "1", "name": "Bash",
                       "input": {"command": "codex review"}}], _ts(1))
        side["isSidechain"] = True
        row = self.scan([_user("go", _ts(0)), side, _user("again", _ts(2))])
        self.assertEqual([e["target"] for e in row["cli_launches"]], ["codex"])
        self.assertFalse(row["multi_turn"])
        self.assertIsNone(row["_user_turns"][1]["prev_assistant_tail"])

    def test_subagent_file_launches_merge_into_the_parent_row(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "projects"
            _write_transcript(proj, [
                _user("review it", _ts(0)),
                _asst([{"type": "text", "text": "delegating"}], _ts(1))])
            agent = [dict(_asst([{"type": "tool_use", "id": "1", "name": "Bash",
                                  "input": {"command": 'codex exec "review"'}}],
                                _ts(2)), sessionId=SID, isSidechain=True)]
            (proj / "-home-user-projects-demo" / "agent-abc123.jsonl").write_text(
                "\n".join(json.dumps(r) for r in agent) + "\n", encoding="utf-8")
            rows = Path(td) / "rows.jsonl"
            subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "scan_transcripts.py"),
                 "--projects-dir", str(proj), "--output", str(rows)],
                check=True, capture_output=True)
            got = [json.loads(l) for l in rows.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["cli_launches"],
                         [{"target": "codex", "ts": _ts(2), "until": None}])

    def test_own_cli_call_is_recorded_too(self):
        row = self.scan([
            _user("ask a fresh one", _ts(0)),
            _asst([{"type": "tool_use", "id": "1", "name": "Bash",
                    "input": {"command": "claude -p 'second opinion'"}}], _ts(1))])
        self.assertEqual([e["target"] for e in row["cli_launches"]], ["claude"])

    def _run_scan(self, td, records_by_sid, *extra):
        proj = Path(td) / "projects"
        for sid, records in records_by_sid.items():
            _write_transcript(proj, records, sid=sid)
        rows, turns = Path(td) / "rows.jsonl", Path(td) / "turns.jsonl"
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scan_transcripts.py"),
             "--projects-dir", str(proj), "--output", str(rows),
             "--user-turns-output", str(turns), *extra],
            capture_output=True, text=True)
        return proc, rows, turns

    def test_turns_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as td:
            proc, _, turns = self._run_scan(td, {SID: [_user("hi", _ts(0))]})
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(stat.S_IMODE(turns.stat().st_mode), 0o600)

    def test_same_path_for_both_outputs_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "projects"
            _write_transcript(proj, [_user("hi", _ts(0))])
            same = Path(td) / "out.jsonl"
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "scan_transcripts.py"),
                 "--projects-dir", str(proj), "--output", str(same),
                 "--user-turns-output", str(Path(td) / "." / "out.jsonl")],
                capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("same file", proc.stderr)
            self.assertFalse(same.exists())

    def test_filtered_out_sessions_leave_no_turns(self):
        other = "99999999-2222-3333-4444-555555555555"
        with tempfile.TemporaryDirectory() as td:
            proc, rows, turns = self._run_scan(td, {
                SID: [_user("KEPT one", _ts(0)),
                      _asst([{"type": "text", "text": "a"}], _ts(1)),
                      _asst([{"type": "text", "text": "b"}], _ts(2))],
                other: [_user("DROPPED one", _ts(0)),
                        _asst([{"type": "text", "text": "a"}], _ts(1))],
            }, "--min-assistant-msgs", "2")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(rows.read_text(encoding="utf-8").splitlines()), 1)
            self.assertIn("KEPT one", turns.read_text(encoding="utf-8"))
            self.assertNotIn("DROPPED one", turns.read_text(encoding="utf-8"))

    def test_cli_writes_turns_file_and_strips_them_from_rows(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "projects"
            _write_transcript(proj, [
                _user("SECRET_TYPED_TEXT one", _ts(0)),
                _asst([{"type": "text", "text": "ok"}], _ts(1)),
                _user("SECRET_TYPED_TEXT two", _ts(2))])
            rows, turns = Path(td) / "rows.jsonl", Path(td) / "turns.jsonl"
            base = [sys.executable, str(REPO_ROOT / "scripts" / "scan_transcripts.py"),
                    "--projects-dir", str(proj), "--output", str(rows)]
            subprocess.run(base, check=True, capture_output=True)
            self.assertFalse(turns.exists())
            without_flag = rows.read_text(encoding="utf-8")
            subprocess.run(base + ["--user-turns-output", str(turns)],
                           check=True, capture_output=True)
            self.assertEqual(rows.read_text(encoding="utf-8"), without_flag)
            row = json.loads(without_flag.splitlines()[0])
            self.assertNotIn("_user_turns", row)
            self.assertNotIn("SECRET_TYPED_TEXT two", without_flag)
            got = [json.loads(l) for l in turns.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([t["text"] for t in got],
                             ["SECRET_TYPED_TEXT one", "SECRET_TYPED_TEXT two"])
            self.assertEqual({t["source"] for t in got}, {"claude"})
            self.assertEqual({t["session_id"] for t in got}, {SID})


def _codex_line(ts, type_, payload):
    return json.dumps({"timestamp": ts, "type": type_, "payload": payload})


def _rollout(td, lines):
    p = Path(td) / "2026" / "04" / "01" / "rollout-2026-04-01T10-00-00-t.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class CodexTurnTests(unittest.TestCase):
    def scan(self, header, body):
        with tempfile.TemporaryDirectory() as td:
            turns = []
            row, _ = scan_codex.scan_one(_rollout(td, [
                _codex_line(_ts(0), "session_meta",
                            {"id": "cx", "cwd": "/w", **header})] + body), turns)
            return row, turns

    def test_turns_carry_the_reply_they_answer(self):
        row, turns = self.scan({"source": "cli"}, [
            _codex_line(_ts(1), "event_msg",
                        {"type": "user_message", "message": "convert it"}),
            _codex_line(_ts(2), "event_msg",
                        {"type": "agent_message", "message": "Done. Keep order?"}),
            _codex_line(_ts(3), "event_msg",
                        {"type": "user_message", "message": "yes"}),
        ])
        self.assertEqual([t["text"] for t in turns], ["convert it", "yes"])
        self.assertIsNone(turns[0]["prev_assistant_tail"])
        self.assertEqual(turns[1]["prev_assistant_tail"], "Done. Keep order?")
        self.assertEqual(row["launch_source"], "cli")
        self.assertTrue(row["multi_turn"])
        self.assertNotIn("_user_turns", row)

    def test_header_source_forms(self):
        body = [_codex_line(_ts(1), "event_msg",
                            {"type": "user_message", "message": "x"})]
        self.assertEqual(self.scan({"source": "Exec"}, body)[0]["launch_source"],
                         "exec")
        self.assertEqual(
            self.scan({"source": {"subagent": "review"}}, body)[0]["launch_source"],
            "subagent")
        for other in ({}, {"something": "else"}, 7):
            self.assertIsNone(self.scan({"source": other}, body)[0]["launch_source"])
        self.assertIsNone(self.scan({}, body)[0]["launch_source"])

    def test_calls_naming_claude_are_recorded_whatever_the_argument_shape(self):
        def call(args, name="shell"):
            return _codex_line(_ts(2), "response_item",
                               {"type": "function_call", "name": name,
                                "arguments": args})
        hits = [
            call(json.dumps({"command": ["bash", "-lc", "claude -p 'hi'"]})),
            call(json.dumps({"cmd": "claude -p hi"}), name="exec_command"),
            call(json.dumps({"command": "cd /w\nclaude -p hi"})),
            call("claude -p not-json"),
        ]
        misses = [
            call(json.dumps({"command": "cat claude-notes.md"})),
            call(json.dumps({"command": "ls ~/.claude/projects"})),
            _codex_line(_ts(2), "response_item",
                        {"type": "function_call", "name": "shell"}),
        ]
        row, _ = self.scan({}, [
            _codex_line(_ts(1), "event_msg",
                        {"type": "user_message", "message": "x"})] + hits + misses)
        self.assertEqual([e["target"] for e in row["cli_launches"]],
                         ["claude"] * len(hits))

    def test_launch_window_closes_at_the_call_output(self):
        row, _ = self.scan({}, [
            _codex_line(_ts(1), "event_msg",
                        {"type": "user_message", "message": "x"}),
            _codex_line(_ts(2), "response_item",
                        {"type": "function_call", "name": "shell", "call_id": "c1",
                         "arguments": json.dumps({"command": "claude -p hi"})}),
            _codex_line(_ts(9), "response_item",
                        {"type": "function_call_output", "call_id": "c1",
                         "output": "done"}),
        ])
        ev = row["cli_launches"][0]
        self.assertEqual(ev["target"], "claude")
        self.assertIsNotNone(ev["until"])
        self.assertGreater(ev["until"], ev["ts"])

    def test_scan_one_without_turns_list_still_works(self):
        with tempfile.TemporaryDirectory() as td:
            row, errors = scan_codex.scan_one(_rollout(td, [
                _codex_line(_ts(0), "session_meta", {"id": "cx", "cwd": "/w"}),
                _codex_line(_ts(1), "event_msg",
                            {"type": "user_message", "message": "x"})]))
        self.assertEqual(errors, 0)
        self.assertFalse(row["multi_turn"])


class GrokTurnTests(unittest.TestCase):
    def test_bash_rows_are_not_turns(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "%2Fhome%2Fuser%2Fprojects%2Fdemo"
            d.mkdir()
            recs = [
                {"timestamp": "2026-04-01T10:00:00.000Z", "session_id": "g",
                 "prompt": "ask one", "is_bash": False},
                {"timestamp": "2026-04-01T10:01:00.000Z", "session_id": "g",
                 "prompt": "ls -la", "is_bash": True},
                {"timestamp": "2026-04-01T10:02:00.000Z", "session_id": "g",
                 "prompt": "ask two", "is_bash": False},
                {"timestamp": "2026-04-01T11:00:00.000Z", "session_id": "h",
                 "prompt": "only one", "is_bash": False},
                {"timestamp": "2026-04-01T11:01:00.000Z", "session_id": "h",
                 "prompt": "no is_bash field"},
                {"timestamp": "2026-04-01T11:02:00.000Z", "session_id": "h",
                 "prompt": "null is_bash", "is_bash": None},
            ]
            (d / "prompt_history.jsonl").write_text(
                "\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
            turns = []
            rows, _ = scan_grok.scan_sessions_dir(Path(td), turns)
        by_sid = {r["session_id"]: r for r in rows}
        self.assertTrue(by_sid["g"]["multi_turn"])
        self.assertFalse(by_sid["h"]["multi_turn"])
        self.assertEqual([t["text"] for t in turns if t["session_id"] == "g"],
                         ["ask one", "ask two"])
        self.assertEqual([t["text"] for t in turns if t["session_id"] == "h"],
                         ["only one"])
        self.assertTrue(all(t["prev_assistant_tail"] is None for t in turns))
        self.assertEqual(turns[0]["project_path"], "/home/user/projects/demo")
        self.assertNotIn("cli_launches", by_sid["g"])


class SourceCardTests(unittest.TestCase):
    CARD = {"source": "codex", "coverage": "full", "session_count": 9,
            "first_date": "2026-03-01", "last_date": "2026-04-01",
            "parse_errors": 0, "detected": True}

    def test_origin_line_renders_in_both_locales(self):
        card = dict(self.CARD,
                    origin_counts={"direct": 4, "launched": 3, "unknown": 2})
        en = _source_card_html(card, "en")
        zh = _source_card_html(card, "zh_TW")
        self.assertIn("by hand 4 · launched by another tool 3 · unknown 2", en)
        self.assertIn("親手 4 · 由其他工具啟動 3 · 無法判定 2", zh)

    def test_no_origin_line_without_counts(self):
        for counts in (None, "bad"):
            html = _source_card_html(dict(self.CARD, origin_counts=counts), "en")
            self.assertNotIn("c-source-card-origin", html)
        self.assertNotIn("c-source-card-origin",
                         _source_card_html(self.CARD, "en"))


class DemoPipelineTests(unittest.TestCase):
    """Runs the real scanners + aggregate over the generated demo tree,
    which plants one session per origin verdict (gen_origin_fixtures)."""

    @classmethod
    def setUpClass(cls):
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "generate_demo_data.py")],
            check=True, cwd=REPO_ROOT, capture_output=True)
        cls.td = tempfile.TemporaryDirectory()
        out = Path(cls.td.name)

        def run(script, *args):
            subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script),
                            *args], check=True, cwd=REPO_ROOT, capture_output=True)

        run("scan_transcripts.py", "--projects-dir", str(DEMO / "projects"),
            "--output", str(out / "t.jsonl"),
            "--user-turns-output", str(out / "user-turns.claude.jsonl"))
        run("scan_codex.py", "--sessions-dir", str(DEMO / "codex-sessions"),
            "--output", str(out / "c.jsonl"),
            "--user-turns-output", str(out / "user-turns.codex.jsonl"))
        run("scan_grok.py", "--sessions-dir", str(DEMO / "grok-sessions"),
            "--output", str(out / "g.jsonl"),
            "--user-turns-output", str(out / "user-turns.grok.jsonl"))
        run("aggregate.py", "--transcript-rows", str(out / "t.jsonl"),
            "--data-dir", str(DEMO / "usage-data"),
            "--cross-llm-rows", str(out / "c.jsonl"),
            "--cross-llm-rows", str(out / "g.jsonl"),
            "--origins-output", str(out / "origins.json"),
            "--output", str(out / "analysis-data.json"))
        cls.out = out
        cls.analysis_text = (out / "analysis-data.json").read_text(encoding="utf-8")
        cls.analysis = json.loads(cls.analysis_text)
        cls.origins = json.loads((out / "origins.json").read_text(encoding="utf-8"))["sessions"]

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    @staticmethod
    def sid(n):
        # Same formula as gen_origin_fixtures. Not imported: importing
        # generate_demo_data wipes and recreates the demo tree.
        import uuid
        return str(uuid.UUID(int=0xC0FFEE00000000000000000000000000 + n))

    def test_each_planted_session_gets_its_verdict(self):
        expect = {f"claude:{self.sid(1)}": "direct",
                  f"codex:{self.sid(2)}": "launched",
                  f"codex:{self.sid(3)}": "launched",
                  f"codex:{self.sid(4)}": "direct",
                  f"claude:{self.sid(5)}": "launched",
                  f"grok:{self.sid(6)}": "unknown",
                  f"grok:{self.sid(7)}": "direct"}
        self.assertEqual({k: self.origins.get(k) for k in expect}, expect)

    def test_source_cards_carry_counts_that_sum_to_classified_sessions(self):
        cards = {c["source"]: c for c in self.analysis["cross_llm"]["sources"]}
        for src in ("claude", "codex", "grok"):
            counts = cards[src]["origin_counts"]
            self.assertEqual(set(counts), {"direct", "launched", "unknown"})
            classified = sum(1 for k in self.origins if k.startswith(src + ":"))
            self.assertEqual(sum(counts.values()), classified)
            self.assertLessEqual(sum(counts.values()), cards[src]["session_count"])
        self.assertGreaterEqual(cards["codex"]["origin_counts"]["launched"], 2)
        self.assertGreaterEqual(cards["grok"]["origin_counts"]["unknown"], 1)
        self.assertIsNone(cards["antigravity"]["origin_counts"])

    def test_session_ids_of_origins_stay_out_of_analysis_data(self):
        self.assertNotIn("session_origins", self.analysis["cross_llm"])
        for n in (2, 3, 4, 6):  # cross-tool session ids
            self.assertNotIn(self.sid(n), self.analysis_text)

    LATER = {"claude": "CLAUDE_LATER_TURN_MARKER",
             "codex": "CODEX_LATER_TURN_MARKER",
             "grok": "GROK_LATER_TURN_MARKER"}
    ROWS = {"claude": "t.jsonl", "codex": "c.jsonl", "grok": "g.jsonl"}

    def test_later_turns_of_every_source_are_in_their_turns_file_only(self):
        for src, marker in self.LATER.items():
            turns = (self.out / f"user-turns.{src}.jsonl").read_text(encoding="utf-8")
            self.assertIn(marker, turns, src)
            self.assertNotIn(marker, (self.out / self.ROWS[src]).read_text(encoding="utf-8"), src)
            self.assertNotIn(marker, self.analysis_text, src)

    def test_injected_text_and_first_prompt_marker(self):
        claude_turns = (self.out / "user-turns.claude.jsonl").read_text(encoding="utf-8")
        self.assertIn("TURN_PRIVATE_MARKER", claude_turns)
        self.assertNotIn("injected, not typed", claude_turns)
        self.assertNotIn("/model", claude_turns)
        self.assertIn("GROK_PRIVATE_MARKER",
                      (self.out / "user-turns.grok.jsonl").read_text(encoding="utf-8"))
        self.assertNotIn("GROK_PRIVATE_MARKER", self.analysis_text)

    def test_working_files_are_owner_only(self):
        for name in ("user-turns.claude.jsonl", "user-turns.codex.jsonl",
                     "user-turns.grok.jsonl", "origins.json"):
            mode = stat.S_IMODE((self.out / name).stat().st_mode)
            self.assertEqual(mode, 0o600, name)

    def test_report_builds_show_the_split_only_in_self(self):
        hist = self.out / "history.jsonl"
        samples = self.out / "samples.json"
        samples.write_text("{}", encoding="utf-8")
        narr = self.out / "ledger.md"
        narr.write_text("# opening\n\nDemo.\n\n# team-ledger\n\nDemo team.\n",
                        encoding="utf-8")
        for audience, expect in (("self", True), ("hr", False)):
            html_path = self.out / f"{audience}.html"
            subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "build_html.py"),
                 "--input", str(self.out / "analysis-data.json"),
                 "--samples", str(samples),
                 "--audience", audience, "--ledger-narration", str(narr),
                 "--output", str(html_path), "--history-file", str(hist)],
                check=True, cwd=REPO_ROOT, capture_output=True)
            html = html_path.read_text(encoding="utf-8")
            self.assertEqual("c-source-card-origin" in html, expect, audience)
            self.assertEqual("launched by another tool" in html, expect, audience)
            self.assertNotIn("origin_counts", html)
            self.assertNotIn("TURN_PRIVATE_MARKER", html)
            for marker in self.LATER.values():
                self.assertNotIn(marker, html, audience)


if __name__ == "__main__":
    unittest.main()
