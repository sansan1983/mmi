"""tests/test_memory.py —— core.memory 单元测试。

覆盖：
  - HashEmbedder 确定性 / 维度
  - store_memory: 写 SQLite + FAISS,id 唯一
  - search_semantic: 召回 top-k,空 query / 索引空时降级
  - rerank: 无 LLM 降级顺序保留;有 LLM 按 id 顺序
  - recall_memories: 端到端 search + rerank
  - build_structured_summary: 规则版提取 title / conclusion
  - clear_memories / memory_count: 测试隔离
  - context 集成: LoaderConfig.memory 字段 + compose_messages 注入 recall 段
"""

from __future__ import annotations

import pytest

from mmi.core import memory
from mmi.core.context import LoaderConfig, build_context_detailed
from mmi.core.llm import Classification, LLMProvider
from mmi.core import paths, storage


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    # 强制使用本地假 embedder,避免下载 sentence-transformers 模型
    memory.reset_for_test()
    memory.set_embedder(memory.HashEmbedder())
    memory.clear_memories()
    yield tmp_path
    memory.reset_for_test()


@pytest.fixture
def fast_embedder():
    return memory.HashEmbedder()


# ---------------------------------------------------------------------------
# HashEmbedder
# ---------------------------------------------------------------------------


def test_hash_embedder_dim(fast_embedder):
    assert fast_embedder.dim == 64


def test_hash_embedder_deterministic(fast_embedder):
    """相同文本 → 相同向量。"""
    a = fast_embedder.embed("hello world")
    b = fast_embedder.embed("hello world")
    assert a == b


def test_hash_embedder_distinguishes_text(fast_embedder):
    """不同文本 → 不同向量。"""
    a = fast_embedder.embed("postgres")
    b = fast_embedder.embed("kubernetes")
    assert a != b


def test_hash_embedder_batch(fast_embedder):
    out = fast_embedder.embed_batch(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == 64 for v in out)


# ---------------------------------------------------------------------------
# store_memory
# ---------------------------------------------------------------------------


def test_store_returns_record(isolated_home, fast_embedder):
    rec = memory.store_memory(
        "session-A", "## postgres 分表\n讨论了 hash vs range 策略。",
        summary="postgres 分表策略", turns_at=5, embedder=fast_embedder,
    )
    assert rec is not None
    assert rec.session_id == "session-A"
    assert rec.turns_at == 5
    assert rec.title == "postgres 分表"
    assert rec.memory_id != ""
    assert rec.vector is not None
    assert len(rec.vector) == fast_embedder.dim


def test_store_increments_count(isolated_home, fast_embedder):
    assert memory.memory_count() == 0
    memory.store_memory("s1", "body1", embedder=fast_embedder)
    memory.store_memory("s2", "body2", embedder=fast_embedder)
    memory.store_memory("s3", "body3", embedder=fast_embedder)
    assert memory.memory_count() == 3


def test_store_idempotent_on_same_memory_id(isolated_home, fast_embedder):
    """INSERT OR REPLACE: 同 id 二次写入不重复（但生产里 id 是新生成的,实际不会撞）。"""
    memory.store_memory("s1", "first", embedder=fast_embedder)
    first_count = memory.memory_count()
    memory.store_memory("s1", "second", embedder=fast_embedder)
    # 不同 memory_id,会追加
    assert memory.memory_count() == first_count + 1


def test_store_survives_embed_failure(isolated_home):
    """embed 抛异常时,SQLite 仍写（raw_excerpt 兜底),vector=None。"""

    class BrokenEmbed:
        @property
        def dim(self):
            return 64

        def embed(self, text):
            raise RuntimeError("boom")

        def embed_batch(self, texts):
            raise RuntimeError("boom")

    rec = memory.store_memory("s1", "## topic\ncontent", embedder=BrokenEmbed())
    assert rec is not None
    assert rec.vector is None
    assert memory.memory_count() == 1


# ---------------------------------------------------------------------------
# search_semantic
# ---------------------------------------------------------------------------


