"""Intent classification and sub-agent routing.

3.2 改进:Router.classify 实现规则分类器(关键词 + 长度启发式);
LLM 分类调用接口保留(后续 4.x 接)。
"""

from __future__ import annotations

import re
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mmi.core.llm import LLMProvider


class IntentType(Enum):
    """Broad categories the router can dispatch to.

    Each value maps to one or more registered agents in the pool.
    """

    CODE_REVIEW = auto()
    """Inspect, audit, or refactor source code."""

    DOC_GENERATION = auto()
    """Generate or update documentation."""

    DATA_ANALYSIS = auto()
    """Query, transform, visualise, or summarise data."""

    BRAINSTORM = auto()
    """Creative ideation and divergent thinking."""

    AUDIT = auto()
    """Compliance, security, or logic audit of a given artifact."""

    QA = auto()
    """Question-answering against known context or skills."""

    TOOL_CALL = auto()
    """Execute a registered tool (search, compute, etc.)."""

    UNKNOWN = auto()
    """No confident intent - fall back to default agent."""


# 关键词 → IntentType 映射(优先匹配,中英混合)
_KEYWORD_RULES: list[tuple[re.Pattern[str], IntentType]] = [
    (re.compile(r"代码\s*审查|code\s*review|审查\s*这段|review\s+pr|review\s+this"), IntentType.CODE_REVIEW),
    (re.compile(r"文档|docstring|readme|生成.*文档|写.*文档|翻译"), IntentType.DOC_GENERATION),
    (re.compile(r"数据\s*分析|统计|可视化|聚合|汇总|sql\s*查询|分析\s*一下"), IntentType.DATA_ANALYSIS),
    (re.compile(r"头脑风暴|发散|创意|想\s*更多|brainstorm|ideas?"), IntentType.BRAINSTORM),
    (re.compile(r"审计|合规|安全\s*审查|漏洞|audit|review\s+security"), IntentType.AUDIT),
    (re.compile(r"工具调用|调用工具|run\s+tool|execute\s+tool"), IntentType.TOOL_CALL),
]

# 启发式:超长文本(>500 字符)→ AUDIT(适合审计大段)
_LONG_TEXT_THRESHOLD = 500


class Router:
    """Maps user input to an IntentType and selects the target agent(s).

    Implements a lightweight classifier (keyword + length heuristic) and
    exposes a route() method that returns agent identifiers.
    """

    __slots__ = ("_use_llm", "_llm")

    def __init__(
        self, use_llm: bool = True, llm: LLMProvider | None = None,
    ) -> None:
        """Configure the router.

        Parameters
        ----------
        use_llm : bool
            When True, ambiguous cases may delegate to LLM (3.x 暂不实现,保留 API)。
        llm : LLMProvider, optional
            LLM 实例(use_llm=True 时生效,3.x 阶段传不传都行)。
        """
        self._use_llm = use_llm
        self._llm = llm

    def classify(self, user_message: str) -> IntentType:
        """Return the most likely IntentType for user_message。

        算法(3.2 规则版):
          1. 关键词匹配(中文 + 英文正则,首匹配胜)
          2. 长度启发式:超长文本(>500 字)→ AUDIT
          3. 都没命中 → QA(由路由层 fallback)
        """
        if not user_message or not user_message.strip():
            return IntentType.UNKNOWN

        # 1) 关键词匹配
        text = user_message.lower()
        for pattern, intent in _KEYWORD_RULES:
            if pattern.search(text):
                return intent

        # 2) 长度启发式
        if len(user_message) > _LONG_TEXT_THRESHOLD:
            return IntentType.AUDIT

        # 3) 默认:QA(短问题 / 未知意图都走通用 QA)
        return IntentType.QA

    def route(self, intent: IntentType) -> list[str]:
        """Return ordered list of agent IDs for the given intent.

        Parameters
        ----------
        intent : IntentType
            Classified intent from :meth:`classify`.

        Returns
        -------
        list[str]
            Agent identifiers, ordered by priority (highest first).
        """
        mapping: dict[IntentType, list[str]] = {
            IntentType.CODE_REVIEW:    ["code_review"],
            IntentType.DOC_GENERATION: ["doc"],
            IntentType.DATA_ANALYSIS:  ["data"],
            IntentType.BRAINSTORM:     ["brainstorm"],
            IntentType.AUDIT:          ["code_review"],   # 没 audit Agent 时落到 code_review
            IntentType.QA:             ["qa"],
            IntentType.TOOL_CALL:      ["tool_executor"],
            IntentType.UNKNOWN:        ["qa", "code_review"],
        }
        return mapping.get(intent, ["qa"])
