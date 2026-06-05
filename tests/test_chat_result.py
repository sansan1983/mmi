"""ChatResult 数据契约测试。"""
from mmi.agent.result import ChatResult
from mmi.agent.validate import ValidationResult, ValidationIssue
from mmi.agent.router import IntentType


def test_chat_result_required_fields():
    r = ChatResult(
        reply="hi",
        intent=IntentType.QA,
        agent_id="qa",
        validation=None,
        trace_ids=[],
    )
    assert r.reply == "hi"
    assert r.intent == IntentType.QA
    assert r.attempts == 1
    assert r.latency_ms == 0.0
    assert r.error is None


def test_chat_result_with_error():
    r = ChatResult(
        reply="",
        intent=IntentType.QA,
        agent_id="qa",
        validation=None,
        trace_ids=["t1"],
        attempts=3,
        latency_ms=1234.5,
        error="LLM timeout",
    )
    assert r.attempts == 3
    assert r.latency_ms == 1234.5
    assert r.error == "LLM timeout"
    assert r.trace_ids == ["t1"]


def test_chat_result_to_dict():
    r = ChatResult(
        reply="ok",
        intent=IntentType.QA,
        agent_id="qa",
        validation=ValidationResult(passed=True, issues=()),
        trace_ids=[],
    )
    d = r.to_dict()
    assert d["reply"] == "ok"
    assert d["intent"] == "qa"
    assert d["agent_id"] == "qa"
    assert d["validation"] == {"passed": True, "issues": []}
