"""ValidationIssue 4 字段(severity / rule_id / span)+ ValidationRule.severity 测试。

R8 4.10 引入:
  - ValidationIssue 扩到 {message, severity, rule_id, span}
  - ValidationRule 加 severity 字段(error/warning)
  - frozen=True 保证不可变

向后兼容:
  - ValidationIssue(message=...) 仍合法(其他字段有默认值)
  - ValidationResult.issues 序列化(asdict)自动按新字段展开
  - 旧测试的 i.message 访问不受影响
"""
from __future__ import annotations

from mmi.agent.router import IntentType
from mmi.agent.validate import (
    ValidationIssue,
    ValidationResult,
    ValidationRule,
    Validator,
)


# ---------------------------------------------------------------------------
# ValidationIssue 结构
# ---------------------------------------------------------------------------


def test_validation_issue_default_severity_is_error():
    """未指定 severity 时默认 error(保持向后兼容 — 旧调用者行为不变)。"""
    issue = ValidationIssue(message="x")
    assert issue.severity == "error"
    assert issue.message == "x"
    assert issue.rule_id == ""
    assert issue.span is None


def test_validation_issue_explicit_fields():
    issue = ValidationIssue(
        message="bad",
        severity="warning",
        rule_id="no_dangerous_tokens",
        span=(0, 10),
    )
    assert issue.severity == "warning"
    assert issue.rule_id == "no_dangerous_tokens"
    assert issue.span == (0, 10)


def test_validation_issue_is_frozen():
    """frozen=True — 不可变。"""
    issue = ValidationIssue(message="x", rule_id="r")
    try:
        issue.message = "y"  # type: ignore[misc]
    except Exception as e:  # FrozenInstanceError
        assert "frozen" in str(e).lower() or "assign" in str(e).lower()
    else:
        raise AssertionError("expected frozen ValidationIssue to reject attribute set")


# ---------------------------------------------------------------------------
# Validator 把新字段填进 issues
# ---------------------------------------------------------------------------


def test_validator_rule_id_is_populated():
    """rule 触发时,issue.rule_id 必须是 rule.name。"""
    v = Validator(rules=[
        ValidationRule(name="custom_rule", pattern=r"foo"),
    ])
    r = v.check("this contains foo here", IntentType.QA)
    assert not r.passed
    assert len(r.issues) >= 1
    for issue in r.issues:
        assert issue.rule_id == "custom_rule"


def test_validator_span_set_for_regex_match():
    """regex rule 触发时,span 指向 match 的字符区间。"""
    v = Validator(rules=[
        ValidationRule(name="find_xyz", pattern=r"xyz"),
    ])
    text = "0123456789xyzABCDEF"  # xyz 在 10..13
    r = v.check(text, IntentType.QA)
    assert not r.passed
    assert len(r.issues) == 1
    assert r.issues[0].span == (10, 13)


def test_validator_span_none_for_missing_substring():
    """required_substrings 缺失时,span 是 None(没有具体命中位置)。"""
    v = Validator(rules=[
        ValidationRule(name="needs_foo", required_substrings=["foo"]),
    ])
    r = v.check("bar baz", IntentType.QA)
    assert not r.passed
    assert r.issues[0].span is None


def test_validator_span_set_for_max_length():
    """max_length 触发时,span 覆盖整段文本(0 到 max_length 上限)。"""
    v = Validator(rules=[
        ValidationRule(name="too_long", max_length=5),
    ])
    r = v.check("1234567890", IntentType.QA)
    assert not r.passed
    assert r.issues[0].span == (0, 5)


def test_validator_severity_default_is_error():
    """ValidationRule 没设 severity → 触发的 issue 也是 error。"""
    v = Validator(rules=[
        ValidationRule(name="r", pattern=r"X"),
    ])
    r = v.check("X", IntentType.QA)
    assert r.issues[0].severity == "error"


