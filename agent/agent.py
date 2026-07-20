from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from rich.markdown import Markdown
from rich.panel import Panel

from . import DEFAULT_MODEL
from .agents import AGENTS, get as get_agent, resolve_tools
from .capabilities import CapabilityDiscoveryEngine
from .context_ranker import ContextRanker
from .mission_engine import (
    Mission,
    MissionState,
    MissionPriority,
    MissionQueue,
    MissionSnapshot,
    CheckpointManager,
    WorkspaceManager,
)
from .memory import IntelligenceEngine
from .recovery import RecoveryEngine, FailureType, classify_failure
from .repo_db import RepositoryDatabase
from .semantic_search import SemanticSearch
from .tools import TOOL_SCHEMAS, execute_tool
from .terminal import console
from .verification import VerificationPipeline
from .worker import ParallelOrchestrator, WorkerPool, TaskGraph


# ---------------------------------------------------------------------------
# Global instances
# ---------------------------------------------------------------------------

_intel = IntelligenceEngine()
_capabilities = CapabilityDiscoveryEngine()
_recovery = RecoveryEngine()
_repo_db = RepositoryDatabase()
_context_ranker = ContextRanker(_repo_db)
_semantic_search = SemanticSearch(_repo_db)
_mission_queue = MissionQueue()
_checkpoints = CheckpointManager()
_workspaces = WorkspaceManager()


# ---------------------------------------------------------------------------
# Low-level agent loop
# ---------------------------------------------------------------------------

_TOOL_RESULT_LIMIT = 32000


