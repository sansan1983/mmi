"""Code review sub-agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mmi.agent.base import BaseAgent, ToolDef

if TYPE_CHECKING:
    from mmi.agent.modes import ThinkingMode


class CodeReviewAgent(BaseAgent):
    """Specialised agent for reviewing, auditing, and refactoring source code.

    Responsibilities
    ----------------
    - Static analysis: style, complexity, naming conventions.
    - Security scanning: hardcoded secrets, injection vectors, unsafe patterns.
    - Logic correctness: edge cases, off-by-one errors, race conditions.
    - Performance hints: algorithmic complexity, unnecessary allocations.
    - Documentation checks: missing docstrings, outdated comments.
    """

    __slots__ = ()

    def __init__(
        self,
        system_prompt: str = "You are a meticulous code reviewer.",
        tools: list[ToolDef] | None = None,
    ) -> None:
        super().__init__(
            agent_id="code_review",
            name="Code Review",
            system_prompt=system_prompt,
            tools=tools,
        )

    async def run(
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
        raise NotImplementedError("CodeReviewAgent not yet implemented")
