"""Synthetic Claude Code transcript builder, shaped like real ~/.claude/projects entries."""

import json
from pathlib import Path

SID = "11111111-1111-4111-8111-111111111111"


def _base(kind, ts, cwd):
    e = {"type": kind, "sessionId": SID, "cwd": cwd, "gitBranch": "main", "version": "2.1.0", "isSidechain": False}
    if ts is not None:
        e["timestamp"] = ts
    return e


def user_prompt(text, ts, cwd="/m/repo"):
    return {**_base("user", ts, cwd), "message": {"role": "user", "content": text}}


def assistant_text(text, ts, cwd="/m/repo"):
    return {**_base("assistant", ts, cwd), "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def tool_use(id, name, input, ts, cwd="/m/repo"):
    return {
        **_base("assistant", ts, cwd),
        "message": {"role": "assistant", "content": [{"type": "tool_use", "id": id, "name": name, "input": input}]},
    }


def tool_result(id, text, is_error=False, ts=None, interrupted=False, cwd="/m/repo"):
    return {
        **_base("user", ts, cwd),
        "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": id, "is_error": is_error, "content": text}]},
        "toolUseResult": {"stdout": text, "stderr": "", "interrupted": interrupted, "isImage": False},
    }


def write(path: Path, entries) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for e in entries:
            f.write((e if isinstance(e, str) else json.dumps(e)) + "\n")
    return path
