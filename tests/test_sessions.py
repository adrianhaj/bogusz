import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills/bogusz/scripts"))

from sessions import (  # noqa: E402
    classify_test_command,
    encode_project_dir,
    find_transcript,
    list_sessions,
    main,
    parse_test_outcome,
    parse_transcript,
)
from tests.transcript import assistant_text, tool_result, tool_use, user_prompt, write  # noqa: E402

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
D = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
M = [Path("/m")]


class LookupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "projects"
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, project, sid, cwd="/m/repo", prompt="hi", mtime=None):
        p = write(self.root / project / f"{sid}.jsonl", [user_prompt(prompt, "2026-11-04T10:00:00Z", cwd=cwd)])
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def test_multiple_roots(self):
        self.session("-m-repo", A, cwd="/m/repo", mtime=1)
        self.session("-w-repo", B, cwd="/w/repo", mtime=2)
        self.session("-z-repo", C, cwd="/z/repo", mtime=3)
        ids = [s["session_id"] for s in list_sessions(self.root, [Path("/m"), Path("/w")])]
        self.assertEqual(ids, [B, A])

    def test_encode(self):
        self.assertEqual(
            encode_project_dir("/Users/a/src/app/worktrees/x/_claude-ah-y"),
            "-Users-a-src-app-worktrees-x--claude-ah-y",
        )

    def test_rejects_bad_refs(self):
        for ref in ["../../etc/passwd", "abc", "last; rm -rf /", ""]:
            with self.assertRaises(ValueError):
                find_transcript(ref, self.root, M)

    def test_scope_by_dir_and_cwd(self):
        self.session("-m-repo", A)
        self.session("-other", B, cwd="/other")
        self.session("-m-other", C, cwd="/elsewhere")
        self.assertEqual(find_transcript(A, self.root, M).stem, A)
        for sid in (B, C):
            with self.assertRaises(LookupError):
                find_transcript(sid, self.root, M)

    def test_last_skips_excluded(self):
        self.session("-m-repo", A, mtime=1000)
        self.session("-m-repo", B, mtime=2000)
        self.assertEqual(find_transcript("last", self.root, M).stem, B)
        self.assertEqual(find_transcript("last", self.root, M, exclude=B).stem, A)

    def test_symlink_outside_rejected(self):
        outside = write(Path(self.tmp.name) / "outside.jsonl", [user_prompt("x", "2026-11-04T10:00:00Z")])
        (self.root / "-m-repo").mkdir()
        (self.root / "-m-repo" / f"{D}.jsonl").symlink_to(outside)
        with self.assertRaises(LookupError):
            find_transcript(D, self.root, M)

    def test_subagent_files_not_sessions(self):
        self.session("-m-repo", A, mtime=1000)
        sub = write(self.root / "-m-repo" / A / "subagents" / "agent-x.jsonl", [user_prompt("x", "2026-11-04T10:00:00Z")])
        os.utime(sub, (3000, 3000))
        self.assertEqual(find_transcript("last", self.root, M).stem, A)
        self.assertEqual([s["session_id"] for s in list_sessions(self.root, M)], [A])

    def test_list_sessions_redacts_prompt(self):
        self.session("-m-repo", A, prompt="deploy with CLIENT_SECRET=zz")
        self.assertNotIn("zz", list_sessions(self.root, M)[0]["first_prompt"])


