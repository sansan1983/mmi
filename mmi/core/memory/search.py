"""mmi.core.memory.search —— 双路语义检索(FAISS + FTS5) → 去重 → top-k。

依赖项:db, faiss, embedder, schema。
被依赖:rerank。
"""

from __future__ import annotations

import re

from mmi.core.memory.db import _db_lock, _get_conn
from mmi.core.memory.embedder import Embedder, get_embedder
from mmi.core.memory.faiss import (
    _INMEM_IDS,
    _INMEM_INDEX,
    _INMEM_LOCK,
    _ensure_loaded,
)
from mmi.core.memory.schema import DEFAULT_TOP_K, MemoryRecord


def _sanitize_fts_query(q: str) -> str:
    """把用户输入清洗成 FTS5 MATCH 表达式。

    FTS5 语法里很多字符是运算符(`*`, `:`, `(`, `)`, `"`, `-` 等);
    直接传可能触发 syntax error。这里只保留 unicode word 字符 + 中文,
    多词用 AND 串起来,保证可匹配 + 不报错。
    """
    # 拆词:中英文按 unicode 类别,英文按空格
    tokens = re.findall(r"[\w一-鿿]+", q, re.UNICODE)
    tokens = [t for t in tokens if len(t) >= 1][:10]  # 限 10 词
    if not tokens:
        return ""
    # 英文加 *,中文直接(unicode61 不用 *)
    parts = []
    for t in tokens:
        if re.match(r"^[A-Za-z0-9_]+$", t):
            parts.append(f'"{t}"*')
        else:
            parts.append(f'"{t}"')
    return " AND ".join(parts)


def _rows_to_records(
    memory_ids: list[str], *, fallback_vector: list[float] | None = None,
) -> list[MemoryRecord]:
    """按 memory_id 顺序从 SQLite 取完整记录。"""
    if not memory_ids:
        return []
    with _db_lock:
        conn = _get_conn()
        placeholders = ",".join("?" for _ in memory_ids)
        rows = conn.execute(
            f"SELECT * FROM memories WHERE memory_id IN ({placeholders})",
            memory_ids,
        ).fetchall()
    by_id = {row["memory_id"]: row for row in rows}
    out: list[MemoryRecord] = []
    for mid in memory_ids:
        row = by_id.get(mid)
        if row is None:
            continue
        rec = MemoryRecord.from_row(row)
        if fallback_vector is not None:
            rec.vector = fallback_vector
        out.append(rec)
    return out


def _search_faiss(
    query: str, *, top_k: int, embedder: Embedder | None,
) -> list[MemoryRecord]:
    """单跑 FAISS 路径(供双路 + 测试用)。走 P2-10 内存池。"""
    emb = embedder or get_embedder()
    try:
        vector = emb.embed(query)
    except Exception:
        return []
    if not vector:
        return []
    try:
        _ensure_loaded(emb.dim)
        with _INMEM_LOCK:
            idx = _INMEM_INDEX
            ids = list(_INMEM_IDS)
    except Exception:
        return []
    if idx is None or idx.ntotal == 0 or not ids:
        return []
    import numpy as np
    vec = np.array([vector], dtype="float32")
    k = min(top_k, idx.ntotal)
    try:
        _, idx_indices = idx.search(vec, k)
    except Exception:
        return []
    positions = [int(p) for p in idx_indices[0] if 0 <= int(p) < len(ids)]
    if not positions:
        return []
    memory_ids = [ids[p] for p in positions]
    return _rows_to_records(memory_ids, fallback_vector=vector)


def _search_fts(query: str, *, top_k: int) -> list[MemoryRecord]:
    """FTS5 关键词路径(供双路 + 测试用)。"""
    if not query or not query.strip():
        return []
    # 简单词法清洗:FTS5 unicode61 接受原 query
    fts_query = _sanitize_fts_query(query)
    if not fts_query:
        return []
    try:
        with _db_lock:
            conn = _get_conn()
            rows = conn.execute(
                """
                SELECT m.* FROM memories_fts f
                JOIN memories m ON m.rowid = f.rowid
                WHERE memories_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, top_k),
            ).fetchall()
    except Exception:
        return []
    return [MemoryRecord.from_row(r) for r in rows]


def search_semantic(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    embedder: Embedder | None = None,
) -> list[MemoryRecord]:
    """双路语义检索:FAISS(向量) + FTS5(关键词) → 合并去重 → top-k。

    双路策略:
      - FAISS 召 top_k 个(语义近邻)
      - FTS5 召 top_k 个(关键词命中)
      - 按 memory_id 合并去重;FAISS 命中的优先(语义更准),FTS5 命中的补在后面

    Args:
        query: 用户输入 / 当前 session 的 summary
        top_k: 每路召回数量
        embedder: 可选外部 embedder

    Returns:
        候选 MemoryRecord 列表(去重后 ≤ 2*top_k)。FAISS 不可用 / 索引空 → 退化为纯 FTS5。
    """
    if not query or not query.strip():
        return []
    faiss_hits: list[MemoryRecord] = []
    try:
        faiss_hits = _search_faiss(query, top_k=top_k, embedder=embedder)
    except Exception:
        faiss_hits = []
    fts_hits: list[MemoryRecord] = []
    try:
        fts_hits = _search_fts(query, top_k=top_k)
    except Exception:
        fts_hits = []
    # 合并:FAISS 在前(优先级高),FTS5 补未在 FAISS 命中的
    seen: set[str] = set()
    merged: list[MemoryRecord] = []
    for c in faiss_hits + fts_hits:
        if c.memory_id in seen:
            continue
        seen.add(c.memory_id)
        merged.append(c)
        if len(merged) >= top_k:
            break
    return merged
