"""mmi.core.memory —— 向量语义记忆与跨会话检索。

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
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from . import paths
from .session import new_session_id, utcnow_iso

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
]


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"     # sentence-transformers 小模型
DEFAULT_TOP_K = 20                                 # FAISS top-K
DEFAULT_RERANK_TOP_N = 3                           # LLM 重排后取 top-N

_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    memory_id    TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    turns_at     INTEGER NOT NULL,
    title        TEXT,
    decision     TEXT,
    conclusion   TEXT,
    todos        TEXT,
    raw_excerpt  TEXT
);
CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    title, decision, conclusion, todos, raw_excerpt,
    content='memories', content_rowid='rowid',
    tokenize='unicode61'
);

-- FTS5 external content 模式:用触发器自动同步,避免手工 DELETE/INSERT 撞内容表
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, title, decision, conclusion, todos, raw_excerpt)
    VALUES (new.rowid, new.title, new.decision, new.conclusion, new.todos, new.raw_excerpt);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, decision, conclusion, todos, raw_excerpt)
    VALUES ('delete', old.rowid, old.title, old.decision, old.conclusion, old.todos, old.raw_excerpt);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, decision, conclusion, todos, raw_excerpt)
    VALUES ('delete', old.rowid, old.title, old.decision, old.conclusion, old.todos, old.raw_excerpt);
    INSERT INTO memories_fts(rowid, title, decision, conclusion, todos, raw_excerpt)
    VALUES (new.rowid, new.title, new.decision, new.conclusion, new.todos, new.raw_excerpt);
END;
"""


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class MemoryRecord:
    """单条记忆记录（与 SQLite 行一一对应 + 可选 vector 字段）。"""

    memory_id: str = ""
    session_id: str = ""
    created_at: str = ""
    turns_at: int = 0
    title: str = ""
    decision: str = ""
    conclusion: str = ""
    todos: str = ""
    raw_excerpt: str = ""
    vector: list[float] | None = None    # 加载时从 FAISS 取，存储时无

    @classmethod
    def from_row(cls, row: sqlite3.Row, vector: list[float] | None = None) -> "MemoryRecord":
        return cls(
            memory_id=row["memory_id"],
            session_id=row["session_id"],
            created_at=row["created_at"],
            turns_at=row["turns_at"],
            title=row["title"] or "",
            decision=row["decision"] or "",
            conclusion=row["conclusion"] or "",
            todos=row["todos"] or "",
            raw_excerpt=row["raw_excerpt"] or "",
            vector=vector,
        )


@dataclass
class MemoryConfig:
    """memory 模块的可调参数（与 LoaderConfig 平级，组装时由 context 读取）。"""

    enabled: bool = True
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    top_k: int = DEFAULT_TOP_K
    rerank_top_n: int = DEFAULT_RERANK_TOP_N
    recall_top_n: int = DEFAULT_RERANK_TOP_N     # 注入 context 的最终数量


# ---------------------------------------------------------------------------
# Embedder 抽象
# ---------------------------------------------------------------------------


class Embedder(Protocol):
    """嵌入器协议。实现需返回固定维度、与文本相关的稠密向量。"""

    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """确定性假嵌入器（用于测试 / 无 sentence-transformers 时降级）。

    把文本 sha256 后切成 64 维 float 区间 [-1, 1] —— 维度固定、内容相关、
    完全可复现。无外部依赖、无模型下载。
    """

    DIM = 64

    @property
    def dim(self) -> int:
        return self.DIM

    def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # 64 维需要 64 字节，sha256 给 32 字节 → 重复拼接
        raw = h + h
        return [(b - 128) / 128.0 for b in raw[: self.DIM]]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class SentenceTransformerEmbedder:
    """sentence-transformers 嵌入器（生产用）。"""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL):
        # 延迟导入：用户没装 sentence-transformers 时不阻塞核心
        from sentence_transformers import SentenceTransformer  # noqa: WPS433

        self._model = SentenceTransformer(model_name)
        self._dim = self._model.get_sentence_embedding_dimension()

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        v = self._model.encode(text, normalize_embeddings=True)
        return v.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vs = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vs]


# ---------------------------------------------------------------------------
# 全局 embedder（可注入）
# ---------------------------------------------------------------------------

_embedder: Embedder | None = None
_embedder_lock = threading.Lock()


def get_embedder() -> Embedder:
    """获取当前 embedder。优先用显式注入的，否则懒加载 sentence-transformers，
    失败时降级到 HashEmbedder。
    """
    global _embedder
    if _embedder is not None:
        return _embedder
    with _embedder_lock:
        if _embedder is not None:
            return _embedder
        try:
            _embedder = SentenceTransformerEmbedder(DEFAULT_EMBEDDING_MODEL)
        except Exception:
            # 任何异常（缺包 / 无网络 / 模型不可用）→ 降级
            _embedder = HashEmbedder()
        return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """注入/重置 embedder。传 None 重置为懒加载默认。"""
    global _embedder
    with _embedder_lock:
        _embedder = embedder


