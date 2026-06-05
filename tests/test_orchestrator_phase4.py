"""Orchestrator 走 Pipeline(R7 4.2) + chat_legacy 兼容。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mmi.agent.orchestrator import Orchestrator
from mmi.agent.pipeline import Pipeline
from mmi.agent.registry import AgentMeta, AgentRegistry
from mmi.agent.result import ChatResult
from mmi.agent.router import IntentType


class _FakeAgent:
    """代替 BaseAgent 的最小可 run 对象。"""

    def __init__(self, reply: str = "test reply") -> None:
        self.agent_id = "qa"
        self.name = "Q"
        self.system_prompt = ""
        self._reply = reply

    def run(self, user_message, mode=None) -> str:
        return self._reply


@pytest.fixture
def fresh_registry(monkeypatch):
    """每个用例一个全新的空 registry,避免污染全局单例。"""
    monkeypatch.setattr(AgentRegistry, "_instance", None)
    reg = AgentRegistry.get_instance()
    yield reg
    monkeypatch.setattr(AgentRegistry, "_instance", None)


@pytest.fixture
def manager(monkeypatch):
    """Mock SessionManager,持久化步骤是 degrade 策略,失败不会 crash pipeline。"""
    mgr = MagicMock()
    mgr.persist_turn = MagicMock(return_value=None)
    return mgr


@pytest.fixture
def orch(fresh_registry, manager):
    """构造一个 mock-heavy Orchestrator,内部走 Pipeline + 6 内建 step。

    注册一个 'qa' agent,Router.classify("hi") 走 QA → RouteStep 选 "qa" →
    InstantiateStep 拿这个实例 → RunStep 调 .run() 返 "test reply"。
    """
    class _StubCls:
        def __init__(self, llm=None, skill_library=None, tool_registry=None):
            self.llm = llm
            self.agent_id = "qa"
            self.name = "Q"
            self.system_prompt = ""

        def run(self, user_message, mode=None) -> str:
            return "test reply"

    fresh_registry.register(
        AgentMeta(agent_id="qa", name="Q", builtin=True),
        _StubCls,
    )
    return Orchestrator(manager=manager, llm=MagicMock(), registry=fresh_registry)


# ---------------------------------------------------------------------------
# Pipeline 装配
# ---------------------------------------------------------------------------


def test_chat_returns_chat_result(orch):
    """chat() 现在返 ChatResult 而非 str。"""
    result = orch.chat("s1", "hello")
    assert isinstance(result, ChatResult)
    # mock agent.run 返 "test reply"
    assert result.reply == "test reply"


def test_chat_legacy_returns_str(orch):
    """chat_legacy() 保持 str 返,跟 phase 3 兼容。"""
    s = orch.chat_legacy("s1", "hello")
    assert isinstance(s, str)
    assert s == "test reply"


def test_chat_default_steps_assembled(orch):
    """Orchestrator 内部 Pipeline 用 default_steps() 6 步装配。"""
    assert isinstance(orch.pipeline, Pipeline)
    assert len(orch.pipeline.steps) == 6
    names = [s.name for s in orch.pipeline.steps]
    assert names == ["classify", "route", "instantiate", "run", "validate", "persist"]


def test_chat_classifies_qa_intent(orch):
    """短文本默认走 QA 路径。"""
    result = orch.chat("s1", "hi")
    assert result.intent == IntentType.QA
    assert result.agent_id == "qa"


def test_chat_persists_via_manager(orch, manager):
    """Pipeline 最后一步 PersistStep 调 manager.persist_turn。"""
    orch.chat("s1", "hi")
    assert manager.persist_turn.called
    # kwargs 至少包含 session_id / user_input / reply
    kwargs = manager.persist_turn.call_args.kwargs
    assert kwargs["session_id"] == "s1"
    assert kwargs["user_input"] == "hi"
    assert kwargs["reply"] == "test reply"


def test_chat_no_validation_failure_blocks(orch):
    """默认 ValidateStep 应让 'test reply' 通过(2 字符 > min_length=2)。"""
    result = orch.chat("s1", "hi")
    assert result.validation is not None
    assert result.validation.passed is True


def test_chat_runs_instantiate_step_with_real_instance(orch, fresh_registry):
    """RunStep 实际跑的是 registry.get() 返回的实例(不是类)。"""
    agent_inst = fresh_registry.get("qa")
    assert agent_inst is not None
    # 调它的 run,验证确实是实例不是类(类调用 run 不会这么顺利)
    r = agent_inst.run("hello")
    assert r == "test reply"


def test_orchestrator_with_custom_pipeline_uses_it(fresh_registry, manager):
    """Orchestrator 接受外部传入的 pipeline(完全控制 6 步流程)。"""
    from mmi.agent.steps import (
        ClassifyStep,
        RouteStep,
        InstantiateStep,
        RunStep,
        ValidateStep,
        PersistStep,
    )
    from mmi.agent.router import Router
    from mmi.agent.validate import Validator
    from mmi.agent.pipeline import Pipeline
    from mmi.agent.event_bus import EventBus

    class _A:
        def __init__(self, llm=None, skill_library=None, tool_registry=None):
            self.llm = llm
            self.agent_id = "qa"
            self.name = "Q"
            self.system_prompt = ""

        def run(self, user_message, mode=None) -> str:
            return "custom-pipeline-reply"

    fresh_registry.register(AgentMeta(agent_id="qa", name="Q"), _A)
    bus = EventBus()
    custom = Pipeline(
        [
            ClassifyStep(router=Router()),
            RouteStep(router=Router()),
            InstantiateStep(registry=fresh_registry),
            RunStep(),
            ValidateStep(validator=Validator()),
            PersistStep(manager=manager),
        ],
        event_bus=bus,
    )
    orch = Orchestrator(
        manager=manager, llm=MagicMock(),
        registry=fresh_registry, pipeline=custom,
    )
    result = orch.chat("s1", "hi")
    assert result.reply == "custom-pipeline-reply"


def test_chat_legacy_on_error_returns_string(orch, manager):
    """chat_legacy() 在 pipeline 出错时也返 str(不抛异常)。"""
    manager.persist_turn.side_effect = Exception("disk full")
    # PersistStep 是 degrade 策略 → error 记 ctx.errors 但 Pipeline 不 crash
    s = orch.chat_legacy("s1", "hi")
    # reply 仍然有("test reply"),persist 出错不阻塞
    assert isinstance(s, str)
    assert s == "test reply"
