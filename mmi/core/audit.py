"""LLM Deep Audit — Two-layer output safety review.

P3-4: When the system generates high-risk output (code execution, file deletion,
sensitive info), a two-layer audit is applied:

  Layer 1 — Rule Engine (zero latency):
    Pattern-based checks for known dangerous patterns (rm -rf, DROP TABLE, etc.).

  Layer 2 — LLM Audit (conditional):
    Triggered only when the rule-engine risk score exceeds ``auto_audit_threshold``.
    Sends the output to an LLM for deeper safety analysis.

Audit results are broadcast via EventBus as ``audit.passed`` / ``audit.flagged``.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from mmi.agent.event_bus import EventBus
    from mmi.core.llm import LLMProvider


# ---------------------------------------------------------------------------
# Risk levels
# ---------------------------------------------------------------------------

class RiskLevel(Enum):
    """Risk classification for audited output."""

    SAFE = auto()
    """No risk detected."""

    LOW = auto()
    """Minor concern, proceed with caution."""

    MEDIUM = auto()
    """Moderate risk, review recommended."""

    HIGH = auto()
    """Significant risk, should be blocked or require confirmation."""

    CRITICAL = auto()
    """Immediate danger, must be blocked."""


@dataclass
class AuditResult:
    """Result of an audit pass."""

    risk_level: RiskLevel
    score: float
    """0.0 (safe) to 1.0 (critical)."""

    reason: str = ""
    """Human-readable explanation."""

    flagged_patterns: list[str] = field(default_factory=list)
    """Patterns that triggered the rule engine."""

    layer1_score: float = 0.0
    layer2_score: float = 0.0

    @property
    def is_safe(self) -> bool:
        return self.risk_level in (RiskLevel.SAFE, RiskLevel.LOW)


# ---------------------------------------------------------------------------
# Rule Engine (Layer 1)
# ---------------------------------------------------------------------------

# Dangerous command patterns
_DANGEROUS_PATTERNS: list[tuple[str, float, str]] = [
    # Filesystem destruction
    (r"\brm\s+-rf\b", 0.95, "Destructive file removal (rm -rf)"),
    (r"\brmdir\s+/s\b", 0.9, "Force directory removal (Windows)"),
    (r"\bdel\s+/[sfq]\b", 0.85, "Force file deletion (Windows)"),
    (r"\bRemove-Item\s+.*-Recurse\s+.*-Force", 0.9, "Force recursive removal (PowerShell)"),
    # Database destruction
    (r"\bDROP\s+TABLE\b", 0.9, "Drop table (SQL)"),
    (r"\bDROP\s+DATABASE\b", 0.95, "Drop database (SQL)"),
    (r"\bTRUNCATE\s+TABLE\b", 0.7, "Truncate table (SQL)"),
    # System access
    (r"\bsudo\s+rm\b", 0.95, "Privileged file removal"),
    (r"\bchmod\s+777\b", 0.6, "Overly permissive file mode"),
    (r"\bformat\s+[A-Z]:", 0.95, "Disk format command"),
    # Credential exposure
    (r"\bpassword\s*=\s*['\"][^'\"]+['\"]", 0.8, "Hardcoded password"),
    (r"\bapi[_-]?key\s*=\s*['\"][^'\"]+['\"]", 0.75, "Hardcoded API key"),
    (r"\bsecret\s*=\s*['\"][^'\"]+['\"]", 0.75, "Hardcoded secret"),
    # Network
    (r"\bwget\s+.*\|\s*sh\b", 0.85, "Pipe remote script to shell"),
    (r"\bcurl\s+.*\|\s*(ba)?sh\b", 0.85, "Pipe remote script to shell"),
]


@dataclass
class AuditConfig:
    """Configuration for the audit engine."""

    auto_audit_threshold: float = 0.7
    """Rule-engine score above which Layer 2 (LLM audit) is triggered."""

    block_threshold: float = 0.9
    """Score above which output is automatically blocked."""

    enabled: bool = True
    """Master switch for the audit system."""


class AuditEngine:
    """Two-layer output safety auditor.

    Usage::

        from mmi.core.audit import AuditEngine

        engine = AuditEngine.get_instance()
        result = engine.audit("rm -rf /")
        if not result.is_safe:
            print(f"BLOCKED: {result.reason}")
    """

    _instance: ClassVar[AuditEngine | None] = None

    def __init__(
        self,
        *,
        config: AuditConfig | None = None,
        event_bus: EventBus | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self._config = config or AuditConfig()
        self._bus = event_bus
        self._llm = llm_provider
        self._lock = threading.RLock()
        self._compiled_patterns = [
            (re.compile(p, re.IGNORECASE), score, reason)
            for p, score, reason in _DANGEROUS_PATTERNS
        ]

    @classmethod
    def get_instance(cls) -> AuditEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    # ------------------------------------------------------------------
    # Layer 1: Rule Engine
    # ------------------------------------------------------------------

    def _rule_engine(self, text: str) -> tuple[float, list[str], list[str]]:
        """Run pattern-based risk assessment.

        Returns
        -------
        tuple[float, list[str], list[str]]
            (score, flagged_patterns, reasons)
        """
        max_score = 0.0
        flagged: list[str] = []
        reasons: list[str] = []

        for pattern, score, reason in self._compiled_patterns:
            if pattern.search(text):
                max_score = max(max_score, score)
                flagged.append(pattern.pattern)
                reasons.append(reason)

        return max_score, flagged, reasons

    # ------------------------------------------------------------------
    # Layer 2: LLM Audit
    # ------------------------------------------------------------------

    def _llm_audit(self, text: str) -> float:
        """Use LLM to assess risk (0.0 safe → 1.0 critical).

        Returns 0.0 if no LLM provider is configured.
        """
        if self._llm is None:
            return 0.0

        prompt = (
            "You are a safety auditor. Rate the risk level of the following output "
            "on a scale from 0.0 (completely safe) to 1.0 (critical danger).\n\n"
            "Consider: code execution risks, data loss, credential exposure, "
            "system compromise, or any harmful actions.\n\n"
            f"Output to audit:\n---\n{text[:2000]}\n---\n\n"
            "Respond with ONLY a number between 0.0 and 1.0."
        )

        try:
            response = self._llm.chat([{"role": "user", "content": prompt}])
            score = float(response.strip())
            return max(0.0, min(1.0, score))
        except (ValueError, Exception):
            return 0.5  # Default to medium risk on LLM failure

    # ------------------------------------------------------------------
    # Main audit
    # ------------------------------------------------------------------

    def audit(self, text: str) -> AuditResult:
        """Audit the given text through both layers.

        Parameters
        ----------
        text : str
            The output text to audit.

        Returns
        -------
        AuditResult
        """
        if not self._config.enabled:
            return AuditResult(risk_level=RiskLevel.SAFE, score=0.0, reason="Audit disabled")

        # Layer 1
        l1_score, flagged, reasons = self._rule_engine(text)

        # Decide if Layer 2 is needed
        l2_score = 0.0
        if l1_score >= self._config.auto_audit_threshold and self._llm is not None:
            l2_score = self._llm_audit(text)

        # Combined score: max of both layers
        final_score = max(l1_score, l2_score)

        # Determine risk level
        if final_score >= 0.9:
            risk = RiskLevel.CRITICAL
        elif final_score >= 0.7:
            risk = RiskLevel.HIGH
        elif final_score >= 0.5:
            risk = RiskLevel.MEDIUM
        elif final_score >= 0.3:
            risk = RiskLevel.LOW
        else:
            risk = RiskLevel.SAFE

        reason = "; ".join(reasons) if reasons else "No issues detected"

        result = AuditResult(
            risk_level=risk,
            score=final_score,
            reason=reason,
            flagged_patterns=flagged,
            layer1_score=l1_score,
            layer2_score=l2_score,
        )

        # Emit event
        if self._bus is not None:
            import time as _time

            from mmi.agent.event_bus import Event
            event_name = "audit.flagged" if not result.is_safe else "audit.passed"
            self._bus.publish(Event(
                name=event_name,
                timestamp=_time.time(),
                payload={
                    "score": final_score,
                    "risk_level": risk.name,
                    "reason": reason,
                },
            ))

        return result
