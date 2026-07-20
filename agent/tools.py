import difflib
import json
import os
import subprocess
import time
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
        lines = text.splitlines()
        close = difflib.get_close_matches(old.strip(), lines, n=3, cutoff=0.5)
        hint = ""
        if close:
            hint = "\nClose matches found:\n" + "\n".join(f"  > {l.strip()}" for l in close)
        ctx_lines = []
        old_stripped = old.strip()
        for i, line in enumerate(lines):
            if any(w in line.lower() for w in old_stripped.lower().split() if len(w) > 3):
                ctx_lines.append(f"  L{i+1}: {line.rstrip()}")
        ctx_hint = ""
        if ctx_lines:
            ctx_hint = "\nRelevant lines in file:\n" + "\n".join(ctx_lines[:5])
        return f"ERROR: old string not found in {path}.{hint}{ctx_hint}\nRead the file first with read_file to get the exact text."
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    return f"Edited {path} ({len(old)} -> {len(new)} chars)"


def list_files(path: str = ".") -> str:
    p = Path(path)
    if not p.exists():
        return f"ERROR: path not found: {path}"
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    lines = []
    for d in items:
        if d.name.startswith(".") and d.name != ".gitignore":
            continue
        if d.name in ("__pycache__", "node_modules", ".git"):
            continue
        if d.is_dir():
            try:
                count = sum(1 for _ in d.iterdir())
            except Exception:
                count = "?"
            lines.append(f"  {d.name}/  ({count} items)")
        else:
            try:
                size = _fmt_size(d.stat().st_size)
            except Exception:
                size = "?"
            lines.append(f"  {d.name}  ({size})")
    if not lines:
        return f"Empty directory: {path}"
    return f"{path}/\n" + "\n".join(lines)


def grep_files(pattern: str, path: str = ".") -> str:
    out = []
    file_count = 0
    matched_files = set()
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in __import__("agent").IGNORE_DIRS]
        for fn in files:
            fp = Path(root) / fn
            try:
                for i, line in enumerate(fp.read_text(errors="ignore").splitlines(), 1):
                    if pattern in line:
                        out.append(f"{fp}:{i}: {line.strip()}")
                        matched_files.add(str(fp))
            except Exception:
                continue
    file_count = len(matched_files)
    result = "\n".join(out[:200])
    if not result:
        return f"No matches for '{pattern}'."
    summary = f"Found {len(out)} matches in {file_count} files."
    if len(out) > 200:
        summary += f" (showing first 200 of {len(out)})"
    return f"{summary}\n{result}"


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}TB"


def _fmt_time(ts: float) -> str:
    diff = time.time() - ts
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff/60)}m ago"
    if diff < 86400:
        return f"{int(diff/3600)}h ago"
    if diff < 604800:
        return f"{int(diff/86400)}d ago"
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def move_file(source: str, destination: str) -> str:
    src = Path(source)
    dst = Path(destination)
    if not src.exists():
        return f"ERROR: source not found: {source}"
    if dst.exists():
        return f"ERROR: destination already exists: {destination}"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return f"Moved {source} -> {destination}"
    except Exception as e:
        return f"ERROR moving {source}: {e}"


def copy_file(source: str, destination: str) -> str:
    import shutil
    src = Path(source)
    dst = Path(destination)
    if not src.exists():
        return f"ERROR: source not found: {source}"
    if dst.exists():
        return f"ERROR: destination already exists: {destination}"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
            return f"Copied directory {source} -> {destination}"
        else:
            shutil.copy2(src, dst)
            return f"Copied {source} -> {destination} ({_fmt_size(dst.stat().st_size)})"
    except Exception as e:
        return f"ERROR copying {source}: {e}"


def delete_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"ERROR: not found: {path}"
    try:
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
            return f"Deleted directory {path}"
        else:
            p.unlink()
            return f"Deleted {path}"
    except Exception as e:
        return f"ERROR deleting {path}: {e}"


def mkdir(path: str) -> str:
    p = Path(path)
    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"Created directory {path}"
    except Exception as e:
        return f"ERROR creating {path}: {e}"


def tree(path: str = ".", depth: int = 3) -> str:
    root = Path(path)
    if not root.exists():
        return f"ERROR: path not found: {path}"
    lines = [f"{root.name}/" if root.is_dir() else root.name]
    _tree_build(root, lines, "", depth, 0)
    return "\n".join(lines)


