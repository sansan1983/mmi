"""mmi.core.search —— 关键词检索。

ARCHITECTURE.md §6.2 / §9 Phase 3：
  - 基础字符串匹配 + BM25 评分（Phase 3 + 改进 Round 2 升级）
  - fuzzywuzzy / rapidfuzz 模糊匹配（Phase 5 升级）
  - embedding 向量检索（Phase 12 升级，扩展模块）

设计目标：给 loader 找"老但相关"的 turn，让 LLM 看到的不只是最近 N 轮。
不做召回率优化 —— 简单、确定性、零依赖优先。

P0-2（改进 Round 2）：分词升级 + 评分升级
  - 中文走 jieba.cut()（支持自定义词典）
  - 英文按空格切
  - 评分从 TF 改为 BM25（IDF 因子：低频关键词权重更高）
  - jieba 不可用时降级为 2-gram（保持向后兼容）
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from typing import TypeVar

__all__ = [
    "search_top_k",
    "tokenize",
    "score_turns",
    "fuzzy_match_scores",
]

T = TypeVar("T")


# ---------------------------------------------------------------------------
# jieba 懒加载(jieba 装不上时降级到 2-gram)
# ---------------------------------------------------------------------------

try:
    import jieba
    # 静默 jieba 的 "Building prefix dict..." log
    jieba.setLogLevel(20)
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False


# ---------------------------------------------------------------------------
# 分词
# ---------------------------------------------------------------------------


_EN_STOPWORDS = frozenset({
    "a", "an", "the", "is", "am", "are", "was", "were", "be", "been", "being",
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

_ZH_STOPWORDS = frozenset({
    "我", "你", "他", "她", "它", "们", "的", "了", "是", "在", "有", "和", "与",
    "或", "但", "就", "也", "都", "还", "已", "将", "要", "能", "会", "可", "让",
    "把", "被", "对", "向", "从", "到", "为", "以", "及", "而", "因", "所以",
    "啊", "吗", "呢", "吧", "哦", "嗯", "呀", "哈", "哎", "啦", "嘛",
    "这", "那", "哪", "谁", "什", "么", "怎", "样", "何",
    "请", "谢", "好", "不", "没", "无", "非",
    "什么", "怎么", "怎样", "为什么", "如何",
    "你好", "hello", "hi",
})


def tokenize(text: str, *, language: str = "zh-CN") -> list[str]:
    """分词(去停用词,保序去重)。

    英文:转小写 + 去标点 + 空格切 + 停用词过滤
    中文:
      - jieba 装了 → jieba.cut()(支持自定义词典:jieba.load_userdict)
      - jieba 没装 → 降级 2-gram(向后兼容)

    Returns:
        去重保序的 token 列表
    """
    if not text:
        return []
    text = text.lower()
    if language.startswith("zh"):
        return tokenize_zh(text)
    return tokenize_en(text)


def tokenize_en(text: str) -> list[str]:
    text = re.sub(r"[^\w\s]", " ", text)
    seen: set[str] = set()
    out: list[str] = []
    for t in text.split():
        if len(t) < 2:
            continue
        if t in _EN_STOPWORDS:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def tokenize_zh(text: str) -> list[str]:
    text = re.sub(r"[^\w\s一-鿿]", " ", text)
    if _HAS_JIEBA:
        # jieba 模式:精确切词(全模式会有大量无意义 1-gram)
        tokens = list(jieba.cut(text, cut_all=False))
    else:
        # 降级:2-gram(只对 ≥ 2 字 CJK 串)
        chars = [c for c in text if "一" <= c <= "鿿"]
        tokens = chars if len(chars) < 2 else [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        t = t.strip()
        if not t or t in _ZH_STOPWORDS:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


# ---------------------------------------------------------------------------
# 评分:BM25
# ---------------------------------------------------------------------------
#
# BM25 公式(Robertson et al.):
#   score(D, Q) = Σ_{q ∈ Q} IDF(q) * (f(q,D) * (k1 + 1)) / (f(q,D) + k1 * (1 - b + b * |D|/avgdl))
# 其中:
#   f(q,D)  = term q 在文档 D 中的 TF
#   |D|    = 文档 D 的 token 数
#   avgdl  = 语料库平均文档长度
#   k1     = 1.5 (饱和度参数,常用值)
#   b      = 0.75 (长度归一化参数,常用值)
#   IDF(q) = log((N - n(q) + 0.5) / (n(q) + 0.5) + 1)
#   N      = 语料库文档总数
#   n(q)   = 含 term q 的文档数

_BM25_K1 = 1.5
_BM25_B = 0.75


def _bm25_idf(n_q: int, n_docs: int) -> float:
    """BM25 IDF(Robertson-Sparck Jones 变种,带 +1 避免负值)。"""
    return math.log((n_docs - n_q + 0.5) / (n_q + 0.5) + 1.0)


def score_turns(
    turns: list[dict],
    query: str,
    *,
    language: str = "zh-CN",
) -> list[tuple[int, float]]:
    """给每个 turn 打 BM25 分。返回 [(index, score), ...] 按 score 倒序。

    每个 turn 当一篇"文档",query 当"查询",按 BM25 公式算。

    与原 TF 公式的关键区别:低频词权重更高(罕见关键词命中 → 高分),
    长 turn 不靠长度取胜(BM25 的 b 参数做长度归一化)。
    """
    q_tokens = tokenize(query, language=language)
    if not q_tokens or not turns:
        return []

    # 1) 预处理:每个 turn 的 token + 长度
    turn_tokens: list[list[str]] = []
    for t in turns:
        content = (t.get("content") or "").lower()
        toks = tokenize(content, language=language)
        turn_tokens.append(toks)

    n_docs = len(turns)
    avgdl = max(1.0, sum(len(t) for t in turn_tokens) / n_docs)

    # 2) 算每个 query token 的 IDF
    q_idf: dict[str, float] = {}
    for qt in set(q_tokens):
        n_q = sum(1 for toks in turn_tokens if qt in toks)
        q_idf[qt] = _bm25_idf(n_q, n_docs)

    # 3) 给每个 turn 算 BM25 分
    scored: list[tuple[int, float]] = []
    for i, toks in enumerate(turn_tokens):
        if not toks:
            continue
        doc_len = len(toks)
        tf = Counter(toks)
        s = 0.0
        for qt in q_tokens:
            f = tf.get(qt, 0)
            if f == 0:
                continue
            denom = f + _BM25_K1 * (1 - _BM25_B + _BM25_B * doc_len / avgdl)
            s += q_idf.get(qt, 0.0) * (f * (_BM25_K1 + 1)) / denom
        if s > 0:
            scored.append((i, s))

    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored


def _detect_language(text: str) -> str:
    """粗判：含 CJK 字符 → zh-CN，否则 en-US。"""
    for c in text:
        if "一" <= c <= "鿿":
            return "zh-CN"
    return "en-US"


def search_top_k(
    turns: list[dict],
    query: str,
    *,
    k: int = 3,
    language: str | None = None,
) -> list[dict]:
    """按 BM25 评分取前 k 个 turn。

    返回的 turn 包含完整"一轮"（user + assistant 配对）：
      - 如果 user turn 命中，把紧随其后的 assistant turn 也带上
      - 如果 assistant turn 命中，把前一条 user turn 也带上
    这样 LLM 看到 Q + A 完整上下文。

    Args:
        turns: 交替的 [{"role": "user"|"assistant", "content": "..."}, ...]
        query: 查询字符串（通常是当前 user input）
        k: 返回的"轮"数（不是 turn 数，每轮是 user+assistant 1-2 条）
        language: 分词语言；None 时按 query 自动检测

    Returns:
        按相关性倒序的 turn 列表（去重后保序）
    """
    if not turns or not query or k <= 0:
        return []

    if language is None:
        language = _detect_language(query)

    scored = score_turns(turns, query, language=language)
    if not scored:
        return []

    picked_indices: list[int] = []
    for idx, _ in scored:
        if len(picked_indices) >= k * 2:
            break
        if idx in picked_indices:
            continue
        # 把 user 之后 / assistant 之前的同轮伙伴带上
        role = turns[idx].get("role")
        partners: list[int] = []
        if role == "user" and idx + 1 < len(turns) and turns[idx + 1].get("role") == "assistant":
            partners.append(idx + 1)
        elif role == "assistant" and idx - 1 >= 0 and turns[idx - 1].get("role") == "user":
            partners.append(idx - 1)
        picked_indices.append(idx)
        for p in partners:
            if p not in picked_indices:
                picked_indices.append(p)

    # 按原顺序输出
    picked_indices.sort()
    return [turns[i] for i in picked_indices]


# ---------------------------------------------------------------------------
# Fuzzy 匹配（Phase 6 P2 #12：从 TUI 下沉到 core）
# ---------------------------------------------------------------------------


def fuzzy_match_scores(
    items: list[T],
    query: str,
    *,
    key: Callable[[T], str],
    threshold: int = 60,
) -> list[tuple[int, T]]:
    """Fuzzy 匹配：返回 [(score, item), ...] 按 score 倒序。

    使用 rapidfuzz.partial_ratio（未装 rapidfuzz 时返回空列表；通过
    `pip install mmi[fuzzy]` 安装）。

    Args:
        items: 候选列表
        query: 查询字符串
        key: 从 item 提取可搜索文本的函数
        threshold: 分数阈值（0-100），低于阈值的被过滤

    Returns:
        按 score 倒序的 [(score, item), ...]
    """
    if not query:
        return []
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return []
    scored: list[tuple[int, T]] = []
    for item in items:
        text = key(item) or ""
        score = fuzz.partial_ratio(query, text)
        if score >= threshold:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored
