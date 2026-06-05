"""mmi.core.classifier —— 杂项识别。

ARCHITECTURE.md §8.1：
  1. 规则预筛（无 LLM）：< 3 轮 **且** < 200 字符 → 直接 trash
  2. LLM 二次确认：3-20 轮时问 LLM；置信度 < 0.6 → trash
  3. > 20 轮 → IS_REAL（不再判定）
  4. LLM 失败 → 默认 IS_REAL（保守，不要因为 LLM 挂了误删）

调用方（manager）拿到 verdict 后决定是否移到 trash。
本模块纯函数，不写磁盘。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .llm import LLMError, LLMProvider

__all__ = [
    "Verdict",
    "ClassificationResult",
    "classify_session",
    "is_trash",
    "RULE_MAX_TURNS",
    "RULE_MAX_CHARS",
    "LLM_MIN_TURNS",
    "LLM_MAX_TURNS",
    "CONFIDENCE_THRESHOLD",
]


# ---------------------------------------------------------------------------
# 常量 / 类型
# ---------------------------------------------------------------------------


class Verdict(str, Enum):
    """判定结果。"""

    IS_TRASH = "trash"        # 应该移到 trash
    IS_REAL = "real"          # 是正经会话，保留
    UNKNOWN = "unknown"        # 拿不准（供调试，调用方应按 IS_REAL 处理）


RULE_MAX_TURNS = 3            # §8.1: < 3 轮
RULE_MAX_CHARS = 200          # §8.1: < 200 字符
LLM_MIN_TURNS = 3             # §8.1: 3-20 轮时调 LLM
LLM_MAX_TURNS = 20
CONFIDENCE_THRESHOLD = 0.6    # §8.1: 置信度 < 0.6 → trash


@dataclass
class ClassificationResult:
    """classify_session 的结果。"""

    verdict: Verdict
    reason: str                # 人类可读原因
    confidence: float = 1.0    # 0.0 - 1.0
    method: str = "rule"        # "rule" | "llm" | "default"


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def classify_session(
    turns: list[dict],
    llm: LLMProvider,
    *,
    language: str = "zh-CN",
) -> ClassificationResult:
    """判定一个会话是否杂项。

    Args:
        turns: 完整 turn 列表，格式 [{"role": "user"|"assistant", "content": ...}, ...]
        llm: LLM provider（仅 3-20 轮时才用）
        language: 输出语言

    Returns:
        ClassificationResult，verdict 是 IS_TRASH / IS_REAL / UNKNOWN
    """
    n_user = sum(1 for t in turns if t.get("role") == "user")
    total_chars = sum(len(t.get("content", "") or "") for t in turns)

    # Rule 1: 规则预筛（< 3 轮 AND < 200 字符）
    if n_user < RULE_MAX_TURNS and total_chars < RULE_MAX_CHARS:
        return ClassificationResult(
            verdict=Verdict.IS_TRASH,
            reason=(
                f"rule: {n_user} user turn(s), {total_chars} chars "
                f"(< {RULE_MAX_TURNS} turns AND < {RULE_MAX_CHARS} chars)"
            ),
            confidence=1.0,
            method="rule",
        )

    # Rule 3: > 20 轮 → IS_REAL
    if n_user > LLM_MAX_TURNS:
        return ClassificationResult(
            verdict=Verdict.IS_REAL,
            reason=f"rule: {n_user} user turns (> {LLM_MAX_TURNS}, assumed real)",
            confidence=1.0,
            method="rule",
        )

    # 不在 3-20 轮范围但也不在 rule 1 / rule 3 范围：1-2 轮但 chars >= 200
    # 默认 IS_REAL（保守：长消息说明用户在认真写）
    if n_user < LLM_MIN_TURNS:
        return ClassificationResult(
            verdict=Verdict.IS_REAL,
            reason=(
                f"rule: {n_user} user turns, {total_chars} chars "
                f"(< {LLM_MIN_TURNS} but long enough, assumed real)"
            ),
            confidence=0.7,
            method="rule",
        )

    # Rule 2: 3-20 轮 → LLM
    try:
        result = llm.classify(
            _build_prompt(turns, language=language),
            options=["yes", "no"],
        )
        if result.choice == "no":
            return ClassificationResult(
                verdict=Verdict.IS_TRASH,
                reason=(
                    f"llm: choice={result.choice}, "
                    f"confidence={result.confidence:.2f} "
                    f"(threshold {CONFIDENCE_THRESHOLD})"
                ),
                confidence=result.confidence,
                method="llm",
            )
        # choice == "yes": LLM 判为正经会话；即使置信度偏低也保留（不要误删活跃会话）
        if result.confidence < CONFIDENCE_THRESHOLD:
            return ClassificationResult(
                verdict=Verdict.IS_REAL,
                reason=(
                    f"llm: choice={result.choice}, "
                    f"confidence={result.confidence:.2f} "
                    f"(below threshold {CONFIDENCE_THRESHOLD}, "
                    f"but choice=yes so keeping)"
                ),
                confidence=result.confidence,
                method="llm",
            )
        return ClassificationResult(
            verdict=Verdict.IS_REAL,
            reason=f"llm: choice={result.choice}, confidence={result.confidence:.2f}",
            confidence=result.confidence,
            method="llm",
        )
    except LLMError as e:
        # 保守：LLM 失败 → IS_REAL
        return ClassificationResult(
            verdict=Verdict.IS_REAL,
            reason=f"llm failed, defaulting to real: {e}",
            confidence=0.0,
            method="default",
        )


def is_trash(result: ClassificationResult) -> bool:
    """便利函数：verdict 是不是 IS_TRASH。"""
    return result.verdict == Verdict.IS_TRASH


# ---------------------------------------------------------------------------
# 内部：prompt 构造
# ---------------------------------------------------------------------------


def _build_prompt(turns: list[dict], *, language: str) -> str:
    """给 LLM 的分类 prompt。"""
    user_msgs = [t.get("content", "") for t in turns if t.get("role") == "user"]
    # 控制总长度
    conversation = "\n".join(f"- {msg[:300]}" for msg in user_msgs[:10])

    if language.startswith("zh"):
        return (
            "判断下面的多轮对话是否在讨论一个具体的主题 / 项目 / 问题。\n"
            "如果只是寒暄（你好 / 天气 / 笑话 / 随口问的琐事），回答 no。\n"
            "如果在认真讨论一个具体话题（代码 / 写作 / 学习 / 设计 / 决策），回答 yes。\n\n"
            f"对话内容：\n{conversation}\n\n"
            "只回答 yes 或 no。"
        )
    return (
        "Determine whether the following multi-turn conversation is discussing a "
        "specific topic / project / question.\n"
        "If it's just chitchat (greetings, weather, jokes, casual small talk), answer no.\n"
        "If it's a real discussion of a concrete topic (code, writing, learning, design, "
        "decision), answer yes.\n\n"
        f"Conversation:\n{conversation}\n\n"
        "Answer only yes or no."
    )