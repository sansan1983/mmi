"""tests/test_trace.py —— Trace 持久化测试（P3-2）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.agent.trace import TraceRecord, Tracer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _tmp_tracer(tmp_path: Path) -> Tracer:
    traces_dir = tmp_path / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    Tracer.reset_instance()
    return Tracer(traces_dir=traces_dir)


def _sample_trace(session_id: str = "sess-001", trace_id: str = "tr-001") -> TraceRecord:
    return TraceRecord(
        trace_id=trace_id,
        session_id=session_id,
        turn_index=0,
        intent="chat",
        agent_id="default",
        user_message="Hello",
        response="Hi there!",
        mode="standard",
        latency_ms=150.5,
        tokens_used=42,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_trace_to_dict_excludes_private():
    t = _sample_trace()
    d = t.to_dict(include_private=False)
    assert "user_message" not in d
    assert "response" not in d
    assert d["trace_id"] == "tr-001"
    assert d["latency_ms"] == 150.5


def test_trace_to_dict_includes_private():
    t = _sample_trace()
    d = t.to_dict(include_private=True)
    assert d["user_message"] == "Hello"
    assert d["response"] == "Hi there!"


def test_trace_from_dict_with_missing_fields():
    d = {"trace_id": "x", "session_id": "s", "turn_index": 0,
         "intent": "chat", "agent_id": "a", "mode": "m", "latency_ms": 1.0}
    t = TraceRecord.from_dict(d)
    assert t.user_message == ""
    assert t.response == ""


def test_trace_roundtrip():
    t = _sample_trace()
    d = t.to_dict(include_private=True)
    t2 = TraceRecord.from_dict(d)
    assert t2.trace_id == t.trace_id
    assert t2.user_message == "Hello"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_record_appends_to_jsonl(tmp_path):
    tracer = _tmp_tracer(tmp_path)
    tracer.record(_sample_trace("sess-001", "tr-001"))
    tracer.record(_sample_trace("sess-001", "tr-002"))

    fpath = tracer._trace_file("sess-001")
    assert fpath.exists()
    lines = fpath.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2

    # Verify no private data in file
    data = json.loads(lines[0])
    assert "user_message" not in data
    assert "response" not in data
    assert data["trace_id"] == "tr-001"


def test_different_sessions_separate_files(tmp_path):
    tracer = _tmp_tracer(tmp_path)
    tracer.record(_sample_trace("sess-a", "tr-a1"))
    tracer.record(_sample_trace("sess-b", "tr-b1"))

    assert tracer._trace_file("sess-a").exists()
    assert tracer._trace_file("sess-b").exists()


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def test_query_by_session(tmp_path):
    tracer = _tmp_tracer(tmp_path)
    tracer.record(_sample_trace("sess-a", "tr-1"))
    tracer.record(_sample_trace("sess-b", "tr-2"))
    results = tracer.query(session_id="sess-a")
    assert len(results) == 1
    assert results[0].session_id == "sess-a"


def test_query_by_intent(tmp_path):
    tracer = _tmp_tracer(tmp_path)
    tracer.record(TraceRecord(
        trace_id="t1", session_id="s", turn_index=0,
        intent="code", agent_id="a", user_message="x",
        response="y", mode="m", latency_ms=10,
    ))
    tracer.record(_sample_trace())  # intent="chat"
    results = tracer.query(intent="code")
    assert len(results) == 1


def test_get_turn_count(tmp_path):
    tracer = _tmp_tracer(tmp_path)
    tracer.record(_sample_trace("s1", "t1"))
    tracer.record(_sample_trace("s1", "t2"))
    tracer.record(_sample_trace("s2", "t3"))
    assert tracer.get_turn_count("s1") == 2
    assert tracer.get_turn_count("s2") == 1


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_stats_empty(tmp_path):
    tracer = _tmp_tracer(tmp_path)
    stats = tracer.stats()
    assert stats["total_records"] == 0


def test_stats_with_records(tmp_path):
    tracer = _tmp_tracer(tmp_path)
    tracer.record(_sample_trace())
    tracer.record(TraceRecord(
        trace_id="t2", session_id="s2", turn_index=0,
        intent="code", agent_id="coder", user_message="x",
        response="y", mode="m", latency_ms=200,
    ))
    stats = tracer.stats()
    assert stats["total_records"] == 2
    assert stats["unique_sessions"] == 2
    assert stats["avg_latency_ms"] == 175.25
    assert "chat" in stats["by_intent"]
    assert "code" in stats["by_intent"]


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_concurrent_record(tmp_path):
    import threading

    tracer = _tmp_tracer(tmp_path)
    errors: list[Exception] = []

    def record_trace(idx: int):
        try:
            tracer.record(TraceRecord(
                trace_id=f"tr-{idx}", session_id="concurrent",
                turn_index=idx, intent="chat", agent_id="a",
                user_message=f"msg-{idx}", response=f"resp-{idx}",
                mode="m", latency_ms=float(idx),
            ))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=record_trace, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(tracer._records) == 20
