from __future__ import annotations

import itertools
import queue
import threading
import time
from collections import deque
from typing import Any, Callable

from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from . import APP_NAME, C_ACCENT, C_DIM, VERSION
from .terminal import console, unicode_ok, detect
from .mission_engine import MissionState

_INFO = detect()
_U = unicode_ok(_INFO)

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

_STATE_COLORS = {
    MissionState.MISSION_CREATED: _MUTED,
    MissionState.DISCOVERY: _CYAN,
    MissionState.CAPABILITY_DISCOVERY: _CYAN,
    MissionState.REPOSITORY_ANALYSIS: _CYAN,
    MissionState.ARCHITECTURE: _AMBER,
    MissionState.PLANNING: _AMBER,
    MissionState.WAITING_APPROVAL: _AMBER,
    MissionState.EXECUTION: _GREEN,
    MissionState.VALIDATION: _GREEN,
    MissionState.SECURITY_REVIEW: _CYAN,
    MissionState.DOCUMENTATION: _MUTED,
    MissionState.REFLECTION: _MUTED,
    MissionState.MISSION_COMPLETE: _GREEN,
    MissionState.FAILED: _RED,
    MissionState.RECOVERING: _AMBER,
    MissionState.CANCELLED: _RED,
}


# ---------------------------------------------------------------------------
# Confidence Engine (v2.0)
# ---------------------------------------------------------------------------

class ConfidenceEngine:
    def __init__(self):
        self._scores: dict[str, float] = {
            "Architecture": 0.0,
            "Verification": 0.0,
            "Tests": 0.0,
            "Security": 0.0,
            "Documentation": 0.0,
            "Context Quality": 0.0,
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


# ---------------------------------------------------------------------------
# Engineering Pulse
# ---------------------------------------------------------------------------

class EngineeringPulse:
    def __init__(self):
        self.health: float = 1.0
        self.risk: str = "Low"
        self.velocity: str = "High"
        self.quality: str = "Excellent"
        self.build: str = "PASS"
        self.tests_passing: float = 100.0
        self.coverage: float = 0.0
        self.repository_health: float = 1.0
        self.mission_progress: float = 0.0

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


# ---------------------------------------------------------------------------
# Cockpit State (v2.0)
# ---------------------------------------------------------------------------

class CockpitState:
    def __init__(self):
        self.messages: list[dict] = []
        self.agents: dict[str, str] = {}
        self.mission_name: str = ""
        self.mission_state: str = ""
        self.mission_tasks: list[dict] = []
        self.timeline: deque[tuple[str, str]] = deque(maxlen=30)
        self.diagnostics: deque[tuple[str, str]] = deque(maxlen=20)
        self.show_diagnostics: bool = False
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
        self.mission_eta: str = ""
        self.capabilities_count: int = 0
        self.indexed_files: int = 0

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

    def add_diagnostic(self, label: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.diagnostics.append((stamp, label))

    def set_agent_status(self, name: str, status: str) -> None:
        self.agents[name] = status

    def set_task_status(self, label: str, status: str) -> None:
        for t in self.mission_tasks:
            if t["label"] == label:
                t["status"] = status
                return
        self.mission_tasks.append({"label": label, "status": status})


# ---------------------------------------------------------------------------
# Intelligence Orb
# ---------------------------------------------------------------------------

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

_ICONS = {
    "pending": "○" if _U else "O",
    "running": "◐" if _U else "~",
    "done": "✓" if _U else "+",
    "failed": "✗" if _U else "x",
}
_AGENT_ICONS = {"running": "●", "idle": "○", "waiting": "◌", "error": "▲"}


# ---------------------------------------------------------------------------
# Renderers (v2.0 Mission Control)
# ---------------------------------------------------------------------------

def _render_header(state: CockpitState) -> Panel:
    title = Text.assemble(
        (f" {APP_NAME} ", f"bold white on {_ACCENT}"),
        (f" {state.model or 'not set'} ", _MUTED),
    )
    orb = _ORB.render()
    status = state.status_message or "READY"
    health = f"H:{state.pulse.health*100:.0f}%" if state.pulse else ""
    return Panel(
        Group(title, Text(f"{orb} {status}  {health}  {state.mission_state or ''}", style=_MUTED)),
        style=_ACCENT,
    )


def _render_feed(state: CockpitState) -> Panel:
    lines = []
    for stamp, label in list(state.timeline)[-20:]:
        color = _RED if ("error" in label.lower() or "fail" in label.lower()) else (_GREEN if "complete" in label.lower() or "done" in label.lower() else _MUTED)
        lines.append(f"  [{color}]{stamp}[/] {label}")
    if not lines:
        lines.append(f"  [{_MUTED}]Awaiting activity...[/]")
    if state.streaming_text:
        lines.append(f"  [{_CYAN}]>>>[/] {state.streaming_text[-300:]}")
    if state.input_text:
        lines.append(f"  [bold]>[/] {state.input_text[:200]}")
    return Panel("\n".join(lines), title="FEED", border_style=_BORDER)


def _render_stats(state: CockpitState) -> Panel:
    lines = []
    if state.mission_name:
        lines.append(f"  Mission: [{_ACCENT}]{state.mission_name}[/]")
    if state.agents:
        running = sum(1 for s in state.agents.values() if s == "running")
        lines.append(f"  Agents: {len(state.agents)} ({running} running)")
    lines.append(f"  T: {state.tokens_used:,}  Ctx: {state.context_percent:.0f}%")
    lines.append(f"  Conﬁdence: {state.confidence.average()*100:.0f}%")
    files = state.active_files or state.edited_files[-4:]
    if files:
        lines.append(f"  Files: {len(files)} changed")
    if not lines:
        lines.append(f"  [{_MUTED}]No stats[/]")
    return Panel("\n".join(lines), title="STATUS", border_style=_BORDER)


def _render_footer(state: CockpitState) -> Panel:
    msg = state.error_message or state.status_message or "READY"
    color = _RED if state.error_message else _WHITE
    hint = "  /cmd  q:quit"
    return Panel(
        Text.assemble((msg, f"bold {color}"), (hint, _MUTED)),
        border_style=_BORDER,
    )


# ---------------------------------------------------------------------------
# Layout builder (v2.0) — minimal 4-panel layout
# ---------------------------------------------------------------------------

def build_layout(state: CockpitState) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", renderable=_render_header(state), size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", renderable=_render_footer(state), size=3),
    )
    body = layout["body"]
    body.split_row(
        Layout(name="feed", renderable=_render_feed(state), ratio=3),
        Layout(name="stats", renderable=_render_stats(state), size=28),
    )
    return layout


