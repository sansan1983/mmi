"""mmi.core.memory —— 向量语义记忆与跨会话检索(包入口,re-export 所有子模块符号)。

三层记忆架构：
  L1 向量语义记忆 —— embedding → FAISS 语义检索
  L2 结构化摘要记忆 —— LLM生成的 {主题, 决策, 结论, 待办}
  L3 完整原文存储 —— 通过 .session.md 按需加载

检索流程：
  embedding → FAISS top-20 → 加载结构化摘要 → LLM 动态重排 → top-3

存储布局（~/.mmi/）：
  memory.db           — SQLite 存元数据（title/decision/conclusion/todos/raw_excerpt）
  faiss.index         — FAISS 索引文件（只存向量）
  faiss_ids.json      — vector 位置 i → memory_id 的映射（FAISS 不存 id）

设计原则：
  - 失败安全：FAISS / SQLite 任何一步失败 → 静默降级到"无记忆"模式，不阻塞主流程
  - 嵌入器可注入：默认走 sentence-transformers（本地，零 API key），
    测试时可注入 DummyEmbedder
  - 单实例：所有状态在模块级锁内串行访问（FAISS 索引在并发 add/search 下需协调）

子模块结构:
  - schema:     MemoryRecord + MemoryConfig + _content_hash + 常量
  - embedder:   Embedder 协议 + HashEmbedder + SentenceTransformerEmbedder + get/set
  - db:         _MEMORY_SCHEMA + _db_lock + _connect_db + _get_conn
  - faiss:      FAISS 内存池 (P2-10): _INMEM_* + FLUSH_* + load/save
  - summary:    build_structured_summary (LLM + 规则)
  - store:      store_memory (组合)
  - search:     search_semantic (FAISS + FTS5 双路)
  - rerank:     rerank + recall_memories

向后兼容:
  - 之前所有 `from mmi.core.memory import X` / `from .memory import X` 仍工作
  - 模块名仍是 `mmi.core.memory`(从 .py 变成包)
  - `from mmi.core import memory as memory_module` 仍工作
"""

from __future__ import annotations

import contextlib

# ---------------------------------------------------------------------------
# PEP 562: module-level __getattr__ 把 _INMEM_* / _db_lock / _embedder_lock /
# _search_fts / _sanitize_fts_query / _get_by_hash / _content_hash 转发到
# 各自的子模块 global。 原因:`from ... import X` 创建 read-only binding,不追踪
# 原 module global 变化;store_memory() mutate faiss._INMEM_INDEX 后,
# __init__._INMEM_INDEX 仍为旧值。 转发保证 test 用 `memory._INMEM_INDEX` 看到
# faiss 模块当前值。
# ---------------------------------------------------------------------------
import mmi.core.memory.db as _db_mod_re
import mmi.core.memory.embedder as _embedder_mod_re
import mmi.core.memory.faiss as _faiss_mod_re
import mmi.core.memory.schema as _schema_mod_re
import mmi.core.memory.search as _search_mod_re
import mmi.core.memory.store as _store_mod_re
from mmi.core.memory.embedder import (
    Embedder,
    HashEmbedder,
    SentenceTransformerEmbedder,
    get_embedder,
    set_embedder,
)
from mmi.core.memory.faiss import flush_faiss
from mmi.core.memory.rerank import recall_memories, rerank
from mmi.core.memory.schema import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RERANK_TOP_N,
    DEFAULT_TOP_K,
    MemoryConfig,
    MemoryRecord,
)
from mmi.core.memory.search import search_semantic
from mmi.core.memory.store import store_memory
from mmi.core.memory.summary import build_structured_summary


def __getattr__(name: str):
    """按需转发 internal helper 到原始子模块,避免 stale binding。"""
    if name in _FAISS_NAMES:
        return getattr(_faiss_mod_re, name)
    if name in _DB_NAMES:
        return getattr(_db_mod_re, name)
    if name in _EMBEDDER_NAMES:
        return getattr(_embedder_mod_re, name)
    if name in _SEARCH_NAMES:
        return getattr(_search_mod_re, name)
    if name in _STORE_NAMES:
        return getattr(_store_mod_re, name)
    if name in _SCHEMA_NAMES:
        return getattr(_schema_mod_re, name)
    raise AttributeError(f"module 'mmi.core.memory' has no attribute {name!r}")


_FAISS_NAMES = frozenset({
    "_INMEM_INDEX", "_INMEM_IDS", "_INMEM_DIM", "_INMEM_DIRTY",
    "_INMEM_LOADED", "_INMEM_LOCK", "_ensure_loaded", "_save_faiss_index",
})
_DB_NAMES = frozenset({"_db_lock", "_get_conn"})
_EMBEDDER_NAMES = frozenset({"_embedder", "_embedder_lock"})
_SEARCH_NAMES = frozenset({"_search_fts", "_sanitize_fts_query"})
_STORE_NAMES = frozenset({"_get_by_hash"})
_SCHEMA_NAMES = frozenset({"_content_hash"})

__all__ = [
    "MemoryRecord",
    "Embedder",
    "SentenceTransformerEmbedder",
    "HashEmbedder",
    "get_embedder",
    "set_embedder",
    "store_memory",
    "search_semantic",
    "rerank",
    "build_structured_summary",
    "recall_memories",
    "MemoryConfig",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_TOP_K",
    "DEFAULT_RERANK_TOP_N",
    "flush_faiss",
]


# ---------------------------------------------------------------------------
# 公开 API：状态查询 / 清空 / 测试重置(放在 __init__ 集中暴露)
# ---------------------------------------------------------------------------


def memory_count() -> int:
    """当前 SQLite 里的记忆条数（用于 `mmi stat` / 测试断言）。"""
    with _db_mod_re._db_lock:
        conn = _db_mod_re._get_conn()
        row = conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()
        return int(row["n"])


def clear_memories() -> None:
    """清空所有记忆(测试用 / CLI 显式 reset)。"""
    with _db_mod_re._db_lock:
        conn = _db_mod_re._get_conn()
        # FTS5 由触发器自动同步(DELETE on memories 触发 DELETE on memories_fts)
        conn.execute("DELETE FROM memories")
        conn.commit()
    with _faiss_mod_re._INMEM_LOCK:
        # P2-10 内存池:清空,下次 lazy load 重新建空索引
        _faiss_mod_re._INMEM_INDEX = None
        _faiss_mod_re._INMEM_IDS = []
        _faiss_mod_re._INMEM_DIRTY = 0  # noqa: N806
        _faiss_mod_re._INMEM_LOADED = False
        _faiss_mod_re._INMEM_DIM = 0
        # 也清磁盘
        _faiss_mod_re._save_faiss_ids([])
        p = _faiss_mod_re._faiss_index_path()
        if p.exists():
            p.unlink()


def reset_for_test() -> None:
    """关闭并清空 thread-local 连接 + 嵌入器,让下一个测试用新 MMI_HOME。

    仅供测试 / 单测 fixture 使用 —— 不要在生产代码调。
    """
    with _db_mod_re._db_lock:
        tls = getattr(_db_mod_re._get_conn, "_tls", None)
        if tls is not None and getattr(tls, "conn", None) is not None:
            with contextlib.suppress(OSError):
                tls.conn.close()
        _db_mod_re._get_conn._tls = None  # type: ignore[attr-defined]
    with _embedder_mod_re._embedder_lock:
        _embedder_mod_re._embedder = None
