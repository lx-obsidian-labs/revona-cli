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
LOCAL_USER_PROFILE_PATH = Path(".user") / "profile.json"
PROJECT_MEMORY_DIR = Path("AI")
EXPERIENCES_DIR = AGENT_DIR / "experiences"
KGRAPH_PATH = AGENT_DIR / "knowledge_graph.json"


# ---------------------------------------------------------------------------
# Layer 1 — Working Memory (enhanced)
# ---------------------------------------------------------------------------

class WorkingMemory:
    def __init__(self):
        self.current_task: str = ""
        self.open_files: list[str] = []
        self.current_errors: list[str] = []
        self.current_plan: str = ""
        self.active_symbols: dict[str, str] = {}
        self.observations: list[str] = []
        self.recent_messages: list[dict] = []
        self.file_contents: dict[str, str] = {}
        self.search_results: list[dict] = []
        self.instructions: list[str] = []
        self.tool_outputs: list[dict] = []
        self.retrieved_data: list[dict] = []

    def observe(self, note: str) -> None:
        self.observations.append(f"[{time.strftime('%H:%M:%S')}] {note}")

    def record_message(self, role: str, content: str) -> None:
        self.recent_messages.append({
            "role": role,
            "content": content[:500],
            "time": time.strftime("%H:%M:%S"),
        })
        if len(self.recent_messages) > 30:
            self.recent_messages = self.recent_messages[-30:]

    def cache_file(self, path: str, content: str, max_chars: int = 8000) -> None:
        self.file_contents[path] = content[:max_chars]
        if len(self.file_contents) > 20:
            oldest = list(self.file_contents.keys())[0]
            del self.file_contents[oldest]

    def record_search(self, query: str, results: list[str]) -> None:
        self.search_results.append({
            "query": query,
            "results": results[:10],
            "time": time.strftime("%H:%M:%S"),
        })
        if len(self.search_results) > 15:
            self.search_results = self.search_results[-15:]

    def add_instruction(self, instruction: str) -> None:
        self.instructions.append(f"[{time.strftime('%H:%M:%S')}] {instruction}")
        if len(self.instructions) > 20:
            self.instructions = self.instructions[-20:]

    def record_tool_output(self, tool: str, args: dict, output: str, success: bool = True) -> None:
        self.tool_outputs.append({
            "tool": tool,
            "args": args,
            "output": output[:1000],
            "success": success,
            "time": time.strftime("%H:%M:%S"),
        })
        if len(self.tool_outputs) > 30:
            self.tool_outputs = self.tool_outputs[-30:]

    def record_retrieved(self, source: str, data_type: str, content: str, meta: dict | None = None) -> None:
        self.retrieved_data.append({
            "source": source,
            "type": data_type,
            "content": content[:2000],
            "meta": meta or {},
            "time": time.strftime("%H:%M:%S"),
        })
        if len(self.retrieved_data) > 20:
            self.retrieved_data = self.retrieved_data[-20:]

    def context_block(self) -> str:
        parts = []
        if self.file_contents:
            parts.append("## Cached File Contents")
            for path, content in list(self.tool_outputs)[-5:]:
                parts.append(f"### {path}\n```\n{content[:2000]}\n```")
        if self.search_results:
            parts.append("## Recent Search Results")
            for sr in self.search_results[-3:]:
                parts.append(f"Query: {sr['query']}\n" + "\n".join(f"- {r}" for r in sr["results"][:5]))
        if self.instructions:
            parts.append("## Instructions\n" + "\n".join(self.instructions[-5:]))
        if self.retrieved_data:
            parts.append("## Retrieved Data")
            for rd in self.retrieved_data[-3:]:
                parts.append(f"[{rd['type']}] {rd['source']}: {rd['content'][:500]}")
        return "\n".join(parts)

    def clear(self) -> None:
        self.__init__()


# ---------------------------------------------------------------------------
# Layer 1b — Sensory Memory
# ---------------------------------------------------------------------------

