"""Documentation generation sub-agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mmi.agent.base import BaseAgent, ToolDef

if TYPE_CHECKING:
    from mmi.agent.modes import ThinkingMode


class DocAgent(BaseAgent):
    """Specialised agent for generating and maintaining documentation.

    Responsibilities
    ----------------
    - API documentation: docstrings, type hints, parameter tables.
    - README and guide generation from codebase structure.
    - Changelog and migration notes.
    - Inline comments and explanatory prose.
    - Multi-format output: Markdown, RST, HTML.
    """

    __slots__ = ()

    def __init__(
        self,
        system_prompt: str = "You are a technical writer who produces clear documentation.",
        tools: list[ToolDef] | None = None,
    ) -> None:
        super().__init__(
            agent_id="doc",
            name="Documentation",
            system_prompt=system_prompt,
            tools=tools,
        )

    async def run(
        self,
        user_message: str,
        mode: ThinkingMode | None = None,
    ) -> str:
        """Generate or update documentation based on user instructions.

        Parameters
        ----------
        user_message : str
            May contain source files, existing docs, or generation requests.
        mode : ThinkingMode, optional
            Thinking mode override.

        Returns
        -------
        str
            Generated documentation content.
        """
        raise NotImplementedError("DocAgent not yet implemented")
