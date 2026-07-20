from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .repo_db import RepositoryDatabase


_SYNONYM_MAP: dict[str, list[str]] = {
    "auth": ["authentication", "login", "signin", "sign-in", "login", "jwt", "token", "session", "oauth", "password", "credentials", "authorization"],
    "login": ["authentication", "signin", "sign-in", "auth", "login", "session"],
    "payment": ["checkout", "billing", "invoice", "charge", "transaction", "payment", "stripe", "paypal", "price", "pricing", "subscription", "purchase"],
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
            symbols = self.db.query_symbols(term)
            for s in symbols:
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

            routes = self.db.query_routes(term)
            for r in routes:
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

            components = self.db.query_components(term)
            for c in components:
                key = f"component:{c['name']}:{c['path']}"
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "type": "component",
                        "name": c["name"],
                        "file": c["path"],
                        "relevance": self._score_match(term, query_lower, c["name"], c["path"]),
                    })

            tests = self.db.query_tests()
            for t in tests:
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

    def _score_match(self, term: str, query: str, name: str, path: str) -> float:
        score = 1.0
        name_lower = name.lower()
        path_lower = path.lower()
        if query == name_lower:
            score += 5.0
        elif query in name_lower:
            score += 3.0
        if query in path_lower:
            score += 2.0
        if term in name_lower:
            score += 1.0
        if name_lower.startswith(term):
            score += 0.5
        return score

    def find_by_concept(self, concept: str) -> list[dict]:
        expanded = self._expand_terms(concept)
        all_results = []
        seen = set()
        for term in expanded:
            results = self.search(term, top_k=10)
            for r in results:
                key = f"{r['type']}:{r.get('name', r.get('path', ''))}"
                if key not in seen:
                    seen.add(key)
                    all_results.append(r)
        all_results.sort(key=lambda x: -x["relevance"])
        return all_results[:20]

    def format_results(self, results: list[dict]) -> str:
        if not results:
            return "No results found."
        lines = ["## Semantic Search Results"]
        for r in results:
            rtype = r["type"].upper()
            relevance = r.get("relevance", 0)
            if rtype == "SYMBOL":
                lines.append(f"  [{relevance:.1f}] {r['symbol_type']:10s} {r['name']}  → {r['file']}")
            elif rtype == "ROUTE":
                lines.append(f"  [{relevance:.1f}] {r['method']:6s} {r['path']}  → {r['file']}")
            elif rtype == "COMPONENT":
                lines.append(f"  [{relevance:.1f}] component {r['name']}  → {r['file']}")
            elif rtype == "TEST":
                lines.append(f"  [{relevance:.1f}] test {r['name']} ({r.get('framework', '?')})  → {r['file']}")
            else:
                lines.append(f"  [{relevance:.1f}] {r}")
        return "\n".join(lines)
