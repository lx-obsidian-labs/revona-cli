import os
import subprocess
import time
from pathlib import Path

from . import IGNORE_DIRS, TEXT_EXTS, INDEX_PATH


def _load_gitignore(root: Path) -> set[str]:
    patterns = set()
    gitignore = root / ".gitignore"
    if gitignore.exists():
        try:
            for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.add(line.rstrip("/"))
        except Exception:
            pass
    return patterns


def _is_gitignored(path: Path, root: Path, patterns: set[str]) -> bool:
    if not patterns:
        return False
    try:
        rel = str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return False
    for pattern in patterns:
        if pattern in rel:
            return True
        if "/" in pattern:
            if rel.startswith(pattern.rstrip("*")):
                return True
        else:
            parts = rel.split("/")
            for part in parts:
                if part == pattern or (pattern.startswith("*") and part.endswith(pattern[1:])):
                    return True
    return False


def _get_git_status(root: Path) -> dict[str, str]:
    try:
        r = subprocess.run(
            "git status --porcelain", shell=True, cwd=str(root),
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return {}
        status = {}
        for line in r.stdout.strip().split("\n"):
            if len(line) < 4:
                continue
            code = line[:2].strip()
            filepath = line[3:]
            status[filepath] = code
        return status
    except Exception:
        return {}


def _walk(root: Path, max_files: int = 400):
    files = []
    gitignore_patterns = _load_gitignore(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not _is_gitignored(Path(dirpath) / d, root, gitignore_patterns)]
        for fn in filenames:
            p = Path(dirpath) / fn
            if _is_gitignored(p, root, gitignore_patterns):
                continue
            if len(files) >= max_files:
                return files
            files.append(p)
    return files


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}TB"


def _fmt_time(ts: float) -> str:
    diff = time.time() - ts
    if diff < 60:
        return "now"
    if diff < 3600:
        return f"{int(diff/60)}m"
    if diff < 86400:
        return f"{int(diff/3600)}h"
    if diff < 604800:
        return f"{int(diff/86400)}d"
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def _type_icon(ext: str) -> str:
    icons = {
        ".py": "py", ".js": "js", ".ts": "ts", ".tsx": "tsx",
        ".jsx": "jsx", ".json": "{}", ".md": "md", ".html": "<>",
        ".css": "css", ".rs": "rs", ".go": "go", ".java": "jv",
        ".rb": "rb", ".php": "php", ".c": "c", ".cpp": "cpp",
        ".h": "h", ".yaml": "yml", ".yml": "yml", ".toml": "tml",
        ".sh": "sh", ".bash": "sh", ".sql": "sql", ".xml": "<>",
    }
    return icons.get(ext, "..")


def _build_tree(root: Path, files: list[Path], git_status: dict[str, str]) -> str:
    """Build a hierarchical tree view with metadata."""
    tree: dict = {}
    for p in files:
        rel = p.relative_to(root)
        parts = rel.parts
        current = tree
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = p

    lines = []
    _render_tree(tree, lines, "", root, git_status, is_last=True)
    return "\n".join(lines)


def _render_tree(node: dict, lines: list, prefix: str, root: Path, git_status: dict, is_last: bool):
    entries = sorted(node.items(), key=lambda x: (not isinstance(x[1], dict), x[0].lower()))
    for i, (name, value) in enumerate(entries):
        is_final = i == len(entries) - 1
        connector = "\\--- " if is_final else "|--- "
        if isinstance(value, dict):
            lines.append(f"{prefix}{connector}{name}/")
            extension = "    " if is_final else "|   "
            _render_tree(value, lines, prefix + extension, root, git_status, is_final)
        else:
            p = value
            try:
                stat = p.stat()
                size = _fmt_size(stat.st_size)
                age = _fmt_time(stat.st_mtime)
            except Exception:
                size = "?"
                age = "?"
            ext = p.suffix.lower()
            icon = _type_icon(ext)
            rel = str(p.relative_to(root))
            git = ""
            if rel in git_status:
                code = git_status[rel]
                giticons = {"M": "!", "A": "+", "D": "-", "R": "~", "?": "?"}
                git = f" [{giticons.get(code[0], code)}]"
            lines.append(f"{prefix}{connector}{icon} {name}  ({size}, {age}){git}")


def build_context(root: str = ".") -> str:
    """Return a compact repo overview: file tree + small file previews."""
    root_path = Path(root).resolve()
    files = _walk(root_path)
    git_status = _get_git_status(root_path)

    lines = ["# Repository overview", ""]

    tree_view = _build_tree(root_path, files, git_status)
    lines.append("## File tree")
    lines.append("```")
    lines.append(tree_view)
    lines.append("```")

    total_size = sum(p.stat().st_size for p in files if p.exists())
    ext_count: dict[str, int] = {}
    for p in files:
        ext = p.suffix.lower() or "(none)"
        ext_count[ext] = ext_count.get(ext, 0) + 1
    top_exts = sorted(ext_count.items(), key=lambda x: -x[1])[:10]

    lines.append("")
    lines.append("## Stats")
    lines.append(f"- Total files: {len(files)}")
    lines.append(f"- Total size: {_fmt_size(total_size)}")
    if top_exts:
        lines.append("- Breakdown: " + ", ".join(f"{ext}({count})" for ext, count in top_exts))
    if git_status:
        modified = sum(1 for v in git_status.values() if v.startswith("M"))
        added = sum(1 for v in git_status.values() if v.startswith("A"))
        untracked = sum(1 for v in git_status.values() if v.startswith("?"))
        lines.append(f"- Git: {modified} modified, {added} added, {untracked} untracked")

    lines += ["", "## Small file contents (<200 lines)", ""]
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if text.count("\n") > 200 or p.suffix not in TEXT_EXTS:
            continue
        relp = str(p.relative_to(root_path))
        ext = p.suffix.lower()
        icon = _type_icon(ext)
        lines.append(f"### {icon} {relp}")
        lines.append("```")
        lines.append(text)
        lines.append("```")
        if len("\n".join(lines)) > 60000:
            lines.append("...(truncated for size)")
            break

    out = "\n".join(lines)
    try:
        INDEX_PATH.parent.mkdir(exist_ok=True)
        INDEX_PATH.write_text(out, encoding="utf-8")
    except Exception:
        pass
    return out
