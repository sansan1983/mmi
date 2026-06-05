"""Pipeline 容器 + 6 个内建 Step 行为测试。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
from unittest.mock import MagicMock

from mmi.agent.base import BaseAgent
from mmi.agent.pipeline import Pipeline, PipelineCtx
from mmi.agent.router import IntentType, Router
from mmi.agent.steps import (
    ClassifyStep, RouteStep, RunStep,
)


# ── 容器测试 ─────────────────────────────────────────────


def test_empty_pipeline_returns_chat_result_with_error():
    ctx = PipelineCtx(session_id="s1", user_message="hi")
    p = Pipeline([])
    result = p.run(ctx)
    # 空 pipeline:无 reply,error 标 "no steps"
    assert result.reply == ""
    assert result.error is not None
    assert "no steps" in result.error.lower()


@dataclass
class _NoopStep:
    name: ClassVar[str] = "noop"
    on_error: ClassVar[str] = "degrade"
    call_count: int = 0

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        self.call_count += 1
        return ctx


def test_pipeline_runs_steps_in_order():
    s1, s2, s3 = _NoopStep(), _NoopStep(), _NoopStep()
    s1.name = "a"
    s2.name = "b"
    s3.name = "c"
    p = Pipeline([s1, s2, s3])
    p.run(PipelineCtx(session_id="s1", user_message="x"))
    assert s1.call_count == s2.call_count == s3.call_count == 1


@dataclass
class _FailStep:
    name: ClassVar[str] = "fail"
    on_error: ClassVar[str] = "fail"

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        raise RuntimeError("boom")


def test_fail_policy_stops_pipeline():
    s_ok, s_bad = _NoopStep(), _FailStep()
    s_ok.name = "ok"
    p = Pipeline([s_ok, s_bad])
    result = p.run(PipelineCtx(session_id="s1", user_message="x"))
    assert result.error is not None
    assert "fail" in result.error.lower()


@dataclass
class _DegradeStep:
    name: ClassVar[str] = "degrade"
    on_error: ClassVar[str] = "degrade"
    call_count: int = 0

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("first call fail")
        return ctx


def test_degrade_policy_continues():
    s = _DegradeStep()
    s_after = _NoopStep()
    s_after.name = "after"
    p = Pipeline([s, s_after])
    result = p.run(PipelineCtx(session_id="s1", user_message="x"))
    assert s.call_count == 2  # 失败重试 1 次
    assert s_after.call_count == 1  # 后续 step 仍跑
    assert any("first call fail" in str(e) for e in result.errors)


# ── 内建 Step 测试 ─────────────────────────────────────────


def test_classify_step_sets_intent():
    router = Router()
    step = ClassifyStep(router=router)
    # 用 "代码审查" 触发 Router 的 CODE_REVIEW 关键词
    # (中文 phrase "审查一下这段代码" Router 的正则不匹配——3.2 规则版的限制)
    ctx = step.run(PipelineCtx(session_id="s1", user_message="请帮我代码审查"))
    assert ctx.intent == IntentType.CODE_REVIEW


def test_route_step_picks_first_agent():
    step = RouteStep(router=Router())
    ctx = PipelineCtx(session_id="s1", user_message="x", intent=IntentType.QA)
    ctx = step.run(ctx)
    assert ctx.agent_id == "qa"


def test_run_step_degrade_on_agent_error():
    class _BoomAgent(BaseAgent):
        def run(self, user_message, *, mode=None):
            raise RuntimeError("agent down")

    agent = _BoomAgent(
        agent_id="boom",
        name="boom",
        llm=MagicMock(),
        system_prompt="x",
    )
    # 走 Pipeline 容器,degrade 策略会捕获 + 记 ctx.errors
    step = RunStep()
    p = Pipeline([step])
    ctx = PipelineCtx(
        session_id="s1", user_message="hi", intent=IntentType.QA, agent=agent
    )
    result = p.run(ctx)
    # reply 是脱敏占位(由 RunStep 的 except 设置)
    assert result.reply is not None
    assert result.reply != ""
    assert len(result.errors) == 1