def test_search_returns_top_k(isolated_home, fast_embedder):
    for i in range(5):
        memory.store_memory(f"s{i}", f"## 主题{i}\n这是第{i}条内容。", embedder=fast_embedder)
    hits = memory.search_semantic("主题3", top_k=2, embedder=fast_embedder)
    assert len(hits) <= 2
    assert all(hasattr(h, "title") for h in hits)


def test_search_empty_query_returns_empty(isolated_home, fast_embedder):
    memory.store_memory("s1", "body", embedder=fast_embedder)
    assert memory.search_semantic("", embedder=fast_embedder) == []
    assert memory.search_semantic("   ", embedder=fast_embedder) == []


def test_search_empty_index_returns_empty(isolated_home, fast_embedder):
    """没有任何记忆时检索 → 空列表,不报错。"""
    assert memory.search_semantic("anything", embedder=fast_embedder) == []


def test_search_does_not_cross_corrupt(isolated_home, fast_embedder):
    memory.store_memory("s1", "## A\ncontent A", embedder=fast_embedder)
    hits = memory.search_semantic("B", top_k=10, embedder=fast_embedder)
    # 至少能取到 1 条（FAISS 不空 → 召回）
    assert len(hits) >= 1


# ---------------------------------------------------------------------------
# rerank
# ---------------------------------------------------------------------------


def test_rerank_no_llm_preserves_order(isolated_home, fast_embedder):
    """无 LLM → 按原顺序截前 top_n。"""
    memory.store_memory("s1", "## A\n", embedder=fast_embedder)
    memory.store_memory("s2", "## B\n", embedder=fast_embedder)
    memory.store_memory("s3", "## C\n", embedder=fast_embedder)
    cands = memory.search_semantic("query", top_k=10, embedder=fast_embedder)
    out = memory.rerank("query", cands, top_n=2, llm=None)
    assert len(out) == 2
    assert out == cands[:2]


def test_rerank_with_llm_respects_id_order(isolated_home, fast_embedder):
    """有 LLM 时按 LLM 返回的 id 顺序重排。"""

    class _IdOnlyLLM(LLMProvider):
        def __init__(self, ordered_ids):
            self._ids = ordered_ids
        def chat(self, messages, **kw):
            return "id=" + ", id=".join(self._ids)
        def classify(self, prompt, *, options):
            return Classification(choice=options[0], confidence=0.99)

    memory.store_memory("s1", "## A\n", embedder=fast_embedder)
    memory.store_memory("s2", "## B\n", embedder=fast_embedder)
    memory.store_memory("s3", "## C\n", embedder=fast_embedder)
    cands = memory.search_semantic("query", top_k=10, embedder=fast_embedder)
    ids_in = [c.memory_id for c in cands]
    # 倒序要求
    wanted = list(reversed(ids_in))
    llm = _IdOnlyLLM(wanted)
    out = memory.rerank("query", cands, top_n=3, llm=llm)
    assert [c.memory_id for c in out] == wanted


def test_rerank_fills_when_llm_returns_unknown(isolated_home, fast_embedder):
    """LLM 返回的 id 都不在候选里 → 退回原顺序补齐。"""

    class _BogusLLM(LLMProvider):
        def chat(self, messages, **kw):
            return "id=ZZZZZZZZZZZZZZZZZZZZZZZZZZ"  # 26 字符但不在候选里
        def classify(self, prompt, *, options):
            return Classification(choice=options[0], confidence=0.99)

    memory.store_memory("s1", "## A\n", embedder=fast_embedder)
    memory.store_memory("s2", "## B\n", embedder=fast_embedder)
    cands = memory.search_semantic("query", top_k=10, embedder=fast_embedder)
    out = memory.rerank("query", cands, top_n=2, llm=_BogusLLM())
    assert len(out) == 2
    assert {c.memory_id for c in out} == {c.memory_id for c in cands}


# ---------------------------------------------------------------------------
# recall_memories (端到端)
# ---------------------------------------------------------------------------


def test_recall_disabled_returns_empty(isolated_home, fast_embedder):
    memory.store_memory("s1", "## topic\n", embedder=fast_embedder)
    cfg = memory.MemoryConfig(enabled=False)
    assert memory.recall_memories("query", config=cfg, embedder=fast_embedder) == []