def _run_agent_loop(
    client,
    model: str,
    system_prompt: str,
    user_prompt: str,
    allowed_tools: list[dict],
    max_iter: int = 30,
    on_tool: Callable | None = None,
    tui_state=None,
    memory=None,
) -> tuple[str, list[dict], dict]:
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": user_prompt})
    files_read: set[str] = set()
    files_modified: set[str] = set()
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0

    for i in range(max_iter):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=allowed_tools or None,
                stream=False,
                temperature=0.2,
            )
        except Exception as e:
            error_msg = f"LLM API error ({type(e).__name__}): {str(e)[:200]}"
            console.print(f"[red]{error_msg}[/]")
            return error_msg, messages, {"prompt_tokens": total_prompt_tokens, "completion_tokens": total_completion_tokens, "total_tokens": total_tokens}

        msg = resp.choices[0].message

        if resp.usage:
            total_prompt_tokens += resp.usage.prompt_tokens or 0
            total_completion_tokens += resp.usage.completion_tokens or 0
            total_tokens += resp.usage.total_tokens or 0
            if tui_state:
                tui_state.tokens_used = total_tokens
                tui_state.prompt_tokens = total_prompt_tokens
                tui_state.completion_tokens = total_completion_tokens
                tui_state.context_percent = min(100.0, (total_tokens / 128000) * 100)

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

            tool_args_list = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                fn_name = tc.function.name
                fp = args.get("path", args.get("file", ""))

                if fn_name == "read_file" and fp:
                    files_read.add(str(Path(fp)))
                    if memory is not None:
                        try:
                            content = Path(fp).read_text(encoding="utf-8", errors="replace")
                            memory.rag.index_text(content, str(fp), "file", {"size": len(content)})
                            memory.sensory.perceive_file(str(fp), content[:4000])
                            memory.working.cache_file(str(fp), content[:8000])
                        except Exception:
                            pass

                if fn_name in ("write_file", "edit_file") and fp:
                    fpath = str(Path(fp))
                    if fpath not in files_read:
                        warning = (
                            f"WARNING: You are modifying '{fp}' without having read it first in this session. "
                            "This is dangerous. You should read the file first to understand its current contents."
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": f"pre-{tc.id}",
                            "content": warning,
                        })
                    files_modified.add(fpath)

                if on_tool:
                    on_tool(fn_name, args)
                tool_args_list.append((tc, fn_name, args, fp))

            def _exec_one(item):
                tc, fn_name, args, fp = item
                t0 = time.time()
                try:
                    result = execute_tool(fn_name, args)
                except Exception as e:
                    result = f"Tool error ({fn_name}): {e}"
                ms = (time.time() - t0) * 1000
                return tc, fn_name, args, fp, result, ms

            max_workers = min(len(tool_args_list), 6)
            results_map = {}
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(_exec_one, item): item for item in tool_args_list}
                for future in as_completed(futures):
                    tc, fn_name, args, fp, result, ms = future.result()
                    results_map[tc.id] = (tc, fn_name, args, fp, result, ms)

            for tc in msg.tool_calls:
                tc_id, fn_name, args, fp, result, ms = results_map[tc.id]
                is_error = str(result).startswith("ERROR") or str(result).startswith("Tool error")
                console.print(f"[dim]  {'\\u2717' if is_error else '\\u2713'} {fn_name}({ms:.0f}ms)[/]")

                if tui_state:
                    tui_state.log_tool_call(fn_name, args, str(result)[:200], ms)

                content = str(result)[:_TOOL_RESULT_LIMIT]
                if len(str(result)) > _TOOL_RESULT_LIMIT:
                    content += f"\n... (truncated, total {len(str(result))} chars). Tip: use grep or a more specific path to narrow results."
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })

                if fn_name in ("write_file", "edit_file") and fp and allowed_tools:
                    auto_read = {
                        "id": f"auto-read-{tc.id}",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": json.dumps({"path": fp})},
                    }
                    read_exists = any(
                        t.get("function", {}).get("name") == "read_file"
                        for t in (allowed_tools if isinstance(allowed_tools, list) else [])
                    )
                    if read_exists:
                        messages.append({
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [auto_read],
                        })
                        try:
                            verify_result = execute_tool("read_file", {"path": fp})
                        except Exception as e:
                            verify_result = f"Auto-read error: {e}"
                        verify_content = str(verify_result)[:_TOOL_RESULT_LIMIT]
                        messages.append({
                            "role": "tool",
                            "tool_call_id": auto_read["id"],
                            "content": verify_content,
                        })
                        files_read.add(str(Path(fp)))
            continue

        final = msg.content or ""
        messages.append({"role": "assistant", "content": final})
        token_info = {"prompt_tokens": total_prompt_tokens, "completion_tokens": total_completion_tokens, "total_tokens": total_tokens}
        return final, messages, token_info

    token_info = {"prompt_tokens": total_prompt_tokens, "completion_tokens": total_completion_tokens, "total_tokens": total_tokens}
    return "(max iterations reached)", messages, token_info


# ---------------------------------------------------------------------------
# v2.0 Orchestrator — mission-driven engineering
# ---------------------------------------------------------------------------

