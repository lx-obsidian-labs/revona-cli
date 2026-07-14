import json
import os
import subprocess
from pathlib import Path

import requests

SHELL_ALLOWLIST = (
    "npm", "pnpm", "yarn", "node", "python", "python3", "pytest", "pip",
    "cargo", "go", "make", "git status", "git diff", "git log", "ls",
    "cat", "type", "ruff", "black", "mypy", "tsc", "eslint", "prettier",
)


def _safe_shell(cmd: str) -> bool:
    c = cmd.strip().lower()
    return any(c.startswith(allow) for allow in SHELL_ALLOWLIST)


def read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"ERROR: file not found: {path}"
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"ERROR reading {path}: {e}"


def write_file(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {path} ({len(content)} bytes)"


def edit_file(path: str, old: str, new: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"ERROR: file not found: {path}"
    text = p.read_text(encoding="utf-8", errors="ignore")
    if old not in text:
        return "ERROR: old string not found (exact match required)."
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    return f"Edited {path}"


def list_files(path: str = ".") -> str:
    p = Path(path)
    if not p.exists():
        return f"ERROR: path not found: {path}"
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
    return "\n".join(
        (d.name + "/") if d.is_dir() else d.name for d in items
    )


def grep_files(pattern: str, path: str = ".") -> str:
    out = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in __import__("agent").IGNORE_DIRS]
        for fn in files:
            fp = Path(root) / fn
            try:
                for i, line in enumerate(fp.read_text(errors="ignore").splitlines(), 1):
                    if pattern in line:
                        out.append(f"{fp}:{i}: {line}")
            except Exception:
                continue
    return "\n".join(out[:200]) or "No matches."


def run_shell(command: str, cwd: str = ".") -> str:
    if not _safe_shell(command):
        return (
            f"BLOCKED: '{command}' is not in the shell allowlist. "
            "Allowed prefixes: " + ", ".join(SHELL_ALLOWLIST)
        )
    try:
        r = subprocess.run(
            command, shell=True, cwd=cwd, capture_output=True,
            text=True, timeout=300,
        )
        body = (r.stdout or "") + (r.stderr or "")
        return f"exit={r.returncode}\n{body[:8000]}"
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out (300s)."
    except Exception as e:
        return f"ERROR: {e}"


def web_fetch(url: str) -> str:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "revona"})
        return r.text[:8000]
    except Exception as e:
        return f"ERROR fetching {url}: {e}"


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace the first exact occurrence of `old` with `new` in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                },
                "required": ["path", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_files",
            "description": "Search for a substring across repository files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run an allowed build/test/lint shell command. Destructive commands are blocked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a URL's content (for docs when stuck).",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]


def execute_tool(name: str, args: dict) -> str:
    args = args or {}
    try:
        if name == "read_file":
            return read_file(args.get("path", ""))
        if name == "write_file":
            return write_file(args.get("path", ""), args.get("content", ""))
        if name == "edit_file":
            return edit_file(args.get("path", ""), args.get("old", ""), args.get("new", ""))
        if name == "list_files":
            return list_files(args.get("path", "."))
        if name == "grep_files":
            return grep_files(args.get("pattern", ""), args.get("path", "."))
        if name == "run_shell":
            return run_shell(args.get("command", ""), args.get("cwd", "."))
        if name == "web_fetch":
            return web_fetch(args.get("url", ""))
    except Exception as e:
        return f"ERROR executing {name}: {e}"
    return f"ERROR: unknown tool {name}"


TOOL_INDEX: dict[str, int] = {}
for _i, _s in enumerate(TOOL_SCHEMAS):
    TOOL_INDEX[_s["function"]["name"]] = _i

