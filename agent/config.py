"""Local non-secret configuration for Revona CLI."""

import json
import os
import tomllib

from . import CONFIG_PATH, DEFAULT_MODEL


def load_config() -> dict:
    """Load model preferences without reading credentials from disk."""
    cfg = {"model": DEFAULT_MODEL}
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("rb") as f:
                data = tomllib.load(f)
            agent = data.get("agent", {})
            if isinstance(agent, dict) and isinstance(agent.get("model"), str):
                cfg["model"] = agent["model"]
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return cfg


def save_config(cfg: dict) -> None:
    """Persist only non-secret preferences using TOML-safe quoted strings."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    model = cfg.get("model", DEFAULT_MODEL)
    if not isinstance(model, str):
        raise TypeError("model must be a string")
    CONFIG_PATH.write_text("[agent]\nmodel = " + json.dumps(model) + "\n", encoding="utf-8")


def get_api_key(cfg: dict) -> str:
    """Read credentials exclusively from the environment, not config files."""
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        raise RuntimeError(
            "NVIDIA_API_KEY not set. Set the NVIDIA_API_KEY environment variable "
            "before starting Revona."
        )
    return key
