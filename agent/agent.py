from __future__ import annotations

import json
from copy import deepcopy
from typing import Callable

from rich.markdown import Markdown
from rich.panel import Panel

from . import DEFAULT_MODEL
from .agents import AGENTS, AgentSpec, get as get_agent, resolve_tools
from .memory import IntelligenceEngine
from .mission import Mission, Task, TaskStatus
from .progress import ProgressEngine
from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, execute_tool
from .terminal import console

_intel = IntelligenceEngine()


# ---------------------------------------------------------------------------
# Low-level agent loop
# ---------------------------------------------------------------------------

def _run_agent_loop(
    client,
    model: str,
    system_prompt: str,
    user_prompt: str,
    allowed_tools: list[dict],
    max_iter: int = 30,
    on_tool: Callable | None = None,
) -> tuple[str, list[dict]]:
    """Run a single agent with its tools. Returns (final_text, messages)."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": user_prompt})

    for i in range(max_iter):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=allowed_tools or None,
            stream=False,
            temperature=0.2,
        )
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
                args = json.loads(tc.function.arguments or "{}")
                if on_tool:
                    on_tool(tc.function.name, args)
                result = execute_tool(tc.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result[:12000],
                })
            continue

        final = msg.content or ""
        messages.append({"role": "assistant", "content": final})
        return final, messages

    return "(max iterations reached)", messages


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def decompose_into_tasks(
    client, model: str, request: str, context: str
) -> list[dict]:
    """Ask the planner to break a request into a structured task list."""
    planner_spec = get_agent("planner")
    if not planner_spec:
        return _default_tasks(request)

    prompt = (
        f"## Repository context\n{context[:20000]}\n\n"
        f"## Request\n{request}\n\n"
        "Break this request into a list of numbered tasks that can be executed "
        "sequentially. Each task should be a single, focused action. "
        "Format as a JSON list:\n"
        '[{"id": "1", "label": "short label", "description": "what to do", '
        '"agent": "builder|tester|reviewer"}]\n'
        "Output ONLY the JSON, no other text."
    )

    try:
        text, _ = _run_agent_loop(
            client, model,
            planner_spec.system_prompt,
            prompt,
            resolve_tools(planner_spec.allowed_tools),
            max_iter=5,
        )
        # Extract JSON from response
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        tasks = json.loads(text)
        if isinstance(tasks, list):
            return tasks
    except Exception:
        pass
    return _default_tasks(request)


def _default_tasks(request: str) -> list[dict]:
    """Fallback when decomposition fails."""
    return [{"id": "1", "label": "Implement", "description": request, "agent": "builder"}]


def verify_changes(
    client, model: str, mission: Mission,
) -> tuple[bool, str]:
    """Run the reviewer agent over changed files."""
    reviewer = get_agent("reviewer")
    if not reviewer:
        return True, "no reviewer configured"

    changed = list(mission.edited_files)
    if not changed:
        return True, "no files changed"

    prompt = (
        "Review these changed files for correctness, security, and style:\n"
        + "\n".join(f"- {f}" for f in changed)
        + "\n\nRun relevant lint/type-check commands. Report any issues."
    )

    text, _ = _run_agent_loop(
        client, model,
        reviewer.system_prompt,
        prompt,
        resolve_tools(reviewer.allowed_tools),
        max_iter=15,
    )
    approved = "APPROVED" in text
    return approved, text


def run_tests(
    client, model: str, mission: Mission,
) -> tuple[bool, str]:
    """Run the tester agent."""
    tester = get_agent("tester")
    if not tester:
        return True, "no tester configured"

    prompt = (
        "Discover and run the project's tests. "
        "If none exist, check a few key files for correctness manually."
    )

    text, _ = _run_agent_loop(
        client, model,
        tester.system_prompt,
        prompt,
        resolve_tools(tester.allowed_tools),
        max_iter=15,
    )
    passing = "ALL TESTS PASSING" in text
    return passing, text


def execute_mission(
    client,
    model: str,
    mission: Mission,
    progress: ProgressEngine,
    max_global_iter: int = 3,
) -> Mission:
    """Execute a mission: run each task with the right agent, verify, retry."""
    for global_pass in range(max_global_iter):
        if mission.all_done():
            break

        # Execute ready tasks
        for task in mission.get_ready_tasks():
            if task.status != TaskStatus.PENDING:
                continue

            task.status = TaskStatus.RUNNING
            progress.start(task.id)

            # Pick agent and model
            agent_spec = get_agent(task.agent) or get_agent("builder")
            task_model = task.model or model

            tools = resolve_tools(agent_spec.allowed_tools) if agent_spec else TOOL_SCHEMAS

            context = mission.context if global_pass == 0 else ""
            prompt = (
                f"## Task: {task.label}\n{task.description}\n\n"
                f"## Repository context\n{context[:20000]}\n\n"
                "Execute this task. Use the available tools."
            )

            def _on_tool(name, args):
                if name in ("write_file", "edit_file"):
                    fp = args.get("path", "")
                    if fp:
                        mission.edited_files.add(fp)
                        task.files_changed.append(fp)

            try:
                text, _ = _run_agent_loop(
                    client, task_model,
                    agent_spec.system_prompt,
                    prompt,
                    tools,
                    max_iter=30,
                    on_tool=_on_tool,
                )
                task.result = text[:2000]

                # Auto-verify: run build/lint/test command
                shell_result = execute_tool("run_shell", {"command": "python -m pytest --version 2>nul || pytest --version 2>nul || echo no test framework found"})
                has_tests = "pytest" in shell_result.lower()

                if has_tests:
                    test_out = execute_tool("run_shell", {"command": "python -m pytest -x -q 2>&1 || echo no tests to run"})
                    if "FAILED" in test_out or "ERROR" in test_out:
                        task.status = TaskStatus.FAILED
                        task.error = "Tests failed"
                        progress.fail(task.id, "tests failing")
                    else:
                        task.status = TaskStatus.DONE
                        progress.done(task.id)
                else:
                    task.status = TaskStatus.DONE
                    progress.done(task.id)

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)[:500]
                progress.fail(task.id, str(e)[:80])

        # Handle failures: retry or re-plan
        for task in mission.tasks.values():
            if task.status == TaskStatus.FAILED and task.retries < task.max_retries:
                task.retries += 1
                task.status = TaskStatus.PENDING
                progress.add_step(f"{task.id}-retry{task.retries}", f"Retry {task.label} ({task.retries}/{task.max_retries})")
                console.print(f"[yellow]Retrying {task.label}...[/]")

    # Final review pass
    if mission.edited_files:
        progress.add_step("review", "Reviewing changes")
        progress.start("review")
        approved, review_text = verify_changes(client, model, mission)
        if approved:
            progress.done("review")
        else:
            progress.fail("review")
            console.print(Panel(review_text[:2000], title="Review Issues"))

    return mission


def orchestrator_build(
    client,
    model: str,
    request: str,
    progress: ProgressEngine,
) -> Mission:
    """Full orchestrated build: decompose → execute → verify → reflect."""
    global _intel

    progress.add_step("brain", "Loading repository intelligence")
    progress.start("brain")
    enriched = _intel.load_all(request)
    progress.done("brain")

    progress.add_step("decompose", "Decomposing request into tasks")
    progress.start("decompose")

    task_list = decompose_into_tasks(client, model, request, enriched)
    progress.done("decompose")

    mission = Mission(request, enriched)
    for t in task_list:
        dep_ids = t.get("depends_on", [])
        if isinstance(dep_ids, str):
            dep_ids = [dep_ids]
        mission.add_task(Task(
            id=t["id"],
            label=t.get("label", t["id"]),
            description=t.get("description", ""),
            agent=t.get("agent", "builder"),
            model=model,
            depends_on=dep_ids,
        ))
        progress.add_step(t["id"], t.get("label", t["id"]))

    mission = execute_mission(client, model, mission, progress)
    mission.save()
    progress.summary(mission.summary())

    # Reflection phase
    progress.add_step("reflect", "Reflecting on mission — extracting lessons")
    progress.start("reflect")
    _intel.after_mission(client, model, request, list(mission.tasks.values()), mission.edited_files)
    progress.done("reflect")

    return mission


# ---------------------------------------------------------------------------
# Keep backward-compatible wrappers
# ---------------------------------------------------------------------------

def run_agent(client, model: str, prompt: str, messages: list | None = None, max_iter: int = 30, tui_state=None) -> list:
    """Simple chat loop (backward compatible). Optionally stream to a TUI state."""
    agent_spec = get_agent("builder")
    system = agent_spec.system_prompt if agent_spec else SYSTEM_PROMPT
    tools = resolve_tools(agent_spec.allowed_tools) if agent_spec else TOOL_SCHEMAS

    if messages is None:
        messages = [{"role": "system", "content": system}]
    messages.append({"role": "user", "content": prompt})

    for i in range(max_iter):
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=tools or None,
            stream=False, temperature=0.2,
        )
        msg = resp.choices[0].message

        if msg.tool_calls:
            messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                detail = f"> {tc.function.name}({json.dumps(args)[:200]})"
                if tui_state:
                    tui_state.add_activity(detail)
                else:
                    console.print(f"[dim]{detail}[/]")
                result = execute_tool(tc.function.name, args)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result[:12000]})
            continue

        stream = client.chat.completions.create(
            model=model,
            messages=messages + [{"role": "assistant", "content": msg.content}],
            stream=True, temperature=0.2,
        )
        if tui_state:
            tui_state.status_message = "Generating..."
            parts = []
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    parts.append(chunk.choices[0].delta.content)
                    tui_state.update_stream("".join(parts))
            tui_state.status_message = "Ready"
        else:
            console.print("[bold cyan]agent>[/] ", end="")
            parts = []
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    console.print(chunk.choices[0].delta.content, end="", highlight=False)
                    parts.append(chunk.choices[0].delta.content)
            console.print()
        messages.append({"role": "assistant", "content": "".join(parts)})
        return messages

    msg = "[yellow]Reached max iterations.[/]"
    if tui_state:
        tui_state.add_activity(msg)
    else:
        console.print(msg)
    return messages


def plan(client, model: str, request: str, context: str) -> list:
    """Generate a plan (backward compatible)."""
    planner_spec = get_agent("planner")
    system = planner_spec.system_prompt if planner_spec else SYSTEM_PROMPT
    messages = [{"role": "system", "content": system}]
    messages.append({"role": "user", "content": f"## Repository context\n{context[:40000]}\n\n## Request\n{request}\n\nProduce a plan."})
    resp = client.chat.completions.create(
        model=model, messages=messages, stream=False, temperature=0.2,
    )
    plan_text = resp.choices[0].message.content or ""
    messages.append({"role": "assistant", "content": plan_text})
    console.print(Panel(Markdown(plan_text), title="Plan", border_style="green"))
    return messages


def build(client, model: str, plan_messages: list, user_request: str, max_iter: int = 50) -> list:
    """Simple build loop (backward compatible)."""
    agent_spec = get_agent("builder")
    system = agent_spec.system_prompt if agent_spec else SYSTEM_PROMPT
    tools = resolve_tools(agent_spec.allowed_tools) if agent_spec else TOOL_SCHEMAS
    plan_text = plan_messages[-1]["content"] if plan_messages[-1]["role"] == "assistant" else ""
    messages = [{"role": "system", "content": f"{system}\n\n## Plan\n{plan_text}\n\nExecute this plan."}]
    messages.append({"role": "user", "content": user_request})

    for i in range(max_iter):
        console.print(f"\n[bold blue]--- Step {i + 1}/{max_iter} ---[/]")
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=tools, stream=False, temperature=0.2,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            stream = client.chat.completions.create(
                model=model,
                messages=messages + [{"role": "assistant", "content": msg.content}],
                stream=True, temperature=0.2,
            )
            console.print("[bold cyan]builder>[/] ", end="")
            parts = []
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    console.print(chunk.choices[0].delta.content, end="", highlight=False)
                    parts.append(chunk.choices[0].delta.content)
            console.print()
            messages.append({"role": "assistant", "content": "".join(parts)})
            return messages

        messages.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            console.print(f"[dim]> {tc.function.name}({json.dumps(args)[:200]})[/]")
            result = execute_tool(tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result[:12000]})

    console.print("[yellow]Builder reached max iterations.[/]")
    return messages
