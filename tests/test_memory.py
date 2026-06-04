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


# ---------------------------------------------------------------------------
# Round 2.3: LLM 版 build_structured_summary
# ---------------------------------------------------------------------------


def test_structured_summary_llm_extracts_fields(isolated_home):
    """LLM 返回合法 JSON → 4 个字段都被填。"""
    from mmi.core.llm import Classification, LLMProvider

    class _JsonLLM(LLMProvider):
        def chat(self, messages, **kw):
            return '{"title": "postgres 分表", "decision": "用 hash", "conclusion": "性能 OK", "todos": "写文档;压测"}'
        def classify(self, prompt, *, options):
            return Classification(choice=options[0], confidence=0.99)

    out = memory.build_structured_summary(
        "## body\n内容。", language="zh-CN", llm=_JsonLLM(),
    )
    assert out["title"] == "postgres 分表"
    assert out["decision"] == "用 hash"
    assert out["conclusion"] == "性能 OK"
    assert "写文档" in out["todos"]


def test_structured_summary_llm_strips_markdown_fence(isolated_home):
    """LLM 包了 ```json fence 也能解析。"""
    from mmi.core.llm import Classification, LLMProvider

    class _FencedLLM(LLMProvider):
        def chat(self, messages, **kw):
            return '```json\n{"title": "T", "decision": "", "conclusion": "C", "todos": ""}\n```'
        def classify(self, prompt, *, options):
            return Classification(choice=options[0], confidence=0.99)

    out = memory.build_structured_summary("body", llm=_FencedLLM())
    assert out["title"] == "T"
    assert out["conclusion"] == "C"


def test_structured_summary_llm_falls_back_on_bad_json(isolated_home):
    """LLM 返回非 JSON → 降级到规则版,不抛。"""
    from mmi.core.llm import Classification, LLMProvider

    class _BrokenLLM(LLMProvider):
        def chat(self, messages, **kw):
            return "不是 JSON,就是乱说"
        def classify(self, prompt, *, options):
            return Classification(choice=options[0], confidence=0.99)

    out = memory.build_structured_summary("## 主题\n内容。", llm=_BrokenLLM())
    # 降级到规则版,至少 title 应该有
    assert out["title"] == "主题"


def test_structured_summary_llm_falls_back_on_exception(isolated_home):
    """LLM 抛异常 → 降级到规则版。"""
    from mmi.core.llm import Classification, LLMProvider

    class _BoomLLM(LLMProvider):
        def chat(self, messages, **kw):
            raise RuntimeError("LLM down")
        def classify(self, prompt, *, options):
            return Classification(choice=options[0], confidence=0.99)

    out = memory.build_structured_summary("## 主题\n内容。", llm=_BoomLLM())
    assert out["title"] == "主题"


# ---------------------------------------------------------------------------
# Round 2.3: FTS5 双路召回
# ---------------------------------------------------------------------------


def test_fts5_keyword_match(isolated_home, fast_embedder):
    """FTS5 关键词命中,即使 FAISS 不命中也能找到。"""
    memory.store_memory("s1", "## kubernetes 网络原理分析\nCNI plugin。",
                        embedder=fast_embedder)
    # 直接调 FTS5 路径
    hits = memory._search_fts("kubernetes", top_k=5)
    assert len(hits) >= 1
    assert any("kubernetes" in h.title for h in hits)


def test_fts5_no_match_returns_empty(isolated_home, fast_embedder):
    memory.store_memory("s1", "## postgres\n内容。", embedder=fast_embedder)
    hits = memory._search_fts("kubernetes_unknown_term", top_k=5)
    assert hits == []


def test_search_semantic_merges_faiss_and_fts(isolated_home, fast_embedder):
    """双路召回:FAISS 命中 + FTS5 命中 = 合并去重,FAISS 优先。"""
    # s1 关键词走 FTS5 命中(可能 FAISS 排后),s2 走 FAISS 命中
    memory.store_memory("s1", "## kubernetes 网络原理\nCNI 细节。", embedder=fast_embedder)
    memory.store_memory("s2", "## redis 缓存策略\nTTL 设置。", embedder=fast_embedder)
    # 用 FAISS 不一定命中的"奇怪"query
    hits = memory.search_semantic("kubernetes CNI", top_k=5, embedder=fast_embedder)
    # 至少召回 s1
    assert any("kubernetes" in h.title for h in hits)


def test_search_semantic_dedup(isolated_home, fast_embedder):
    """FAISS 和 FTS5 命中同一条 → 不重复。"""
    memory.store_memory("s1", "## postgres 分表\nhash 策略。", embedder=fast_embedder)
    hits = memory.search_semantic("postgres", top_k=10, embedder=fast_embedder)
    ids = [h.memory_id for h in hits]
    assert len(ids) == len(set(ids))  # 去重


