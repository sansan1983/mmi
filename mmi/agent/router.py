"""Intent classification and sub-agent routing."""

from __future__ import annotations

from enum import Enum, auto


class IntentType(Enum):
    """Broad categories the router can dispatch to.

    Each value maps to one or more registered agents in the pool.
    """

    CODE_REVIEW = auto()
    """Inspect, audit, or refactor source code."""

    DOC_GENERATION = auto()
    """Generate or update documentation."""

    DATA_ANALYSIS = auto()
    """Query, transform, visualise, or summarise data."""

    BRAINSTORM = auto()
    """Creative ideation and divergent thinking."""

    AUDIT = auto()
    """Compliance, security, or logic audit of a given artifact."""

    QA = auto()
    """Question-answering against known context or skills."""

    TOOL_CALL = auto()
    """Execute a registered tool (search, compute, etc.)."""

    UNKNOWN = auto()
    """No confident intent - fall back to default agent."""


class Router:
    """Maps user input to an IntentType and selects the target agent(s).

    Implements a lightweight classifier (heuristic + optional LLM call)
    and exposes a route() method that returns agent identifiers.
    """

    __slots__ = ("_use_llm",)

    def __init__(self, use_llm: bool = True) -> None:
        """Configure the router.

        Parameters
        ----------
        use_llm : bool
            When True, delegate ambiguous cases to the LLM. When False,
            fall back to keyword / heuristic scoring only.
        """
        self._use_llm = use_llm

    def classify(self, user_message: str) -> IntentType:
        """Return the most likely IntentType for user_message.

        Parameters
        ----------
        user_message : str
            Raw user input.

        Returns
        -------
        IntentType
        """
        raise NotImplementedError("Classifier model not yet integrated")

    def route(self, intent: IntentType) -> list[str]:
        """Return ordered list of agent IDs for the given intent.

        Parameters
        ----------
        intent : IntentType
            Classified intent from :meth:class:`classify`.

        Returns
        -------
        list[str]
            Agent identifiers, ordered by priority (highest first).
        """
        mapping: dict[IntentType, list[str]] = {
            IntentType.CODE_REVIEW:    ["code_review"],
            IntentType.DOC_GENERATION: ["doc"],
            IntentType.DATA_ANALYSIS:  ["data"],
            IntentType.BRAINSTORM:     ["brainstorm"],
            IntentType.AUDIT:          ["audit"],
            IntentType.QA:             ["qa"],
            IntentType.TOOL_CALL:      ["tool_executor"],
            IntentType.UNKNOWN:        ["fallback"],
        }
        return mapping.get(intent, ["fallback"])
