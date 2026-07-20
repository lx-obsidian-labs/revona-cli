from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import AGENT_DIR

PLUGINS_DIR = AGENT_DIR / "plugins"
INSTALLED_PLUGINS_PATH = AGENT_DIR / "installed_plugins.json"


# ---------------------------------------------------------------------------
# Plugin types
# ---------------------------------------------------------------------------

@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    plugin_type: str  # agent, skill, blueprint, accelerator, theme, validator, model_provider, memory_provider, verification, command
    author: str = ""
    entry_point: str = ""
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plugin:
    manifest: PluginManifest
    path: Path
    loaded: bool = False
    instance: Any = None

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def plugin_type(self) -> str:
        return self.manifest.plugin_type


# ---------------------------------------------------------------------------
# Plugin SDK
# ---------------------------------------------------------------------------

class PluginSDK:
    """Manage plugins: install, load, uninstall, discover.

    Supports:
    - Agents
    - Skills
    - Blueprints
    - Accelerators
    - Themes
    - Validators
    - Model Providers
    - Memory Providers
    - Verification Modules
    - Commands
    """

    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._type_index: dict[str, list[Plugin]] = {}
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_installed()
        self._discover()
        self._initialized = True

    def _load_installed(self) -> None:
        if INSTALLED_PLUGINS_PATH.exists():
            try:
                data = json.loads(INSTALLED_PLUGINS_PATH.read_text(encoding="utf-8"))
                for manifest_data in data:
                    manifest = PluginManifest(**manifest_data)
                    plugin_path = PLUGINS_DIR / manifest.name
                    if plugin_path.exists():
                        self._plugins[manifest.name] = Plugin(manifest=manifest, path=plugin_path)
            except Exception:
                pass

    def _discover(self) -> None:
        for d in sorted(PLUGINS_DIR.iterdir()):
            if not d.is_dir():
                continue
            if d.name.startswith("_"):
                continue
            if d.name in self._plugins:
                continue
            manifest_path = d / "plugin.json"
            if manifest_path.exists():
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest = PluginManifest(**data)
                    plugin = Plugin(manifest=manifest, path=d)
                    self._plugins[manifest.name] = plugin
                except Exception:
                    pass

    def install(self, name: str, source: str | Path) -> bool:
        """Install a plugin from a path."""
        src = Path(source)
        if not src.exists():
            return False

        target = PLUGINS_DIR / name
        target.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            for item in src.iterdir():
                if item.is_file():
                    (target / item.name).write_bytes(item.read_bytes())
                elif item.is_dir():
                    import shutil
                    shutil.copytree(item, target / item.name, dirs_exist_ok=True)
        elif src.is_file():
            target_path = target / src.name
            target_path.write_bytes(src.read_bytes())

        self._save_installed()
        self._discover()
        return True

    def uninstall(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        import shutil
        shutil.rmtree(self._plugins[name].path, ignore_errors=True)
        del self._plugins[name]
        self._save_installed()
        return True

    def load(self, name: str) -> Any:
        plugin = self._plugins.get(name)
        if not plugin:
            return None
        if plugin.loaded:
            return plugin.instance

        entry = plugin.path / plugin.manifest.entry_point
        if entry.exists() and entry.suffix == ".py":
            try:
                spec = importlib.util.spec_from_file_location(f"plugin_{name}", entry)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    plugin.instance = module
                    plugin.loaded = True
            except Exception:
                pass

        return plugin.instance

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def by_type(self, plugin_type: str) -> list[Plugin]:
        return [p for p in self._plugins.values() if p.manifest.plugin_type == plugin_type]

    def all(self) -> list[Plugin]:
        return list(self._plugins.values())

    def _save_installed(self) -> None:
        data = [p.manifest.__dict__ for p in self._plugins.values()]
        INSTALLED_PLUGINS_PATH.parent.mkdir(exist_ok=True)
        INSTALLED_PLUGINS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def summary(self) -> str:
        lines = ["## Installed Plugins"]
        for p in self._plugins.values():
            marker = "✓" if p.loaded else " "
            lines.append(f"  {marker} {p.manifest.name:20s} {p.manifest.plugin_type:18s} v{p.manifest.version}")
        return "\n".join(lines)