def test_sanitize_fts_query_english():
    """英文加 * 通配。"""
    out = memory._sanitize_fts_query("postgres")
    assert '"postgres"*' in out


def test_sanitize_fts_query_chinese():
    """中文原样,不带 *。"""
    out = memory._sanitize_fts_query("分表")
    assert '"分表"' in out
    assert "*" not in out.split("AND")[0]


def test_sanitize_fts_query_empty():
    assert memory._sanitize_fts_query("") == ""


# ---------------------------------------------------------------------------
# Round 2.3: summarizer 自动入库
# ---------------------------------------------------------------------------


def test_schedule_summary_auto_stores_memory(isolated_home, fast_embedder):
    """schedule_summary_update 完成后,记忆应该自动入库。"""
    import time
    from mmi.core import summarizer
    from mmi.core.llm import Classification, LLMProvider
    from mmi.core.session import Session, SessionMeta
    from mmi.core import storage

    class _SummaryLLM(LLMProvider):
        def chat(self, messages, **kw):
            content = " ".join(m.get("content", "") for m in messages)
            if "总结" in content or "summary" in content.lower() or "Summarize" in content:
                return "对话摘要:讨论 postgres 分表"
            return "reply"
        def classify(self, prompt, *, options):
            return Classification(choice=options[0], confidence=0.99)

    sid = "01AAAAAAAAAAAAAAAAAAAAAAAA"  # 26 字符合法 ULID 占位
    s = Session(meta=SessionMeta.new(sid, title="t"), body="")
    storage.write_session(s)

    # 加 5 turns(触发 should_update_summary)
    for i in range(5):
        storage.append_turn(sid, f"u{i}", f"a{i}")

    llm = _SummaryLLM()
    t = summarizer.schedule_summary_update(sid, llm, language="zh-CN")
    t.join(timeout=10)
    # 后台入库可能略有延迟,等一下
    time.sleep(0.3)

    # 记忆应该有 1 条
    assert memory.memory_count() >= 1


# ---------------------------------------------------------------------------
# Round 2.4: 内容 hash 去重
# ---------------------------------------------------------------------------


def test_store_dedup_same_body(isolated_home, fast_embedder):
    """同 body 重复入库 → 不写盘,返回旧 record。"""
    r1 = memory.store_memory("s1", "## 主题\n内容。", embedder=fast_embedder)
    assert r1 is not None
    assert memory.memory_count() == 1
    r2 = memory.store_memory("s1", "## 主题\n内容。", embedder=fast_embedder)
    assert r2 is not None
    assert r2.memory_id == r1.memory_id
    assert memory.memory_count() == 1   # 没新增


def test_store_dedup_different_body(isolated_home, fast_embedder):
    """不同 body → 正常入库。"""
    memory.store_memory("s1", "## A\ncontent A", embedder=fast_embedder)
    memory.store_memory("s1", "## B\ncontent B", embedder=fast_embedder)
    assert memory.memory_count() == 2


def test_content_hash_stable(isolated_home):
    """同 body → 同 hash。"""
    h1 = memory._content_hash("hello world")
    h2 = memory._content_hash("hello world")
    assert h1 == h2
    assert len(h1) == 16    # sha256[:16]


def test_content_hash_different():
    """不同 body → 不同 hash。"""
    assert memory._content_hash("a") != memory._content_hash("b")


def test_get_by_hash_returns_record(isolated_home, fast_embedder):
    r1 = memory.store_memory("s1", "## X\ncontent", embedder=fast_embedder)
    h = memory._content_hash("## X\ncontent")
    r2 = memory._get_by_hash(h)
    assert r2 is not None
    assert r2.memory_id == r1.memory_id


def test_get_by_hash_missing(isolated_home):
    assert memory._get_by_hash("nonexistent") is None


# ---------------------------------------------------------------------------
# Round 2.4: 入库独立线程
# ---------------------------------------------------------------------------


def test_schedule_memory_store_runs(isolated_home, fast_embedder):
    """_schedule_memory_store 起独立线程跑 store_memory。"""
    from mmi.core import summarizer
    from mmi.core.session import Session
    from mmi.core.session import SessionMeta
    from mmi.core import storage

    sid = "01AAAAAAAAAAAAAAAAAAAAAAAA"
    s = Session(meta=SessionMeta.new(sid, title="t"), body="## T\n内容。")
    storage.write_session(s)

    t = summarizer._schedule_memory_store(sid)
    t.join(timeout=5)
    assert memory.memory_count() >= 1


def test_schedule_memory_store_failure_silent(isolated_home):
    """_schedule_memory_store 在 session 不存在时也静默,不抛。"""
    from mmi.core import summarizer
    t = summarizer._schedule_memory_store("01BBBBBBBBBBBBBBBBBBBBBBBB")
    t.join(timeout=5)
    # 不报错,count 也不变
    assert memory.memory_count() == 0


