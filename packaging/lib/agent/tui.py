from __future__ import annotations

import itertools
import queue
import threading
import time
from collections import deque
from typing import Any, Callable

from rich.columns import Columns
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, SpinnerColumn
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from . import APP_NAME, COMPANY, C_ACCENT, C_SUCCESS, C_DIM
from .terminal import console, unicode_ok, detect

_INFO = detect()
_U = unicode_ok(_INFO)

# Brand palette (Rich named colours)
_BG = "grey3"
_PANEL = "grey11"
_BORDER = "grey23"
_ACCENT = "bright_blue"
_CYAN = "cyan"
_GREEN = "bright_green"
_AMBER = "bright_yellow"
_RED = "bright_red"
_MUTED = "bright_black"
_WHITE = "white"

_ORB_FRAMES = itertools.cycle(["○", "◐", "◑", "◒"] if _U else ["o", "~", "=", "+"])


# ===================================================================
# Confidence Engine
# ===================================================================

class ConfidenceEngine:
    def __init__(self):
        self._scores: dict[str, float] = {
            "Authentication": 0.0,
            "Architecture": 0.0,
            "Database": 0.0,
            "Security": 0.0,
            "Deployment": 0.0,
        }

    def set(self, domain: str, score: float) -> None:
        self._scores[domain] = max(0.0, min(1.0, score))

    def average(self) -> float:
        vals = list(self._scores.values())
        return sum(vals) / len(vals) if vals else 0.0

    def render(self) -> str:
        lines = []
        for domain, score in sorted(self._scores.items()):
            bar_len = 10
            filled = int(score * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            color = _GREEN if score >= 0.8 else (_AMBER if score >= 0.5 else _RED)
            lines.append(f"  [{color}]{bar}[/] {domain} {score*100:.0f}%")
        return "\n".join(lines)


# ===================================================================
# Engineering Pulse
# ===================================================================

class EngineeringPulse:
    def __init__(self):
        self.health: float = 1.0
        self.risk: str = "Low"
        self.velocity: str = "High"
        self.quality: str = "Excellent"
        self.build: str = "PASS"
        self.tests_passing: float = 100.0
        self.coverage: float = 0.0

    def render(self) -> str:
        health_pct = self.health * 100
        bar_len = 20
        filled = int(health_pct / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        color = _GREEN if health_pct >= 80 else (_AMBER if health_pct >= 50 else _RED)
        return (
            f"  Health   [{color}]{bar}[/] {health_pct:.0f}%\n"
            f"  Build    [{_GREEN if self.build == 'PASS' else _RED}]{self.build}[/]\n"
            f"  Tests    {self.tests_passing:.0f}%\n"
            f"  Coverage {self.coverage:.0f}%\n"
            f"  Risk     {self.risk}"
        )


# ===================================================================
# Shared state
# ===================================================================

class CockpitState:
    """Mutable state rendered by the Mission Control TUI."""

    def __init__(self):
        self.messages: list[dict] = []
        self.agents: dict[str, str] = {}
        self.mission_name: str = ""
        self.mission_tasks: list[dict] = []
        self.timeline: deque[tuple[str, str]] = deque(maxlen=30)
        self.edited_files: list[str] = []
        self.knowledge_stats: dict[str, int] = {
            "Learned Today": 0, "Verified": 0, "Patterns": 0, "Solutions": 0,
        }
        self.active_files: list[str] = []
        self.streaming_text: str = ""
        self.model: str = ""
        self.tokens_used: int = 0
        self.context_percent: float = 0.0
        self.input_text: str = ""
        self.command_mode: bool = False
        self.status_message: str = "READY"
        self.error_message: str = ""
        self.confidence = ConfidenceEngine()
        self.pulse = EngineeringPulse()

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.streaming_text = ""

    def update_stream(self, text: str) -> None:
        self.streaming_text = text

    def add_timeline(self, label: str) -> None:
        stamp = time.strftime("%H:%M")
        self.timeline.append((stamp, label))

    def add_activity(self, msg: str) -> None:
        self.add_timeline(msg)

    def set_agent_status(self, name: str, status: str) -> None:
        self.agents[name] = status

    def set_task_status(self, label: str, status: str) -> None:
        for t in self.mission_tasks:
            if t["label"] == label:
                t["status"] = status
                return
        self.mission_tasks.append({"label": label, "status": status})


# ===================================================================
# Intelligence Orb
# ===================================================================

class IntelligenceOrb:
    def __init__(self):
        self._frame = 0
        self._state = "idle"
        self._label = ""

    def set_state(self, state: str, label: str = "") -> None:
        self._state = state
        self._label = label
        self._frame = 0

    def render(self) -> Text:
        self._frame += 1
        char = next(_ORB_FRAMES)
        color_map = {"thinking": _CYAN, "planning": _AMBER, "coding": _GREEN, "idle": _MUTED, "done": _GREEN}
        c = color_map.get(self._state, _MUTED)
        label = self._label or self._state.upper()
        return Text.assemble((char, f"bold {c}"), (" " + label, _MUTED))


_ORB = IntelligenceOrb()


# ===================================================================
# Renderers
# ===================================================================

_ICONS = {
    "pending": "○" if _U else "O",
    "running": "◐" if _U else "~",
    "done": "✓" if _U else "+",
    "failed": "✗" if _U else "x",
}
_AGENT_ICONS = {"running": "●", "idle": "○", "waiting": "◌", "error": "▲"}


def _render_header(state: CockpitState) -> Panel:
    left = Text.assemble(
        (f" {APP_NAME} ", f"bold white on {_ACCENT}"),
    )
    right = Text.assemble(
        (f" Built by {COMPANY} ", _MUTED),
        f" {state.model or 'not set'} ",
        (_ORB.render().plain, _MUTED),
    )
    return Panel(Group(left, right), style=_ACCENT)


def _render_mission_bar(state: CockpitState) -> Panel:
    name = state.mission_name or "No active mission"
    bar = Progress(
        BarColumn(bar_width=40, complete_style=_ACCENT, style=_BORDER),
        TextColumn("{task.percentage:>3.0f}%", style=_MUTED),
        console=console,
    )
    bar.add_task("ctx", total=100, completed=min(state.context_percent, 100))
    group = Group(
        Text.assemble((f" Mission: {name}", f"bold {_WHITE}")),
        bar,
    )
    return Panel(group, border_style=_BORDER, padding=(0, 1))


def _render_command_panel(state: CockpitState) -> Panel:
    prompt = state.input_text or ""
    if state.command_mode:
        prompt = f"[bold]/[/]{prompt}"
    lines = [
        f" [bold]>[/] {prompt}",
        "",
    ]
    return Panel("\n".join(lines), title="COMMAND", border_style=_BORDER)


def _render_engineering_feed(state: CockpitState) -> Panel:
    items = list(state.timeline)[-12:]
    lines = []
    for stamp, label in items:
        lines.append(f" [{_MUTED}]{stamp}[/] {label}")
    if state.streaming_text:
        lines.append(f" [{_CYAN}]>>>[/] {state.streaming_text[-300:]}")
    if not lines:
        lines.append(f" [{_MUTED}]Awaiting mission...[/]")
    return Panel("\n".join(lines), title="ENGINEERING FEED", border_style=_BORDER)


def _render_agents_panel(state: CockpitState) -> Panel:
    lines = [f"  {_ORB.render()}"]
    for name, status in sorted(state.agents.items()):
        icon = _AGENT_ICONS.get(status, "○")
        color = _GREEN if status == "running" else (_AMBER if status == "waiting" else _MUTED)
        lines.append(f"  [{color}]{icon}[/] {name}")
    if not state.agents:
        lines.append(f"  [{_MUTED}]No agents active[/]")
    return Panel("\n".join(lines), title="AGENTS", border_style=_BORDER)


def _render_active_files(state: CockpitState) -> Panel:
    files = state.active_files or state.edited_files[-6:]
    if not files:
        return Panel(f"  [{_MUTED}]No files changed[/]", title="ACTIVE FILES", border_style=_BORDER)
    return Panel("\n".join(f"  {f}" for f in files[-6:]), title="ACTIVE FILES", border_style=_BORDER)


def _render_knowledge(state: CockpitState) -> Panel:
    lines = []
    for k, v in state.knowledge_stats.items():
        lines.append(f"  {k}: [{_ACCENT}]{v}[/]")
    if not lines:
        lines.append(f"  [{_MUTED}]Collecting...[/]")
    return Panel("\n".join(lines), title="KNOWLEDGE", border_style=_BORDER)


def _render_system_health(state: CockpitState) -> Panel:
    return Panel(state.pulse.render(), title="SYSTEM HEALTH", border_style=_BORDER)


def _render_footer(state: CockpitState) -> Panel:
    left = Text.assemble(
        (_ORB.render().plain + " ", _MUTED),
        (f" {state.status_message} ", f"bold {_WHITE}"),
    )
    if state.error_message:
        left = Text.assemble(
            (state.error_message, f"bold {_RED}"),
        )
    hint = f"  Tab:explorer  /:command  Space:palette  Ctrl+Q:quit"
    return Panel(Group(left, Text(hint, style=_MUTED)), border_style=_BORDER)


# ===================================================================
# Layout builder
# ===================================================================

def build_layout(state: CockpitState) -> Layout:
    # Top section: header + mission bar
    top = Layout()
    top.split_column(
        Layout(name="header_bar", renderable=_render_header(state), size=3),
        Layout(name="mission_bar", renderable=_render_mission_bar(state), size=4),
    )

    # Middle row: COMMAND | ENGINEERING FEED | AGENTS
    cmd_panel = _render_command_panel(state)
    feed_panel = _render_engineering_feed(state)
    agents_panel = _render_agents_panel(state)

    middle = Layout()
    middle.split_row(
        Layout(name="cmd", renderable=cmd_panel, size=24),
        Layout(name="feed", renderable=feed_panel),
        Layout(name="agents", renderable=agents_panel, size=24),
    )

    # Bottom row: ACTIVE FILES | KNOWLEDGE | SYSTEM HEALTH
    files_panel = _render_active_files(state)
    knowledge_panel = _render_knowledge(state)
    health_panel = _render_system_health(state)

    bottom_row = Columns([files_panel, knowledge_panel, health_panel])

    # Body = middle + bottom_row
    body = Layout()
    body.split_column(
        Layout(name="middle", renderable=middle, ratio=3),
        Layout(name="bottom_info", renderable=bottom_row, ratio=1),
    )

    # Footer
    footer = Layout(name="footer_bar", renderable=_render_footer(state), size=4)

    # Full page
    layout = Layout()
    layout.split_column(
        Layout(name="top", renderable=top, size=7),
        Layout(name="body", renderable=body),
        Layout(name="footer", renderable=footer, size=4),
    )
    return layout


# ===================================================================
# Input thread
# ===================================================================

def _input_worker(input_queue: queue.Queue, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            line = input()
            input_queue.put(line)
        except (EOFError, KeyboardInterrupt):
            stop_event.set()
            break


# ===================================================================
# Main cockpit loop
# ===================================================================

def run_cockpit(
    model: str,
    on_message: Callable,
    initial_messages: list | None = None,
    refresh_rate: float = 0.15,
) -> None:
    if not _INFO["is_tty"]:
        console.print("[yellow]TUI requires a TTY. Falling back to simple mode.[/]")
        _simple_fallback(model, on_message, initial_messages)
        return

    state = CockpitState()
    state.model = model
    if initial_messages:
        state.messages = initial_messages

    input_queue: queue.Queue = queue.Queue()
    stop_event = threading.Event()

    input_thread = threading.Thread(
        target=_input_worker, args=(input_queue, stop_event), daemon=True
    )
    input_thread.start()

    try:
        with Live(build_layout(state), console=console, refresh_per_second=1 / refresh_rate, screen=True) as live:
            frame = 0
            while not stop_event.is_set():
                try:
                    line = input_queue.get_nowait()
                except queue.Empty:
                    frame += 1
                    if frame % 3 == 0:
                        live.update(build_layout(state))
                    time.sleep(refresh_rate / 3)
                    continue

                line = line.strip()
                if not line:
                    state.input_text = ""
                    live.update(build_layout(state))
                    continue

                state.input_text = line

                if line.lower() in ("exit", "quit", "q"):
                    state.status_message = "SHUTTING DOWN"
                    live.update(build_layout(state))
                    time.sleep(0.5)
                    break

                if line.startswith("/"):
                    if line.startswith("/exit") or line.startswith("/quit"):
                        break

                    state.command_mode = True
                    state.add_message("user", line)
                    state.status_message = f"COMMAND: {line}"
                    _ORB.set_state("planning", "Processing")
                    live.update(build_layout(state))

                    on_message(state, line)
                    state.command_mode = False
                    state.input_text = ""
                    state.status_message = "READY"
                    _ORB.set_state("idle")
                    live.update(build_layout(state))
                    continue

                state.add_message("user", line)
                state.status_message = "PROCESSING"
                _ORB.set_state("thinking", label="Thinking")
                state.input_text = ""
                state.add_timeline(f"Processing: {line[:60]}")
                live.update(build_layout(state))

                on_message(state, line)

                state.status_message = "READY"
                _ORB.set_state("idle")
                live.update(build_layout(state))

    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        console.print("[dim]Session ended.[/]")


def _simple_fallback(model: str, on_message: Callable, initial_messages: list | None = None) -> None:
    from rich.prompt import Prompt

    console.print(f"[dim]{APP_NAME} — Model: {model or 'not set'}[/]\n")

    messages = initial_messages or []
    state = CockpitState()
    state.model = model or ""
    state.messages = messages

    while True:
        raw = Prompt.ask("[bold]>[/]")
        if raw.lower() in ("exit", "quit", "q"):
            break
        if raw.startswith("/exit") or raw.startswith("/quit"):
            break
        state.add_message("user", raw)
        state.input_text = raw
        on_message(state, raw)
