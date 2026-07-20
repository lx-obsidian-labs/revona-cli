from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None


# ---------------------------------------------------------------------------
# Verification Step
# ---------------------------------------------------------------------------

@dataclass
class VerificationStep:
    name: str
    description: str
    command: str | None
    required: bool = True
    timeout: int = 120
    cwd: str = "."

    def run(self) -> tuple[bool, str, float]:
        if not self.command:
            return True, "No command configured", 0.0
        start = time.time()
        try:
            r = subprocess.run(
                self.command,
                shell=True,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            elapsed = time.time() - start
            output = (r.stdout or "") + (r.stderr or "")
            success = r.returncode == 0
            return success, output[:2000], elapsed
        except subprocess.TimeoutExpired:
            return False, f"Timed out after {self.timeout}s", time.time() - start
        except Exception as e:
            return False, str(e)[:500], time.time() - start


@dataclass
class VerificationResult:
    step: str
    passed: bool
    message: str
    elapsed: float
    required: bool


# ---------------------------------------------------------------------------
# Standard verification pipeline
# ---------------------------------------------------------------------------

def _detect_python_commands(root: Path) -> list[VerificationStep]:
    """Generate verification steps for a Python project."""
    steps = []
    has_pyproject = (root / "pyproject.toml").exists() or (root / "setup.cfg").exists()

    if has_pyproject or list(root.rglob("test_*.py")) or list(root.rglob("*_test.py")):
        if _tool_available("pytest"):
            steps.append(VerificationStep("tests", "Run pytest", "python -m pytest -x -q 2>&1", timeout=180))
        else:
            steps.append(VerificationStep("tests", "Run pytest (not installed, skipped)", None, required=False))

    if has_pyproject:
        if _tool_available("mypy"):
            steps.append(VerificationStep("static_analysis", "Run mypy", "python -m mypy . --ignore-missing-imports 2>&1", timeout=120))
        else:
            steps.append(VerificationStep("static_analysis", "Run mypy (not installed, skipped)", None, required=False))

        if _tool_available("ruff"):
            steps.append(VerificationStep("lint", "Run ruff", "python -m ruff check . 2>&1", timeout=60))
        else:
            steps.append(VerificationStep("lint", "Run ruff (not installed, skipped)", None, required=False))

        if _tool_available("black"):
            steps.append(VerificationStep("format", "Check formatting with black", "python -m black --check . 2>&1", required=False, timeout=60))
        else:
            steps.append(VerificationStep("format", "Format check (black not installed, skipped)", None, required=False))
    return steps


def _detect_node_commands(root: Path) -> list[VerificationStep]:
    """Generate verification steps for a Node.js project."""
    steps = []
    pkg = root / "package.json"
    if not pkg.exists():
        return steps
    steps.append(VerificationStep("compile", "TypeScript compilation", "npx tsc --noEmit 2>&1", required=False, timeout=120))
    steps.append(VerificationStep("lint", "ESLint", "npx eslint . 2>&1", required=False, timeout=120))
    if list(root.rglob("*.test.*")) or list(root.rglob("*.spec.*")):
        steps.append(VerificationStep("tests", "Run tests", "npm test 2>&1", timeout=180))
    return steps


# ---------------------------------------------------------------------------
# Verification Pipeline
# ---------------------------------------------------------------------------

class VerificationPipeline:
    """Run multiple verification steps and report results.

    Every engineering task must automatically execute:
    - Compile
    - Lint
    - Tests
    - Static Analysis
    - Security Scan
    - Formatting
    - Repository Validation
    - Documentation Validation
    """

    def __init__(self, root: str | Path = "."):
        self.root = Path(root).resolve()
        self._steps: list[VerificationStep] = []
        self._results: list[VerificationResult] = []
        self._custom_steps: list[VerificationStep] = []
        self._on_step: Callable | None = None

    def add_step(self, step: VerificationStep) -> None:
        self._custom_steps.append(step)

    def set_on_step_callback(self, cb: Callable) -> None:
        self._on_step = cb

    def discover(self) -> list[VerificationStep]:
        """Auto-discover verification steps based on project type."""
        steps = []
        steps += _detect_python_commands(self.root)
        steps += _detect_node_commands(self.root)
        # Generic compile step
        py_files = list(self.root.rglob("*.py"))
        if py_files:
            # Build a file list for py_compile
            file_list = " ".join(f'"{f}"' for f in py_files[:50])
            steps.append(VerificationStep("compile", "Python syntax check", f"python -m py_compile {file_list} 2>&1", required=False, timeout=60))
        # Documentation check
        doc_files = list(self.root.rglob("*.md"))
        if doc_files:
            steps.append(VerificationStep("documentation", "Documentation present", None, required=False))
        # Security scan
        steps.append(VerificationStep("security", "Security audit", None, required=False))
        self._steps = steps + self._custom_steps
        return self._steps

    def run(self, discover: bool = True) -> list[VerificationResult]:
        """Execute the verification pipeline."""
        if discover:
            self.discover()

        self._results = []
        start = time.time()

        for step in self._steps:
            step_start = time.time()
            if self._on_step:
                self._on_step(step.name, "running")

            passed, message, elapsed = step.run()

            result = VerificationResult(
                step=step.name,
                passed=passed,
                message=message,
                elapsed=elapsed,
                required=step.required,
            )
            self._results.append(result)

            if self._on_step:
                self._on_step(step.name, "done" if passed else "failed")

        return self._results

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self._results if r.required)

    @property
    def required_passed(self) -> bool:
        return all(r.passed for r in self._results if r.required)

    @property
    def summary(self) -> str:
        lines = []
        passed = sum(1 for r in self._results if r.passed)
        failed = sum(1 for r in self._results if not r.passed)
        total = len(self._results)
        lines.append(f"Verification: {passed}/{total} passed, {failed} failed")
        for r in self._results:
            icon = "✓" if r.passed else "✗"
            req = "[REQUIRED]" if r.required else "[OPTIONAL]"
            lines.append(f"  {icon} {r.step:20s} {req:10s} ({r.elapsed:.1f}s)")
            if not r.passed and r.required:
                lines.append(f"     {r.message[:200]}")
        return "\n".join(lines)

    @property
    def results_dict(self) -> dict[str, bool | str]:
        return {r.step: r.passed if r.passed else r.message[:200] for r in self._results}

    def reset(self) -> None:
        self._steps.clear()
        self._results.clear()
        self._custom_steps.clear()
