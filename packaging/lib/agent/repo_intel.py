from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import AGENT_DIR, IGNORE_DIRS, TEXT_EXTS

INTEL_CACHE_PATH = AGENT_DIR / "repo_intel.json"


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_imports_py(text: str) -> list[str]:
    """Extract local module imports from Python source."""
    imports = []
    for m in re.finditer(r"^\s*(?:from\s+(\S+)\s+import|\bimport\s+(\S+))", text, re.MULTILINE):
        mod = m.group(1) or m.group(2)
        if mod:
            imports.append(mod.split(".")[0])
    return list(set(imports))


def _parse_imports_ts(text: str) -> list[str]:
    """Extract relative/absolute imports from TypeScript/JS source."""
    imports = []
    for m in re.finditer(
        r"""(?:import\s+(?:[\w*{}\s,]+\s+from\s+)?['"])([^'"]+)['"]|require\(['"]([^'"]+)['"]\)""",
        text,
    ):
        path = m.group(1) or m.group(2) or ""
        if path.startswith(".") or path.startswith("/") or path.startswith("@/"):
            imports.append(path)
    return list(set(imports))


def _parse_symbols(text: str, ext: str) -> list[dict]:
    """Extract top-level defined symbols (classes, functions, types)."""
    symbols = []
    ext = ext.lower()

    if ext in (".py",):
        for m in re.finditer(r"^(?:class|def|async def)\s+(\w+)", text, re.MULTILINE):
            symbols.append({"name": m.group(1), "type": "function" if "def" in m.group(0) else "class"})

    elif ext in (".ts", ".tsx", ".js", ".jsx"):
        for m in re.finditer(
            r"^(?:export\s+)?(?:default\s+)?(?:class|function|const|let|var|type|interface|enum)\s+(\w+)",
            text, re.MULTILINE,
        ):
            kw = m.group(0)
            if "class" in kw:
                sym_type = "class"
            elif "function" in kw:
                sym_type = "function"
            elif "type" in kw or "interface" in kw:
                sym_type = "type"
            elif "enum" in kw:
                sym_type = "enum"
            else:
                sym_type = "variable"
            symbols.append({"name": m.group(1), "type": sym_type})

    return symbols


def _detect_framework(path: Path) -> dict[str, str]:
    """Detect frameworks and tools from config files."""
    frameworks = {}
    config_files = {
        "next.config": "Next.js",
        "package.json": None,  # handled below
        "pyproject.toml": None,
        "requirements.txt": None,
        "tsconfig.json": "TypeScript",
        "tailwind.config": "Tailwind CSS",
        "prisma/schema.prisma": "Prisma",
        "docker-compose.yml": "Docker",
        "Dockerfile": "Docker",
        "vite.config": "Vite",
        "astro.config": "Astro",
        "svelte.config": "Svelte",
        "nuxt.config": "Nuxt",
        "angular.json": "Angular",
    }

    for fname, label in config_files.items():
        if list(path.rglob(fname)):
            if label:
                frameworks[label] = fname

    # Check package.json for specific dependencies
    pkg = path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            indicators = {
                "next": "Next.js", "react": "React", "vue": "Vue",
                "@angular/core": "Angular", "svelte": "Svelte",
                "express": "Express", "fastify": "Fastify",
                "prisma": "Prisma", "@prisma/client": "Prisma",
                "vitest": "Vitest", "jest": "Jest",
                "playwright": "Playwright", "tailwindcss": "Tailwind CSS",
                "zod": "Zod", "trpc": "tRPC",
                "graphql": "GraphQL", "apollo-server": "Apollo",
                "typeorm": "TypeORM", "drizzle-orm": "Drizzle",
                "redis": "Redis", "ioredis": "Redis",
                "passport": "Passport", "next-auth": "NextAuth",
                "@auth/core": "Auth.js",
            }
            for dep, label in indicators.items():
                if dep in all_deps:
                    frameworks[label] = f"npm:{dep}"
        except Exception:
            pass

    # Check pyproject.toml
    pyproj = path / "pyproject.toml"
    if pyproj.exists():
        try:
            text = pyproj.read_text(encoding="utf-8")
            py_indicators = {
                "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
                "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic",
                "pytest": "pytest", "alembic": "Alembic",
                "celery": "Celery", "httpx": "httpx",
                "requests": "requests", "click": "Click",
            }
            for dep, label in py_indicators.items():
                if dep in text:
                    frameworks[label] = f"pip:{dep}"
        except Exception:
            pass

    return frameworks


# ---------------------------------------------------------------------------
# API Route detection
# ---------------------------------------------------------------------------

