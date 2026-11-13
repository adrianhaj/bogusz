"""Read-only, redacted digests of Claude Code session transcripts under the given project roots."""

import argparse
import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePath

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `python3 -I` leaves the script dir off sys.path

from redact import redact, redact_text  # noqa: E402

KNOWN_TYPES = {"user", "assistant", "system", "summary"}
KNOWN_IGNORED = {
    "mode", "permission-mode", "file-history-snapshot", "attachment", "last-prompt",
    "queue-operation", "ai-title", "cost-state", "api-request", "api-request-blob", "api-request-shape",
    "atis-latch", "session-owner", "pr-link", "custom-title", "agent-name", "relocated", "frame-link", "tools-used",
    "file-history-delta", "artifact-autoreact-ledger", "artifact-comment-monitor",
}
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def encode_project_dir(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def project_dirs(projects_root: Path, roots: list[Path]) -> list[Path]:
    encs = [encode_project_dir(str(r)) for r in roots]
    if not projects_root.is_dir():
        return []
    return sorted(
        d for d in projects_root.iterdir()
        if d.is_dir() and any(d.name == e or d.name.startswith(e + "-") for e in encs)
    )


def _entries(path: Path):
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except ValueError:
                yield None


def _first_cwd(path: Path) -> str | None:
    try:
        for e in _entries(path):
            if isinstance(e, dict) and isinstance(e.get("cwd"), str):
                return e["cwd"]
    except OSError:
        pass
    return None


def _content(entry: dict) -> object:
    msg = entry.get("message")
    return msg.get("content") if isinstance(msg, dict) else None


def _prompt_text(entry: dict) -> str | None:
    """Text of a prompt the user typed; None for tool results, meta entries, compaction summaries and non-user entries."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
        return None
    content = _content(entry)
    if isinstance(content, str):
        return content
    if isinstance(content, list) and not any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        return "\n".join(texts) if texts else None
    return None


def _in_scope(projects_root: Path, roots: list[Path], name: str = "*") -> list[Path]:
    root = projects_root.resolve()
    found = []
    for d in project_dirs(projects_root, roots):
        for f in d.glob(f"{name}.jsonl"):
            try:
                real = f.resolve()
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if not real.is_relative_to(root):
                continue
            cwd = _first_cwd(real)
            if cwd and any(PurePath(cwd).is_relative_to(r) for r in roots):
                found.append((f, mtime))
    return found


def find_transcript(ref: str, projects_root: Path, roots: list[Path], exclude: str | None = None) -> Path:
    if ref != "last" and not UUID_RE.match(ref):
        raise ValueError(f"session ref must be 'last' or a session UUID, got {ref!r}")
    name = "*" if ref == "last" else ref
    candidates = [(f, t) for f, t in _in_scope(projects_root, roots, name) if f.stem != exclude]
    if ref == "last":
        if not candidates:
            raise LookupError("no sessions found under the given roots")
        return max(candidates, key=lambda x: x[1])[0]
    for f, _ in candidates:
        if f.stem == ref:
            return f
    raise LookupError(f"session {ref} not found under the given roots")


def list_sessions(projects_root: Path, roots: list[Path], limit: int = 20) -> list[dict]:
    files = sorted(_in_scope(projects_root, roots), key=lambda x: x[1], reverse=True)[:limit]
    home = encode_project_dir(str(Path.home()))
    out = []
    for f, mtime in files:
        try:
            prompt = next((t for e in _entries(f) if isinstance(e, dict) and (t := _prompt_text(e))), "")
        except OSError:
            continue
        out.append({
            "session_id": f.stem,
            "project": "~" + f.parent.name[len(home):] if f.parent.name.startswith(home) else f.parent.name,
            "modified": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
            "first_prompt": redact_text(prompt)[:120],
        })
    return out


def _ts(value: object) -> datetime | None:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, timezone.utc)
        if isinstance(value, str) and value:
            t = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        pass
    return None


def _cut(value: object, limit: int = 500) -> object:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return [_cut(v, limit) for v in value]
    if isinstance(value, dict):
        return {k: _cut(v, limit) for k, v in value.items()}
    return value


def _tail(text: str) -> str:
    return "\n".join(line[:200] for line in redact_text(text).splitlines()[-20:])


def _result_text(entry: dict, item: dict) -> str:
    r = entry.get("toolUseResult")
    if isinstance(r, dict) and "stdout" in r:
        return (r.get("stdout") or "") + ("\n" + r["stderr"] if r.get("stderr") else "")
    content = item.get("content")
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return content if isinstance(content, str) else ""


def parse_transcript(path: Path, e2e: tuple[str, ...] = ()) -> dict:
    session_dir = (path.parent / path.stem).resolve()
    files = [("main", path)] + [
        (f.stem, f) for f in sorted((path.parent / path.stem / "subagents").glob("*.jsonl"))
        if f.resolve().is_relative_to(session_dir)
    ]
    meta = {"session_id": path.stem, "cwd": None, "git_branch": None, "version": None}
    items, results, spans = [], {}, []
    malformed, unknown = 0, {}
    order, main_ts = 0, []

    for agent, f in files:
        try:
            entries = list(_entries(f))
        except OSError:
            continue
        last_ts = None
        for e in entries:
            if not isinstance(e, dict):
                malformed += 1
                continue
            kind = e.get("type")
            kind = kind if isinstance(kind, str) else str(kind)
            if kind not in KNOWN_TYPES:
                if kind not in KNOWN_IGNORED:
                    unknown[kind] = unknown.get(kind, 0) + 1
                continue
            ts = _ts(e.get("timestamp")) or last_ts
            last_ts = ts
            if agent == "main":
                if ts:
                    main_ts.append(ts)
                for key, field in (("cwd", "cwd"), ("git_branch", "gitBranch"), ("version", "version")):
                    meta[key] = meta[key] or e.get(field)
            order += 1
            text = _prompt_text(e) if agent == "main" else None
            if text:
                items.append((ts, order, {"kind": "prompt", "ts": e.get("timestamp"), "text": redact_text(text)[:500]}))
                continue
            content = _content(e)
            for c in content if isinstance(content, list) else []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text" and kind == "assistant":
                    spans.extend(_code_spans(c.get("text") or ""))
                elif c.get("type") == "tool_use":
                    call = {"kind": "tool", "id": c.get("id"), "ts": e.get("timestamp"), "agent": agent,
                            "tool": c.get("name"), "cwd": e.get("cwd") if isinstance(e.get("cwd"), str) else "",
                            "raw_input": c["input"] if isinstance(c.get("input"), dict) else {"value": c.get("input")}}
                    items.append((ts, order, call))
                elif c.get("type") == "tool_result":
                    r = e.get("toolUseResult")
                    results[c.get("tool_use_id")] = {
                        "ts": ts, "is_error": bool(c.get("is_error")), "text": _result_text(e, c),
                        "interrupted": isinstance(r, dict) and bool(r.get("interrupted")),
                    }

    # ponytail: entries with no timestamp borrow the previous one's in the same file; sort is stable by file order otherwise
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    items.sort(key=lambda x: (x[0] or epoch, x[1]))

    prompts, calls, interrupted = [], [], False
    for seq, (ts, _, item) in enumerate(items, 1):
        if item["kind"] == "prompt":
            prompts.append({"seq": seq, "ts": item["ts"], "text": item["text"]})
            continue
        res = results.get(item["id"])
        done = res is not None
        interrupted = interrupted or not done or res["interrupted"]
        calls.append({
            "seq": seq, "ts": item["ts"], "agent": item["agent"], "tool": item["tool"],
            "input": _cut(redact(item["raw_input"])),
            "completed": done,
            "is_error": res["is_error"] if done else None,
            "duration_s": (res["ts"] - ts).total_seconds() if done and res["ts"] and ts else None,
            "output_tail": _tail(res["text"]) if done else "",
            "_raw_input": item["raw_input"], "_output": res["text"] if done else "", "_cwd": item["cwd"],
        })

    tests = _tests(calls, e2e)
    ran = {_norm(c["_raw_input"]["command"]) for c in calls
           if c["tool"] == "Bash" and isinstance(c["_raw_input"].get("command"), str)}
    discussed = []
    for s in spans:
        n = _norm(s)
        if n not in ran and n not in discussed and classify_test_command(n, ""):
            discussed.append(n)

    files_modified = sorted({
        p for c in calls if _edited(c)
        for p in [c["_raw_input"].get("file_path") or c["_raw_input"].get("notebook_path")]
        if isinstance(p, str)
    })
    digest = {
        **redact(meta),
        "started_at": min(main_ts).isoformat() if main_ts else None,
        "ended_at": max(main_ts).isoformat() if main_ts else None,
        "prompts": prompts,
        "tool_calls": calls,
        "tests": tests,
        "discussed_not_run": [redact_text(s) for s in discussed],
        "files_modified": [redact_text(f) for f in files_modified],
        "interrupted": interrupted,
        "malformed_lines": malformed,
        "unknown_entry_types": {redact_text(k)[:100]: v for k, v in unknown.items()},
    }
    for c in calls:
        del c["_raw_input"], c["_output"], c["_cwd"]
    return digest


def _norm(command: str) -> str:
    return " ".join(command.split())


def _edited(call: dict) -> bool:
    """An edit call that was not refused; one with no recorded result still counts."""
    return call["tool"] in EDIT_TOOLS and call["is_error"] is not True


def _code_spans(text: str) -> list[str]:
    fenced = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    lines = [line for block in fenced for line in block.splitlines() if line.strip()]
    inline = re.findall(r"(?<!`)`([^`\n]+)`(?!`)", re.sub(r"```.*?```", "", text, flags=re.S))
    return lines + inline


def _runner(words: list[str]) -> str | None:
    while words:
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]) or words[0] == "env":
            words = words[1:]
        elif PurePath(words[0]).name in {"uv", "poetry", "pipenv"} and words[1:2] == ["run"]:
            words = words[2:]
        elif words[0] == "timeout" and len(words) > 1:
            words = words[2:]
        else:
            break
    if not words:
        return None
    head, rest = PurePath(words[0]).name, words[1:]
    if {"--help", "--version"} & set(rest):
        return None
    via_pm = head in {"npx", "bunx", "npm", "pnpm", "yarn"}
    js_bin = rest[1:] if rest[:1] == ["exec"] else rest  # `pnpm exec playwright test`, `yarn vitest`
    if head == "make":
        rest = [w for i, w in enumerate(rest) if not (w == "-C" or (i and rest[i - 1] == "-C"))]
    if (head == "go" and rest[:1] == ["test"]) or head == "gotestsum":
        return "go"
    if (via_pm and js_bin[:2] == ["playwright", "test"]) or (head == "playwright" and rest[:1] == ["test"]):
        return "playwright"
    if head in {"npm", "yarn", "pnpm"} and rest[:1] == ["run"] and rest[1:2] and rest[1].startswith("e2e"):
        return "playwright"
    if head == "k6" and rest[:1] == ["run"]:
        return "k6"
    if head == "govulncheck":
        return "govulncheck"
    if head == "trivy" and rest[:1] and rest[0] in {"fs", "filesystem", "image", "repo", "config"}:
        return "trivy"
    if head == "npm" and rest[:1] == ["audit"]:
        return "npm-audit"
    if head == "pip-audit":
        return "pip-audit"
    if head == "cargo" and rest[:1] == ["audit"]:
        return "cargo-audit"
    if head == "locust":
        return "locust"
    if head == "pytest" or (head.startswith("python") and rest[:2] == ["-m", "pytest"]):
        return "pytest"
    if head == "make" and rest[:1] and (rest[0] in {"test", "e2e", "it"} or rest[0].startswith("test-")):
        return "make"
    if head in {"npm", "yarn", "pnpm"} and (
        rest[:1] == ["test"] or (rest[:1] == ["run"] and rest[1:2] and re.fullmatch(r"test(?::\S*)?", rest[1]))
    ):
        return "js"
    if via_pm and js_bin[:1] and js_bin[0] in {"vitest", "jest"}:
        return "js"
    # ponytail: the runners below without an outcome parser show up as `unknown`; add a parser when a project needs one
    if head.startswith("python") and rest[:2] == ["-m", "unittest"]:
        return "unittest"
    if head in {"cargo", "bun", "dotnet"} and rest[:1] == ["test"]:
        return head
    if head == "tox":
        return "tox"
    if head in {"mvn", "mvnw"} and {"test", "verify"} & set(rest):
        return "maven"
    if head in {"gradle", "gradlew"} and any(w == "test" or w.endswith(":test") for w in rest):
        return "gradle"
    return None


def classify_test_command(command: str, cwd: str, e2e: tuple[str, ...] = ()) -> dict | None:
    for segment in re.split(r"&&|\|\||;|\||\n", command):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        runner = _runner(words)
        if runner:
            break
    else:
        return None
    where = f"{cwd} {command}"
    if runner == "playwright":
        layer = "ui"
    elif runner in {"k6", "locust"} or (runner == "go" and "-bench" in command):
        layer = "perf"
    elif runner in {"govulncheck", "trivy", "npm-audit", "pip-audit", "cargo-audit"}:
        layer = "security"
    elif "e2e" in where or any(p in where for p in e2e):
        layer = "e2e"
    elif "integration" in command:
        layer = "integration"
    elif re.search(r"(?<![A-Za-z])unit(?![A-Za-z])", command):
        layer = "unit"
    else:
        layer = "unknown"
    return {"runner": runner, "layer": layer}


_GO_SUMMARY = re.compile(r"^(ok|FAIL): (\d+) passed, (\d+) failed, (\d+) build-failed, (\d+) skipped", re.M)
_PYTEST_SUMMARY = re.compile(r"^(?:=+ )?(\d+ \w+(?:, \d+ \w+)*) in [\d.]+s\b", re.M)
_PLAYWRIGHT_SUMMARY = re.compile(r"^\s*(\d+) (passed|failed|flaky|skipped)(?: \([\d.]+(?:ms|s|m|h)\))?\s*$", re.M)
_JS_SUMMARY = re.compile(r"^\s*Tests:?\s+(.*\d+ (?:passed|failed).*)$", re.M)  # Jest `Tests:`, Vitest `Tests`
_PLAYWRIGHT_FAILED = re.compile(r"^\s*(?:\d+\) )?(\[[\w-]+\] › .+?)(?:\s+─+)?\s*$", re.M)
_REFUSED = re.compile(  # a hook or a permission prompt stopped the command before it ran
    r"^(?:PreToolUse:\S+ hook error:|Permission for this (?:action|command) was denied"
    r"|This (?:Bash )?command (?:contains multiple operations\. The following part )?requires approval"
    r"|The user doesn't want to proceed with this tool use)"
)
_UNITTEST_SUMMARY = re.compile(r"^Ran (\d+) tests? in [\d.]+s\s+^(?:OK|FAILED|NO TESTS RAN)(?: \((.*)\))?", re.M)
_CARGO_SUMMARY = re.compile(r"^test result: \w+\. (\d+) passed; (\d+) failed; (\d+) ignored", re.M)
_FAILURE_LINE = re.compile(r"--- FAIL|^E\s|^(?:FAIL|ERROR)\b|^FAILED\b|panicked|Error\b|Exception\b")


def _failure_excerpt(output: str) -> str:
    """Up to 25 lines around the first line that reports a failure: the message is rarely in the last lines."""
    lines = redact_text(output).splitlines()
    first = next((i for i, line in enumerate(lines) if _FAILURE_LINE.search(line)), 0)
    return "\n".join(line[:200] for line in lines[max(first - 10, 0):first + 15])


def parse_test_outcome(output: str, completed: bool, is_error: bool | None, command: str = "") -> dict:
    """A command that hides the runner's exit code is never `passed`; a run that executed no test is `no_tests`."""
    out = {"status": "unknown", "passed": None, "failed": None, "skipped": None, "failed_tests": [], "failure_excerpt": ""}
    no_tests = False
    if not completed:
        out["status"] = "not_completed"
        return out
    if _REFUSED.match(output):
        out["status"] = "blocked"
        return out
    out["failed_tests"] = list(dict.fromkeys(
        re.findall(r"^\s*--- FAIL: (\S+)", output, re.M) + re.findall(r"^FAILED ([^\s(]\S*)", output, re.M)
        + _PLAYWRIGHT_FAILED.findall(output)
    ))
    failed_flag, recognized = False, False
    if m := _GO_SUMMARY.search(output):
        recognized, failed_flag = True, m.group(1) == "FAIL"
        out.update(passed=int(m.group(2)), failed=int(m.group(3)) + int(m.group(4)), skipped=int(m.group(5)))
    elif m := _UNITTEST_SUMMARY.search(output):
        recognized = True
        counts = {k: int(n) for k, n in re.findall(r"([a-z][a-z ]*)=(\d+)", m.group(2) or "")}
        failed = sum(counts.get(k, 0) for k in ("failures", "errors", "unexpected successes"))
        skipped = counts.get("skipped", 0)
        out.update(passed=int(m.group(1)) - failed - skipped, failed=failed, skipped=skipped)
        out["failed_tests"] += re.findall(r"^(?:FAIL|ERROR): (\S+ \(\S+\))$", output, re.M)
    elif cargo := _CARGO_SUMMARY.findall(output):
        recognized = True
        out.update(passed=sum(int(c[0]) for c in cargo), failed=sum(int(c[1]) for c in cargo),
                   skipped=sum(int(c[2]) for c in cargo))
        out["failed_tests"] += dict.fromkeys(re.findall(r"^(?:test )?(\S+) (?:\.\.\.|---) FAILED$", output, re.M))
    elif ms := _PYTEST_SUMMARY.findall(output):
        counts = {}
        for summary in ms:
            for n, k in re.findall(r"(\d+) (passed|failed|errors?|skipped)", summary):
                k = "error" if k.startswith("error") else k
                counts[k] = counts.get(k, 0) + int(n)
        if counts:
            recognized = True
            out.update(passed=counts.get("passed", 0), failed=counts.get("failed", 0) + counts.get("error", 0),
                       skipped=counts.get("skipped", 0))
    elif pw := _PLAYWRIGHT_SUMMARY.findall(output):
        recognized = True
        out.update(passed=sum(int(n) for n, k in pw if k in {"passed", "flaky"}),
                   failed=sum(int(n) for n, k in pw if k == "failed"),
                   skipped=sum(int(n) for n, k in pw if k == "skipped"))
    elif js := _JS_SUMMARY.findall(output):
        counts = {}
        for n, k in re.findall(r"(\d+) (passed|failed|skipped|todo)", " ".join(js)):
            counts[k] = counts.get(k, 0) + int(n)
        recognized = True
        out.update(passed=counts.get("passed", 0), failed=counts.get("failed", 0),
                   skipped=counts.get("skipped", 0) + counts.get("todo", 0))
    elif "http_req_" in output:
        recognized, failed_flag = True, bool(re.search(r"^\s*✗ ", output, re.M))
    elif "No vulnerabilities found" in output or (vuln := re.search(r"affected by (\d+) vulnerabilit", output)):
        recognized = True
        out["failed"] = int(vuln.group(1)) if "No vulnerabilities found" not in output else 0
    elif totals := re.findall(r"^(?:Total|Failures): (\d+) \(", output, re.M):
        recognized = True
        out["failed"] = sum(int(n) for n in totals)
    elif "found 0 vulnerabilities" in output or (audit := re.search(r"^(\d+) (?:[a-z]+ severity )?vulnerabilit(?:y|ies)\b", output, re.M)):
        recognized = True
        out["failed"] = int(audit.group(1)) if "found 0 vulnerabilities" not in output else 0
    else:
        marks = re.findall(r"^\s*--- (PASS|FAIL|SKIP):", output, re.M)
        pkg_ok = re.findall(r"^ok\s.*$", output, re.M)
        failed_flag = bool(re.search(r"^FAIL\b", output, re.M))
        if marks:
            out.update(passed=marks.count("PASS"), failed=marks.count("FAIL"), skipped=marks.count("SKIP"))
        else:
            no_tests = bool(pkg_ok) and all("[no tests to run]" in line for line in pkg_ok)
        recognized = bool(marks or pkg_ok or failed_flag)
    if failed_flag or (out["failed"] or 0) > 0 or out["failed_tests"]:
        out["status"] = "failed"
        out["failure_excerpt"] = _failure_excerpt(output)
    elif recognized and (no_tests or out["passed"] == 0):
        out["status"] = "no_tests"
    elif recognized and is_error is False and not _hides_exit_code(command):
        out["status"] = "passed"
    out["failed_tests"] = [redact_text(t) for t in out["failed_tests"]]
    return out


def _hides_exit_code(command: str) -> bool:
    """True when the shell's exit status may not be the runner's: a pipe or `||` outside quotes, or a last
    command (after `;` or a newline) that is not a test runner."""
    punct = set("();<>|&\n")
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="".join(punct))
        lexer.whitespace, lexer.whitespace_split = " \t\r", True
        tokens = list(lexer)
    except ValueError:
        return any(ch in command for ch in "|;\n")
    statements, current = [], [[]]  # a statement ends at `;` or a newline and holds its simple commands
    for tok in tokens:
        if not set(tok) <= punct:
            current[-1].append(tok)
        elif "|" in tok:
            return True
        elif ";" in tok or "\n" in tok:
            statements.append(current)
            current = [[]]
        else:
            current.append([])
    statements = [s for s in statements + [current] if any(s)]
    return len(statements) > 1 and not any(_runner(words) for words in statements[-1])


