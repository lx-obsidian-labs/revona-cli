from __future__ import annotations

import enum
import json
import time
import threading
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Callable

from . import AGENT_DIR
from .terminal import console


# ---------------------------------------------------------------------------
# Mission States (formal state machine)
# ---------------------------------------------------------------------------

class MissionState(enum.Enum):
    MISSION_CREATED = "MISSION_CREATED"
    DISCOVERY = "DISCOVERY"
    CAPABILITY_DISCOVERY = "CAPABILITY_DISCOVERY"
    REPOSITORY_ANALYSIS = "REPOSITORY_ANALYSIS"
    ARCHITECTURE = "ARCHITECTURE"
    PLANNING = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTION = "EXECUTION"
    VALIDATION = "VALIDATION"
    SECURITY_REVIEW = "SECURITY_REVIEW"
    DOCUMENTATION = "DOCUMENTATION"
    REFLECTION = "REFLECTION"
    MISSION_COMPLETE = "MISSION_COMPLETE"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    CANCELLED = "CANCELLED"


_MISSION_FLOW: list[MissionState] = [
    MissionState.MISSION_CREATED,
    MissionState.DISCOVERY,
    MissionState.CAPABILITY_DISCOVERY,
    MissionState.REPOSITORY_ANALYSIS,
    MissionState.ARCHITECTURE,
    MissionState.PLANNING,
    MissionState.WAITING_APPROVAL,
    MissionState.EXECUTION,
    MissionState.VALIDATION,
    MissionState.SECURITY_REVIEW,
    MissionState.DOCUMENTATION,
    MissionState.REFLECTION,
    MissionState.MISSION_COMPLETE,
]


def _state_index(s: MissionState) -> int:
    try:
        return _MISSION_FLOW.index(s)
    except ValueError:
        return -1


def can_transition(from_state: MissionState, to_state: MissionState) -> bool:
    if from_state == to_state:
        return True
    if to_state in (MissionState.FAILED, MissionState.CANCELLED):
        return True
    if to_state == MissionState.RECOVERING:
        return from_state != MissionState.MISSION_COMPLETE
    fi = _state_index(from_state)
    ti = _state_index(to_state)
    if fi >= 0 and ti >= 0:
        return ti == fi + 1 or ti == fi
    return False


# ---------------------------------------------------------------------------
# Mission Priority
# ---------------------------------------------------------------------------

