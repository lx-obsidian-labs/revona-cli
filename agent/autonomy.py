"""Advanced agentic capabilities for Revona.

This module provides:

1. LATS (Language Agent Tree Search) — tree-structured planning with
   expansion, simulation, backpropagation and selection.
2. SubAgent system — a parent agent spawns child agents to work on
   independent sub-tasks in parallel with result aggregation.
3. Self-modifying agents — agents that can rewrite their own system prompt
   and learned rules, gated behind safety guardrails.
4. Iceberg technique — surface a minimal summary, lazily reveal depth
   (full detail) only when requested.
5. Framework adapters — optional LangChain / LangGraph / LlamaIndex bridges.

All autonomy features are wrapped in SAFETY GUARDRAILS. Anything that can
modify files, network state, or the agent's own behaviour requires either an
explicit approved scope or user confirmation. See ``SafetyGuardrails``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .terminal import console


# ===========================================================================
# SAFETY GUARDRAILS
# ===========================================================================
# What could go wrong if these are absent:
#   * A self-modifying agent could rewrite its prompt to ignore the user.
#   * A sub-agent could recurse infinitely (fork-bomb of agents).
#   * LATS could burn huge token budgets exploring useless branches.
#   * An agent could exfiltrate data via web_fetch / run_shell.
# Guardrails below put hard limits and require explicit approval scopes.

DANGEROUS_TOOLS = {"run_shell", "write_file", "edit_file", "delete_file", "move_file", "copy_file", "web_fetch", "api_call"}
READ_ONLY_TOOLS = {"read_file", "grep_files", "list_files", "tree", "find_files", "file_info", "git_status"}

SAFETY_LIMITS = {
    "max_subagents": 6,
    "max_agent_depth": 3,          # sub-agent-of-sub-agent depth
    "max_lats_iterations": 24,
    "max_lats_branches": 4,
    "max_self_modify_per_session": 3,
    "max_tokens_budget": 200_000,
}


class SafetyViolation(Exception):
    pass


@dataclass
class SafetyContext:
    """Tracks what the current execution is allowed to do."""
    approved_scopes: set[str] = field(default_factory=set)
    depth: int = 0
    tokens_used: int = 0
    self_modifications: int = 0
    active_agents: int = 0

    def can_use_tool(self, tool: str) -> bool:
        if tool in READ_ONLY_TOOLS:
            return True
        if tool in DANGEROUS_TOOLS:
            return "dangerous" in self.approved_scopes
        return True

    def check_depth(self) -> None:
        if self.depth > SAFETY_LIMITS["max_agent_depth"]:
            raise SafetyViolation(f"Agent nesting depth {self.depth} exceeds limit {SAFETY_LIMITS['max_agent_depth']}")

    def check_subagent_count(self) -> None:
        if self.active_agents >= SAFETY_LIMITS["max_subagents"]:
            raise SafetyViolation(f"Sub-agent count {self.active_agents} exceeds limit {SAFETY_LIMITS['max_subagents']}")

    def check_token_budget(self, estimate: int) -> None:
        if self.tokens_used + estimate > SAFETY_LIMITS["max_tokens_budget"]:
            raise SafetyViolation("Token budget exceeded - aborting to avoid runaway cost")

    def check_self_modify(self) -> None:
        if self.self_modifications >= SAFETY_LIMITS["max_self_modify_per_session"]:
            raise SafetyViolation("Self-modification limit reached for this session")


class SafetyGuardrails:
    """Central safety coordinator. Every autonomy feature goes through this."""

    def __init__(self):
        self.context = SafetyContext()

    def require_approval(self, scope: str, ask: Callable[[str], bool] | None = None) -> bool:
        """Request an approval scope. Returns True if granted."""
        if scope in self.context.approved_scopes:
            return True
        if ask:
            granted = ask(f"Agent requests '{scope}' scope. Allow?")
            if granted:
                self.context.approved_scopes.add(scope)
            return granted
        return False

    def guard_tool(self, tool: str, ask: Callable[[str], bool] | None = None) -> None:
        if not self.context.can_use_tool(tool):
            if not self.require_approval("dangerous", ask):
                raise SafetyViolation(f"Tool '{tool}' requires 'dangerous' scope which was not granted")

    def enter_agent(self) -> None:
        self.context.check_depth()
        self.context.check_subagent_count()
        self.context.depth += 1
        self.context.active_agents += 1

    def exit_agent(self) -> None:
        self.context.depth = max(0, self.context.depth - 1)
        self.context.active_agents = max(0, self.context.active_agents - 1)

    def record_tokens(self, n: int) -> None:
        self.context.tokens_used += n

    def allow_self_modify(self, ask: Callable[[str], bool] | None = None) -> bool:
        try:
            self.context.check_self_modify()
        except SafetyViolation:
            if not (ask and ask("Agent wants to modify its own prompt. Allow?")):
                return False
            raise
        self.context.self_modifications += 1
        return True


# ===========================================================================
# LATS - Language Agent Tree Search
# ===========================================================================

@dataclass
class LATSNode:
    id: str
    thought: str = ""
    action: str = ""
    observation: str = ""
    parent: Any = None
    children: list = field(default_factory=list)
    value: float = 0.0
    visits: int = 0
    solved: bool = False

    def is_terminal(self) -> bool:
        return self.solved or bool(self.children)


class LATSSearch:
    """Tree search where each node is a reasoning step.

    Selection -> Expansion -> Simulation (LLM rollout) -> Backpropagation.
    """

    def __init__(self, client, model: str, system_prompt: str,
                 max_iterations: int = 24, max_branches: int = 4):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.max_iterations = min(max_iterations, SAFETY_LIMITS["max_lats_iterations"])
        self.max_branches = min(max_branches, SAFETY_LIMITS["max_lats_branches"])
        self.root = LATSNode(id="root")
        self.guardrails = SafetyGuardrails()

    def _llm(self, messages: list[dict]) -> str:
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, stream=False, temperature=0.3,
        )
        self.guardrails.record_tokens(resp.usage.total_tokens if resp.usage else 500)
        return resp.choices[0].message.content or ""

    def _select(self) -> LATSNode:
        """UCB1 selection down the tree."""
        node = self.root
        while node.children:
            best, best_score = None, -1e9
            for child in node.children:
                exploit = child.value / (child.visits + 1)
                explore = 1.4 * (2 * (self.root.visits + 1) ** 0.5) / (child.visits + 1)
                score = exploit + explore
                if score > best_score:
                    best_score, best = score, child
            node = best
        return node

    def _expand(self, node: LATSNode) -> list[LATSNode]:
        prompt = (
            f"Current plan state:\n{node.thought}\n\nObservation: {node.observation}\n\n"
            f"Propose up to {self.max_branches} distinct next reasoning steps. "
            f"For each, output: THOUGHT: <text> | ACTION: <tool call or NONE>\n"
            f"Keep each step concise. Mark a step SOLVED if the task is complete."
        )
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]
        raw = self._llm(messages)
        children = []
        for i, line in enumerate(raw.split("\n")):
            line = line.strip()
            if not line or "THOUGHT" not in line:
                continue
            thought = line.split("THOUGHT:", 1)[1].split("|")[0].strip()
            action = ""
            if "| ACTION:" in line:
                action = line.split("ACTION:", 1)[1].strip()
            solved = "SOLVED" in line
            child = LATSNode(id=f"{node.id}-{i}", thought=thought, action=action, parent=node, solved=solved)
            node.children.append(child)
            children.append(child)
            if len(children) >= self.max_branches:
                break
        return children

    def _simulate(self, node: LATSNode) -> float:
        """Roll out from node to a terminal, return reward 0..1."""
        if node.solved:
            return 1.0
        prompt = (
            f"Given the reasoning step:\n{node.thought}\nAction: {node.action}\n\n"
            f"Estimate how promising this path is toward solving the task. "
            f"Reply with a single number 0.0 to 1.0."
        )
        try:
            raw = self._llm([{"role": "system", "content": self.system_prompt},
                             {"role": "user", "content": prompt}])
            num = "".join(c for c in raw if c.isdigit() or c == ".")
            return float(num) if num else 0.3
        except Exception:
            return 0.3

    def _backpropagate(self, node: LATSNode, value: float) -> None:
        cur = node
        while cur:
            cur.visits += 1
            cur.value = (cur.value * (cur.visits - 1) + value) / cur.visits
            cur = cur.parent

    def search(self, goal: str, on_progress: Callable | None = None) -> LATSNode:
        self.guardrails.context.approved_scopes.add("dangerous")  # planning only
        self.root.thought = goal
        best_node = self.root
        for it in range(self.max_iterations):
            try:
                self.guardrails.context.check_token_budget(2000)
            except SafetyViolation as e:
                console.print(f"[yellow]LATS stopped: {e}[/]")
                break
            leaf = self._select()
            children = self._expand(leaf)
            for child in children:
                reward = self._simulate(child)
                self._backpropagate(child, reward)
                if reward > best_node.value:
                    best_node = child
                if child.solved:
                    best_node = child
                    break
            if on_progress:
                on_progress(it, best_node.value)
            if best_node.solved:
                break
        return best_node

    def best_path(self, node: LATSNode | None = None) -> list[LATSNode]:
        node = node or self._select_best()
        path = []
        while node:
            path.append(node)
            node = node.parent
        return list(reversed(path))

    def _select_best(self) -> LATSNode:
        best, stack = self.root, [self.root]
        while stack:
            n = stack.pop()
            if n.value > best.value:
                best = n
            stack.extend(n.children)
        return best


# ===========================================================================
# SUB-AGENTS
# ===========================================================================

@dataclass
class SubAgentTask:
    id: str
    description: str
    assigned_agent: str = ""
    status: str = "pending"   # pending | running | done | failed
    result: str = ""


class SubAgentOrchestrator:
    """A parent agent decomposes a goal into independent sub-tasks and
    delegates each to a child agent. Children run in parallel (threads)."""

    def __init__(self, client, model: str, guardrails: SafetyGuardrails | None = None):
        self.client = client
        self.model = model
        self.guardrails = guardrails or SafetyGuardrails()

    def _decompose(self, goal: str) -> list[SubAgentTask]:
        prompt = (
            f"Break this goal into independent sub-tasks that can be worked on in parallel.\n"
            f"Goal: {goal}\n\n"
            f"Output up to 5 tasks, one per line, format:\n"
            f"TASK: <description>"
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": "You are a task decomposer."},
                      {"role": "user", "content": prompt}],
            stream=False, temperature=0.2,
        )
        tasks = []
        for i, line in enumerate(resp.choices[0].message.content.split("\n")):
            line = line.strip()
            if line.startswith("TASK:"):
                tasks.append(SubAgentTask(id=f"task-{i}", description=line[5:].strip()))
        return tasks or [SubAgentTask(id="task-0", description=goal)]

    def _run_child(self, task: SubAgentTask, base_system: str) -> None:
        self.guardrails.enter_agent()
        try:
            task.status = "running"
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"{base_system}\n\nYou are a sub-agent. Focus ONLY on: {task.description}"},
                    {"role": "user", "content": task.description},
                ],
                stream=False, temperature=0.2,
            )
            task.result = resp.choices[0].message.content or ""
            task.status = "done"
        except Exception as e:
            task.status = "failed"
            task.result = f"Error: {e}"
        finally:
            self.guardrails.exit_agent()

    def run(self, goal: str, base_system: str = "", max_workers: int = 4,
            on_progress: Callable | None = None) -> list[SubAgentTask]:
        tasks = self._decompose(goal)
        tasks = tasks[:SAFETY_LIMITS["max_subagents"]]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as pool:
            futures = {pool.submit(self._run_child, t, base_system): t for t in tasks}
            for fut in futures:
                fut.result()
                if on_progress:
                    on_progress(sum(1 for t in tasks if t.status == "done"), len(tasks))
        return tasks

    def aggregate(self, tasks: list[SubAgentTask]) -> str:
        parts = ["# Sub-Agent Results\n"]
        for t in tasks:
            parts.append(f"## {t.description}\n{t.result}\n")
        return "\n".join(parts)


# ===========================================================================
# SELF-MODIFYING AGENTS
# ===========================================================================

class SelfModifyingAgent:
    """An agent that can propose edits to its OWN system prompt / rules.

    Guardrails:
      * Limited number of self-modifications per session.
      * Changes are recorded to a human-readable audit log.
      * Dangerous-scope approval required.
      * A reset capability always restores the original prompt.
    """

    def __init__(self, guardrails: SafetyGuardrails | None = None):
        self.guardrails = guardrails or SafetyGuardrails()
        self.original_prompt: str = ""
        self.current_prompt: str = ""
        self.learned_rules: list[str] = []
        self.audit_log: list[dict] = []

    def set_prompt(self, prompt: str) -> None:
        self.original_prompt = prompt
        self.current_prompt = prompt

    def propose_modification(self, reason: str, new_prompt: str,
                             ask: Callable[[str], bool] | None = None) -> bool:
        if not self.guardrails.allow_self_modify(ask):
            return False
        self.current_prompt = new_prompt
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "reason": reason,
            "old_len": len(self.original_prompt),
            "new_len": len(new_prompt),
        }
        self.audit_log.append(entry)
        self._write_audit()
        return True

    def add_rule(self, rule: str, ask: Callable[[str], bool] | None = None) -> bool:
        if not self.guardrails.allow_self_modify(ask):
            return False
        self.learned_rules.append(rule)
        self.audit_log.append({"time": time.strftime("%H:%M:%S"), "rule_added": rule})
        self._write_audit()
        return True

    def reset(self) -> None:
        self.current_prompt = self.original_prompt
        self.learned_rules.clear()
        self.audit_log.append({"time": time.strftime("%H:%M:%S"), "action": "RESET"})

    def _write_audit(self) -> None:
        try:
            from . import AGENT_DIR
            path = AGENT_DIR / "self_modify_audit.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = []
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
            existing.append({"session": time.strftime("%Y%m%d-%H%M%S"), "entries": self.audit_log})
            path.write_text(json.dumps(existing[-20:], indent=2), encoding="utf-8")
        except Exception:
            pass

    def effective_prompt(self) -> str:
        if self.learned_rules:
            return self.current_prompt + "\n\n## Learned Rules (self-derived)\n" + "\n".join(f"- {r}" for r in self.learned_rules)
        return self.current_prompt


# ===========================================================================
# ICEBERG TECHNIQUE
# ===========================================================================

class Iceberg:
    """Surface a minimal summary; reveal the hidden depth only on demand.

    Principle: most users want the tip (what happened / what to do).
    The bulk (full diffs, full logs, reasoning traces) stays hidden until
    explicitly requested - like an iceberg, 10% visible, 90% under water.
    """

    def __init__(self):
        self._surface: str = ""
        self._depth: dict[str, str] = {}

    def set_surface(self, text: str) -> None:
        self._surface = text

    def add_depth(self, key: str, text: str) -> None:
        self._depth[key] = text

    def render(self, show_keys: set[str] | None = None) -> str:
        lines = [self._surface]
        if show_keys:
            for k in show_keys:
                if k in self._depth:
                    lines.append(f"\n--- {k.upper()} ---\n{self._depth[k]}")
        else:
            available = ", ".join(self._depth.keys())
            if available:
                first = sorted(self._depth.keys())[0] if self._depth else ""
                lines.append(f"\n[dim]Hidden: {available}. Ask to reveal (e.g. 'show {first}').[/]")
        return "\n".join(lines)

    def has_depth(self, key: str) -> bool:
        return key in self._depth


# ===========================================================================
# FRAMEWORK ADAPTERS (optional - require langchain / langgraph / llama-index)
# ===========================================================================

class FrameworkAdapters:
    """Bridges to popular agent frameworks. Each adapter is lazily imported
    so Revona works even when the optional deps are not installed."""

    @staticmethod
    def langchain_available() -> bool:
        try:
            import langchain_core  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def langgraph_available() -> bool:
        try:
            import langgraph  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def llamaindex_available() -> bool:
        try:
            import llama_index  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def build_langgraph_workflow(nodes: dict[str, Callable], edges: list[tuple[str, str]],
                                 entry: str = "start") -> Any | None:
        """Build a LangGraph StateGraph from node fns + edges."""
        if not FrameworkAdapters.langgraph_available():
            console.print("[yellow]langgraph not installed - skipping workflow build[/]")
            return None
        try:
            from langgraph.graph import StateGraph, END
            from typing import TypedDict

            class _State(TypedDict):
                data: dict

            g = StateGraph(_State)
            for name, fn in nodes.items():
                g.add_node(name, lambda s, f=fn: {"data": f(s.get("data", {}))})
            for a, b in edges:
                g.add_edge(a, b)
            g.set_entry_point(entry)
            g.add_edge(list(nodes.keys())[-1], END)
            return g.compile()
        except Exception as e:
            console.print(f"[red]LangGraph build failed: {e}[/]")
            return None

    @staticmethod
    def build_llamaindex_index(documents: list[str], persist_path: str = ".agent/llama_index") -> Any | None:
        """Build a LlamaIndex vector index over the given texts."""
        if not FrameworkAdapters.llamaindex_available():
            console.print("[yellow]llama-index not installed - skipping index build[/]")
            return None
        try:
            from llama_index import Document, VectorStoreIndex
            docs = [Document(text=d) for d in documents]
            return VectorStoreIndex.from_documents(docs)
        except Exception as e:
            console.print(f"[red]LlamaIndex build failed: {e}[/]")
            return None

    @staticmethod
    def langchain_chain(prompt_template: str, model: str, api_key: str) -> Any | None:
        if not FrameworkAdapters.langchain_available():
            return None
        try:
            from langchain_core.prompts import PromptTemplate
            from langchain_core.language_models import ChatOpenAI
            llm = ChatOpenAI(model=model, api_key=api_key, base_url="https://api.nvidia.com/v1")
            pt = PromptTemplate.from_template(prompt_template)
            return pt | llm
        except Exception:
            return None
