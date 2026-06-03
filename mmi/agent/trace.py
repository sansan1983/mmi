"""Call-chain tracing and observability framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar


@dataclass
class TraceRecord:
    """A single unit of work captured by the tracer.

    Attributes
    ----------
    trace_id : str
        Unique identifier for this trace (ULID recommended).
    session_id : str
        Parent session this trace belongs to.
    turn_index : int
        Turn number within the session (0-based).
    intent : str
        IntentType name at classification time.
    agent_id : str
        ID of the agent that handled this turn.
    user_message : str
        Raw user input.
    response : str
        Agent response text.
    mode : str
        ThinkingMode name used for this turn.
    latency_ms : float
        Wall-clock elapsed time in milliseconds.
    tokens_used : int, optional
        Token count consumed by this turn.
    metadata : dict, optional
        Arbitrary extra fields (tool calls, skill_ids, etc.).
    timestamp : str
        ISO-8601 UTC timestamp when the record was created.
    """

    trace_id: str
    session_id: str
    turn_index: int
    intent: str
    agent_id: str
    user_message: str
    response: str
    mode: str
    latency_ms: float
    tokens_used: int | None = None
    metadata: dict[str, Any] | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Tracer:
    """In-memory trace recorder with query support.

    Traces are held in memory for the lifetime of the process.  For
    persistence, wrap or subclass and delegate to storage.
    """

    _instance: ClassVar[Tracer | None] = None

    def __init__(self) -> None:
        self._records: list[TraceRecord] = []

    @classmethod
    def get_instance(cls) -> Tracer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, trace: TraceRecord) -> None:
        """Append a trace record.

        Parameters
        ----------
        trace : TraceRecord
            Completed turn trace.
        """
        self._records.append(trace)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def query(
        self,
        session_id: str | None = None,
        agent_id: str | None = None,
        intent: str | None = None,
        limit: int = 100,
    ) -> list[TraceRecord]:
        """Filter trace records by the given criteria.

        Parameters
        ----------
        session_id : str, optional
            Filter by session.
        agent_id : str, optional
            Filter by agent.
        intent : str, optional
            Filter by intent type name.
        limit : int
            Maximum number of records to return (most recent first).

        Returns
        -------
        list[TraceRecord]
        """
        results = self._records

        if session_id is not None:
            results = [r for r in results if r.session_id == session_id]
        if agent_id is not None:
            results = [r for r in results if r.agent_id == agent_id]
        if intent is not None:
            results = [r for r in results if r.intent == intent]

        # Most recent first
        return list(reversed(results))[:limit]

    def get_turn_count(self, session_id: str) -> int:
        """Return the number of recorded turns for *session_id*."""
        return sum(1 for r in self._records if r.session_id == session_id)
