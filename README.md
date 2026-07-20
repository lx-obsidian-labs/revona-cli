# Revona CLI

**Autonomous Software Engineering Operating System** — v2.2.0

Built by [LX Obsidian Labs](https://github.com/lx-obsidian-labs)

Revona is an AI-powered CLI agent that plans, builds, tests, and documents software projects autonomously. It features 16 specialist agents, 15 tool types, a full mission state machine, parallel worker execution, and a rich terminal dashboard.

---

## Quick Start

```bash
# Install
pip install revona

# Set your NVIDIA NIM API key
export NVIDIA_API_KEY="nvapi-..."

# Launch interactive mode
revona

# Or run a single prompt
revona run "add user authentication with JWT"
```

### Requirements

- Python 3.11+
- NVIDIA NIM API key ([get one here](https://build.nvidia.com/))

### Dependencies

| Package | Version |
|---------|---------|
| openai | >=1.30 |
| click | >=8.1 |
| rich | >=13.0 |
| requests | >=2.31 |

---

## Features at a Glance

| Feature | Description |
|---------|-------------|
| 16 Specialist Agents | Commander, Planners, Engineers (Frontend/Backend/DB/DevOps/Security/QA), Docs, Release, Reflection |
| 15 Tool Types | File read/write/edit, search, shell, web fetch, move/copy/delete, tree, file info, find, git status |
| Mission State Machine | 13 ordered states from DISCOVERY through EXECUTION to REFLECTION |
| Parallel Workers | Decompose plans into DAGs and run 4+ concurrent agent workers |
| Intelligence Engine | 5-layer memory: Working, Project, User Profile, Experience DB, Knowledge Graph |
| Repository Database | SQLite index of files, symbols, imports, routes, schemas, components |
| Semantic Search | Concept-based code search with 20+ synonym mappings |
| Rich TUI Dashboard | Real-time cockpit with confidence scores, health metrics, agent status |
| Session Management | Save, resume, search, and list previous sessions |
| Verification Pipeline | Auto-detect project type, run compile/lint/test/security checks |
| Recovery Engine | Classifies 13 failure types with specific recovery strategies |
| Governance & Audit | Policy engine with 4 permission levels, full audit trail |
| Plugin System | Install and manage plugins from local paths |
| Skills & Blueprints | Reusable procedural and architectural knowledge |

---

## Installation

```bash
# From PyPI
pip install revona

# From source
git clone https://github.com/lx-obsidian-labs/revona-cli.git
cd revona-cli
pip install -e .
```

---

## Configuration

```bash
# Set API key (recommended via environment variable)
export NVIDIA_API_KEY="nvapi-..."

# Set default model
revona config --model deepseek-ai/deepseek-v4-pro

# View current config
revona config

# Refresh model cache from NVIDIA
revona refresh
```

Config is stored in `.agent/config.json`. The API key should be set via environment variable for security.

---

## Usage

### Interactive Mode

Launch the full TUI dashboard:

```bash
revona
# or with model override
revona -m deepseek-ai/deepseek-v4-pro
```

### Non-Interactive Mode

```bash
# Run a single prompt and exit
revona run "create a REST API with Express and Prisma"

# Plan + execute with approval prompt
revona build "add dark mode toggle to settings page"

# Full mission lifecycle
revona mission "refactor database layer to use connection pooling" --priority high

# Parallel execution with 4 workers
revona workers "implement the checkout flow: cart, payment, confirmation" -w 4
```

---

## CLI Commands

| Command | Description | Options |
|---------|-------------|---------|
| `revona` | Launch interactive TUI cockpit | `--model/-m`, `--no-banner`, `--version` |
| `revona mission <request>` | Start a full engineering mission | `--model/-m`, `--yes/-y`, `--priority/-p` (low/normal/high/critical), `--parallel/-P`, `--workers/-w` |
| `revona run <prompt>` | Execute a prompt non-interactively | `--model/-m` |
| `revona build <prompt>` | Plan then execute with approval | `--model/-m`, `--yes/-y`, `--parallel/-P`, `--workers/-w` |
| `revona workers <request>` | Run in parallel worker mode | `--model/-m`, `--workers/-w`, `--yes/-y` |
| `revona config` | View or set configuration | `--key`, `--model/-m`, `--list-models` |
| `revona models` | List cached NVIDIA NIM models | `--search/-s`, `--category/-c` |
| `revona refresh` | Refresh cached model list | — |
| `revona search <query>` | Semantic code search | `--top/-k` |
| `revona verify` | Run verification pipeline | `--root` |
| `revona discover` | Discover system capabilities | — |
| `revona recovery` | Show recovery engine history | — |
| `revona queue` | Show mission queue | — |
| `revona workspace` | Manage workspaces | `name`, `path` |
| `revona checkpoints` | List checkpoints | — |
| `revona install <source> <name>` | Install a plugin | — |

---

## Slash Commands (Interactive Mode)

Type these in the interactive session:

### General

| Command | Description |
|---------|-------------|
| `/help` | List all commands |
| `/exit`, `/quit`, `/q` | Exit session |
| `/plan` | Toggle plan-only mode (no tool execution) |
| `/undo` | Undo last assistant response |
| `/redo` | Redo previously undone response |

### Model & Config

| Command | Description |
|---------|-------------|
| `/change model <id>` | Switch model mid-session |
| `/models [keyword]` | Browse/search cached models |
| `/save` | Save current model as default |

### Intelligence

| Command | Description |
|---------|-------------|
| `/init` | Index repository (SQLite DB + context) |
| `/refresh` | Reload context from disk |
| `/context` | Show loaded context stats |
| `/brain` | Show repository intelligence summary |
| `/search <query>` | Semantic search across codebase |
| `/capabilities` | Discover system capabilities |
| `/skills [keyword]` | List/query skills, blueprints, accelerators |

### Missions & Workers

| Command | Description |
|---------|-------------|
| `/mission` | Show current mission status |
| `/workers <request>` | Run parallel mission with 4 workers |
| `/queue` | Show mission queue |
| `/verify` | Run verification pipeline |
| `/recovery` | Show recovery history |

### Sessions

| Command | Description |
|---------|-------------|
| `/sessions` | List saved sessions |
| `/resume <id>` | Resume a previous session |
| `/history [n]` | Show last N exchanges |

### File Management

| Command | Description |
|---------|-------------|
| `/tree [path] [depth]` | Show directory tree with sizes |
| `/find <pattern>` | Find files by glob pattern |
| `/filestats [path]` | Show file/directory statistics |
| `/gitstatus` | Show git status (modified, untracked) |
| `/mv <src> <dst>` | Move/rename a file |
| `/cp <src> <dst>` | Copy a file |
| `/rm <path>` | Delete a file (with confirmation) |
| `/mkdir <path>` | Create a directory |

### File References

| Command | Description |
|---------|-------------|
| `@filename` | Inline file content in your prompt (e.g. `@src/main.py fix the bug`) |

---

## Agent Tools

These are available to agents during execution:

| Tool | Description | Parameters |
|------|-------------|------------|
| `read_file` | Read full file contents | `path` |
| `write_file` | Create or overwrite a file | `path`, `content` |
| `edit_file` | Search-and-replace in file (with fuzzy hints on failure) | `path`, `old`, `new` |
| `list_files` | List directory contents with sizes | `path` |
| `grep_files` | Substring search across files | `pattern`, `path` |
| `run_shell` | Run allowed shell command | `command`, `cwd` |
| `web_fetch` | Fetch URL content | `url` |
| `move_file` | Move/rename file | `source`, `destination` |
| `copy_file` | Copy file or directory | `source`, `destination` |
| `delete_file` | Delete file or directory | `path` |
| `mkdir` | Create directory | `path` |
| `tree` | Recursive directory tree | `path`, `depth` |
| `file_info` | File metadata (size, dates, permissions, lines) | `path` |
| `find_files` | Glob-based file finder | `pattern`, `path` |
| `git_status` | Git status grouped by type | `path` |

**Shell allowlist:** npm, pnpm, yarn, node, python, python3, pytest, pip, cargo, go, make, git status/diff/log, ls, cat, type, ruff, black, mypy, tsc, eslint, prettier

---

## Agents

16 specialist roles, each with tool restrictions and domain expertise:

### Planning & Analysis (Read-Only)

| Agent | Description |
|-------|-------------|
| **Commander** | Top-level orchestrator — breaks missions into tasks, assigns agents, monitors progress |
| **Mission Planner** | Creates detailed engineering plans with dependencies |
| **Repository Analyst** | Analyzes structure, frameworks, dependencies, API endpoints |
| **Architecture Agent** | Designs system architecture for new features |
| **Research Agent** | Searches web for documentation, APIs, and solutions |

### Engineering (Read/Write)

| Agent | Description |
|-------|-------------|
| **Frontend Engineer** | Builds/modifies frontend code (React, Vue, Svelte, etc.) |
| **Backend Engineer** | Builds/modifies backend code (APIs, services, data layer) |
| **Database Engineer** | Designs/modifies schemas, migrations, queries |
| **DevOps Engineer** | Manages Docker, CI/CD, deployment configs |
| **Security Engineer** | Audits code for vulnerabilities |
| **QA Engineer** | Writes and runs comprehensive tests |
| **Builder** | General-purpose code executor |

### Support (Read/Write)

| Agent | Description |
|-------|-------------|
| **Performance Engineer** | Analyses and optimises code performance |
| **Documentation Engineer** | Writes/updates docs, README, API docs |
| **Release Engineer** | Manages versioning, changelog, build, packaging |

### Meta (Read-Only)

| Agent | Description |
|-------|-------------|
| **Reflection Agent** | Analyses completed missions, extracts lessons |
| **Knowledge Curator** | Updates knowledge graph, experience DB, project memory |

---

## Mission State Machine

A mission progresses through 13 ordered states:

```
MISSION_CREATED
    ↓
DISCOVERY → CAPABILITY_DISCOVERY → REPOSITORY_ANALYSIS
    ↓
ARCHITECTURE → PLANNING → WAITING_APPROVAL
    ↓
EXECUTION → VALIDATION → SECURITY_REVIEW
    ↓
DOCUMENTATION → REFLECTION → MISSION_COMPLETE
```

Each state has:
- An `execute()` method that runs the state's logic
- A `transition_to()` guard that validates the next state
- Thread-safe state transitions with history tracking

### Mission Priority

| Priority | Description |
|----------|-------------|
| `LOW` | Background tasks, documentation |
| `NORMAL` | Standard feature work (default) |
| `HIGH` | Important features, bug fixes |
| `CRITICAL` | Security patches, production issues |

---

## Memory System

5-layer intelligence architecture:

### Layer 1: Working Memory
Ephemeral in-process dict. Tracks current task, open files, errors, plan, symbols, observations. Reset each session.

### Layer 2: Project Memory
Persistent `AI/*.md` files:
- `Architecture.md` — System architecture decisions
- `Coding Standards.md` — Code style conventions
- `Lessons.md` — Extracted lessons from past missions
- `Decisions.md` — Key technical decisions
- `Roadmap.md` — Planned features
- `Bugs.md` — Known issues
- `API Index.md` — API endpoint registry

### Layer 3: User Profile
Global `~/.config/revona/user/profile.json` + local `.user/profile.json`:
```json
{
  "name": "Nathan",
  "preferred_stack": ["TypeScript", "Next.js", "Prisma", "Tailwind"],
  "principles": ["clean code", "type safety"]
}
```

### Layer 4: Experience Memory
ExperienceDB stores problem → root-cause → solution records with:
- Confidence scoring (0.0–1.0)
- Reuse tracking (times applied, success rate)
- Search by keywords, confidence threshold

### Layer 5: Knowledge Graph
Node-edge graph in `.agent/knowledge_graph.json`:
- **KNode:** id, label, type (file/function/class/module/concept), attributes
- **KEdge:** source, target, relation (contains/imports/calls/depends/extends)

### After-Mission Cycle
```
Mission Complete → Observe results → Reflection Agent analyzes
    → Extract lessons → Store in Experience DB + Knowledge Graph
    → Update Lessons.md / Decisions.md → Improve confidence scores
```

---

## Repository Database

SQLite index in `.agent/repo.db` with 8 tables:

| Table | Contents |
|-------|----------|
| `files` | Path, language, lines, size, hash, mtime |
| `symbols` | Classes, functions, types, enums with line numbers |
| `imports` | Import statements and their sources |
| `routes` | API routes/endpoints |
| `schemas` | Database schemas |
| `components` | UI components |
| `tests` | Test files and what they test |
| `dependencies` | Package dependencies |

Queries: `query_symbols()`, `query_imports()`, `query_routes()`, `query_components()`, `query_tests()`, `query_dependencies()`, `search_keyword()`

---

## Parallel Workers

Decompose a plan into a DAG and run concurrent agents:

```bash
# Via slash command
/workers implement the checkout flow: cart, payment, confirmation page

# Via CLI
revona workers "implement the checkout flow" -w 4
```

**TaskGraph** resolves dependencies:
- Tasks with no unmet dependencies → ready to run
- Tasks with failed dependencies → skipped
- Thread pool executes ready tasks concurrently

**Task statuses:** PENDING → QUEUED → RUNNING → COMPLETED / FAILED / SKIPPED

---

## Verification Pipeline

Auto-detects project type and runs appropriate checks:

| Step | Description | Required |
|------|-------------|----------|
| Compile | Syntax/type check | Yes |
| Lint | ruff (Python) / ESLint (JS) | Yes |
| Tests | pytest / npm test | Yes |
| Static Analysis | mypy type checking | No |
| Security Audit | Dependency vulnerability scan | No |
| Formatting | black (Python) / prettier (JS) | No |
| Documentation | README presence check | No |

---

## Recovery Engine

Classifies failures into 13 types with specific recovery strategies:

| Failure Type | Strategies |
|-------------|-----------|
| COMPILATION_ERROR | fix_syntax, add_type_annotations, simplify |
| TEST_FAILURE | fix_assertions, add_fixtures, mock_external |
| LINT_ERROR | fix_formatting, remove_unused, refactor |
| TIMEOUT | optimize_hot_path, add_caching, parallelize |
| TOOL_UNAVAILABLE | install_tool, use_alternative, skip_gracefully |
| API_ERROR | retry_with_backoff, check_auth, simplify_payload |
| RATE_LIMIT | wait_and_retry, batch_requests, cache_response |
| PERMISSION_DENIED | check_permissions, run_as_user, escalate |
| FILE_NOT_FOUND | create_file, check_path, search_alternative |
| SYNTAX_ERROR | fix_syntax, check_encoding, validate_json |
| DEPENDENCY_MISSING | install_package, add_to_requirements, mock |
| NETWORK_ERROR | retry, check_connectivity, use_cache |
| UNKNOWN | log_and_escalate, retry_once, skip |

Tracks strategy attempts per context to avoid infinite loops.

---

## Governance & Audit

### Policy Engine

4 permission levels:

| Level | Capabilities |
|-------|-------------|
| `READ_ONLY` | read_file, list_files, grep_files, find_files, file_info, tree, git_status |
| `READ_WRITE` | + write_file, edit_file, move_file, copy_file, mkdir |
| `DESTRUCTIVE` | + delete_file, run_shell |
| `ADMIN` | Full access |

Blocked patterns: `rm -rf`, `git push --force`, `drop table`, `shutdown`, `format`, etc.

### Audit Trail

All tool calls logged to `.agent/audit.jsonl`:
```json
{
  "timestamp": 1721481600.0,
  "agent": "builder",
  "action": "tool_call",
  "tool": "write_file",
  "args": {"path": "src/main.py", "content": "..."},
  "result": "Wrote src/main.py (1234 bytes)",
  "allowed": true,
  "duration_ms": 12.5
}
```

---

## TUI Dashboard

The interactive mode launches a rich terminal UI with:

| Panel | Content |
|-------|---------|
| **Header** | App name, version, active model, intelligence orb |
| **Mission Bar** | Current state, progress bar, task count |
| **Input** | User prompt with tab completion for slash commands |
| **Feed** | Timeline of events, messages, tool calls |
| **Agents** | Status of each specialist agent (idle/running/error) |
| **Workers** | Active parallel workers with task descriptions |
| **Health** | Engineering pulse: health, risk, velocity, quality, build status |
| **Stats** | Knowledge stats, memory counts, session info |
| **Footer** | Version, keyboard shortcuts |

**Intelligence Orb** animates based on agent state: thinking, planning, coding, idle, done.

**Confidence Engine** tracks per-domain scores:
- Architecture, Verification, Tests, Security, Documentation, Context Quality
- Displayed as percentage bars with overall average

---

## Skills & Blueprints

### Skills (`Skills/<name>/`)
Procedural knowledge with:
- `skill.json` — Name, description, keywords
- `instructions.md` — Step-by-step guide
- `best-practices.md` — Do's and don'ts
- `verification.md` — How to verify success

### Blueprints (`Blueprints/<name>/`)
Architectural knowledge with:
- `blueprint.json` — Name, description, keywords
- `architecture.md` — System design
- `schema.md` — Data models
- `modules.md` — Module breakdown

### Accelerators (`Accelerators/<name>/`)
Reusable assets with:
- `manifest.json` — Name, description, referenced files
- Referenced files (templates, configs, scripts)

---

## Plugin System

```bash
# Install a plugin
revona install /path/to/plugin my-plugin

# Plugins extend capabilities via the PluginSDK
```

---

## File Structure

```
.agent/
├── audit.jsonl          # Audit trail
├── config.json          # Configuration
├── checkpoints/         # Mission snapshots
├── sessions/            # Session history (JSONL)
├── repo.db              # Repository SQLite index
├── knowledge_graph.json # Knowledge graph
├── experience_db.json   # Experience memory
├── index.txt            # Context builder output
└── lessons/             # Extracted lessons

.user/
└── profile.json         # Local user preferences

AI/
├── Architecture.md      # System architecture
├── Coding Standards.md  # Code conventions
├── Lessons.md           # Extracted lessons
├── Decisions.md         # Technical decisions
├── Roadmap.md           # Planned features
├── Bugs.md              # Known issues
└── API Index.md         # API endpoints
```

---

## Development

```bash
# Clone and install in dev mode
git clone https://github.com/lx-obsidian-labs/revona-cli.git
cd revona-cli
pip install -e .

# Run
revona
```

---

## License

MIT License — Copyright (c) 2025 LX Obsidian Labs

---

## Links

- **Repository:** https://github.com/lx-obsidian-labs/revona-cli
- **Issues:** https://github.com/lx-obsidian-labs/revona-cli/issues
- **PyPI:** https://pypi.org/project/revona/
