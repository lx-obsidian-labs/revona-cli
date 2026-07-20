from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import AGENT_DIR, IGNORE_DIRS, TEXT_EXTS
from .repo_db import RepositoryDatabase
from .terminal import console


class ContextRanker:
    def __init__(self, db: RepositoryDatabase | None = None):
        self.db = db or RepositoryDatabase()
        self._max_tokens = 8000
        self._max_files = 15
        self._max_symbols = 30

    def configure(self, max_tokens: int = 8000, max_files: int = 15, max_symbols: int = 30) -> None:
        self._max_tokens = max_tokens
        self._max_files = max_files
        self._max_symbols = max_symbols

    def rank_context(self, request: str, repo_root: Path | None = None) -> str:
        root = repo_root or Path(".")
        query = request.lower()
        key_terms = self._extract_key_terms(query)
        scored_files = self._score_files(query, key_terms, root)
        scored_symbols = self._score_symbols(query, key_terms)
        relevant_deps = self._find_relevant_deps(query, scored_files)

        parts = ["## Context (ranked by relevance)", ""]
        top_files = scored_files[:self._max_files]
        if top_files:
            parts.append("### Relevant Files")
            for score, file_path, snippet in top_files:
                parts.append(f"  [{score:.2f}] {file_path}")
                if snippet:
                    parts.append(f"```\n{snippet[:500]}\n```")
            parts.append("")
        top_symbols = scored_symbols[:self._max_symbols]
        if top_symbols:
            parts.append("### Relevant Symbols")
            for score, name, sym_type, file_path in top_symbols:
                parts.append(f"  [{score:.2f}] {name} ({sym_type}) — {file_path}")
            parts.append("")
        if relevant_deps:
            parts.append("### Relevant Dependencies")
            for dep in relevant_deps[:10]:
                parts.append(f"  {dep}")
            parts.append("")
        parts.append(f"  *Scored {len(scored_files)} files, {len(scored_symbols)} symbols*")
        return "\n".join(parts)

    def _extract_key_terms(self, query: str) -> set[str]:
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "has", "have", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "can", "shall", "need",
            "find", "show", "get", "make", "create", "add", "update",
            "remove", "delete", "change", "fix", "implement", "build",
            "help", "me", "with", "this", "that", "these", "those",
            "for", "and", "but", "or", "not", "of", "to", "in", "on",
            "at", "by", "from", "as", "into", "through", "during",
            "before", "after", "above", "below", "between", "please",
        }
        terms = set()
        for word in re.findall(r'\b[a-zA-Z_]\w{2,}\b', query):
            if word.lower() not in stop_words:
                terms.add(word.lower())
                for part in re.findall(r'[A-Z]?[a-z]+|[A-Z]+', word):
                    if len(part) > 2 and part.lower() not in stop_words:
                        terms.add(part.lower())
        return terms

    def _score_files(self, query: str, key_terms: set[str], root: Path) -> list[tuple[float, str, str]]:
        scored = []
        for ext in TEXT_EXTS:
            for f in root.rglob(f"*{ext}"):
                if any(part in IGNORE_DIRS or part.startswith(".") for part in f.relative_to(root).parts):
                    continue
                rel = str(f.relative_to(root).as_posix())
                score = 0.0
                snippet = ""
                fname = f.stem.lower()
                for term in key_terms:
                    if term in fname:
                        score += 3.0
                    if fname.startswith(term) or fname.endswith(term):
                        score += 2.0
                for part in rel.lower().split("/"):
                    for term in key_terms:
                        if term in part:
                            score += 1.5
                if score > 0:
                    try:
                        text = f.read_text(encoding="utf-8", errors="replace")
                        lines = text.split("\n")
                        for term in key_terms:
                            count = text.lower().count(term)
                            score += count * 0.5
                        snippet_lines = [l for l in lines[:20] if any(t in l.lower() for t in key_terms)]
                        if snippet_lines:
                            snippet = "\n".join(snippet_lines[:5])
                        else:
                            snippet = "\n".join(lines[:5])
                    except Exception:
                        pass
                if score > 0:
                    scored.append((score, rel, snippet))
        scored.sort(key=lambda x: -x[0])
        return scored

    def _score_symbols(self, query: str, key_terms: set[str]) -> list[tuple[float, str, str, str]]:
        scored = []
        try:
            for term in key_terms:
                symbols = self.db.query_symbols(term)
                for sym in symbols:
                    score = 2.0
                    if term == sym["name"].lower():
                        score = 5.0
                    scored.append((score, sym["name"], sym["symbol_type"], sym["path"]))
        except Exception:
            pass
        scored.sort(key=lambda x: -x[0])
        return scored

    def _find_relevant_deps(self, query: str, scored_files: list[tuple]) -> list[str]:
        deps = set()
        try:
            for _, rel, _ in scored_files[:10]:
                if "package.json" in rel or "pyproject.toml" in rel or "requirements" in rel:
                    path = Path(rel)
                    if path.exists():
                        deps.add(rel)
        except Exception:
            pass
        return sorted(deps)

    def build_prompt(
        self,
        request: str,
        system_prompt: str,
        context: str,
        capabilities_block: str = "",
        max_length: int = 32000,
    ) -> list[dict]:
        system_parts = [system_prompt]
        if capabilities_block:
            system_parts.append(capabilities_block)
        system_content = "\n\n".join(system_parts)
        user_content = f"{context}\n\n## Request\n{request}"
        if len(system_content) + len(user_content) > max_length:
            excess = len(system_content) + len(user_content) - max_length + 1000
            if len(context) > excess:
                context = context[:-excess]
                user_content = f"{context}\n\n## Request\n{request}"
        return [
            {"role": "system", "content": system_content[:16000]},
            {"role": "user", "content": user_content[:32000]},
        ]
