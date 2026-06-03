"""Output validation — rule engine + optional LLM deep audit."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mmi.agent.router import IntentType


@dataclass
class ValidationRule:
    """A single rule for the rule engine."""

    name: str
    pattern: str | None = None
    """Regex pattern the output must not match (negative rule)."""

    required_substrings: list[str] = field(default_factory=list)
    """Substrings that must be present (positive rule)."""

    max_length: int | None = None
    """Reject if output exceeds this length."""


class Validator:
    """Validates agent output before it is returned to the user.

    Two-stage pipeline:
    1. Fast rule engine (regex / substring / length checks).
    2. Optional LLM deep audit for high-risk outputs.
    """

    __slots__ = ("_rules", "_use_llm_deep_audit", "_high_risk_intents")

    def __init__(
        self,
        rules: list[ValidationRule] | None = None,
        use_llm_deep_audit: bool = True,
    ) -> None:
        """Configure the validator.

        Parameters
        ----------
        rules : list[ValidationRule], optional
            Rule set for the fast engine. A default set covers common
            safety and format concerns.
        use_llm_deep_audit : bool
            Enable LLM-based deep audit for high-risk intents.
        """
        self._rules = rules or _default_rules()
        self._use_llm_deep_audit = use_llm_deep_audit
        self._high_risk_intents: set[IntentType] = set()

    def add_high_risk_intent(self, intent: IntentType) -> None:
        """Mark an intent type as high-risk (triggers deep audit)."""
        self._high_risk_intents.add(intent)

    def check(self, text: str, intent: IntentType) -> ValidationResult:
        """Run the full validation pipeline.

        Parameters
        ----------
        text : str
            Agent output to validate.
        intent : IntentType
            Intent type of the originating request.

        Returns
        -------
        ValidationResult
            ``passed=True`` if all checks pass, ``passed=False`` otherwise.
        """
        # Stage 1: fast rule engine
        rule_result = self._check_rules(text)
        if not rule_result.passed:
            return rule_result

        # Stage 2: LLM deep audit for high-risk intents
        if self._use_llm_deep_audit and intent in self._high_risk_intents:
            return self._llm_deep_audit(text, intent)

        return ValidationResult(passed=True, reasons=[])

    def _check_rules(self, text: str) -> ValidationResult:
        """Run the fast rule engine."""
        reasons: list[str] = []
        for rule in self._rules:
            # Length check
            if rule.max_length is not None and len(text) > rule.max_length:
                reasons.append(f"[{rule.name}] Output exceeds max length {rule.max_length}")

            # Required substrings
            for sub in rule.required_substrings:
                if sub not in text:
                    reasons.append(f"[{rule.name}] Missing required substring: {sub!r}")

            # Negative regex
            if rule.pattern is not None and re.search(rule.pattern, text):
                reasons.append(f"[{rule.name}] Output matches prohibited pattern: {rule.pattern!r}")

        return ValidationResult(passed=len(reasons) == 0, reasons=reasons)

    def _llm_deep_audit(self, text: str, intent: IntentType) -> ValidationResult:
        """Call LLM for nuanced safety / quality audit."""
        raise NotImplementedError("LLM deep audit not yet integrated")


@dataclass
class ValidationResult:
    """Outcome of a validation run."""

    passed: bool
    """True when all checks passed."""

    reasons: list[str] = field(default_factory=list)
    """Human-readable list of failure reasons. Empty when ``passed=True``."""


# --------------------------------------------------------------------------


def _default_rules() -> list[ValidationRule]:
    """Return the default rule set applied when no rules are supplied."""
    return [
        ValidationRule(
            name="no_dangerous_tokens",
            pattern=r"(?i)\b(password|secret|api.?key|token)\s*=\s*[\"'][^\"']+[\"']",
        ),
        ValidationRule(
            name="not_empty",
            required_substrings=[],
        ),
    ]
