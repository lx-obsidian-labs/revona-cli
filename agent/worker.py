from __future__ import annotations

import enum
import json
import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from .agents import AGENTS, get as get_agent, AgentState, AgentSpec
from .tools import TOOL_SCHEMAS, execute_tool
from .terminal import console


# ---------------------------------------------------------------------------
# Task model
# ---------------------------------------------------------------------------

class TaskStatus(enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    id: str
    description: str
    agent_name: str
    prompt: str
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: str = ""
    files_changed: list[str] = field(default_factory=list)
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    tool_calls: int = 0
    tokens_estimate: int = 0
    priority: int = 1

    @property
    def elapsed(self) -> float:
        if self.started_at == 0:
            return 0.0
        end = self.completed_at if self.completed_at else time.time()
        return end - self.started_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "agent": self.agent_name,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "files_changed": self.files_changed,
            "tool_calls": self.tool_calls,
            "elapsed": round(self.elapsed, 2),
            "error": self.error[:200] if self.error else "",
        }


# ---------------------------------------------------------------------------
# Task Graph (dependency-aware scheduling)
# ---------------------------------------------------------------------------

class TaskGraph:
    """Manages a DAG of tasks with dependency resolution."""

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()

    def add(self, task: Task) -> None:
        with self._lock:
            self._tasks[task.id] = task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def completed_ids(self) -> set[str]:
        with self._lock:
            return {tid for tid, t in self._tasks.items() if t.status == TaskStatus.COMPLETED}

    def failed_ids(self) -> set[str]:
        with self._lock:
            return {tid for tid, t in self._tasks.items() if t.status == TaskStatus.FAILED}

    def ready_tasks(self) -> list[Task]:
        """Return tasks whose dependencies are all completed and not yet started."""
        completed = self.completed_ids()
        failed = self.failed_ids()
        with self._lock:
            ready = []
            for t in self._tasks.values():
                if t.status != TaskStatus.PENDING:
                    continue
                deps_met = all(d in completed for d in t.dependencies)
                deps_failed = any(d in failed for d in t.dependencies)
                if deps_failed:
                    t.status = TaskStatus.SKIPPED
                    t.error = "Dependency failed"
                    continue
                if deps_met:
                    ready.append(t)
            return sorted(ready, key=lambda t: -t.priority)

    def mark_running(self, task_id: str) -> None:
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = TaskStatus.RUNNING
                self._tasks[task_id].started_at = time.time()

    def mark_completed(self, task_id: str, result: str, files: list[str] | None = None) -> None:
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                t.status = TaskStatus.COMPLETED
                t.result = result
                t.files_changed = files or []
                t.completed_at = time.time()

    def mark_failed(self, task_id: str, error: str) -> None:
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                t.status = TaskStatus.FAILED
                t.error = error
                t.completed_at = time.time()

    @property
    def is_complete(self) -> bool:
        with self._lock:
            return all(
                t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)
                for t in self._tasks.values()
            )

    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            counts = {}
            for t in self._tasks.values():
                counts[t.status.value] = counts.get(t.status.value, 0) + 1
            return counts

    def progress_percent(self) -> float:
        with self._lock:
            total = len(self._tasks)
            if total == 0:
                return 0.0
            done = sum(1 for t in self._tasks.values()
                       if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED))
            return done / total * 100


# ---------------------------------------------------------------------------
# Worker Pool
# ---------------------------------------------------------------------------

