from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable

from . import AGENT_DIR, IGNORE_DIRS, TEXT_EXTS

DB_PATH = AGENT_DIR / "repo.db"


# ---------------------------------------------------------------------------
# Repository Database
#
# Persists:
#   - classes, functions, interfaces, enums, imports
#   - routes, components, schemas, tests
#   - packages, dependencies, symbols, documentation
#
# Stored in SQLite for fast incremental queries.
# Avoid rescanning entire repositories.
# ---------------------------------------------------------------------------

class RepositoryDatabase:
    """SQLite-backed persistent repository index."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH
        self._conn: sqlite3.Connection | None = None
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        if self._initialized:
            return
        conn = self._connect()
        conn.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;

            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                language TEXT,
                lines INTEGER DEFAULT 0,
                size INTEGER DEFAULT 0,
                hash TEXT,
                last_scanned REAL,
                created_at REAL DEFAULT (julianday('now'))
            );

            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER REFERENCES files(id),
                name TEXT NOT NULL,
                symbol_type TEXT NOT NULL,
                line_start INTEGER,
                line_end INTEGER,
                parent TEXT,
                visibility TEXT DEFAULT 'public',
                doc_comment TEXT
            );

            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER REFERENCES files(id),
                source TEXT NOT NULL,
                symbol TEXT,
                is_relative INTEGER DEFAULT 0,
                is_third_party INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER REFERENCES files(id),
                path TEXT NOT NULL,
                method TEXT DEFAULT 'ANY',
                framework TEXT,
                handler TEXT
            );

            CREATE TABLE IF NOT EXISTS schemas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER REFERENCES files(id),
                name TEXT NOT NULL,
                schema_type TEXT,
                fields TEXT
            );

            CREATE TABLE IF NOT EXISTS components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER REFERENCES files(id),
                name TEXT NOT NULL,
                component_type TEXT,
                props TEXT
            );

            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER REFERENCES files(id),
                name TEXT NOT NULL,
                framework TEXT,
                status TEXT DEFAULT 'unknown'
            );

            CREATE TABLE IF NOT EXISTS dependencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version TEXT,
                dependency_type TEXT,
                source_file TEXT,
                UNIQUE(name, source_file)
            );

            CREATE TABLE IF NOT EXISTS documentation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER REFERENCES files(id),
                section TEXT,
                content TEXT,
                keywords TEXT
            );

            CREATE TABLE IF NOT EXISTS scan_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
            CREATE INDEX IF NOT EXISTS idx_symbols_type ON symbols(symbol_type);
            CREATE INDEX IF NOT EXISTS idx_imports_source ON imports(source);
            CREATE INDEX IF NOT EXISTS idx_routes_path ON routes(path);
            CREATE INDEX IF NOT EXISTS idx_components_name ON components(name);
            CREATE INDEX IF NOT EXISTS idx_tests_name ON tests(name);
            CREATE INDEX IF NOT EXISTS idx_deps_name ON dependencies(name);
        """)
        self._initialized = True

    def _get_or_create_file(self, path: str, language: str = "", lines: int = 0, size: int = 0) -> int:
        conn = self._connect()
        cur = conn.execute("SELECT id FROM files WHERE path = ?", (path,))
        row = cur.fetchone()
        if row:
            conn.execute(
                "UPDATE files SET lines=?, size=?, last_scanned=? WHERE id=?",
                (lines, size, time.time(), row["id"]),
            )
            return row["id"]
        conn.execute(
            "INSERT INTO files (path, language, lines, size, last_scanned) VALUES (?, ?, ?, ?, ?)",
            (path, language, lines, size, time.time()),
        )
        return conn.lastrowid

    def index_file(self, file_path: Path, root: Path) -> dict | None:
        """Index a single file into the database. Returns indexed data or None."""
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        rel = str(file_path.relative_to(root).as_posix())
        suffix = file_path.suffix.lower()
        lines = text.count("\n") + 1
        size = len(text)

        self.initialize()
        file_id = self._get_or_create_file(rel, suffix.lstrip("."), lines, size)
        conn = self._connect()

        # Clear old data for this file
        for table in ("symbols", "imports", "routes", "components", "tests"):
            conn.execute(f"DELETE FROM {table} WHERE file_id = ?", (file_id,))

        data = {"file": rel, "symbols": [], "imports": [], "routes": [], "components": [], "tests": []}

        # Parse symbols
        if suffix in (".py",):
            data["symbols"] = self._index_python(text, file_id, conn)
        elif suffix in (".ts", ".tsx", ".js", ".jsx"):
            data["symbols"] = self._index_typescript(text, file_id, conn)

        # Parse imports
        data["imports"] = self._index_imports(text, suffix, file_id, conn)

        # Parse routes
        if suffix == ".py":
            data["routes"] = self._index_routes_python(text, rel, file_id, conn)
        elif suffix in (".ts", ".tsx", ".js", ".jsx"):
            data["routes"] = self._index_routes_js(text, rel, suffix, file_id, conn)

        # Parse components
        if suffix in (".tsx", ".jsx"):
            data["components"] = self._index_components(text, rel, file_id, conn)

        # Detect test files
        if "test" in file_path.stem.lower() or "spec" in file_path.stem.lower():
            framework = "pytest" if suffix == ".py" else "jest"
            for match in self._find_test_names(text, suffix):
                conn.execute(
                    "INSERT INTO tests (file_id, name, framework) VALUES (?, ?, ?)",
                    (file_id, match, framework),
                )
                data["tests"].append({"name": match, "framework": framework})

        conn.commit()
        return data

    def _index_python(self, text: str, file_id: int, conn) -> list[dict]:
        import re
        symbols = []
        for m in re.finditer(r"^(?:class|def|async def)\s+(\w+)", text, re.MULTILINE):
            kind = "function" if "def" in m.group(0) else "class"
            conn.execute(
                "INSERT INTO symbols (file_id, name, symbol_type, line_start) VALUES (?, ?, ?, ?)",
                (file_id, m.group(1), kind, text[:m.start()].count("\n") + 1),
            )
            symbols.append({"name": m.group(1), "type": kind})
        return symbols

    def _index_typescript(self, text: str, file_id: int, conn) -> list[dict]:
        import re
        symbols = []
        for m in re.finditer(
            r"^(?:export\s+)?(?:default\s+)?(?:class|function|const|let|var|type|interface|enum)\s+(\w+)",
            text, re.MULTILINE,
        ):
            kw = m.group(0)
            if "class" in kw:
                kind = "class"
            elif "function" in kw:
                kind = "function"
            elif "type" in kw or "interface" in kw:
                kind = "type"
            elif "enum" in kw:
                kind = "enum"
            else:
                kind = "variable"
            conn.execute(
                "INSERT INTO symbols (file_id, name, symbol_type, line_start) VALUES (?, ?, ?, ?)",
                (file_id, m.group(1), kind, text[:m.start()].count("\n") + 1),
            )
            symbols.append({"name": m.group(1), "type": kind})
        return symbols

    def _index_imports(self, text: str, suffix: str, file_id: int, conn) -> list[dict]:
        import re
        imports = []
        if suffix == ".py":
            for m in re.finditer(r"^\s*(?:from\s+(\S+)\s+import|\bimport\s+(\S+))", text, re.MULTILINE):
                src = m.group(1) or m.group(2)
                if src:
                    is_rel = 0
                    is_third = 0
                    conn.execute(
                        "INSERT INTO imports (file_id, source, is_relative, is_third_party) VALUES (?, ?, ?, ?)",
                        (file_id, src.split(".")[0], is_rel, is_third),
                    )
                    imports.append({"source": src.split(".")[0]})
        elif suffix in (".ts", ".tsx", ".js", ".jsx"):
            for m in re.finditer(r"""(?:import\s+(?:[\w*{}\s,]+\s+from\s+)?['"])([^'"]+)['"]""", text):
                src = m.group(1)
                is_rel = 1 if src.startswith((".", "/", "@")) else 0
                conn.execute(
                    "INSERT INTO imports (file_id, source, is_relative, is_third_party) VALUES (?, ?, ?, ?)",
                    (file_id, src, is_rel, 0),
                )
                imports.append({"source": src})
        return imports

    def _index_routes_python(self, text: str, rel: str, file_id: int, conn) -> list[dict]:
        import re
        routes = []
        for m in re.finditer(r'@\w+\.(?:get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']', text):
            conn.execute(
                "INSERT INTO routes (file_id, path, method, framework, handler) VALUES (?, ?, ?, ?, ?)",
                (file_id, m.group(1), "ANY", "fastapi/flask", rel),
            )
            routes.append({"path": m.group(1)})
        return routes

    def _index_routes_js(self, text: str, rel: str, suffix: str, file_id: int, conn) -> list[dict]:
        import re
        routes = []
        for v in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            if re.search(rf"(?:^|export\s+)(?:async\s+)?function\s+{v}\b", text, re.MULTILINE) or \
               re.search(rf"^\s*(?:export\s+)?const\s+{v}\b", text, re.MULTILINE):
                conn.execute(
                    "INSERT INTO routes (file_id, path, method, framework, handler) VALUES (?, ?, ?, ?, ?)",
                    (file_id, rel, v, "nextjs", rel),
                )
                routes.append({"path": rel, "method": v})
        return routes

    def _index_components(self, text: str, rel: str, file_id: int, conn) -> list[dict]:
        import re
        comps = []
        m = re.search(r"(?:export\s+(?:default\s+)?)?(?:function|const)\s+(\w+)\s*(?:=|:|\()", text)
        if m:
            ctype = "page" if "page." in rel else "component"
            conn.execute(
                "INSERT INTO components (file_id, name, component_type) VALUES (?, ?, ?)",
                (file_id, m.group(1), ctype),
            )
            comps.append({"name": m.group(1), "type": ctype})
        return comps

    def _find_test_names(self, text: str, suffix: str) -> list[str]:
        import re
        names = []
        for m in re.finditer(r"^(?:def |async def |it\s*\(|test\s*\()\s*['\"]?(\w+)", text, re.MULTILINE):
            names.append(m.group(1))
        return names

    def remove_file(self, path: str) -> None:
        conn = self._connect()
        cur = conn.execute("SELECT id FROM files WHERE path = ?", (path,))
        row = cur.fetchone()
        if row:
            fid = row["id"]
            for table in ("symbols", "imports", "routes", "schemas", "components", "tests", "documentation"):
                conn.execute(f"DELETE FROM {table} WHERE file_id = ?", (fid,))
            conn.execute("DELETE FROM files WHERE id = ?", (fid,))
            conn.commit()

    def scan_repository(self, root: Path) -> int:
        """Full repository scan. Returns number of files indexed."""
        self.initialize()
        count = 0
        for ext in TEXT_EXTS:
            for f in root.rglob(f"*{ext}"):
                if any(part in IGNORE_DIRS or part.startswith(".") for part in f.relative_to(root).parts):
                    continue
                if self.index_file(f, root):
                    count += 1
        conn = self._connect()
        conn.execute("INSERT OR REPLACE INTO scan_meta (key, value) VALUES (?, ?)",
                     ("last_scan", str(time.time())))
        conn.execute("INSERT OR REPLACE INTO scan_meta (key, value) VALUES (?, ?)",
                     ("root", str(root)))
        conn.commit()
        return count

    # -----------------------------------------------------------------------
    # Queries
    # -----------------------------------------------------------------------

    def query_symbols(self, name: str, symbol_type: str | None = None) -> list[dict]:
        conn = self._connect()
        if symbol_type:
            rows = conn.execute(
                """SELECT s.*, f.path FROM symbols s JOIN files f ON s.file_id = f.id
                   WHERE s.name LIKE ? AND s.symbol_type = ? ORDER BY s.name""",
                (f"%{name}%", symbol_type),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT s.*, f.path FROM symbols s JOIN files f ON s.file_id = f.id
                   WHERE s.name LIKE ? ORDER BY s.name""",
                (f"%{name}%",),
            ).fetchall()
        return [dict(r) for r in rows]

    def query_imports(self, source: str) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            """SELECT i.*, f.path FROM imports i JOIN files f ON i.file_id = f.id
               WHERE i.source LIKE ? ORDER BY i.source""",
            (f"%{source}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_routes(self, path_filter: str = "") -> list[dict]:
        conn = self._connect()
        if path_filter:
            rows = conn.execute(
                """SELECT r.*, f.path as file_path FROM routes r JOIN files f ON r.file_id = f.id
                   WHERE r.path LIKE ? ORDER BY r.path""",
                (f"%{path_filter}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT r.*, f.path as file_path FROM routes r JOIN files f ON r.file_id = f.id
                   ORDER BY r.path""",
            ).fetchall()
        return [dict(r) for r in rows]

    def query_components(self, name: str = "") -> list[dict]:
        conn = self._connect()
        if name:
            rows = conn.execute(
                """SELECT c.*, f.path FROM components c JOIN files f ON c.file_id = f.id
                   WHERE c.name LIKE ? ORDER BY c.name""",
                (f"%{name}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT c.*, f.path FROM components c JOIN files f ON c.file_id = f.id
                   ORDER BY c.name""",
            ).fetchall()
        return [dict(r) for r in rows]

    def query_tests(self, status: str = "") -> list[dict]:
        conn = self._connect()
        if status:
            rows = conn.execute(
                """SELECT t.*, f.path FROM tests t JOIN files f ON t.file_id = f.id
                   WHERE t.status = ? ORDER BY t.name""",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT t.*, f.path FROM tests t JOIN files f ON t.file_id = f.id
                   ORDER BY t.name""",
            ).fetchall()
        return [dict(r) for r in rows]

    def query_dependencies(self) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM dependencies ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def search_keyword(self, keyword: str) -> list[dict]:
        """Search across all indexed content by keyword."""
        conn = self._connect()
        results = []
        q = f"%{keyword}%"

        for table, label in [("symbols", "symbol"), ("routes", "route"), ("components", "component"),
                              ("tests", "test")]:
            rows = conn.execute(
                f"""SELECT t.*, f.path, '{label}' as result_type FROM {table} t
                    JOIN files f ON t.file_id = f.id
                    WHERE t.name LIKE ? LIMIT 20""",
                (q,),
            ).fetchall()
            results.extend(dict(r) for r in rows)

        rows = conn.execute(
            """SELECT f.path, 'file' as result_type FROM files f WHERE f.path LIKE ? LIMIT 10""",
            (q,),
        ).fetchall()
        results.extend(dict(r) for r in rows)

        return results

    def stats(self) -> dict:
        conn = self._connect()
        return {
            "files": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "symbols": conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
            "imports": conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0],
            "routes": conn.execute("SELECT COUNT(*) FROM routes").fetchone()[0],
            "components": conn.execute("SELECT COUNT(*) FROM components").fetchone()[0],
            "tests": conn.execute("SELECT COUNT(*) FROM tests").fetchone()[0],
            "schemas": conn.execute("SELECT COUNT(*) FROM schemas").fetchone()[0],
            "dependencies": conn.execute("SELECT COUNT(*) FROM dependencies").fetchone()[0],
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Repository Watcher (background file monitoring)
# ---------------------------------------------------------------------------

class FileChange:
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"

    def __init__(self, path: str, change_type: str):
        self.path = path
        self.type = change_type

    def __repr__(self) -> str:
        return f"{self.type.upper():8s} {self.path}"


class RepositoryWatcher:
    def __init__(
        self,
        root: str | Path = ".",
        interval: float = 5.0,
        db: RepositoryDatabase | None = None,
    ):
        self.root = Path(root).resolve()
        self.interval = interval
        self.db = db or RepositoryDatabase()
        self._snapshot: dict[str, float] = {}
        self._stop = Event()
        self._thread: Thread | None = None
        self._on_change: Callable | None = None
        self._change_count = 0

    def set_on_change(self, cb: Callable) -> None:
        self._on_change = cb

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._take_snapshot()
        self._stop.clear()
        self._thread = Thread(target=self._run, daemon=True, name="repo-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def change_count(self) -> int:
        return self._change_count

    def _take_snapshot(self) -> None:
        self._snapshot = {}
        for ext in TEXT_EXTS:
            for f in self.root.rglob(f"*{ext}"):
                if any(part in IGNORE_DIRS or part.startswith(".") for part in f.relative_to(self.root).parts):
                    continue
                try:
                    self._snapshot[str(f.relative_to(self.root))] = f.stat().st_mtime
                except Exception:
                    pass

    def _run(self) -> None:
        import time
        while not self._stop.is_set():
            time.sleep(self.interval)
            try:
                for change in self._check():
                    self._change_count += 1
                    self._handle_change(change)
            except Exception:
                pass

    def _check(self) -> list[FileChange]:
        changes = []
        current: dict[str, float] = {}
        for ext in TEXT_EXTS:
            for f in self.root.rglob(f"*{ext}"):
                if any(part in IGNORE_DIRS or part.startswith(".") for part in f.relative_to(self.root).parts):
                    continue
                try:
                    rel = str(f.relative_to(self.root))
                    mtime = f.stat().st_mtime
                    current[rel] = mtime
                    if rel not in self._snapshot:
                        changes.append(FileChange(rel, FileChange.CREATED))
                    elif abs(mtime - self._snapshot[rel]) > 0.1:
                        changes.append(FileChange(rel, FileChange.MODIFIED))
                except Exception:
                    pass
        for rel in self._snapshot:
            if rel not in current:
                changes.append(FileChange(rel, FileChange.DELETED))
        self._snapshot = current
        return changes

    def _handle_change(self, change: FileChange) -> None:
        try:
            if change.type == FileChange.DELETED:
                self.db.remove_file(change.path)
            elif change.type in (FileChange.CREATED, FileChange.MODIFIED):
                full_path = self.root / change.path
                if full_path.exists():
                    self.db.index_file(full_path, self.root)
        except Exception:
            pass
        if self._on_change:
            try:
                self._on_change(change)
            except Exception:
                pass

    def summary(self) -> str:
        return f"Watcher: {'running' if self.is_running else 'stopped'}, {self._change_count} changes detected"


# ---------------------------------------------------------------------------
# Semantic Search (synonym-based code search)
# ---------------------------------------------------------------------------

_SYNONYM_MAP: dict[str, list[str]] = {
    "auth": ["authentication", "login", "signin", "sign-in", "jwt", "token", "session", "oauth", "password", "credentials", "authorization"],
    "login": ["authentication", "signin", "sign-in", "auth", "session"],
    "payment": ["checkout", "billing", "invoice", "charge", "transaction", "stripe", "paypal", "price", "pricing", "subscription", "purchase"],
    "api": ["endpoint", "route", "rest", "graphql", "api", "service", "controller", "handler", "request", "response"],
    "dashboard": ["dashboard", "analytics", "metrics", "stats", "statistics", "overview", "report", "monitor"],
    "user": ["user", "profile", "account", "member", "person", "customer", "client"],
    "email": ["email", "mail", "sendgrid", "ses", "smtp", "notification", "message"],
    "search": ["search", "query", "find", "lookup", "filter", "index", "discover"],
    "database": ["database", "db", "sql", "model", "schema", "table", "collection", "entity", "repository", "dao", "migration"],
    "error": ["error", "exception", "fail", "retry", "fallback", "catch", "handle"],
    "test": ["test", "spec", "unit", "integration", "e2e", "assertion", "mock"],
    "config": ["config", "configuration", "setting", "env", "environment", "dotenv", "constant"],
    "deploy": ["deploy", "deployment", "release", "publish", "ci", "cd", "pipeline", "build", "docker"],
    "cache": ["cache", "redis", "memcached", "ttl", "store"],
    "security": ["security", "permission", "role", "guard", "protect", "encrypt", "hash", "sanitize"],
    "notification": ["notification", "alert", "push", "webhook", "event", "message"],
    "file": ["file", "upload", "download", "storage", "s3", "blob", "media", "attachment"],
    "logging": ["log", "logging", "logger", "debug", "trace", "monitor"],
    "middleware": ["middleware", "interceptor", "filter", "guard", "hook"],
    "validation": ["validation", "validator", "validate", "schema", "assert", "check", "sanitize", "zod", "pydantic"],
}


class SemanticSearch:
    def __init__(self, db: RepositoryDatabase | None = None):
        self.db = db or RepositoryDatabase()

    def search(self, query: str, top_k: int = 15) -> list[dict]:
        query_lower = query.lower().strip()
        terms = self._expand_terms(query_lower)
        results: list[dict] = []
        seen = set()

        for term in terms:
            for s in self.db.query_symbols(term):
                key = f"symbol:{s['name']}:{s['path']}"
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "type": "symbol",
                        "name": s["name"],
                        "symbol_type": s["symbol_type"],
                        "file": s["path"],
                        "relevance": self._score_match(term, query_lower, s["name"], s["path"]),
                    })
            for r in self.db.query_routes(term):
                key = f"route:{r['path']}:{r['file_path']}"
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "type": "route",
                        "path": r["path"],
                        "method": r.get("method", "ANY"),
                        "file": r["file_path"],
                        "relevance": self._score_match(term, query_lower, r["path"], r["file_path"]),
                    })
            for c in self.db.query_components(term):
                key = f"component:{c['name']}:{c['path']}"
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "type": "component",
                        "name": c["name"],
                        "file": c["path"],
                        "relevance": self._score_match(term, query_lower, c["name"], c["path"]),
                    })
            for t in self.db.query_tests():
                if term in t["name"].lower() or term in t["path"].lower():
                    key = f"test:{t['name']}:{t['path']}"
                    if key not in seen:
                        seen.add(key)
                        results.append({
                            "type": "test",
                            "name": t["name"],
                            "framework": t.get("framework", ""),
                            "file": t["path"],
                            "relevance": self._score_match(term, query_lower, t["name"], t["path"]),
                        })

        results.sort(key=lambda x: -x["relevance"])
        return results[:top_k]

    def _expand_terms(self, query: str) -> set[str]:
        import re
        terms = {query}
        for word in re.findall(r'\b\w{2,}\b', query):
            terms.add(word)
        for word in list(terms):
            for concept, synonyms in _SYNONYM_MAP.items():
                if word in synonyms or word == concept:
                    terms.add(concept)
                    terms.update(synonyms)
        for word in list(terms):
            for part in re.findall(r'[A-Z]?[a-z]+', word):
                if len(part) > 2:
                    terms.add(part.lower())
        return terms

    @staticmethod
    def _score_match(term: str, query: str, name: str, path: str) -> float:
        score = 1.0
        nl = name.lower()
        pl = path.lower()
        if query == nl:
            score += 5.0
        elif query in nl:
            score += 3.0
        if query in pl:
            score += 2.0
        if term in nl:
            score += 1.0
        if nl.startswith(term):
            score += 0.5
        return score

    def find_by_concept(self, concept: str) -> list[dict]:
        expanded = self._expand_terms(concept)
        all_results = []
        seen = set()
        for term in expanded:
            for r in self.search(term, top_k=10):
                key = f"{r['type']}:{r.get('name', r.get('path', ''))}"
                if key not in seen:
                    seen.add(key)
                    all_results.append(r)
        all_results.sort(key=lambda x: -x["relevance"])
        return all_results[:20]

    @staticmethod
    def format_results(results: list[dict]) -> str:
        if not results:
            return "No results found."
        lines = ["## Semantic Search Results"]
        for r in results:
            rel = r.get("relevance", 0)
            rtype = r["type"].upper()
            if rtype == "SYMBOL":
                lines.append(f"  [{rel:.1f}] {r['symbol_type']:10s} {r['name']}  → {r['file']}")
            elif rtype == "ROUTE":
                lines.append(f"  [{rel:.1f}] {r['method']:6s} {r['path']}  → {r['file']}")
            elif rtype == "COMPONENT":
                lines.append(f"  [{rel:.1f}] component {r['name']}  → {r['file']}")
            elif rtype == "TEST":
                lines.append(f"  [{rel:.1f}] test {r['name']} ({r.get('framework', '?')})  → {r['file']}")
            else:
                lines.append(f"  [{rel:.1f}] {r}")
        return "\n".join(lines)
