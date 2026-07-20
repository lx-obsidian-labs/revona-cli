import json
import os
from pathlib import Path

import requests

from . import MODELS_CACHE_PATH


def _categorize(model_id: str) -> str:
    """Assign a rough category based on model name patterns."""
    mid = model_id.lower()
    if any(k in mid for k in ("code", "coder", "codestral", "starcoder", "deepseek-v4", "nemotron", "mistral-nemotron")):
        return "coding"
    if any(k in mid for k in ("embed", "rerank", "bge", "retriever")):
        return "embedding"
    if any(k in mid for k in ("safety", "guard", "content")):
        return "safety"
    if any(k in mid for k in ("voice", "tts", "asr", "translate", "speech")):
        return "speech"
    if any(k in mid for k in ("vision", "vlm", "kosmos", "paligemma")):
        return "vision"
    if any(k in mid for k in ("pii",)):
        return "pii"
    if any(k in mid for k in ("cosmos", "driving", "bevformer", "streampetr", "sparsedrive")):
        return "autonomous"
    if any(k in mid for k in ("protein", "esmfold", "genmol", "molmim", "diffdock")):
        return "biology"
    return "general"


def fetch_models(api_key: str, base_url: str) -> list[dict]:
    """Fetch available models from the NVIDIA NIM API."""
    resp = requests.get(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()["data"]
    models = []
    for m in raw:
        models.append({
            "id": m["id"],
            "owner": m.get("owned_by", ""),
            "category": _categorize(m["id"]),
        })
    models.sort(key=lambda x: x["id"])
    return models


def cache_models(models: list[dict], path: Path) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(models, indent=2), encoding="utf-8")


def load_cached_models(path: Path | None = None) -> list[dict]:
    p = path or MODELS_CACHE_PATH
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def refresh(api_key: str, base_url: str) -> list[dict]:
    models = fetch_models(api_key, base_url)
    cache_models(models, MODELS_CACHE_PATH)
    return models