def run_mission_engine(
    client,
    model: str,
    request: str,
    progress: Any = None,
    mission_id: str | None = None,
    priority: MissionPriority = MissionPriority.NORMAL,
    auto_approve: bool = False,
    parallel: bool = False,
    max_workers: int = 4,
) -> Mission:
    """Full mission lifecycle using the formal state machine."""
    # Phase: MISSION_CREATED
    mission = Mission(request, mission_id=mission_id, priority=priority)
    mission.parallel_mode = parallel
    mission.worker_count = max_workers
    _mission_queue.add(mission)

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

    try:
        mission.transition_to(MissionState.DISCOVERY, "Starting mission")
        _update_tui("DISCOVERY")

        # Phase: CAPABILITY_DISCOVERY
        mission.transition_to(MissionState.CAPABILITY_DISCOVERY)
        _update_tui("CAPABILITY_DISCOVERY")
        _log("Discovering capabilities...")
        try:
            capabilities = _capabilities.discover_all()
            mission.capabilities = capabilities
            caps_block = _capabilities.context_block
        except Exception as e:
            _log(f"Capability discovery degraded: {e}")
            caps_block = ""

        # Phase: REPOSITORY_ANALYSIS
        mission.transition_to(MissionState.REPOSITORY_ANALYSIS)
        _update_tui("REPOSITORY_ANALYSIS")
        _log("Analyzing repository...")
        try:
            enriched = _intel.load_all(request)
            mission.context = enriched
        except Exception as e:
            _log(f"Repository analysis degraded: {e}")
            enriched = request

        # Index repository in SQLite DB
        try:
            _repo_db.initialize()
            _repo_db.scan_repository(Path("."))
        except Exception:
            pass

        # Phase: ARCHITECTURE
        mission.transition_to(MissionState.ARCHITECTURE)
        _update_tui("ARCHITECTURE")
        _log("Planning architecture...")
        try:
            architecture_text = _generate_architecture(client, model, request, enriched, caps_block)
            mission.architecture = architecture_text
        except Exception as e:
            _log(f"Architecture phase error: {e}")
            architecture_text = f"Architecture generation failed: {e}"

        # Phase: PLANNING
        mission.transition_to(MissionState.PLANNING)
        _update_tui("PLANNING")
        _log("Creating engineering plan...")
        try:
            plan_text = _generate_plan(client, model, request, architecture_text, enriched, caps_block)
            mission.plan = plan_text
        except Exception as e:
            _log(f"Planning phase error: {e}")
            plan_text = f"Plan generation failed: {e}"

        # Phase: WAITING_APPROVAL
        mission.transition_to(MissionState.WAITING_APPROVAL)
        _update_tui("WAITING_APPROVAL")
        if not auto_approve:
            from rich.prompt import Confirm
            console.print(Panel(Markdown(plan_text), title="Engineering Plan", border_style="green"))
            if not Confirm.ask("\nApprove this plan and start execution?"):
                mission.transition_to(MissionState.CANCELLED, "User cancelled")
                return mission
        _log("Plan approved, starting execution")

        # Phase: EXECUTION
        mission.transition_to(MissionState.EXECUTION)
        _update_tui("EXECUTION")
        try:
            if parallel:
                _log(f"Starting parallel execution with {max_workers} workers...")
                orchestrator = ParallelOrchestrator(max_workers=max_workers)
                exec_result = orchestrator.execute(
                    client, model, plan_text, request, progress=progress,
                )
                mission.files_changed = exec_result.get("files_changed", [])
                mission.tasks = exec_result.get("tasks", [])
                mission.edited_files = set(mission.files_changed)
                _log(f"Parallel execution complete: {exec_result['stats']}")
            else:
                result = _execute_plan(client, model, request, plan_text, mission)
                mission.files_changed = list(mission.edited_files)
        except Exception as e:
            mission.transition_to(MissionState.FAILED, str(e))
            _update_tui("FAILED", str(e))
            return mission

        # Phase: VALIDATION
        mission.transition_to(MissionState.VALIDATION)
        _update_tui("VALIDATION")
        _log("Running verification pipeline...")
        try:
            verifier = VerificationPipeline()
            verifier.discover()
            results = verifier.run(discover=False)
            mission.verification_results = verifier.results_dict
            if progress:
                try:
                    progress.update_from_verification(verifier.results_dict)
                except Exception:
                    pass
        except Exception as e:
            _log(f"Verification error: {e}")
            verifier = None

        if verifier and not verifier.required_passed:
            mission.transition_to(MissionState.RECOVERING, "Verification failed, attempting recovery")
            _update_tui("RECOVERING")
            _log("Verification failed, attempting recovery...")
            recovered = _attempt_recovery(client, model, verifier, mission)
            if not recovered:
                mission.transition_to(MissionState.FAILED, "Verification failed, recovery unsuccessful")
                _update_tui("FAILED", "recovery failed")
                return mission
            # Re-verify after recovery
            try:
                verifier.reset()
                verifier.discover()
                results = verifier.run(discover=False)
                mission.verification_results = verifier.results_dict
            except Exception:
                pass

        # Phase: SECURITY_REVIEW
        mission.transition_to(MissionState.SECURITY_REVIEW)
        _update_tui("SECURITY_REVIEW")
        _log("Running security review...")
        try:
            security_ok, security_text = _security_review(client, model, mission)
            if not security_ok:
                _log(f"Security issues found: {security_text[:200]}")
            if progress:
                try:
                    progress.confidence.set("Security", 0.90 if security_ok else 0.30)
                except Exception:
                    pass
        except Exception as e:
            _log(f"Security review error: {e}")

        # Phase: DOCUMENTATION
        mission.transition_to(MissionState.DOCUMENTATION)
        _update_tui("DOCUMENTATION")
        _log("Updating documentation...")
        _update_documentation(client, model, request, mission)
        if progress:
            try:
                progress.confidence.set("Documentation", 0.70 if mission.edited_files else 0.0)
            except Exception:
                pass

        # Phase: REFLECTION
        mission.transition_to(MissionState.REFLECTION)
        _update_tui("REFLECTION")
        _log("Reflecting on mission...")
        try:
            _intel.after_mission(client, model, request, mission.tasks, mission.edited_files)
        except Exception as e:
            _log(f"Reflection error: {e}")

        # Phase: MISSION_COMPLETE
        mission.transition_to(MissionState.MISSION_COMPLETE)
        _update_tui("MISSION_COMPLETE")

        # Save checkpoint
        try:
            _checkpoints.save(mission.snapshot())
        except Exception:
            pass

        _log(f"[green]Mission complete: {mission.summary()}[/]")

    except Exception as e:
        mission.transition_to(MissionState.FAILED, f"Unexpected error: {type(e).__name__}: {str(e)[:200]}")
        console.print(f"[red]Mission crashed: {type(e).__name__}: {e}[/]")

    return mission