class MissionPriority(enum.IntEnum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


# ---------------------------------------------------------------------------
# Mission Queue Status
# ---------------------------------------------------------------------------

class QueueStatus(enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Mission Data Classes
# ---------------------------------------------------------------------------

@dataclass
class MissionSnapshot:
    state: MissionState
    request: str
    context: str
    capabilities: dict[str, bool | str]
    architecture: str
    plan: str
    files_changed: list[str]
    verification_results: dict[str, bool | str]
    agent_states: dict[str, str]
    checkpoint_id: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "request": self.request,
            "context": self.context,
            "capabilities": self.capabilities,
            "architecture": self.architecture,
            "plan": self.plan,
            "files_changed": self.files_changed,
            "verification_results": self.verification_results,
            "agent_states": self.agent_states,
            "checkpoint_id": self.checkpoint_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MissionSnapshot:
        return cls(
            state=MissionState(d["state"]),
            request=d["request"],
            context=d.get("context", ""),
            capabilities=d.get("capabilities", {}),
            architecture=d.get("architecture", ""),
            plan=d.get("plan", ""),
            files_changed=d.get("files_changed", []),
            verification_results=d.get("verification_results", {}),
            agent_states=d.get("agent_states", {}),
            checkpoint_id=d.get("checkpoint_id", ""),
            timestamp=d.get("timestamp", 0.0),
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Mission Class (v2.0)
# ---------------------------------------------------------------------------

class Mission:
    """Formal mission with state machine enforcement."""

    def __init__(
        self,
        request: str,
        mission_id: str | None = None,
        priority: MissionPriority = MissionPriority.NORMAL,
        metadata: dict | None = None,
    ):
        self.id = mission_id or f"mis-{int(time.time())}-{id(self) % 10000}"
        self.request = request
        self.priority = priority
        self.metadata = metadata or {}
        self._state: MissionState = MissionState.MISSION_CREATED
        self._state_history: list[tuple[MissionState, float]] = [(self._state, time.time())]
        self._lock = threading.Lock()
        self._created_at = time.time()
        self._completed_at: float | None = None
        self._error: str | None = None

        self.capabilities: dict[str, bool | str] = {}
        self.architecture: str = ""
        self.plan: str = ""
        self.context: str = ""
        self.files_changed: list[str] = []
        self.verification_results: dict[str, bool | str] = {}
        self.agent_states: dict[str, str] = {}
        self.edited_files: set[str] = set()
        self.checkpoint_count: int = 0

        self.on_state_change: Callable | None = None

    @property
    def state(self) -> MissionState:
        return self._state

    @state.setter
    def state(self, new_state: MissionState) -> None:
        self.transition_to(new_state)

    def transition_to(self, new_state: MissionState, reason: str = "") -> bool:
        with self._lock:
            if not can_transition(self._state, new_state):
                console.print(f"[red]Invalid transition: {self._state.value} → {new_state.value}[/]")
                return False
            old = self._state
            self._state = new_state
            self._state_history.append((new_state, time.time()))
            if new_state == MissionState.MISSION_COMPLETE:
                self._completed_at = time.time()
            if new_state == MissionState.FAILED and reason:
                self._error = reason
            if self.on_state_change:
                try:
                    self.on_state_change(old, new_state, reason)
                except Exception:
                    pass
            return True

    def elapsed(self) -> float:
        end = self._completed_at or time.time()
        return end - self._created_at

    def state_history(self) -> list[tuple[str, float]]:
        return [(s.value, t) for s, t in self._state_history]

    @property
    def is_complete(self) -> bool:
        return self._state in (MissionState.MISSION_COMPLETE, MissionState.FAILED, MissionState.CANCELLED)

    @property
    def is_terminal(self) -> bool:
        return self._state in (MissionState.MISSION_COMPLETE, MissionState.FAILED, MissionState.CANCELLED)

    @property
    def error(self) -> str | None:
        return self._error

    def snapshot(self) -> MissionSnapshot:
        return MissionSnapshot(
            state=self._state,
            request=self.request,
            context=self.context,
            capabilities=dict(self.capabilities),
            architecture=self.architecture,
            plan=self.plan,
            files_changed=list(self.files_changed),
            verification_results=dict(self.verification_results),
            agent_states=dict(self.agent_states),
            checkpoint_id=f"cp-{self.id}-{self.checkpoint_count}",
            timestamp=time.time(),
            metadata={"priority": self.priority.name, "elapsed": self.elapsed()},
        )

    def summary(self) -> str:
        parts = [
            f"Mission: {self.id}",
            f"State: {self._state.value}",
            f"Request: {self.request[:80]}",
            f"Files changed: {len(self.files_changed)}",
            f"Verification: {sum(1 for v in self.verification_results.values() if v == True)}/{len(self.verification_results)} passed",
            f"Elapsed: {self.elapsed():.1f}s",
        ]
        return "\n".join(parts)

    def engineering_score(self) -> dict[str, float]:
        score = {
            "architecture": 0.0,
            "quality": 0.0,
            "tests": 0.0,
            "security": 0.0,
            "performance": 0.0,
            "documentation": 0.0,
            "overall": 0.0,
        }
        if self.plan:
            score["architecture"] = 0.85
        if self.files_changed:
            score["quality"] = 0.80
        if self.verification_results.get("tests") == True:
            score["tests"] = 0.90
        if self.verification_results.get("security") == True:
            score["security"] = 1.0
        score["overall"] = sum(score.values()) / max(len(score) - 1, 1)
        return score


# ---------------------------------------------------------------------------
# Mission Queue
# ---------------------------------------------------------------------------

class MissionQueue:
    """Manage multiple missions concurrently."""

    def __init__(self):
        self._missions: dict[str, Mission] = {}
        self._status: dict[str, QueueStatus] = {}
        self._lock = threading.Lock()

    def add(self, mission: Mission, status: QueueStatus = QueueStatus.QUEUED) -> None:
        with self._lock:
            self._missions[mission.id] = mission
            self._status[mission.id] = status

    def get(self, mission_id: str) -> Mission | None:
        return self._missions.get(mission_id)

    def status(self, mission_id: str) -> QueueStatus:
        return self._status.get(mission_id, QueueStatus.CANCELLED)

    def set_status(self, mission_id: str, status: QueueStatus) -> None:
        with self._lock:
            if mission_id in self._status:
                self._status[mission_id] = status

    def running(self) -> list[Mission]:
        return [m for i, m in self._missions.items() if self._status.get(i) == QueueStatus.RUNNING]

    def queued(self) -> list[Mission]:
        return [m for i, m in self._missions.items() if self._status.get(i) == QueueStatus.QUEUED]

    def all(self) -> list[Mission]:
        return list(self._missions.values())

    def summary(self) -> str:
        lines = []
        for mid, m in self._missions.items():
            s = self._status.get(mid, QueueStatus.QUEUED)
            p = m.priority.name
            lines.append(f"  {s.value.upper():20s} [{p:8s}] {m.id} — {m.request[:60]}")
        return "\n".join(lines)

    def remove(self, mission_id: str) -> None:
        with self._lock:
            self._missions.pop(mission_id, None)
            self._status.pop(mission_id, None)


# ---------------------------------------------------------------------------
# Checkpoint Manager
# ---------------------------------------------------------------------------

CHECKPOINT_DIR = AGENT_DIR / "checkpoints"


class CheckpointManager:
    """Save and restore mission state."""

    def __init__(self):
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    def save(self, snapshot: MissionSnapshot) -> str:
        path = CHECKPOINT_DIR / f"{snapshot.checkpoint_id}.json"
        path.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
        return str(path)

    def load(self, checkpoint_id: str) -> MissionSnapshot | None:
        path = CHECKPOINT_DIR / f"{checkpoint_id}.json"
        if not path.exists():
            for p in CHECKPOINT_DIR.glob(f"{checkpoint_id}*.json"):
                path = p
                break
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return MissionSnapshot.from_dict(data)
        except Exception:
            return None

    def list_checkpoints(self, mission_id: str | None = None) -> list[str]:
        if mission_id:
            pattern = f"cp-{mission_id}-*.json"
        else:
            pattern = "cp-*.json"
        return sorted(str(p) for p in CHECKPOINT_DIR.glob(pattern))

    def purge(self, mission_id: str) -> int:
        count = 0
        for p in CHECKPOINT_DIR.glob(f"cp-{mission_id}-*.json"):
            p.unlink()
            count += 1
        return count


# ---------------------------------------------------------------------------
# Workspace Manager
# ---------------------------------------------------------------------------

class Workspace:
    """A single repository workspace with independent memory."""

    def __init__(self, name: str, root: Path):
        self.name = name
        self.root = root.resolve()
        self._missions: list[str] = []

    def add_mission(self, mission_id: str) -> None:
        self._missions.append(mission_id)

    @property
    def mission_ids(self) -> list[str]:
        return list(self._missions)

    def __repr__(self) -> str:
        return f"Workspace({self.name}, {self.root})"


class WorkspaceManager:
    """Manage multiple repository workspaces."""

    def __init__(self):
        self._workspaces: dict[str, Workspace] = {}
        self._active: str | None = None

    def add(self, name: str, root: str | Path) -> Workspace:
        ws = Workspace(name, Path(root))
        self._workspaces[name] = ws
        return ws

    def get(self, name: str) -> Workspace | None:
        return self._workspaces.get(name)

    def remove(self, name: str) -> None:
        self._workspaces.pop(name, None)
        if self._active == name:
            self._active = None

    def activate(self, name: str) -> bool:
        if name in self._workspaces:
            self._active = name
            return True
        return False

    @property
    def active(self) -> Workspace | None:
        if self._active:
            return self._workspaces.get(self._active)
        return None

    @property
    def active_name(self) -> str | None:
        return self._active

    def all(self) -> list[Workspace]:
        return list(self._workspaces.values())

    def summary(self) -> str:
        lines = []
        for w in self._workspaces.values():
            marker = "→ " if w.name == self._active else "  "
            lines.append(f"{marker}{w.name:20s} {w.root}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Governance — Policy Engine
# ---------------------------------------------------------------------------

class PermissionLevel(Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    DESTRUCTIVE = "destructive"
    ADMIN = "admin"


_DESTRUCTIVE_TOOLS = {
    "run_shell": {"rm", "del", "rd", "rmdir", "remove", "unlink", "wipe", "format"},
    "write_file": set(),
    "edit_file": set(),
}

_DESTRUCTIVE_PATTERNS = {
    "rm -rf", "rm -r", "rm -f",
    "del /f", "rd /s",
    "git push --force", "git reset --hard",
    "drop table", "drop database", "truncate",
    "shutdown", "reboot",
    "chmod 777", "chown",
}


class PolicyEngine:
    def __init__(self, level: PermissionLevel = PermissionLevel.READ_WRITE):
        self.level = level
        self._approval_gates: list[Callable] = []

    def set_level(self, level: PermissionLevel) -> None:
        self.level = level

    def check_tool(self, tool_name: str, args: dict | None = None) -> tuple[bool, str]:
        if self.level == PermissionLevel.ADMIN:
            return True, "admin level"
        if self.level == PermissionLevel.READ_ONLY:
            if tool_name in ("write_file", "edit_file", "run_shell"):
                return False, "read-only mode"
        if self.level == PermissionLevel.READ_WRITE and tool_name in _DESTRUCTIVE_TOOLS:
            for arg_val in (args or {}).values():
                if isinstance(arg_val, str):
                    al = arg_val.lower()
                    for pat in _DESTRUCTIVE_TOOLS[tool_name]:
                        if pat in al:
                            return False, f"destructive pattern blocked: {pat}"
                    for dp in _DESTRUCTIVE_PATTERNS:
                        if dp in al:
                            return False, f"destructive pattern blocked: {dp}"
        for gate in self._approval_gates:
            try:
                ok, msg = gate(tool_name, args)
                if not ok:
                    return False, msg
            except Exception:
                pass
        return True, "allowed"

    def requires_approval(self, tool_name: str, args: dict | None = None) -> bool:
        if self.level == PermissionLevel.ADMIN:
            return False
        if tool_name == "run_shell":
            cmd = (args or {}).get("command", "")
            if any(dp in cmd.lower() for dp in _DESTRUCTIVE_PATTERNS):
                return True
        return False


# ---------------------------------------------------------------------------
# Governance — Audit Logger
# ---------------------------------------------------------------------------

AUDIT_LOG_PATH = AGENT_DIR / "audit.jsonl"


@dataclass
class AuditEntry:
    timestamp: float
    agent: str
    action: str
    tool: str
    args: dict
    result: str
    allowed: bool
    duration_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "agent": self.agent,
            "action": self.action,
            "tool": self.tool,
            "args": {k: str(v)[:200] for k, v in self.args.items()},
            "result": self.result[:500],
            "allowed": self.allowed,
            "duration_ms": round(self.duration_ms, 1),
            "metadata": self.metadata,
        }


class AuditLogger:
    def __init__(self):
        AGENT_DIR.mkdir(exist_ok=True)

    def log(self, entry: AuditEntry) -> None:
        try:
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except Exception:
            pass

    def recent(self, n: int = 20) -> list[dict]:
        if not AUDIT_LOG_PATH.exists():
            return []
        entries = []
        try:
            with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except Exception:
            pass
        return entries[-n:]

    def summary(self) -> str:
        entries = self.recent(50)
        if not entries:
            return "No audit entries"
        allowed = sum(1 for e in entries if e.get("allowed"))
        blocked = sum(1 for e in entries if not e.get("allowed"))
        return f"Audit: {len(entries)} actions ({allowed} allowed, {blocked} blocked)"
