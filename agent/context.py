import os
from pathlib import Path

from . import IGNORE_DIRS, TEXT_EXTS, INDEX_PATH


def _walk(root: Path, max_files: int = 400):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if len(files) >= max_files:
                return files
            files.append(p)
    return files


def build_context(root: str = ".") -> str:
    """Return a compact repo overview: file tree + small file previews."""
    root_path = Path(root).resolve()
    files = _walk(root_path)
    rel = [str(p.relative_to(root_path)) for p in files]

    lines = ["# Repository overview", "", "## File tree", ""]
    lines.extend(f"- {r}" for r in sorted(rel))

    lines += ["", "## Small file contents (<200 lines)", ""]
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if text.count("\n") > 200 or p.suffix not in TEXT_EXTS:
            continue
        relp = str(p.relative_to(root_path))
        lines.append(f"### {relp}")
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
