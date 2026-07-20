from __future__ import annotations

import enum
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

class FailureType(enum.Enum):
    COMPILATION_ERROR = "compilation_error"
    TEST_FAILURE = "test_failure"
    LINT_ERROR = "lint_error"
    TIMEOUT = "timeout"
    TOOL_UNAVAILABLE = "tool_unavailable"
    API_ERROR = "api_error"
    RATE_LIMIT = "rate_limit"
    PERMISSION_DENIED = "permission_denied"
    FILE_NOT_FOUND = "file_not_found"
    SYNTAX_ERROR = "syntax_error"
    DEPENDENCY_MISSING = "dependency_missing"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class FailureRecord:
    id: str
    failure_type: FailureType
    message: str
    context: str
    timestamp: float
    traceback: str = ""
    attempts: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryStrategy:
    name: str
    description: str
    action: str  # what to do


# ---------------------------------------------------------------------------
# Failure classifiers
# ---------------------------------------------------------------------------

def classify_failure(error_text: str, context: str = "") -> FailureType:
    err_lower = error_text.lower()
    ctx_lower = context.lower()

    if any(k in ctx_lower for k in ("rate limit", "too many requests", "429")):
        return FailureType.RATE_LIMIT
    if any(k in ctx_lower for k in ("permission", "access denied", "forbidden")):
        return FailureType.PERMISSION_DENIED
    if any(k in ctx_lower for k in ("network", "connection refused", "timeout")):
        return FailureType.NETWORK_ERROR
    if any(k in ctx_lower for k in ("module not found", "cannot find module", "no module named")):
        return FailureType.DEPENDENCY_MISSING
    if any(k in err_lower for k in ("syntaxerror", "syntax error", "unexpected token")):
        return FailureType.SYNTAX_ERROR
    if any(k in err_lower for k in ("filenotfounderror", "no such file", "not found", "cannot find")):
        return FailureType.FILE_NOT_FOUND
    if any(k in err_lower for k in ("compilation", "compile error", "tsc", "does not compile")):
        return FailureType.COMPILATION_ERROR
    if any(k in err_lower for k in ("test failed", "assertionerror", "assertion error", "failures")):
        return FailureType.TEST_FAILURE
    if any(k in err_lower for k in ("lint", "eslint", "ruff", "pylint", "mypy")):
        return FailureType.LINT_ERROR
    if any(k in ctx_lower for k in ("timeout", "timed out")):
        return FailureType.TIMEOUT
    if any(k in ctx_lower for k in ("tool", "command not found", "not installed")):
        return FailureType.TOOL_UNAVAILABLE
    if any(k in ctx_lower for k in ("api", "apikey", "unauthorized")):
        return FailureType.API_ERROR

    return FailureType.UNKNOWN


# ---------------------------------------------------------------------------
# Recovery strategies for each failure type
# ---------------------------------------------------------------------------

RECOVERY_STRATEGIES: dict[FailureType, list[RecoveryStrategy]] = {
    FailureType.COMPILATION_ERROR: [
        RecoveryStrategy("fix_syntax", "Fix syntax errors in affected files", "Read the file, fix the compilation error, re-verify"),
        RecoveryStrategy("add_type_annotations", "Add missing type annotations", "Check for missing types and add them"),
        RecoveryStrategy("simplify", "Simplify the problematic code", "Rewrite the problematic section with simpler logic"),
    ],
    FailureType.TEST_FAILURE: [
        RecoveryStrategy("fix_test", "Fix the failing test", "Read the test, understand the expected behavior, fix the test or code"),
        RecoveryStrategy("update_test", "Update test assertions to match actual behavior", "If the behavior change is intentional, update the test"),
        RecoveryStrategy("skip_flaky", "Skip flaky test and document", "Mark the test as flaky and continue"),
    ],
    FailureType.LINT_ERROR: [
        RecoveryStrategy("auto_fix", "Run auto-fix if available", "Run linter auto-fix command"),
        RecoveryStrategy("manual_fix", "Fix lint issues manually", "Read the lint output and fix each issue"),
    ],
    FailureType.TIMEOUT: [
        RecoveryStrategy("increase_timeout", "Increase timeout and retry", "Retry with longer timeout"),
        RecoveryStrategy("optimize", "Optimize the operation to complete faster", "Break the operation into smaller parts"),
        RecoveryStrategy("defer", "Defer the operation for later", "Mark as non-blocking and continue"),
    ],
    FailureType.TOOL_UNAVAILABLE: [
        RecoveryStrategy("install_tool", "Install the missing tool", "Run appropriate install command"),
        RecoveryStrategy("use_alternative", "Use an alternative tool", "Use a different tool that achieves the same goal"),
        RecoveryStrategy("skip_step", "Skip this step and document", "Mark the step as skipped due to missing tool"),
    ],
    FailureType.API_ERROR: [
        RecoveryStrategy("retry_auth", "Re-authenticate and retry", "Check API key validity and retry"),
        RecoveryStrategy("use_fallback", "Use fallback API endpoint", "Switch to a backup API URL"),
    ],
    FailureType.RATE_LIMIT: [
        RecoveryStrategy("wait_and_retry", "Wait for rate limit window and retry", "Wait 60 seconds then retry"),
        RecoveryStrategy("reduce_batch", "Reduce batch size", "Process in smaller batches"),
    ],
    FailureType.PERMISSION_DENIED: [
        RecoveryStrategy("request_permission", "Request elevated permissions", "Ask user for permission escalation"),
        RecoveryStrategy("use_alternative_path", "Use an alternative path", "Write to a different location with proper permissions"),
    ],
    FailureType.FILE_NOT_FOUND: [
        RecoveryStrategy("create_file", "Create the missing file", "Create the file with appropriate content"),
        RecoveryStrategy("find_alternative", "Find the file in an alternative location", "Search for the file in common locations"),
    ],
    FailureType.SYNTAX_ERROR: [
        RecoveryStrategy("fix_syntax", "Fix syntax error", "Read the file and fix the syntax error"),
        RecoveryStrategy("rewrite_block", "Rewrite the problematic code block", "Replace the broken code block"),
    ],
    FailureType.DEPENDENCY_MISSING: [
        RecoveryStrategy("install_dependency", "Install missing dependency", "Run pip/npm install for the missing package"),
        RecoveryStrategy("use_stdlib", "Use standard library alternative", "Replace with stdlib equivalent"),
    ],
    FailureType.NETWORK_ERROR: [
        RecoveryStrategy("retry_network", "Retry network operation", "Retry after a short delay"),
        RecoveryStrategy("use_cache", "Use cached data", "Fall back to cached version if available"),
    ],
    FailureType.UNKNOWN: [
        RecoveryStrategy("retry_once", "Retry once", "Give it one more try"),
        RecoveryStrategy("simplify_request", "Simplify the request and retry", "Break into smaller steps"),
        RecoveryStrategy("ask_user", "Ask the user for guidance", "Present the error and ask how to proceed"),
    ],
}


