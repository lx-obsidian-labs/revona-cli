from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Thread, Event
from typing import Any, Callable

from . import IGNORE_DIRS, TEXT_EXTS
from .repo_db import RepositoryDatabase


class FileChange:
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"

    def __init__(self, path: str, change_type: str):
        self.path = path
        self.type = change_type

    def __repr__(self) -> str:
        return f"{self.type.upper():8s} {self.path}"


class RepositoryWatcher:
    def __init__(
        self,
        root: str | Path = ".",
        interval: float = 5.0,
        db: RepositoryDatabase | None = None,
    ):
        self.root = Path(root).resolve()
        self.interval = interval
        self.db = db or RepositoryDatabase()
        self._snapshot: dict[str, float] = {}
        self._stop = Event()
        self._thread: Thread | None = None
        self._on_change: Callable | None = None
        self._change_count = 0

    def set_on_change(self, cb: Callable) -> None:
        self._on_change = cb

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._take_snapshot()
        self._stop.clear()
        self._thread = Thread(target=self._run, daemon=True, name="repo-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def change_count(self) -> int:
        return self._change_count

    def _take_snapshot(self) -> None:
        self._snapshot = {}
        for ext in TEXT_EXTS:
            for f in self.root.rglob(f"*{ext}"):
                if any(part in IGNORE_DIRS or part.startswith(".") for part in f.relative_to(self.root).parts):
                    continue
                try:
                    self._snapshot[str(f.relative_to(self.root))] = f.stat().st_mtime
                except Exception:
                    pass

    def _run(self) -> None:
        while not self._stop.is_set():
            time.sleep(self.interval)
            try:
                changes = self._check()
                for change in changes:
                    self._change_count += 1
                    self._handle_change(change)
            except Exception:
                pass

    def _check(self) -> list[FileChange]:
        changes = []
        current: dict[str, float] = {}
        for ext in TEXT_EXTS:
            for f in self.root.rglob(f"*{ext}"):
                if any(part in IGNORE_DIRS or part.startswith(".") for part in f.relative_to(self.root).parts):
                    continue
                try:
                    rel = str(f.relative_to(self.root))
                    mtime = f.stat().st_mtime
                    current[rel] = mtime
                    if rel not in self._snapshot:
                        changes.append(FileChange(rel, FileChange.CREATED))
                    elif abs(mtime - self._snapshot[rel]) > 0.1:
                        changes.append(FileChange(rel, FileChange.MODIFIED))
                except Exception:
                    pass
        for rel in self._snapshot:
            if rel not in current:
                changes.append(FileChange(rel, FileChange.DELETED))
        self._snapshot = current
        return changes

    def _handle_change(self, change: FileChange) -> None:
        try:
            if change.type == FileChange.DELETED:
                self.db.remove_file(change.path)
            elif change.type in (FileChange.CREATED, FileChange.MODIFIED):
                full_path = self.root / change.path
                if full_path.exists():
                    self.db.index_file(full_path, self.root)
        except Exception:
            pass
        if self._on_change:
            try:
                self._on_change(change)
            except Exception:
                pass

    def summary(self) -> str:
        return f"Watcher: {'running' if self.is_running else 'stopped'}, {self._change_count} changes detected"
