"""Data analysis sub-agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mmi.agent.base import BaseAgent, ToolDef

if TYPE_CHECKING:
    from mmi.agent.modes import ThinkingMode


class DataAgent(BaseAgent):
    """Specialised agent for querying, transforming, and visualising data.

    Responsibilities
    ----------------
    - SQL query generation and optimisation hints.
    - Data profiling: missing values, distributions, correlations.
    - Transformation pipelines: filter, aggregate, join, pivot.
    - Chart specification: chart type selection, axis labelling.
    - Summary narration: translate findings into plain language.
    """

    __slots__ = ()

    def __init__(
        self,
        system_prompt: str = "You are a data analyst who produces accurate, reproducible insights.",
        tools: list[ToolDef] | None = None,
    ) -> None:
        super().__init__(
            agent_id="data",
            name="Data Analysis",
            system_prompt=system_prompt,
            tools=tools,
        )

    async def run(
        self,
        user_message: str,
        mode: ThinkingMode | None = None,
    ) -> str:
        """Analyse the described data and return findings or generated code.

        Parameters
        ----------
        user_message : str
            May contain data descriptions, schema, or analysis requests.
        mode : ThinkingMode, optional
            Thinking mode override.

        Returns
        -------
        str
            Analysis results, SQL, or code snippets.
        """
        raise NotImplementedError("DataAgent not yet implemented")