# ---------------------------------------------------------------------------
# SQLite 连接
# ---------------------------------------------------------------------------

_db_lock = threading.Lock()
_INDEX_SCHEMA_VERSION = 1


def _connect_db() -> sqlite3.Connection:
    """开 SQLite 连接（同步、单线程安全，靠 _db_lock 串行）。"""
    paths.ensure_dirs()
    conn = sqlite3.connect(str(paths.get_memory_db_path()), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(_MEMORY_SCHEMA)
    return conn


def _get_conn() -> sqlite3.Connection:
    """获取（每线程）连接 —— 用 thread-local 避免跨线程共享。"""
    import threading as _t
    tls = getattr(_get_conn, "_tls", None)
    if tls is None:
        tls = _t.local()
        _get_conn._tls = tls  # type: ignore[attr-defined]
    if not hasattr(tls, "conn") or tls.conn is None:
        tls.conn = _connect_db()
    return tls.conn


# ---------------------------------------------------------------------------
# FAISS 索引管理
# ---------------------------------------------------------------------------

_faiss_lock = threading.Lock()


def _faiss_index_path() -> Path:
    return paths.get_faiss_index_path()


def _faiss_ids_path() -> Path:
    return paths.get_faiss_ids_path()


def _load_faiss_ids() -> list[str]:
    """读 vector 位置 i → memory_id 的列表。文件不存在 → 空列表。"""
    p = _faiss_ids_path()
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_faiss_ids(ids: list[str]) -> None:
    paths.ensure_dirs()
    p = _faiss_ids_path()
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False)
    tmp.replace(p)


def _load_faiss_index(dim: int):
    """读 FAISS 索引；不存在 / 维度不匹配 → 重建空索引。"""
    import faiss  # 局部导入：不依赖时可降级
    p = _faiss_index_path()
    if p.exists():
        try:
            idx = faiss.read_index(str(p))
            if idx.d == dim:
                return idx
        except Exception:
            pass
    return faiss.IndexFlatL2(dim)


def _save_faiss_index(idx) -> None:
    import faiss
    paths.ensure_dirs()
    p = _faiss_index_path()
    tmp = p.with_suffix(".index.tmp")
    faiss.write_index(idx, str(tmp))
    tmp.replace(p)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def build_structured_summary(
    body: str,
    *,
    language: str = "zh-CN",
    llm: Any = None,
) -> dict[str, str]:
    """从对话正文提取结构化摘要。

    两种模式:
      - LLM 模式(传 llm):让 LLM 抽 {主题, 决策, 关键结论, 待办} 四个字段
      - 规则模式(默认,不传 llm):从 markdown 头/尾提 title + conclusion

    LLM 模式失败时自动降级到规则模式,不抛错(摘要是辅助,坏了别影响主流程)。

    Args:
        body: Markdown body
        language: 输出语言(影响 prompt)
        llm: LLMProvider(要有 chat 方法)

    Returns:
        dict with keys: title, decision, conclusion, todos(都是 str)
    """
    if not body or not body.strip():
        return {"title": "", "decision": "", "conclusion": "", "todos": ""}
    if llm is not None:
        try:
            return _build_structured_summary_llm(body, language=language, llm=llm)
        except Exception:
            # 降级到规则版
            pass
    return _build_structured_summary_rules(body)


def _build_structured_summary_rules(body: str) -> dict[str, str]:
    """规则版:从 markdown 头/尾提 title + conclusion。"""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    title = ""
    for ln in lines:
        if ln.startswith("#"):
            title = ln.lstrip("#").strip()
            break
    if not title and lines:
        title = lines[0][:80]
    conclusion = lines[-1][:200] if lines else ""
    return {"title": title, "decision": "", "conclusion": conclusion, "todos": ""}


_STRUCTURED_PROMPT_ZH = (
    "请从以下对话中提取结构化摘要,严格用 JSON 格式输出,字段固定为:\n"
    '  {"title": "...", "decision": "...", "conclusion": "...", "todos": "..."}\n'
    "- title: 一句话主题(<= 30 字)\n"
    "- decision: 做出的关键决策(无则空字符串)\n"
    "- conclusion: 关键结论(无则空字符串)\n"
    "- todos: 待办事项,多条用「;」分隔(无则空字符串)\n"
    "只输出 JSON,不要任何前后缀。"
)
_STRUCTURED_PROMPT_EN = (
    "Extract a structured summary from the conversation below. "
    'Output STRICT JSON with exactly these fields:\n'
    '  {"title": "...", "decision": "...", "conclusion": "...", "todos": "..."}\n'
    "- title: one-line topic (<= 30 chars)\n"
    "- decision: key decision made (empty if none)\n"
    "- conclusion: key conclusion (empty if none)\n"
    "- todos: pending items, ';' separated (empty if none)\n"
    "Output JSON only, no prefix or explanation."
)