def ts(sec):
    return f"2026-11-04T10:{sec // 60:02d}:{sec % 60:02d}Z"


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name) / "-m-repo" / f"{A}.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def parse(self, entries):
        write(self.p, entries)
        return parse_transcript(self.p)

    def test_tool_call_pairing_and_duration(self):
        d = self.parse([tool_use("t1", "Bash", {"command": "make test"}, ts(0)), tool_result("t1", "ok", ts=ts(30))])
        c = d["tool_calls"][0]
        self.assertEqual((c["tool"], c["completed"], c["is_error"], c["duration_s"]), ("Bash", True, False, 30.0))

    def test_discussed_not_executed(self):
        d = self.parse([assistant_text("run `make test PKG=./internal/batch/...`", ts(0))])
        self.assertEqual(d["tool_calls"], [])

    def test_malformed_lines_counted(self):
        d = self.parse([
            tool_use("t1", "Bash", {"command": "ls"}, ts(0)),
            "{not json",
            "",
            tool_result("t1", "x", ts=ts(1)),
        ])
        self.assertEqual(d["malformed_lines"], 1)
        self.assertEqual(len(d["tool_calls"]), 1)

    def test_unknown_types_and_string_content(self):
        no_ts = tool_use("t1", "Bash", {"command": "ls"}, None)
        d = self.parse([{"type": "atis-latch"}, user_prompt("plain string", ts(0)), no_ts, {"type": "cost-state"}])
        self.assertEqual(d["unknown_entry_types"], {"atis-latch": 1})
        self.assertEqual(d["prompts"][0]["text"], "plain string")

    def test_interrupted_session(self):
        d = self.parse([
            tool_use("t1", "Bash", {"command": "ls"}, ts(0)), tool_result("t1", "x", ts=ts(1)),
            tool_use("t2", "Bash", {"command": "make test"}, ts(2)),
        ])
        self.assertTrue(d["interrupted"])
        self.assertFalse(d["tool_calls"][-1]["completed"])

    def test_subagent_tool_calls_included(self):
        write(self.p.parent / A / "subagents" / "agent-x.jsonl", [
            tool_use("s1", "Bash", {"command": "go test ./..."}, ts(60)), tool_result("s1", "ok", ts=ts(61)),
        ])
        d = self.parse([tool_use("t1", "Agent", {"prompt": "run tests"}, ts(0)), tool_result("t1", "done", ts=ts(120))])
        self.assertEqual([c["agent"] for c in d["tool_calls"]], ["main", "agent-x"])

    def test_prompts_share_seq(self):
        d = self.parse([
            user_prompt("test batch", ts(0)),
            tool_use("t1", "Bash", {"command": "ls"}, ts(1)), tool_result("t1", "x", ts=ts(2)),
            user_prompt("now storage", ts(3)),
        ])
        self.assertEqual([x["seq"] for x in d["prompts"]], [1, 3])
        self.assertEqual(d["tool_calls"][0]["seq"], 2)

    def test_secrets_in_tool_input_and_output(self):
        d = self.parse([
            tool_use("t1", "Bash", {"command": "CLIENT_SECRET=abc make test"}, ts(0)),
            tool_result("t1", "Bearer abcdefgh12345678", ts=ts(1)),
        ])
        self.assertNotIn("abc", json.dumps(d["tool_calls"][0]["input"]))
        self.assertNotIn("abcdefgh12345678", json.dumps(d))

    def test_files_modified(self):
        d = self.parse([
            tool_use("t1", "Edit", {"file_path": "/m/repo/a.go"}, ts(0)),
            tool_use("t2", "Write", {"file_path": "/m/repo/b_test.go"}, ts(1)),
            tool_use("t3", "Edit", {"file_path": "/m/repo/a.go"}, ts(2)),
        ])
        self.assertEqual(d["files_modified"], ["/m/repo/a.go", "/m/repo/b_test.go"])

    def test_notebook_edits_counted(self):
        d = self.parse([tool_use("t1", "NotebookEdit", {"notebook_path": "/m/repo/n.ipynb"}, ts(0))])
        self.assertEqual(d["files_modified"], ["/m/repo/n.ipynb"])

    def test_compaction_summary_is_not_a_prompt(self):
        d = self.parse([
            {**user_prompt("This session is being continued from a previous conversation", ts(0)), "isCompactSummary": True},
            user_prompt("run the tests", ts(1)),
        ])
        self.assertEqual([p["text"] for p in d["prompts"]], ["run the tests"])


GO_OK = "ok: 12 passed, 0 failed, 0 build-failed, 0 skipped (1 packages)"
GO_FAIL = "FAIL: 11 passed, 1 failed, 0 build-failed, 0 skipped (1 packages)"


class TestDetectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name) / "-m-repo" / f"{A}.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def parse(self, entries):
        write(self.p, entries)
        return parse_transcript(self.p)

    def run_cmd(self, id, cmd, out, is_error, sec):
        return [tool_use(id, "Bash", {"command": cmd}, ts(sec)), tool_result(id, out, is_error=is_error, ts=ts(sec + 1))]

    def test_classify(self):
        self.assertEqual(
            classify_test_command("cd x && make test PKG=./internal/batch/...", "/m/api-server"),
            {"runner": "make", "layer": "unknown"},
        )
        self.assertEqual(classify_test_command(".venv/bin/pytest tests/unit -q", "/m/py-client")["layer"], "unit")
        self.assertEqual(classify_test_command("make test TEST_NAME_FILTER=deployments", "/m/qa-suite", e2e=("qa-suite",))["layer"], "e2e")
        self.assertEqual(
            classify_test_command("go test ./internal/service/... -run 'TestServices_postgres'", "/m/store")["runner"], "go"
        )
        self.assertIsNone(classify_test_command("go vet ./... && golangci-lint run", "/m/x"))
        self.assertIsNone(classify_test_command("grep -rn 'make test' CLAUDE.md", "/m/x"))

    def test_go_summary(self):
        # tools/test-summary.sh names failing *packages* in summary mode
        pkg = "github.com/acme/api-server/internal/batch"
        o = parse_test_outcome(
            f"FAIL: 41 passed, 2 failed, 0 build-failed, 1 skipped (3 packages)\n\n--- FAIL: {pkg} ---\n"
            "    batch_test.go:42: expected 3, got 2",
            True, True,
        )
        self.assertEqual((o["status"], o["passed"], o["failed"], o["skipped"], o["failed_tests"]), ("failed", 41, 2, 1, [pkg]))

    def test_raw_go_test(self):
        o = parse_test_outcome("--- PASS: TestA (0.01s)\n--- FAIL: TestB (0.02s)\nFAIL\tpkg\t0.1s", True, True)
        self.assertEqual((o["status"], o["passed"], o["failed"]), ("failed", 1, 1))

    def test_pytest_summary(self):
        o = parse_test_outcome(
            "FAILED tests/unit/test_x.py::test_y - AssertionError\n==== 1 failed, 12 passed, 2 skipped in 3.10s ====",
            True, True,
        )
        self.assertEqual((o["status"], o["failed"], o["passed"], o["failed_tests"]), ("failed", 1, 12, ["tests/unit/test_x.py::test_y"]))

    def test_pytest_quiet_summary(self):
        o = parse_test_outcome("..F.\n1 failed, 3 passed, 2 deselected in 0.40s\n", True, True)
        self.assertEqual((o["status"], o["failed"], o["passed"]), ("failed", 1, 3))
        self.assertEqual(parse_test_outcome("12 passed, 1 warning in 2.1s", True, False)["status"], "passed")

    def test_hook_blocked_is_not_run(self):
        out = "PreToolUse:Bash hook error: [~/.claude/hooks/bash-guard.sh]: Blocked: run lint/tests unpiped"
        self.assertEqual(parse_test_outcome(out, True, True)["status"], "blocked")

    def test_no_summary_is_unknown(self):
        self.assertEqual(parse_test_outcome("done\n", True, False)["status"], "unknown")

    def test_not_completed(self):
        self.assertEqual(parse_test_outcome("", False, None)["status"], "not_completed")

    def test_fail_then_fix_then_pass(self):
        d = self.parse(
            self.run_cmd("t1", "make test", GO_FAIL, True, 0)
            + [tool_use("e1", "Edit", {"file_path": "/m/repo/a.go"}, ts(5)), tool_result("e1", "ok", ts=ts(6))]
            + self.run_cmd("t2", "make test", GO_OK, False, 10)
        )
        self.assertEqual(
            [(x["status"], x["attempt"], x["edits_since_previous_attempt"]) for x in d["tests"]],
            [("failed", 1, False), ("passed", 2, True)],
        )

    def test_flaky_suspect(self):
        d = self.parse(self.run_cmd("t1", "make  test", GO_FAIL, True, 0) + self.run_cmd("t2", "make test", GO_OK, False, 10))
        self.assertEqual(d["tests"][1]["attempt"], 2)
        self.assertFalse(d["tests"][1]["edits_since_previous_attempt"])

    def test_multiple_runners(self):
        d = self.parse(
            self.run_cmd("t1", "go test ./a/...", "ok  \tpkg/a\t0.1s", False, 0)
            + self.run_cmd("t2", ".venv/bin/pytest tests/unit", "==== 3 passed in 0.2s ====", False, 10)
        )
        self.assertEqual([x["runner"] for x in d["tests"]], ["go", "pytest"])

    def test_discussed_not_run(self):
        d = self.parse(
            [assistant_text("next: `make test PKG=./internal/batch/...` and `go test ./a/...`", ts(0))]
            + self.run_cmd("t1", "go test ./a/...", "ok  \tpkg/a\t0.1s", False, 5)
        )
        self.assertEqual(d["discussed_not_run"], ["make test PKG=./internal/batch/..."])

    def test_cli_show_and_bad_ref(self):
        root = Path(self.tmp.name)
        write(root / "-m-repo" / f"{A}.jsonl", [user_prompt("hi", ts(0))] + self.run_cmd("t1", "make test", GO_OK, False, 1))
        env = {"BOGUSZ_PROJECTS_ROOT": str(root)}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(["show", "last", "--root", "/m"]), 0)
            self.assertEqual(main(["show", "../x", "--root", "/m"]), 2)
        self.assertEqual(json.loads(out.getvalue())["tests"][0]["status"], "passed")
        self.assertIn("session ref", err.getvalue())

    def test_piped_never_passed(self):
        o = parse_test_outcome("ok  \tpkg/a\t0.1s\nok  \tpkg/b\t0.2s", True, False, "go test ./... 2>&1 | tail -5")
        self.assertEqual(o["status"], "unknown")
        o = parse_test_outcome("==== 3 passed in 0.2s ====", True, False, "pytest tests || true")
        self.assertEqual(o["status"], "unknown")
        o = parse_test_outcome("--- FAIL: TestB (0.0s)\nFAIL\tpkg\t0.1s", True, False, "go test ./... | tail")
        self.assertEqual(o["status"], "failed")

    def test_chained_pytest_failure(self):
        out = "FAILED tests/a.py::t - x\n==== 1 failed in 0.1s ====\n==== 4 passed in 0.2s ===="
        o = parse_test_outcome(out, True, False, "pytest tests/a.py; pytest tests/b.py")
        self.assertEqual((o["status"], o["failed"], o["passed"]), ("failed", 1, 4))

    def test_more_runner_forms(self):
        for cmd, runner in [
            ("uv run pytest tests", "pytest"), ("poetry run pytest -q", "pytest"),
            ("make test-docker", "make"), ("make -C sub test", "make"),
            ("timeout 600 go test ./...", "go"), ("gotestsum -- ./...", "go"),
        ]:
            with self.subTest(cmd=cmd):
                self.assertEqual(classify_test_command(cmd, "/m/x")["runner"], runner)

    def test_format_drift_does_not_crash(self):
        d = self.parse([
            {"type": "user", "timestamp": 1762250400000, "message": "a string message", "cwd": "/m/repo"},
            {"type": "assistant", "timestamp": "2026-11-04T10:00:05", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": "not a dict"}]}},
            {"type": ["weird"]},
            tool_use("t2", "Bash", {"command": "ls"}, ts(9)),
        ])
        self.assertEqual(len(d["tool_calls"]), 2)
        self.assertEqual(d["unknown_entry_types"], {"['weird']": 1})

    def test_printed_fields_redacted(self):
        home = str(Path.home())
        d = self.parse([tool_use("t1", "Bash", {"command": "ls"}, ts(0), cwd=home + "/src/app/x")])
        self.assertTrue(d["cwd"].startswith("~/"))

    def test_unreadable_and_missing(self):
        root = Path(self.tmp.name) / "projects"
        write(root / "-m-repo" / f"{A}.jsonl", [user_prompt("hi", ts(0))])
        (root / "-m-repo" / f"{B}.jsonl").write_bytes(b"\xff\xfe\x00garbage\n")
        self.assertEqual(find_transcript(A, root, M).stem, A)
        self.assertEqual(len(list_sessions(root, M)), 1)
        with self.assertRaises(LookupError):
            find_transcript("last", Path(self.tmp.name) / "nope", M)

    def test_quoted_pipe_can_pass(self):
        o = parse_test_outcome("ok  \tpkg\t0.1s", True, False, "go test -run 'TestA|TestB' ./pkg/...")
        self.assertEqual(o["status"], "passed")
        self.assertEqual(parse_test_outcome("ok  \tpkg\t0.1s", True, False, "go test ./... | tail")["status"], "unknown")
        self.assertEqual(parse_test_outcome("ok  \tpkg\t0.1s", True, False, "go test ./... || true")["status"], "unknown")

    def test_discussed_ignores_redaction_of_ran_command(self):
        d = self.parse([
            assistant_text("run `CLIENT_SECRET=x make test`", ts(0)),
            *self.run_cmd("t1", "CLIENT_SECRET=x make test", GO_OK, False, 1),
        ])
        self.assertEqual(d["discussed_not_run"], [])

    def test_subagent_symlink_outside_ignored(self):
        outside = write(Path(self.tmp.name) / "elsewhere.jsonl", [tool_use("s1", "Bash", {"command": "go test ./..."}, ts(5))])
        sub = self.p.parent / A / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-evil.jsonl").symlink_to(outside)
        d = self.parse([tool_use("t1", "Bash", {"command": "ls"}, ts(0))])
        self.assertEqual([c["agent"] for c in d["tool_calls"]], ["main"])

    def test_subagent_does_not_borrow_main_timestamp(self):
        write(self.p.parent / A / "subagents" / "agent-x.jsonl", [tool_use("s1", "Bash", {"command": "ls"}, None)])
        d = self.parse([tool_use("t1", "Bash", {"command": "ls"}, ts(30))])
        self.assertIsNone(next(c for c in d["tool_calls"] if c["agent"] == "agent-x")["ts"])
        self.assertEqual([c["agent"] for c in d["tool_calls"]], ["agent-x", "main"])

    def test_cli_out_and_empty_exclude(self):
        root = Path(self.tmp.name)
        write(root / "-m-repo" / f"{A}.jsonl", [user_prompt("hi", ts(0))] + self.run_cmd("t1", "make test", GO_OK, False, 1))
        out_file = root / "nested" / "digest.json"
        env = {"BOGUSZ_PROJECTS_ROOT": str(root)}
        with mock.patch.dict(os.environ, env), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["show", "last", "--root", "/m", "--exclude", "--out", str(out_file)]), 0)
        self.assertEqual(json.loads(out_file.read_text())["session_id"], A)
    def test_ui_perf_security_runners(self):
        for cmd, runner, layer in [
            ("npx playwright test --config=./e2e/playwright.config.ts e2e/models.spec.ts", "playwright", "ui"),
            ("npm run e2e:ci", "playwright", "ui"),
            ("k6 run tests/e2e/utils/benchmarks/k6_load.js", "k6", "perf"),
            ("go test -bench=BenchmarkScore -benchmem -run=^$ ./internal/score/...", "go", "perf"),
            ("govulncheck ./...", "govulncheck", "security"),
            ("trivy fs --scanners vuln,secret .", "trivy", "security"),
            ("npm audit --omit=dev", "npm-audit", "security"),
        ]:
            with self.subTest(cmd=cmd):
                self.assertEqual(classify_test_command(cmd, "/m/x"), {"runner": runner, "layer": layer})

    def test_ui_perf_security_outcomes(self):
        cases = [
            ("Running 4 tests using 2 workers\n  1 failed\n    [chromium] › models.spec.ts:12:5 › list\n  3 passed (8.1s)", True, "failed"),
            ("  5 passed (4.0s)", False, "passed"),
            ("     ✓ http_req_duration..............: avg=12ms p(95)=40ms\n     ✓ http_req_failed................: 0.00%", False, "passed"),
            ("     ✗ http_req_duration..............: avg=900ms p(95)=2.1s", True, "failed"),
            ("No vulnerabilities found.", False, "passed"),
            ("Your code is affected by 2 vulnerabilities from 1 module.", True, "failed"),
            ("Total: 0 (UNKNOWN: 0, LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0)", False, "passed"),
            ("Total: 3 (UNKNOWN: 0, LOW: 1, MEDIUM: 0, HIGH: 2, CRITICAL: 0)", False, "failed"),
            ("found 0 vulnerabilities", False, "passed"),
            ("7 vulnerabilities (2 moderate, 5 high)", True, "failed"),
        ]
        for out, is_error, status in cases:
            with self.subTest(out=out[:30]):
                self.assertEqual(parse_test_outcome(out, True, is_error)["status"], status)

    def test_trivy_misconfig_failures_fail(self):
        out = ("Dockerfile (dockerfile)\nTests: 23 (SUCCESSES: 22, FAILURES: 1)\n"
               "Failures: 1 (UNKNOWN: 0, LOW: 0, MEDIUM: 0, HIGH: 1, CRITICAL: 0)\n\n"
               "go.mod (gomod)\nTotal: 0 (UNKNOWN: 0, LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0)")
        o = parse_test_outcome(out, True, False, "trivy fs --scanners vuln,secret,misconfig .")
        self.assertEqual((o["status"], o["failed"]), ("failed", 1))

    def test_playwright_minute_duration(self):
        self.assertEqual(parse_test_outcome("  3 passed (1.5m)", True, False)["status"], "passed")

    def test_playwright_failed_names(self):
        out = ("  1) [chromium] › models.spec.ts:12:5 › list models ──────\n\n"
               "  1 failed\n    [chromium] › models.spec.ts:12:5 › list models\n  3 passed (8.1s)")
        o = parse_test_outcome(out, True, True)
        self.assertEqual(o["failed_tests"], ["[chromium] › models.spec.ts:12:5 › list models"])

    def test_npm_audit_single_severity(self):
        for out in ["1 high severity vulnerability", "3 moderate severity vulnerabilities"]:
            with self.subTest(out=out):
                self.assertEqual(parse_test_outcome(out, True, True)["status"], "failed")

    def test_e2e_patterns(self):
        self.assertEqual(classify_test_command("make test", "/m/web/e2e")["layer"], "e2e")
        self.assertEqual(classify_test_command(".venv/bin/pytest tests/unit", "/m/py", e2e=("qa-suite",))["layer"], "unit")
        self.assertEqual(classify_test_command("make test", "/m/qa-suite")["layer"], "unknown")

    def test_cli_e2e_and_default_root(self):
        work = Path(self.tmp.name).resolve() / "work"
        work.mkdir()
        projects = Path(self.tmp.name) / "projects"
        write(projects / encode_project_dir(str(work)) / f"{A}.jsonl",
              [user_prompt("hi", ts(0), cwd=str(work / "qa-suite"))]
              + [tool_use("t1", "Bash", {"command": "make test"}, ts(1), cwd=str(work / "qa-suite")),
                 tool_result("t1", GO_OK, ts=ts(2))])
        script = Path(__file__).resolve().parent.parent / "skills/bogusz/scripts/sessions.py"
        env = {**os.environ, "BOGUSZ_PROJECTS_ROOT": str(projects)}
        r = subprocess.run([sys.executable, "-I", str(script), "show", "last", "--e2e", "qa-suite"],
                           env=env, capture_output=True, text=True, cwd=work)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["tests"][0]["layer"], "e2e")
        r = subprocess.run([sys.executable, "-I", str(script), "list", "--root", "/elsewhere"],
                           env=env, capture_output=True, text=True, cwd=work)
        self.assertEqual(r.stdout, "")

    def test_cli_runs_isolated(self):
        # SKILL.md runs the script with `python3 -I`, which drops the script's folder from sys.path
        root = Path(self.tmp.name)
        write(root / "-m-repo" / f"{A}.jsonl", [user_prompt("hi", ts(0))])
        script = Path(__file__).resolve().parent.parent / "skills/bogusz/scripts/sessions.py"
        env = {**os.environ, "BOGUSZ_PROJECTS_ROOT": str(root)}
        r = subprocess.run([sys.executable, "-I", str(script), "list", "--root", "/m"], env=env, capture_output=True, text=True, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["session_id"], A)


if __name__ == "__main__":
    unittest.main()