def _tests(calls: list[dict], e2e: tuple[str, ...] = ()) -> list[dict]:
    tests, last_edits, attempts, edits_seen = [], {}, {}, 0
    for c in calls:
        edits_seen += _edited(c)
        command = c["_raw_input"].get("command") if c["tool"] == "Bash" else None
        kind = classify_test_command(command, c["_cwd"], e2e) if isinstance(command, str) else None
        if not kind:
            continue
        key = _norm(command)
        prev = last_edits.get(key)
        last_edits[key] = edits_seen
        attempts[key] = attempts.get(key, 0) + 1
        tests.append({
            "seq": c["seq"], "command": redact_text(command)[:500], "agent": c["agent"], **kind,
            "attempt": attempts[key],
            "edits_since_previous_attempt": prev is not None and edits_seen > prev,
            **parse_test_outcome(c["_output"], c["completed"], c["is_error"], command),
        })
    return tests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sessions.py", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--limit", type=int, default=20)
    show = sub.add_parser("show")
    runs = sub.add_parser("tests", help="one JSON line per test run of a session")
    for p in (ls, show, runs):
        p.add_argument("--root", action="append", type=Path, help="project root whose sessions count (default: cwd)")
    for p in (show, runs):
        p.add_argument("--e2e", action="append", default=[], help="path or name fragment that marks an E2E test run")
        p.add_argument("ref")
        p.add_argument("--exclude", nargs="?", help="session id to skip; empty is ignored")
    show.add_argument("--out", help="write the digest to this file (parent dirs created) instead of stdout")
    args = parser.parse_args(argv)

    projects = Path(os.environ.get("BOGUSZ_PROJECTS_ROOT", "~/.claude/projects")).expanduser()
    roots = [r.expanduser().resolve() for r in args.root] if args.root else [Path.cwd()]
    try:
        if args.cmd == "list":
            for s in list_sessions(projects, roots, args.limit):
                print(json.dumps(s))
            return 0
        parsed = parse_transcript(find_transcript(args.ref, projects, roots, args.exclude), tuple(args.e2e))
        if args.cmd == "tests":
            for t in parsed["tests"]:
                print(json.dumps(t))
        else:
            digest = json.dumps(parsed, indent=1)
            if args.out:
                out = Path(args.out).expanduser()
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(digest + "\n")
                print(f"{out} ({len(digest.splitlines()) + 1} lines)")
            else:
                print(digest)
    except (ValueError, LookupError) as e:
        print(f"sessions.py: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
