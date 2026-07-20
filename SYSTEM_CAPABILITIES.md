# Revona CLI v2.0 — System Capabilities Document

**Version:** 2.0.0  
**Built by:** LX Obsidian Labs  
**Default Model:** deepseek-ai/deepseek-v4-pro (via NVIDIA NIM API)  
**Architecture:** Mission-Driven Autonomous Software Engineering Operating System

---

## 1. Mission Engine (Core Architecture)

Every request becomes a **Mission** with a formal state machine. No phase may be skipped.

```
MISSION_CREATED → DISCOVERY → CAPABILITY_DISCOVERY → REPOSITORY_ANALYSIS →
ARCHITECTURE → PLANNING → WAITING_APPROVAL → EXECUTION → VALIDATION →
SECURITY_REVIEW → DOCUMENTATION → REFLECTION → MISSION_COMPLETE
```

Also supports: FAILED, RECOVERING, CANCELLED.

### Mission lifecycle:
- State transition enforcement (invalid transitions prevented)
- Priority system (LOW, NORMAL, HIGH, CRITICAL)
- State history tracking with timestamps
- Engineering score calculation (architecture, quality, tests, security, performance, docs)
- Snapshot/checkpoint creation at every state transition

## 2. CLI Commands

| Command | Description |
|---------|-------------|
| `revona` (no subcommand) | Launch interactive Mission Control cockpit |
| `revona mission <request>` | **[v2.0]** Start a full engineering mission with state machine lifecycle |
| `revona run <prompt>` | Non-interactive: execute a single prompt (v1.x compat) |
| `revona build <prompt>` | Plan → approve → execute (v1.x compat) |
| `revona config` | View or set configuration |
| `revona models` | List cached models |
| `revona refresh` | Refresh cached model list from NVIDIA NIM |
| `revona discover` | **[v2.0]** Discover available system capabilities |
| `revona search <query>` | **[v2.0]** Semantic code search across repository |
| `revona verify` | **[v2.0]** Run verification pipeline on repository |
| `revona recovery` | **[v2.0]** Show recovery engine history |
| `revona queue` | **[v2.0]** Show mission queue |
| `revona workspace` | **[v2.0]** Manage workspaces (list/add/switch) |
| `revona checkpoints` | **[v2.0]** List available checkpoints |
| `revona install <source> <name>` | **[v2.0]** Install a plugin |

## 3. Interactive Slash Commands

| Command | Action |
|---------|--------|
| `/help` | List all slash commands |
| `/change model <id>` | Switch model mid-session |
| `/models [keyword]` | Browse/search cached models |
| `/plan` | Toggle plan-only mode |
| `/undo` | Undo last assistant response |
| `/redo` | Redo previously undone response |
| `/init` | Index repo (SQLite DB + context) |
| `/save` | Save current model as default |
| `/skills [keyword]` | List/search skills, blueprints, accelerators |
| `/brain` | Show repository intelligence summary |
| `/capabilities` | **[v2.0]** Discover system capabilities |
| `/search <query>` | **[v2.0]** Semantic search repository |
| `/verify` | **[v2.0]** Run verification pipeline |
| `/recovery` | **[v2.0]** Show recovery history |
| `/mission` | **[v2.0]** Show current mission status |
| `/queue` | **[v2.0]** Show mission queue |
| `/workspace` | **[v2.0]** List/manage workspaces |
| `/checkpoints` | **[v2.0]** List available checkpoints |
| `@file` | Reference file content in prompt |

## 4. Capability Discovery Engine

Before ANY task begins, automatically detects:

| Capability | Detection Method |
|------------|-----------------|
| Filesystem | Always available |
| Git | `git --version` probe |
| Internet | HTTP reachability check |
| Shell | Environment detection |
| Docker | `docker info` probe |
| Python | Runtime version detection |
| pip | `pip --version` probe |
| Node | `node --version` probe |
| npm | `npm --version` probe |
| pnpm | `pnpm --version` probe |
| ADB | `adb devices` probe |
| Browser | Binary/install path detection |
| MCP Servers | Config file discovery |
| Permissions | Filesystem read/write/network checks |
| Databases | PostgreSQL, MySQL, MongoDB, Redis detection |