class WorkerPool:
    """Thread pool that executes tasks from a TaskGraph concurrently."""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._threads: list[threading.Thread] = []
        self._task_queue: queue.Queue[Task] = queue.Queue()
        self._graph: TaskGraph | None = None
        self._client = None
        self._model: str = ""
        self._stop = threading.Event()
        self._active_workers: dict[str, str] = {}  # thread_name -> task_id
        self._lock = threading.Lock()
        self._on_task_start: Callable | None = None
        self._on_task_complete: Callable | None = None
        self._on_task_error: Callable | None = None
        self._all_files: list[str] = []

    def configure(
        self,
        client,
        model: str,
        graph: TaskGraph,
        on_task_start: Callable | None = None,
        on_task_complete: Callable | None = None,
        on_task_error: Callable | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._graph = graph
        self._on_task_start = on_task_start
        self._on_task_complete = on_task_complete
        self._on_task_error = on_task_error

    def start(self) -> None:
        self._stop.clear()
        self._threads = []
        for i in range(self.max_workers):
            t = threading.Thread(target=self._worker_loop, name=f"worker-{i}", daemon=True)
            self._threads.append(t)
            t.start()

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)
        self._threads.clear()

    def submit(self, task: Task) -> None:
        self._task_queue.put(task)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active_workers)

    @property
    def worker_states(self) -> dict[str, str]:
        with self._lock:
            return dict(self._active_workers)

    @property
    def all_files_changed(self) -> list[str]:
        return list(set(self._all_files))

    def _worker_loop(self) -> None:
        worker_name = threading.current_thread().name
        while not self._stop.is_set():
            try:
                task = self._task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            with self._lock:
                self._active_workers[worker_name] = task.id

            if self._on_task_start:
                try:
                    self._on_task_start(task)
                except Exception:
                    pass

            agent_spec = get_agent(task.agent_name)
            if not agent_spec:
                if self._graph:
                    self._graph.mark_failed(task.id, f"Agent '{task.agent_name}' not found")
                if self._on_task_error:
                    try:
                        self._on_task_error(task, f"Agent '{task.agent_name}' not found")
                    except Exception:
                        pass
                with self._lock:
                    self._active_workers.pop(worker_name, None)
                continue

            try:
                result, files, tool_count = self._run_agent_task(agent_spec, task)
                task.tool_calls = tool_count
                if self._graph:
                    self._graph.mark_completed(task.id, result, files)
                with self._lock:
                    self._all_files.extend(files)
                if self._on_task_complete:
                    try:
                        self._on_task_complete(task)
                    except Exception:
                        pass
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)[:300]}"
                if self._graph:
                    self._graph.mark_failed(task.id, error_msg)
                if self._on_task_error:
                    try:
                        self._on_task_error(task, error_msg)
                    except Exception:
                        pass

            with self._lock:
                self._active_workers.pop(worker_name, None)

    def _run_agent_task(
        self, agent_spec: AgentSpec, task: Task
    ) -> tuple[str, list[str], int]:
        """Run a single agent task, return (result_text, files_changed, tool_call_count)."""
        from .tools import TOOL_INDEX

        tools = []
        for name in agent_spec.allowed_tools:
            if name in TOOL_INDEX:
                tools.append(TOOL_SCHEMAS[TOOL_INDEX[name]])

        system = agent_spec.system_prompt
        messages = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": task.prompt})

        files_changed = []
        tool_count = 0

        for i in range(30):
            if self._stop.is_set():
                break

            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools or None,
                    stream=False,
                    temperature=0.2,
                )
            except Exception as e:
                return f"LLM error: {e}", files_changed, tool_count

            msg = resp.choices[0].message

            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                })
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    tool_count += 1
                    try:
                        result = execute_tool(tc.function.name, args)
                    except Exception as e:
                        result = f"Tool error ({tc.function.name}): {e}"
                    if tc.function.name in ("write_file", "edit_file"):
                        fp = args.get("path", "")
                        if fp:
                            files_changed.append(fp)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(result)[:32000],
                    })
                continue

            final = msg.content or ""
            return final, files_changed, tool_count

        return "(max iterations)", files_changed, tool_count


# ---------------------------------------------------------------------------
# Parallel Orchestrator
# ---------------------------------------------------------------------------

class ParallelOrchestrator:
    """Decomposes a mission into tasks and runs them with a WorkerPool."""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.graph = TaskGraph()
        self.pool = WorkerPool(max_workers)
        self._mission_id: str = ""
        self._on_phase: Callable | None = None

    def decompose(
        self,
        client,
        model: str,
        plan_text: str,
        request: str,
    ) -> list[Task]:
        """Use the LLM to decompose a plan into concrete tasks with dependencies."""
        system = (
            "You are a task decomposition engine. Given an engineering plan, "
            "break it into concrete, executable tasks. Each task must specify:\n"
            "- A unique task ID (t-1, t-2, ...)\n"
            "- The agent type to assign (Frontend Engineer, Backend Engineer, QA Engineer, "
            "Security Engineer, Documentation Engineer, Database Engineer, DevOps Engineer)\n"
            "- A clear prompt for the agent\n"
            "- Dependency task IDs (if any)\n\n"
            "Output a JSON array of task objects:\n"
            '[{"id": "t-1", "agent": "Backend Engineer", "description": "...", '
            '"prompt": "...", "deps": []}]\n\n'
            "Rules:\n"
            "- Use the simplest viable dependency graph\n"
            "- Independent tasks should have no dependencies\n"
            "- If frontend depends on backend API, add that dependency\n"
            "- Max 12 tasks\n"
            "- Be concrete, not vague"
        )

        user_msg = (
            f"## Plan\n{plan_text[:8000]}\n\n"
            f"## Request\n{request}\n\n"
            "Decompose this plan into tasks."
        )

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                stream=False,
                temperature=0.1,
            )
            content = resp.choices[0].message.content or ""
        except Exception as e:
            console.print(f"[red]Task decomposition failed: {e}[/]")
            return self._fallback_decomposition(plan_text, request)

        return self._parse_tasks(content)

    def _parse_tasks(self, content: str) -> list[Task]:
        """Parse LLM output into Task objects."""
        import re

        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if not json_match:
            return []

        try:
            raw = json.loads(json_match.group())
        except json.JSONDecodeError:
            return []

        tasks = []
        for item in raw:
            t = Task(
                id=item.get("id", f"t-{len(tasks)+1}"),
                description=item.get("description", ""),
                agent_name=item.get("agent", "builder").lower(),
                prompt=item.get("prompt", item.get("description", "")),
                dependencies=item.get("deps", []),
                priority=item.get("priority", 1),
            )
            tasks.append(t)
        return tasks

    def _fallback_decomposition(self, plan_text: str, request: str) -> list[Task]:
        """Create a single fallback task when decomposition fails."""
        return [Task(
            id="t-1",
            description="Execute the full plan",
            agent_name="builder",
            prompt=f"## Plan\n{plan_text}\n\n## Request\n{request}\n\nExecute this plan step by step.",
        )]

    def execute(
        self,
        client,
        model: str,
        plan_text: str,
        request: str,
        progress: Any = None,
    ) -> dict[str, Any]:
        """Full parallel execution pipeline."""
        def _log(msg: str):
            if progress:
                try:
                    progress.add_timeline(msg)
                except Exception:
                    console.print(f"[dim]{msg}[/]")
            else:
                console.print(f"[dim]{msg}[/]")

        def _update_tui(phase: str, error: str = ""):
            if progress:
                try:
                    progress.update_from_mission(phase, error)
                except Exception:
                    pass

        # Phase 1: Decompose
        _log("Decomposing plan into parallel tasks...")
        _update_tui("EXECUTION")
        tasks = self.decompose(client, model, plan_text, request)

        if not tasks:
            _log("Decomposition produced no tasks, falling back to sequential")
            tasks = self._fallback_decomposition(plan_text, request)

        _log(f"Created {len(tasks)} tasks")
        for t in tasks:
            self.graph.add(t)

        # Phase 2: Configure worker pool
        def on_start(task: Task):
            _log(f"Worker started: {task.description[:60]}")
            if progress:
                try:
                    progress.set_agent_status(task.agent_name, "running")
                except Exception:
                    pass

        def on_complete(task: Task):
            _log(f"Worker done: {task.description[:60]} ({task.elapsed:.1f}s, {task.tool_calls} tools)")
            if progress:
                try:
                    progress.set_agent_status(task.agent_name, "idle")
                    progress.add_activity(f"Completed: {task.description[:80]}")
                except Exception:
                    pass

        def on_error(task: Task, error: str):
            _log(f"Worker failed: {task.description[:60]} — {error[:100]}")
            if progress:
                try:
                    progress.set_agent_status(task.agent_name, "error")
                    progress.add_diagnostic(f"Task {task.id} failed: {error[:100]}")
                except Exception:
                    pass

        self.pool.configure(
            client, model, self.graph,
            on_task_start=on_start,
            on_task_complete=on_complete,
            on_task_error=on_error,
        )

        # Phase 3: Start workers and feed tasks
        self.pool.start()
        _log(f"Started {self.max_workers} workers")

        # Feed ready tasks as they become available
        submitted = set()
        while not self.graph.is_complete:
            ready = self.graph.ready_tasks()
            for task in ready:
                if task.id not in submitted:
                    self.pool.submit(task)
                    submitted.add(task.id)
            time.sleep(0.3)

        # Stop workers
        self.pool.stop()

        # Phase 4: Collect results
        all_files = self.pool.all_files_changed
        stats = self.graph.stats
        _log(f"Execution complete: {stats}")

        return {
            "tasks": [t.to_dict() for t in self.graph.all_tasks()],
            "files_changed": all_files,
            "stats": stats,
            "total_elapsed": sum(t.elapsed for t in self.graph.all_tasks()),
        }