def _tree_build(current: Path, lines: list, prefix: str, max_depth: int, current_depth: int):
    if current_depth >= max_depth:
        return
    try:
        entries = sorted(current.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    except PermissionError:
        return
    entries = [e for e in entries if not e.name.startswith(".") or e.name == ".gitignore"]
    for i, entry in enumerate(entries):
        if entry.name.startswith("__pycache__") or entry.name == "node_modules":
            continue
        is_last = i == len(entries) - 1
        connector = "\\--- " if is_last else "|--- "
        if entry.is_dir():
            lines.append(f"{prefix}{connector}{entry.name}/")
            extension = "    " if is_last else "|   "
            _tree_build(entry, lines, prefix + extension, max_depth, current_depth + 1)
        else:
            try:
                size = _fmt_size(entry.stat().st_size)
            except Exception:
                size = "?"
            lines.append(f"{prefix}{connector}{entry.name}  ({size})")


def file_info(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"ERROR: not found: {path}"
    try:
        stat = p.stat()
        info = [
            f"Path:       {path}",
            f"Type:       {'Directory' if p.is_dir() else 'File'}",
            f"Size:       {_fmt_size(stat.st_size)} ({stat.st_size} bytes)",
            f"Modified:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))} ({_fmt_time(stat.st_mtime)})",
            f"Created:    {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_ctime))} ({_fmt_time(stat.st_ctime)})",
            f"Permissions: {oct(stat.st_mode)[-3:]}",
        ]
        if p.is_file():
            ext = p.suffix.lower()
            info.append(f"Extension:  {ext or '(none)'}")
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                lines = text.count("\n") + 1
                info.append(f"Lines:      {lines}")
            except Exception:
                pass
        elif p.is_dir():
            try:
                children = list(p.iterdir())
                dirs = sum(1 for c in children if c.is_dir())
                files = len(children) - dirs
                info.append(f"Contents:   {dirs} directories, {files} files")
            except Exception:
                pass
        return "\n".join(info)
    except Exception as e:
        return f"ERROR: {e}"


def find_files(pattern: str, path: str = ".") -> str:
    root = Path(path)
    if not root.exists():
        return f"ERROR: path not found: {path}"
    matches = []
    try:
        for p in root.rglob(pattern):
            if any(part.startswith(".") and part != ".gitignore" for part in p.relative_to(root).parts):
                continue
            if any(part in ("__pycache__", "node_modules", ".git") for part in p.relative_to(root).parts):
                continue
            try:
                size = _fmt_size(p.stat().st_size)
            except Exception:
                size = "?"
            matches.append(f"{p.relative_to(root)}  ({size})")
    except Exception as e:
        return f"ERROR: {e}"
    if not matches:
        return f"No files matching '{pattern}' in {path}"
    result = f"Found {len(matches)} files matching '{pattern}':\n" + "\n".join(matches[:50])
    if len(matches) > 50:
        result += f"\n... and {len(matches) - 50} more"
    return result


def git_status(path: str = ".") -> str:
    try:
        r = subprocess.run(
            "git status --porcelain", shell=True, cwd=path,
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return f"Not a git repository or git not available."
        lines = r.stdout.strip().split("\n") if r.stdout.strip() else []
        if not lines:
            return "Working tree clean — no changes."
        status_map = {
            "M": "modified", "A": "added", "D": "deleted",
            "R": "renamed", "C": "copied", "?": "untracked",
        }
        grouped = {}
        for line in lines:
            if len(line) < 4:
                continue
            code = line[:2].strip()
            filepath = line[3:]
            label = status_map.get(code[0], code) if code else status_map.get(code[-1], "unknown")
            grouped.setdefault(label, []).append(filepath)
        parts = [f"Git status ({len(lines)} changes):"]
        for label, files in grouped.items():
            parts.append(f"\n  {label.upper()} ({len(files)}):")
            for f in files[:20]:
                parts.append(f"    {f}")
            if len(files) > 20:
                parts.append(f"    ... and {len(files) - 20} more")
        return "\n".join(parts)
    except Exception as e:
        return f"ERROR: {e}"


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
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a file/directory. Fails if destination exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Current path."},
                    "destination": {"type": "string", "description": "New path."},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copy a file or directory. Fails if destination exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Path to copy from."},
                    "destination": {"type": "string", "description": "Path to copy to."},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory permanently.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mkdir",
            "description": "Create a directory (and parents).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tree",
            "description": "Show a recursive directory tree with file sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Root path (default: current dir)."},
                    "depth": {"type": "integer", "description": "Max depth (default: 3)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_info",
            "description": "Show detailed file metadata: size, dates, permissions, lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to inspect."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": "Find files by glob pattern (e.g. '*.py', '**/*.ts').",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern."},
                    "path": {"type": "string", "description": "Directory to search in (default: .)."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show git status of the repository (modified, added, untracked files).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repository path (default: .)."},
                },
            },
        },
    },
]


def execute_tool(name: str, args: dict) -> str:
    args = args or {}
    start = time.time()
    result = ""
    allowed = True
    try:
        if name == "read_file":
            result = read_file(args.get("path", ""))
        elif name == "write_file":
            result = write_file(args.get("path", ""), args.get("content", ""))
        elif name == "edit_file":
            result = edit_file(args.get("path", ""), args.get("old", ""), args.get("new", ""))
        elif name == "list_files":
            result = list_files(args.get("path", "."))
        elif name == "grep_files":
            result = grep_files(args.get("pattern", ""), args.get("path", "."))
        elif name == "run_shell":
            result = run_shell(args.get("command", ""), args.get("cwd", "."))
        elif name == "web_fetch":
            result = web_fetch(args.get("url", ""))
        elif name == "move_file":
            result = move_file(args.get("source", ""), args.get("destination", ""))
        elif name == "copy_file":
            result = copy_file(args.get("source", ""), args.get("destination", ""))
        elif name == "delete_file":
            result = delete_file(args.get("path", ""))
        elif name == "mkdir":
            result = mkdir(args.get("path", ""))
        elif name == "tree":
            result = tree(args.get("path", "."), args.get("depth", 3))
        elif name == "file_info":
            result = file_info(args.get("path", ""))
        elif name == "find_files":
            result = find_files(args.get("pattern", ""), args.get("path", "."))
        elif name == "git_status":
            result = git_status(args.get("path", "."))
        else:
            result = f"ERROR: unknown tool {name}"
    except Exception as e:
        result = f"ERROR executing {name}: {e}"
        allowed = False

    duration = (time.time() - start) * 1000
    try:
        from .governance import AuditLogger, AuditEntry
        _audit = AuditLogger()
        _audit.log(AuditEntry(
            timestamp=time.time(),
            agent="agent",
            action="tool_call",
            tool=name,
            args=args,
            result=result[:500],
            allowed=allowed,
            duration_ms=duration,
            metadata={},
        ))
    except Exception:
        pass

    return result


TOOL_INDEX: dict[str, int] = {}
for _i, _s in enumerate(TOOL_SCHEMAS):
    TOOL_INDEX[_s["function"]["name"]] = _i

