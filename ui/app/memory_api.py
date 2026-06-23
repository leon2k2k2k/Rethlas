"""Memory journal channels for a run."""
import json

from .config import Settings


def read_memory(settings: Settings, run: dict, limit_per_channel: int = 300) -> dict:
    mdir = settings.roots[run["root"]] / "memory" / run["rel_id"]
    channels = {}
    if mdir.is_dir():
        for p in sorted(mdir.glob("*.jsonl")):
            records = []
            try:
                for line in open(p, errors="replace"):
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            except OSError:
                continue
            channels[p.stem] = records[-limit_per_channel:]
    return {"run": run["id"], "channels": channels}