class SensoryMemory:
    """Short-term sensory buffer — what the agent has seen this session."""

    TYPES = ("file", "doc", "text", "screen", "api", "web", "email", "message")

    def __init__(self):
        self._entries: list[dict] = []
        self._by_type: dict[str, list[dict]] = {t: [] for t in self.TYPES}

    def perceive(self, source: str, data_type: str, content: str, meta: dict | None = None) -> None:
        if data_type not in self.TYPES:
            data_type = "text"
        entry = {
            "source": source,
            "type": data_type,
            "content": content[:4000],
            "meta": meta or {},
            "time": time.strftime("%H:%M:%S"),
            "ts": time.time(),
        }
        self._entries.append(entry)
        self._by_type[data_type].append(entry)
        max_per_type = 15
        if len(self._by_type[data_type]) > max_per_type:
            self._by_type[data_type] = self._by_type[data_type][-max_per_type:]
        max_total = 80
        if len(self._entries) > max_total:
            self._entries = self._entries[-max_total:]

    def perceive_file(self, path: str, content: str, encoding: str = "utf-8") -> None:
        self.perceive(path, "file", content, {"encoding": encoding, "size": len(content)})

    def perceive_doc(self, source: str, content: str, doc_type: str = "doc") -> None:
        self.perceive(source, "doc", content, {"doc_type": doc_type})

    def perceive_text(self, source: str, content: str) -> None:
        self.perceive(source, "text", content)

    def perceive_screen(self, source: str, content: str) -> None:
        self.perceive(source, "screen", content)

    def perceive_api(self, endpoint: str, response: str, status: int = 200) -> None:
        self.perceive(endpoint, "api", response, {"status": status})

    def perceive_web(self, url: str, content: str) -> None:
        self.perceive(url, "web", content)

    def perceive_email(self, subject: str, content: str, sender: str = "") -> None:
        self.perceive(subject, "email", content, {"sender": sender})

    def perceive_message(self, sender: str, content: str, channel: str = "") -> None:
        self.perceive(sender, "message", content, {"channel": channel})

    def search(self, query: str, data_type: str | None = None) -> list[dict]:
        q = query.lower()
        pool = self._by_type.get(data_type, self._entries) if data_type else self._entries
        results = []
        for entry in reversed(pool):
            if q in entry["source"].lower() or q in entry["content"].lower():
                results.append(entry)
        return results[:10]

    def recent(self, data_type: str | None = None, limit: int = 10) -> list[dict]:
        pool = self._by_type.get(data_type, self._entries) if data_type else self._entries
        return pool[-limit:]

    def stats(self) -> dict[str, int]:
        return {t: len(self._by_type[t]) for t in self.TYPES}

    def summary(self) -> str:
        counts = self.stats()
        active = [f"{t}:{n}" for t, n in counts.items() if n > 0]
        return " ".join(active) if active else "empty"

    def context_block(self, max_chars: int = 6000) -> str:
        if not self._entries:
            return ""
        parts = ["## Sensory Memory (recent)"]
        for entry in self._entries[-8:]:
            tag = entry["type"].upper()
            src = entry["source"][:60]
            preview = entry["content"][:400].replace("\n", " ")
            parts.append(f"[{tag}] {src}: {preview}")
        return "\n".join(parts)


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
    for path in (LOCAL_USER_PROFILE_PATH, USER_PROFILE_PATH):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
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


# ---------------------------------------------------------------------------
# Episodic Memory
# ---------------------------------------------------------------------------

EPISODES_DIR = AGENT_DIR / "episodes"


@dataclass
class Episode:
    id: str
    request: str
    goal: str
    outcome: str
    quality: str
    files_touched: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    key_decisions: list[str] = field(default_factory=list)
    errors_encountered: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    context_tags: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    token_usage: int = 0
    iteration_count: int = 0
    created_at: float = 0.0
    sensory_snapshot: str = ""
    working_snapshot: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = d["created_at"] or time.time()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Episode:
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})

    def similarity(self, query: str) -> float:
        q = query.lower()
        score = 0.0
        q_words = set(q.split())
        for word in q_words:
            if len(word) < 3:
                continue
            if word in self.request.lower():
                score += 0.3
            if word in self.goal.lower():
                score += 0.2
            if word in " ".join(self.context_tags).lower():
                score += 0.15
            if word in " ".join(self.lessons).lower():
                score += 0.1
        if self.quality in ("excellent", "good"):
            score += 0.1
        return min(score, 1.0)