def _generate_architecture(
    client, model: str, request: str, context: str, caps_block: str
) -> str:
    """Generate architecture design for the request."""
    planner_spec = get_agent("architecture agent") or get_agent("mission planner")
    system = planner_spec.system_prompt if planner_spec else "You are an architecture agent."

    prompt = (
        f"{caps_block}\n\n"
        f"## Repository Context\n{context[:15000]}\n\n"
        f"## Request\n{request}\n\n"
        "Design the architecture for implementing this request. Consider:\n"
        "- How it fits the existing codebase\n"
        "- Component/data flow\n"
        "- Database changes needed\n"
        "- API endpoints\n"
        "- Security considerations\n"
        "Output a clear architecture document."
    )

    text, _, _ = _run_agent_loop(client, model, system, prompt, resolve_tools(["read_file", "list_files", "grep_files"]), max_iter=5)
    return text


def _generate_plan(
    client, model: str, request: str, architecture: str, context: str, caps_block: str
) -> str:
    """Generate a detailed engineering plan."""
    planner = get_agent("mission planner")
    system = planner.system_prompt if planner else "You are a mission planner."

    prompt = (
        f"{caps_block}\n\n"
        f"## Architecture\n{architecture[:5000]}\n\n"
        f"## Repository Context\n{context[:10000]}\n\n"
        f"## Request\n{request}\n\n"
        "Produce a detailed implementation plan with:\n"
        "- Ordered tasks with dependencies\n"
        "- Agent assignment per task\n"
        "- Files to create/modify\n"
        "- Verification steps\n"
        "- A 'Risks' section"
    )

    text, _, _ = _run_agent_loop(client, model, system, prompt, resolve_tools(["read_file", "list_files", "grep_files"]), max_iter=5)
    return text


