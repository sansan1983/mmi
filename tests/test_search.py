"""tests/test_search.py —— core.search 单元测试。

覆盖：
  - tokenize 英文 / 中文 / 停用词
  - score_turns 排序
  - search_top_k 命中 / 不命中 / 空 query / 完整轮配对
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core import search  # noqa: E402


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------


def test_tokenize_empty():
    assert search.tokenize("") == []
    assert search.tokenize(None) == []  # type: ignore[arg-type]


def test_tokenize_en_filters_stopwords():
    toks = search.tokenize("I am the best programmer in the world", language="en-US")
    # 停用词被过滤：am / the / in / I 都不应该出现
    for t in toks:
        assert t not in {"am", "the", "in", "i"}
    assert "programmer" in toks
    assert "world" in toks


def test_tokenize_zh_uses_jieba_or_bigrams():
    toks = search.tokenize("我在写一个 Python 爬虫", language="zh-CN")
    # 装了 jieba 应该是 jieba 切词(可能含"爬虫"作为整体)
    # 降级(2-gram)应该含 "爬虫"
    if search._HAS_JIEBA:
        # jieba 切词后 "爬虫" 应作为单 token 出现
        assert "爬虫" in toks
    else:
        # 2-gram 模式
        assert "爬虫" in toks
    # 停用字不会单独出现(被过滤);在 jieba 模式下长度可能为 1
    if not search._HAS_JIEBA:
        assert all(len(t) >= 2 for t in toks)


def test_tokenize_zh_filters_stopwords():
    """停用词(我/的/了)不出现。"""
    toks = search.tokenize("我的项目方案", language="zh-CN")
    # 停用字"我"和"的"不应出现
    assert "我" not in toks
    assert "的" not in toks
    # 内容词"项目"应出现
    assert "项目" in toks or "项" in toks


def test_tokenize_zh_no_jieba_falls_back_to_bigrams(monkeypatch):
    """模拟 jieba 不可用 → 2-gram fallback 仍能用。"""
    monkeypatch.setattr(search, "_HAS_JIEBA", False)
    toks = search.tokenize("分表策略", language="zh-CN")
    # 2-gram 模式:chars < 2 时直接返 chars;>= 2 时 2-gram
    assert "分表" in toks
    assert "表策" in toks
    # 所有 token 长度 >= 2
    assert all(len(t) >= 2 for t in toks)


def test_tokenize_dedup_preserves_order():
    toks = search.tokenize("postgres postgres redis", language="en-US")
    assert toks == ["postgres", "redis"]


# ---------------------------------------------------------------------------
# score_turns
# ---------------------------------------------------------------------------


def test_score_turns_empty():
    assert search.score_turns([], "x") == []
    assert search.score_turns([{"role": "user", "content": "x"}], "") == []


def test_score_turns_no_match():
    turns = [
        {"role": "user", "content": "what is the weather today"},
    ]
    assert search.score_turns(turns, "kubernetes") == []


def test_score_turns_returns_sorted_desc():
    turns = [
        {"role": "user", "content": "how to design postgres sharding"},
        {"role": "assistant", "content": "use hash sharding for postgres"},
        {"role": "user", "content": "what about redis caching"},
    ]
    scored = search.score_turns(turns, "postgres sharding", language="en-US")
    assert len(scored) == 2  # redis 那条不命中
    # 倒序
    assert scored[0][1] >= scored[1][1]


# ---------------------------------------------------------------------------
# search_top_k
# ---------------------------------------------------------------------------


def test_search_top_k_empty_inputs():
    assert search.search_top_k([], "x") == []
    assert search.search_top_k([{"role": "user", "content": "x"}], "") == []


def test_search_top_k_returns_full_round_for_user_match():
    """user turn 命中时，把紧随的 assistant 也带上。"""
    turns = [
        {"role": "user", "content": "how to design postgres sharding"},
        {"role": "assistant", "content": "use hash sharding"},
        {"role": "user", "content": "what about redis"},
        {"role": "assistant", "content": "use redis for cache"},
    ]
    hits = search.search_top_k(turns, "postgres sharding", k=1)
    # 应返回 user + assistant 一对
    assert len(hits) == 2
    assert hits[0]["role"] == "user"
    assert hits[1]["role"] == "assistant"
    assert "postgres" in hits[0]["content"]


def test_search_top_k_returns_full_round_for_assistant_match():
    """assistant turn 命中时，把前面的 user 也带上。"""
    turns = [
        {"role": "user", "content": "what is a good database"},
        {"role": "assistant", "content": "postgres is great"},
    ]
    hits = search.search_top_k(turns, "postgres", k=1)
    # 应返回 user + assistant 一对
    assert len(hits) == 2
    assert hits[0]["role"] == "user"
    assert "database" in hits[0]["content"]


def test_search_top_k_respects_k():
    turns = []
    for i in range(10):
        turns.append({"role": "user", "content": f"postgres topic {i}"})
        turns.append({"role": "assistant", "content": f"postgres reply {i}"})
    # 10 个 user + 10 个 assistant = 10 轮
    hits = search.search_top_k(turns, "postgres", k=3)
    # 3 轮 = 6 条（user+assistant 各 3）
    assert len(hits) == 6
    # 都是 postgres 相关
    assert all("postgres" in t["content"] for t in hits)


def test_search_top_k_preserves_original_order():
    """命中段按原文顺序输出，不按 score 顺序。"""
    turns = [
        {"role": "user", "content": "earlier turn about redis"},
        {"role": "assistant", "content": "ok redis is fast"},
        {"role": "user", "content": "postgres sharding question"},
        {"role": "assistant", "content": "use hash sharding"},
    ]
    hits = search.search_top_k(turns, "redis postgres", k=2)
    # 应该按原顺序：redis pair 在前，postgres pair 在后
    contents = [t["content"] for t in hits]
    redis_idx = next(i for i, c in enumerate(contents) if "redis" in c and "earlier" in c)
    postgres_idx = next(i for i, c in enumerate(contents) if "postgres" in c and "sharding question" in c)
    assert redis_idx < postgres_idx


# ---------------------------------------------------------------------------
# fuzzy_match_scores（Phase 6 P2 #12）
# ---------------------------------------------------------------------------


def test_fuzzy_match_scores_basic():
    """基本 fuzzy 匹配：相近标题命中，乱写的不命中。"""
    items = [
        {"title": "postgres sharding design"},
        {"title": "redis caching strategy"},
        {"title": "kubernetes networking deep dive"},
    ]
    scored = search.fuzzy_match_scores(
        items, "postgres", key=lambda x: x["title"], threshold=60,
    )
    assert len(scored) >= 1
    # postgres 标题应当排第一
    assert "postgres" in scored[0][1]["title"]


def test_fuzzy_match_scores_empty_query():
    """空 query → 空列表。"""
    items = [{"title": "anything"}]
    assert search.fuzzy_match_scores(items, "", key=lambda x: x["title"]) == []


def test_fuzzy_match_scores_threshold():
    """阈值 100 时只有完全匹配才被返回。"""
    items = [{"title": "hello"}, {"title": "world"}]
    scored = search.fuzzy_match_scores(
        items, "hello", key=lambda x: x["title"], threshold=100,
    )
    assert len(scored) == 1
    assert scored[0][1]["title"] == "hello"


def test_fuzzy_match_scores_no_rapidfuzz(monkeypatch):
    """rapidfuzz 不可用 → 返回空列表（静默退化）。"""
    import sys
    # 强制 rapidfuzz import 失败
    monkeypatch.setitem(sys.modules, "rapidfuzz", None)
    monkeypatch.setitem(sys.modules, "rapidfuzz.fuzz", None)
    items = [{"title": "anything"}]
    scored = search.fuzzy_match_scores(items, "anything", key=lambda x: x["title"])
    assert scored == []


def test_fuzzy_match_scores_sorted_desc():
    """返回列表按 score 倒序。"""
    items = [
        {"title": "completely unrelated xyz"},
        {"title": "postgres sharding"},
    ]
    scored = search.fuzzy_match_scores(
        items, "postgres", key=lambda x: x["title"], threshold=10,
    )
    # 至少 2 个命中（threshold=10 很低）
    assert len(scored) >= 1
    # 第一个 score >= 第二个 score
    for i in range(len(scored) - 1):
        assert scored[i][0] >= scored[i + 1][0]
