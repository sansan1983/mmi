"""可插拔 Pipeline:把 Orchestrator 的 5 步拆成 Step + 容器。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from mmi.agent.event_bus import Event, bus as default_bus

if TYPE_CHECKING:
    from mmi.agent.event_bus import EventBus
    from mmi.agent.modes import ThinkingMode
    from mmi.agent.result import ChatResult
    from mmi.agent.router import IntentType
    from mmi.agent.trace import TraceRecord
    from mmi.agent.validate import ValidationResult
    from mmi.core.manager import SessionManager

log = logging.getLogger(__name__)


@dataclass
class StepError:
    step: str
    cause: Exception
    policy: str

    def __str__(self) -> str:
        return f"[{self.step}] {self.cause!r}"


@dataclass
class PipelineCtx:
    session_id: str
    user_message: str
    mode: "ThinkingMode | None" = None
    intent: "IntentType | None" = None
    agent_id: str | None = None
    agent: object = None  # BaseAgent | None
    reply: str | None = None
    validation: "ValidationResult | None" = None
    trace: list["TraceRecord"] = field(default_factory=list)
    errors: list[StepError] = field(default_factory=list)
    chat_result: "ChatResult | None" = None
    manager: "SessionManager | None" = None


@runtime_checkable
class PipelineStep(Protocol):
    name: str
    on_error: str  # "fail" | "degrade" | "skip"

    def run(self, ctx: PipelineCtx) -> PipelineCtx: ...


class Pipeline:
    def __init__(
        self,
        steps: list[PipelineStep],
        *,
        event_bus: "EventBus | None" = None,
    ) -> None:
        self.steps = steps
        self.bus = event_bus or default_bus

    def run(self, ctx: PipelineCtx) -> "ChatResult":
        from mmi.agent.result import ChatResult

        started = time.perf_counter()
        self.bus.publish(Event(
            name="pipeline.start",
            timestamp=time.time(),
            payload={"session_id": ctx.session_id, "user_message": ctx.user_message},
        ))

        if not self.steps:
            # 空 pipeline:无任何 step 执行,直接返回带错误的 ChatResult。
            result = ChatResult(
                reply="",
                intent=ctx.intent,
                agent_id=ctx.agent_id or "",
                validation=ctx.validation,
                trace_ids=[],
                latency_ms=(time.perf_counter() - started) * 1000,
                error="pipeline has no steps",
                errors=list(ctx.errors),
            )
            ctx.chat_result = result
            self.bus.publish(Event(
                name="chat.end",
                timestamp=time.time(),
                payload={
                    "session_id": ctx.session_id,
                    "agent_id": ctx.agent_id,
                    "latency_ms": result.latency_ms,
                    "attempts": result.attempts,
                },
            ))
            return result

        for step in self.steps:
            # 上一步是 fail 策略且出错,后续 step 全部跳过
            if ctx.errors and ctx.errors[-1].policy == "fail":
                continue
            ctx = self._run_step(step, ctx)

        result = ChatResult(
            reply=ctx.reply or "",
            intent=ctx.intent,
            agent_id=ctx.agent_id or "",
            validation=ctx.validation,
            trace_ids=[t.id for t in ctx.trace],
            latency_ms=(time.perf_counter() - started) * 1000,
            error="; ".join(str(e) for e in ctx.errors) if ctx.errors else None,
            errors=list(ctx.errors),
        )
        ctx.chat_result = result

        self.bus.publish(Event(
            name="chat.end",
            timestamp=time.time(),
            payload={
                "session_id": ctx.session_id,
                "agent_id": ctx.agent_id,
                "latency_ms": result.latency_ms,
                "attempts": result.attempts,
            },
        ))
        return result

    def _run_step(self, step: PipelineStep, ctx: PipelineCtx) -> PipelineCtx:
        self.bus.publish(Event(
            name="step.start",
            timestamp=time.time(),
            payload={"step": step.name},
        ))
        t0 = time.perf_counter()
        try:
            ctx = step.run(ctx)
            self.bus.publish(Event(
                name="step.end",
                timestamp=time.time(),
                payload={"step": step.name, "duration_ms": (time.perf_counter() - t0) * 1000},
            ))
            return ctx
        except Exception as e:
            log.exception("Step %s failed (attempt 1)", step.name)
            self.bus.publish(Event(
                name="step.error",
                timestamp=time.time(),
                payload={"step": step.name, "error": str(e), "policy": step.on_error, "attempt": 1},
            ))
            # fail 策略:记 error 后 return;后续 step 由外层循环跳过
            if step.on_error == "fail":
                err = StepError(step=step.name, cause=e, policy=step.on_error)
                ctx.errors.append(err)
                return ctx
            # degrade 策略:记第一次 error,再重试一次
            err = StepError(step=step.name, cause=e, policy=step.on_error)
            ctx.errors.append(err)
            try:
                ctx = step.run(ctx)
                self.bus.publish(Event(
                    name="step.recovered",
                    timestamp=time.time(),
                    payload={"step": step.name, "attempts": 2},
                ))
                return ctx
            except Exception as e2:
                log.exception("Step %s failed (attempt 2)", step.name)
                # 重试也失败,只更新最后一次 error(不重复 append,
                # 避免 ctx.errors 在 degrade 策略下每次都翻倍)
                self.bus.publish(Event(
                    name="step.error",
                    timestamp=time.time(),
                    payload={"step": step.name, "error": str(e2), "policy": step.on_error, "attempt": 2},
                ))
                ctx.errors[-1] = StepError(step=step.name, cause=e2, policy=step.on_error)
                # 仍然继续,后续 step 由外层循环决定(degrade 不带 fail 策略 → 不跳过)
                return ctx