def _execute_plan(client, model: str, request: str, plan_text: str, mission: Mission) -> str:
    """Execute the plan step by step with error tracking."""
    builder = get_agent("builder")
    system = builder.system_prompt if builder else "You are a coding agent."
    tools = resolve_tools(builder.allowed_tools) if builder else TOOL_SCHEMAS

    messages = [{"role": "system", "content": f"{system}\n\n## Plan\n{plan_text}\n\nExecute this plan step by step."}]
    messages.append({"role": "user", "content": request})

    error_counts: dict[str, int] = {}
    files_successfully_written: set[str] = set()

    def _on_tool(name, args):
        if name in ("write_file", "edit_file"):
            fp = args.get("path", "")
            if fp:
                mission.edited_files.add(fp)
        if name == "run_shell":
            cmd = args.get("command", "")
            if "error" in cmd.lower() or "fail" in cmd.lower():
                error_counts[cmd[:50]] = error_counts.get(cmd[:50], 0) + 1

    original_on_tool = _on_tool

    def _on_tool_with_learning(name, args):
        original_on_tool(name, args)
        if name in ("write_file", "edit_file"):
            fp = args.get("path", "")
            if fp:
                files_successfully_written.add(fp)
        total_errors = sum(error_counts.values())
        if total_errors > 5:
            for cmd, count in list(error_counts.items()):
                if count >= 3:
                    messages.append({
                        "role": "system",
                        "content": (
                            f"PATTERN DETECTED: The command '{cmd}' has failed {count} times. "
                            "Try a completely different approach. Read the error output carefully."
                        ),
                    })
                    error_counts.clear()
                    break

    final_text, _, _ = _run_agent_loop(
        client, model, system,
        f"## Plan\n{plan_text}\n\n## Request\n{request}",
        tools, max_iter=50, on_tool=_on_tool_with_learning,
    )
    return final_text


def _attempt_recovery(client, model: str, verifier: VerificationPipeline, mission: Mission) -> bool:
    """Attempt recovery from verification failures."""
    for result in verifier._results:
        if not result.passed and result.required:
            record = _recovery.record_failure(
                error_message=result.message,
                context=f"Verification step: {result.step}",
            )
            strategies = _recovery.suggest_strategies(record)
            for strategy in strategies[:2]:
                console.print(f"[yellow]Recovery: {strategy.name} — {strategy.description}[/]")
                # Try to fix via the builder agent
                builder = get_agent("builder")
                if builder:
                    fix_prompt = (
                        f"## Verification Failure\nStep: {result.step}\nError: {result.message[:500]}\n\n"
                        f"## Recovery Strategy\n{strategy.action}\n\nFix the issue."
                    )
                    try:
                        _, _, _ = _run_agent_loop(
                            client, model,
                            builder.system_prompt,
                            fix_prompt,
                            resolve_tools(builder.allowed_tools),
                            max_iter=10,
                        )
                    except Exception:
                        continue
        _recovery.mark_strategy_used(result)
    # Re-verify
    try:
        verifier.reset()
        verifier.discover()
        verifier.run(discover=False)
        return verifier.required_passed
    except Exception:
        return False


def _security_review(client, model: str, mission: Mission) -> tuple[bool, str]:
    """Run security review on changed files."""
    security = get_agent("security engineer")
    if not security:
        return True, "no security engineer configured"

    if not mission.edited_files:
        return True, "no files changed"

    file_contents = []
    for fp in list(mission.edited_files)[:10]:
        try:
            text = Path(fp).read_text(encoding="utf-8", errors="replace")
            file_contents.append(f"### {fp}\n```\n{text[:8000]}\n```")
        except Exception:
            file_contents.append(f"### {fp}\n(Unable to read file)")

    prompt = (
        "Review these changed files for security vulnerabilities.\n\n"
        "You MUST read each file below. The contents are provided for your review:\n\n"
        + "\n\n".join(file_contents)
        + "\n\nCheck for: hardcoded secrets, SQL injection, XSS, CSRF, insecure deserialization."
        + "\nIf no issues, say 'SECURE'."
        + "\nIf issues found, list them with file:line references and severity."
    )

    text, _, _ = _run_agent_loop(
        client, model, security.system_prompt, prompt,
        resolve_tools(security.allowed_tools), max_iter=10,
    )
    approved = "SECURE" in text
    return approved, text