class EpisodicMemory:
    def __init__(self):
        self._episodes: dict[str, Episode] = {}
        self._load()

    def _load(self) -> None:
        EPISODES_DIR.mkdir(parents=True, exist_ok=True)
        for p in EPISODES_DIR.glob("*.json"):
            if p.name == "index.json":
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                ep = Episode.from_dict(data)
                self._episodes[ep.id] = ep
            except Exception:
                pass

    def _save(self, ep: Episode) -> None:
        path = EPISODES_DIR / f"{ep.id}.json"
        path.write_text(json.dumps(ep.to_dict(), indent=2), encoding="utf-8")

    def store(self, request: str, goal: str, outcome: str, quality: str = "good",
              files_touched: list[str] | None = None, tools_used: list[str] | None = None,
              key_decisions: list[str] | None = None, errors_encountered: list[str] | None = None,
              lessons: list[str] | None = None, context_tags: list[str] | None = None,
              duration_seconds: float = 0.0, token_usage: int = 0, iteration_count: int = 0,
              sensory_snapshot: str = "", working_snapshot: str = "") -> Episode:
        ep = Episode(
            id=f"ep-{int(time.time())}-{len(self._episodes)}",
            request=request,
            goal=goal,
            outcome=outcome,
            quality=quality,
            files_touched=files_touched or [],
            tools_used=tools_used or [],
            key_decisions=key_decisions or [],
            errors_encountered=errors_encountered or [],
            lessons=lessons or [],
            context_tags=context_tags or [],
            duration_seconds=duration_seconds,
            token_usage=token_usage,
            iteration_count=iteration_count,
            created_at=time.time(),
            sensory_snapshot=sensory_snapshot,
            working_snapshot=working_snapshot,
        )
        self._episodes[ep.id] = ep
        self._save(ep)
        self.prune()
        return ep

    def prune(self, max_episodes: int = 200, age_days: float = 90.0,
              keep_qualities: tuple[str, ...] = ("excellent", "good")) -> dict:
        """Auto-prune episodic memory to keep it lean and high-signal.

        Strategy: if over `max_episodes`, drop oldest episodes first, but always
        keep those whose quality is in `keep_qualities` unless they are also the
        oldest beyond the cap. Also drop episodes older than `age_days` whose
        quality is not 'excellent'.
        """
        before = len(self._episodes)
        if before == 0:
            return {"removed": 0, "kept": 0}

        now = time.time()
        age_cutoff = now - (age_days * 86400)

        removable = []
        protected = []
        for ep in self._episodes.values():
            if ep.created_at < age_cutoff and ep.quality != "excellent":
                removable.append(ep)
            else:
                protected.append(ep)

        over_cap = len(self._episodes) - max_episodes
        if over_cap > 0:
            sorted_all = sorted(self._episodes.values(), key=lambda e: e.created_at)
            idx = 0
            while over_cap > 0 and idx < len(sorted_all):
                ep = sorted_all[idx]
                if ep in protected and ep.quality in keep_qualities:
                    idx += 1
                    continue
                removable.append(ep)
                over_cap -= 1
                idx += 1

        seen = set()
        actual_removed = 0
        for ep in removable:
            if ep.id in seen:
                continue
            seen.add(ep.id)
            try:
                (EPISODES_DIR / f"{ep.id}.json").unlink(missing_ok=True)
            except Exception:
                pass
            self._episodes.pop(ep.id, None)
            actual_removed += 1

        return {"removed": actual_removed, "kept": len(self._episodes)}

    def retrieve(self, query: str, top_k: int = 5, min_score: float = 0.1) -> list[Episode]:
        scored = []
        for ep in self._episodes.values():
            sim = ep.similarity(query)
            if sim >= min_score:
                scored.append((sim, ep))
        scored.sort(key=lambda x: -x[0])
        return [s[1] for s in scored[:top_k]]

    def recent(self, limit: int = 10) -> list[Episode]:
        all_eps = sorted(self._episodes.values(), key=lambda e: e.created_at, reverse=True)
        return all_eps[:limit]

    def by_quality(self, quality: str, limit: int = 10) -> list[Episode]:
        matched = [ep for ep in self._episodes.values() if ep.quality == quality]
        matched.sort(key=lambda e: e.created_at, reverse=True)
        return matched[:limit]

    def stats(self) -> dict:
        total = len(self._episodes)
        if total == 0:
            return {"total": 0}
        qualities = {}
        total_duration = 0.0
        total_tokens = 0
        all_tools = []
        all_files = []
        for ep in self._episodes.values():
            qualities[ep.quality] = qualities.get(ep.quality, 0) + 1
            total_duration += ep.duration_seconds
            total_tokens += ep.token_usage
            all_tools.extend(ep.tools_used)
            all_files.extend(ep.files_touched)
        tool_counts = {}
        for t in all_tools:
            tool_counts[t] = tool_counts.get(t, 0) + 1
        top_tools = sorted(tool_counts.items(), key=lambda x: -x[1])[:5]
        return {
            "total": total,
            "qualities": qualities,
            "avg_duration": total_duration / total,
            "total_tokens": total_tokens,
            "top_tools": top_tools,
            "unique_files": len(set(all_files)),
        }

    def context_block(self, query: str = "", max_episodes: int = 3) -> str:
        if not self._episodes:
            return ""
        episodes = self.retrieve(query, top_k=max_episodes) if query else self.recent(limit=max_episodes)
        if not episodes:
            return ""
        parts = ["## Episodic Memory (relevant past experiences)"]
        for ep in episodes:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(ep.created_at)) if ep.created_at else "?"
            quality_icon = {"excellent": "★★★", "good": "★★", "mediocre": "★", "bad": "☆"}.get(ep.quality, "?")
            parts.append(f"### [{quality_icon}] {ep.request[:80]}")
            parts.append(f"- **Goal:** {ep.goal[:120]}")
            parts.append(f"- **Outcome:** {ep.outcome[:200]}")
            if ep.files_touched:
                parts.append(f"- **Files:** {', '.join(ep.files_touched[:5])}")
            if ep.tools_used:
                parts.append(f"- **Tools:** {', '.join(ep.tools_used[:5])}")
            if ep.lessons:
                parts.append(f"- **Lessons:** {'; '.join(ep.lessons[:3])}")
            if ep.errors_encountered:
                parts.append(f"- **Errors:** {'; '.join(ep.errors_encountered[:2])}")
            parts.append(f"- **When:** {ts} | **Tokens:** {ep.token_usage:,} | **Iters:** {ep.iteration_count}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Semantic Memory — user preferences, domain facts, learned rules
# ---------------------------------------------------------------------------

SEMANTIC_PATH = AGENT_DIR / "semantic_memory.json"


@dataclass
class SemanticFact:
    id: str
    category: str
    key: str
    value: str
    confidence: float = 1.0
    source: str = "learned"
    created_at: float = 0.0
    last_used: float = 0.0
    use_count: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = d["created_at"] or time.time()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> SemanticFact:
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


class SemanticMemory:
    CATEGORIES = ("preference", "domain", "rule", "pattern", "constraint", "convention", "fact")

    def __init__(self):
        self._facts: dict[str, SemanticFact] = {}
        self._load()

    def _load(self) -> None:
        if SEMANTIC_PATH.exists():
            try:
                data = json.loads(SEMANTIC_PATH.read_text(encoding="utf-8"))
                for d in data.get("facts", []):
                    f = SemanticFact.from_dict(d)
                    self._facts[f.id] = f
            except Exception:
                pass

    def _save(self) -> None:
        SEMANTIC_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {"facts": [f.to_dict() for f in self._facts.values()]}
        SEMANTIC_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def learn(self, category: str, key: str, value: str, confidence: float = 1.0,
              source: str = "learned", tags: list[str] | None = None) -> SemanticFact:
        for existing in self._facts.values():
            if existing.category == category and existing.key.lower() == key.lower():
                existing.value = value
                existing.confidence = max(existing.confidence, confidence)
                existing.source = source
                existing.last_used = time.time()
                existing.use_count += 1
                if tags:
                    existing.tags = list(set(existing.tags + tags))
                self._save()
                return existing
        fact = SemanticFact(
            id=f"sem-{int(time.time())}-{len(self._facts)}",
            category=category,
            key=key,
            value=value,
            confidence=confidence,
            source=source,
            created_at=time.time(),
            last_used=time.time(),
            tags=tags or [],
        )
        self._facts[fact.id] = fact
        self._save()
        return fact

    def recall(self, query: str, category: str | None = None, top_k: int = 10) -> list[SemanticFact]:
        q = query.lower()
        results = []
        for fact in self._facts.values():
            if category and fact.category != category:
                continue
            score = 0.0
            if q in fact.key.lower():
                score += 0.4
            if q in fact.value.lower():
                score += 0.3
            for tag in fact.tags:
                if q in tag.lower():
                    score += 0.2
            score *= fact.confidence
            if fact.use_count > 3:
                score += 0.1
            if score > 0:
                results.append((score, fact))
        results.sort(key=lambda x: -x[0])
        return [r[1] for r in results[:top_k]]

    def get_preferences(self) -> list[SemanticFact]:
        return [f for f in self._facts.values() if f.category == "preference"]

    def get_domain_facts(self) -> list[SemanticFact]:
        return [f for f in self._facts.values() if f.category == "domain"]

    def get_rules(self) -> list[SemanticFact]:
        return [f for f in self._facts.values() if f.category == "rule"]

    def get_patterns(self) -> list[SemanticFact]:
        return [f for f in self._facts.values() if f.category == "pattern"]

    def delete(self, fact_id: str) -> bool:
        if fact_id in self._facts:
            del self._facts[fact_id]
            self._save()
            return True
        return False

    def stats(self) -> dict:
        by_cat = {}
        for f in self._facts.values():
            by_cat[f.category] = by_cat.get(f.category, 0) + 1
        return {"total": len(self._facts), "by_category": by_cat}

    def context_block(self, query: str = "", max_facts: int = 8) -> str:
        if not self._facts:
            return ""
        facts = self.recall(query, top_k=max_facts) if query else list(self._facts.values())[:max_facts]
        if not facts:
            return ""
        parts = ["## Semantic Memory"]
        by_cat: dict[str, list[SemanticFact]] = {}
        for f in facts:
            by_cat.setdefault(f.category, []).append(f)
        for cat, cat_facts in by_cat.items():
            parts.append(f"### {cat.title()}s")
            for f in cat_facts:
                conf = f"{f.confidence:.0%}" if f.confidence < 1.0 else ""
                parts.append(f"- **{f.key}:** {f.value}" + (f" ({conf})" if conf else ""))
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# RAG — Retrieval-Augmented Generation
# ---------------------------------------------------------------------------

class RAGEngine:
    """Retrieval-Augmented Generation backed by ChromaDB vector database.

    Pipeline:  Index → Embed → Store → Retrieve → Generate.

    ChromaDB is used when available (with sentence-transformers or a
    lightweight hashing embedder fallback). If chromadb is not installed,
    a pure-Python TF-IDF cosine fallback is used so the package still works.
    """

    VDB_PATH = AGENT_DIR / "vector_db.json"

    def __init__(self, collection: str = "revona", persist_dir: str | None = None):
        self._chunks: list[dict] = []
        self._chunk_id = 0
        self._client = None
        self._collection = None
        self._collection_name = collection
        self._use_chroma = False
        self._embedder = None
        self._persist_dir = persist_dir or str(AGENT_DIR / "chroma")
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb
            from chromadb.config import Settings
            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=Settings(anonymized_telemetry=False, allow_reset=True),
            )
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name, metadata={"hnsw:space": "cosine"}
            )
            self._embedder = _Embedder()
            self._use_chroma = True
        except Exception:
            self._use_chroma = False

    def _get_embedder(self):
        if self._embedder is None:
            self._embedder = _Embedder()
        return self._embedder

    def _chunk_text(self, text: str, chunk_size: int = 600, overlap: int = 80) -> list[str]:
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunks.append(" ".join(words[i:i + chunk_size]))
            i += chunk_size - overlap
        return chunks or [text]

    def index_text(self, text: str, source: str, source_type: str, meta: dict | None = None) -> int:
        pieces = self._chunk_text(text)
        count = 0
        for piece in pieces:
            self._chunk_id += 1
            cid = self._chunk_id
            self._chunks.append({
                "id": cid, "text": piece, "source": source,
                "source_type": source_type, "meta": meta or {},
            })
            if self._use_chroma:
                try:
                    emb = self._get_embedder().embed(piece)
                    self._collection.add(
                        ids=[str(cid)],
                        documents=[piece],
                        embeddings=[emb],
                        metadatas=[{"source": source, "source_type": source_type}],
                    )
                except Exception:
                    pass
            count += 1
        return count

    def index_file(self, path: str) -> int:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            return self.index_text(text, path, "file", {"size": len(text)})
        except Exception:
            return 0

    def index_directory(self, root: str = ".", extensions: tuple = (".py", ".ts", ".js", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".html", ".css", ".sql")) -> int:
        count = 0
        root_path = Path(root)
        for p in root_path.rglob("*"):
            if p.is_file() and p.suffix.lower() in extensions:
                if any(skip in str(p) for skip in ("node_modules", ".git", "__pycache__", "dist", ".venv", "venv")):
                    continue
                count += self.index_file(str(p))
        return count

    def retrieve(self, query: str, top_k: int = 5, source_type: str | None = None) -> list[dict]:
        if self._use_chroma:
            try:
                emb = self._get_embedder().embed(query)
                where = {"source_type": source_type} if source_type else None
                res = self._collection.query(
                    query_embeddings=[emb], n_results=top_k, where=where,
                )
                out = []
                docs = res.get("documents", [[]])[0]
                metas = res.get("metadatas", [[]])[0]
                dists = res.get("distances", [[]])[0]
                for d, m, dist in zip(docs, metas, dists):
                    sim = 1.0 - (dist or 1.0)
                    out.append({"text": d, "source": m.get("source", "?"),
                                "source_type": m.get("source_type", "?"), "score": sim})
                return out
            except Exception:
                pass
        return self._retrieve_tfidf(query, top_k, source_type)

    def _retrieve_tfidf(self, query: str, top_k: int = 5, source_type: str | None = None) -> list[dict]:
        q = set(w.lower() for w in query.split() if len(w) > 2)
        scored = []
        for c in self._chunks:
            if source_type and c["source_type"] != source_type:
                continue
            words = set(w.lower() for w in c["text"].split() if len(w) > 2)
            overlap = len(q & words)
            if overlap > 0:
                scored.append((overlap / (len(q) + 1), c))
        scored.sort(key=lambda x: -x[0])
        return [{"text": c["text"], "source": c["source"], "source_type": c["source_type"], "score": s} for s, c in scored[:top_k]]

    def context_block(self, query: str, max_chunks: int = 4, chars_per_chunk: int = 600) -> str:
        results = self.retrieve(query, top_k=max_chunks)
        if not results:
            return ""
        parts = [f"## RAG Context (query: {query[:60]})"]
        for r in results:
            preview = r["text"][:chars_per_chunk].replace("\n", " ")
            parts.append(f"### [{r['source_type']}] {r['source']}\n{preview}...")
        return "\n".join(parts)

    def stats(self) -> dict:
        by_type: dict[str, int] = {}
        for c in self._chunks:
            by_type[c["source_type"]] = by_type.get(c["source_type"], 0) + 1
        return {
            "backend": "chromadb" if self._use_chroma else "tfidf-fallback",
            "total_chunks": len(self._chunks),
            "by_type": by_type,
        }


