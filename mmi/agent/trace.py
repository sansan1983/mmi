"""Call-chain tracing and observability framework with disk persistence.

R8 4.7: Tracer accepts optional event_bus, publishes 'trace.recorded'.
P3-2: Traces are persisted to JSON Lines files in ~/.mmi/traces/.

Storage layout::

    ~/.mmi/traces/<session_id>.jsonl

Each line is a JSON object with trace metadata (no user_message/response
content for privacy compliance).
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from mmi.core.paths import get_traces_dir

if TYPE_CHECKING:
    from mmi.agent.event_bus import EventBus


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
        Raw user input (NOT persisted to disk for privacy).
    response : str
        Agent response text (NOT persisted to disk for privacy).
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
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    # Fields excluded from disk persistence for privacy compliance
    _PRIVATE_FIELDS: ClassVar[frozenset[str]] = frozenset({"user_message", "response"})

    def to_dict(self, *, include_private: bool = False) -> dict:
        """Convert to JSON-serializable dict.

        Parameters
        ----------
        include_private : bool
            If True, include ``user_message`` and ``response``.
            Default False for disk persistence (privacy compliance).
        """
        d = asdict(self)
        if not include_private:
            for f in self._PRIVATE_FIELDS:
                d.pop(f, None)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> TraceRecord:
        """Reconstruct from a dict (e.g. loaded from JSON).

        Missing ``user_message`` / ``response`` are filled with empty strings.
        """
        data = dict(data)
        data.setdefault("user_message", "")
        data.setdefault("response", "")
        return cls(**data)


class Tracer:
    """Trace recorder with in-memory query support and disk persistence.

    Traces are:
    1. Held in memory for fast querying (``query()`` / ``get_turn_count()``).
    2. Persisted to ``~/.mmi/traces/<session_id>.jsonl`` on each ``record()``.

    Thread safety via internal ``RLock``.
    """

    _instance: ClassVar[Tracer | None] = None

    def __init__(
        self,
        event_bus: EventBus | None = None,
        *,
        traces_dir: Path | None = None,
    ) -> None:
        """
        Parameters
        ----------
        event_bus : EventBus, optional
            Inject EventBus for 'trace.recorded' events.
        traces_dir : Path, optional
            Override trace storage directory (for testing).
        """
        self._records: list[TraceRecord] = []
        self._lock = threading.RLock()
        self._bus = event_bus
        self._traces_dir = traces_dir or get_traces_dir()
        self._traces_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> Tracer:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """测试用:清掉单例(避免测试间污染)。"""
        cls._instance = None

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _trace_file(self, session_id: str) -> Path:
        """Return the JSON Lines file path for *session_id*."""
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_.")
        if not safe:
            safe = "unknown"
        return self._traces_dir / f"{safe}.jsonl"

    def _append_to_disk(self, trace: TraceRecord) -> None:
        """Append a trace record to its session's JSON Lines file."""
        path = self._trace_file(trace.session_id)
        line = json.dumps(trace.to_dict(include_private=False), ensure_ascii=False)
        with self._lock, open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, trace: TraceRecord) -> None:
        """Append a trace record, persist to disk, then publish event.

        Parameters
        ----------
        trace : TraceRecord
            Completed turn trace.
        """
        with self._lock:
            self._records.append(trace)
        self._append_to_disk(trace)

        if self._bus is not None:
            import time

            from mmi.agent.event_bus import Event
            self._bus.publish(Event(
                name="trace.recorded",
                timestamp=time.time(),
                payload={
                    "trace_id": trace.trace_id,
                    "session_id": trace.session_id,
                    "agent_id": trace.agent_id,
                    "intent": trace.intent,
                    "latency_ms": trace.latency_ms,
                },
            ))

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
        with self._lock:
            results = list(self._records)

        if session_id is not None:
            results = [r for r in results if r.session_id == session_id]
        if agent_id is not None:
            results = [r for r in results if r.agent_id == agent_id]
        if intent is not None:
            results = [r for r in results if r.intent == intent]

        return list(reversed(results))[:limit]

    def get_turn_count(self, session_id: str) -> int:
        """Return the number of recorded turns for *session_id*."""
        with self._lock:
            return sum(1 for r in self._records if r.session_id == session_id)

    # ------------------------------------------------------------------
    # Disk-based stats (for CLI `mmi trace stats`)
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return aggregate statistics from in-memory records.

        Returns
        -------
        dict
            Keys: total_records, unique_sessions, avg_latency_ms,
            by_intent, by_agent.
        """
        with self._lock:
            records = list(self._records)

        if not records:
            return {
                "total_records": 0,
                "unique_sessions": 0,
                "avg_latency_ms": 0.0,
                "by_intent": {},
                "by_agent": {},
            }

        by_intent: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        total_latency = 0.0

        for r in records:
            by_intent[r.intent] = by_intent.get(r.intent, 0) + 1
            by_agent[r.agent_id] = by_agent.get(r.agent_id, 0) + 1
            total_latency += r.latency_ms

        return {
            "total_records": len(records),
            "unique_sessions": len({r.session_id for r in records}),
            "avg_latency_ms": round(total_latency / len(records), 2),
            "by_intent": by_intent,
            "by_agent": by_agent,
        }
