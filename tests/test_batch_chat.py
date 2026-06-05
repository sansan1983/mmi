"""Manager.batch_* 行为测试。"""
from __future__ import annotations

from unittest.mock import MagicMock


from mmi.agent.result import ChatResult
from mmi.agent.router import IntentType


def _make_manager_with_orch():
    """构造一个 mock SessionManager,带 orchestrator。"""
    from mmi.core.manager import SessionManager
    m = SessionManager.__new__(SessionManager)  # 跳过 __init__
    m.orchestrator = MagicMock()
    return m


def test_batch_chat_returns_results():
    m = _make_manager_with_orch()
    m.orchestrator.chat.side_effect = [
        ChatResult(reply="a", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[]),
        ChatResult(reply="b", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[]),
    ]
    out = m.batch_chat([("s1", "hi"), ("s2", "yo")])
    assert [r.reply for r in out] == ["a", "b"]
    assert m.orchestrator.chat.call_count == 2


def test_batch_chat_isolates_exception():
    """单条 chat() 抛错不阻塞后续;失败条返 ChatResult 带 error。"""
    m = _make_manager_with_orch()
    m.orchestrator.chat.side_effect = [
        ChatResult(reply="a", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[]),
        RuntimeError("boom"),
        ChatResult(reply="c", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[]),
    ]
    out = m.batch_chat([("s1", "hi"), ("s2", "yo"), ("s3", "hey")])
    assert len(out) == 3
    assert out[0].reply == "a"
    assert out[1].reply == ""
    assert out[1].error is not None
    assert "boom" in out[1].error
    assert out[2].reply == "c"
    assert out[2].error is None


def test_batch_touch_isolates_failure():
    m = _make_manager_with_orch()
    m.touch = MagicMock(side_effect=[None, RuntimeError("x"), None])
    m.batch_touch(["s1", "s2", "s3"])
    assert m.touch.call_count == 3


def test_batch_get_meta_skips_missing():
    m = _make_manager_with_orch()
    m.get_session_meta = MagicMock(side_effect=[
        {"id": "s1", "title": "t1"},
        KeyError("s2 missing"),
        {"id": "s3", "title": "t3"},
    ])
    out = m.batch_get_meta(["s1", "s2", "s3"])
    assert "s1" in out
    assert "s2" not in out
    assert "s3" in out


# ---------------------------------------------------------------------------
# R9 9.4:batch_chat 并发(后台线程池)
# ---------------------------------------------------------------------------


def test_batch_chat_serial_when_single_item():
    """1 item 走串行快路径,不启线程池。"""
    m = _make_manager_with_orch()
    m.orchestrator.chat.return_value = ChatResult(
        reply="a", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[],
    )
    out = m.batch_chat([("s1", "hi")])
    assert len(out) == 1
    assert out[0].reply == "a"


def test_batch_chat_concurrent_when_multiple():
    """3 items 用 3 worker,并发启动(用 barrier 验证同时跑)。"""
    import threading
    from mmi.core.manager import SessionManager

    m = SessionManager.__new__(SessionManager)  # 跳过 __init__
    m.orchestrator = MagicMock()

    barrier = threading.Barrier(3, timeout=2.0)

    def slow_chat(sid, msg):
        barrier.wait()  # 3 个都到这里才放行,证明并发
        return ChatResult(
            reply=f"r-{sid}", intent=IntentType.QA, agent_id="qa",
            validation=None, trace_ids=[],
        )

    m.orchestrator.chat.side_effect = slow_chat
    m._max_batch_workers = 3
    out = m.batch_chat([("s1", "hi"), ("s2", "yo"), ("s3", "hey")])
    assert len(out) == 3
    assert {r.reply for r in out} == {"r-s1", "r-s2", "r-s3"}


def test_batch_chat_respects_max_workers():
    """max_workers=1 时退化为串行(等同旧实现)。"""
    from mmi.core.manager import SessionManager

    m = SessionManager.__new__(SessionManager)
    m.orchestrator = MagicMock()
    m.orchestrator.chat.side_effect = [
        ChatResult(reply="a", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[]),
        ChatResult(reply="b", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[]),
    ]
    m._max_batch_workers = 1
    out = m.batch_chat([("s1", "hi"), ("s2", "yo")])
    assert [r.reply for r in out] == ["a", "b"]


def test_batch_chat_preserves_input_order():
    """返回 list 顺序跟输入 items 顺序一致(不因线程完成先后乱序)。"""
    import time
    from mmi.core.manager import SessionManager

    m = SessionManager.__new__(SessionManager)
    m.orchestrator = MagicMock()

    delays = {"s1": 0.05, "s2": 0.01, "s3": 0.03}  # 故意让 s2 先完

    def slow_chat(sid, msg):
        time.sleep(delays[sid])
        return ChatResult(
            reply=f"r-{sid}", intent=IntentType.QA, agent_id="qa",
            validation=None, trace_ids=[],
        )

    m.orchestrator.chat.side_effect = slow_chat
    m._max_batch_workers = 3
    out = m.batch_chat([("s1", "hi"), ("s2", "yo"), ("s3", "hey")])
    assert [r.reply for r in out] == ["r-s1", "r-s2", "r-s3"]


def test_batch_touch_concurrent():
    """batch_touch 走线程池。"""
    import threading
    from mmi.core.manager import SessionManager

    m = SessionManager.__new__(SessionManager)
    barrier = threading.Barrier(3, timeout=2.0)
    call_order = []

    def slow_touch(sid):
        barrier.wait()
        call_order.append(sid)

    m.touch = MagicMock(side_effect=slow_touch)
    m._max_batch_workers = 3
    m.batch_touch(["s1", "s2", "s3"])
    assert set(call_order) == {"s1", "s2", "s3"}


def test_batch_get_meta_concurrent():
    """batch_get_meta 走线程池。"""
    import threading
    from mmi.core.manager import SessionManager

    m = SessionManager.__new__(SessionManager)
    barrier = threading.Barrier(3, timeout=2.0)

    def slow_get(sid):
        barrier.wait()
        return {"sid": sid}

    m.get_session_meta = MagicMock(side_effect=slow_get)
    m._max_batch_workers = 3
    out = m.batch_get_meta(["s1", "s2", "s3"])
    assert out == {"s1": {"sid": "s1"}, "s2": {"sid": "s2"}, "s3": {"sid": "s3"}}


def test_max_batch_workers_constructor_kwarg():
    """SessionManager(max_batch_workers=8) 构造时透传到 _max_batch_workers 字段。"""
    from mmi.core.manager import SessionManager
    from mmi.core.llm import LLMProvider

    class _StubLLM(LLMProvider):
        def chat(self, messages, *, max_tokens=4096, temperature=0.7):  # noqa: ARG002
            return ""

        def stream_chat(self, messages, *, max_tokens=4096, temperature=0.7):  # noqa: ARG002
            yield ""

        def classify(self, prompt, *, options):  # noqa: ARG002
            from mmi.core.llm import Classification
            return Classification(choice=options[0] if options else "", confidence=0.0)

    m = SessionManager(llm=_StubLLM(), max_batch_workers=8)
    assert m._max_batch_workers == 8

    # 默认值 = 4
    m2 = SessionManager(llm=_StubLLM())
    assert m2._max_batch_workers == 4
