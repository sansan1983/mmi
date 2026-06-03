"""Abstract base class for all sub-agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mmi.agent.modes import ThinkingMode
    from mmi.agent.skill import SkillLibrary


@dataclass
class ToolDef:
    """Definition of a capability this agent can call.

    Attributes
    ----------
    name : str
        Unique tool identifier.
    description : str
        Human-readable description shown to the LLM.
    schema : dict
        JSON Schema describing the tool's input parameters.
    """

    name: str
    description: str
    schema: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base for all sub-agents.

    Subclasses must implement :meth:`run`, which contains the agent's
    core logic.  The framework handles lifecycle, tracing, and skill
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
    """

    __slots__ = (
        "agent_id",
        "name",
        "system_prompt",
        "tools",
        "skill_library",
    )

    def __init__(
        self,
        agent_id: str,
        name: str,
        system_prompt: str,
        tools: list[ToolDef] | None = None,
        skill_library: SkillLibrary | None = None,  # type: ignore[name-defined]  # mmi.agent.skill not yet implemented
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.skill_library = skill_library

    @abstractmethod
    async def run(
        self,
        user_message: str,
        mode: ThinkingMode | None = None,
    ) -> str:
        """Execute the agent's task.

        Parameters
        ----------
        user_message : str
            The user's request (may include attached context).
        mode : ThinkingMode, optional
            Thinking mode override for this turn.

        Returns
        -------
        str
            The agent's response text.

        Raises
        ------
        NotImplementedError
            Placeholder until the agent is implemented.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.run() not yet implemented")
