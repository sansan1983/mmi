"""mmi.core.memory.schema —— 数据类 + 常量。

依赖项:无。
被依赖:几乎所有 memory 子模块。
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"     # sentence-transformers 小模型
DEFAULT_TOP_K = 20                                 # FAISS top-K
DEFAULT_RERANK_TOP_N = 3                           # LLM 重排后取 top-N


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
    content_hash: str = ""
    vector: list[float] | None = None    # 加载时从 FAISS 取，存储时无

    @classmethod
    def from_row(cls, row: sqlite3.Row, vector: list[float] | None = None) -> MemoryRecord:
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
            content_hash=row["content_hash"] or "",
            vector=vector,
        )


def _content_hash(body: str) -> str:
    """同 body → 同 hash,用于去重。"""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


@dataclass
class MemoryConfig:
    """memory 模块的可调参数（与 LoaderConfig 平级，组装时由 context 读取）。"""

    enabled: bool = True
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    top_k: int = DEFAULT_TOP_K
    rerank_top_n: int = DEFAULT_RERANK_TOP_N
    recall_top_n: int = DEFAULT_RERANK_TOP_N     # 注入 context 的最终数量
