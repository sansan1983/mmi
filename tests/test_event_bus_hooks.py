"""R8 4.7 + 4.9 集成测试:Tracer/Validate/Persist 通过 EventBus 发事件。

测试设计:
  - 用临时 EventBus(不污染全局单例)— Pipeline 注入 event_bus
  - 订阅事件名,跑 chat(),断言事件被发出且 payload 字段齐全
"""
from __future__ import annotations

import pytest

from mmi.agent.event_bus import Event, EventBus
from mmi.agent.orchestrator import Orchestrator
from mmi.agent.pipeline import PipelineCtx
from mmi.agent.registry import AgentRegistry, AgentMeta
from mmi.agent.router import IntentType, Router
from mmi.agent.steps import (
    PersistStep,
    ValidateStep,
    default_steps,
)
from mmi.agent.trace import Tracer, TraceRecord
from mmi.agent.validate import Validator
from mmi.core import manager as mgr_module
from mmi.core.llm import LLMProvider, Classification
from mmi.core.session import Session, SessionMeta
from mmi.core import storage


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


class _StubLLM(LLMProvider):
    name = "stub"

    def chat(self, messages, **kw):
        return "stub-reply"

    def classify(self, prompt, *, options):
        return Classification(choice=options[0], confidence=0.99)


def _fresh_registry():
    AgentRegistry._instance = None
    return AgentRegistry.get_instance()


@pytest.fixture
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    yield tmp_path
    AgentRegistry._instance = None


# ---------------------------------------------------------------------------
# 4.7 Tracer → EventBus
# ---------------------------------------------------------------------------


def test_tracer_publishes_trace_recorded_event(isolated_home):
    """注入 bus 后,Tracer.record() 应 publish 'trace.recorded' 事件。"""
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("trace.recorded", lambda e: received.append(e))

    t = Tracer(event_bus=bus)
    t.record(TraceRecord(
        trace_id="01ABC",
        session_id="s1",
        turn_index=0,
        intent="qa",
        agent_id="qa",
        user_message="hi",
        response="hello",
        mode="standard",
        latency_ms=42.0,
    ))

    assert len(received) == 1
    e = received[0]
    assert e.name == "trace.recorded"
    assert e.payload["trace_id"] == "01ABC"
    assert e.payload["session_id"] == "s1"
    assert e.payload["agent_id"] == "qa"
    assert e.payload["latency_ms"] == 42.0


def test_tracer_without_bus_does_not_crash():
    """不传 bus 时,record() 行为不变(纯 in-memory,无事件)。"""
    t = Tracer()  # event_bus=None
    t.record(TraceRecord(
        trace_id="x", session_id="s", turn_index=0, intent="qa",
        agent_id="qa", user_message="u", response="r",
        mode="standard", latency_ms=0.0,
    ))
    assert t.get_turn_count("s") == 1


def test_tracer_event_handler_exception_isolated(isolated_home):
    """订阅者抛错不应影响 record() 主体(EventBus 内部 try/except)。"""
    bus = EventBus()
    def bad_handler(e):
        raise RuntimeError("boom")
    bus.subscribe("trace.recorded", bad_handler)

    t = Tracer(event_bus=bus)
    t.record(TraceRecord(
        trace_id="x", session_id="s", turn_index=0, intent="qa",
        agent_id="qa", user_message="u", response="r",
        mode="standard", latency_ms=0.0,
    ))
    # 仍正常入库
    assert t.get_turn_count("s") == 1


def test_orchestrator_passes_bus_to_tracer(isolated_home):
    """Orchestrator.__init__ 应把 self.bus 透传给 Tracer(默认情况)。"""
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("trace.recorded", lambda e: received.append(e))

    sid = "01" + "A" * 24
    storage.write_session(Session(meta=SessionMeta.new(sid, title="t"), body=""))

    llm = _StubLLM()
    reg = _fresh_registry()
    from mmi.agent.builtin import DocAgent
    reg.register(AgentMeta(agent_id="doc", name="Doc", builtin=True), DocAgent)

    mgr = mgr_module.SessionManager(llm=llm)
    # 关键:不传 tracer → 应自动构造 Tracer(event_bus=bus)
    orch = Orchestrator(manager=mgr, llm=llm, registry=reg, event_bus=bus)
    orch.chat_legacy(sid, "hi")

    # 至少 1 个 trace.recorded 事件(可能 0 因为 trace 列表是 PipelineCtx 内自填,
    # 实际 orchestrator.chat 里 for tr in ctx.trace: tracer.record(tr) )
    # —— 这里主要验证 Tracer 接到了 bus,不验证具体数量
    assert orch.tracer._bus is bus  # 透传成功


