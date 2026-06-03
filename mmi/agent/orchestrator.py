"""Main Orchestrator - entry point for single-turn conversation flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mmi.agent.modes import ThinkingMode
from mmi.agent.router import IntentType
from mmi.agent.skill import SkillLibrary
from mmi.agent.trace import TraceRecord, Tracer
from mmi.agent.validate import Validator

if TYPE_CHECKING:
    from mmi.core.session import Session


class Orchestrator:
    """Central coordinator for a single user turn.

    Orchestrates: intent classification - agent selection - execution -
    validation - skill update - trace recording.

    Parameters
    ----------
    session : Session
        Active session providing context and history.
    skill_library : SkillLibrary
        Shared skill repository for agent use and evolution.
    tracer : Tracer
        Call-chain recorder for observability.
    validator : Validator
        Output checker (rule engine + deep audit).
    """

    __slots__ = ("session", "skill_library", "tracer", "validator")

    def __init__(
        self,
        session: Session,  # type: ignore[name-defined]  # mmi.core not yet implemented
        skill_library: SkillLibrary,
        tracer: Tracer,
        validator: Validator,
    ) -> None:
        self.session = session
        self.skill_library = skill_library
        self.tracer = tracer
        self.validator = validator

    async def chat(
        self,
        user_message: str,
        mode: ThinkingMode | None = None,
    ) -> str:
        """Process a single user turn end-to-end.

        Parameters
        ----------
        user_message : str
            Raw user input.
        mode : ThinkingMode, optional
            Override thinking mode (defaults to session preference).

        Returns
        -------
        str
            Assistant response text.
        """
        raise NotImplementedError("LLM integration pending")

    async def _classify_intent(self, message: str) -> IntentType:
        """Classify user intent using the Router."""
        raise NotImplementedError("Router integration pending")

    async def _select_agent(self, intent: IntentType) -> str:
        """Pick the most suitable agent ID for the given intent."""
        raise NotImplementedError("Registry lookup pending")

    async def _run_agent(self, agent_id: str, message: str, mode: ThinkingMode) -> str:
        """Dispatch to the chosen sub-agent."""
        raise NotImplementedError("Agent execution pending")

    async def _validate_output(self, text: str, intent: IntentType) -> bool:
        """Check output quality; raise on failure."""
        raise NotImplementedError("Validator integration pending")

    async def _update_skills(self, agent_id: str, message: str, response: str) -> None:
        """Evolve skill library based on this turn."""
        raise NotImplementedError("Skill evolution pending")

    async def _record_trace(
        self,
        user_message: str,
        intent: IntentType,
        agent_id: str,
        response: str,
    ) -> None:
        """Append a trace record for observability."""
        raise NotImplementedError("Tracer integration pending")
