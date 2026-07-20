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
from rich.markdown import Markdown as RichMarkdown
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

_BORDER_HEADER = "bright_blue"
_BORDER_MISSION = "bright_cyan"
_BORDER_INPUT = "bright_green"
_BORDER_FEED = "bright_yellow"
_BORDER_AGENTS = "bright_magenta"
_BORDER_HEALTH = "bright_red"
_BORDER_STATS = "bright_white"
_BORDER_FOOTER = "bright_black"
_BORDER_ACCENT = "bright_blue"

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
        self.tool_calls: deque[dict] = deque(maxlen=50)
        self.show_diagnostics: bool = False
        self.edited_files: list[str] = []
        self.knowledge_stats: dict[str, int] = {
            "Learned Today": 0, "Verified": 0, "Patterns": 0, "Solutions": 0,
        }
        self.active_files: list[str] = []
        self.streaming_text: str = ""
        self.model: str = ""
        self.tokens_used: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.context_percent: float = 0.0
        self.context_max: int = 128000
        self.vector_chunks: int = 0
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
        self.chat_scroll_offset: int = 0

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

    def log_tool_call(self, tool: str, args: dict, result: str = "", duration_ms: float = 0) -> None:
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "tool": tool,
            "args": args,
            "result": result[:200] if result else "",
            "duration_ms": duration_ms,
            "success": not result.startswith("ERROR") if result else True,
        }
        self.tool_calls.append(entry)
        arg_summary = str(args)[:80] if args else ""
        status = "✓" if entry["success"] else "✗"
        ms = f" {duration_ms:.0f}ms" if duration_ms else ""
        self.add_timeline(f"{status} {tool}({arg_summary}){ms}")

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
    "/help", "/exit", "/quit", "/q",
    "/plan", "/undo", "/redo",
    "/change model", "/models", "/save",
    "/init", "/refresh", "/context", "/brain",
    "/search", "/capabilities", "/skills",
    "/mission", "/workers", "/queue", "/verify", "/recovery",
    "/sessions", "/resume", "/history",
    "/tree", "/find", "/filestats", "/gitstatus",
    "/mv", "/cp", "/rm", "/mkdir",
    "/workspace", "/checkpoints",
    "/lats", "/subagents", "/selfmodify", "/iceberg",
    "/vectors", "/episodes", "/semantic", "/sensory", "/memory", "/guardrails",
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
    return Panel(Group(left, right), style=_BORDER_HEADER, padding=(0, 0))


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
        border_style=_BORDER_MISSION, padding=(0, 1),
    )


def _render_input(state: CockpitState) -> Panel:
    lines = []
    if state.command_mode:
        lines.append(f" [bold {_AMBER}]CMD[/] [bold bright_blue]/[/]{state.input_text}")
        lines.append(f" [dim]Tab to complete  Enter to run[/]")
    elif state.input_text:
        lines.append(f" [bold bright_blue]>[/] {state.input_text}")
        lines.append("")
    else:
        lines.append(f" [bold bright_blue]>[/] ")
        lines.append(f" [dim]Type a message or /help  Tab to autocomplete[/]")
    title = "[bold]INPUT[/]"
    if state.command_mode:
        title += "  [bold bright_blue]/ CMD[/]"
    elif state.status_message == "PROCESSING":
        title += "  [bold bright_yellow]...[/]"
    return Panel(
        "\n".join(lines),
        title=title,
        border_style=_BORDER_INPUT,
    )


def _render_feed(state: CockpitState) -> Panel:
    items = list(state.timeline)[-10:]
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

    if state.tool_calls:
        tc_items = list(state.tool_calls)[-8:]
        if tc_items:
            lines.append(f" [{_AMBER}]--- TOOL CALLS ---[/]")
            for tc in tc_items:
                tool = tc.get("tool", "?")
                success = tc.get("success", True)
                dur = tc.get("duration_ms", 0)
                icon = "\u2713" if success else "\u2717"
                c = _GREEN if success else _RED
                dur_str = f" {dur:.0f}ms" if dur else ""
                lines.append(f" [{c}]{icon}[/] [{_CYAN}]{tool}[/][{_MUTED}]{dur_str}[/]")

    if state.show_diagnostics and state.diagnostics:
        lines.append(f" [{_RED}]--- ERRORS ---[/]")
        for stamp, label in list(state.diagnostics)[-4:]:
            lines.append(f" [{_RED}]{stamp}[/] {label}")
    if state.streaming_text:
        lines.append(f" [{_CYAN}]\u25b8[/] {state.streaming_text[-280:]}")
    if not lines:
        lines.append(f" [{_MUTED}]Awaiting activity...[/]")
    return Panel("\n".join(lines), title="FEED", border_style=_BORDER_FEED)