# ---------------------------------------------------------------------------
# 4.9 ValidateStep 事件
# ---------------------------------------------------------------------------


def test_validate_step_publishes_validation_complete_when_passed(isolated_home):
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("validation.complete", lambda e: received.append(e))

    step = ValidateStep(validator=Validator(), event_bus=bus)
    ctx = PipelineCtx(
        session_id="s1", user_message="hi",
        intent=IntentType.QA, reply="正常的输出内容",  # 默认 rule 集通过
    )
    step.run(ctx)

    assert len(received) == 1
    assert received[0].payload["session_id"] == "s1"
    assert received[0].payload["passed"] is True
    assert received[0].payload["issue_count"] == 0


def test_validate_step_publishes_per_issue(isolated_home):
    bus = EventBus()
    issues: list[Event] = []
    bus.subscribe("validation.issue", lambda e: issues.append(e))

    step = ValidateStep(validator=Validator(), event_bus=bus)
    ctx = PipelineCtx(
        session_id="s1", user_message="hi",
        intent=IntentType.QA, reply='password = "leaked"',  # 触发 no_dangerous_tokens
    )
    step.run(ctx)

    assert len(issues) == 1
    assert issues[0].payload["rule_id"] == "no_dangerous_tokens"
    assert issues[0].payload["severity"] == "error"
    assert "dangerous" in issues[0].payload["message"]
    assert issues[0].payload["span"] is not None


def test_validate_step_without_bus_silent(isolated_home):
    """不传 bus 时不应崩溃(R8 4.9 向后兼容)。"""
    step = ValidateStep(validator=Validator(), event_bus=None)
    ctx = PipelineCtx(
        session_id="s1", user_message="hi",
        intent=IntentType.QA, reply="hi",
    )
    # 无异常
    step.run(ctx)
    assert ctx.validation is not None


# ---------------------------------------------------------------------------
# 4.9 PersistStep 事件
# ---------------------------------------------------------------------------


def test_persist_step_publishes_complete(isolated_home):
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("persist.complete", lambda e: received.append(e))

    sid = "01" + "A" * 24
    storage.write_session(Session(meta=SessionMeta.new(sid, title="t"), body=""))

    mgr = mgr_module.SessionManager(llm=_StubLLM())
    step = PersistStep(manager=mgr, event_bus=bus)
    ctx = PipelineCtx(
        session_id=sid, user_message="hi",
        agent_id="qa", reply="hello world",
    )
    step.run(ctx)

    assert len(received) == 1
    assert received[0].payload["session_id"] == sid
    assert received[0].payload["agent_id"] == "qa"
    assert received[0].payload["reply_length"] == 11


def test_persist_step_without_bus_silent(isolated_home):
    """不传 bus 时不应崩溃(向后兼容)。"""
    sid = "01" + "A" * 24
    storage.write_session(Session(meta=SessionMeta.new(sid, title="t"), body=""))

    mgr = mgr_module.SessionManager(llm=_StubLLM())
    step = PersistStep(manager=mgr, event_bus=None)
    ctx = PipelineCtx(
        session_id=sid, user_message="hi",
        agent_id="qa", reply="hello",
    )
    step.run(ctx)  # 无异常


def test_default_steps_includes_event_bus(isolated_home):
    """default_steps 接受 event_bus 关键字参数(向后兼容:None 时不发事件)。"""
    bus = EventBus()
    steps_with_bus = default_steps(
        router=Router(), registry=_fresh_registry(),
        validator=Validator(), manager=mgr_module.SessionManager(llm=_StubLLM()),
        event_bus=bus,
    )
    steps_no_bus = default_steps(
        router=Router(), registry=_fresh_registry(),
        validator=Validator(), manager=mgr_module.SessionManager(llm=_StubLLM()),
    )
    assert len(steps_with_bus) == 6
    assert len(steps_no_bus) == 6
    # ValidateStep / PersistStep 应带上 bus
    v_with = next(s for s in steps_with_bus if isinstance(s, ValidateStep))
    p_with = next(s for s in steps_with_bus if isinstance(s, PersistStep))
    assert v_with.event_bus is bus
    assert p_with.event_bus is bus
    # 默认情况 event_bus=None(向后兼容)
    v_no = next(s for s in steps_no_bus if isinstance(s, ValidateStep))
    p_no = next(s for s in steps_no_bus if isinstance(s, PersistStep))
    assert v_no.event_bus is None
    assert p_no.event_bus is None
