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

# Token 估算：优先 tiktoken 精确(cl100k_base),降级为中英文区分
# 中文 1 字 ≈ 2 token,英文 1 词 ≈ 1.3 token(粗估)
try:
    import tiktoken
    _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
    _HAS_TIKTOKEN = True
except ImportError:
    _TIKTOKEN_ENC = None
    _HAS_TIKTOKEN = False
_CHARS_PER_TOKEN = 2  # 仅降级路径用


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
    """build_context 的中间结果(供测试 / debug 用)。

    P1-4 改进后新增 `sections` 字段(结构化消息,按 system/hits/recent/user 分区)。
    截断按 section 独立删,优先级:summary (system) > hits > recent。
    `messages` 仍为 LLM 用的扁平列表(向后兼容)。
    """

    summary: str
    recent_turns: list[dict] = field(default_factory=list)
    hit_turns: list[dict] = field(default_factory=list)
    recalled_memories: list = field(default_factory=list)   # MemoryRecord 列表
    messages: list[dict] = field(default_factory=list)
    sections: dict[str, list[dict]] = field(default_factory=lambda: {
        "system": [], "hits": [], "recent": [], "user": [],
    })
    total_chars: int = 0
    estimated_tokens: int = 0
    truncated: bool = False
    truncated_what: str = ""  # "hits" | "recent" | ""(空 = 没截断)


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
        config: context 配置(默认走 LoaderConfig())
        language: 输出语言(影响 system prompt 和搜索分词)

    Returns:
        OpenAI 格式 messages 列表
    """
    if config is None:
        config = LoaderConfig()

    ctx = _load_intermediate(session_id, user_input, config, language=language)
    sections = compose_sections(ctx, user_input, config, language=language)
    messages = flatten_sections(sections)

    if estimate_tokens(messages) > config.max_tokens:
        sections, truncated_what = _truncate_by_section(sections, config)
        messages = flatten_sections(sections)
        ctx.sections = sections
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
    """build_context 的详细版,返回 LoadedContext 供测试 / debug。"""
    if config is None:
        config = LoaderConfig()

    ctx = _load_intermediate(session_id, user_input, config, language=language)
    sections = compose_sections(ctx, user_input, config, language=language)
    messages = flatten_sections(sections)

    if estimate_tokens(messages) > config.max_tokens:
        sections, truncated_what = _truncate_by_section(sections, config)
        messages = flatten_sections(sections)
        ctx.truncated = True
        ctx.truncated_what = truncated_what

    ctx.sections = sections
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
        # 3) 最近 N 轮(P1-5 动态窗口)
        n_recent_pairs = _compute_recent_window(
            all_turns, config, user_input=user_input, language=language,
        )
        recent_pairs = _take_last_pairs(all_turns, n_recent_pairs)
        ctx.recent_turns = recent_pairs

        # 4) 关键词命中(排除最近 N 轮 + 当前 user input 自身)
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


def _compute_recent_window(
    all_turns: list[dict],
    config: LoaderConfig,
    *,
    user_input: str = "",
    language: str = "zh-CN",
) -> int:
    """P1-5 动态最近轮窗口。

    根据 token 余量动态调 recent_turns:
      remaining = budget - summary - hits - user
      recent = clamp(remaining / avg_pair_tokens, MIN, MAX)

    - MIN_RECENT_PAIRS = 5(再少就失语境)
    - MAX_RECENT_PAIRS = DEFAULT_RECENT_TURNS * 2 = 20(防止吃满 token)
    - 短对话/没 hits → 窗口可扩到 MAX
    - 长对话/hits 多 → 窗口缩到 MIN

    无 hits 召回时(pure recent)也会算一遍(简化为 0 hits)

    依赖 P0-3(精确 token 估算)才能给准确 budget。
    """
    DEFAULT_MIN = 5  # noqa: N806
    DEFAULT_MAX = max(10, config.recent_turns * 2)  # noqa: N806

    # 先估算 system + user token(强制必留)
    system_msg = {"role": "system", "content": config.system_prompt_zh if language.startswith("zh") else config.system_prompt_en}
    user_msg = {"role": "user", "content": user_input}
    overhead = estimate_tokens([system_msg, user_msg])

    budget = config.max_tokens - overhead
    if budget <= 0:
        return DEFAULT_MIN  # 极端,至少给 5

    # 算平均每对 token(user + assistant = 2 turn)
    # 抽样最近几对:取最近 5 对(若有)的平均
    sample_pairs = min(5, len(all_turns) // 2)
    if sample_pairs > 0:
        sample = all_turns[-(sample_pairs * 2):]
        sample_text = "\n".join((t.get("content") or "") for t in sample)
        # 样本 total token / 样本对数
        sample_tokens = estimate_tokens([{"role": "user", "content": sample_text}])
        avg_pair_tokens = max(50, sample_tokens // sample_pairs)  # 兜底 50 token / 对
    else:
        avg_pair_tokens = 200  # 启发式默认 200 token / 对

    # 预算还可放多少对(给 hits 也留点)
    hits_reserve = min(config.hit_paragraphs * 2, budget // 4)
    pairs_budget = max(0, (budget - hits_reserve) // avg_pair_tokens)

    n = max(DEFAULT_MIN, min(DEFAULT_MAX, pairs_budget))
    return n


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


def compose_sections(
    ctx: LoadedContext,
    user_input: str,
    config: LoaderConfig,
    *,
    language: str,
) -> dict[str, list[dict]]:
    """把 LoadedContext 拼成结构化 messages(P1-4 改进)。

    返回 {system, hits, recent, user} 四区,每区 list[dict]。
    截断按 section 独立删(优先级 system > hits > recent),详见 _truncate_by_section。
    """
    sections: dict[str, list[dict]] = {
        "system": [], "hits": [], "recent": [], "user": [],
    }

    # 1) system(带 summary + 跨会话记忆)
    system = config.system_prompt_zh if language.startswith("zh") else config.system_prompt_en
    if ctx.summary:
        if language.startswith("zh"):
            system = f"{system}\n\n会话摘要:{ctx.summary}"
        else:
            system = f"{system}\n\nSession summary: {ctx.summary}"

    if ctx.recalled_memories:
        if language.startswith("zh"):
            mem_lines = ["相关历史记忆:"]
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

    sections["system"].append({"role": "system", "content": system})

    # 2) hits(优先 recent:按相关性命中段)
    for turn in ctx.hit_turns:
        content = turn.get("content") or ""
        if content:
            sections["hits"].append({"role": turn["role"], "content": content})

    # 3) recent(hits 之外的最近 N 轮,按内容指纹去重)
    seen_keys = {h["content"][:200] for h in sections["hits"]}
    for turn in ctx.recent_turns:
        content = turn.get("content") or ""
        if not content:
            continue
        key = content[:200]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        sections["recent"].append({"role": turn["role"], "content": content})

    # 4) user
    sections["user"].append({"role": "user", "content": user_input})

    return sections


def flatten_sections(sections: dict[str, list[dict]]) -> list[dict]:
    """把 sections 拼回 LLM 用的扁平 messages 列表。

    顺序:system → hits → recent → user(向后兼容老 API)。
    """
    return (
        list(sections["system"])
        + list(sections["hits"])
        + list(sections["recent"])
        + list(sections["user"])
    )


# 向后兼容:旧名字 compose_messages 仍可用(返扁平 list)
def compose_messages(
    ctx: LoadedContext,
    user_input: str,
    config: LoaderConfig,
    *,
    language: str,
) -> list[dict]:
    """DEPRECATED:用 compose_sections + flatten_sections。保留此函数
    是为了不破坏外部直接 import 的代码(测试 / 第三方)。"""
    return flatten_sections(
        compose_sections(ctx, user_input, config, language=language)
    )


# ---------------------------------------------------------------------------
# Token 估算 + 截断
# ---------------------------------------------------------------------------


def estimate_tokens(messages: list[dict]) -> int:
    """粗估 token 数。

    优先 tiktoken(cl100k_base,GPT-4o 编码)精确算;
    装不上时降级为中英文区分:
      - 中文 1 字 ≈ 2 token
      - 英文 1 词 ≈ 1.3 token
    """
    if _HAS_TIKTOKEN:
        total = 0
        for m in messages:
            text = m.get("content") or ""
            # role 标签("system"/"user"/"assistant")也占 token
            total += len(_TIKTOKEN_ENC.encode(text)) + 4
        return total
    # 降级:区分中英文
    import re
    total = 0
    for m in messages:
        text = m.get("content") or ""
        cn = sum(1 for c in text if '一' <= c <= '鿿' or
                                '㐀' <= c <= '䶿')
        en_text = re.sub(r'[一-鿿㐀-䶿]', ' ', text)
        en_words = max(1, len(en_text.split()))
        total += cn * 2 + int(en_words * 1.3) + 4  # role 标签
    return total


def _truncate_by_section(
    sections: dict[str, list[dict]],
    config: LoaderConfig,
) -> tuple[dict[str, list[dict]], str]:
    """按"summary > hits > recent"优先级截断(P1-4 改进)。

    必留:system(1 条)+ user(1 条)
    可删顺序:recent → hits(system + user 永不删)
    每轮删最早的一条,直到总 token ≤ budget。

    与旧实现的区别:
      - 旧:_truncate(messages, ...) 把 system / hits / recent 合成一坨,
        不知道哪条是 hits,实际只能从前往后删(违反了"先 recent 再 hits"的设计)
      - 新:按 section 独立删,精确遵守"recent 优先"原则
    """
    system_msgs = sections["system"]
    user_msgs = sections["user"]
    # 强制至少留 1 条 user(否则 LLM 不知道 query 是啥)
    if not system_msgs or not user_msgs:
        return sections, ""

    # 当前 token 用量
    cur_total = estimate_tokens(flatten_sections(sections))
    if cur_total <= config.max_tokens:
        return sections, ""

    truncated_what = ""
    # 先删 recent
    while sections["recent"] and cur_total > config.max_tokens:
        sections["recent"].pop(0)
        truncated_what = truncated_what if truncated_what else "recent"
        cur_total = estimate_tokens(flatten_sections(sections))

    # 再删 hits(recent 删完仍超)
    while sections["hits"] and cur_total > config.max_tokens:
        sections["hits"].pop(0)
        truncated_what = "hits"
        cur_total = estimate_tokens(flatten_sections(sections))

    # 极端:连 system + user 都超 —— 强制保留,不截断
    return sections, truncated_what


# 向后兼容:旧的 _truncate 函数(对老测试 / 第三方 import 保留)
def _truncate(
    messages: list[dict],
    config: LoaderConfig,
) -> tuple[list[dict], str]:
    """DEPRECATED:用 _truncate_by_section。保留此函数是过渡期兼容。"""
    # 假设 messages 形如 [system, *middle, user]
    if len(messages) < 2:
        return messages, ""
    system_msg = messages[0]
    user_msg = messages[-1]
    if user_msg.get("role") != "user":
        return messages, ""
    # 全部归到 recent section
    fake_sections = {
        "system": [system_msg],
        "hits": [],
        "recent": list(messages[1:-1]),
        "user": [user_msg],
    }
    new_sections, what = _truncate_by_section(fake_sections, config)
    return flatten_sections(new_sections), what