def _render_agents(state: CockpitState) -> Panel:
    lines = []
    if state.parallel_mode:
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
                lines.append(f"  [{_GREEN}]\u25b6[/] {worker_name}")
                if task_desc:
                    lines.append(f"    [{_MUTED}]{task_desc}[/]")
        else:
            lines.append(f"  [{_MUTED}]All workers idle[/]")
        if state.parallel_tasks:
            lines.append("")
            done = sum(1 for t in state.parallel_tasks if t.get("status") in ("completed", "failed", "skipped"))
            total = len(state.parallel_tasks)
            pct = (done / total * 100) if total else 0
            lines.append(f"  [{_WHITE}]{done}/{total}[/] tasks done [{_GREEN}]{pct:.0f}%[/]")
    else:
        if state.agents:
            running = sum(1 for s in state.agents.values() if s == "running")
            total = len(state.agents)
            lines.append(f"  [{_WHITE}]{running}/{total}[/] active")
            lines.append("")
            for name, status in sorted(state.agents.items()):
                icon = _AGENT_ICONS.get(status, "\u25cb")
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
    return Panel("\n".join(lines), title="AGENTS" if not state.parallel_mode else "WORKERS", border_style=_BORDER_AGENTS)


def _render_health(state: CockpitState) -> Panel:
    lines = []
    h = state.pulse.health * 100
    h_color = _GREEN if h > 70 else (_AMBER if h > 40 else _RED)
    lines.append(f"  [{h_color}]{h:.0f}%[/] Overall")
    t = state.pulse.tests_passing
    t_color = _GREEN if t > 70 else (_AMBER if t > 40 else _RED)
    lines.append(f"  [{t_color}]{t:.0f}%[/] Tests")
    b = 100.0 if state.pulse.build == "PASS" else (0.0 if state.pulse.build == "FAIL" else 50.0)
    b_color = _GREEN if b > 70 else (_AMBER if b > 40 else _RED)
    b_label = state.pulse.build if state.pulse.build != "UNKNOWN" else "---"
    lines.append(f"  [{b_color}]{b_label}[/] Build")
    risk_map = {"Low": 20, "Medium": 50, "High": 80, "Unknown": 50}
    r = risk_map.get(state.pulse.risk, 50)
    r_color = _GREEN if r < 30 else (_AMBER if r < 60 else _RED)
    lines.append(f"  [{r_color}]{state.pulse.risk}[/] Risk")
    return Panel("\n".join(lines), title="HEALTH", border_style=_BORDER_HEALTH)


def _render_stats(state: CockpitState) -> Panel:
    lines = []
    # Token usage with visual bar
    lines.append(f"  Tokens:     [{_ACCENT}]{state.tokens_used:,}[/]")
    if state.prompt_tokens or state.completion_tokens:
        lines.append(f"    in:{state.prompt_tokens:,} out:{state.completion_tokens:,}")
    # Context window usage bar
    ctx = state.context_percent
    bar_len = 14
    filled = int(ctx / 100 * bar_len)
    bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
    ctx_color = _GREEN if ctx <= 70 else (_AMBER if ctx <= 85 else _RED)
    lines.append(f"  Context:    [{ctx_color}]{bar}[/] {ctx:.0f}%")
    if ctx > 85:
        lines.append(f"    [{_RED}]! near limit ({state.context_max:,})[/]")
    # Confidence
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
    if state.vector_chunks > 0:
        lines.append(f"  Vectors:    [{_ACCENT}]{state.vector_chunks:,}[/]")
    if state.session_id:
        lines.append(f"  Session:    [{_MUTED}]{state.session_id}[/]")
    return Panel("\n".join(lines), title="STATS", border_style=_BORDER_STATS)


def _render_footer(state: CockpitState) -> Panel:
    left = Text.assemble(
        (_ORB.render().plain + " ", _MUTED),
        (f" {state.status_message} ", _WHITE),
    )
    if state.error_message:
        left = Text.assemble((state.error_message, f"bold {_RED}"))
    right = Text.assemble(
        (" /help", _MUTED),
        (" · ", _BORDER),
        ("q", _AMBER),
        (":quit ", _MUTED),
    )
    return Panel(Group(left, right), border_style=_BORDER_FOOTER)