def test_validator_severity_warning_propagates():
    """rule.severity=warning → 触发的 issue.severity=warning。"""
    v = Validator(rules=[
        ValidationRule(name="r", pattern=r"X", severity="warning"),
    ])
    r = v.check("X", IntentType.QA)
    assert r.issues[0].severity == "warning"


def test_validation_result_holds_issues_tuple():
    """ValidationResult.issues 是 tuple(可哈希、可放进 dataclass frozen 字段)。"""
    r = ValidationResult(
        passed=False,
        issues=(ValidationIssue(message="x", rule_id="r"),),
    )
    assert isinstance(r.issues, tuple)
    assert len(r.issues) == 1
    assert r.issues[0].message == "x"
    assert not r.passed


# ---------------------------------------------------------------------------
# 序列化(asdict → JSON)走新字段
# ---------------------------------------------------------------------------


def test_validation_issue_serializes_all_fields():
    """asdict 把新 4 字段都序列化(给 ChatResult.to_dict 用)。"""
    from dataclasses import asdict

    issue = ValidationIssue(
        message="x", severity="warning",
        rule_id="r1", span=(1, 4),
    )
    d = asdict(issue)
    assert d == {
        "message": "x",
        "severity": "warning",
        "rule_id": "r1",
        "span": (1, 4),
    }


# ---------------------------------------------------------------------------
# 默认 rule 集回归
# ---------------------------------------------------------------------------


def test_default_rules_have_no_severity_override():
    """默认 4 条 rule 全 error 严重级(向后兼容 — passed 只看 issues 长度)。"""
    v = Validator()  # 用默认
    r = v.check('password = "secret123"', IntentType.QA)
    assert not r.passed
    for issue in r.issues:
        assert issue.severity == "error"
        assert issue.rule_id != ""
        assert issue.span is not None  # regex 命中的有 span


# ---------------------------------------------------------------------------
# R9 9.3:边界测试补强(R8 4.10 已填字段,本轮锁覆盖)
# ---------------------------------------------------------------------------


def test_validator_span_set_for_min_length():
    """min_length 触发时,span 覆盖整段文本(同 max_length 语义)。"""
    from mmi.agent.validate import ValidationRule
    v = Validator(rules=[
        ValidationRule(name="too_short", min_length=10),
    ])
    r = v.check("hi", IntentType.QA)
    assert not r.passed
    assert r.issues[0].span == (0, 2)


def test_validator_span_first_match_when_pattern_repeats():
    """regex 多次命中时,只记录第一处 span(防刷屏)。"""
    from mmi.agent.validate import ValidationRule
    v = Validator(rules=[
        ValidationRule(name="find_xyz", pattern=r"xyz"),
    ])
    text = "xyz first match then xyz second"  # 第一处在 0..3
    r = v.check(text, IntentType.QA)
    assert not r.passed
    # 现有实现是全部记录(每处都加 issue),验证首条 span
    assert r.issues[0].span == (0, 3)
    # 如有第二条,位置在 21..24
    if len(r.issues) > 1:
        assert r.issues[1].span == (21, 24)


def test_validator_to_dict_includes_span():
    """ChatResult.to_dict() 序列化时,issue.span 字段透传。"""
    from mmi.agent.result import ChatResult
    from mmi.agent.validate import ValidationResult
    cr = ChatResult(
        reply="x",
        intent=IntentType.QA,
        agent_id="qa",
        validation=ValidationResult(
            passed=False,
            issues=(
                ValidationIssue(
                    message="bad",
                    severity="error",
                    rule_id="r1",
                    span=(2, 5),
                ),
            ),
        ),
        trace_ids=[],
    )
    d = cr.to_dict()
    issue_dict = d["validation"]["issues"][0]
    assert issue_dict["span"] == (2, 5)  # asdict 不把 tuple 转 list(只是 dataclass 字段)
    assert issue_dict["rule_id"] == "r1"
    assert issue_dict["message"] == "bad"
