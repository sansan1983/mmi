"""Call-chain tracing and observability framework.

R8 4.7 改进:Tracer 接收 event_bus(可选),每次 record() 后 publish 'trace.recorded'
事件 — 让外部订阅者(审计 / metrics / UI 实时面板)不必直接耦合 Tracer。
向后兼容:不传 event_bus 时行为不变(只追加到 _records)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar

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

    R8 4.7 改进:可选注入 event_bus,每次 record() 后 publish 'trace.recorded' 事件。
    设计目标:让审计 / 指标 / UI 实时面板等外部订阅者通过 EventBus 接入,
    不必直接依赖 Tracer 内部数据结构。Tracer 自己仍保留 _records 列表以保证
    query() / get_turn_count() 行为不变。
    """

    _instance: ClassVar[Tracer | None] = None

    def __init__(self, event_bus: "EventBus | None" = None) -> None:
        """
        Parameters
        ----------
        event_bus : EventBus, optional
            注入 EventBus(默认 None → 不发事件,纯 in-memory 模式)。
        """
        self._records: list[TraceRecord] = []
        self._bus = event_bus

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
    # Recording
    # ------------------------------------------------------------------

    def record(self, trace: TraceRecord) -> None:
        """Append a trace record, then publish 'trace.recorded' 事件(如注入 bus)。

        Parameters
        ----------
        trace : TraceRecord
            Completed turn trace.
        """
        self._records.append(trace)
        if self._bus is not None:
            # EventBus.publish 内部异常隔离 — 这里不需要 try/except
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
