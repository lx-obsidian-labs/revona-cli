import json
import time
import re
from uuid import uuid4
from pathlib import Path

from . import SESSIONS_DIR


def new_session_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:12]


def _session_path(session_id: str) -> Path:
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", session_id):
        raise ValueError("Invalid session identifier")
    return SESSIONS_DIR / (session_id + ".jsonl")


def save_session(session_id: str, messages: list) -> None:
    SESSIONS_DIR.mkdir(exist_ok=True)
    path = _session_path(session_id)
    with open(path, "w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m) + "\n")


def load_session(session_id: str) -> list:
    path = _session_path(session_id)
    if not path.exists():
        return []
    msgs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                msgs.append(json.loads(line))
    return msgs
