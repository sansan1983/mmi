"""Main Orchestrator - entry point for single-turn conversation flow.

3.3 改进:Orchestrator.chat() 核心逻辑实现。
  - 同步优先(Pipeline/EventBus 是 4.x 改造)
  - 5 步流程:classify → select agent → build context → run agent → validate
  - LLM 错误兜底
  - 生命周期钩子:on_start / on_stop / on_error
  - 调用 Manager.persist() 持久化结果

Agent 池来源:AgentRegistry(全局单例)。
LLM 来源:Manager 注入 → self.llm。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from mmi.agent.modes import ThinkingMode
from mmi.agent.registry import AgentRegistry
from mmi.agent.router import Router
from mmi.agent.skill import SkillLibrary
from mmi.agent.trace import TraceRecord, Tracer
from mmi.agent.validate import Validator

if TYPE_CHECKING:
    from mmi.core.llm import LLMProvider
    from mmi.core.manager import SessionManager

log = logging.getLogger(__name__)


class Orchestrator:
    """Central coordinator for a single user turn.

    3.3 改进:从空壳变完整 — 5 步流程。
    """

    __slots__ = (
        "manager", "router", "registry", "validator", "tracer",
        "skill_library", "llm",
    )

    def __init__(
        self,
        manager: "SessionManager",
        llm: "LLMProvider | None" = None,
        *,
        router: Router | None = None,
        registry: AgentRegistry | None = None,
        validator: Validator | None = None,
        tracer: Tracer | None = None,
        skill_library: SkillLibrary | None = None,
    ) -> None:
        self.manager = manager
        self.llm = llm  # 不传则用 manager 自带
        self.router = router or Router()
        self.registry = registry or AgentRegistry.get_instance()
        self.validator = validator or Validator()
        self.tracer = tracer or Tracer()
        self.skill_library = skill_library or SkillLibrary.get_instance()

    # ------------------------------------------------------------------
    # 3.3 改进:核心 chat()
    # ------------------------------------------------------------------

    def chat(
        self,
        session_id: str,
        user_message: str,
        mode: ThinkingMode | None = None,
    ) -> str:
        """Process a single user turn end-to-end.

        流程:
          1) classify intent
          2) select agent (按 priority)
          3) run agent.run() → 失败兜底
          4) validate output(规则引擎)
          5) manager.persist() 持久化(turn + summary 调度 + 记忆入库)

        Returns:
            agent 的 reply
        """
        try:
            # 1) 意图分类
            intent = self.router.classify(user_message)
            # 2) 选 agent
            agent_ids = self.router.route(intent)
            agent_id = agent_ids[0] if agent_ids else "qa"

            # 3) 构造 agent 实例并 run
            agent = self._instantiate_agent(agent_id)
            if agent is None:
                # 兜底:返回"未注册 agent"提示
                return f"[Orchestrator] No agent registered for id={agent_id!r} (intent={intent.name})"
            try:
                # 3.x 简易 trace:每次构造一个 TraceRecord
                self.tracer.record(TraceRecord(
                    trace_id="",
                    session_id=session_id,
                    turn_index=0,   # 4.x 改造;3.x 不追踪
                    intent=intent.name,
                    agent_id=agent_id,
                    user_message=user_message,
                    response="",
                    mode=(mode.name if mode else ""),
                    latency_ms=0.0,
                ))
                reply = agent.run(user_message, mode=mode)
            except Exception as e:
                log.exception("Agent %s run failed", agent_id)
                reply = f"[Agent {agent_id} error] {e}"
                self.tracer.record(TraceRecord(
                    trace_id="",
                    session_id=session_id,
                    turn_index=0,
                    intent=intent.name,
                    agent_id=agent_id,
                    user_message=user_message,
                    response=reply,
                    mode=(mode.name if mode else ""),
                    latency_ms=0.0,
                ))

            # 4) 验证
            result = self.validator.check(reply, intent)
            if not result.passed:
                log.warning("Validation failed for %s: %s", agent_id, [i.message for i in result.issues])
                self.tracer.record(TraceRecord(
                    trace_id="",
                    session_id=session_id,
                    turn_index=0,
                    intent=intent.name,
                    agent_id=agent_id,
                    user_message=user_message,
                    response=reply,
                    mode=(mode.name if mode else ""),
                    latency_ms=0.0,
                ))

            # 5) 持久化
            try:
                self.manager.persist_turn(
                    session_id=session_id,
                    user_input=user_message,
                    reply=reply,
                )
            except Exception as e:
                log.exception("Persist failed: %s", e)

            # 成功 trace(覆盖前面的空版本)
            self.tracer.record(TraceRecord(
                trace_id="",
                session_id=session_id,
                turn_index=0,
                intent=intent.name,
                agent_id=agent_id,
                user_message=user_message,
                response=reply,
                mode=(mode.name if mode else ""),
                latency_ms=0.0,
            ))
            return reply
        except Exception as e:
            log.exception("Orchestrator.chat failed: %s", e)
            return f"[Orchestrator error] {e}"

    # ------------------------------------------------------------------
    # 3.3 改进:辅助
    # ------------------------------------------------------------------

    def _instantiate_agent(self, agent_id: str) -> Any:
        """从 registry 拿 agent 类,实例化(注入 llm + 共享组件)。

        3.3 实现:用 try/except 包裹,BaseAgent 的子类签名可能不一
        (有的子类 CodeReviewAgent(llm=) 有,有的没),失败了用无参构造再 setattr。
        """
        from mmi.agent.tools import ToolRegistry

        agent_cls = self.registry.match(agent_id)
        if agent_cls is None:
            return None
        try:
            return agent_cls(
                llm=self.llm,
                skill_library=self.skill_library,
                tool_registry=ToolRegistry.get_instance(),
            )
        except TypeError:
            # 子类签名不兼容 → 无参构造后 setattr
            try:
                inst = agent_cls()
            except Exception:
                return None
            for attr, val in [
                ("llm", self.llm),
                ("skill_library", self.skill_library),
                ("tool_registry", ToolRegistry.get_instance()),
            ]:
                if hasattr(inst, attr):
                    try:
                        setattr(inst, attr, val)
                    except Exception:
                        pass
            return inst
