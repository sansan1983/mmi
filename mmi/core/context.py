"""mmi.core.context —— 按需构建 LLM 上下文。

ARCHITECTURE.md §6.2 / §8.5：

  build_context 流程：
    1. 读 frontmatter → summary
    2. 读正文最后 N 轮（默认 10）
    3. 关键词检索 → top_k 段落（默认 3）
    4. 拼 messages = [system: summary, ...hits, ...recent, current_user]
    5. token 估算，超 4k → 按"摘要 > 命中段 > 最近轮"优先级截断

设计原则：
  - 不重写 storage / session 的 IO —— 只读
  - 失败安全：任何一步读不到 → 降级（不抛）
  - 纯函数：输入 session_id + user_input，输出 messages
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import search, storage
from .memory import MemoryConfig, recall_memories

if TYPE_CHECKING:
    pass

__all__ = [
    "LoaderConfig",
    "LoadedContext",
    "build_context",
    "estimate_tokens",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_RECENT_TURNS",
    "DEFAULT_HIT_PARAGRAPHS",
]


# ---------------------------------------------------------------------------
# 常量 / 配置
# ---------------------------------------------------------------------------


# §8.5: 单次 LLM 调用的 messages 总量硬上限 4k tokens
DEFAULT_MAX_TOKENS = 4000
# §6.2: 最近 N 轮
DEFAULT_RECENT_TURNS = 10
# §6.2: 关键词命中 top_k 段
DEFAULT_HIT_PARAGRAPHS = 3

# Token 估算：保守值 1 token ≈ 2 字符（英文 4 字符/token + 中文 1.5 字符/token 平均）
# 不用 tiktoken（多一个依赖），要更准再换
_CHARS_PER_TOKEN = 2


@dataclass
class LoaderConfig:
    """context 的可调参数。"""

    recent_turns: int = DEFAULT_RECENT_TURNS
    hit_paragraphs: int = DEFAULT_HIT_PARAGRAPHS
    max_tokens: int = DEFAULT_MAX_TOKENS
    system_prompt_zh: str = "你是一个乐于助人的助手。"
    system_prompt_en: str = "You are a helpful assistant."
    # 跨会话记忆：开启后会把 user_input 拿去向量检索 + 注入到 system 段
    memory: MemoryConfig = field(default_factory=MemoryConfig)


@dataclass
class LoadedContext:
    """build_context 的中间结果（供测试 / debug 用）。"""

    summary: str
    recent_turns: list[dict] = field(default_factory=list)
    hit_turns: list[dict] = field(default_factory=list)
    recalled_memories: list = field(default_factory=list)   # MemoryRecord 列表
    messages: list[dict] = field(default_factory=list)
    total_chars: int = 0
    estimated_tokens: int = 0
    truncated: bool = False
    truncated_what: str = ""  # "hits" | "recent" | ""（空 = 没截断）


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def build_context(
    session_id: str,
    user_input: str,
    config: LoaderConfig | None = None,
    *,
    language: str = "zh-CN",
) -> list[dict]:
    """构造 LLM 的 messages 列表。

    Args:
        session_id: 目标会话
        user_input: 当前用户输入
        config: context 配置（默认走 LoaderConfig()）
        language: 输出语言（影响 system prompt 和搜索分词）

    Returns:
        OpenAI 格式 messages 列表
    """
    if config is None:
        config = LoaderConfig()

    ctx = _load_intermediate(session_id, user_input, config, language=language)
    messages = compose_messages(ctx, user_input, config, language=language)

    # 截断检查
    if estimate_tokens(messages) > config.max_tokens:
        messages, truncated_what = _truncate(messages, config)
        ctx.messages = messages
        ctx.truncated = True
        ctx.truncated_what = truncated_what
        ctx.estimated_tokens = estimate_tokens(messages)
        ctx.total_chars = sum(len(m["content"]) for m in messages)

    return messages


def build_context_detailed(
    session_id: str,
    user_input: str,
    config: LoaderConfig | None = None,
    *,
    language: str = "zh-CN",
) -> LoadedContext:
    """build_context 的详细版，返回 LoadedContext 供测试 / debug。"""
    if config is None:
        config = LoaderConfig()

    ctx = _load_intermediate(session_id, user_input, config, language=language)
    messages = compose_messages(ctx, user_input, config, language=language)

    if estimate_tokens(messages) > config.max_tokens:
        messages, truncated_what = _truncate(messages, config)
        ctx.truncated = True
        ctx.truncated_what = truncated_what

    ctx.messages = messages
    ctx.estimated_tokens = estimate_tokens(messages)
    ctx.total_chars = sum(len(m["content"]) for m in messages)
    return ctx


# ---------------------------------------------------------------------------
# 内部：分步
# ---------------------------------------------------------------------------


def _load_intermediate(
    session_id: str,
    user_input: str,
    config: LoaderConfig,
    *,
    language: str,
) -> LoadedContext:
    """读 session → 解析 → 取 recent + hits。"""
    ctx = LoadedContext(summary="")

    # 1) frontmatter → summary
    try:
        meta = storage.read_meta(session_id)
        ctx.summary = meta.summary or ""
    except (storage.SessionNotFound, storage.SessionCorrupt):
        return ctx  # 拿不到就全空

    # 2) 全文 → turns
    try:
        session = storage.read_session(session_id)
    except (storage.SessionNotFound, storage.SessionCorrupt):
        session = None
    all_turns = storage.parse_turns(session.body) if session else []
    if all_turns:
        # 3) 最近 N 轮（1 轮 = user + assistant 两条，按 pair 切）
        n_recent_pairs = max(0, config.recent_turns)
        recent_pairs = _take_last_pairs(all_turns, n_recent_pairs)
        ctx.recent_turns = recent_pairs

        # 4) 关键词命中（排除最近 N 轮 + 当前 user input 自身）
        older = all_turns[: max(0, len(all_turns) - len(recent_pairs))]
        if older and user_input and config.hit_paragraphs > 0:
            ctx.hit_turns = search.search_top_k(
                older, user_input, k=config.hit_paragraphs, language=language
            )

    # 5) 跨会话记忆：用 user_input 召回历史相关记忆（不依赖本 session 有 turns）
    if config.memory.enabled and user_input:
        try:
            ctx.recalled_memories = recall_memories(user_input, config=config.memory)
        except Exception:
            # 记忆检索失败不阻塞主流程
            ctx.recalled_memories = []

    return ctx


def _take_last_pairs(turns: list[dict], n_pairs: int) -> list[dict]:
    """取最后 n_pairs 个"完整轮"（user + assistant 配对）。

    从右往左走：先看到 assistant 时往前看 user 配对；先看到 user 时往后看 assistant 配对。
    边界：孤立的 user（无 assistant 回复）算半轮，但放宽到算 1 对（避免漏）。
    """
    if n_pairs <= 0 or not turns:
        return []
    out: list[dict] = []
    i = len(turns)
    pairs_collected = 0
    while i > 0 and pairs_collected < n_pairs:
        i -= 1
        role = turns[i].get("role")
        if role == "assistant" and i > 0 and turns[i - 1].get("role") == "user":
            # 先拿到 pair，往前走两步
            out.append(turns[i])       # assistant
            out.append(turns[i - 1])   # user
            i -= 1
            pairs_collected += 1
        elif role == "user":
            out.append(turns[i])
            # 找紧随的 assistant
            if i + 1 < len(turns) and turns[i + 1].get("role") == "assistant":
                out.append(turns[i + 1])
                # 但 i 不再前移；外层 while 会再走 i -= 1
                # 我们已经收集了这一对，半轮算 1 对
                pairs_collected += 1
            else:
                # 孤立 user，算半轮
                pairs_collected += 1
        else:
            # 边界情况（assistant 前面不是 user）
            out.append(turns[i])
            pairs_collected += 1
    out.reverse()
    return out


def compose_messages(
    ctx: LoadedContext,
    user_input: str,
    config: LoaderConfig,
    *,
    language: str,
) -> list[dict]:
    """把 LoadedContext 拼成 OpenAI messages。

    顺序：system(with summary) → hits → recent → current user
    hits 和 recent 可能重叠，做内容去重。
    """
    # 1) system
    if language.startswith("zh"):
        system = config.system_prompt_zh
    else:
        system = config.system_prompt_en
    if ctx.summary:
        if language.startswith("zh"):
            system = f"{system}\n\n会话摘要：{ctx.summary}"
        else:
            system = f"{system}\n\nSession summary: {ctx.summary}"

    # 1.5) 跨会话记忆（Recall 段）
    if ctx.recalled_memories:
        if language.startswith("zh"):
            mem_lines = ["相关历史记忆："]
            for m in ctx.recalled_memories:
                title = m.title or "(无标题)"
                snippet = m.conclusion or m.raw_excerpt or ""
                mem_lines.append(f"- [{title}] {snippet[:120]}")
            system = system + "\n\n" + "\n".join(mem_lines)
        else:
            mem_lines = ["Relevant memories from past sessions:"]
            for m in ctx.recalled_memories:
                title = m.title or "(untitled)"
                snippet = m.conclusion or m.raw_excerpt or ""
                mem_lines.append(f"- [{title}] {snippet[:120]}")
            system = system + "\n\n" + "\n".join(mem_lines)

    messages: list[dict] = [{"role": "system", "content": system}]

    # 2) hits + recent 去重拼接
    seen_keys: set[str] = set()
    for src in (ctx.hit_turns, ctx.recent_turns):
        for turn in src:
            content = turn.get("content") or ""
            if not content:
                continue
            key = content[:200]  # 截前 200 字符做指纹
            if key in seen_keys:
                continue
            seen_keys.add(key)
            messages.append({"role": turn["role"], "content": content})

    # 3) current user
    messages.append({"role": "user", "content": user_input})

    return messages


# ---------------------------------------------------------------------------
# Token 估算 + 截断
# ---------------------------------------------------------------------------


def estimate_tokens(messages: list[dict]) -> int:
    """粗估 token 数：1 token ≈ 2 字符（保守值）。

    不引入 tiktoken 依赖；要更准再换。
    """
    total = 0
    for m in messages:
        total += len(m.get("content") or "")
        # role 标签也占 token
        total += 10
    return total // _CHARS_PER_TOKEN


def _truncate(
    messages: list[dict],
    config: LoaderConfig,
) -> tuple[list[dict], str]:
    """按"摘要 > 命中段 > 最近轮"优先级截断。

    必留：system（带 summary）+ 最后一条 user（current）
    可删：hits（先删）→ recent（从最早的开始删）

    Returns:
        (新 messages, 被截断的部分 "hits"|"recent"|"")
    """
    if len(messages) < 2:
        return messages, ""

    # 找到 system 和最后 user 的位置
    system_msg = messages[0]
    current_user = messages[-1]
    if current_user.get("role") != "user":
        # 异常：最后不是 user，直接不动
        return messages, ""

    middle = messages[1:-1]
    if not middle:
        return messages, ""

    # 切 hits vs recent：hits 在前，recent 在后
    # 我们没法直接区分（顺序在 compose_messages 里已经混在一起了）
    # 简化策略：先按"前半可删、后半优先"删
    # 实际：把 messages 切成 [system, A, B, C, current_user]，
    #       A B C 都是 middle，从 A 开始尝试删

    # 重新算 budget
    overhead = estimate_tokens([system_msg, current_user])
    budget = config.max_tokens - overhead
    if budget <= 0:
        # 极端情况：连 system + current 都超 —— 强制保留
        return [system_msg, current_user], "recent"

    # 倒着累加 middle（保留最新的）直到超 budget
    kept_reverse: list[dict] = []
    used = 0
    for m in reversed(middle):
        t = estimate_tokens([m])
        if used + t > budget:
            break
        kept_reverse.append(m)
        used += t

    kept = list(reversed(kept_reverse))
    if len(kept) < len(middle):
        truncated_what = "recent" if kept and any(
            m.get("role") in ("user", "assistant") for m in middle[len(kept):]
        ) else "recent"
    else:
        truncated_what = ""

    return [system_msg, *kept, current_user], truncated_what