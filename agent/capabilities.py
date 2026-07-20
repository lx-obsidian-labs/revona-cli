from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Capability status
# ---------------------------------------------------------------------------

class CapabilityStatus:
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    RESTRICTED = "restricted"


# ---------------------------------------------------------------------------
# Discovery probes
# ---------------------------------------------------------------------------

def _probe_command(name: str) -> bool:
    return shutil.which(name) is not None


def _probe_python_package(pkg: str) -> bool:
    try:
        __import__(pkg)
        return True
    except ImportError:
        return False


def _probe_npm_package(name: str) -> bool:
    try:
        result = subprocess.run(
            ["npx", "--yes", name, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _probe_path(path: str) -> bool:
    return Path(path).exists()


def _probe_docker() -> tuple[bool, str]:
    if not _probe_command("docker"):
        return False, "docker not found in PATH"
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return True, "docker daemon is running"
        return False, "docker daemon is not running"
    except Exception as e:
        return False, str(e)


def _probe_git() -> tuple[bool, str]:
    if not _probe_command("git"):
        return False, "git not found"
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        return True, r.stdout.strip() or "git available"
    except Exception as e:
        return False, str(e)


def _probe_node() -> tuple[bool, str]:
    if not _probe_command("node"):
        return False, "node not found"
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        return True, r.stdout.strip() or "node available"
    except Exception as e:
        return False, str(e)


def _probe_npm() -> tuple[bool, str]:
    if not _probe_command("npm"):
        return False, "npm not found"
    try:
        r = subprocess.run(["npm", "--version"], capture_output=True, text=True, timeout=5)
        return True, r.stdout.strip() or "npm available"
    except Exception as e:
        return False, str(e)


def _probe_pnpm() -> tuple[bool, str]:
    if not _probe_command("pnpm"):
        return False, "pnpm not found"
    try:
        r = subprocess.run(["pnpm", "--version"], capture_output=True, text=True, timeout=5)
        return True, r.stdout.strip() or "pnpm available"
    except Exception as e:
        return False, str(e)


def _probe_python() -> tuple[bool, str]:
    return True, f"Python {sys.version.split()[0]}"


def _probe_pip() -> tuple[bool, str]:
    if not _probe_command("pip"):
        return False, "pip not found"
    try:
        r = subprocess.run(["pip", "--version"], capture_output=True, text=True, timeout=5)
        return True, r.stdout.strip() or "pip available"
    except Exception as e:
        return False, str(e)


def _probe_adb() -> tuple[bool, str]:
    if not _probe_command("adb"):
        return False, "adb not found in PATH"
    try:
        r = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
        devices = [l for l in r.stdout.splitlines() if l and l.strip() and "\tdevice" in l]
        if devices:
            return True, f"{len(devices)} device(s) connected"
        return True, "adb available (no devices connected)"
    except Exception as e:
        return False, str(e)


def _probe_browser() -> tuple[bool, str]:
    browsers = ["chrome", "chromium", "firefox", "edge", "brave", "google-chrome"]
    found = [b for b in browsers if _probe_command(b)]
    if found:
        return True, f"found: {', '.join(found[:3])}"
    # Check common install paths on Windows
    win_paths = [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files\\Mozilla Firefox\\firefox.exe",
        "C:\\Program Files (x86)\\Mozilla Firefox\\firefox.exe",
        os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"),
        os.path.expanduser("~\\AppData\\Local\\Microsoft\\Edge\\Application\\msedge.exe"),
    ]
    found_win = [p for p in win_paths if Path(p).exists()]
    if found_win:
        return True, f"found installed browsers: {len(found_win)}"
    return False, "no browser binaries found in PATH or common install paths"


def _probe_database() -> dict[str, bool]:
    """Detect database engines available in the environment."""
    dbs = {
        "sqlite": True,
        "postgresql": _probe_command("psql"),
        "mysql": _probe_command("mysql"),
        "mongodb": _probe_command("mongosh") or _probe_command("mongo"),
        "redis": _probe_command("redis-cli"),
    }
    return dbs


def _probe_mcp() -> tuple[bool, str]:
    """Check if MCP (Model Context Protocol) servers are available."""
    mcp_dirs = [
        Path.home() / ".mcp",
        Path.home() / ".config" / "mcp",
        Path(".") / ".mcp",
    ]
    for d in mcp_dirs:
        if d.exists() and d.is_dir():
            servers = list(d.glob("*.json")) + list(d.glob("*.yaml")) + list(d.glob("*.yml"))
            if servers:
                return True, f"found {len(servers)} MCP server config(s) in {d}"
    return False, "no MCP server configurations found"


def _probe_permissions() -> dict[str, bool]:
    return {
        "filesystem_write": os.access(".", os.W_OK),
        "filesystem_read": os.access(".", os.R_OK),
        "network": _probe_python_package("requests"),
    }


def _probe_shell() -> tuple[bool, str]:
    shell = os.environ.get("SHELL", os.environ.get("ComSpec", "cmd"))
    return True, f"default shell: {shell}"


def _probe_internet() -> tuple[bool, str]:
    try:
        import urllib.request
        urllib.request.urlopen("https://8.8.8.8", timeout=3)
        return True, "internet reachable"
    except Exception:
        return False, "internet not reachable"


# ---------------------------------------------------------------------------
# Capability Discovery Engine
# ---------------------------------------------------------------------------

class CapabilityDiscoveryEngine:
    """Detect available capabilities before any mission starts.

    The Planner must never assume a capability exists.
    """

    def __init__(self):
        self._results: dict[str, Any] = {}
        self._probed = False

    def discover_all(self) -> dict[str, Any]:
        self._results = {
            "filesystem": CapabilityStatus.AVAILABLE,
            "git": self._probe("git", _probe_git),
            "internet": self._probe("internet", _probe_internet),
            "shell": self._probe("shell", _probe_shell),
            "docker": self._probe("docker", _probe_docker),
            "python": self._probe("python", _probe_python),
            "pip": self._probe("pip", _probe_pip),
            "node": self._probe("node", _probe_node),
            "npm": self._probe("npm", _probe_npm),
            "pnpm": self._probe("pnpm", _probe_pnpm),
            "adb": self._probe("adb", _probe_adb),
            "browser": self._probe("browser", _probe_browser),
            "mcp_servers": self._probe("mcp", _probe_mcp),
            "permissions": _probe_permissions(),
            "databases": _probe_database(),
        }
        self._probed = True
        return self._results

    def _probe(self, name: str, probe_fn) -> str | dict:
        try:
            result = probe_fn()
            if isinstance(result, tuple):
                ok, msg = result
                return CapabilityStatus.AVAILABLE if ok else f"{CapabilityStatus.UNAVAILABLE}: {msg}"
            if isinstance(result, dict):
                return {k: CapabilityStatus.AVAILABLE if v else CapabilityStatus.UNAVAILABLE for k, v in result.items()}
            return CapabilityStatus.AVAILABLE if result else CapabilityStatus.UNAVAILABLE
        except Exception as e:
            return f"{CapabilityStatus.UNAVAILABLE}: {e}"

    def get(self, name: str) -> Any:
        return self._results.get(name, CapabilityStatus.UNAVAILABLE)

    def is_available(self, name: str) -> bool:
        val = self._results.get(name, CapabilityStatus.UNAVAILABLE)
        if isinstance(val, str):
            return val == CapabilityStatus.AVAILABLE
        if isinstance(val, dict):
            return any(v == CapabilityStatus.AVAILABLE for v in val.values())
        return False

    def summary(self) -> str:
        lines = ["## Capability Discovery", ""]
        for key, val in sorted(self._results.items()):
            if isinstance(val, dict):
                lines.append(f"  {key}:")
                for k, v in val.items():
                    icon = "✓" if CapabilityStatus.AVAILABLE in str(v) else "✗"
                    lines.append(f"    {icon} {k}: {v}")
            else:
                icon = "✓" if CapabilityStatus.AVAILABLE in str(val) else ("~" if CapabilityStatus.RESTRICTED in str(val) else "✗")
                lines.append(f"  {icon} {key}: {val}")
        return "\n".join(lines)

    @property
    def all_available(self) -> list[str]:
        return [k for k in self._results if self.is_available(k)]

    @property
    def context_block(self) -> str:
        """Compact context block for planners."""
        available = []
        unavailable = []
        for key in sorted(self._results.keys()):
            val = self._results[key]
            if isinstance(val, str) and val == CapabilityStatus.AVAILABLE:
                available.append(key)
            elif isinstance(val, dict) and any(CapabilityStatus.AVAILABLE in str(v) for v in val.values()):
                available.append(key)
            else:
                unavailable.append(key)
        parts = ["## Available Capabilities"]
        parts.append("Available: " + ", ".join(available))
        if unavailable:
            parts.append("Unavailable: " + ", ".join(unavailable))
        return "\n".join(parts)
