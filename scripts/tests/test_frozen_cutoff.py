"""Tests for the literature-cutoff enforcement.

The offline tests lock in the date logic that is the security guarantee; they
need no network. The two network tests (marked) confirm the live arXiv/Wayback
behaviour and can be skipped in CI with `-m 'not network'`.

Run:  python3 -m pytest scripts/tests/test_frozen_cutoff.py -q
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent


def _load_proxy(cutoff="2024-12-31"):
    os.environ["RETHLAS_LITERATURE_CUTOFF"] = cutoff
    spec = importlib.util.spec_from_file_location("frozen_proxy", SCRIPTS / "frozen_proxy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- offline: date parsing + cutoff arithmetic (the core guarantee) ----

def test_date_int_parsing():
    fp = _load_proxy()
    assert fp._date_int("2024-05-01T12:00:00Z") == 20240501
    assert fp._date_int("20240501") == 20240501
    assert fp._date_int("garbage") is None


def test_cutoff_constants():
    fp = _load_proxy("2024-12-31")
    assert fp.CUTOFF_INT == 20241231
    assert fp.WB_TS == "20241231235959"


def test_cutoff_is_a_parameter():
    assert _load_proxy("2010-12-31").CUTOFF_INT == 20101231
    assert _load_proxy("2024-12-31").CUTOFF_INT == 20241231


def test_arxiv_query_embeds_date_range():
    # the built query must AND a paren term-group with the submittedDate window
    fp = _load_proxy("2024-12-31")
    import urllib.request
    captured = {}
    fp._get = lambda url, timeout=30: (captured.setdefault("url", url) or "<feed></feed>", 200, url)
    fp.arxiv_search("class field tower", 3)
    assert "submittedDate:[" in captured["url"]
    assert "202412312359" in captured["url"]
    assert "%28all:" in captured["url"]  # paren-grouped terms


def test_post_cutoff_arxiv_entry_filtered():
    fp = _load_proxy("2024-12-31")
    feed = ("<feed><entry><id>http://arxiv.org/abs/2605.20579</id>"
            "<title>target</title><published>2026-05-20T00:00:00Z</published>"
            "<updated>2026-05-20T00:00:00Z</updated><summary>x</summary></entry></feed>")
    fp._get = lambda url, timeout=30: (feed, 200, url)
    assert fp.arxiv_search("anything", 5) == []  # 2026 entry dropped


def test_pre_cutoff_arxiv_entry_kept():
    fp = _load_proxy("2024-12-31")
    feed = ("<feed><entry><id>http://arxiv.org/abs/2406.00797</id>"
            "<title>tower</title><published>2024-06-02T00:00:00Z</published>"
            "<updated>2024-06-02T00:00:00Z</updated><summary>x</summary></entry></feed>")
    fp._get = lambda url, timeout=30: (feed, 200, url)
    out = fp.arxiv_search("anything", 5)
    assert len(out) == 1 and out[0]["id"] == "2406.00797"


def test_web_fetch_refuses_post_cutoff_snapshot():
    fp = _load_proxy("2024-12-31")
    # CDX returns only a 2026 capture -> must refuse
    fp._get = lambda url, timeout=30: ('[["timestamp","original","statuscode"],'
                                       '["20260101000000","http://x","200"]]', 200, url)
    res, err = fp.web_fetch("http://x")
    assert res is None and "after cutoff" in err


def test_web_fetch_refuses_when_no_snapshot():
    fp = _load_proxy("2024-12-31")
    fp._get = lambda url, timeout=30: ('[["timestamp","original","statuscode"]]', 200, url)
    res, err = fp.web_fetch("http://never-archived")
    assert res is None and "no Wayback snapshot" in err


# ---- offline: the audit tripwire ----

def _load_audit():
    spec = importlib.util.spec_from_file_location("audit", SCRIPTS / "audit_blind_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_audit_flags_evasion_and_web_search():
    a = _load_audit()
    log = (
        "/bin/bash -lc 'env -u LD_PRELOAD curl https://arxiv.org/abs/2605.20579' in /home/x\n"
        "/bin/bash -lc 'curl https://www.erdosproblems.com/186' in /home/x\n"
        "web search: erdos unit distance disproved\n"
    )
    out = a.audit("# problem", log, "p/x")
    kinds = {v["type"] for v in out["violations"]}
    assert "egress_block_evasion" in kinds
    assert "direct_network_access" in kinds
    assert "native_web_search" in kinds
    assert out["ok"] is False


def test_audit_clean_log_passes():
    a = _load_audit()
    out = a.audit("# problem", "wrote branch_states; proved a lemma.\n", "p/x")
    assert out["ok"] is True


# ---- network: live arXiv / Wayback (skip with -m 'not network') ----

@pytest.mark.network
def test_live_arxiv_refuses_target_paper():
    fp = _load_proxy("2024-12-31")
    res, err = fp.arxiv_fetch("2605.20579")
    assert res is None and "after cutoff" in err


@pytest.mark.network
def test_live_arxiv_search_only_pre_cutoff():
    fp = _load_proxy("2024-12-31")
    for r in fp.arxiv_search("class field tower", 5):
        assert fp._date_int(r["published"]) <= fp.CUTOFF_INT