# ---------------------------------------------------------------------------
# Input thread
# ---------------------------------------------------------------------------

def _input_worker(input_queue: queue.Queue, stop_event: threading.Event) -> None:
    buffer: list[str] = []
    while not stop_event.is_set():
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            if buffer:
                input_queue.put(("\n".join(buffer), True))
            stop_event.set()
            break

        stripped = line.strip()

        # Empty line with buffer → flush as a single batch
        if not stripped and buffer:
            input_queue.put(("\n".join(buffer), False))
            buffer.clear()
            continue

        # Empty line without buffer → just redraw signal
        if not stripped and not buffer:
            input_queue.put(("", False))
            continue

        # Slash command → flush buffer first if non-empty, then send command
        if stripped.startswith("/"):
            if buffer:
                input_queue.put(("\n".join(buffer), False))
                buffer.clear()
            input_queue.put((line, False))
            continue

        # Exit/quit → flush buffer then exit
        if stripped.lower() in ("exit", "quit", "q"):
            if buffer:
                input_queue.put(("\n".join(buffer), False))
                buffer.clear()
            input_queue.put((line, False))
            continue

        # Accumulate into buffer
        buffer.append(line)


# ---------------------------------------------------------------------------
# Main cockpit loop (v2.0)
# ---------------------------------------------------------------------------

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
                    raw = input_queue.get_nowait()
                    if isinstance(raw, tuple):
                        line, _is_batch = raw
                    else:
                        line, _is_batch = raw, False
                except queue.Empty:
                    frame += 1
                    if frame % 3 == 0:
                        live.update(build_layout(state))
                    time.sleep(refresh_rate / 3)
                    continue

                stripped = line.strip()

                # Empty redraw signal
                if not stripped:
                    state.input_text = ""
                    live.update(build_layout(state))
                    continue

                state.input_text = line

                # Show multi-line indicator
                if "\n" in line:
                    line_count = line.count("\n") + 1
                    state.add_timeline(f"Pasted {line_count} lines")

                if stripped.lower() in ("exit", "quit", "q"):
                    state.status_message = "SHUTTING DOWN"
                    live.update(build_layout(state))
                    time.sleep(0.5)
                    break

                if stripped.startswith("/"):
                    cmd = stripped.split()[0].lower()
                    if cmd in ("/exit", "/quit"):
                        break

                    state.command_mode = True
                    state.add_message("user", line)
                    state.status_message = f"COMMAND: {line.split("\n")[0][:60]}"
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

    console.print(f"[dim]{APP_NAME} v{VERSION} — Model: {model or 'not set'}[/]\n")
    console.print("[dim](Press Enter on an empty line to send multi-line input)[/]\n")

    messages = initial_messages or []
    state = CockpitState()
    state.model = model or ""
    state.messages = messages
    buffer: list[str] = []

    while True:
        raw = Prompt.ask("[bold]>[/]")
        stripped = raw.strip()

        # Empty line with buffer → flush as batch
        if not stripped and buffer:
            full_text = "\n".join(buffer)
            console.print(f"[dim]Sending {len(buffer)} lines[/]")
            buffer.clear()
            if full_text.lower() in ("exit", "quit", "q"):
                break
            if full_text.startswith("/exit") or full_text.startswith("/quit"):
                break
            state.add_message("user", full_text)
            state.input_text = full_text
            on_message(state, full_text)
            continue

        # Empty line without buffer → just redraw prompt silently
        if not stripped and not buffer:
            continue

        # Slash command → flush buffer first if needed, then process immediately
        if stripped.startswith("/"):
            if buffer:
                console.print(f"[dim]Flushing {len(buffer)} lines before command[/]")
                full_text = "\n".join(buffer)
                buffer.clear()
                state.add_message("user", full_text)
                state.input_text = full_text
                on_message(state, full_text)
            if stripped in ("/exit", "/quit"):
                break
            state.add_message("user", raw)
            state.input_text = raw
            on_message(state, raw)
            continue

        # Exit/quit
        if stripped.lower() in ("exit", "quit", "q"):
            if buffer:
                full_text = "\n".join(buffer)
                console.print(f"[dim]Sending {len(buffer)} lines before exit[/]")
                buffer.clear()
                state.add_message("user", full_text)
                state.input_text = full_text
                on_message(state, full_text)
            break

        # Accumulate into buffer (multi-line paste)
        buffer.append(raw)
        console.print(f"[dim]Buffered: {len(buffer)} line(s) — send with empty Enter[/]")