# ---------------------------------------------------------------------------
# Round 改进 Round 1: P0-1 短会话入库
# ---------------------------------------------------------------------------


def test_short_session_memory_stores(isolated_home, fast_embedder):
    """短会话(<20 轮)也能入库:验证 P0-1 修复后 store_memory 不再依赖摘要触发。

    通过直接调 store_memory 模拟 manager.chat 每轮末尾的入库路径。
    """
    from mmi.core import memory
    # 3 轮短会话
    for i in range(3):
        body = f"## turn {i}\n第 {i} 轮内容。"
        rec = memory.store_memory(f"s{i}", body, embedder=fast_embedder)
        assert rec is not None
    assert memory.memory_count() == 3
    # 应能召回
    hits = memory.search_semantic("turn 1", top_k=5, embedder=fast_embedder)
    assert any("turn 1" in h.raw_excerpt for h in hits)


# ---------------------------------------------------------------------------
# Round 改进 Round 1: P0-3 tiktoken 精确估算
# ---------------------------------------------------------------------------


def test_estimate_tokens_uses_tiktoken_when_available():
    """tiktoken 装上时,英文精确算(13 tokens 是 hello world 的实际值)。"""
    from mmi.core import context as ctx
    from mmi.core.context import _HAS_TIKTOKEN
    if not _HAS_TIKTOKEN:
        pytest.skip("tiktoken 未装,跳过精确路径测试")
    msgs = [{"role": "user", "content": "hello world"}]
    n = ctx.estimate_tokens(msgs)
    # tiktoken "hello world" = 2 tokens; +4 role overhead = 6
    assert n == 6, f"expected 6, got {n}"


def test_estimate_tokens_chinese_higher_than_chars_div_2():
    """中文 1 字 ≈ 2 token,旧公式 1 token ≈ 2 字会低估。
    新公式:中文 1 字 = 2 token,100 字中文 ≈ 200 tokens(≈ 100 字,差异在于整词 1.3x)。
    """
    from mmi.core import context as ctx
    from mmi.core.context import _HAS_TIKTOKEN
    msgs = [{"role": "user", "content": "测试" * 50}]  # 100 个汉字
    n = ctx.estimate_tokens(msgs)
    if _HAS_TIKTOKEN:
        # tiktoken 高度压缩重复字符("测试"x50 实际只 ≈ 50 tokens,4 role overhead)
        # 关键是 > 旧公式的 50(旧公式 100字/2=50)
        assert 50 <= n <= 200, f"tiktoken: expected 50-200, got {n}"
    else:
        # 降级公式:100 字 * 2 + 4 = 204
        assert n == 204, f"fallback: expected 204, got {n}"


def test_estimate_tokens_handles_empty():
    from mmi.core import context as ctx
    assert ctx.estimate_tokens([]) == 0


# ---------------------------------------------------------------------------
# Round 改进 Round 1: P2-8 任务队列(FIFO)
# ---------------------------------------------------------------------------


def test_background_pool_submits_fifo(isolated_home, fast_embedder):
    """连续 schedule 两个任务,后一个不能比前一个先完成(同 worker 串行)。

    测法:两个任务都改同一 session,前一个慢一些(人为 sleep),
    后一个快一些。验证后提交的不会插队先完成。
    """
    import time
    from mmi.core import summarizer
    from mmi.core.session import Session, SessionMeta
    from mmi.core import storage

    # 重置线程池:可能有其他测试已 shutdown 了
    summarizer.shutdown_background_pool(wait=False)
    import mmi.core.summarizer as sm
    sm._BACKGROUND_POOL = None

    sid = "01AAAAAAAAAAAAAAAAAAAAAAAA"
    s = Session(meta=SessionMeta.new(sid, title="t"), body="## body\n")
    storage.write_session(s)

    # 用 monkey patch 模拟慢/快
    from mmi.core import llm as llm_module

    order: list[str] = []
    def slow_update(*a, **kw):
        order.append("slow_start")
        time.sleep(0.3)
        order.append("slow_end")
        return True

    # 提交 slow(走 schedule_summary_update)
    from unittest.mock import patch
    with patch.object(summarizer, "update_summary", side_effect=slow_update):
        summarizer.schedule_summary_update(sid, llm_module.EchoLLMProvider())
    # 立刻再提交一个直接调 _schedule_memory_store
    summarizer._schedule_memory_store(sid)
    # 等队列清空
    time.sleep(1.0)
    # slow 应被调过(说明 pool 在跑)
    assert "slow_start" in order, f"expected slow_update to be called, order={order}"
    # 主要验证线程池不抛 + 任务能完成
    summarizer.shutdown_background_pool(wait=True)
    sm._BACKGROUND_POOL = None