def _build_structured_summary_llm(
    body: str, *, language: str, llm: Any,
) -> dict[str, str]:
    """LLM 抽 {主题, 决策, 结论, 待办}。失败由调用方降级。"""
    prompt = _STRUCTURED_PROMPT_ZH if language.startswith("zh") else _STRUCTURED_PROMPT_EN
    # 截断 body 避免 prompt 过长(8k 字符够用)
    body_truncated = body[:8000]
    user_msg = (
        f"{prompt}\n\n对话全文:\n{body_truncated}"
        if language.startswith("zh")
        else f"{prompt}\n\nConversation:\n{body_truncated}"
    )
    raw = llm.chat(
        [
            {"role": "user", "content": user_msg},
        ],
        max_tokens=300,
        temperature=0.0,
    )
    return _parse_structured_json(raw, body_for_fallback=body)


def _parse_structured_json(
    raw: str, *, body_for_fallback: str,
) -> dict[str, str]:
    """从 LLM 输出里抠 JSON。解析失败 → 用原 body 走规则版(不污染)。"""
    import json
    import re
    text = (raw or "").strip()
    # 去掉 markdown 代码块围栏
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # 找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return _build_structured_summary_rules(body_for_fallback)
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return _build_structured_summary_rules(body_for_fallback)
    if not isinstance(obj, dict):
        return _build_structured_summary_rules(body_for_fallback)
    return {
        "title": str(obj.get("title", "") or "").strip()[:200],
        "decision": str(obj.get("decision", "") or "").strip()[:500],
        "conclusion": str(obj.get("conclusion", "") or "").strip()[:500],
        "todos": str(obj.get("todos", "") or "").strip()[:500],
    }


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
        且不写 FAISS（SQLite 仍写，检索时降级到 L2 距离不可用时的"无候选"）
    """
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
        vector=vector if vector else None,
    )
    with _db_lock:
        conn = _get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO memories
                (memory_id, session_id, created_at, turns_at,
                 title, decision, conclusion, todos, raw_excerpt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (record.memory_id, record.session_id, record.created_at, record.turns_at,
             record.title, record.decision, record.conclusion, record.todos, record.raw_excerpt),
        )
        conn.commit()

    # 3) FAISS 写向量（仅在 embedding 成功时）
    if vector:
        try:
            with _faiss_lock:
                import faiss
                idx = _load_faiss_index(emb.dim)
                ids = _load_faiss_ids()
                v = faiss.vector_to_array  # type: ignore[attr-defined]
                import numpy as np
                vec = np.array([vector], dtype="float32")
                idx.add(vec)
                ids.append(memory_id)
                _save_faiss_index(idx)
                _save_faiss_ids(ids)
        except Exception:
            # FAISS 写失败不阻塞主流程（SQLite 已有 record）
            pass

    return record


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


def _search_faiss(
    query: str, *, top_k: int, embedder: Embedder | None,
) -> list[MemoryRecord]:
    """单跑 FAISS 路径(供双路 + 测试用)。"""
    emb = embedder or get_embedder()
    try:
        vector = emb.embed(query)
    except Exception:
        return []
    if not vector:
        return []
    try:
        with _faiss_lock:
            idx = _load_faiss_index(emb.dim)
            ids = _load_faiss_ids()
    except Exception:
        return []
    if idx.ntotal == 0 or not ids:
        return []
    import numpy as np
    vec = np.array([vector], dtype="float32")
    k = min(top_k, idx.ntotal)
    try:
        _, I = idx.search(vec, k)
    except Exception:
        return []
    positions = [int(p) for p in I[0] if 0 <= int(p) < len(ids)]
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


def _sanitize_fts_query(q: str) -> str:
    """把用户输入清洗成 FTS5 MATCH 表达式。

    FTS5 语法里很多字符是运算符(`*`, `:`, `(`, `)`, `"`, `-` 等);
    直接传可能触发 syntax error。这里只保留 unicode word 字符 + 中文,
    多词用 AND 串起来,保证可匹配 + 不报错。
    """
    import re
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


def rerank(
    query: str,
    candidates: list[MemoryRecord],
    *,
    top_n: int = DEFAULT_RERANK_TOP_N,
    llm: Any = None,
    language: str = "zh-CN",
) -> list[MemoryRecord]:
    """LLM 动态重排序：从 candidates 选 top_n 最相关的。

    无 LLM 时降级：直接按 candidates 原顺序截前 top_n。

    Args:
        query: 当前上下文 query
        candidates: search_semantic 的输出
        top_n: 重排后取的数量
        llm: LLMProvider（要有 chat 方法）
        language: 输出语言

    Returns:
        top_n 候选；候选不足则全返回。
    """
    if not candidates:
        return []
    if top_n > len(candidates) or llm is None:
        return candidates[:top_n]

    # 构造 prompt：列每条候选的 title + 关键结论，让 LLM 排
    if language.startswith("zh"):
        sys_prompt = (
            "你是相关性排序助手。根据当前用户问题，对候选记忆按相关度从高到低重排。"
            "只输出重新排序后的 memory_id 列表（用逗号分隔），不要其他文字。"
        )
    else:
        sys_prompt = (
            "You are a relevance reranker. Rerank the candidate memories by relevance "
            "to the user's current question. Output only the reordered memory_id list "
            "(comma-separated), no other text."
        )
    candidate_lines = []
    for i, c in enumerate(candidates, 1):
        snippet = (c.title + " | " + c.conclusion).strip(" |") or c.raw_excerpt
        candidate_lines.append(f"[{i}] id={c.memory_id} | {snippet[:120]}")
    user_msg = (
        f"Question: {query}\n\nCandidates:\n" + "\n".join(candidate_lines)
    )
    try:
        resp = llm.chat(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=200,
            temperature=0.0,
        )
    except Exception:
        return candidates[:top_n]
    # 解析：找形如 "id=01XXX" 的，按出现顺序
    import re
    found = re.findall(r"id=([0-9A-HJKMNP-TV-Z]{26})", resp)
    by_id = {c.memory_id: c for c in candidates}
    reranked: list[MemoryRecord] = []
    seen: set[str] = set()
    for mid in found:
        if mid in by_id and mid not in seen:
            reranked.append(by_id[mid])
            seen.add(mid)
        if len(reranked) >= top_n:
            break
    # 兜底：没解析到 / 数量不够 → 用原顺序补齐
    if len(reranked) < top_n:
        for c in candidates:
            if c.memory_id not in seen:
                reranked.append(c)
                seen.add(c.memory_id)
                if len(reranked) >= top_n:
                    break
    return reranked


def recall_memories(
    query: str,
    *,
    config: MemoryConfig | None = None,
    embedder: Embedder | None = None,
    llm: Any = None,
    language: str = "zh-CN",
) -> list[MemoryRecord]:
    """对外主入口：search_semantic + rerank 一站式。

    Args:
        query: 当前上下文（用户输入 / summary）
        config: MemoryConfig
        embedder: 注入的 embedder
        llm: rerank 用的 LLM（None → 跳过重排）
        language: rerank prompt 语言

    Returns:
        最终候选（已重排 / 已截断），供 context 注入使用。
    """
    if config is None:
        config = MemoryConfig()
    if not config.enabled:
        return []
    candidates = search_semantic(query, top_k=config.top_k, embedder=embedder)
    if not candidates:
        return []
    return rerank(
        query, candidates, top_n=config.rerank_top_n, llm=llm, language=language
    )


# ---------------------------------------------------------------------------
# 工具：状态查询
# ---------------------------------------------------------------------------


def memory_count() -> int:
    """当前 SQLite 里的记忆条数（用于 `mmi stat` / 测试断言）。"""
    with _db_lock:
        conn = _get_conn()
        row = conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()
        return int(row["n"])


def clear_memories() -> None:
    """清空所有记忆（测试用 / CLI 显式 reset）。"""
    with _db_lock:
        conn = _get_conn()
        # FTS5 由触发器自动同步(DELETE on memories 触发 DELETE on memories_fts)
        conn.execute("DELETE FROM memories")
        conn.commit()
    with _faiss_lock:
        _save_faiss_ids([])
        p = _faiss_index_path()
        if p.exists():
            p.unlink()


def reset_for_test() -> None:
    """关闭并清空 thread-local 连接 + 嵌入器,让下一个测试用新 MMI_HOME。

    仅供测试 / 单测 fixture 使用 —— 不要在生产代码调。
    """
    global _embedder
    with _db_lock:
        tls = getattr(_get_conn, "_tls", None)
        if tls is not None and getattr(tls, "conn", None) is not None:
            try:
                tls.conn.close()
            except OSError:
                pass
        _get_conn._tls = None  # type: ignore[attr-defined]
    with _embedder_lock:
        _embedder = None
