"""Codex rollout parsing: simplify JSONL records into UI events.

Reading is incremental by byte offset so live sessions can be tailed; only
complete lines are consumed and the new offset is returned to the client.
"""
import glob
import json
import os

from .config import Settings


def _text_of(items) -> str:
    parts = []
    for item in items or []:
        if isinstance(item, dict):
            t = item.get("text")
            if t:
                parts.append(t)
    return "\n".join(parts)


def _trunc(value, n=4000):
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    return (s[:n] + f"\n... [{len(s) - n} more chars]") if len(s) > n else s


def simplify(record: dict):
    rtype = record.get("type")
    p = record.get("payload", {})
    if rtype == "session_meta":
        return {"kind": "meta", "cwd": p.get("cwd"), "model_provider": p.get("model_provider"),
                "cli_version": p.get("cli_version"), "timestamp": p.get("timestamp")}
    if rtype == "compacted" or (rtype == "event_msg" and p.get("type") == "context_compacted"):
        return {"kind": "compacted"}
    if rtype != "response_item":
        return None
    ptype = p.get("type")
    if ptype == "message":
        text = _text_of(p.get("content"))
        if text:
            return {"kind": "message", "role": p.get("role"), "text": _trunc(text, 20000)}
    elif ptype == "reasoning":
        text = _text_of(p.get("summary")) or _text_of(p.get("content"))
        if text:
            return {"kind": "reasoning", "text": _trunc(text, 8000)}
    elif ptype in ("function_call", "custom_tool_call"):
        return {"kind": "call", "name": p.get("name"), "call_id": p.get("call_id") or p.get("id"),
                "args": _trunc(p.get("arguments") or p.get("input") or "", 2000)}
    elif ptype in ("function_call_output", "custom_tool_call_output"):
        return {"kind": "output", "call_id": p.get("call_id") or p.get("id"),
                "text": _trunc(p.get("output") or "", 4000)}
    elif ptype == "web_search_call":
        action = p.get("action") or {}
        return {"kind": "search", "query": action.get("query") or _trunc(action, 200)}
    return None


def find_rollout(settings: Settings, session_id: str):
    matches = glob.glob(str(settings.sessions_dir / "**" / f"rollout-*-{session_id}.jsonl"),
                        recursive=True)
    return matches[0] if matches else None


def read_transcript(settings: Settings, session_id: str, offset: int = 0, limit: int = 2000):
    path = find_rollout(settings, session_id)
    if path is None:
        return None
    size = os.path.getsize(path)
    if offset > size:
        offset = 0
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n")
    if end == -1:
        return {"events": [], "offset": offset, "size": size, "truncated": 0}
    events = []
    for line in data[: end + 1].splitlines():
        try:
            ev = simplify(json.loads(line))
        except json.JSONDecodeError:
            continue
        if ev:
            events.append(ev)
    truncated = max(0, len(events) - limit)
    return {"events": events[-limit:], "offset": offset + end + 1, "size": size,
            "truncated": truncated}
