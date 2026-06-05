"""Dynamic agent registration and discovery.

3.8 改进:get_instance() 加 threading.Lock,避免多线程环境创建多实例。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from mmi.agent.base import BaseAgent


@dataclass
class AgentMeta:
    """Static metadata attached to a registered agent."""

    agent_id: str
    """Unique identifier (e.g. ``"code_review"``)."""

    name: str
    """Human-readable display name."""

    description: str = ""
    """One-sentence description of the agent's responsibility."""

    tags: list[str] = field(default_factory=list)
    """Arbitrary labels for filtering / discovery."""

    version: str = "0.1.0"
    """Semantic version of the agent implementation."""

    builtin: bool = False
    """Whether this agent ships with the framework."""


class AgentRegistry:
    """Central registry for all sub-agents.

    Agents are registered at startup (builtin) or dynamically at runtime.
    Lookup by ID is O(1); filtering by tag or capability is O(n) with a
    small n (expected < 100 agents in typical deployments).
    """

    _instance: ClassVar[AgentRegistry | None] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._agents: dict[str, tuple[AgentMeta, type[BaseAgent]]] = {}

    @classmethod
    def get_instance(cls) -> AgentRegistry:
        """Return the singleton registry, creating it on first call.

        3.8 改进:加锁保护(原版无锁,多线程可能创建多实例)。
        """
        # 快速路径:已存在直接返
        if cls._instance is not None:
            return cls._instance
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        meta: AgentMeta,
        agent_cls: type[BaseAgent],
    ) -> None:
        """Add *agent_cls* to the registry under *meta.agent_id*.

        Raises
        ------
        ValueError
            If an agent with the same ``agent_id`` is already registered.
        """
        if meta.agent_id in self._agents:
            raise ValueError(f"Agent already registered: {meta.agent_id!r}")
        self._agents[meta.agent_id] = (meta, agent_cls)

    def register_instance(
        self,
        meta: AgentMeta,
        agent: BaseAgent,
    ) -> None:
        """Register a pre-instantiated agent (singleton-like pattern)."""
        if meta.agent_id in self._agents:
            raise ValueError(f"Agent already registered: {meta.agent_id!r}")
        self._agents[meta.agent_id] = (meta, type(agent))

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def match(self, agent_id: str) -> type[BaseAgent] | None:
        """Return the agent class for *agent_id*, or None if not found."""
        entry = self._agents.get(agent_id)
        return entry[1] if entry else None

    def get(self, agent_id: str) -> "BaseAgent | None":
        """Return an instantiated agent for *agent_id*, or None if not found.

        R7 4.2 引入:Pipeline.InstantiateStep 直接调这个,无需 Orchestrator 包一层。
        构造时尝试常见签名 ``(llm=, skill_library=, tool_registry=)``;
        失败则无参构造 + setattr(子类签名不兼容时兜底)。
        """
        from mmi.agent.tools import ToolRegistry

        agent_cls = self.match(agent_id)
        if agent_cls is None:
            return None
        llm = getattr(self, "_default_llm", None)
        skill_library = getattr(self, "_default_skill_library", None)
        tool_registry = ToolRegistry.get_instance()
        try:
            return agent_cls(
                llm=llm,
                skill_library=skill_library,
                tool_registry=tool_registry,
            )
        except TypeError:
            try:
                inst = agent_cls()
            except Exception:
                return None
            for attr, val in [
                ("llm", llm),
                ("skill_library", skill_library),
                ("tool_registry", tool_registry),
            ]:
                if hasattr(inst, attr):
                    try:
                        setattr(inst, attr, val)
                    except Exception:
                        pass
            return inst

    def set_default_llm(self, llm: object) -> None:
        """R7 4.2 引入:让 .get() 构造时用这个 llm(由 Orchestrator 注入)。"""
        self._default_llm = llm

    def set_default_skill_library(self, skill_library: object) -> None:
        """R7 4.2 引入:让 .get() 构造时用这个 skill_library(由 Orchestrator 注入)。"""
        self._default_skill_library = skill_library

    def get_meta(self, agent_id: str) -> AgentMeta | None:
        """Return metadata for *agent_id*, or None if not found."""
        entry = self._agents.get(agent_id)
        return entry[0] if entry else None

    def list_all(self, tag: str | None = None) -> list[AgentMeta]:
        """Return all registered agent metadata.

        Parameters
        ----------
        tag : str, optional
            When provided, filter to agents whose ``tags`` contain *tag*.

        Returns
        -------
        list[AgentMeta]
        """
        metas = [m for m, _ in self._agents.values()]
        if tag:
            metas = [m for m in metas if tag in m.tags]
        return metas
