"""mmi.core.memory.store —— 写入记忆(embedding + SQLite + FAISS)。

依赖项:db, faiss, embedder, summary, schema, mmi.core.session。
被依赖:外部 callers(import from mmi.core.memory)。
"""

from __future__ import annotations

# 用模块引用（不是 from import）保证 clear_memories() 重新赋值 _INMEM_INDEX/_INMEM_IDS
# 后,store_memory 仍拿到最新对象。原 from import 拿到 import-time 的旧 binding。
import mmi.core.memory.faiss as _faiss_mod
from mmi.core.memory.db import _db_lock, _get_conn
from mmi.core.memory.embedder import Embedder, get_embedder
from mmi.core.memory.faiss import (
    _INMEM_LOCK,
    _ensure_loaded,
    _maybe_flush,
)
from mmi.core.memory.schema import MemoryRecord, _content_hash
from mmi.core.memory.summary import build_structured_summary
from mmi.core.session import new_session_id, utcnow_iso


def _get_by_hash(content_hash: str) -> MemoryRecord | None:
    """按 content_hash 取 record(去重用)。无则 None。"""
    if not content_hash:
        return None
    with _db_lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT * FROM memories WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        ).fetchone()
    return MemoryRecord.from_row(row) if row else None


def store_memory(
    session_id: str,
    body: str,
    *,
    summary: str = "",
    turns_at: int = 0,
    embedder: Embedder | None = None,
) -> MemoryRecord | None:
    """把一条对话的摘要入库：embedding + SQLite + FAISS。

    Args:
        session_id: 关联的会话 id
        body: 完整 Markdown body（用于 raw_excerpt 兜底和规则摘要）
        summary: 已生成的摘要文本（外部传入；用于 raw_excerpt 兜底）
        turns_at: 该 session 当时的 turn 数
        embedder: 可选外部 embedder（默认走 get_embedder()）

    Returns:
        写入的 MemoryRecord；embedding 失败 / faiss 不可用 → 返回 record 但 vector=None
        且不写 FAISS（SQLite 仍写，检索时降级到 L2 距离不可用时的"无候选"）。
        同 body 重复入库 → 返回旧 record,不再写盘/重算向量（去重）。
    """
    if not body or not body.strip():
        return None
    body_hash = _content_hash(body)
    # 0) 去重：同 hash 已存在 → 返回旧 record
    existing = _get_by_hash(body_hash)
    if existing is not None:
        return existing
    emb = embedder or get_embedder()
    struct = build_structured_summary(body)
    raw_excerpt = (summary or struct["title"] or body)[:300]
    memory_id = new_session_id()    # ULID
    created_at = utcnow_iso()

    # 1) embedding
    text_to_embed = " ".join([
        struct["title"] or "",
        struct["decision"] or "",
        struct["conclusion"] or "",
        raw_excerpt,
    ]).strip() or session_id
    try:
        vector = emb.embed(text_to_embed)
    except Exception:
        vector = []

    # 2) SQLite 写元数据（始终）。FTS5 同步由 _MEMORY_SCHEMA 里的触发器自动处理。
    record = MemoryRecord(
        memory_id=memory_id,
        session_id=session_id,
        created_at=created_at,
        turns_at=turns_at,
        title=struct["title"],
        decision=struct["decision"],
        conclusion=struct["conclusion"],
        todos=struct["todos"],
        raw_excerpt=raw_excerpt,
        content_hash=body_hash,
        vector=vector if vector else None,
    )
    with _db_lock:
        conn = _get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO memories
                (memory_id, session_id, created_at, turns_at,
                 title, decision, conclusion, todos, raw_excerpt, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (record.memory_id, record.session_id, record.created_at, record.turns_at,
             record.title, record.decision, record.conclusion, record.todos, record.raw_excerpt,
             record.content_hash),
        )
        conn.commit()

    # 3) FAISS 写向量(仅在 embedding 成功时) — P2-10 内存池
    if vector:
        try:
            _ensure_loaded(emb.dim)
            with _INMEM_LOCK:
                import numpy as np
                vec = np.array([vector], dtype="float32")
                _faiss_mod._INMEM_INDEX.add(vec)
                _faiss_mod._INMEM_IDS.append(memory_id)
                _faiss_mod._INMEM_DIRTY += 1
            _maybe_flush()  # 阈值外只 dirty,不写盘
        except Exception:
            # FAISS 写失败不阻塞主流程(SQLite 已有 record)
            pass

    return record