def _update_documentation(client, model: str, request: str, mission: Mission) -> None:
    """Update documentation after mission completion."""
    doc_agent = get_agent("documentation engineer")
    if not doc_agent:
        return
    if not mission.edited_files:
        return

    file_contents = []
    for fp in list(mission.edited_files)[:10]:
        try:
            text = Path(fp).read_text(encoding="utf-8", errors="replace")
            file_contents.append(f"### {fp}\n```\n{text[:8000]}\n```")
        except Exception:
            file_contents.append(f"### {fp}\n(Unable to read file)")

    prompt = (
        f"## Request\n{request}\n\n"
        f"## Changed Files (contents included for documentation)\n\n"
        + "\n\n".join(file_contents)
        + "\n\nGenerate documentation updates for these changes."
    )

    try:
        _run_agent_loop(
            client, model, doc_agent.system_prompt, prompt,
            resolve_tools(doc_agent.allowed_tools), max_iter=5,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Backward-compatible wrappers
# ---------------------------------------------------------------------------

def _build_chat_context(prompt: str, context_block: str = "", memory=None) -> str:
    """Build enriched context for a chat message by combining intelligence context,
    ranked files/symbols, semantic search results, and per-message RAG retrieval."""
    parts = []
    if context_block:
        parts.append(context_block)

    if memory is not None:
        try:
            rag_ctx = memory.rag.context_block(query=prompt, max_chunks=4, chars_per_chunk=600)
            if rag_ctx:
                parts.append("## Retrieved from Vector Memory (RAG)\n" + rag_ctx)
        except Exception:
            pass
        try:
            epi_ctx = memory.episodic.context_block(query=prompt, max_episodes=2)
            if epi_ctx:
                parts.append(epi_ctx)
        except Exception:
            pass
        try:
            sem_ctx = memory.semantic.context_block(query=prompt, max_facts=6)
            if sem_ctx:
                parts.append(sem_ctx)
        except Exception:
            pass

    try:
        ranked = _context_ranker.rank_context(prompt)
        if ranked and len(ranked) > 50:
            parts.append(ranked)
    except Exception:
        pass

    try:
        search_results = _semantic_search.search(prompt, top_k=5)
        if search_results:
            lines = ["## Auto-discovered relevant code"]
            for r in search_results:
                score = r.get("score", 0)
                path = r.get("path", "")
                snippet = r.get("snippet", "")[:300]
                lines.append(f"  [{score:.2f}] {path}")
                if snippet:
                    lines.append(f"  ```\n{snippet}\n```")
            parts.append("\n".join(lines))
    except Exception:
        pass

    try:
        _repo_db.initialize()
        keywords = [w for w in prompt.lower().split() if len(w) > 3]
        db_symbols = []
        for kw in keywords[:3]:
            syms = _repo_db.query_symbols(kw)
            db_symbols.extend(syms[:5])
        if db_symbols:
            seen = set()
            sym_lines = ["## Relevant symbols in codebase"]
            for s in db_symbols:
                key = f"{s['name']}:{s['path']}"
                if key not in seen:
                    seen.add(key)
                    sym_lines.append(f"  - {s['name']} ({s['symbol_type']}) — {s['path']}")
            if len(sym_lines) > 1:
                parts.append("\n".join(sym_lines))
    except Exception:
        pass

    return "\n\n".join(parts)


def run_agent(client, model: str, prompt: str, messages: list | None = None, max_iter: int = 30, tui_state=None, context_block: str = "", memory=None) -> list:
    """Simple chat loop (backward compatible)."""
    if tui_state and memory is not None:
        try:
            tui_state.vector_chunks = len(memory.rag._chunks)
        except Exception:
            pass
    agent_spec = get_agent("builder")
    from .prompts import SYSTEM_PROMPT
    system = agent_spec.system_prompt if agent_spec else SYSTEM_PROMPT
    tools = resolve_tools(agent_spec.allowed_tools) if agent_spec else TOOL_SCHEMAS

    if messages is None:
        system_content = system
        if context_block:
            system_content = f"{system}\n\n--- Project Context (auto-loaded) ---\n{context_block}\n--- End Context ---"
        now = datetime.now()
        system_content += (
            f"\n\n[Runtime] Current time: {now.strftime('%Y-%m-%d %H:%M')}. "
            f"Session started: {now.strftime('%H:%M')}. "
            "You have file read, write, edit, list, grep, shell, and web_fetch tools."
        )
        messages = [{"role": "system", "content": system_content}]

    enriched = _build_chat_context(prompt, context_block, memory)
    user_content = prompt
    if enriched and len(enriched) > len(prompt) + 50:
        user_content = f"{enriched}\n\n## User Request\n{prompt}"
    messages.append({"role": "user", "content": user_content})

    files_read: set[str] = set()
    files_modified: set[str] = set()
    error_count = 0

    for i in range(max_iter):
        if i > 0 and i % 10 == 0:
            try:
                runtime_msg = (
                    f"[Runtime update — iteration {i}] "
                    f"Files read: {len(files_read)}, modified: {len(files_modified)}, errors: {error_count}. "
                    f"Time: {datetime.now().strftime('%H:%M:%S')}. "
                    "Stay focused on the task. Read files before editing."
                )
                messages.insert(1, {"role": "system", "content": runtime_msg})
                if len(messages) > 50:
                    messages = messages[:2] + messages[-48:]
            except Exception:
                pass

        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, tools=tools or None,
                stream=False, temperature=0.2,
            )
        except Exception as e:
            error_msg = f"LLM error ({type(e).__name__}): {str(e)[:200]}"
            if tui_state:
                tui_state.add_diagnostic(error_msg)
            console.print(f"[red]{error_msg}[/]")
            return messages

        if resp.usage and tui_state:
            tui_state.prompt_tokens += resp.usage.prompt_tokens or 0
            tui_state.completion_tokens += resp.usage.completion_tokens or 0
            tui_state.tokens_used = tui_state.prompt_tokens + tui_state.completion_tokens
            tui_state.context_percent = min(100.0, (tui_state.tokens_used / 128000) * 100)

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

            tool_args_list = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                fn_name = tc.function.name
                fp = args.get("path", args.get("file", ""))

                if tui_state:
                    tui_state.add_activity(f"> {fn_name}({json.dumps(args)[:200]})")
                else:
                    console.print(f"[dim]> {fn_name}({json.dumps(args)[:200]})[/]")

                if fn_name == "read_file" and fp:
                    files_read.add(str(Path(fp)))
                    if memory is not None:
                        try:
                            content = Path(fp).read_text(encoding="utf-8", errors="replace")
                            memory.rag.index_text(content, str(fp), "file", {"size": len(content)})
                            memory.sensory.perceive_file(str(fp), content[:4000])
                            memory.working.cache_file(str(fp), content[:8000])
                        except Exception:
                            pass

                if fn_name in ("write_file", "edit_file") and fp:
                    fpath = str(Path(fp))
                    if fpath not in files_read:
                        warning = (
                            f"WARNING: Modifying '{fp}' without reading it first. "
                            "Read the file first to avoid breaking existing code."
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": f"pre-{tc.id}",
                            "content": warning,
                        })
                        if tui_state:
                            tui_state.add_diagnostic(f"WARN: read before write: {fp}")
                    files_modified.add(fpath)
                    try:
                        _intel.working.observe(f"Modified: {fp}")
                    except Exception:
                        pass
                tool_args_list.append((tc, fn_name, args, fp))

            def _exec_one_run(item):
                tc, fn_name, args, fp = item
                t0 = time.time()
                try:
                    result = execute_tool(fn_name, args)
                except Exception as e:
                    result = f"Tool error: {e}"
                ms = (time.time() - t0) * 1000
                return tc, fn_name, args, fp, result, ms

            max_workers = min(len(tool_args_list), 6)
            results_map = {}
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(_exec_one_run, item): item for item in tool_args_list}
                for future in as_completed(futures):
                    tc, fn_name, args, fp, result, ms = future.result()
                    results_map[tc.id] = (tc, fn_name, args, fp, result, ms)

            for tc in msg.tool_calls:
                tc_id, fn_name, args, fp, result, ms = results_map[tc.id]
                is_error = str(result).startswith("ERROR") or str(result).startswith("Tool error")
                if is_error:
                    error_count += 1
                    try:
                        record = _recovery.record_failure(
                            error_message=str(result),
                            context=f"Tool: {fn_name}, args: {json.dumps(args)[:200]}",
                        )
                        strategies = _recovery.suggest_strategies(record)
                        if strategies:
                            hint = f"Recovery suggestion: {strategies[0].name} - {strategies[0].description}"
                            result += f"\n{hint}"
                            if tui_state:
                                tui_state.add_diagnostic(hint)
                    except Exception:
                        pass

                content = str(result)[:_TOOL_RESULT_LIMIT]
                if len(str(result)) > _TOOL_RESULT_LIMIT:
                    content += f"\n... (truncated, total {len(str(result))} chars). Tip: use grep or a more specific path to narrow results."
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

                if memory is not None:
                    try:
                        memory.working.record_tool_output(fn_name, args, content, success=not is_error)
                        if is_error:
                            memory.working.current_errors.append(f"{fn_name}: {result[:200]}")
                        if fn_name == "grep_files" and "pattern" in args:
                            memory.working.record_search(args["pattern"], [r for r in str(result).split("\n") if r.strip()][:10])
                        if fn_name in ("web_fetch", "api_call"):
                            memory.working.record_retrieved(str(args.get("url", args.get("endpoint", "?"))), fn_name, str(result)[:2000])
                    except Exception:
                        pass

                if tui_state:
                    tui_state.log_tool_call(fn_name, args, content, ms)

                if fn_name in ("write_file", "edit_file") and fp and tools:
                    has_read = any(
                        t.get("function", {}).get("name") == "read_file"
                        for t in tools
                    )
                    if has_read:
                        auto_read_id = f"auto-read-{tc.id}"
                        messages.append({
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [{
                                "id": auto_read_id,
                                "type": "function",
                                "function": {"name": "read_file", "arguments": json.dumps({"path": fp})},
                            }],
                        })
                        try:
                            verify_result = execute_tool("read_file", {"path": fp})
                        except Exception as e:
                            verify_result = f"Auto-read error: {e}"
                        messages.append({
                            "role": "tool",
                            "tool_call_id": auto_read_id,
                            "content": str(verify_result)[:_TOOL_RESULT_LIMIT],
                        })
                        files_read.add(str(Path(fp)))
            continue

        try:
            stream = client.chat.completions.create(
                model=model,
                messages=messages + [{"role": "assistant", "content": msg.content}],
                stream=True, temperature=0.2,
            )
        except Exception as e:
            if tui_state:
                tui_state.add_diagnostic(f"Stream error: {e}")
            console.print(f"[red]Stream error: {e}[/]")
            return messages

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

        if files_modified:
            try:
                _intel.working.open_files = list(files_modified)
                _intel.working.current_task = prompt[:200]
            except Exception:
                pass

        return messages

    if tui_state:
        tui_state.add_activity("[yellow]Reached max iterations.[/]")
    else:
        console.print("[yellow]Reached max iterations.[/]")
    return messages


def plan(client, model: str, request: str, context: str) -> list:
    """Generate a plan (backward compatible)."""
    planner_spec = get_agent("mission planner") or get_agent("planner")
    from .prompts import SYSTEM_PROMPT
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
    from .prompts import SYSTEM_PROMPT, BUILDER_PROMPT
    system = agent_spec.system_prompt if agent_spec else BUILDER_PROMPT
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
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)[:_TOOL_RESULT_LIMIT]})

    console.print("[yellow]Builder reached max iterations.[/]")
    return messages


def orchestrator_build(client, model: str, request: str, progress) -> Any:
    """Legacy orchestrator — delegates to run_mission_engine."""
    return run_mission_engine(client, model, request, progress=progress, auto_approve=True)


# v2.0 verify command
def verify_repository(root: str = ".") -> dict:
    """Run verification on the entire repository."""
    pipeline = VerificationPipeline(root)
    pipeline.discover()
    results = pipeline.run(discover=False)
    return {
        "all_passed": pipeline.all_passed,
        "results": pipeline.results_dict,
        "summary": pipeline.summary,
    }


# v2.0 search command
def search_repository(query: str, top_k: int = 15) -> list[dict]:
    """Semantic search across the repository."""
    return _semantic_search.search(query, top_k=top_k)
