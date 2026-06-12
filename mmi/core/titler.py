"""mmi.core.titler —— 会话标题生成。

ARCHITECTURE.md §8.2 规则：
  - 时机：10 轮触发一次，20 轮复核
  - 失败兜底：LLM 调用 3 次仍无法生成主题 → 归类 trash
  - 规则：禁止用第一轮 User 消息作为标题（"你好"开场失效）

Phase 2 实现：
  - generate_title()：调 LLM 生成，失败回退到启发式
  - heuristic_title()：基于前 N 轮 user 消息提取关键词
  - 标题长度：英文 3-8 词，中文 6-20 字

故意做成纯函数（不写磁盘），让 manager / 单元测试都好调用。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from .llm import LLMError, LLMProvider

__all__ = [
    "generate_title",
    "heuristic_title",
    "detect_topic_drift",
    "TITLE_MAX_TRIES",
    "TITLE_MIN_WORDS",
    "TITLE_MAX_WORDS",
]


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

TITLE_MAX_TRIES = 3            # §8.2: 失败 3 次仍无法生成 → trash
TITLE_MIN_WORDS = 2            # 低于此数认为是无效标题
TITLE_MAX_WORDS = 12           # 高于此数会被截断

# 英文停用词（heuristic 用）
_EN_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their",
    "and", "or", "but", "if", "so", "as", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "up", "down", "out", "about", "into", "over", "after",
    "this", "that", "these", "those",
    "do", "does", "did", "have", "has", "had", "will", "would", "should", "could",
    "can", "may", "might", "must", "shall",
    "not", "no", "yes", "ok", "okay", "hi", "hello", "hey", "thanks", "thank",
    "what", "when", "where", "why", "how", "who", "which",
    "just", "only", "also", "very", "really", "much", "some", "any", "all",
    "there", "here", "now", "then", "than",
})

# 中文停用词（heuristic 用）
_ZH_STOPWORDS = frozenset({
    "我", "你", "他", "她", "它", "们", "的", "了", "是", "在", "有", "和", "与",
    "或", "但", "就", "也", "都", "还", "已", "将", "要", "能", "会", "可", "让",
    "把", "被", "对", "向", "从", "到", "为", "以", "及", "而", "因", "所以",
    "啊", "吗", "呢", "吧", "哦", "嗯", "呀", "哈", "哎", "啦", "嘛",
    "这", "那", "哪", "谁", "什", "么", "怎", "样", "为", "何",
    "请", "谢", "好", "不", "没", "无", "非",
    "什么", "怎么", "怎样", "为什么", "如何",
    "你好", "hello", "hi",
})


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def generate_title(
    turns: list[dict],
    llm: LLMProvider,
    *,
    language: str = "zh-CN",
) -> str:
    """基于会话内容生成标题。

    流程：
      1. 调 LLM 生成（最多 TITLE_MAX_TRIES 次）
      2. 任一次成功 → 返回
      3. 全部失败 → 回退到启发式

    Args:
        turns: 完整 turn 列表，格式 [{"role": "user"|"assistant", "content": "..."}]
        llm: LLM provider
        language: 输出语言（zh-CN / en-US），影响 LLM prompt 和启发式行为

    Returns:
        非空标题字符串。
    """
    # 至少要有一轮 user 才有意义
    if not turns or not any(t.get("role") == "user" for t in turns):
        return heuristic_title(turns, language=language)

    for _ in range(TITLE_MAX_TRIES):
        try:
            title = _llm_title(turns, llm, language=language)
            cleaned = _clean_title(title, language=language)
            if cleaned and _is_acceptable(cleaned, turns, language=language):
                return cleaned
        except LLMError:
            continue

    # 全部失败：回退启发式；heuristic 也可能产出"原首句"，再做一次兜底检查
    fallback = heuristic_title(turns, language=language)
    if not _is_acceptable(fallback, turns, language=language):
        return "untitled"
    return fallback


def heuristic_title(
    turns: list[dict],
    *,
    language: str = "zh-CN",
) -> str:
    """无 LLM 时的标题启发式。

    策略：
      - 取前 3 条 user 消息
      - 分词 + 去停用词 + 词频统计
      - 取前 3-5 个最高频的词拼成标题
    """
    keywords = extract_keywords(turns, max_turns=3, language=language)
    if not keywords:
        return _truncate_raw(
            next((t.get("content", "") for t in turns if t.get("role") == "user"), ""),
            language=language,
        )
    title = " ".join(list(keywords)[:TITLE_MAX_WORDS])
    return _truncate_words(title, language=language)


def extract_keywords(
    turns: list[dict],
    *,
    max_turns: int = 5,
    language: str = "zh-CN",
) -> set[str]:
    """从 turns 中提取关键词集合（供话题偏移检测用）。

    Args:
        turns: 完整 turn 列表
        max_turns: 最多取前 N 条 user 消息
        language: 语言

    Returns:
        去停用词后的关键词集合。
    """
    user_messages = [
        t.get("content", "") for t in turns
        if t.get("role") == "user"
    ]
    user_messages = user_messages[:max_turns]
    if not user_messages:
        return set()

    text = " ".join(user_messages)
    tokens = _tokenize(text, language=language)
    return set(_filter_stopwords(tokens, language=language))


def detect_topic_drift(
    turns: list[dict],
    *,
    early_window: int = 5,
    recent_window: int = 5,
    threshold: float = 0.3,
    language: str = "zh-CN",
) -> bool:
    """检测话题是否发生偏移。

    策略：
      1. 取前 early_window 条 user 消息作为「原始话题」
      2. 取后 recent_window 条 user 消息作为「当前话题」
      3. 提取两组关键词，计算 Jaccard 相似度
      4. 相似度 < threshold → 认为偏移

    Args:
        turns: 完整 turn 列表
        early_window: 原始话题取前 N 条
        recent_window: 当前话题取后 N 条
        threshold: 相似度阈值（< threshold 认为偏移）
        language: 语言

    Returns:
        True 如果检测到话题偏移。
    """
    if len(turns) < early_window + recent_window:
        return False  # 对话太短，不检测

    early_turns = turns[:early_window]
    recent_turns = turns[-recent_window:]

    early_keywords = extract_keywords(early_turns, max_turns=early_window, language=language)
    recent_keywords = extract_keywords(recent_turns, max_turns=recent_window, language=language)

    if not early_keywords or not recent_keywords:
        return False

    # Jaccard 相似度 = |A ∩ B| / |A ∪ B|
    intersection = len(early_keywords & recent_keywords)
    union = len(early_keywords | recent_keywords)
    similarity = intersection / union if union > 0 else 0.0

    return similarity < threshold


# ---------------------------------------------------------------------------
# 内部：LLM 调用
# ---------------------------------------------------------------------------


def _llm_title(turns: list[dict], llm: LLMProvider, *, language: str) -> str:
    system = _title_system_prompt(language)
    user = _format_turns_for_title(turns)
    return llm.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=64,
        temperature=0.3,
    )


def _title_system_prompt(language: str) -> str:
    if language.startswith("zh"):
        return (
            "你是一个会话标题生成器。规则：\n"
            "1. 用中文输出，3-8 个字（或 2-6 个词）\n"
            "2. 概括会话主题，不要直接复制用户第一句话\n"
            "3. 不要包含标点、引号或前缀如「主题：」\n"
            "4. 只输出标题本身，不要任何解释"
        )
    return (
        "You are a session title generator. Rules:\n"
        "1. Output in English, 3-8 words\n"
        "2. Summarize the topic, do NOT just copy the user's first message\n"
        "3. No punctuation, quotes, or prefixes like 'Topic:'\n"
        "4. Output only the title, no explanation"
    )


def _format_turns_for_title(turns: list[dict]) -> str:
    """把 turns 拼成 user message（控制长度，避免超 token）。"""
    lines: list[str] = []
    for t in turns[:20]:  # 最多前 20 轮
        role = t.get("role", "")
        content = (t.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"User: {content}")
        elif role == "assistant":
            lines.append(f"Assistant: {content}")
    text = "\n".join(lines)
    # 单轮消息过长的，截断到 500 字
    if len(text) > 4000:
        text = text[:4000] + "..."
    return text


# ---------------------------------------------------------------------------
# 内部：标题清洗 / 校验
# ---------------------------------------------------------------------------


def _clean_title(raw: str, *, language: str) -> str:
    """去掉 LLM 输出里的引号、前缀、多余空白。"""
    s = (raw or "").strip()
    # 去掉成对引号
    for q in ('"', "'", "「", "」", "『", "』", "《", "》", "`"):
        s = s.strip(q)
    # 去掉常见前缀
    for prefix in ("Title:", "标题：", "标题:", "Topic:", "主题：", "主题:"):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    # 多余空白
    s = re.sub(r"\s+", " ", s).strip()
    # 去掉结尾的标点
    s = s.rstrip(".,;:!?。,;:!?")
    return s


def _is_acceptable(title: str, turns: list[dict], *, language: str) -> bool:
    """判断标题是否合理（不能太短、不能与第一句 user 完全相同）。"""
    if not title:
        return False
    # 长度：英文按词数，中文按字数
    if language.startswith("zh"):
        if len(title) < 2 or len(title) > 30:
            return False
    else:
        word_count = len(title.split())
        if word_count < TITLE_MIN_WORDS or word_count > TITLE_MAX_WORDS:
            return False

    # §8.2: 禁止与第一轮 user 消息完全相同
    first_user = next(
        (t.get("content", "").strip() for t in turns if t.get("role") == "user"),
        "",
    )
    if first_user and title.lower().strip() == first_user.lower().strip():
        return False
    return True


# ---------------------------------------------------------------------------
# 内部：启发式分词
# ---------------------------------------------------------------------------


def _tokenize(text: str, *, language: str) -> list[str]:
    """简易分词：英文按空格 + 标点；中文按 2-gram + 标点。"""
    # 统一小写
    text = text.lower()
    if language.startswith("zh"):
        return _tokenize_zh(text)
    return _tokenize_en(text)


def _tokenize_en(text: str) -> list[str]:
    # 去掉标点，保留字母数字
    text = re.sub(r"[^\w\s]", " ", text)
    return [t for t in text.split() if len(t) >= 2]


def _tokenize_zh(text: str) -> list[str]:
    # 去掉标点
    text = re.sub(r"[^\w\s一-鿿]", " ", text)
    # 单字噪音大，取 2-gram
    chars = [c for c in text if "一" <= c <= "鿿"]
    if len(chars) < 2:
        return chars
    return [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]


def _filter_stopwords(tokens: Iterable[str], *, language: str) -> list[str]:
    stops = _ZH_STOPWORDS if language.startswith("zh") else _EN_STOPWORDS
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t in stops:
            continue
        if len(t) < 2:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _truncate_words(title: str, *, language: str) -> str:
    if language.startswith("zh"):
        return title[:20]  # 最多 20 字
    words = title.split()
    return " ".join(words[:TITLE_MAX_WORDS])


def _truncate_raw(text: str, *, language: str) -> str:
    """极端情况：全是停用词时，回退到原文前 N 字。"""
    text = text.strip()
    if not text:
        return "untitled"
    if language.startswith("zh"):
        return text[:12] or "untitled"
    return " ".join(text.split()[:TITLE_MAX_WORDS]) or "untitled"