def _render_response(state: CockpitState) -> Panel:
    renderables = []

    tool_calls_shown = 0
    for tc in list(state.tool_calls)[-6:]:
        tool_calls_shown += 1
        tool = tc.get("tool", "?")
        args = tc.get("args", {})
        success = tc.get("success", True)
        dur = tc.get("duration_ms", 0)
        icon = "\u2713" if success else "\u2717"
        color = _GREEN if success else _RED

        arg_summary = ""
        if "path" in args:
            arg_summary = args["path"]
        elif "pattern" in args:
            arg_summary = args["pattern"]
        elif "command" in args:
            arg_summary = args["command"][:40]
        elif "source" in args:
            arg_summary = f"{args['source']} -> {args.get('destination', '?')}"
        elif "url" in args:
            arg_summary = args["url"][:40]

        dur_str = f" {dur:.0f}ms" if dur else ""
        header = Text.assemble(
            (f"  {icon} ", f"bold {color}"),
            (tool, f"bold {_CYAN}"),
            (f" {arg_summary}" if arg_summary else "", _MUTED),
            (dur_str, _MUTED),
        )
        renderables.append(header)

    if tool_calls_shown:
        renderables.append(Text(""))

    display_msgs = state.messages[-6:] if state.messages else []
    for msg in display_msgs:
        role = msg.get("role", "")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls", [])

        if role == "user" and content:
            lines = content.split("\n")
            preview = lines[0][:120]
            if len(lines) > 1:
                preview += f" (+{len(lines)-1} more lines)"
            renderables.append(Text.assemble(
                ("  \u25b6 ", f"bold {_GREEN}"),
                ("You", f"bold {_GREEN}"),
                (f"  {preview}", _WHITE),
            ))

        elif role == "assistant":
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {}).get("name", "?")
                    renderables.append(Text.assemble(
                        ("  \u25b8 ", f"bold {_AMBER}"),
                        ("calling ", _MUTED),
                        (fn, f"bold {_CYAN}"),
                    ))
            if content:
                try:
                    md = RichMarkdown(content[:1200])
                    renderables.append(md)
                except Exception:
                    renderables.append(Text(f"  {content[:1200]}", _WHITE))
                renderables.append(Text(""))

    if state.streaming_text:
        renderables.append(Text.assemble(
            ("  \u25b8 ", f"bold {_CYAN}"),
            (state.streaming_text[-400:], _CYAN),
        ))

    if not renderables:
        renderables.append(Text("  No responses yet.", style=_MUTED))
        renderables.append(Text(""))
        renderables.append(Text("  Type a message below to get started.", style=_MUTED))
        renderables.append(Text("  The agent will read your code, plan, and build.", style=f"{_MUTED}"))
        renderables.append(Text(""))
        renderables.append(Text("  Try:", style=_MUTED))
        renderables.append(Text("    add user authentication", style=f"italic {_CYAN}"))
        renderables.append(Text("    fix the bug in src/main.py", style=f"italic {_CYAN}"))
        renderables.append(Text("    refactor the database layer", style=f"italic {_CYAN}"))

    msg_count = len([m for m in state.messages if m.get("role") == "user"])
    tc_count = len(state.tool_calls)
    title = f"CHAT"
    if msg_count or tc_count:
        title += f"  ({msg_count} msgs, {tc_count} tools)"

    return Panel(
        Group(*renderables),
        title=f"[bold]{title}[/]",
        border_style=_BORDER_ACCENT,
        padding=(0, 1),
    )


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
        Layout(renderable=_render_input(state), size=28),
        Layout(renderable=_render_response(state), ratio=3),
        Layout(renderable=_render_feed(state), size=28),
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

    def _redraw() -> None:
        try:
            console.clear()
            console.print(build_layout(state))
        except Exception:
            pass

    try:
        while True:
            _redraw()
            try:
                line = console.input("[bold bright_green]> [/]")
            except (EOFError, KeyboardInterrupt):
                break

            stripped = line.strip()
            if not stripped:
                continue
            if stripped.lower() in ("exit", "quit", "q"):
                state.status_message = "SHUTTING DOWN"
                _redraw()
                time.sleep(0.2)
                break

            state.input_text = line

            if stripped.startswith("/"):
                cmd = stripped.split()[0].lower()
                if cmd in ("/exit", "/quit"):
                    break
                state.command_mode = True
                state.add_message("user", line)
                state.status_message = f"CMD: {stripped[:60]}"
                _ORB.set_state("planning", "Processing")
                _redraw()
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
                _redraw()
                continue

            state.add_message("user", line)
            state.status_message = "PROCESSING"
            _ORB.set_state("thinking", label="Thinking")
            state.input_text = ""
            state.add_timeline(f"Processing: {line[:60]}")
            _redraw()

            try:
                on_message(state, line)
            except Exception as e:
                state.add_timeline(f"Error: {type(e).__name__}")
                state.error_message = f"{type(e).__name__}: {str(e)[:100]}"
                state.add_diagnostic(f"UNCAUGHT: {e}")

            state.status_message = "READY"
            _ORB.set_state("idle")
            _redraw()
    except Exception as e:
        console.print(f"[yellow]TUI unavailable ({type(e).__name__}: {e}). Using simple mode.[/]")
        try:
            _simple_fallback(model, on_message, initial_messages)
        except Exception as e2:
            console.print(f"[red]Simple mode also failed: {e2}[/]")
            _basic_fallback(model, on_message, initial_messages)
        return
    finally:
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
