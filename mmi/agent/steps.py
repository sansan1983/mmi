"""Pipeline 内建 Step 实现。

R8 4.9 改进:ValidateStep / PersistStep 支持 event_bus 注入(可选),
完成后 publish 'validation.complete' / 'persist.complete' 事件,
供审计 / 指标 / 外部监控订阅。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mmi.agent.pipeline import PipelineCtx, PipelineStep

if TYPE_CHECKING:
    from mmi.agent.event_bus import EventBus
    from mmi.agent.router import Router
    from mmi.agent.validate import Validator
    from mmi.core.manager import SessionManager

log = logging.getLogger(__name__)


@dataclass
class ClassifyStep(PipelineStep):
    name: str = "classify"
    on_error: str = "fail"
    router: Router | None = None

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.router is None:
            raise RuntimeError("ClassifyStep.router not set")
        ctx.intent = self.router.classify(ctx.user_message)
        return ctx


@dataclass
class RouteStep(PipelineStep):
    name: str = "route"
    on_error: str = "fail"
    router: Router | None = None

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.router is None or ctx.intent is None:
            raise RuntimeError("RouteStep.router/intent missing")
        ids = self.router.route(ctx.intent)
        ctx.agent_id = ids[0] if ids else "qa"
        return ctx


@dataclass
class InstantiateStep(PipelineStep):
    name: str = "instantiate"
    on_error: str = "fail"
    registry: object = None  # AgentRegistry

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.registry is None or ctx.agent_id is None:
            raise RuntimeError("InstantiateStep.registry/agent_id missing")
        agent = self.registry.get(ctx.agent_id)
        if agent is None:
            raise RuntimeError(f"agent {ctx.agent_id!r} not registered")
        ctx.agent = agent
        return ctx


@dataclass
class RunStep(PipelineStep):
    name: str = "run"
    on_error: str = "degrade"

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if ctx.agent is None:
            raise RuntimeError("RunStep: ctx.agent is None")
        try:
            ctx.reply = ctx.agent.run(ctx.user_message, mode=ctx.mode)
        except Exception as e:
            # 脱敏占位
            ctx.reply = f"[LLM 暂时不可用: {type(e).__name__}]"
            log.exception("RunStep agent.run failed")
            raise  # 由 Pipeline 容器记 ctx.errors
        return ctx


@dataclass
class ValidateStep(PipelineStep):
    name: str = "validate"
    on_error: str = "degrade"
    validator: Validator | None = None
    event_bus: EventBus | None = None  # R8 4.9 引入:可注入
    # R9 9.2:节流配置
    issue_batch_threshold: int = 5
    """issues 数量 > 此值时改 publish 'validation.issue_batch' 单条事件,
    而不是逐 issue publish 'validation.issue'。"""
    force_individual: bool = False
    """强制逐条 publish(给调试 / 排错场景,绕过阈值)。"""

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.validator is None:
            raise RuntimeError("ValidateStep.validator not set")
        reply = ctx.reply or ""
        ctx.validation = self.validator.check(reply, ctx.intent)
        # R8 4.9 + R9 9.2:完成后 publish 'validation.complete' +
        # 按阈值决定逐 issue publish 或合并 publish batch
        if self.event_bus is not None:
            from mmi.agent.event_bus import Event
            self.event_bus.publish(Event(
                name="validation.complete",
                timestamp=time.time(),
                payload={
                    "session_id": ctx.session_id,
                    "passed": ctx.validation.passed,
                    "issue_count": len(ctx.validation.issues),
                },
            ))
            n = len(ctx.validation.issues)
            if self.force_individual or n <= self.issue_batch_threshold:
                # 阈值下 / 强制:逐条 publish
                for issue in ctx.validation.issues:
                    self.event_bus.publish(Event(
                        name="validation.issue",
                        timestamp=time.time(),
                        payload={
                            "session_id": ctx.session_id,
                            "rule_id": issue.rule_id,
                            "severity": issue.severity,
                            "message": issue.message,
                            "span": list(issue.span) if issue.span is not None else None,
                        },
                    ))
            else:
                # 超阈值:合并 publish batch
                self.event_bus.publish(Event(
                    name="validation.issue_batch",
                    timestamp=time.time(),
                    payload={
                        "session_id": ctx.session_id,
                        "count": n,
                        "issues": [
                            {
                                "rule_id": i.rule_id,
                                "severity": i.severity,
                                "message": i.message,
                                "span": list(i.span) if i.span is not None else None,
                            }
                            for i in ctx.validation.issues
                        ],
                    },
                ))
        return ctx


@dataclass
class PersistStep(PipelineStep):
    name: str = "persist"
    on_error: str = "degrade"
    manager: SessionManager | None = None
    event_bus: EventBus | None = None  # R8 4.9 引入:可注入

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.manager is None:
            raise RuntimeError("PersistStep.manager not set")
        self.manager.persist_turn(
            session_id=ctx.session_id,
            user_input=ctx.user_message,
            reply=ctx.reply or "",
        )
        # R8 4.9:完成后 publish 'persist.complete' 事件(供审计 / 外部监控)
        if self.event_bus is not None:
            from mmi.agent.event_bus import Event
            self.event_bus.publish(Event(
                name="persist.complete",
                timestamp=time.time(),
                payload={
                    "session_id": ctx.session_id,
                    "agent_id": ctx.agent_id or "",
                    "reply_length": len(ctx.reply or ""),
                },
            ))
        return ctx


def default_steps(
    *,
    router: Router,
    registry: object,
    validator: Validator,
    manager: SessionManager,
    event_bus: EventBus | None = None,  # R8 4.9 引入
) -> list[PipelineStep]:
    """返回 6 个内建 Step 的默认装配。

    R8 4.9 改进:event_bus 注入到 ValidateStep / PersistStep(向后兼容,
    None 时不发事件)。
    """
    return [
        ClassifyStep(router=router),
        RouteStep(router=router),
        InstantiateStep(registry=registry),
        RunStep(),
        ValidateStep(validator=validator, event_bus=event_bus),
        PersistStep(manager=manager, event_bus=event_bus),
    ]
