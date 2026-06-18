"""mmi.core.memory.rerank —— LLM 重排 + 一站式 recall。

依赖项:schema, search。
被依赖:外部 callers(import from mmi.core.memory)。
"""

from __future__ import annotations

import re
from typing import Any

from mmi.core.memory.schema import (
    DEFAULT_RERANK_TOP_N,
    MemoryConfig,
    MemoryRecord,
)
from mmi.core.memory.search import search_semantic


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
    embedder: Any = None,
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
