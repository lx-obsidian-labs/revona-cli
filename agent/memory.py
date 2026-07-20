from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from . import AGENT_DIR
from .repo_db import RepositoryDatabase
from .repo_intel import ProjectBrain
from .skills import KnowledgeEngine

USER_DIR = Path.home() / ".config" / "revona" / "user"
USER_PROFILE_PATH = USER_DIR / "profile.json"
PROJECT_MEMORY_DIR = Path("AI")
EXPERIENCES_DIR = AGENT_DIR / "experiences"
KGRAPH_PATH = AGENT_DIR / "knowledge_graph.json"


# ---------------------------------------------------------------------------
# Layer 1 — Working Memory
# ---------------------------------------------------------------------------

class WorkingMemory:
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


# ---------------------------------------------------------------------------
# Layer 2 — Project Memory
# ---------------------------------------------------------------------------

PROJECT_MEMORY_FILES = [
    "Architecture.md", "Coding Standards.md", "Lessons.md",
    "Decisions.md", "Roadmap.md", "Bugs.md", "API Index.md",
]


def load_project_memory() -> dict[str, str]:
    result = {}
    for name in PROJECT_MEMORY_FILES:
        path = PROJECT_MEMORY_DIR / name
        if path.exists():
            result[name] = path.read_text(encoding="utf-8", errors="replace")
    return result


def append_lesson(content: str) -> None:
    path = PROJECT_MEMORY_DIR / "Lessons.md"
    path.parent.mkdir(parents=True, exist_ok=True)
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


# ---------------------------------------------------------------------------
# Layer 3 — User Profile
# ---------------------------------------------------------------------------

def load_user_profile() -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Layer 4 — Experience Memory
# ---------------------------------------------------------------------------

@dataclass
class Experience:
    id: str
    problem: str
    root_cause: str
    solution: str
    files_changed: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    score: float = 1.0
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


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------

@dataclass
class KNode:
    id: str
    label: str
    type: str
    attrs: dict = field(default_factory=dict)


@dataclass
class KEdge:
    source: str
    target: str
    relation: str


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


# ---------------------------------------------------------------------------
# Reflection (v2.0 enhanced)
# ---------------------------------------------------------------------------

def reflect_on_mission(
    client, model: str, request: str, tasks: list, edited_files: set[str], observations: list[str], max_iter: int = 8
) -> dict:
    from .agent import _run_agent_loop
    from .agents import get_agent, resolve_tools

    learner = get_agent("reflection agent") or get_agent("learner")
    if not learner:
        return {"lesson": "", "quality": "", "decisions": []}

    prompt = (
        f"## Request\n{request}\n\n"
        f"## Files Changed\n{json.dumps(list(edited_files))}\n\n"
        f"## Observations\n{chr(10).join(observations[-20:])}\n\n"
        "Reflect on this mission. Output a JSON object with:\n"
        '- "lesson": a concise, reusable lesson\n'
        '- "quality": "excellent" | "good" | "mediocre" | "bad"\n'
        '- "security_issues": list of concerns\n'
        '- "suggestions": list of improvements\n'
        '- "verified_solution": description or ""\n'
        '- "engineering_score": number 0-100\n'
        "Output ONLY the JSON."
    )

    text, _ = _run_agent_loop(
        client, model, learner.system_prompt, prompt,
        resolve_tools(learner.allowed_tools), max_iter=max_iter,
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


# ---------------------------------------------------------------------------
# Intelligence Engine (v2.0)
# ---------------------------------------------------------------------------

class IntelligenceEngine:
    def __init__(self):
        self.working = WorkingMemory()
        self.project_memory: dict[str, str] = {}
        self.experiences = ExperienceDB()
        self.knowledge_graph = KnowledgeGraph()
        self.knowledge = KnowledgeEngine()
        self.brain = ProjectBrain()
        self.repo_db = RepositoryDatabase()
        self._user_profile: dict = {}

    def load_all(self, request: str = "", repo_root: Path | None = None) -> str:
        self.project_memory = load_project_memory()
        self._user_profile = load_user_profile()
        self.knowledge.load_all()
        self.brain.load(repo_root)
        return self._build_context(request)

    def _build_context(self, request: str = "") -> str:
        parts = []

        up = user_context_block()
        if up:
            parts.append(up)

        for name, content in self.project_memory.items():
            if content.strip() and name not in ("Lessons.md", "Bugs.md", "API Index.md"):
                parts.append(f"## {name.replace('.md', '')}\n{content.strip()[:2000]}")

        lessons = self.project_memory.get("Lessons.md", "")
        if lessons.strip():
            lines = [l for l in lessons.split("\n") if l.strip().startswith("-")]
            if lines:
                parts.append("## Recent Lessons\n" + "\n".join(lines[-10:]))

        top_nodes = list(self.knowledge_graph.nodes.values())[:20]
        if top_nodes:
            parts.append("## Knowledge Graph\n" + "\n".join(f"- {n.label} ({n.type})" for n in top_nodes))

        brain_ctx = self.brain.context_block()
        if brain_ctx:
            parts.append(brain_ctx)

        if request:
            skill_ctx = self.knowledge.get_context_for(request)
            if skill_ctx:
                parts.append("## Relevant Knowledge\n" + skill_ctx)

        return "\n".join(parts)

    def after_mission(self, client, model: str, request: str, tasks: list, edited_files: set[str]) -> None:
        """Knowledge evolution: Observe → Extract → Update → Rank → Store."""
        observations = self.working.observations[:]

        reflection = reflect_on_mission(client, model, request, tasks, edited_files, observations)

        lesson = reflection.get("lesson", "")
        if lesson:
            append_lesson(lesson)
            self.knowledge_graph.nodes[f"lesson-{int(time.time())}"] = KNode(
                id=f"lesson-{int(time.time())}",
                label=lesson[:80],
                type="lesson",
                attrs={"text": lesson},
            )
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
