from __future__ import annotations

import itertools
import queue
import sys
import threading
import time
from collections import deque
from typing import Any, Callable

from rich.columns import Columns
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.text import Text

from . import APP_NAME, COMPANY, C_ACCENT, C_DIM, VERSION
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
# Confidence Engine
# ---------------------------------------------------------------------------

class ConfidenceEngine:
    def __init__(self):
        self._scores: dict[str, float] = {
            "Architecture": 0.0, "Verification": 0.0, "Tests": 0.0,
            "Security": 0.0, "Documentation": 0.0, "Context Quality": 0.0,
        }

    def set(self, domain: str, score: float) -> None:
        self._scores[domain] = max(0.0, min(1.0, score))

    def get(self, domain: str) -> float:
        return self._scores.get(domain, 0.0)

    def average(self) -> float:
        vals = [v for v in self._scores.values() if v > 0]
        return sum(vals) / len(vals) if vals else 0.0

    def reset(self) -> None:
        for k in self._scores:
            self._scores[k] = 0.0

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
        self.health: float = 0.0
        self.risk: str = "Unknown"
        self.velocity: str = "Unknown"
        self.quality: str = "Unknown"
        self.build: str = "UNKNOWN"
        self.tests_passing: float = 0.0
        self.coverage: float = 0.0
        self.repository_health: float = 0.0
        self.mission_progress: float = 0.0
        self._error_count: int = 0
        self._success_count: int = 0

    def record_success(self) -> None:
        self._success_count += 1
        self._recalculate()

    def record_error(self) -> None:
        self._error_count += 1
        self._recalculate()

    def update_health(self, score: float) -> None:
        self.health = max(0.0, min(1.0, score))
        self._recalculate()

    def update_from_verification(self, results: dict) -> None:
        if not results:
            return
        passed = sum(1 for v in results.values() if v is True)
        total = len(results)
        self.tests_passing = (passed / total * 100) if total else 0.0
        self.build = "PASS" if passed == total else "FAIL"
        self._recalculate()

    def update_mission_progress(self, phase: str, phases_total: int = 10) -> None:
        phase_order = [
            "MISSION_CREATED", "DISCOVERY", "CAPABILITY_DISCOVERY",
            "REPOSITORY_ANALYSIS", "ARCHITECTURE", "PLANNING",
            "WAITING_APPROVAL", "EXECUTION", "VALIDATION",
            "SECURITY_REVIEW", "DOCUMENTATION", "REFLECTION", "MISSION_COMPLETE",
        ]
        try:
            idx = phase_order.index(phase) + 1
        except ValueError:
            idx = 0
        self.mission_progress = (idx / phases_total * 100) if phases_total else 0.0

    def _recalculate(self) -> None:
        total = self._success_count + self._error_count
        if total == 0:
            self.health = 0.0
            self.risk = "Unknown"
            self.velocity = "Unknown"
            self.quality = "Unknown"
            return
        success_rate = self._success_count / total
        self.health = success_rate
        self.risk = "Low" if success_rate > 0.9 else ("Medium" if success_rate > 0.7 else "High")
        self.velocity = "High" if success_rate > 0.85 else ("Normal" if success_rate > 0.6 else "Low")
        self.quality = "Excellent" if success_rate > 0.9 else ("Good" if success_rate > 0.7 else "Degraded")

    def render(self) -> str:
        hp = self.health * 100
        bar_len = 12
        filled = int(hp / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        color = _GREEN if hp >= 80 else (_AMBER if hp >= 50 else _RED)
        build_color = _GREEN if self.build == "PASS" else (_RED if self.build == "FAIL" else _AMBER)
        return (f"  Health [{color}]{bar}[/] {hp:.0f}%\n"
                f"  Build  [{build_color}]{self.build}[/]\n"
                f"  Tests  {self.tests_passing:.0f}%\n"
                f"  Risk   {self.risk}")


# ---------------------------------------------------------------------------
# Cockpit State
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
        self.memory_working: int = 0
        self.memory_experiences: int = 0
        self.memory_kg_nodes: int = 0
        self.session_id: str = ""

        # Worker pool state
        self.workers: dict[str, str] = {}  # worker_name -> task_id
        self.parallel_tasks: list[dict] = []
        self.parallel_mode: bool = False
        self.max_workers: int = 4

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.streaming_text = ""

    def update_stream(self, text: str) -> None:
        self.streaming_text = text

    def add_timeline(self, label: str) -> None:
        self.timeline.append((time.strftime("%H:%M"), label))

    def add_activity(self, msg: str) -> None:
        self.add_timeline(msg)

    def add_diagnostic(self, label: str) -> None:
        self.diagnostics.append((time.strftime("%H:%M:%S"), label))

    def set_agent_status(self, name: str, status: str) -> None:
        self.agents[name] = status

    def update_from_verification(self, results: dict) -> None:
        if not results:
            return
        passed = sum(1 for v in results.values() if v is True)
        total = len(results)
        ratio = passed / total if total else 0
        self.confidence.set("Verification", ratio)
        self.confidence.set("Tests", ratio)
        self.pulse.update_from_verification(results)

    def update_from_mission(self, phase: str, error: str = "") -> None:
        self.mission_state = phase
        self.pulse.update_mission_progress(phase)
        self.context_percent = self.pulse.mission_progress
        if error:
            self.pulse.record_error()
            self.confidence.set("Security", max(0.0, self.confidence.get("Security") - 0.2))
        else:
            self.pulse.record_success()

    def set_task_status(self, label: str, status: str) -> None:
        for t in self.mission_tasks:
            if t["label"] == label:
                t["status"] = status
                return
        self.mission_tasks.append({"label": label, "status": status})

    def update_workers(self, worker_states: dict[str, str]) -> None:
        self.workers = worker_states

    def update_parallel_tasks(self, tasks: list[dict]) -> None:
        self.parallel_tasks = tasks

    def set_parallel_mode(self, mode: bool, max_workers: int = 4) -> None:
        self.parallel_mode = mode
        self.max_workers = max_workers


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
        cmap = {"thinking": _CYAN, "planning": _AMBER, "coding": _GREEN, "idle": _MUTED, "done": _GREEN}
        c = cmap.get(self._state, _MUTED)
        return Text.assemble((char, f"bold {c}"), (" " + (self._label or self._state.upper()), _MUTED))


_ORB = IntelligenceOrb()

_AGENT_ICONS = {"running": "●", "idle": "○", "waiting": "◌", "error": "▲"}


# ---------------------------------------------------------------------------
# Character-by-character input
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    import msvcrt as _msvcrt
    def _read_key() -> str:
        ch = _msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            _msvcrt.getch()
            return ""
        try:
            return ch.decode("utf-8")
        except UnicodeDecodeError:
            return ch.decode("cp1252", errors="replace")
else:
    import tty as _tty
    import termios as _termios
    def _read_key() -> str:
        fd = sys.stdin.fileno()
        old = _termios.tcgetattr(fd)
        try:
            _tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            _termios.tcsetattr(fd, _termios.TCSADRAIN, old)
        return ch


_COMMANDS = [
    "/workers", "/mission", "/plan", "/build", "/help", "/exit", "/quit",
    "/change model", "/models", "/init", "/save", "/skills", "/brain",
    "/capabilities", "/search", "/verify", "/recovery", "/queue",
    "/workspace", "/checkpoints", "/undo", "/redo", "/plan",
]


def _tab_complete(buf: list[str]) -> list[str]:
    current = "".join(buf)
    if not current.startswith("/"):
        return []
    lower = current.lower()
    return [cmd for cmd in _COMMANDS if cmd.lower().startswith(lower)]


def _input_worker(input_queue: queue.Queue, state: CockpitState, stop_event: threading.Event) -> None:
    buf: list[str] = []
    while not stop_event.is_set():
        ch = _read_key()
        if not ch:
            continue
        if ch in ("\r", "\n"):
            line = "".join(buf)
            buf.clear()
            stripped = line.strip()
            if stripped.startswith("/"):
                input_queue.put((line, False))
            elif stripped.lower() in ("exit", "quit", "q", ""):
                input_queue.put((line, True if stripped else False))
            else:
                input_queue.put((line, False))
            state.input_text = ""
            continue
        if ch == "\t":
            matches = _tab_complete(buf)
            if len(matches) == 1:
                completion = matches[0][len("".join(buf)):]
                buf.extend(list(completion + " "))
                state.input_text = "".join(buf)
            elif len(matches) > 1:
                state.input_text = "".join(buf) + "  "
                state.add_activity(f"Matches: {', '.join(matches[:6])}")
            continue
        if ch in ("\x7f", "\b"):
            if buf:
                buf.pop()
            state.input_text = "".join(buf)
            continue
        if ch in ("\x03", "\x04"):
            buf.clear()
            state.input_text = ""
            input_queue.put(("", False))
            continue
        buf.append(ch)
        state.input_text = "".join(buf)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _render_header(state: CockpitState) -> Panel:
    left = Text.assemble(
        (f" {APP_NAME} ", f"bold white on {_ACCENT}"),
        (f" v{VERSION} ", _MUTED),
    )
    orb = _ORB.render()
    model_text = state.model or "not set"
    right = Text.assemble(
        (f" {model_text} ", _WHITE),
        (" │ ", _BORDER),
        (orb.plain, _MUTED),
    )
    return Panel(Group(left, right), style=_ACCENT, padding=(0, 0))


def _render_mission_bar(state: CockpitState) -> Panel:
    name = state.mission_name or "No active mission"
    bar = Progress(
        BarColumn(bar_width=24, complete_style=_ACCENT, style=_BORDER),
        TextColumn("{task.percentage:>3.0f}%", style=_MUTED),
        console=console,
    )
    bar.add_task("ctx", total=100, completed=min(state.context_percent, 100))
    sd = state.mission_state or "STANDBY"
    sc = _STATE_COLORS.get(MissionState(state.mission_state), _WHITE) if state.mission_state else _MUTED
    left = Text.assemble(
        (f" {name}", f"bold {_WHITE}"),
    )
    right = Text.assemble(
        (f"[{sd}]", f"bold {sc}"),
    )
    return Panel(
        Group(Text.assemble(left, right), bar),
        border_style=_BORDER, padding=(0, 1),
    )


def _render_input(state: CockpitState) -> Panel:
    prompt = state.input_text or ""
    if state.command_mode:
        prompt = f"[bold bright_blue]/[/]{prompt}"
    lines = []
    lines.append(f" [bold bright_blue]>[/] {prompt}")
    lines.append("")
    return Panel("\n".join(lines), title="INPUT", border_style=_BORDER)


def _render_feed(state: CockpitState) -> Panel:
    items = list(state.timeline)[-12:]
    lines = []
    for stamp, label in items:
        color = _MUTED
        if "error" in label.lower() or "fail" in label.lower():
            color = _RED
        elif "complete" in label.lower() or "done" in label.lower() or "passed" in label.lower():
            color = _GREEN
        elif "running" in label.lower() or "processing" in label.lower():
            color = _CYAN
        elif "phase:" in label.lower() or "discovery" in label.lower() or "execution" in label.lower():
            color = _AMBER
        lines.append(f" [{_MUTED}]{stamp}[/] [{color}]{label}[/]")
    if state.show_diagnostics and state.diagnostics:
        lines.append(f" [{_RED}]--- ERRORS ---[/]")
        for stamp, label in list(state.diagnostics)[-4:]:
            lines.append(f" [{_RED}]{stamp}[/] {label}")
    if state.streaming_text:
        lines.append(f" [{_CYAN}]▸[/] {state.streaming_text[-280:]}")
    if not lines:
        lines.append(f" [{_MUTED}]Awaiting activity...[/]")
    return Panel("\n".join(lines), title="FEED", border_style=_BORDER)


def _render_agents(state: CockpitState) -> Panel:
    lines = []
    if state.parallel_mode:
        # Show workers
        worker_count = state.max_workers
        active_workers = len(state.workers)
        lines.append(f"  [{_ACCENT}]Parallel Mode[/] ({active_workers}/{worker_count} active)")
        lines.append("")
        if state.workers:
            for worker_name, task_id in sorted(state.workers.items()):
                task_desc = ""
                for t in state.parallel_tasks:
                    if t.get("id") == task_id:
                        task_desc = t.get("description", "")[:20]
                        break
                lines.append(f"  [{_GREEN}]▸[/] {worker_name}")
                if task_desc:
                    lines.append(f"    [{_MUTED}]{task_desc}[/]")
        else:
            lines.append(f"  [{_MUTED}]All workers idle[/]")
        # Show task summary
        if state.parallel_tasks:
            lines.append("")
            done = sum(1 for t in state.parallel_tasks if t.get("status") in ("completed", "failed", "skipped"))
            total = len(state.parallel_tasks)
            lines.append(f"  [{_WHITE}]{done}/{total}[/] tasks done")
    else:
        # Show agents (sequential mode)
        if state.agents:
            for name, status in sorted(state.agents.items()):
                icon = _AGENT_ICONS.get(status, "○")
                if status == "running":
                    color = _GREEN
                    tag = "RUN"
                elif status == "waiting":
                    color = _AMBER
                    tag = "WAIT"
                elif status == "error":
                    color = _RED
                    tag = "ERR"
                else:
                    color = _MUTED
                    tag = "IDLE"
                lines.append(f" [{color}]{icon}[/] {name} [{_MUTED}]{tag}[/]")
        else:
            lines.append(f" [{_MUTED}]No agents active[/]")
    return Panel("\n".join(lines), title="AGENTS" if not state.parallel_mode else "WORKERS", border_style=_BORDER)


def _render_health(state: CockpitState) -> Panel:
    lines = []
    h = state.pulse.health
    h_color = _GREEN if h > 70 else (_AMBER if h > 40 else _RED)
    lines.append(f"  [{h_color}]{h:.0f}%[/] Overall")
    t = state.pulse.test_pass_rate
    t_color = _GREEN if t > 70 else (_AMBER if t > 40 else _RED)
    lines.append(f"  [{t_color}]{t:.0f}%[/] Tests")
    b = state.pulse.build_success_rate
    b_color = _GREEN if b > 70 else (_AMBER if b > 40 else _RED)
    lines.append(f"  [{b_color}]{b:.0f}%[/] Build")
    r = state.pulse.risk_score
    r_color = _GREEN if r < 30 else (_AMBER if r < 60 else _RED)
    lines.append(f"  [{r_color}]{r:.0f}%[/] Risk")
    return Panel("\n".join(lines), title="HEALTH", border_style=_BORDER)


def _render_stats(state: CockpitState) -> Panel:
    lines = []
    lines.append(f"  Tokens:     [{_ACCENT}]{state.tokens_used:,}[/]")
    ctx = state.context_percent
    ctx_color = _GREEN if ctx > 70 else (_AMBER if ctx > 40 else _RED)
    lines.append(f"  Context:    [{ctx_color}]{ctx:.0f}%[/]")
    avg = state.confidence.average() * 100
    c_color = _GREEN if avg > 70 else (_AMBER if avg > 40 else _RED)
    lines.append(f"  Confidence: [{c_color}]{avg:.0f}%[/]")
    if state.active_files or state.edited_files:
        files = state.active_files or state.edited_files[-6:]
        lines.append(f"  Files:      [{_WHITE}]{len(files)}[/]")
    if state.knowledge_stats:
        for k, v in list(state.knowledge_stats.items())[:3]:
            lines.append(f"  {k}: [{_ACCENT}]{v}[/]")
    mem_parts = []
    if state.memory_working > 0:
        mem_parts.append(f"{state.memory_working} work")
    if state.memory_experiences > 0:
        mem_parts.append(f"{state.memory_experiences} exp")
    if state.memory_kg_nodes > 0:
        mem_parts.append(f"{state.memory_kg_nodes} kg")
    if mem_parts:
        lines.append(f"  Memory:     [{_ACCENT}]{' · '.join(mem_parts)}[/]")
    if state.session_id:
        lines.append(f"  Session:    [{_MUTED}]{state.session_id}[/]")
    return Panel("\n".join(lines), title="STATS", border_style=_BORDER)


def _render_footer(state: CockpitState) -> Panel:
    left = Text.assemble(
        (_ORB.render().plain + " ", _MUTED),
        (f" {state.status_message} ", _WHITE),
    )
    if state.error_message:
        left = Text.assemble((state.error_message, f"bold {_RED}"))
    right = Text.assemble(
        (" /menu", _MUTED),
        (" · ", _BORDER),
        ("q", _AMBER),
        (":quit ", _MUTED),
    )
    return Panel(Group(left, right), border_style=_BORDER)


# ---------------------------------------------------------------------------
# Layout builder
# ---------------------------------------------------------------------------

def build_layout(state: CockpitState) -> Layout:
    top = Layout()
    top.split_column(
        Layout(renderable=_render_header(state), size=3),
        Layout(renderable=_render_mission_bar(state), size=4),
    )

    middle = Layout()
    middle.split_row(
        Layout(renderable=_render_input(state), size=24),
        Layout(renderable=_render_feed(state)),
        Layout(renderable=_render_agents(state), size=22),
    )

    bottom = Columns([_render_health(state), _render_stats(state)], padding=1)

    body = Layout()
    body.split_column(
        Layout(renderable=middle, ratio=3),
        Layout(renderable=bottom, ratio=1),
    )

    layout = Layout()
    layout.split_column(
        Layout(renderable=top, size=7),
        Layout(renderable=body),
        Layout(renderable=_render_footer(state), size=3),
    )
    return layout


# ---------------------------------------------------------------------------
# Main cockpit loop
# ---------------------------------------------------------------------------

def run_cockpit(
    model: str,
    on_message: Callable,
    initial_messages: list | None = None,
    refresh_rate: float = 0.1,
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
        target=_input_worker, args=(input_queue, state, stop_event), daemon=True
    )
    input_thread.start()

    try:
        with Live(build_layout(state), console=console, refresh_per_second=1 / refresh_rate, screen=True) as live:
            frame = 0
            while not stop_event.is_set():
                try:
                    raw = input_queue.get_nowait()
                    line, is_exit = raw if isinstance(raw, tuple) else (raw, False)
                except queue.Empty:
                    if frame % 3 == 0:
                        live.update(build_layout(state))
                    frame += 1
                    time.sleep(refresh_rate / 3)
                    continue

                stripped = line.strip()

                if not stripped:
                    state.input_text = ""
                    live.update(build_layout(state))
                    continue

                state.input_text = line

                if is_exit or stripped.lower() in ("exit", "quit", "q"):
                    state.status_message = "SHUTTING DOWN"
                    live.update(build_layout(state))
                    time.sleep(0.3)
                    break

                if stripped.startswith("/"):
                    cmd = stripped.split()[0].lower()
                    if cmd in ("/exit", "/quit"):
                        break
                    state.command_mode = True
                    state.add_message("user", line)
                    state.status_message = f"CMD: {line.split(chr(10))[0][:60]}"
                    _ORB.set_state("planning", "Processing")
                    live.update(build_layout(state))
                    try:
                        on_message(state, line)
                    except Exception as e:
                        state.add_timeline(f"Cmd error: {type(e).__name__}")
                        state.error_message = f"{type(e).__name__}: {str(e)[:100]}"
                        state.add_diagnostic(f"CMD ERROR: {e}")
                    state.command_mode = False
                    state.status_message = "READY"
                    _ORB.set_state("idle")
                    state.input_text = ""
                    live.update(build_layout(state))
                    continue

                state.add_message("user", line)
                state.status_message = "PROCESSING"
                _ORB.set_state("thinking", label="Thinking")
                state.input_text = ""
                state.add_timeline(f"Processing: {line[:60]}")
                live.update(build_layout(state))

                try:
                    on_message(state, line)
                except Exception as e:
                    state.add_timeline(f"Error: {type(e).__name__}")
                    state.error_message = f"{type(e).__name__}: {str(e)[:100]}"
                    state.add_diagnostic(f"UNCAUGHT: {e}")

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
        if not stripped and not buffer:
            continue
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
        if stripped.lower() in ("exit", "quit", "q"):
            if buffer:
                full_text = "\n".join(buffer)
                console.print(f"[dim]Sending {len(buffer)} lines before exit[/]")
                buffer.clear()
                state.add_message("user", full_text)
                state.input_text = full_text
                on_message(state, full_text)
            break
        buffer.append(raw)
        console.print(f"[dim]Buffered: {len(buffer)} line(s) — send with empty Enter[/]")