def _detect_routes(path: Path, files: list[Path]) -> list[dict]:
    """Detect API route definitions from common frameworks."""
    routes = []

    # Next.js App Router — route.ts / route.js / page.ts files in app/ dir
    for f in files:
        rel = str(f.relative_to(path).as_posix())
        if "/app/" in rel and f.name in ("route.ts", "route.js", "route.tsx", "route.jsx"):
            verb = "ANY"
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                for v in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    if re.search(rf"(?:^|export\s+)(?:async\s+)?function\s+{v}\b", text, re.MULTILINE) or \
                       re.search(rf"^\s*(?:export\s+)?const\s+{v}\b", text, re.MULTILINE):
                        verb = v
                        break
            except Exception:
                pass
            routes.append({"path": rel.replace("\\", "/"), "method": verb, "type": "nextjs-app-router"})

        # FastAPI routes
        if f.suffix == ".py" and ("route" in f.stem or "api" in f.stem or "endpoint" in f.stem):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'@\w+\.(?:get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']', text):
                    routes.append({"path": m.group(1), "method": "ANY", "type": "fastapi", "file": rel})
            except Exception:
                pass

        # Flask routes
        if f.suffix == ".py" and ("route" in f.stem or "view" in f.stem):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'@\w+\.route\(["\']([^"\']+)["\']', text):
                    routes.append({"path": m.group(1), "method": "ANY", "type": "flask", "file": rel})
            except Exception:
                pass

    return routes


# ---------------------------------------------------------------------------
# Database schema detection
# ---------------------------------------------------------------------------

