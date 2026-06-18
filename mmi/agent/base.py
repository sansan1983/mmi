"""Abstract base class for all sub-agents.

3.7 改进:
  - run() 实现骨架(LLM 调用 + system_prompt 注入 + modes 套用)
  - 生命周期钩子:on_start / on_stop / on_error(默认 no-op,子类可覆盖)
  - 构造时注入 ToolRegistry / SkillLibrary
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from mmi.core.llm import LLMError, LLMProvider

if TYPE_CHECKING:
    from mmi.agent.modes import ThinkingMode
    from mmi.agent.tools import ToolDef


# ToolDef 在 mmi.agent.tools 里有完整定义(3.6 改),这里只 re-export 保持向后兼容。
# 不再重复定义,避免 dataclass 冲突。
from mmi.agent.tools import ToolDef  # noqa: F401  (re-export)


class BaseAgent(ABC):
    """Abstract base for all sub-agents.

    Subclasses must implement :meth:`run`, which contains the agent's
    core logic. The framework handles lifecycle, tracing, and skill
    injection — agents should focus purely on their task.

    Parameters
    ----------
    agent_id : str
        Unique identifier, must match an entry in AgentRegistry.
    name : str
        Display name.
    system_prompt : str
        Static instruction string prepended to every conversation.
    tools : list[ToolDef], optional
        Tools available to this agent (injected into context).
    skill_library : SkillLibrary, optional
        Reference to the shared skill repository.
    tool_registry : ToolRegistry, optional
        3.7 改进:可调用的工具注册中心
    llm : LLMProvider, optional
        3.7 改进:run() 用 LLM 实例调 chat;不传则用全局 get_default_provider()
    """

    __slots__ = (
        "agent_id",
        "name",
        "system_prompt",
        "llm",
    )

    def __init__(
        self,
        agent_id: str,
        name: str,
        system_prompt: str,
        llm: LLMProvider | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.system_prompt = system_prompt
        self.llm = llm  # None → run() 时用 get_default_provider()

    # ------------------------------------------------------------------
    # 3.7 改进:生命周期钩子(默认 no-op,子类可覆盖)
    # ------------------------------------------------------------------

    def on_start(self) -> None:  # noqa: B027
        """Agent 启动时调(资源初始化)。"""
        pass

    def on_stop(self) -> None:  # noqa: B027
        """Agent 停止时调(资源清理)。"""
        pass

    def on_error(self, exc: BaseException) -> None:  # noqa: B027
        """Agent run() 抛异常时调。"""
        pass

    # ------------------------------------------------------------------
    # 核心:子类必须实现
    # ------------------------------------------------------------------

    @abstractmethod
    def run(
        self,
        user_message: str,
        mode: ThinkingMode | None = None,
    ) -> str:
        """Execute the agent's task.

        子类实现:构造 messages → 调 LLM → 返回 reply。
        3.7 改进:基类提供 _chat_with_llm() 辅助。
        """
        raise NotImplementedError(f"{self.__class__.__name__}.run() not yet implemented")

    # ------------------------------------------------------------------
    # 3.7 改进:共享辅助
    # ------------------------------------------------------------------

    def _get_llm(self) -> LLMProvider:
        """取 LLM 实例(self.llm 优先,否则全局)。"""
        if self.llm is not None:
            return self.llm
        from mmi.core.llm import get_default_provider
        return get_default_provider()

    def _chat_with_llm(
        self,
        user_message: str,
        mode: ThinkingMode | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        """标准的 chat 调用:拼 messages(system + mode + user)→ 调 LLM → 返 reply。

        错误处理:LLMError / ValueError → 重新 raise,让 on_error 钩子处理。
        """
        from mmi.agent.modes import get_mode_prompt
        llm = self._get_llm()

        # 构造 messages
        system_content = self.system_prompt
        if mode is not None:
            mode_p = get_mode_prompt(mode)
            system_content = f"{system_content}\n\n{mode_p.system_suffix}"

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_message},
        ]
        try:
            return llm.chat(messages, max_tokens=max_tokens, temperature=temperature)
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"{self.agent_id} chat failed: {e}") from e

