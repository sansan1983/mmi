"""Manager.batch_* 行为测试。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

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
