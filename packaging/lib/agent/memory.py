from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from . import AGENT_DIR
from .repo_intel import ProjectBrain
from .skills import KnowledgeEngine

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

USER_DIR = Path.home() / ".config" / "revona" / "user"
USER_PROFILE_PATH = USER_DIR / "profile.json"
PROJECT_MEMORY_DIR = Path("AI")
EXPERIENCES_DIR = AGENT_DIR / "experiences"
KGRAPH_PATH = AGENT_DIR / "knowledge_graph.json"


# ===================================================================
# Layer 1 — Working Memory (in-process only, not persisted)
# ===================================================================

class WorkingMemory:
    """Ephemeral context for the current task."""

    def __init__(self):
        self.current_task: str = ""
        self.open_files: list[str] = []
        self.current_errors: list[str] = []
        self.current_plan: str = ""
        self.active_symbols: dict[str, str] = {}
        self.observations: list[str] = []

    def observe(self, note: str) -> None:
        self.observations.append(f"[{time.strftime('%H:%M:%S')}] {note}")

    def clear(self) -> None:
        self.__init__()


# ===================================================================
# Layer 2 — Project Memory (AI/*.md files in the repo)
# ===================================================================

PROJECT_MEMORY_FILES = [
    "Architecture.md",
    "Coding Standards.md",
    "Lessons.md",
    "Decisions.md",
    "Roadmap.md",
    "Bugs.md",
    "API Index.md",
]


def load_project_memory() -> dict[str, str]:
    """Read all AI/*.md files. Returns {filename: content}."""
    result = {}
    for name in PROJECT_MEMORY_FILES:
        path = PROJECT_MEMORY_DIR / name
        if path.exists():
            result[name] = path.read_text(encoding="utf-8", errors="replace")
    return result


def append_lesson(content: str) -> None:
    path = PROJECT_MEMORY_DIR / "Lessons.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Lessons Learned\n\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n- {time.strftime('%Y-%m-%d %H:%M')}: {content}\n")


def append_decision(title: str, context: str, decision: str) -> None:
    path = PROJECT_MEMORY_DIR / "Decisions.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"""
