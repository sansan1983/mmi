"""mmi.core.memory —— 向量语义记忆与跨会话检索。

三层记忆架构：
  L1 向量语义记忆 —— embedding → FAISS 语义检索
  L2 结构化摘要记忆 —— LLM生成的 {主题, 决策, 结论, 待办}
  L3 完整原文存储 —— 通过 .session.md 按需加载

检索流程：
  embedding → FAISS top-20 → 加载结构化摘要 → LLM 动态重排 → top-3
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "MemoryRecord",
    "store_memory",
    "search_semantic",
    "rerank",
    "build_structured_summary",
]


@dataclass
class MemoryRecord:
    memory_id: str = ""
    session_id: str = ""
    vector: list[float] | None = None
    summary_title: str = ""
    summary_decision: str = ""
    summary_conclusion: str = ""
    summary_todos: str = ""
    raw_content_ref: str = ""


def store_memory(
    session_id: str,
    body: str,
    *,
    embedding_model: str = "text-embedding-3-small",
) -> MemoryRecord:
    """对话结束后，生成 embedding + 结构化摘要并持久化。"""
    raise NotImplementedError("memory.store_memory — 待实现")


def search_semantic(
    query: str,
    *,
    top_k: int = 20,
    embedding_model: str = "text-embedding-3-small",
) -> list[MemoryRecord]:
    """语义检索：embedding → FAISS 匹配 → 返回 top-k。"""
    raise NotImplementedError("memory.search_semantic — 待实现")


def rerank(
    query: str,
    candidates: list[MemoryRecord],
    *,
    top_n: int = 3,
) -> list[MemoryRecord]:
    """LLM 动态重排序：根据当前上下文评估候选记忆的相关性。"""
    raise NotImplementedError("memory.rerank — 待实现")


def build_structured_summary(
    body: str,
    *,
    language: str = "zh-CN",
) -> dict[str, str]:
    """LLM 生成结构化摘要。"""
    raise NotImplementedError("memory.build_structured_summary — 待实现")
