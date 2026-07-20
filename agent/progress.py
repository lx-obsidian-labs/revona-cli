import time

from rich.console import Console
from rich.spinner import Spinner
from rich.table import Table

from .terminal import console, unicode_ok, detect

_INFO = detect()


class ProgressEngine:
    """Structured progress display with checkmarks, spinners, and summaries."""

    def __init__(self, title: str = ""):
        self.console = console
        self.title = title
        self.steps: list[dict] = []
        self._current_spinner: Spinner | None = None
        self._start_time = time.time()

    def add_step(self, step_id: str, label: str) -> None:
        self.steps.append({"id": step_id, "label": label, "status": "pending", "error": None})

    def start(self, step_id: str) -> None:
        self._set(step_id, "running")

    def done(self, step_id: str) -> None:
        self._set(step_id, "done")

    def fail(self, step_id: str, reason: str = "") -> None:
        self._set(step_id, "failed", reason)

    def _set(self, step_id: str, status: str, error: str | None = None) -> None:
        for s in self.steps:
            if s["id"] == step_id:
                s["status"] = status
                if error:
                    s["error"] = error
                self._render()
                return

    def _render(self) -> None:
        for s in self.steps:
            icon = self._icon(s["status"])
            label = s["label"]
            if s["error"]:
                self.console.print(f"  {icon} {label}  [red]{s['error']}[/]")
            else:
                self.console.print(f"  {icon} {label}")

    def _icon(self, status: str) -> str:
        if not _INFO["is_tty"] or _INFO["no_color"]:
            return {"pending": " ", "running": "~", "done": "+", "failed": "!"}.get(status, " ")
        if unicode_ok(_INFO):
            return {"pending": " ", "running": "\u25D4", "done": "\u2713", "failed": "\u2717"}.get(status, " ")
        return {"pending": " ", "running": "~", "done": "+", "failed": "x"}.get(status, " ")

    def elapsed(self) -> str:
        t = time.time() - self._start_time
        return f"{t:.0f}s" if t < 120 else f"{t/60:.1f}m"

    def summary(self, mission_stats: str) -> None:
        self.console.print()
        self.console.print(f"[bold]Result:[/] {mission_stats}  [dim]({self.elapsed()})[/]")
