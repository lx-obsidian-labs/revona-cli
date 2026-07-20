from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Directory structure
#
# Skills/
#   <name>/
#     skill.json          # metadata
#     instructions.md     # procedures
#     best-practices.md   # conventions
#     verification.md     # checklist
#
# Blueprints/
#   <name>/
#     blueprint.json      # metadata
#     architecture.md     # system structure
#     schema.md           # data model
#     modules.md          # component breakdown
#
# Accelerators/
#   <name>/
#     manifest.json       # metadata + file list
#     <files...>          # reusable assets
# ---------------------------------------------------------------------------

SKILLS_DIR = Path("Skills")
BLUEPRINTS_DIR = Path("Blueprints")
ACCELERATORS_DIR = Path("Accelerators")


# ===================================================================
# Level 1 — Skills (procedural knowledge)
# ===================================================================

@dataclass
class Skill:
    name: str
    description: str
    when_to_use: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    instructions: str = ""
    best_practices: str = ""
    verification: str = ""

    @property
    def context_block(self) -> str:
        parts = [f"### Skill: {self.name}", self.description]
        if self.instructions:
            parts.append(f"\n**Instructions:**\n{self.instructions[:3000]}")
        if self.best_practices:
            parts.append(f"\n**Best Practices:**\n{self.best_practices[:2000]}")
        if self.verification:
            parts.append(f"\n**Verification:**\n{self.verification[:1000]}")
        return "\n".join(parts)


def discover_skills() -> dict[str, Skill]:
    """Scan Skills/ directory and load all skill definitions."""
    skills = {}
    if not SKILLS_DIR.is_dir():
        return skills
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta = d / "skill.json"
        if not meta.exists():
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            skill = Skill(
                name=data.get("name", d.name),
                description=data.get("description", ""),
                when_to_use=data.get("when_to_use", []),
                tags=data.get("tags", []),
                instructions=_read(d / "instructions.md"),
                best_practices=_read(d / "best-practices.md"),
                verification=_read(d / "verification.md"),
            )
            skills[skill.name.lower()] = skill
        except Exception:
            pass
    return skills


def find_relevant_skills(query: str, skills: dict[str, Skill], top_k: int = 3) -> list[Skill]:
    """Match skills by keyword against name, description, tags, when_to_use."""
    q = query.lower()
    scored = []
    for s in skills.values():
        score = 0
        if q in s.name.lower():
            score += 5
        if q in s.description.lower():
            score += 3
        for tag in s.tags:
            if q in tag.lower():
                score += 2
        for w in s.when_to_use:
            if q in w.lower():
                score += 2
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [s[1] for s in scored[:top_k]]


# ===================================================================
# Level 2 — Blueprints (architectural knowledge)
# ===================================================================

@dataclass
class Blueprint:
    name: str
    description: str
    architecture: str = ""
    schema: str = ""
    modules: str = ""

    @property
    def context_block(self) -> str:
        parts = [f"### Blueprint: {self.name}", self.description]
        if self.architecture:
            parts.append(f"\n**Architecture:**\n{self.architecture[:3000]}")
        if self.schema:
            parts.append(f"\n**Schema:**\n{self.schema[:2000]}")
        if self.modules:
            parts.append(f"\n**Modules:**\n{self.modules[:2000]}")
        return "\n".join(parts)


def discover_blueprints() -> dict[str, Blueprint]:
    """Scan Blueprints/ directory."""
    bps = {}
    if not BLUEPRINTS_DIR.is_dir():
        return bps
    for d in sorted(BLUEPRINTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta = d / "blueprint.json"
        if not meta.exists():
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            bp = Blueprint(
                name=data.get("name", d.name),
                description=data.get("description", ""),
                architecture=_read(d / "architecture.md"),
                schema=_read(d / "schema.md"),
                modules=_read(d / "modules.md"),
            )
            bps[bp.name.lower()] = bp
        except Exception:
            pass
    return bps


def find_relevant_blueprints(query: str, bps: dict[str, Blueprint], top_k: int = 2) -> list[Blueprint]:
    q = query.lower()
    scored = []
    for bp in bps.values():
        score = 0
        if q in bp.name.lower():
            score += 5
        if q in bp.description.lower():
            score += 3
        if q in bp.architecture.lower():
            score += 1
        if score > 0:
            scored.append((score, bp))
    scored.sort(key=lambda x: -x[0])
    return [s[1] for s in scored[:top_k]]


# ===================================================================
# Level 3 — Accelerators (reusable assets)
# ===================================================================

@dataclass
class Accelerator:
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)  # relative path -> content

    @property
    def context_block(self) -> str:
        parts = [f"### Accelerator: {self.name}", self.description]
        for path, content in self.files.items():
            parts.append(f"\n**{path}:**\n```\n{content[:2000]}\n```")
        return "\n".join(parts)


def discover_accelerators() -> dict[str, Accelerator]:
    """Scan Accelerators/ directory."""
    accs = {}
    if not ACCELERATORS_DIR.is_dir():
        return accs
    for d in sorted(ACCELERATORS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta = d / "manifest.json"
        if not meta.exists():
            continue
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            files = {}
            for rel_path in data.get("files", []):
                fp = d / rel_path
                if fp.is_file():
                    files[rel_path] = fp.read_text(encoding="utf-8", errors="replace")
            acc = Accelerator(
                name=data.get("name", d.name),
                description=data.get("description", ""),
                tags=data.get("tags", []),
                files=files,
            )
            accs[acc.name.lower()] = acc
        except Exception:
            pass
    return accs


def find_relevant_accelerators(query: str, accs: dict[str, Accelerator], top_k: int = 2) -> list[Accelerator]:
    q = query.lower()
    scored = []
    for a in accs.values():
        score = 0
        if q in a.name.lower():
            score += 5
        if q in a.description.lower():
            score += 3
        for tag in a.tags:
            if q in tag.lower():
                score += 2
        if score > 0:
            scored.append((score, a))
    scored.sort(key=lambda x: -x[0])
    return [s[1] for s in scored[:top_k]]


# ===================================================================
# Knowledge Engine — loads all three levels for a given request
# ===================================================================

class KnowledgeEngine:
    """Load and query Skills, Blueprints, and Accelerators."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._blueprints: dict[str, Blueprint] = {}
        self._accelerators: dict[str, Accelerator] = {}
        self._loaded = False

    def load_all(self) -> None:
        self._skills = discover_skills()
        self._blueprints = discover_blueprints()
        self._accelerators = discover_accelerators()
        self._loaded = True

    def get_context_for(self, request: str) -> str:
        """Return relevant knowledge blocks for the given request."""
        if not self._loaded:
            self.load_all()
        parts = []

        skills = find_relevant_skills(request, self._skills)
        for s in skills:
            parts.append(s.context_block)

        bps = find_relevant_blueprints(request, self._blueprints)
        for bp in bps:
            parts.append(bp.context_block)

        accs = find_relevant_accelerators(request, self._accelerators)
        for a in accs:
            parts.append(a.context_block)

        return "\n---\n".join(parts)

    def all_skills(self) -> list[Skill]:
        if not self._loaded:
            self.load_all()
        return list(self._skills.values())

    def all_blueprints(self) -> list[Blueprint]:
        if not self._loaded:
            self.load_all()
        return list(self._blueprints.values())

    def all_accelerators(self) -> list[Accelerator]:
        if not self._loaded:
            self.load_all()
        return list(self._accelerators.values())


def _read(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return ""
