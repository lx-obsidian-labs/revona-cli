import json
import time
from pathlib import Path

from . import SESSIONS_DIR


def new_session_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def save_session(session_id: str, messages: list) -> None:
    SESSIONS_DIR.mkdir(exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m) + "\n")


def load_session(session_id: str) -> list:
    path = SESSIONS_DIR / f"{session_id}.jsonl"
    if not path.exists():
        return []
    msgs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                msgs.append(json.loads(line))
    return msgs