Every tool reports: `available`, `unavailable`, or `restricted`.  
The Planner must never assume a capability exists.

## 5. Agent System (v2.0 — 16 Specialist Roles)

| Agent | Priority | Purpose |
|-------|----------|---------|
| **Commander** | CRITICAL | Top-level orchestrator, task assignment, monitoring |
| **Mission Planner** | HIGH | Creates detailed engineering plans with dependencies |
| **Repository Analyst** | HIGH | Analyzes structure, frameworks, dependencies |
| **Architecture Agent** | HIGH | Designs system architecture for features |
| **Frontend Engineer** | NORMAL | Builds UI components (React, Vue, Svelte, etc.) |
| **Backend Engineer** | NORMAL | Implements APIs, services, data layer |
| **Database Engineer** | NORMAL | Designs schemas, migrations, queries |
| **DevOps Engineer** | NORMAL | Docker, CI/CD, deployment configs |
| **Security Engineer** | HIGH | Audits for vulnerabilities (read-only) |
| **QA Engineer** | NORMAL | Writes and runs comprehensive tests |
| **Performance Engineer** | LOW | Analyzes and optimizes performance |
| **Documentation Engineer** | LOW | Writes/updates docs, README, API docs |
| **Release Engineer** | LOW | Versioning, changelog, packaging |
| **Research Agent** | NORMAL | Web documentation/solutions research |
| **Reflection Agent** | LOW | Post-mission analysis and lesson extraction |
| **Knowledge Curator** | LOW | Updates knowledge graph and experience DB |

Every agent tracks: priority, state, progress, current task, dependencies, confidence.

## 6. Recovery Engine (Replaces Blind Retries)

**Old behaviour:** Retry → Retry → Retry → Retry  
**New behaviour:** Failure → Classify → Strategy → Recover → Continue

### Failure classification (12 types):
- COMPILATION_ERROR, TEST_FAILURE, LINT_ERROR, TIMEOUT
- TOOL_UNAVAILABLE, API_ERROR, RATE_LIMIT, PERMISSION_DENIED
- FILE_NOT_FOUND, SYNTAX_ERROR, DEPENDENCY_MISSING, NETWORK_ERROR

### Recovery strategies per failure type:
- Compilation: fix syntax, add type annotations, simplify code
- Test failure: fix test, update assertions, skip flaky
- Lint: auto-fix, manual fix
- Timeout: increase timeout, optimize, defer
- Tool unavailable: install tool, use alternative, skip step
- API error: retry auth, use fallback endpoint
- Rate limit: wait and retry, reduce batch size
- Permission: request elevation, use alternative path
- File not found: create file, find alternative location
- Syntax error: fix syntax, rewrite block
- Dependency missing: install dependency, use stdlib
- Network: retry, use cache
- Unknown: retry once, simplify, ask user

## 7. Verification Pipeline

Every engineering task automatically executes:

| Step | Description | Required |
|------|-------------|----------|
| Compile | Python syntax check / TypeScript `--noEmit` | Yes |
| Lint | ruff/ESLint | No (auto-detected) |
| Tests | pytest / npm test | Yes (if tests exist) |
| Static Analysis | mypy | No (auto-detected) |
| Security Scan | Heuristic check | No |
| Formatting | black `--check` | No |
| Documentation | Markdown file presence | No |
| Repository Validation | Structure check | No |

Auto-detects Python and Node.js project types. Pipeline stops on required failures.

## 8. Repository Database (SQLite)

Persistent index stored in `.agent/repo.db`:

| Table | Content |
|-------|---------|
| `files` | File paths, language, lines, hash, last scan |
| `symbols` | Classes, functions, types, interfaces, enums (with line ranges) |
| `imports` | Source imports (relative/third-party) |
| `routes` | API endpoints (path, method, framework) |
| `schemas` | Database models (Prisma, SQLAlchemy, Drizzle) |
| `components` | React/Vue components |
| `tests` | Test names and frameworks |
| `dependencies` | Package dependencies |
| `documentation` | Doc sections and keywords |

**Benefits:** Incremental updates, no full rescan needed.

## 9. Context Intelligence Engine

Instead of dumping the repository into prompts:

```
Repository → ProjectBrain → Symbol Index → Dependency Graph →
Context Ranker → Prompt Builder → LLM
```

### ContextRanker:
- Extracts key terms from the request
- Scores files by relevance (filename, path, content matching)
- Scores symbols from database
- Finds relevant dependencies
- Respects token limits (configurable max_tokens, max_files, max_symbols)
- Builds optimized prompt messages

## 10. Semantic Search

Search by meaning, not just grep/filename:

| Query | Finds |
|-------|-------|
| `Find Authentication` | JWT, middleware, login, refresh token, guards |
| `Find Payment` | Checkout, billing, Stripe, subscription |
| `Find API` | Endpoints, routes, controllers, services |
| `Find Dashboard` | Analytics, metrics, reports |
| `Find User` | Profile, account, members, customers |

### Features:
- Synonym expansion (20+ concept mappings)
- CamelCase splitting
- Cross-table search (symbols, routes, components, tests)
- Relevance scoring with results formatting

## 11. Mission Queue

Manage multiple engineering missions simultaneously:

- QUEUED → RUNNING → PAUSED → WAITING_APPROVAL → BLOCKED → COMPLETED → CANCELLED
- Priority-based scheduling
- Full mission state tracking

## 12. Workspace Manager

One CLI, multiple repositories:

- Add workspaces (`revona workspace <name> <path>`)
- Switch between workspaces
- Independent memory per workspace
- Active workspace tracking

## 13. Checkpoint System

Automatically saves mission state at every phase:

- Mission state + snapshot
- Agent states
- Files changed
- Verification results
- Timestamps

Allows resume after crashes. Stored in `.agent/checkpoints/`.

## 14. Governance & Audit

### Policy Engine:
- Permission levels: READ_ONLY, READ_WRITE, DESTRUCTIVE, ADMIN
- Destructive operation detection (rm -rf, git push --force, etc.)
- Approval gates for high-risk actions

### Audit Logger:
- All agent actions logged to `.agent/audit.jsonl`
- Includes: timestamp, agent, tool, args, result, allowed, duration
- Recent action summary

## 15. Plugin SDK

Install third-party extensions:

```
revona install ./path/to/plugin <name>
```

### Plugin types:
- Agents, Skills, Blueprints, Accelerators
- Themes, Validators, Model Providers
- Memory Providers, Verification Modules, Commands

### Plugin lifecycle:
- `plugin.json` manifest discovery
- Python entry point loading via `importlib`
- Type-based indexing
- Install/uninstall support

## 16. Background Repository Watcher

Monitors file changes in real-time:

- File creation, modification, deletion
- Auto-updates Repository Database
- Change counting and callbacks
- Daemon thread (configurable interval)

## 17. Knowledge Evolution

After every mission, the full Observe→Extract→Update→Rank→Store cycle:

1. **Observe**: Collect working memory observations
2. **Extract**: Run Reflection Agent to extract lessons
3. **Update**: Append to Lessons.md, Decisions.md
4. **Store**: Add to Knowledge Graph (nodes + edges)
5. **Rank**: Store verified solutions in Experience DB with confidence scores
6. **Improve**: Update confidence based on success rate

## 18. TUI — Mission Control Dashboard

