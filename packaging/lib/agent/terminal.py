import os
import sys
from pathlib import Path

from rich.console import Console as RichConsole
from rich.table import Table as RichTable
from rich.theme import Theme

# Revona brand theme
REVONA_THEME = Theme({
    "brand": "bold bright_blue on black",
    "success": "bright_green",
    "warning": "bright_yellow",
    "error": "bright_red",
    "muted": "bright_black",
    "accent": "bright_blue",
    "cyan": "cyan",
    "info": "white",
    "dim": "bright_black",
})


def detect() -> dict:
    """Detect terminal/IDE environment capabilities."""
    return {
        "is_tty": sys.stdout.isatty(),
        "is_ci": os.environ.get("CI") == "true",
        "no_color": os.environ.get("NO_COLOR") is not None,
        "term_program": os.environ.get("TERM_PROGRAM", ""),
        "term": os.environ.get("TERM", ""),
        "wt_session": "WT_SESSION" in os.environ,
        "conemu": os.environ.get("ConEmuANSI") == "ON",
        "encoding": sys.stdout.encoding or "",
        "is_windows": sys.platform == "win32",
        "is_vscode": os.environ.get("TERM_PROGRAM") == "vscode",
        "is_jetbrains": bool(os.environ.get("TERMINAL_EMULATOR", "").startswith("JetBrains")),
    }


def unicode_ok(info: dict | None = None) -> bool:
    """Whether the terminal likely supports Unicode box-drawing."""
    if info is None:
        info = detect()
    if info["is_vscode"] or info["is_jetbrains"]:
        return True
    if info["wt_session"] or info["conemu"]:
        return True
    if info["term"] in ("xterm-256color", "xterm-kitty", "alacritty", "wezterm", "tmux-256color"):
        return True
    enc = info["encoding"].lower()
    if enc in ("utf-8", "utf8"):
        return True
    return False


_INFO = detect()

if _INFO["is_windows"]:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

if not _INFO["is_tty"] or _INFO["is_ci"]:
    console = RichConsole(no_color=True, force_terminal=False)
elif _INFO["no_color"]:
    console = RichConsole(no_color=True, force_terminal=True)
else:
    console = RichConsole(highlight=False, theme=REVONA_THEME)


def make_console(info: dict | None = None) -> RichConsole:
    """Build a Console tuned to the current terminal."""
    return console


def print_table(
    console: RichConsole,
    title: str,
    columns: list[str],
    rows: list[list[str]],
    info: dict | None = None,
) -> None:
    """Print a table, falling back to plain text when Unicode is unavailable."""
    if info is None:
        info = detect()

    if unicode_ok(info) and info["is_tty"] and not info["no_color"]:
        table = RichTable(title=title)
        for c in columns:
            table.add_column(c)
        for r in rows:
            table.add_row(*r)
        console.print(table)
        return

    console.print(f"\n--- {title} ---")
    header = "  |  ".join(columns)
    sep = "=" * len(header)
    console.print(header)
    console.print(sep)
    for r in rows:
        console.print("  |  ".join(r))
    console.print(f"({len(rows)} items)")