# ---------------------------------------------------------------------------
# Recovery Engine
# ---------------------------------------------------------------------------

class RecoveryEngine:
    """Intelligent recovery instead of blind retries.

    On failure:
    1. Classify the failure type
    2. Choose a recovery strategy
    3. Execute the strategy
    4. Verify the recovery
    5. Continue the mission or escalate
    """

    def __init__(self):
        self.history: list[FailureRecord] = []
        self._strategy_index: dict[str, int] = {}  # context_id -> strategy attempt count

    def record_failure(
        self,
        error_message: str,
        context: str = "",
        failure_type: FailureType | None = None,
        metadata: dict | None = None,
    ) -> FailureRecord:
        if failure_type is None:
            failure_type = classify_failure(error_message, context)
        record = FailureRecord(
            id=f"fail-{int(time.time())}-{len(self.history)}",
            failure_type=failure_type,
            message=error_message[:500],
            context=context[:200],
            timestamp=time.time(),
            traceback=traceback.format_exc()[:1000],
            attempts=0,
            metadata=metadata or {},
        )
        self.history.append(record)
        return record

    def suggest_strategies(self, record: FailureRecord) -> list[RecoveryStrategy]:
        strategies = RECOVERY_STRATEGIES.get(record.failure_type, RECOVERY_STRATEGIES[FailureType.UNKNOWN])
        # Track which strategies we've already tried for this context
        ctx_key = f"{record.failure_type.value}:{record.context[:50]}"
        tried = self._strategy_index.get(ctx_key, 0)
        return strategies[tried:] if tried < len(strategies) else strategies[-1:]

    def mark_strategy_used(self, record: FailureRecord) -> None:
        ctx_key = f"{record.failure_type.value}:{record.context[:50]}"
        self._strategy_index[ctx_key] = self._strategy_index.get(ctx_key, 0) + 1

    def recover(
        self,
        error_message: str,
        context: str = "",
        executor: Callable | None = None,
        metadata: dict | None = None,
    ) -> tuple[bool, str, str]:
        """Attempt recovery from a failure.

        Returns (recovered, result_message, strategy_name)
        """
        record = self.record_failure(error_message, context, metadata=metadata)
        strategies = self.suggest_strategies(record)

        for strategy in strategies:
            self.mark_strategy_used(record)
            if executor:
                try:
                    result = executor(strategy)
                    if result and result.get("success"):
                        return True, result.get("message", "Recovered"), strategy.name
                except Exception:
                    continue
            # If no executor, just log the suggested strategy
            return False, f"Suggested: {strategy.action}", strategy.name

        return False, "All recovery strategies exhausted", "none"

    def reset(self) -> None:
        self.history.clear()
        self._strategy_index.clear()

    def summary(self) -> str:
        if not self.history:
            return "No failures recorded"
        lines = ["## Recovery History"]
        for r in self.history[-10:]:
            lines.append(f"  {r.failure_type.value:20s} {r.message[:80]}")
        return "\n".join(lines)
