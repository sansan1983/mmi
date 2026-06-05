"""Pipeline 内建 Step 实现。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mmi.agent.pipeline import PipelineCtx, PipelineStep

if TYPE_CHECKING:
    from mmi.agent.router import Router
    from mmi.agent.validate import Validator
    from mmi.core.manager import SessionManager

log = logging.getLogger(__name__)


@dataclass
class ClassifyStep(PipelineStep):
    name: str = "classify"
    on_error: str = "fail"
    router: "Router | None" = None

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.router is None:
            raise RuntimeError("ClassifyStep.router not set")
        ctx.intent = self.router.classify(ctx.user_message)
        return ctx


@dataclass
class RouteStep(PipelineStep):
    name: str = "route"
    on_error: str = "fail"
    router: "Router | None" = None

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
    validator: "Validator | None" = None

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.validator is None:
            raise RuntimeError("ValidateStep.validator not set")
        reply = ctx.reply or ""
        ctx.validation = self.validator.check(reply, ctx.intent)
        return ctx


@dataclass
class PersistStep(PipelineStep):
    name: str = "persist"
    on_error: str = "degrade"
    manager: "SessionManager | None" = None

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.manager is None:
            raise RuntimeError("PersistStep.manager not set")
        self.manager.persist_turn(
            session_id=ctx.session_id,
            user_input=ctx.user_message,
            reply=ctx.reply or "",
        )
        return ctx


def default_steps(
    *,
    router: "Router",
    registry: object,
    validator: "Validator",
    manager: "SessionManager",
) -> list[PipelineStep]:
    """返回 6 个内建 Step 的默认装配。"""
    return [
        ClassifyStep(router=router),
        RouteStep(router=router),
        InstantiateStep(registry=registry),
        RunStep(),
        ValidateStep(validator=validator),
        PersistStep(manager=manager),
    ]
