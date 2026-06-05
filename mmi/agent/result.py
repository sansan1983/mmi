"""统一的 chat 结果数据契约。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Any

from mmi.agent.validate import ValidationResult

if TYPE_CHECKING:
    from mmi.agent.router import IntentType


@dataclass
class ChatResult:
    """Unified contract for a single chat turn.

    Used by callers that need a structured reply (UI / API / pipeline)
    instead of a bare string. Returned by ``chat_with_retry`` and by
    the future async orchestrator.
    """

    reply: str
    intent: "IntentType"
    agent_id: str
    validation: "ValidationResult | None"
    trace_ids: list[str] = field(default_factory=list)
    attempts: int = 1
    latency_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["intent"] = self.intent.name.lower() if self.intent is not None else None
        # issues is a tuple of ValidationIssue; serialize as a list of dicts
        if isinstance(self.validation, ValidationResult):
            d["validation"] = {
                "passed": self.validation.passed,
                "issues": [asdict(i) for i in self.validation.issues],
            }
        return d