class _Embedder:
    """Local embedding generator. Prefers sentence-transformers if available,
    otherwise falls back to a deterministic content-based hashing embedder."""

    DIM = 256

    def __init__(self):
        self._model = None
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            self._model = None

    def embed(self, text: str) -> list[float]:
        if self._model is not None:
            try:
                return self._model.encode(text, normalize_embeddings=True).tolist()
            except Exception:
                pass
        return self._hash_embed(text)

    def _hash_embed(self, text: str) -> list[float]:
        import hashlib
        vec = [0.0] * self.DIM
        tokens = [t for t in text.lower().split() if len(t) > 1]
        for tok in tokens:
            h = hashlib.md5(tok.encode()).digest()
            for i in range(min(self.DIM, len(h))):
                vec[i] += (h[i] / 255.0) - 0.5
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


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

    file_contents = []
    for fp in list(edited_files)[:8]:
        try:
            text = Path(fp).read_text(encoding="utf-8", errors="replace")
            file_contents.append(f"### {fp}\n```\n{text[:6000]}\n```")
        except Exception:
            file_contents.append(f"### {fp}\n(Unable to read file)")

    prompt = (
        f"## Request\n{request}\n\n"
        f"## Changed Files (contents included for reflection)\n\n"
        + "\n\n".join(file_contents)
        + "\n\n## Observations\n" + chr(10).join(observations[-20:])
        + "\n\nReflect on this mission. Output a JSON object with:\n"
        '- "lesson": a concise, reusable lesson\n'
        '- "quality": "excellent" | "good" | "mediocre" | "bad"\n'
        '- "security_issues": list of concerns\n'
        '- "suggestions": list of improvements\n'
        '- "verified_solution": description or ""\n'
        '- "engineering_score": number 0-100\n'
        "Output ONLY the JSON."
    )

    text, _, _ = _run_agent_loop(
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
        self.sensory = SensoryMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.rag = RAGEngine()
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

        working_ctx = self.working.context_block()
        if working_ctx:
            parts.append(working_ctx)

        sensory_ctx = self.sensory.context_block()
        if sensory_ctx:
            parts.append(sensory_ctx)

        episodic_ctx = self.episodic.context_block(query=request)
        if episodic_ctx:
            parts.append(episodic_ctx)

        semantic_ctx = self.semantic.context_block(query=request)
        if semantic_ctx:
            parts.append(semantic_ctx)

        rag_ctx = self.rag.context_block(query=request) if request else ""
        if rag_ctx:
            parts.append(rag_ctx)

        for name, content in self.project_memory.items():
            if content.strip() and name not in ("Lessons.md", "Bugs.md", "API Index.md"):
                parts.append(f"## {name.replace('.md', '')}\n{content.strip()[:2000]}")

        lessons = self.project_memory.get("Lessons.md", "")
        if lessons.strip():
            lines = [l for l in lessons.split("\n") if l.strip().startswith("-")]
            if lines:
                parts.append("## Recent Lessons\n" + "\n".join(lines[-10:]))

        if request:
            query_terms = set(request.lower().split())
            matched_nodes = []
            for n in self.knowledge_graph.nodes.values():
                label_lower = n.label.lower()
                if any(t in label_lower for t in query_terms if len(t) > 2):
                    matched_nodes.append(n)
            if not matched_nodes:
                matched_nodes = list(self.knowledge_graph.nodes.values())[:10]
            if matched_nodes:
                parts.append("## Knowledge Graph\n" + "\n".join(
                    f"- {n.label} ({n.type})" for n in matched_nodes[:15]
                ))
        else:
            top_nodes = list(self.knowledge_graph.nodes.values())[:10]
            if top_nodes:
                parts.append("## Knowledge Graph\n" + "\n".join(
                    f"- {n.label} ({n.type})" for n in top_nodes
                ))

        if request:
            relevant_experiences = self.experiences.search(request, min_confidence=0.2, top_k=3)
            if relevant_experiences:
                parts.append("## Relevant Past Solutions\n" + "\n".join(
                    f"- **{e.problem[:80]}** → {e.solution[:200]}" for e in relevant_experiences
                ))

        brain_ctx = self.brain.context_block()
        if brain_ctx:
            parts.append(brain_ctx)

        if request:
            skill_ctx = self.knowledge.get_context_for(request)
            if skill_ctx:
                parts.append("## Relevant Knowledge\n" + skill_ctx)

        return "\n".join(parts)

    def memory_dashboard(self) -> dict:
        """Aggregate a snapshot of every memory layer for the /memory dashboard."""
        sensory = self.sensory.stats()
        episodic = self.episodic.stats()
        semantic = self.semantic.stats()
        rag = self.rag.stats()
        working = {
            "recent_messages": len(self.working.recent_messages),
            "cached_files": len(self.working.file_contents),
            "search_results": len(self.working.search_results),
            "instructions": len(self.working.instructions),
            "tool_outputs": len(self.working.tool_outputs),
            "retrieved_data": len(self.working.retrieved_data),
        }
        experiences = {"total": len(self.experiences._experiences)}
        kg = {"nodes": len(self.knowledge_graph.nodes)}
        skills = {"total": len(getattr(self.knowledge, "_skills", {}))}
        brain = {}
        try:
            brain = self.brain.stats()
        except Exception:
            pass
        return {
            "sensory": sensory,
            "working": working,
            "episodic": episodic,
            "semantic": semantic,
            "rag": rag,
            "experiences": experiences,
            "knowledge_graph": kg,
            "skills": skills,
            "brain": brain,
        }

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
