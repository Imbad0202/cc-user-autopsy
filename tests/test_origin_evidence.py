"""What each scanner records about how a session was run (findings-first
Phase 1): the `interactive` field, the calls that start another AI CLI,
the private origins file, and the counts on a source card. No scanner
output carries prompt text beyond the pre-existing first prompt."""
import argparse
import contextlib
import io
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
    check_distinct_outputs, parse_ts, to_local_iso, write_private_text)
from scripts.report_render import _source_card_html  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"
DEMO = Path("/tmp/cc-autopsy-demo")


def _user(content, ts, **extra):
    return {"type": "user", "timestamp": ts,
            "message": {"role": "user", "content": content}, **extra}


def _typed(content, ts, **extra):
    """A prompt carrying the labels Claude Code writes when a person
    typed it."""
    labels = {"entrypoint": "cli", "promptSource": "typed",
              "turnOrigin": "human", "origin": {"kind": "human"}}
    return _user(content, ts, **{**labels, **extra})


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


REPLY = _asst([{"type": "text", "text": "ok"}], _ts(1))
SDK = dict(entrypoint="sdk-cli", promptSource="sdk", turnOrigin="sdk")


class PrivateFileTests(unittest.TestCase):
    def test_new_file_is_owner_only_whatever_the_umask(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "sub" / "origins.json"
            old = os.umask(0o022)
            try:
                write_private_text("x\n", out)
            finally:
                os.umask(old)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
            # A umask that would strip the owner's own access as well.
            other = Path(td) / "strict.json"
            old = os.umask(0o777)
            try:
                write_private_text("y\n", other)
            finally:
                os.umask(old)
            self.assertEqual(stat.S_IMODE(other.stat().st_mode), 0o600)
            self.assertEqual(other.read_text(encoding="utf-8"), "y\n")

    def test_existing_loose_file_is_tightened(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "origins.json"
            out.write_text("old")
            os.chmod(out, 0o644)
            write_private_text("new", out)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
            self.assertEqual(out.read_text(encoding="utf-8"), "new")

    def test_an_earlier_file_is_replaced_not_written_into(self):
        # Whoever holds the old file open, or reaches it through another
        # name, keeps the old content and never sees the new.
        with tempfile.TemporaryDirectory() as td:
            out, other_name = Path(td) / "origins.json", Path(td) / "hardlink"
            out.write_text("old")
            os.link(out, other_name)
            with open(out, encoding="utf-8") as held_open:
                write_private_text("new private text", out)
                self.assertEqual(held_open.read(), "old")
            self.assertEqual(other_name.read_text(encoding="utf-8"), "old")
            self.assertEqual(out.read_text(encoding="utf-8"), "new private text")

    def test_a_symlink_at_the_path_is_replaced_not_followed(self):
        with tempfile.TemporaryDirectory() as td:
            victim, out = Path(td) / "victim", Path(td) / "origins.json"
            victim.write_text("untouched")
            os.symlink(victim, out)
            write_private_text("new", out)
            self.assertFalse(out.is_symlink())
            self.assertEqual(victim.read_text(encoding="utf-8"), "untouched")
            self.assertEqual(out.read_text(encoding="utf-8"), "new")

    def test_no_temp_file_is_left_behind(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "origins.json"
            write_private_text("x", out)
            self.assertEqual([p.name for p in Path(td).iterdir()],
                             ["origins.json"])
            with self.assertRaises(TypeError):
                write_private_text(None, out)
            self.assertEqual([p.name for p in Path(td).iterdir()],
                             ["origins.json"])
            self.assertEqual(out.read_text(encoding="utf-8"), "x")


class DistinctOutputTests(unittest.TestCase):
    def refused(self, a, b):
        parser = argparse.ArgumentParser()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            try:
                check_distinct_outputs(parser, str(a), str(b))
            except SystemExit:
                return "same file" in err.getvalue()
        return False

    def test_one_file_under_two_spellings_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            self.assertTrue(self.refused(td / "a.json", td / "a.json"))
            self.assertTrue(self.refused(td / "a.json", td / "sub" / ".." / "a.json"))
            # Neither exists yet, so there is no inode to compare: a
            # volume that ignores case would make these one file.
            self.assertTrue(self.refused(td / "Rows.json", td / "rows.json"))
            # Composed and decomposed accents: one file on macOS volumes.
            self.assertTrue(self.refused(td / "caf\u00e9.json",
                                         td / "cafe\u0301.json"))
            # Case-folding a composed letter can itself decompose it.
            self.assertTrue(self.refused(td / "p\u0390q.json",
                                         td / "P\u0399\u0308\u0301Q.json"))
            existing, link = td / "x.json", td / "y.json"
            existing.write_text("x")
            os.link(existing, link)
            self.assertTrue(self.refused(existing, link))

    def test_different_files_and_missing_flags_pass(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            self.assertFalse(self.refused(td / "a.json", td / "b.json"))
            check_distinct_outputs(argparse.ArgumentParser(),
                                   str(td / "a.json"), None)


class ClaudeEvidenceTests(unittest.TestCase):
    def scan(self, records):
        with tempfile.TemporaryDirectory() as td:
            return scan_transcripts.scan_one(_write_transcript(td, records))

    def interactive(self, *records):
        return self.scan(list(records))["interactive"]

    def test_interactive_is_what_the_transcript_records(self):
        cases = [
            ([_typed("hi", _ts(0)), REPLY], True),
            # A slash command is a person at the keyboard too.
            ([_typed("<command-name>/model</command-name>", _ts(0)), REPLY], True),
            # Another interactive client's name is not a programmatic one.
            ([_typed("hi", _ts(0), entrypoint="claude-vscode"), REPLY], True),
            # Programmatic entrypoint: never interactive, whatever a
            # prompt claims.
            ([_user("hi", _ts(0), **SDK), REPLY], False),
            ([_typed("hi", _ts(0), entrypoint="sdk-cli"), REPLY], False),
            ([_typed("hi", _ts(0), entrypoint="SDK-py"), REPLY], False),
            # Labelled, and no prompt is a person's: a scheduled run.
            ([_user("go", _ts(0), entrypoint="cli", promptSource="system",
                    turnOrigin="scheduled"), REPLY], False),
            # A person's prompt inside a subagent thread is not the
            # session's.
            ([_typed("hi", _ts(0), isSidechain=True), REPLY], None),
            ([_typed("hi", _ts(0), isMeta=True), REPLY], False),
            ([_typed("hi", _ts(0), isCompactSummary=True), REPLY], False),
            # No labels (older transcript format): not known either way.
            ([_user("hi", _ts(0)), REPLY, _user("again", _ts(2))], None),
            ([_user("hi", _ts(0), entrypoint="cli"), REPLY], None),
        ]
        for records, want in cases:
            self.assertIs(self.scan(records)["interactive"], want, records[0])

    def test_every_label_present_must_name_a_person(self):
        def rec(source, turn, kind):
            extra = {}
            if source:
                extra["promptSource"] = source
            if turn:
                extra["turnOrigin"] = turn
            if kind:
                extra["origin"] = {"kind": kind}
            return _user("text", _ts(0), entrypoint="cli", **extra)
        human = [("typed", "human", "human"), ("queued", "human", "human"),
                 ("suggestion_accepted", "human", "human"),
                 (None, "human", None), (None, "human", "human"),
                 ("typed", None, None)]
        other = [("system", "task_notification", "task-notification"),
                 ("system", None, "task-notification"),
                 (None, "task_notification", None), ("system", "peer", "peer"),
                 (None, "peer", None), ("sdk", "sdk", None),
                 ("system", "scheduled", None), ("system", "system", None),
                 # Labels that disagree: anything not a person wins.
                 ("typed", "scheduled", None), ("typed", "human", "peer"),
                 ("some_future_source", "human", "human")]
        for labels in human:
            self.assertIs(self.interactive(rec(*labels)), True, labels)
        for labels in other:
            self.assertIs(self.interactive(rec(*labels)), False, labels)
        # No label at all: never assumed to be the user's.
        self.assertIsNone(self.interactive(rec(None, None, None)))

    def test_malformed_labels_are_not_a_person(self):
        for bad in (
                _user("a", _ts(0), entrypoint="cli", promptSource=["typed"]),
                _user("b", _ts(0), entrypoint="cli", turnOrigin={"human": True}),
                _user("c", _ts(0), entrypoint="cli", origin="human"),
                _user("d", _ts(0), entrypoint="cli", origin={"kind": ["human"]}),
                # One valid label does not outvote a malformed one.
                _typed("e", _ts(0), origin={"kind": ["peer"]}),
                _typed("f", _ts(0), origin="peer"),
                # A label that is present and null is a label, and not a
                # person's.
                _typed("g", _ts(0), turnOrigin=None),
                _typed("h", _ts(0), promptSource=None),
                _typed("i", _ts(0), origin=None)):
            # Labelled, however badly: not "no record".
            self.assertIs(self.interactive(bad), False, bad)

    def test_a_prompt_must_name_how_it_arrived(self):
        nameless = _typed("who", _ts(0))
        del nameless["entrypoint"]
        for unnamed in (nameless, _typed("who", _ts(0), entrypoint=""),
                        _typed("who", _ts(0), entrypoint="  "),
                        _typed("who", _ts(0), entrypoint=None),
                        _typed("who", _ts(0), entrypoint=["cli"])):
            self.assertIs(self.interactive(unnamed, REPLY), False, unnamed)

    def test_entrypoint_is_read_per_record(self):
        # Opened in the terminal, later resumed by a program: a person
        # did sit in this session.
        self.assertIs(self.interactive(
            _typed("mine", _ts(0)), REPLY,
            _typed("scripted", _ts(2), entrypoint="sdk-cli")), True)
        # The only "typed" record came through the programmatic part.
        self.assertIs(self.interactive(
            _user("go", _ts(0), entrypoint="cli", promptSource="system",
                  turnOrigin="scheduled"), REPLY,
            _typed("scripted", _ts(2), entrypoint="sdk-cli")), False)

    def test_tool_output_is_never_the_sign_of_a_person(self):
        result = _typed([{"type": "tool_result", "tool_use_id": "t",
                          "content": "out"}], _ts(1))
        self.assertIs(self.interactive(_user("go", _ts(0), **SDK), result), False)
        self.assertIs(self.interactive(result), False)

    def test_malformed_lines_and_records_do_not_stop_the_scan(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_transcript(td, [
                {"type": "user", "timestamp": _ts(0), "message": None},
                {"type": "assistant", "timestamp": _ts(1), "message": "broken"},
                {"type": "user", "timestamp": _ts(2)}])
            with p.open("a", encoding="utf-8") as fh:
                fh.write('[1, 2]\n"text"\n7\nnull\n{broken\n')
                fh.write(json.dumps(_typed("still here", _ts(3))) + "\n")
            row = scan_transcripts.scan_one(p)
        self.assertIs(row["interactive"], True)
        self.assertEqual(row["user_message_count"], 1)

    def test_bash_calls_to_other_clis_are_recorded(self):
        row = self.scan([
            _typed("review", _ts(0)),
            _asst([{"type": "tool_use", "id": "1", "name": "Bash",
                    "input": {"command": 'codex exec "review"'}},
                   {"type": "tool_use", "id": "2", "name": "Bash",
                    "input": {"command": "cat codex-notes.md"}},
                   {"type": "tool_use", "id": "3", "name": "Read",
                    "input": {"command": "grok -p x"}}], _ts(1)),
        ])
        self.assertEqual(row["cli_launches"],
                         [{"target": "codex", "ts": _ts(1), "until": None}])

    def test_own_cli_call_is_recorded_too(self):
        row = self.scan([
            _typed("ask a fresh one", _ts(0)),
            _asst([{"type": "tool_use", "id": "1", "name": "Bash",
                    "input": {"command": "claude -p 'second opinion'"}}], _ts(1))])
        self.assertEqual([e["target"] for e in row["cli_launches"]], ["claude"])

    def test_launch_records_when_its_result_came_back(self):
        row = self.scan([
            _typed("review", _ts(0)),
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

    def test_launch_without_a_usable_call_id_is_never_paired(self):
        def call(i, **ident):
            return _asst([{"type": "tool_use", "name": "Bash", **ident,
                           "input": {"command": "codex review"}}], _ts(i))
        row = self.scan([
            _typed("go", _ts(0)), call(1), call(2, id=None),
            call(3, id=["x"]), call(4, id={"a": 1}), call(5, id=""),
            # One call with a good id, so results are actually looked up.
            call(6, id="good"),
            _user([{"type": "tool_result", "content": "no id"}], _ts(7)),
            _user([{"type": "tool_result", "tool_use_id": None,
                    "content": "x"}], _ts(8)),
            _user([{"type": "tool_result", "tool_use_id": ["x"],
                    "content": "x"}], _ts(9)),
            _user([{"type": "tool_result", "tool_use_id": {"a": 1},
                    "content": "x"}], _ts(10)),
            _user([{"type": "tool_result", "tool_use_id": "",
                    "content": "x"}], _ts(11)),
            _user([{"type": "tool_result", "tool_use_id": "good",
                    "content": "x"}], _ts(12))])
        self.assertEqual([e["until"] for e in row["cli_launches"]],
                         [None] * 5 + [_ts(12)])

    def test_shell_calls_in_a_subagent_thread_count(self):
        side = _asst([{"type": "tool_use", "id": "1", "name": "Bash",
                       "input": {"command": "codex review"}}], _ts(1))
        side["isSidechain"] = True
        row = self.scan([_typed("go", _ts(0)), side])
        self.assertEqual([e["target"] for e in row["cli_launches"]], ["codex"])

    def _run_scan(self, td, records_by_sid, *extra):
        proj = Path(td) / "projects"
        for sid, records in records_by_sid.items():
            _write_transcript(proj, records, sid=sid)
        rows = Path(td) / "rows.jsonl"
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "scan_transcripts.py"),
             "--projects-dir", str(proj), "--output", str(rows), *extra],
            check=True, capture_output=True)
        return [json.loads(l) for l in rows.read_text(encoding="utf-8").splitlines()]

    def test_subagent_file_launches_merge_into_the_parent_row(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "projects"
            agent = [dict(_asst([{"type": "tool_use", "id": "1", "name": "Bash",
                                  "input": {"command": 'codex exec "review"'}}],
                                _ts(2)), sessionId=SID, isSidechain=True)]
            d = proj / "-home-user-projects-demo"
            d.mkdir(parents=True)
            (d / "agent-abc123.jsonl").write_text(
                "\n".join(json.dumps(r) for r in agent) + "\n", encoding="utf-8")
            got = self._run_scan(td, {SID: [
                _typed("review it", _ts(0)),
                _asst([{"type": "text", "text": "delegating"}], _ts(1))]})
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["cli_launches"],
                         [{"target": "codex", "ts": _ts(2), "until": None}])

    def test_rows_carry_the_evidence_and_no_text_beyond_the_first_prompt(self):
        with tempfile.TemporaryDirectory() as td:
            got = self._run_scan(td, {SID: [
                _typed("SECRET_TYPED_TEXT one", _ts(0)),
                _asst([{"type": "text", "text": "SECRET_REPLY_TEXT"}], _ts(1)),
                _typed("SECRET_TYPED_TEXT two", _ts(2))]})
        self.assertIs(got[0]["interactive"], True)
        self.assertEqual(got[0]["cli_launches"], [])
        text = json.dumps(got)
        self.assertIn("SECRET_TYPED_TEXT one", text)     # first_prompt, as before
        self.assertNotIn("SECRET_TYPED_TEXT two", text)
        self.assertNotIn("SECRET_REPLY_TEXT", text)

    def test_a_filtered_out_session_takes_its_launch_evidence_along(self):
        other = "22222222-2222-3333-4444-555555555555"
        with tempfile.TemporaryDirectory() as td:
            got = self._run_scan(td, {
                SID: [_typed("go", _ts(0)),
                      _asst([{"type": "tool_use", "id": "1", "name": "Bash",
                              "input": {"command": "codex review"}}], _ts(1))],
                other: [_typed("a", _ts(0)), REPLY,
                        _typed("b", _ts(2)),
                        _asst([{"type": "text", "text": "ok"}], _ts(3))],
            }, "--min-assistant-msgs", "2")
        self.assertEqual([r["session_id"] for r in got], [other])
        self.assertEqual(got[0]["cli_launches"], [])


def _codex_line(ts, type_, payload):
    return json.dumps({"timestamp": ts, "type": type_, "payload": payload})


def _rollout(td, lines):
    p = Path(td) / "2026" / "04" / "01" / "rollout-2026-04-01T10-00-00-t.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _codex_header(n, **payload):
    return _codex_line(_ts(n), "session_meta", {"id": "cx", "cwd": "/w", **payload})


def _codex_user(n, text):
    return _codex_line(_ts(n), "event_msg", {"type": "user_message", "message": text})


class CodexEvidenceTests(unittest.TestCase):
    def scan_lines(self, lines):
        with tempfile.TemporaryDirectory() as td:
            return scan_codex.scan_one(_rollout(td, lines))[0]

    def scan(self, header, body):
        return self.scan_lines([_codex_header(0, **header)] + body)

    def test_interactive_follows_the_header(self):
        body = [_codex_user(1, "x")]
        for header, want in (({"source": "cli"}, True),
                             ({"source": "VSCode"}, True),
                             ({"source": "exec"}, False),
                             ({"source": "mcp"}, False),
                             ({"source": {"subagent": "review"}}, None),
                             ({"source": "something-new"}, None),
                             ({"source": {"something": "else"}}, None),
                             ({}, None)):
            self.assertIs(self.scan(header, body)["interactive"], want, header)

    def test_header_source_forms(self):
        body = [_codex_user(1, "x")]
        self.assertEqual(self.scan({"source": "Exec"}, body)["launch_source"],
                         "exec")
        self.assertEqual(
            self.scan({"source": {"subagent": "review"}}, body)["launch_source"],
            "subagent")
        for other in ({}, {"something": "else"}, 7, "  "):
            self.assertIsNone(self.scan({"source": other}, body)["launch_source"])
        self.assertIsNone(self.scan({}, body)["launch_source"])

    def test_every_header_of_a_resumed_rollout_must_vouch_for_it(self):
        def verdict(*sources):
            lines = []
            for n, src in enumerate(sources):
                lines.append(_codex_header(2 * n, **({} if src is None
                                                     else {"source": src})))
                lines.append(_codex_user(2 * n + 1, "x"))
            row = self.scan_lines(lines)
            return row["interactive"], row["launch_source"]
        # Interactive throughout.
        self.assertEqual(verdict("cli", "vscode"), (True, "vscode"))
        # A program ran one stretch, in either order.
        self.assertEqual(verdict("exec", "cli"), (False, "exec"))
        self.assertEqual(verdict("cli", "exec"), (False, "exec"))
        # One stretch does not say how it was run: the stretches that do
        # cannot vouch for the whole.
        self.assertEqual(verdict(None, "cli"), (None, "cli"))
        self.assertEqual(verdict("cli", None), (None, "cli"))
        self.assertEqual(verdict("cli", "something-new"), (None, "something-new"))
        self.assertEqual(verdict("cli", {"other": 1}), (None, "cli"))
        # Spawned at any point: the row says so.
        self.assertEqual(verdict("cli", {"subagent": "r"})[1], "subagent")
        self.assertEqual(verdict(None, "exec"), (False, "exec"))

    def test_only_a_shell_tools_command_field_is_a_command_line(self):
        def call(args, name="shell"):
            return _codex_line(_ts(2), "response_item",
                               {"type": "function_call", "name": name,
                                "arguments": args})
        hits = [
            call(json.dumps({"command": ["bash", "-lc", "claude -p 'hi'"]})),
            call(json.dumps({"cmd": "claude -p hi"}), name="exec_command"),
            call(json.dumps({"command": "cd /w\nclaude -p hi"})),
            # An executable path in quotes: the raw JSON has a backslash
            # right after the name.
            call(json.dumps({"cmd": '"/opt/bin/claude" -p hi'})),
            call(json.dumps({"cmd": "C:\\bin\\claude.exe -p hi"})),
            call(json.dumps(["bash", "-lc", "claude -p hi"]), name="local_shell"),
            call("claude -p not-json"),
            # Nested too deeply to decode: read as plain text, not fatal.
            call("[" * 5000 + '"claude -p hi"' + "]" * 5000),
        ]
        misses = [
            # File content, not a command line.
            call(json.dumps({"input": "*** Update File: a.md\n+run claude -p x"}),
                 name="apply_patch"),
            call(json.dumps({"command": "cat claude-notes.md"})),
            call(json.dumps({"command": "ls ~/.claude/projects"})),
            call(json.dumps({"cmd": "dir C:\\work\\claude\\src"})),
            _codex_line(_ts(2), "response_item",
                        {"type": "function_call", "name": "shell"}),
            # Fields beside the command can name a CLI without running it.
            call(json.dumps({"cmd": "pwd", "prefix_rule": ["claude", "-p"]})),
            call(json.dumps({"command": "pwd", "workdir": "/work/claude"})),
            call(json.dumps({"command": ["ls"], "cwd": "/home/u/claude",
                             "justification": "see what claude wrote"})),
            # Tools that are not a shell, whatever their name contains.
            call(json.dumps({"query": "select 'claude -p'"}), name="execute_sql"),
            call(json.dumps({"query": "select 'claude -p'"}), name="exec_sql"),
        ]
        for line, expected in [(h, ["claude"]) for h in hits] + \
                [(m, []) for m in misses]:
            row = self.scan({}, [line])
            self.assertEqual([e["target"] for e in row["cli_launches"]],
                             expected, line[:200])

    def test_launch_window_closes_at_the_call_output(self):
        def call(n, call_id):
            return _codex_line(_ts(n), "response_item", {
                "type": "function_call", "name": "shell", "call_id": call_id,
                "arguments": json.dumps({"command": "claude -p hi"})})
        def output(n, call_id):
            return _codex_line(_ts(n), "response_item", {
                "type": "function_call_output", "call_id": call_id, "output": "x"})
        row = self.scan({}, [
            call(2, "c1"), call(3, ["bad"]), call(4, {"a": 1}), call(5, ""),
            output(6, ["bad"]), output(7, {"a": 1}), output(8, ""),
            output(9, "c1")])
        self.assertEqual(row["cli_launches"][0], {
            "target": "claude", "ts": to_local_iso(parse_ts(_ts(2))),
            "until": to_local_iso(parse_ts(_ts(9)))})
        self.assertEqual([e["until"] for e in row["cli_launches"][1:]], [None] * 3)

    def test_rows_carry_no_text_beyond_the_first_prompt(self):
        row = self.scan({"source": "cli"}, [
            _codex_user(1, "SECRET one"),
            _codex_line(_ts(2), "event_msg",
                        {"type": "agent_message", "message": "SECRET_REPLY"}),
            _codex_user(3, "SECRET two")])
        self.assertEqual(row["session_id"], "cx")
        self.assertEqual((row["user_message_count"], row["first_prompt"]),
                         (2, "SECRET one"))
        text = json.dumps(row)
        self.assertNotIn("SECRET two", text)
        self.assertNotIn("SECRET_REPLY", text)


class GrokEvidenceTests(unittest.TestCase):
    def test_grok_rows_record_nothing_about_how_they_were_run(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "%2Fhome%2Fuser%2Fprojects%2Fdemo"
            d.mkdir()
            recs = [
                {"timestamp": "2026-04-01T10:00:00.000Z", "session_id": "g",
                 "prompt": "ask one", "is_bash": False},
                {"timestamp": "2026-04-01T10:02:00.000Z", "session_id": "g",
                 "prompt": "ask two", "is_bash": False}]
            (d / "prompt_history.jsonl").write_text(
                "\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
            rows, _ = scan_grok.scan_sessions_dir(Path(td))
        self.assertEqual(len(rows), 1)
        self.assertIn("interactive", rows[0])
        self.assertIsNone(rows[0]["interactive"])
        self.assertNotIn("cli_launches", rows[0])
        self.assertNotIn("ask two", json.dumps(rows))


class SourceCardTests(unittest.TestCase):
    CARD = {"source": "codex", "coverage": "full", "session_count": 9,
            "first_date": "2026-03-01", "last_date": "2026-04-01",
            "parse_errors": 0, "detected": True}

    def test_origin_line_renders_in_both_locales(self):
        card = dict(self.CARD,
                    origin_counts={"direct": 4, "launched": 3, "unknown": 0})
        en = _source_card_html(card, "en")
        zh = _source_card_html(card, "zh_TW")
        self.assertIn("by hand 4 · launched by a tool 3 · unknown 0", en)
        self.assertIn("親手 4 · 由工具啟動 3 · 無法判定 0", zh)

    def test_no_origin_line_without_three_plain_counts(self):
        good = {"direct": 1, "launched": 2, "unknown": 3}
        for counts in (None, "bad", [1], {}, {"direct": 1, "launched": 2},
                       dict(good, direct="<script>alert(1)</script>"),
                       dict(good, launched=-3), dict(good, unknown=float("inf")),
                       dict(good, unknown=1.0), dict(good, direct=True),
                       dict(good, direct=None)):
            html = _source_card_html(dict(self.CARD, origin_counts=counts), "en")
            self.assertNotIn("c-source-card-origin", html, counts)
            self.assertNotIn("<script>", html)
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
            "--output", str(out / "t.jsonl"))
        run("scan_codex.py", "--sessions-dir", str(DEMO / "codex-sessions"),
            "--output", str(out / "c.jsonl"))
        run("scan_grok.py", "--sessions-dir", str(DEMO / "grok-sessions"),
            "--output", str(out / "g.jsonl"))
        run("aggregate.py", "--transcript-rows", str(out / "t.jsonl"),
            "--data-dir", str(DEMO / "usage-data"),
            "--cross-llm-rows", str(out / "c.jsonl"),
            "--cross-llm-rows", str(out / "g.jsonl"),
            "--origins-output", str(out / "origins.json"),
            "--output", str(out / "analysis-data.json"))
        cls.out = out
        cls.analysis_text = (out / "analysis-data.json").read_text(encoding="utf-8")
        cls.analysis = json.loads(cls.analysis_text)
        cls.origins_doc = json.loads((out / "origins.json").read_text(encoding="utf-8"))
        cls.origins = cls.origins_doc["sessions"]

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
                  f"grok:{self.sid(7)}": "unknown",
                  f"claude:{self.sid(8)}": "unknown",
                  f"claude:{self.sid(9)}": "unknown"}
        self.assertEqual({k: self.origins.get(k) for k in expect}, expect)
        self.assertEqual(self.origins_doc["schema_version"], 1)
        self.assertLessEqual(set(self.origins.values()),
                             {"direct", "launched", "unknown"})

    def test_source_cards_carry_counts_that_sum_to_classified_sessions(self):
        cards = {c["source"]: c for c in self.analysis["cross_llm"]["sources"]}
        for src in ("claude", "codex", "grok"):
            counts = cards[src]["origin_counts"]
            self.assertEqual(set(counts), {"direct", "launched", "unknown"})
            classified = sum(1 for k in self.origins if k.startswith(src + ":"))
            self.assertEqual(sum(counts.values()), classified)
            self.assertLessEqual(sum(counts.values()), cards[src]["session_count"])
        self.assertGreaterEqual(cards["codex"]["origin_counts"]["launched"], 2)
        self.assertEqual(cards["grok"]["origin_counts"]["direct"], 0)
        self.assertIsNone(cards["antigravity"]["origin_counts"])

    def test_session_ids_of_origins_stay_out_of_analysis_data(self):
        self.assertNotIn("session_origins", self.analysis["cross_llm"])
        for n in (2, 3, 4, 6):  # cross-tool session ids
            self.assertNotIn(self.sid(n), self.analysis_text)

    LATER = ("CLAUDE_LATER_TURN_MARKER", "CODEX_LATER_TURN_MARKER",
             "GROK_LATER_TURN_MARKER", "AUTOMATED_TURN_MARKER now post it",
             "UNLABELLED_TURN_MARKER second", "Apply both fixes?")

    def test_no_output_carries_prompt_text_beyond_the_first_prompt(self):
        for name in ("t.jsonl", "c.jsonl", "g.jsonl", "analysis-data.json",
                     "origins.json"):
            text = (self.out / name).read_text(encoding="utf-8")
            for marker in self.LATER:
                self.assertNotIn(marker, text, (name, marker))
        # Nothing but the files asked for was written.
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         ["analysis-data.json", "c.jsonl", "g.jsonl",
                          "origins.json", "t.jsonl"])

    def test_aggregate_refuses_one_path_for_both_outputs(self):
        same = self.out / "clash.json"
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "aggregate.py"),
             "--transcript-rows", str(self.out / "t.jsonl"),
             "--data-dir", str(DEMO / "usage-data"),
             "--origins-output", str(same), "--output", str(same)],
            cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("same file", proc.stderr)
        self.assertFalse(same.exists())

    def test_origins_file_is_owner_only(self):
        mode = stat.S_IMODE((self.out / "origins.json").stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_report_builds_show_the_split_only_in_self(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            samples = td / "samples.json"
            samples.write_text("{}", encoding="utf-8")
            narr = td / "ledger.md"
            narr.write_text("# opening\n\nDemo.\n\n# team-ledger\n\nDemo team.\n",
                            encoding="utf-8")
            for audience, expect in (("self", True), ("hr", False)):
                html_path = td / f"{audience}.html"
                subprocess.run(
                    [sys.executable, str(REPO_ROOT / "scripts" / "build_html.py"),
                     "--input", str(self.out / "analysis-data.json"),
                     "--samples", str(samples),
                     "--audience", audience, "--ledger-narration", str(narr),
                     "--output", str(html_path),
                     "--history-file", str(td / "history.jsonl")],
                    check=True, cwd=REPO_ROOT, capture_output=True)
                html = html_path.read_text(encoding="utf-8")
                self.assertEqual("c-source-card-origin" in html, expect, audience)
                self.assertEqual("launched by a tool" in html, expect, audience)
                self.assertNotIn("origin_counts", html)
                for marker in ("TURN_PRIVATE_MARKER", "GROK_PRIVATE_MARKER",
                               *self.LATER):
                    self.assertNotIn(marker, html, (audience, marker))


if __name__ == "__main__":
    unittest.main()
