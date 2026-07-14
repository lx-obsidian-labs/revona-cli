from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from . import AGENT_DIR


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Task:
    id: str
    label: str
    description: str
    agent: str = "builder"
    model: str | None = None
    depends_on: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    error: str | None = None
    retries: int = 0
    max_retries: int = 2
    files_changed: list[str] = field(default_factory=list)

class Mission:
    """A structured session with tasks, decisions, checkpoints."""

    def __init__(self, request: str, context: str = ""):
        self.id = time.strftime("%Y%m%d-%H%M%S")
        self.request = request
        self.context = context
        self.tasks: dict[str, Task] = {}
        self.edited_files: set[str] = set()
        self.decisions: list[str] = []
        self.checkpoints: list[dict] = []
        self.created_at = time.time()

    def add_task(self, task: Task) -> None:
        self.tasks[task.id] = task

    def get_ready_tasks(self) -> list[Task]:
        """Return tasks whose dependencies are all done and that are pending."""
        ready = []
        for t in self.tasks.values():
            if t.status != TaskStatus.PENDING:
                continue
            if all(
                self.tasks[dep].status == TaskStatus.DONE
                for dep in t.depends_on
            ):
                ready.append(t)
        return ready

    def any_running(self) -> bool:
        return any(t.status == TaskStatus.RUNNING for t in self.tasks.values())

    def any_failed(self) -> bool:
        return any(t.status == TaskStatus.FAILED for t in self.tasks.values())

    def all_done(self) -> bool:
        return all(t.status == TaskStatus.DONE for t in self.tasks.values())

    def all_terminal(self) -> bool:
        return all(t.status in (TaskStatus.DONE, TaskStatus.FAILED) for t in self.tasks.values())

    def summary(self) -> str:
        done = sum(1 for t in self.tasks.values() if t.status == TaskStatus.DONE)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        total = len(self.tasks)
        return f"[{done}/{total} tasks done, {failed} failed]"

    def status_counts(self) -> str:
        done = sum(1 for t in self.tasks.values() if t.status == TaskStatus.DONE)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
        running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
        parts = []
        if done: parts.append(f"{done} done")
        if failed: parts.append(f"{failed} failed")
        if running: parts.append(f"{running} running")
        if pending: parts.append(f"{pending} pending")
        return ", ".join(parts) or "0 tasks"

    def checkpoint(self, label: str, data: dict) -> None:
        self.checkpoints.append({"time": time.time(), "label": label, **data})

    def save(self, path: Path | None = None) -> str:
        path = path or AGENT_DIR / "missions" / f"{self.id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "id": self.id,
            "request": self.request,
            "context": self.context[:500],
            "edited_files": list(self.edited_files),
            "decisions": self.decisions,
            "tasks": {
                tid: {
                    "label": t.label,
                    "status": t.status.value,
                    "agent": t.agent,
                    "depends_on": t.depends_on,
                    "error": t.error,
                    "retries": t.retries,
                    "files_changed": t.files_changed,
                }
                for tid, t in self.tasks.items()
            },
            "checkpoints": self.checkpoints,
            "created_at": self.created_at,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return str(path)
