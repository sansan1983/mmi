"""Main Orchestrator - entry point for single-turn conversation flow.

3.3 改进:Orchestrator.chat() 核心逻辑实现。
  - 同步优先(Pipeline/EventBus 是 4.x 改造)
  - 5 步流程:classify → select agent → build context → run agent → validate
  - LLM 错误兜底
  - 生命周期钩子:on_start / on_stop / on_error
  - 调用 Manager.persist() 持久化结果

R7 4.2 改进:把 5 步流程抽到 Pipeline + 6 个内建 Step;
Orchestrator.chat() 改成构造 PipelineCtx 然后跑 pipeline.run()。
外部行为尽量保持不变,但 chat() 现在返 ChatResult(原 str 返值用 chat_legacy()
兼容,供 phase 3 测试和老调用点用)。

Agent 池来源:AgentRegistry(全局单例)。
LLM 来源:Manager 注入 → self.llm → AgentRegistry.set_default_llm()。
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from mmi.agent.event_bus import bus as default_bus
from mmi.agent.modes import ThinkingMode
from mmi.agent.pipeline import Pipeline, PipelineCtx
from mmi.agent.registry import AgentRegistry
from mmi.agent.result import ChatResult
from mmi.agent.router import Router
from mmi.agent.steps import default_steps
from mmi.agent.trace import Tracer
from mmi.agent.validate import Validator

if TYPE_CHECKING:
    from mmi.agent.event_bus import EventBus
    from mmi.core.llm import LLMProvider
    from mmi.core.manager import SessionManager

log = logging.getLogger(__name__)


class Orchestrator:
    """Central coordinator for a single user turn.

    3.3 实现:5 步流程(类内硬编码)。
    R7 4.2 改造:把流程拆到 Pipeline + 6 个内建 Step;Orchestrator 只负责
    装配依赖、构造 PipelineCtx、调 pipeline.run()。
    """

    __slots__ = (
        "manager", "router", "registry", "validator", "tracer",
        "skill_library", "llm", "pipeline", "bus",
    )

    def __init__(
        self,
        manager: SessionManager,
        llm: LLMProvider | None = None,
        *,
        router: Router | None = None,
        registry: AgentRegistry | None = None,
        validator: Validator | None = None,
        tracer: Tracer | None = None,
        skill_library: object = None,
        pipeline: Pipeline | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.manager = manager
        self.llm = llm  # 不传则用 manager 自带
        self.router = router or Router()
        self.registry = registry or AgentRegistry.get_instance()
        self.validator = validator or Validator()
        self.bus = event_bus or default_bus
        # R8 4.7:Tracer 注入同一个 bus,record() 时 publish 'trace.recorded' 事件
        self.tracer = tracer or Tracer(event_bus=self.bus)
        self.skill_library = skill_library

        # R7 4.2:把 llm / skill_library 注入 registry,让 InstantiateStep 能
        # 拿到依赖去构造 BaseAgent 实例(避免重复从 orchestrator 取)。
        if self.llm is not None:
            self.registry.set_default_llm(self.llm)
        if self.skill_library is not None:
            self.registry.set_default_skill_library(self.skill_library)

        if pipeline is None:
            pipeline = Pipeline(
                default_steps(
                    router=self.router,
                    registry=self.registry,
                    validator=self.validator,
                    manager=self.manager,
                    event_bus=self.bus,  # R8 4.9:把 bus 透传到 Validate/Persist
                ),
                event_bus=self.bus,
            )
        self.pipeline = pipeline

    # ------------------------------------------------------------------
    # R7 4.2:核心 chat() 走 Pipeline
    # ------------------------------------------------------------------

    def chat(
        self,
        session_id: str,
        user_message: str,
        mode: ThinkingMode | None = None,
    ) -> ChatResult:
        """Process a single user turn end-to-end via Pipeline。

        流程(由 Pipeline 6 步装配执行):
          1) ClassifyStep     - router.classify → intent
          2) RouteStep        - router.route   → agent_id
          3) InstantiateStep  - registry.get   → BaseAgent 实例
          4) RunStep          - agent.run      → reply
          5) ValidateStep     - validator.check → ValidationResult
          6) PersistStep      - manager.persist_turn

        Returns:
            ChatResult(包含 reply / intent / agent_id / validation / trace_ids)
        """
        ctx = PipelineCtx(
            session_id=session_id,
            user_message=user_message,
            mode=mode,
            manager=self.manager,
        )
        result = self.pipeline.run(ctx)
        # 3.x 兼容:每次成功的 chat 也记 trace(用 ctx 的 trace 列表)
        for tr in ctx.trace:
            with contextlib.suppress(Exception):
                self.tracer.record(tr)
        return result

    def chat_legacy(
        self,
        session_id: str,
        user_message: str,
        mode: ThinkingMode | None = None,
    ) -> str:
        """R7 4.2:返回纯 reply 字符串(phase 3 + 老调用点兼容)。

        等价于 ``self.chat(...).reply``;如果 chat() 出错,返 ``result.error``
        或占位 "[Orchestrator error] ..."。
        """
        result = self.chat(session_id, user_message, mode=mode)
        if result.reply:
            return result.reply
        if result.error:
            return f"[Orchestrator error] {result.error}"
        return ""

    # ------------------------------------------------------------------
    # 3.x 兼容:暴露 _instantiate_agent 给外部 mock 场景(已无内调用)
    # ------------------------------------------------------------------

    def _instantiate_agent(self, agent_id: str) -> Any:
        """从 registry 拿 agent 类,实例化(注入 llm + 共享组件)。

        R7 4.2:内部流程已搬到 InstantiateStep;保留此方法仅为老测试/老调用点。
        """
        return self.registry.get(agent_id)
