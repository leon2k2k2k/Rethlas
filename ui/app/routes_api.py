"""Route cards (discovery output) and promotion lineage."""
import json

from .config import Settings

_MANIFESTS = ("promotion_manifest.json", "source_obstruction_promotion_manifest.json")


def _load_json(path):
    try:
        return json.loads(path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def read_routes(settings: Settings, run: dict) -> dict:
    rdir = settings.roots[run["root"]] / "results" / run["rel_id"]
    out = {"cards": [], "batch_manifest": None, "promotion_decision": None,
           "promotion_manifest": None, "triage_report": None}
    if not rdir.is_dir():
        return out
    card_paths = sorted(rdir.glob("route_card.json")) + sorted(rdir.glob("sample_*/route_card.json"))
    for p in card_paths:
        card = _load_json(p)
        if card is None:
            continue
        validation = _load_json(p.parent / "route_card_validation.json")
        out["cards"].append({
            "sample": p.parent.name if p.parent != rdir else None,
            "card": card,
            "valid": (validation or {}).get("valid"),
            "errors": (validation or {}).get("errors") or [],
        })
    out["batch_manifest"] = _load_json(rdir / "batch_manifest.json")
    out["promotion_decision"] = _load_json(rdir / "promotion_decision.json")
    for name in _MANIFESTS:
        m = _load_json(rdir / name)
        if m:
            out["promotion_manifest"] = m
            break
    tr = rdir / "triage_report.md"
    if tr.is_file():
        out["triage_report"] = tr.read_text(errors="replace")[:40_000]
    return out


def read_lineage(settings: Settings, index, run: dict) -> dict:
    """parents: runs whose promotion manifests generated this run's problem;
    children: runs generated from this run's promotion manifests."""
    gen = settings.roots[run["root"]]
    results = gen / "results"
    prefix = "" if run["root"] == "main" else f"{run['root']}/"
    parents, children = [], []

    my_children_ids = set()
    rdir = results / run["rel_id"]
    if rdir.is_dir():
        for name in _MANIFESTS:
            m = _load_json(rdir / name)
            if m and m.get("generated_problem_id"):
                my_children_ids.add(m["generated_problem_id"])

    if not results.is_dir():
        return {"parents": [], "children": []}
    known = {r["rel_id"]: r["id"] for r in index.discover() if r["root"] == run["root"]}

    for cat in results.iterdir():
        if not cat.is_dir():
            continue
        for other in cat.iterdir():
            if not other.is_dir():
                continue
            rel = f"{cat.name}/{other.name}"
            if rel == run["rel_id"]:
                continue
            for name in _MANIFESTS:
                m = _load_json(other / name)
                if not m:
                    continue
                gid = m.get("generated_problem_id")
                if gid == run["rel_id"]:
                    parents.append({"id": prefix + rel, "action": m.get("action")})
                elif gid and gid in my_children_ids and rel == gid:
                    pass  # handled below via my_children_ids
    for gid in sorted(my_children_ids):
        children.append({"id": known.get(gid, prefix + gid), "rel_id": gid,
                         "exists": gid in known})
    return {"parents": parents, "children": children}
