"""tests/test_classifier.py —— core.classifier 单元测试。

覆盖：
  - Rule 1：< 3 轮 + < 200 字符 → IS_TRASH
  - Rule 2：3-20 轮 LLM 判定（yes/no + 置信度阈值 0.6）
  - Rule 3：> 20 轮 → IS_REAL
  - 边界：1-2 轮但 chars >= 200 → IS_REAL（保守）
  - LLM 失败 → 默认 IS_REAL（保守）
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core.classifier import (  # noqa: E402
    CONFIDENCE_THRESHOLD,
    ClassificationResult,
    LLM_MAX_TURNS,
    RULE_MAX_CHARS,
    RULE_MAX_TURNS,
    Verdict,
    classify_session,
    is_trash,
)
from mmi.core.llm import LLMError, LLMProvider  # noqa: E402


# ---------------------------------------------------------------------------
# Stub LLM：可预设 classify 返回
# ---------------------------------------------------------------------------


class _StubLLM(LLMProvider):
    def __init__(self, choice="yes", confidence=0.99):
        self.name = "stub"
        self._choice = choice
        self._confidence = confidence
        self.fail_with: Exception | None = None
        self.calls: int = 0

    def chat(self, messages, **kw):
        raise LLMError("not used in classifier tests")

    def classify(self, prompt, *, options):
        self.calls += 1
        if self.fail_with:
            raise self.fail_with
        from mmi.core.llm import Classification
        return Classification(self._choice, self._confidence)


def _turns(user_msgs: list[str], assistant_msgs: list[str] | None = None) -> list[dict]:
    """构造多轮 turns。"""
    a = assistant_msgs or ["ack"] * len(user_msgs)
    out = []
    for u, x in zip(user_msgs, a):
        out.append({"role": "user", "content": u})
        out.append({"role": "assistant", "content": x})
    return out


# ---------------------------------------------------------------------------
# Rule 1：< 3 轮 + < 200 字符
# ---------------------------------------------------------------------------


def test_rule1_short_chitchat_trashed():
    llm = _StubLLM()  # 即便 LLM 不会用上
    turns = _turns(["hi", "how are you"])  # 2 user turns, ~15 chars
    r = classify_session(turns, llm)
    assert r.verdict == Verdict.IS_TRASH
    assert r.method == "rule"
    assert r.confidence == 1.0


def test_rule1_one_turn_short_trashed():
    llm = _StubLLM()
    turns = _turns(["hi"])
    r = classify_session(turns, llm)
    assert r.verdict == Verdict.IS_TRASH
    assert r.method == "rule"


def test_rule1_does_not_apply_when_chars_over_threshold():
    llm = _StubLLM(choice="no", confidence=0.99)
    # 2 turns, but 500 chars total（user 写了一大段）
    long_msg = "x" * 500
    turns = _turns([long_msg, "second"])
    r = classify_session(turns, llm)
    # chars >= 200 → rule 1 不适用；2 < 3 → 也不走 LLM
    # 兜底为 IS_REAL
    assert r.verdict == Verdict.IS_REAL


def test_rule1_does_not_apply_when_3_turns_even_if_short():
    llm = _StubLLM(choice="no", confidence=0.99)
    # 3 turns（rule 1 要求 < 3）
    turns = _turns(["hi", "there", "friend"])
    r = classify_session(turns, llm)
    # 3 turns → rule 2（LLM）
    assert llm.calls == 1
    # LLM 返 "no" → IS_TRASH
    assert r.verdict == Verdict.IS_TRASH
    assert r.method == "llm"


# ---------------------------------------------------------------------------
# Rule 2：3-20 轮 LLM 判定
# ---------------------------------------------------------------------------


def test_rule2_llm_says_yes_with_high_confidence_keeps():
    llm = _StubLLM(choice="yes", confidence=0.9)
    turns = _turns([f"topic {i}" for i in range(5)])
    r = classify_session(turns, llm)
    assert r.verdict == Verdict.IS_REAL
    assert r.method == "llm"
    assert r.confidence == 0.9


def test_rule2_llm_says_no_trashes():
    llm = _StubLLM(choice="no", confidence=0.95)
    turns = _turns([f"msg {i}" for i in range(5)])
    r = classify_session(turns, llm)
    assert r.verdict == Verdict.IS_TRASH
    assert r.method == "llm"


def test_rule2_low_confidence_trashes():
    llm = _StubLLM(choice="yes", confidence=0.3)  # < 0.6 阈值
    turns = _turns([f"msg {i}" for i in range(5)])
    r = classify_session(turns, llm)
    assert r.verdict == Verdict.IS_TRASH


def test_rule2_confidence_at_threshold_keeps():
    # 正好 0.6 应该是 >= 0.6 → IS_REAL
    llm = _StubLLM(choice="yes", confidence=CONFIDENCE_THRESHOLD)
    turns = _turns([f"msg {i}" for i in range(5)])
    r = classify_session(turns, llm)
    assert r.verdict == Verdict.IS_REAL


def test_rule2_llm_failure_defaults_to_real():
    llm = _StubLLM()
    llm.fail_with = LLMError("network down")
    turns = _turns([f"msg {i}" for i in range(5)])
    r = classify_session(turns, llm)
    # 保守：LLM 失败 → IS_REAL
    assert r.verdict == Verdict.IS_REAL
    assert r.method == "default"


# ---------------------------------------------------------------------------
# Rule 3：> 20 轮
# ---------------------------------------------------------------------------


def test_rule3_long_session_is_real_without_llm():
    llm = _StubLLM(choice="no", confidence=0.0)  # 即便返 no，也不用
    user_msgs = [f"long conv msg {i}" for i in range(LLM_MAX_TURNS + 1)]  # 21 turns
    turns = _turns(user_msgs)
    r = classify_session(turns, llm)
    assert r.verdict == Verdict.IS_REAL
    assert r.method == "rule"
    assert llm.calls == 0  # LLM 完全没被调


# ---------------------------------------------------------------------------
# is_trash 便利函数
# ---------------------------------------------------------------------------


def test_is_trash_helper():
    assert is_trash(ClassificationResult(Verdict.IS_TRASH, "x")) is True
    assert is_trash(ClassificationResult(Verdict.IS_REAL, "x")) is False


# ---------------------------------------------------------------------------
# 空 turns
# ---------------------------------------------------------------------------


def test_empty_turns_trashed_by_rule1():
    llm = _StubLLM()
    r = classify_session([], llm)
    # 0 turns, 0 chars → rule 1
    assert r.verdict == Verdict.IS_TRASH