def test_recall_returns_at_most_top_n(isolated_home, fast_embedder):
    for i in range(5):
        memory.store_memory(f"s{i}", f"## t{i}\n", embedder=fast_embedder)
    cfg = memory.MemoryConfig(top_k=10, rerank_top_n=2)
    out = memory.recall_memories("query", config=cfg, embedder=fast_embedder, llm=None)
    assert len(out) <= 2


# ---------------------------------------------------------------------------
# build_structured_summary
# ---------------------------------------------------------------------------


def test_structured_summary_extracts_title():
    out = memory.build_structured_summary("## 主题\n一些内容。\n更多内容。")
    assert out["title"] == "主题"
    assert "更多内容" in out["conclusion"]


def test_structured_summary_handles_empty():
    out = memory.build_structured_summary("")
    assert out["title"] == ""
    assert out["conclusion"] == ""


def test_structured_summary_falls_back_to_first_line():
    out = memory.build_structured_summary("没有标题的内容。\n第二行。")
    assert "没有标题" in out["title"]


# ---------------------------------------------------------------------------
# clear / count
# ---------------------------------------------------------------------------


def test_clear_empties(isolated_home, fast_embedder):
    memory.store_memory("s1", "body1", embedder=fast_embedder)
    memory.store_memory("s2", "body2", embedder=fast_embedder)
    assert memory.memory_count() == 2
    memory.clear_memories()
    assert memory.memory_count() == 0
    assert memory.search_semantic("anything", embedder=fast_embedder) == []


# ---------------------------------------------------------------------------
# context 集成
# ---------------------------------------------------------------------------


def test_context_injects_recalled_memories(isolated_home, fast_embedder, monkeypatch):
    """loader 启用 memory 时,系统 prompt 末尾会追加 '相关历史记忆' 段。"""
    # 先存几条记忆
    memory.store_memory("session-old", "## postgres 分表\n讨论了 hash 策略。",
                        summary="postgres 分表策略", embedder=fast_embedder)
    memory.store_memory("session-older", "## redis 缓存\n策略。", embedder=fast_embedder)

    # 写一个空 session
    from mmi.core.session import Session
    sid = "01AAAAAAAAAAAAAAAAAAAAAAAA"
    storage.write_session(Session.empty(sid, title="current"))

    # 强制使用记忆 + 走快速 embedder
    cfg = LoaderConfig(memory=memory.MemoryConfig(enabled=True, top_k=5, rerank_top_n=3))
    ctx = build_context_detailed(sid, "postgres 怎么分表", config=cfg, language="zh-CN")
    # 系统 prompt 末尾应包含"相关历史记忆"
    assert any("相关历史记忆" in m["content"] for m in ctx.messages)
    # 至少召回 1 条
    assert len(ctx.recalled_memories) >= 1


def test_context_memory_disabled_no_inject(isolated_home, fast_embedder):
    """memory.enabled=False → 不注入 recall 段。"""
    memory.store_memory("session-old", "## postgres\n内容。", embedder=fast_embedder)
    from mmi.core.session import Session
    sid = "01AAAAAAAAAAAAAAAAAAAAAAAA"
    storage.write_session(Session.empty(sid, title="x"))

    cfg = LoaderConfig(memory=memory.MemoryConfig(enabled=False))
    ctx = build_context_detailed(sid, "postgres", config=cfg, language="zh-CN")
    assert all("相关历史记忆" not in m["content"] for m in ctx.messages)
    assert ctx.recalled_memories == []


def test_context_memory_failure_does_not_block(isolated_home, fast_embedder, monkeypatch):
    """记忆检索失败时,主流程照常返回 messages。"""
    from mmi.core.session import Session
    sid = "01AAAAAAAAAAAAAAAAAAAAAAAA"
    storage.write_session(Session.empty(sid, title="x"))

    def boom(*a, **kw):
        raise RuntimeError("memory broke")

    monkeypatch.setattr("mmi.core.context.recall_memories", boom)
    cfg = LoaderConfig(memory=memory.MemoryConfig(enabled=True))
    ctx = build_context_detailed(sid, "anything", config=cfg, language="zh-CN")
    # 不抛,且 recalled_memories 留空
    assert ctx.recalled_memories == []
    assert len(ctx.messages) >= 1
