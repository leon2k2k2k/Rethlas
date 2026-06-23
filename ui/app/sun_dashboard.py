"""Live campaign dashboard for the Sun-prize overnight runs (GET /sun).

Self-contained server-side HTML; scans the generation root on each request
(cheap: a few dozen stat/read calls) and auto-refreshes every 30s.
"""
import json
import re
import time
from pathlib import Path

_LABELS = {
    "prob-001": "$3500 a²+b²+3ᶜ+5ᵈ",
    "prob-002": "$2500 four squares w/ S-unit squares",
    "prob-003": "$2468 2-4-6-8",
    "prob-004": "$2400 24-conjecture",
    "prob-005": "$1000 2ᵏ+m prime",
    "prob-006": "$1000 alternating prime sums",
    "prob-007": "2000RMB primitive roots x²+1",
    "prob-007b": "↳ re-scope: safe-prime class",
    "prob-007c": "↳ re-scope: GRH, all primes",
    "prob-008": "1680RMB 1680-conjecture",
    "prob-009": "$234 x⁴+y³+z²+2ᵏ",
    "prob-010": "$200 x+ny, x²+ny² prime",
    "prob-011": "$135 little 1-3-5",
    "prob-012": "$100 Bertrand-style",
}


def _latest_verdict(results_dir: Path):
    best = None
    for f in sorted(results_dir.glob("verification_attempt_*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if "verification_report" not in d:
            continue
        r = d["verification_report"]
        best = (d.get("verdict"), len(r.get("critical_errors", [])),
                len(r.get("gaps", [])), f.name)
    return best


def _lane_state(log: Path):
    if not log.exists():
        return ""
    try:
        line = log.read_text().strip().splitlines()[-1]
    except Exception:
        return ""
    m = re.search(r"\] (.*)", line)
    return (m.group(1) if m else line)[:90]


def _lane_queue(log: Path):
    """Return (problems, started, last_line) parsed from a lane log."""
    if not log.exists():
        return None
    try:
        text = log.read_text()
    except Exception:
        return None
    m = re.search(r"problems=([\d\s]+?) attempts", text)
    probs = m.group(1).split() if m else []
    started = re.findall(r"starting sun_prizes/prob-(\S+)", text)
    lines = text.strip().splitlines()
    return probs, started, (lines[-1][-90:] if lines else "")


def render(gen_root: Path) -> str:
    now = time.time()
    rows = []
    base = gen_root / "results" / "sun_prizes"
    for pid in sorted(_LABELS):
        rdir = base / pid
        label = _LABELS[pid]
        hb = ""
        hbf = rdir / "heartbeat.txt"
        running = False
        if hbf.exists():
            age = int(now - hbf.stat().st_mtime)
            running = age < 180
            hb = f"{age}s" if age < 3600 else f"{age // 3600}h{(age % 3600) // 60}m"
        verified = (rdir / "blueprint_verified.md").exists()
        v = _latest_verdict(rdir) if rdir.exists() else None
        verdict = ""
        if verified:
            verdict = "✅ VERIFIED (correct 0/0)"
        elif v:
            verdict = f"{v[0]} — {v[1]} errs / {v[2]} gaps"
        state = _lane_state(gen_root / "logs" / "sun_prizes" / pid / "lane.log")
        att = ""
        m = re.search(r"Attempt (\d+)(?:/(\d+))?", state)
        if m:
            att = f"att {m.group(1)}" + (f"/{m.group(2)}" if m.group(2) else "")
        bp = rdir / "blueprint.md"
        link = (f"<a href='/api/file?root=main&path=results/sun_prizes/{pid}/"
                f"{'blueprint_verified.md' if verified else 'blueprint.md'}'>📄</a>"
                if (verified or bp.exists()) else "")
        cls = "ok" if verified else ("run" if running else "idle")
        rows.append(
            f"<tr class='{cls}'><td>{pid} {link}</td><td>{label}</td>"
            f"<td>{'🟢' if running else ('🏁' if verified else '⚪')} {hb}</td>"
            f"<td>{att}</td><td>{verdict}</td><td class='st'>{state}</td></tr>"
        )

    lanes_html = ""
    for name, logname in [("gpt lane 2", "lane_gpt2.log"),
                          ("gpt lane 3", "lane_gpt3.log"),
                          ("DS lane (retired)", "lane_ds.log")]:
        q = _lane_queue(gen_root / "logs" / "sun_prizes" / logname)
        if not q:
            continue
        probs, started, last = q
        cur = started[-1] if started else "?"
        done = ", ".join(started[:-1]) or "—"
        todo = ", ".join(p for p in probs if p not in started) or "—"
        lanes_html += (f"<div class='lane'><b>{name}</b>: now <b>prob-{cur}</b>"
                       f" · done: {done} · queued: {todo}"
                       f"<br><span class='st'>{last}</span></div>")

    fp = gen_root / "results" / "first_proof" / "prob-007"
    fp_note = "✅ VERIFIED" if (fp / "blueprint_verified.md").exists() else "—"

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<title>Sun campaign — live</title>
<style>
body{{font-family:ui-monospace,Menlo,monospace;background:#0d1117;color:#c9d1d9;margin:2em}}
h1{{font-size:1.2em}} table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #21262d;padding:6px 10px;text-align:left;font-size:.85em}}
tr.ok td{{color:#3fb950}} tr.run td{{color:#e3b341}} tr.idle td{{color:#8b949e}}
.st{{color:#58a6ff!important;font-size:.75em}}
.hdr{{color:#3fb950;margin:.4em 0}}
.lane{{border:1px solid #21262d;border-radius:6px;padding:6px 10px;margin:4px 0;font-size:.85em}}
a{{color:#58a6ff;text-decoration:none}}
</style></head><body>
<h1>☀️ Sun prize campaign — live dashboard <small>(auto-refresh 30s, {time.strftime('%H:%M:%S')})</small></h1>
<div class="hdr">🏆 prob-007b: DOUBLE-VERIFIED candidate theorem (safe-prime class) &nbsp;|&nbsp;
📐 prob-011: 0-error conditional theorem &nbsp;|&nbsp;
First Proof prob-007: {fp_note}</div>
{lanes_html}
<table><tr><th>problem</th><th>prize / statement</th><th>alive</th><th>attempt</th><th>latest verdict</th><th>lane state</th></tr>
{''.join(rows)}</table>
<p style="color:#8b949e;font-size:.8em">🟢 running (heartbeat &lt;3min) · 🏁 verified · ⚪ settled/idle.
Full notes: notes/sun_prizes_overnight_report.md · candidates: results/sun_prizes/CANDIDATES.md</p>
</body></html>"""