Live terminal dashboard with panels:
- **Header** — App name, version, model, company
- **Mission Bar** — Mission name, state (color-coded), progress bar
- **Command Panel** — Input display
- **Engineering Feed** — Timeline with color-coded events (green=success, red=error, cyan=processing)
- **Diagnostics** — Hidden toggle for errors, retries, stack traces
- **Agents Panel** — Agent states with icons and status
- **Active Files** — Recently changed files
- **Knowledge** — Stats: learned, verified, patterns, solutions, capabilities
- **System Health** — Health bar, build status, test %, coverage, risk
- **Confidence** — Per-domain confidence bars
- **Footer** — Status message, ETA, keyboard hints

## 19. Tool Set

| Tool | Description |
|------|-------------|
| `read_file` | Read full file contents |
| `write_file` | Create or overwrite a file |
| `edit_file` | String replacement in a file |
| `list_files` | List directory contents |
| `grep_files` | Substring search across files |
| `run_shell` | Allowed shell commands (with allowlist) |
| `web_fetch` | Fetch URL content |

Shell allowlist: npm, pnpm, yarn, node, python, pip, cargo, go, make, git (status/diff/log), pytest, ruff, black, mypy, tsc, eslint, prettier

## 20. Memory System (5 Layers)

| Layer | Storage | Persistence |
|-------|---------|-------------|
| Working Memory | In-process dict | Ephemeral |
| Project Memory | `AI/*.md` files | Persistent (repo) |
| User Profile | `~/.config/revona/user/profile.json` | Persistent (global) |
| Experience DB | `.agent/experiences/*.json` | Persistent (local) |
| Knowledge Graph | `.agent/knowledge_graph.json` | Persistent (local) |
| Repository DB | `.agent/repo.db` (SQLite) | Persistent (local) |

## 21. Architecture Overview

```
                REVONA CORE
                     |
     ┌───────────────┼──────────────────┐
     │               │                  │
  Commander    Repository Brain     Memory
     │               │                  │
     └─────── Mission Engine ───────────┘
                     |
         Capability Discovery
                     |
          Agent Orchestrator (16 agents)
                     |
     ┌──────┬────────┼─────────┬──────┐
     │      │        │         │      │
  Frontend Backend  QA    Security  DevOps
     │      │        │         │      │
     └──────┴────────┼─────────┘
                     |
            Verification Pipeline
                     |
             Recovery Engine
                     |
             Knowledge Engine
                     |
            Reflection & Learning
                     |
               Mission Complete
```

## 22. Files

| File | Purpose |
|------|---------|
| `agent/__init__.py` | Constants, paths, version |
| `agent/mission_engine.py` | Mission state machine, queue, workspace, checkpoints |
| `agent/capabilities.py` | Capability discovery engine |
| `agent/recovery.py` | Intelligent recovery engine |
| `agent/verification.py` | Verification pipeline |
| `agent/repo_db.py` | SQLite repository database |
| `agent/context_ranker.py` | Context intelligence / prompt builder |
| `agent/semantic_search.py` | Semantic code search |
| `agent/agents.py` | 16 agent role definitions |
| `agent/agent.py` | Agent orchestration, mission engine runner |
| `agent/governance.py` | Policy engine, audit logger |
| `agent/plugin_sdk.py` | Plugin installation and loading |
| `agent/watcher.py` | Background repository file watcher |
| `agent/memory.py` | 5-layer memory system |
| `agent/cli.py` | CLI commands (18 total) |
| `agent/tui.py` | Mission Control TUI dashboard |
| `agent/tools.py` | 7 agent tools |
| `agent/context.py` | Repository context builder |
| `agent/client.py` | OpenAI/NVIDIA API client |
| `agent/config.py` | Config file management |
| `agent/session.py` | Session persistence |
| `agent/progress.py` | Progress display engine |
| `agent/repo_intel.py` | Repository intelligence scanner |
| `agent/skills.py` | Skills/blueprints/accelerators loader |
| `agent/mission.py` | Legacy mission (v1.x compat) |
| `agent/models.py` | Model cache management |
| `agent/terminal.py` | Terminal detection and theming |
| `agent/prompts.py` | Legacy prompt templates |