def _detect_schema(path: Path) -> list[dict]:
    """Detect database models from Prisma, SQLAlchemy, Drizzle, etc."""
    schemas = []

    # Prisma
    for pf in path.rglob("schema.prisma"):
        try:
            text = pf.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"^model\s+(\w+)\s*\{", text, re.MULTILINE):
                schemas.append({"name": m.group(1), "type": "prisma", "file": str(pf)})
        except Exception:
            pass

    # SQLAlchemy models
    for f in path.rglob("models*.py"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"^\s*class\s+(\w+)\(.*?db\.Model.*?\)\s*:", text, re.MULTILINE):
                schemas.append({"name": m.group(1), "type": "sqlalchemy", "file": str(f)})
        except Exception:
            pass

    # Drizzle schema
    for f in path.rglob("schema.ts"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:pgTable|mysqlTable|sqliteTable)\s*\(", text):
                schemas.append({"name": m.group(1), "type": "drizzle", "file": str(f)})
        except Exception:
            pass

    return schemas


# ---------------------------------------------------------------------------
# Component tree (React)
# ---------------------------------------------------------------------------

def _detect_components(path: Path, files: list[Path]) -> list[dict]:
    """Detect React components and their parent-child relationships."""
    components = []
    for f in files:
        if f.suffix not in (".tsx", ".jsx", ".ts", ".js"):
            continue
        rel = str(f.relative_to(path).as_posix())
        if "component" in rel.lower() or "page" in rel.lower():
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                # Detect component definition
                comp_match = re.search(
                    r"(?:export\s+(?:default\s+)?)?(?:function|const)\s+(\w+)\s*(?:=|:|\()",
                    text,
                )
                if comp_match:
                    components.append({
                        "name": comp_match.group(1),
                        "file": rel,
                        "type": "page" if "page." in f.name else "component",
                    })
            except Exception:
                pass
    return components


# ---------------------------------------------------------------------------
# Main ProjectBrain
# ---------------------------------------------------------------------------

class ProjectBrain:
    """Builds and caches a deep understanding of the repository."""

    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._dirty = False

    def build(self, root: Path | None = None) -> dict:
        """Full scan. Returns the intelligence data."""
        root = root or Path(".")
        start = time.time()

        # Collect source files
        files = []
        for ext in TEXT_EXTS:
            files.extend(root.rglob(f"*{ext}"))

        # Filter ignored dirs
        files = [f for f in files if not any(
            part in IGNORE_DIRS or part.startswith(".")
            for part in f.relative_to(root).parts
        )]

        # Architecture: detect frameworks
        frameworks = _detect_framework(root)

        # Structure map
        dir_structure = self._build_structure(root)

        # Import / dependency graph
        dep_graph = self._build_dep_graph(root, files)

        # Symbol index
        symbols = {}
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                syms = _parse_symbols(text, f.suffix)
                if syms:
                    rel = str(f.relative_to(root).as_posix())
                    symbols[rel] = syms
            except Exception:
                pass

        # API routes
        routes = _detect_routes(root, files)

        # Database schemas
        schemas = _detect_schema(root)

        # Component tree
        components = _detect_components(root, files)

        # File statistics
        total_lines = 0
        total_size = 0
        for f in files:
            try:
                total_lines += sum(1 for _ in f.open(encoding="utf-8", errors="replace"))
                total_size += f.stat().st_size
            except Exception:
                pass

        self._cache = {
            "frameworks": frameworks,
            "dir_structure": dir_structure,
            "dep_graph": dep_graph,
            "symbols": symbols,
            "routes": routes,
            "schemas": schemas,
            "components": components,
            "stats": {
                "files": len(files),
                "lines": total_lines,
                "size_kb": total_size // 1024,
                "scan_ms": int((time.time() - start) * 1000),
            },
            "built_at": time.time(),
        }
        self._dirty = True
        self._save()
        return self._cache

    def load(self, root: Path | None = None) -> dict:
        """Load from cache or build if missing."""
        if self._cache:
            return self._cache
        if INTEL_CACHE_PATH.exists():
            try:
                data = json.loads(INTEL_CACHE_PATH.read_text(encoding="utf-8"))
                # Auto-rebuild if cache is older than 1 hour
                if time.time() - data.get("built_at", 0) < 3600:
                    self._cache = data
                    return self._cache
            except Exception:
                pass
        return self.build(root)

    def context_block(self, max_depth: int = 3) -> str:
        """Return a compressed context block for prompts."""
        if not self._cache:
            return ""

        parts = ["## Project Brain (Repository Intelligence)"]

        # Framework summary
        fw = self._cache.get("frameworks", {})
        if fw:
            parts.append("### Stack\n" + "\n".join(f"- {k}" for k in sorted(fw.keys())))

        # Stats
        stats = self._cache.get("stats", {})
        if stats:
            parts.append(f"### Stats\n- {stats.get('files',0)} files, {stats.get('lines',0)} lines, {stats.get('size_kb',0)}KB")

        # Directory structure (compressed)
        structure = self._cache.get("dir_structure", "")
        if structure:
            lines = structure.split("\n")
            if len(lines) > 60:
                lines = lines[:max_depth * 15] + ["  ..."]
            parts.append("### Structure\n" + "\n".join(lines))

        # API routes
        routes = self._cache.get("routes", [])
        if routes:
            parts.append("### API Routes\n" + "\n".join(
                f"- {r['method']:6s} {r['path']}" for r in routes[:20]
            ))

        # Database schemas
        schemas = self._cache.get("schemas", [])
        if schemas:
            parts.append("### Database Models\n" + "\n".join(
                f"- {s['name']} ({s['type']})" for s in schemas[:10]
            ))

        # Components
        components = self._cache.get("components", [])
        if components:
            parts.append("### Components\n" + "\n".join(
                f"- {c['name']} ({c['type']})" for c in components[:20]
            ))

        return "\n".join(parts)

    def query_symbol(self, name: str) -> list[dict]:
        """Find where a symbol is defined."""
        results = []
        for file, syms in self._cache.get("symbols", {}).items():
            for s in syms:
                if name.lower() in s["name"].lower():
                    results.append({"file": file, "symbol": s})
        return results

    def dependencies_of(self, file: str) -> list[str]:
        """List files that depend on the given file."""
        return self._cache.get("dep_graph", {}).get(file, [])

    def affected_files(self, changed_file: str) -> list[str]:
        """BFS to find all files transitively affected by a change."""
        graph = self._cache.get("dep_graph", {})
        affected = []
        visited = {changed_file}
        queue = [changed_file]
        while queue:
            current = queue.pop(0)
            for dep_file, deps in graph.items():
                if dep_file in visited:
                    continue
                if current in deps:
                    visited.add(dep_file)
                    affected.append(dep_file)
                    queue.append(dep_file)
        return affected

    def _build_structure(self, root: Path, max_files_per_dir: int = 15) -> str:
        """Build an indented directory listing."""
        lines = []
        for d in sorted(root.iterdir()):
            if d.name.startswith(".") or d.name in IGNORE_DIRS:
                continue
            if d.is_dir():
                lines.append(f"  {d.name}/")
                sub = sorted(d.iterdir())[:max_files_per_dir]
                for s in sub:
                    if s.name.startswith("."):
                        continue
                    if s.is_dir():
                        lines.append(f"    {s.name}/")
                    else:
                        lines.append(f"    {s.name}")
                if len(list(d.iterdir())) > max_files_per_dir:
                    lines.append("    ...")
            else:
                lines.append(f"  {d.name}")
        return "\n".join(lines)

    def _build_dep_graph(self, root: Path, files: list[Path]) -> dict[str, list[str]]:
        """Build a dependency graph: file -> [files it depends on]."""
        graph: dict[str, list[str]] = {}
        file_map: dict[str, Path] = {}
        for f in files:
            rel = str(f.relative_to(root).as_posix())
            file_map[rel] = f
            graph[rel] = []

        for rel, f in file_map.items():
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            if f.suffix == ".py":
                imports = _parse_imports_py(text)
            elif f.suffix in (".ts", ".tsx", ".js", ".jsx"):
                imports = _parse_imports_ts(text)
            else:
                imports = []

            for imp in imports:
                # Try to resolve relative imports
                if imp.startswith(".") or imp.startswith("/") or imp.startswith("@/"):
                    for candidate in file_map:
                        if imp.split("/")[-1] in candidate or imp.replace("@/", "") in candidate:
                            graph[rel].append(candidate)
                else:
                    # Third-party imports: try to find local files matching module name
                    for candidate in file_map:
                        if candidate.replace("\\", "/").startswith(imp.replace(".", "/")) or \
                           candidate.replace("/", ".").startswith(imp):
                            graph[rel].append(candidate)
        return graph

    def _save(self) -> None:
        if self._dirty:
            AGENT_DIR.mkdir(parents=True, exist_ok=True)
            INTEL_CACHE_PATH.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")
            self._dirty = False