## {title}
- **Date:** {time.strftime('%Y-%m-%d %H:%M')}
- **Context:** {context}
- **Decision:** {decision}
""")


# ===================================================================
# Layer 3 — User Memory (~/.config/revona/user/profile.json)
# ===================================================================

def load_user_profile() -> dict[str, Any]:
    """Load the global user profile."""
    if USER_PROFILE_PATH.exists():
        try:
            return json.loads(USER_PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_user_profile(profile: dict) -> None:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")


def user_context_block() -> str:
    """Format user profile as a prompt block."""
    profile = load_user_profile()
    if not profile:
        return ""
    lines = [f"## User Profile ({profile.get('name', 'User')})"]
    stack = profile.get("preferred_stack", {})
    if stack:
        lines.append("### Preferred Stack")
        for k, v in stack.items():
            lines.append(f"- {k}: {v}")
    principles = profile.get("principles", [])
    if principles:
        lines.append("### Principles")
        for p in principles:
            lines.append(f"- {p}")
    return "\n".join(lines)


# ===================================================================
# Layer 4 — Experience Memory (verified solutions DB)
# ===================================================================

@dataclass
class Experience:
    id: str
    problem: str
    root_cause: str
    solution: str
    files_changed: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    score: float = 1.0  # 0.0 - 1.0 confidence
    reliability: float = 1.0
    speed: float = 1.0
    maintainability: float = 1.0
    reuses: int = 0
    successes: int = 0
    failures: int = 0
    created_at: float = 0.0
    last_used: float = 0.0

    def confidence(self) -> float:
        if self.reuses == 0:
            return self.score
        ratio = self.successes / max(self.reuses, 1)
        return self.score * ratio

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = d["created_at"] or time.time()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Experience:
        return cls(**d)


class ExperienceDB:
    """Persistent store of verified solutions."""

    def __init__(self):
        self._experiences: dict[str, Experience] = {}
        self._load()

    def _load(self) -> None:
        EXPERIENCES_DIR.mkdir(parents=True, exist_ok=True)
        for p in EXPERIENCES_DIR.glob("*.json"):
            if p.name == "index.json":
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                exp = Experience.from_dict(data)
                self._experiences[exp.id] = exp
            except Exception:
                pass

    def add(self, exp: Experience) -> None:
        exp.id = exp.id or f"exp-{int(time.time())}-{len(self._experiences)}"
        exp.created_at = exp.created_at or time.time()
        self._experiences[exp.id] = exp
        self._save(exp)

    def _save(self, exp: Experience) -> None:
        path = EXPERIENCES_DIR / f"{exp.id}.json"
        path.write_text(json.dumps(exp.to_dict(), indent=2), encoding="utf-8")

    def search(self, query: str, min_confidence: float = 0.3, top_k: int = 5) -> list[Experience]:
        """Find relevant experiences by keyword match on problem/solution/tags."""
        q = query.lower()
        scored = []
        for exp in self._experiences.values():
            if exp.confidence() < min_confidence:
                continue
            relevance = 0
            if q in exp.problem.lower():
                relevance += 3
            if q in exp.tags:
                relevance += 2
            if q in exp.solution.lower():
                relevance += 1
            if relevance > 0:
                scored.append((relevance * exp.confidence(), exp))
        scored.sort(key=lambda x: -x[0])
        return [s[1] for s in scored[:top_k]]

    def record_result(self, exp_id: str, success: bool) -> None:
        exp = self._experiences.get(exp_id)
        if not exp:
            return
        exp.reuses += 1
        exp.last_used = time.time()
        if success:
            exp.successes += 1
        else:
            exp.failures += 1
        self._save(exp)

    def all(self) -> list[Experience]:
        return list(self._experiences.values())


# ===================================================================
# Knowledge Graph (simple JSON-based)
# ===================================================================

@dataclass
class KNode:
    id: str
    label: str
    type: str  # concept, solution, file, pattern, tool
    attrs: dict = field(default_factory=dict)

@dataclass
class KEdge:
    source: str
    target: str
    relation: str  # relates_to, solves, depends_on, implements

class KnowledgeGraph:
    def __init__(self):
        self.nodes: dict[str, KNode] = {}
        self.edges: list[KEdge] = []
        self._load()

    def _load(self) -> None:
        if KGRAPH_PATH.exists():
            try:
                data = json.loads(KGRAPH_PATH.read_text(encoding="utf-8"))
                for n in data.get("nodes", []):
                    self.nodes[n["id"]] = KNode(**n)
                for e in data.get("edges", []):
                    self.edges.append(KEdge(**e))
            except Exception:
                pass

    def save(self) -> None:
        KGRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [asdict(n) for n in self.nodes.values()],
            "edges": [asdict(e) for e in self.edges],
        }
        KGRAPH_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_node(self, node: KNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: KEdge) -> None:
        self.edges.append(edge)

    def find_related(self, node_id: str, max_depth: int = 2) -> list[KNode]:
        """BFS traversal to find related nodes."""
        related = []
        visited = {node_id}
        queue = [(node_id, 0)]
        while queue:
            current, depth = queue.pop(0)
            if depth > max_depth:
                continue
            for e in self.edges:
                neighbor = None
                if e.source == current and e.target not in visited:
                    neighbor = e.target
                elif e.target == current and e.source not in visited:
                    neighbor = e.source
                if neighbor:
                    visited.add(neighbor)
                    if neighbor in self.nodes:
                        related.append(self.nodes[neighbor])
                    queue.append((neighbor, depth + 1))
        return related

    def query(self, text: str) -> list[KNode]:
        """Full-text search on node labels and attributes."""
        q = text.lower()
        results = []
        for n in self.nodes.values():
            if q in n.label.lower():
                results.append(n)
                continue
            for v in n.attrs.values():
                if isinstance(v, str) and q in v.lower():
                    results.append(n)
                    break
        return results


# ===================================================================
# Adaptive Intelligence Engine
# ===================================================================

def reflect_on_mission(
    client, model: str, request: str, tasks: list, edited_files: set[str], observations: list[str], max_iter: int = 8
) -> dict:
    """Post-mission reflection: extract lessons, rate code, update graph."""
    from .agent import _run_agent_loop
    from .agents import get_agent, resolve_tools

    learner = get_agent("learner")
    if not learner:
        return {"lesson": "", "quality": "", "decisions": []}

    prompt = (
        f"## Request\n{request}\n\n"
        f"## Tasks & Results\n{json.dumps([{'id': t.id, 'label': t.label, 'status': t.status.value, 'error': t.error} for t in tasks], indent=2)}\n\n"
        f"## Files Changed\n{json.dumps(list(edited_files))}\n\n"
        f"## Observations\n{chr(10).join(observations[-20:])}\n\n"
        "Reflect on this mission. Output a JSON object with:\n"
        '- "lesson": a concise, reusable lesson from this work\n'
        '- "quality": "excellent" | "good" | "mediocre" | "bad"\n'
        '- "security_issues": list of any concerns\n'
        '- "suggestions": list of specific improvements\n'
        '- "verified_solution": a description if a recurring problem was solved, or ""\n'
        "Output ONLY the JSON."
    )

    text, _ = _run_agent_loop(
        client, model,
        learner.system_prompt,
        prompt,
        resolve_tools(learner.allowed_tools),
        max_iter=max_iter,
    )
    try:
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except Exception:
        return {"lesson": "", "quality": "unknown", "decisions": []}


class IntelligenceEngine:
    """Ties together all memory layers + knowledge graph + skills + reflection."""

    def __init__(self):
        self.working = WorkingMemory()
        self.project_memory: dict[str, str] = {}
        self.experiences = ExperienceDB()
        self.knowledge_graph = KnowledgeGraph()
        self.knowledge = KnowledgeEngine()
        self.brain = ProjectBrain()
        self._user_profile: dict = {}

    def load_all(self, request: str = "", repo_root: Path | None = None) -> str:
        """Preload all persistent memory. Returns a context block for prompts."""
        self.project_memory = load_project_memory()
        self._user_profile = load_user_profile()
        self.knowledge.load_all()
        self.brain.load(repo_root)
        # experiences and kg are loaded on init
        return self._build_context(request)

    def _build_context(self, request: str = "") -> str:
        parts = []

        # User profile
        up = user_context_block()
        if up:
            parts.append(up)

        # Project memory
        for name, content in self.project_memory.items():
            if content.strip() and name not in ("Lessons.md", "Bugs.md", "API Index.md"):
                parts.append(f"## {name.replace('.md', '')}\n{content.strip()[:2000]}")

        # Recent lessons
        lessons = self.project_memory.get("Lessons.md", "")
        if lessons.strip():
            lines = [l for l in lessons.split("\n") if l.strip().startswith("-")]
            if lines:
                parts.append("## Recent Lessons\n" + "\n".join(lines[-10:]))

        # Knowledge graph context (top concepts)
        top_nodes = list(self.knowledge_graph.nodes.values())[:20]
        if top_nodes:
            parts.append("## Knowledge Graph\n" + "\n".join(f"- {n.label} ({n.type})" for n in top_nodes))

        # Project Brain (repository intelligence)
        brain_ctx = self.brain.context_block()
        if brain_ctx:
            parts.append(brain_ctx)

        # Relevant skills / blueprints / accelerators
        if request:
            skill_ctx = self.knowledge.get_context_for(request)
            if skill_ctx:
                parts.append("## Relevant Knowledge\n" + skill_ctx)

        return "\n".join(parts)

    def after_mission(self, client, model: str, request: str, tasks: list, edited_files: set[str]) -> None:
        """Run the full Observe→Execute→Verify→Reflect→Extract→Update→Rank→Store cycle."""
        observations = self.working.observations[:]

        reflection = reflect_on_mission(client, model, request, tasks, edited_files, observations)

        lesson = reflection.get("lesson", "")
        if lesson:
            append_lesson(lesson)
            # Add to knowledge graph
            self.knowledge_graph.add_node(KNode(
                id=f"lesson-{int(time.time())}",
                label=lesson[:80],
                type="lesson",
                attrs={"text": lesson},
            ))
            self.knowledge_graph.save()

        vs = reflection.get("verified_solution", "")
        if vs:
            exp = Experience(
                id=f"exp-{int(time.time())}",
                problem=request[:200],
                root_cause=vs,
                solution=vs,
                files_changed=list(edited_files),
                tags=[reflection.get("quality", "general")],
                score=0.8 if reflection.get("quality") in ("excellent", "good") else 0.5,
            )
            self.experiences.add(exp)

        decisions = reflection.get("decisions", [])
        for d in decisions:
            if isinstance(d, dict):
                append_decision(d.get("title", "Unnamed"), d.get("context", ""), d.get("decision", ""))

        self.working.clear()
