from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from . import AGENT_DIR


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
