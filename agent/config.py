import os
import tomllib
from pathlib import Path

from . import CONFIG_PATH, DEFAULT_MODEL


def load_config() -> dict:
    cfg = {"model": DEFAULT_MODEL, "api_key": os.environ.get("NVIDIA_API_KEY", "")}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "rb") as f:
                data = tomllib.load(f)
            cfg.update(data.get("agent", {}))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    lines = ["[agent]", f'model = "{cfg.get("model", DEFAULT_MODEL)}"', ""]
    CONFIG_PATH.write_text("\n".join(lines))


def get_api_key(cfg: dict) -> str:
    key = cfg.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        raise RuntimeError(
            "NVIDIA_API_KEY not set. Run `revona config --key nvapi-...` "
            "or export NVIDIA_API_KEY in your environment."
        )
    return key
