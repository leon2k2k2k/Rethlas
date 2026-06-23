#!/usr/bin/env python3
"""Frozen-literature proxy: the single egress gate for a cutoff-restricted run.

Runs as a localhost daemon WITHOUT the noegress LD_PRELOAD, so it has real
network access. Everything it serves is frozen at RETHLAS_LITERATURE_CUTOFF:

  GET /search?q=<query>&max=<n>
      arXiv API search, results hard-filtered to v1 submittedDate <= cutoff.
  GET /fetch_arxiv?id=<arxiv_id>
      arXiv abstract + metadata; refuses papers first submitted after cutoff;
      reports the latest version revised on or before the cutoff.
  GET /fetch_web?url=<url>
      The page as captured by the Wayback Machine on/before the cutoff.
      Refuses if no snapshot exists at or before the cutoff.
  GET /health

Every served request is appended to RETHLAS_PROXY_LOG (jsonl) so a run's full
external bibliography is auditable.

The cutoff is the clock: a math agent behind this proxy sees the world exactly
as it existed on the cutoff date and cannot reach anything published later.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CUTOFF = os.environ.get("RETHLAS_LITERATURE_CUTOFF", "2024-12-31")
PORT = int(os.environ.get("RETHLAS_PROXY_PORT", "38450"))
PROXY_LOG = os.environ.get("RETHLAS_PROXY_LOG", "/tmp/frozen_proxy.jsonl")
UA = "rethlas-frozen-proxy/1.0"

# cutoff as YYYYMMDD int and a Wayback timestamp (end of cutoff day)
_c = CUTOFF.replace("-", "")
CUTOFF_INT = int(_c)
WB_TS = _c + "235959"


def _log(kind, detail, allowed):
    try:
        with open(PROXY_LOG, "a") as f:
            f.write(json.dumps({
                "t": int(time.time()), "kind": kind, "detail": detail,
                "allowed": allowed, "cutoff": CUTOFF,
            }) + "\n")
    except OSError:
        pass


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
            import gzip
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        return raw.decode("utf-8", "replace"), r.status, r.geturl()


def _date_int(iso):
    """'2024-05-01T...' or '20240501...' -> 20240501 int, else None."""
    m = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", iso or "")
    return int(m.group(1) + m.group(2) + m.group(3)) if m else None


# ----- arXiv -----
ARXIV_API = "http://export.arxiv.org/api/query"
_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.S)
def _tag(block, name):
    m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
    return (m.group(1).strip() if m else "")


def arxiv_search(query, max_results):
    # Constrain the query itself to the frozen window so arXiv returns only
    # pre-cutoff papers. The arXiv API date-range operator is mangled by
    # urlencode (it encodes the ':[ ]' operators), so build the query string
    # by hand: '+' for spaces, literal operators, phrase in %22 quotes.
    # AND the terms inside a paren group so the trailing date AND binds to the
    # whole group (arXiv's parser otherwise ORs bare terms and drops the date).
    group = "+AND+".join(f"all:{urllib.parse.quote(t)}" for t in query.split() if t)
    date_range = f"submittedDate:[199101010000+TO+{_c}2359]"
    n = min(max(max_results, 1), 50)
    qs = (f"search_query=%28{group}%29+AND+{date_range}"
          f"&start=0&max_results={n}&sortBy=submittedDate&sortOrder=descending")
    body, _, _ = _get(f"{ARXIV_API}?{qs}")
    out = []
    for block in _ENTRY.findall(body):
        published = _tag(block, "published")
        pid = _tag(block, "id")
        if _date_int(published) is None or _date_int(published) > CUTOFF_INT:
            continue  # submitted after cutoff -> does not exist in frozen world
        out.append({
            "id": pid.rsplit("/", 1)[-1],
            "title": " ".join(_tag(block, "title").split()),
            "published": published,
            "updated": _tag(block, "updated"),
            "summary": " ".join(_tag(block, "summary").split())[:1200],
        })
    return out


def arxiv_fetch(arxiv_id):
    clean = re.sub(r"[^0-9A-Za-z.\-/]", "", arxiv_id).split("v")[0]
    q = urllib.parse.urlencode({"id_list": clean})
    body, _, _ = _get(f"{ARXIV_API}?{q}")
    blocks = _ENTRY.findall(body)
    if not blocks:
        return None, "no such arXiv id"
    b = blocks[0]
    published = _tag(b, "published")
    if _date_int(published) is None or _date_int(published) > CUTOFF_INT:
        return None, f"paper first submitted {published} is after cutoff {CUTOFF}"
    # version pinning: ask the abstract page (via Wayback at cutoff) which
    # versions existed by then; report the newest one.
    pinned = _arxiv_version_asof(clean)
    return {
        "id": clean,
        "title": " ".join(_tag(b, "title").split()),
        "authors": re.findall(r"<name>(.*?)</name>", b),
        "published": published,
        "updated": _tag(b, "updated"),
        "pinned_version_asof_cutoff": pinned,
        "summary": " ".join(_tag(b, "summary").split()),
    }, None


def _arxiv_version_asof(clean):
    """Best-effort: read the arXiv abs page as frozen by Wayback (CDX, closest
    capture <= cutoff) and return the highest version listed by then."""
    try:
        cdx = ("http://web.archive.org/cdx/search/cdx?url=arxiv.org/abs/" +
               clean + f"&to={WB_TS}&output=json&fl=timestamp&filter=statuscode:200&limit=-1")
        rows = json.loads(_get(cdx, timeout=20)[0])
        data = rows[1:] if rows and rows[0][0] == "timestamp" else rows
        if not data:
            return "unknown (no pre-cutoff abs snapshot)"
        ts = data[-1][0]
        body, _, _ = _get(f"http://web.archive.org/web/{ts}id_/https://arxiv.org/abs/{clean}", timeout=25)
        vers = re.findall(r"\[v(\d+)\]", body)
        if vers:
            return f"v{max(int(v) for v in vers)} (as of {ts[:8]})"
    except Exception:
        pass
    return "unknown (no pre-cutoff abs snapshot)"


# ----- general web via Wayback -----
def web_fetch(url, timeout=12):
    # Use the Wayback CDX API for the most recent successful capture at or
    # before the cutoff (more reliable than the availability endpoint).
    cdx = ("http://web.archive.org/cdx/search/cdx?url=" +
           urllib.parse.quote(url, safe="") +
           f"&to={WB_TS}&output=json&fl=timestamp,original,statuscode"
           "&filter=statuscode:200&limit=-1")
    try:
        rows = json.loads(_get(cdx, timeout=min(timeout, 12))[0])
    except Exception as e:
        return None, f"wayback lookup failed: {e}"
    data = rows[1:] if rows and rows[0][0] == "timestamp" else rows
    if not data:
        return None, f"no Wayback snapshot at or before cutoff {CUTOFF}"
    ts = data[-1][0]
    if int(ts[:8]) > CUTOFF_INT:
        return None, f"closest snapshot {ts[:8]} is after cutoff {CUTOFF}"
    # id_ suffix returns the raw archived bytes without the Wayback chrome
    raw = f"http://web.archive.org/web/{ts}id_/{url}"
    body, status, final = _get(raw, timeout=timeout)
    text = re.sub(r"<script.*?</script>", " ", body, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"snapshot_timestamp": ts, "url": url, "text": text[:20000]}, None


# ----- frozen general web search -----
# Use a live search engine ONLY to discover candidate URLs, then return each
# one as its Wayback snapshot at/before the cutoff. URLs with no pre-cutoff
# snapshot are dropped, and titles/snippets come from the frozen page (never
# the live SERP), so post-cutoff content cannot surface.
def _candidates(query):
    """Discover candidate reference URLs via Wikipedia OpenSearch (no key, fast,
    bot-friendly). The content the agent sees is always the cutoff-frozen
    Wayback snapshot, so a live listing cannot leak post-cutoff text."""
    urls = []
    try:
        wp = ("https://en.wikipedia.org/w/api.php?action=opensearch&limit=8"
              "&format=json&search=" + urllib.parse.quote(query))
        data = json.loads(_get(wp, timeout=8)[0])
        urls += [u for u in data[3] if u.startswith("http")]
    except Exception:
        pass
    return urls[:8]


def web_search(query, max_results):
    import time as _t
    deadline = _t.time() + 22        # always return within ~22s
    out = []
    for cand in _candidates(query):
        if len(out) >= max_results or _t.time() > deadline:
            break
        snap, err = web_fetch(cand, timeout=7)   # frozen Wayback snapshot
        if err:
            continue                 # no pre-cutoff snapshot -> didn't exist yet
        out.append({
            "url": cand,
            "snapshot_timestamp": snap.get("snapshot_timestamp"),
            "snippet": snap.get("text", "")[:500],
        })
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/health":
                return self._send(200, {"status": "ok", "cutoff": CUTOFF})
            if u.path == "/search":
                q = qs.get("q", [""])[0]
                n = int(qs.get("max", ["10"])[0])
                res = arxiv_search(q, n)
                _log("search", q, True)
                return self._send(200, {"cutoff": CUTOFF, "results": res})
            if u.path == "/fetch_arxiv":
                aid = qs.get("id", [""])[0]
                res, err = arxiv_fetch(aid)
                _log("fetch_arxiv", aid, err is None)
                if err:
                    return self._send(403, {"error": err, "cutoff": CUTOFF})
                return self._send(200, res)
            if u.path == "/fetch_web":
                url = qs.get("url", [""])[0]
                res, err = web_fetch(url)
                _log("fetch_web", url, err is None)
                if err:
                    return self._send(403, {"error": err, "cutoff": CUTOFF})
                return self._send(200, res)
            if u.path == "/web_search":
                q = qs.get("q", [""])[0]
                n = int(qs.get("max", ["6"])[0])
                res = web_search(q, n)
                _log("web_search", q, True)
                return self._send(200, {"cutoff": CUTOFF, "results": res})
            return self._send(404, {"error": "unknown endpoint"})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    sys.stderr.write(f"frozen_proxy on 127.0.0.1:{PORT}, cutoff={CUTOFF}\n")
    sys.stderr.flush()
    srv.serve_forever()


if __name__ == "__main__":
    main()
