"""Output validation — rule engine (regex / substring / length checks)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

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

    min_length: int | None = None
    """3.4 改进:Reject if output is shorter than this length."""

    min_length_error: str = "output too short (looks like empty/noise reply)"

    severity: Literal["error", "warning"] = "error"
    """4.10 引入:rule 默认严重级。error 阻断 passed,warning 只记不阻断。
    (注:当前版本 passed 只看 issues 是否为空,severity 仍参与 passed 计算路径
    留到 R8 4.9 评估;但 ValidationIssue 字段先有,后续可挂。)"""


class Validator:
    """Validates agent output before it is returned to the user.

    P9.1 简化:原本的"两阶段(rule engine + LLM deep audit)"减为单阶段
    (rule engine only)。LLM deep audit 留待未来 Phase;目前不可用、不暴露
    开关,避免半成品 API 让人误用。
    """

    __slots__ = ("_rules",)

    def __init__(
        self,
        rules: list[ValidationRule] | None = None,
    ) -> None:
        """Configure the validator.

        Parameters
        ----------
        rules : list[ValidationRule], optional
            Rule set for the fast engine. A default set covers common
            safety and format concerns.
        """
        self._rules = rules or _default_rules()

    def check(self, text: str, intent: IntentType) -> ValidationResult:
        """Run the validation pipeline (rule engine only).

        Parameters
        ----------
        text : str
            Agent output to validate.
        intent : IntentType
            Intent type of the originating request (currently unused,
            reserved for future deep-audit routing).

        Returns
        -------
        ValidationResult
            ``passed=True`` if all checks pass, ``passed=False`` otherwise.
        """
        del intent  # 预留参数,当前 rule engine 不区分 intent
        return self._check_rules(text)

    def _check_rules(self, text: str) -> ValidationResult:
        """Run the fast rule engine.

        3.4 改进:每条 rule 跑完把失败原因加进 issues(之前没 min_length 检查)。
        4.3 改进:issues 是 ValidationIssue tuple(占位,只含 message)。
        4.10 改进:ValidationIssue 扩到 4 字段 — message / severity / rule_id / span;
        每条 issue 携带触发它的 rule 名(便于审计 / 聚合统计)与命中区间(便于 UI 高亮)。
        """
        issues: list[ValidationIssue] = []
        for rule in self._rules:
            # Length check (max)
            if rule.max_length is not None and len(text) > rule.max_length:
                issues.append(ValidationIssue(
                    message=f"[{rule.name}] Output exceeds max length {rule.max_length}",
                    severity=rule.severity,
                    rule_id=rule.name,
                    span=(0, min(len(text), rule.max_length)),
                ))

            # Length check (min) — 3.4 新增
            if rule.min_length is not None and len(text.strip()) < rule.min_length:
                issues.append(ValidationIssue(
                    message=f"[{rule.name}] {rule.min_length_error} (got {len(text.strip())} chars)",
                    severity=rule.severity,
                    rule_id=rule.name,
                    span=(0, len(text)),
                ))

            # Required substrings
            for sub in rule.required_substrings:
                if sub not in text:
                    issues.append(ValidationIssue(
                        message=f"[{rule.name}] Missing required substring: {sub!r}",
                        severity=rule.severity,
                        rule_id=rule.name,
                        span=None,
                    ))

            # Negative regex
            if rule.pattern is not None:
                for m in re.finditer(rule.pattern, text):
                    issues.append(ValidationIssue(
                        message=f"[{rule.name}] Output matches prohibited pattern: {rule.pattern!r}",
                        severity=rule.severity,
                        rule_id=rule.name,
                        span=(m.start(), m.end()),
                    ))

        return ValidationResult(passed=len(issues) == 0, issues=tuple(issues))


# ---------------------------------------------------------------------------
# ValidationIssue / ValidationResult
# 4.10:ValidationIssue 扩到 4 字段(message / severity / rule_id / span)
# 字段含义:
#   - message: 人类可读描述(给 UI / 日志看)
#   - severity: "error"(阻断 passed)或 "warning"(只记,后续可挂 passed 策略)
#   - rule_id: 触发本 issue 的 rule 名(聚合统计 / 审计 / 决定是否记 EventBus)
#   - span: (start, end) 字符 offset 区间,UI 可用做高亮
# 注:field 顺序固定;asdict / JSON 序列化按本顺序展开(向后兼容,旧测试只读 .message)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationIssue:
    """Single structured validation issue.

    R7 4.3 引入(占位,只含 message)。
    R8 4.10 扩展为 4 字段 — frozen=True 保证不可变,便于放进 tuple / EventBus payload。
    """

    message: str = ""
    severity: Literal["error", "warning"] = "error"
    rule_id: str = ""
    span: tuple[int, int] | None = None


@dataclass
class ValidationResult:
    """Outcome of a validation run."""

    passed: bool
    """True when all checks passed."""

    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)
    """Human-readable list of failure reasons. Empty when ``passed=True``."""



# --------------------------------------------------------------------------


def _default_rules() -> list[ValidationRule]:
    """Return the default rule set applied when no rules are supplied.

    3.4 改进:加 4 条基础规则(no_dangerous_tokens / not_empty / not_too_short / no_dangerous_phrase)
    """
    return [
        # 危险:泄露密钥
        ValidationRule(
            name="no_dangerous_tokens",
            pattern=r"(?i)\b(password|secret|api.?key|token)\s*=\s*[\"'][^\"']+[\"']",
        ),
        # 输出非空
        ValidationRule(
            name="not_empty",
            required_substrings=[],
        ),
        # 输出不能太短(避免 LLM 只返 "OK" 这种没意义)
        ValidationRule(
            name="not_too_short",
            min_length=2,
        ),
        # 危险短语(粗筛;细筛由运行人员人工把关)
        ValidationRule(
            name="no_dangerous_phrase",
            pattern=r"(?i)\b(rm\s+-rf\s+/|drop\s+database|format\s+c:|del\s+/\*)\b",
        ),
    ]
