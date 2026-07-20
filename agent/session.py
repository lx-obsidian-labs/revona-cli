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


def list_sessions() -> list[dict]:
    SESSIONS_DIR.mkdir(exist_ok=True)
    sessions = []
    for p in sorted(SESSIONS_DIR.glob("*.jsonl"), reverse=True):
        sid = p.stem
        try:
            msgs = load_session(sid)
            user_msgs = [m for m in msgs if m.get("role") == "user"]
            first_msg = ""
            if user_msgs:
                content = user_msgs[0].get("content", "")
                first_msg = content[:100].replace("\n", " ")
            modified_files = set()
            for m in msgs:
                if m.get("role") == "tool":
                    pass
                tc = m.get("tool_calls", [])
                for t in tc:
                    fn = t.get("function", {}).get("name", "")
                    if fn in ("write_file", "edit_file"):
                        try:
                            args = json.loads(t.get("function", {}).get("arguments", "{}"))
                            fp = args.get("path", "")
                            if fp:
                                modified_files.add(fp)
                        except Exception:
                            pass
            sessions.append({
                "id": sid,
                "message_count": len(msgs),
                "first_message": first_msg,
                "modified_files": sorted(modified_files),
                "file_path": str(p),
            })
        except Exception:
            sessions.append({
                "id": sid,
                "message_count": 0,
                "first_message": "(error reading session)",
                "modified_files": [],
                "file_path": str(p),
            })
    return sessions


def search_sessions(query: str) -> list[dict]:
    q = query.lower()
    results = []
    for s in list_sessions():
        if q in s["first_message"].lower():
            results.append(s)
            continue
        for fp in s["modified_files"]:
            if q in fp.lower():
                results.append(s)
                break
    return results
