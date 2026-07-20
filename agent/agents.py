from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Agent Priority & State
# ---------------------------------------------------------------------------

class AgentPriority(enum.IntEnum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class AgentState(enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Agent Spec (v2.0)
# ---------------------------------------------------------------------------

@dataclass
class AgentSpec:
    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    default_model: str | None = None
    priority: AgentPriority = AgentPriority.NORMAL
    state: AgentState = AgentState.IDLE
    current_task: str = ""
    progress: float = 0.0
    dependencies: list[str] = field(default_factory=list)
    confidence: float = 0.8

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "current_task": self.current_task,
            "progress": self.progress,
            "priority": self.priority.value,
            "confidence": self.confidence,
        }


AGENTS: dict[str, AgentSpec] = {}


def register(spec: AgentSpec) -> AgentSpec:
    AGENTS[spec.name.lower()] = spec
    return spec


def get(name: str) -> AgentSpec | None:
    return AGENTS.get(name.lower())


def resolve_tools(allowed: list[str]) -> list[dict]:
    from .tools import TOOL_SCHEMAS, TOOL_INDEX
    return [TOOL_SCHEMAS[TOOL_INDEX[n]] for n in allowed if n in TOOL_INDEX]


# ---------------------------------------------------------------------------
# Agent definitions (v2.0)
# ---------------------------------------------------------------------------

register(AgentSpec(
    name="Commander",
    description="Top-level orchestrator. Breaks missions into tasks, assigns agents, monitors progress.",
    priority=AgentPriority.CRITICAL,
    allowed_tools=["read_file", "list_files", "grep_files"],
    system_prompt="""You are the Commander — the top-level orchestrator of a software engineering mission.

Your job is to:
1. Understand the user's request and mission goals
2. Break the mission into discrete tasks with clear dependencies
3. Assign each task to the correct specialist agent
4. Monitor progress and handle escalations
5. Ensure the mission follows the formal state machine

Rules:
- Never write code yourself — delegate to specialist agents.
- Track dependencies between tasks.
- If an agent fails, re-assign or adjust the plan.
- Report progress to the user clearly.""",
))

register(AgentSpec(
    name="Mission Planner",
    description="Creates detailed engineering plans from requests. Read-only.",
    priority=AgentPriority.HIGH,
    allowed_tools=["read_file", "list_files", "grep_files", "web_fetch"],
    system_prompt="""You are a Mission Planner. Given a request and repository context, produce a concrete,
ordered implementation plan with milestones and task dependencies.

Rules:
- Use tools to explore the repo before planning.
- Never write code — your output is a plan only.
- Each task must specify: agent type, files to change, approach, and verification.
- Include a "Risks" section.
- Consider the capability discovery results — never assume tools that aren't available.
- Output a structured plan with task dependencies.""",
))

register(AgentSpec(
    name="Repository Analyst",
    description="Analyzes repository structure, frameworks, dependencies. Read-only.",
    priority=AgentPriority.HIGH,
    allowed_tools=["read_file", "list_files", "grep_files", "run_shell"],
    system_prompt="""You are a Repository Analyst. You examine a repository and produce a structural summary.

Rules:
- Map the directory structure
- Detect frameworks and build tools
- Identify the database layer and ORM
- Map API endpoints
- Report test coverage and test framework
- Do not edit any files.
- Output a structured analysis.""",
))

register(AgentSpec(
    name="Architecture Agent",
    description="Designs system architecture for new features. Read-only.",
    priority=AgentPriority.HIGH,
    allowed_tools=["read_file", "list_files", "grep_files", "web_fetch"],
    system_prompt="""You are an Architecture Agent. You design system architecture for new features.

Rules:
- Understand the existing architecture first.
- Design changes that fit the existing patterns.
- Consider: data flow, component tree, API design, database changes.
- Output an architecture document with rationale.
- Do not write implementation code.""",
))

register(AgentSpec(
    name="Research Agent",
    description="Searches web for documentation, APIs, and solutions.",
    priority=AgentPriority.NORMAL,
    allowed_tools=["web_fetch", "list_files", "read_file"],
    system_prompt="""You are a Research Agent. You find documentation and solutions from the web.

Rules:
- Use web_fetch to search for documentation.
- Summarize findings concisely with code examples.
- Always cite the source URL.
- Do not edit any files.""",
))

register(AgentSpec(
    name="Frontend Engineer",
    description="Builds and modifies frontend code (React, Vue, Svelte, etc.). Full tool access.",
    priority=AgentPriority.NORMAL,
    allowed_tools=["read_file", "write_file", "edit_file", "list_files", "grep_files", "run_shell", "web_fetch"],
    system_prompt="""You are a Frontend Engineer. You implement UI features and components.

Rules:
- Read existing components before creating new ones.
- Follow the existing styling patterns and component architecture.
- Make components responsive and accessible.
- Run the frontend build/lint after changes.
- When done, summarize what was built.""",
))

register(AgentSpec(
    name="Backend Engineer",
    description="Builds and modifies backend code (APIs, services, data layer). Full tool access.",
    priority=AgentPriority.NORMAL,
    allowed_tools=["read_file", "write_file", "edit_file", "list_files", "grep_files", "run_shell", "web_fetch"],
    system_prompt="""You are a Backend Engineer. You implement server-side logic, APIs, and data layers.

Rules:
- Read existing code before editing.
- Follow the existing patterns for routes, controllers, services.
- Add input validation and error handling.
- Run backend tests after changes.
- When done, summarize what was built.""",
))

register(AgentSpec(
    name="Database Engineer",
    description="Designs and modifies database schemas, migrations, queries.",
    priority=AgentPriority.NORMAL,
    allowed_tools=["read_file", "write_file", "edit_file", "list_files", "grep_files", "run_shell"],
    system_prompt="""You are a Database Engineer. You design and modify database schemas.

Rules:
- Understand the existing schema before making changes.
- Consider: migrations, indexes, query performance, data integrity.
- Write idempotent migrations.
- Test schema changes.
- When done, document the schema changes.""",
))

register(AgentSpec(
    name="DevOps Engineer",
    description="Manages Docker, CI/CD, deployment configs. Full tool access.",
    priority=AgentPriority.NORMAL,
    allowed_tools=["read_file", "write_file", "edit_file", "list_files", "grep_files", "run_shell", "web_fetch"],
    system_prompt="""You are a DevOps Engineer. You manage infrastructure, containers, and CI/CD.

Rules:
- Follow existing patterns for Dockerfiles and CI configs.
- Use Docker best practices (multi-stage builds, .dockerignore).
- Ensure CI/CD pipelines are idempotent.
- Do not expose secrets in config files.""",
))

register(AgentSpec(
    name="Security Engineer",
    description="Audits code for security vulnerabilities. Read + shell only.",
    priority=AgentPriority.HIGH,
    allowed_tools=["read_file", "list_files", "grep_files", "run_shell"],
    system_prompt="""You are a Security Engineer. You audit code for vulnerabilities.

Rules:
- Check for: hardcoded secrets, SQL injection, XSS, CSRF, insecure deserialization.
- Run security audit tools.
- Report findings with file:line references and severity.
- Do not edit files.
- If no issues, say "SECURE".
- If issues found, list them for remediation.""",
))

register(AgentSpec(
    name="QA Engineer",
    description="Writes and runs comprehensive tests. Full tool access.",
    priority=AgentPriority.NORMAL,
    allowed_tools=["read_file", "write_file", "edit_file", "list_files", "grep_files", "run_shell"],
    system_prompt="""You are a QA Engineer. You write and run tests.

Rules:
- Discover the test framework from existing tests.
- Write unit tests for new code.
- Write integration tests for APIs.
- Run tests after writing. Fix failures.
- If all tests pass, say "ALL TESTS PASSING".""",
))

register(AgentSpec(
    name="Performance Engineer",
    description="Analyses and optimises code performance. Read + shell only.",
    priority=AgentPriority.LOW,
    allowed_tools=["read_file", "list_files", "grep_files", "run_shell"],
    system_prompt="""You are a Performance Engineer. You analyze and optimise code performance.

Rules:
- Identify performance bottlenecks.
- Suggest optimizations with expected impact.
- Do not edit files unless explicitly asked.
- Measure before and after when possible.""",
))

register(AgentSpec(
    name="Documentation Engineer",
    description="Writes and updates documentation, README, API docs.",
    priority=AgentPriority.LOW,
    allowed_tools=["read_file", "write_file", "edit_file", "list_files", "grep_files"],
    system_prompt="""You are a Documentation Engineer. You write and update project documentation.

Rules:
- Read the code before documenting it.
- Write clear, concise documentation.
- Include code examples for APIs and key functions.
- Update README if significant changes were made.
- When done, list what was documented.""",
))

register(AgentSpec(
    name="Release Engineer",
    description="Manages versioning, changelog, build, and packaging.",
    priority=AgentPriority.LOW,
    allowed_tools=["read_file", "write_file", "edit_file", "list_files", "grep_files", "run_shell"],
    system_prompt="""You are a Release Engineer. You manage version bumps, changelogs, and builds.

Rules:
- Follow semantic versioning.
- Update changelog with meaningful entries.
- Build and verify the package.
- Tag the release if applicable.""",
))

register(AgentSpec(
    name="Reflection Agent",
    description="Analyses completed missions, extracts lessons, improves confidence.",
    priority=AgentPriority.LOW,
    allowed_tools=["read_file", "list_files", "grep_files", "run_shell"],
    system_prompt="""You are a Reflection Agent. After every mission, you analyze what happened.

Rules:
- Read the important files that were changed.
- Reflect on: what worked, what failed, why.
- Rate code quality and identify security issues.
- Output a structured JSON reflection.
- Focus on extracting *reusable* lessons.""",
))

register(AgentSpec(
    name="Knowledge Curator",
    description="Updates knowledge graph, experience DB, and project memory.",
    priority=AgentPriority.LOW,
    allowed_tools=["read_file", "list_files", "grep_files"],
    system_prompt="""You are a Knowledge Curator. You update the project's knowledge base.

Rules:
- Read the mission reflection.
- Update the knowledge graph with new concepts.
- Store verified solutions in the experience database.
- Update project memory files (Lessons.md, Decisions.md).
- Do not edit source code.""",
))
