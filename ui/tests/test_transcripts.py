import json

from app.transcripts import read_transcript, simplify
from conftest import SESSION_A


def test_read_transcript_kinds(settings):
    t = read_transcript(settings, SESSION_A)
    kinds = [e["kind"] for e in t["events"]]
    assert kinds == ["meta", "message", "reasoning", "call", "call",
                     "output", "output", "compacted", "message"]
    assert t["truncated"] == 0
    assert t["offset"] == t["size"]


def test_call_output_pairing_ids(settings):
    t = read_transcript(settings, SESSION_A)
    calls = [e for e in t["events"] if e["kind"] == "call"]
    outs = [e for e in t["events"] if e["kind"] == "output"]
    assert [c["call_id"] for c in calls] == ["call_1", "call_2"]
    assert [o["call_id"] for o in outs] == ["call_1", "call_2"]


def test_offset_resume(settings):
    full = read_transcript(settings, SESSION_A)
    first = read_transcript(settings, SESSION_A, offset=0, limit=3)
    assert first["truncated"] == len(full["events"]) - 3
    # resume from returned offset yields nothing new
    again = read_transcript(settings, SESSION_A, offset=full["offset"])
    assert again["events"] == []
    assert again["offset"] == full["offset"]


def test_offset_beyond_size_resets(settings):
    t = read_transcript(settings, SESSION_A, offset=10**9)
    assert t["events"]  # re-read from start


def test_unknown_session(settings):
    assert read_transcript(settings, "deadbeef-0000") is None


def test_simplify_truncation():
    ev = simplify({"type": "response_item",
                   "payload": {"type": "function_call_output", "call_id": "c",
                               "output": "x" * 10000}})
    assert len(ev["text"]) < 5000
    assert "more chars" in ev["text"]


def test_simplify_skips_empty_reasoning():
    assert simplify({"type": "response_item",
                     "payload": {"type": "reasoning", "summary": [],
                                 "encrypted_content": "gAAA"}}) is None


def test_simplify_partial_line_ignored(settings):
    path = settings.sessions_dir / "2026" / "06" / "09"
    f = next(path.glob(f"*{SESSION_A}.jsonl"))
    with open(f, "a") as fh:
        fh.write(json.dumps({"type": "response_item",
                             "payload": {"type": "message", "role": "assistant",
                                         "content": [{"type": "output_text", "text": "tail"}]}})[:20])
    t = read_transcript(settings, SESSION_A)
    # incomplete trailing line must not be consumed
    assert t["offset"] < t["size"]
    assert all(e.get("text") != "tail" for e in t["events"])
