"""Code review sub-agent.

3.5 改进:CodeReviewAgent 最小可行实现。
继承 BaseAgent,用 _chat_with_llm() 调 LLM 完成审查。
支持 tools 列表(可后续接入 read_file 等)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mmi.agent.base import BaseAgent, ToolDef

if TYPE_CHECKING:
    from mmi.agent.modes import ThinkingMode
    from mmi.agent.skill import SkillLibrary
    from mmi.agent.tools import ToolRegistry
    from mmi.core.llm import LLMProvider


DEFAULT_SYSTEM_PROMPT = """You are a meticulous code reviewer.
Review the supplied code for: bugs, edge cases, security issues, style.
Output in this format:

## Summary
(one sentence overall)

## Issues
- **[severity]** description (file:line if applicable)

## Suggestions
- improvement recommendation

Be specific. Cite line numbers when possible. Reply in the user's language."""


class CodeReviewAgent(BaseAgent):
    """Specialised agent for reviewing, auditing, and refactoring source code.

    3.5 改进:run() 实现 — system_prompt 注入 + LLM 调用 + 错误兜底。
    """

    __slots__ = ()

    def __init__(
        self,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        tools: list[ToolDef] | None = None,
        skill_library: SkillLibrary | None = None,
        tool_registry: ToolRegistry | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        super().__init__(
            agent_id="code_review",
            name="Code Review",
            system_prompt=system_prompt,
            tools=tools,
            skill_library=skill_library,
            tool_registry=tool_registry,
            llm=llm,
        )

    def run(
        self,
        user_message: str,
        mode: ThinkingMode | None = None,
    ) -> str:
        """Review the supplied code and return structured findings.

        Parameters
        ----------
        user_message : str
            May contain code snippets, file paths, or review instructions.
        mode : ThinkingMode, optional
            Thinking mode override.

        Returns
        -------
        str
            Formatted review report.
        """
        from mmi.core.llm import LLMError
        try:
            self.on_start()
            reply = self._chat_with_llm(user_message, mode=mode, max_tokens=2048)
            return reply
        except LLMError as e:
            self.on_error(e)
            return f"[CodeReviewAgent error] {e}"
        finally:
            self.on_stop()
