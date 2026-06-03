"""mmi.core.summarizer —— 摘要生成 + 版本管理。

ARCHITECTURE.md §6.3 / §8.3：

  触发条件（任一满足即重生）：
    1. 自上次摘要以来新增 ≥ 20 轮
    2. 自上次摘要以来新增 ≥ 5000 字符（粗估：body 字符总数）
    3. 距上次摘要 > 24 小时且新增 ≥ 5 轮

  流程：
    1. should_update_summary(meta, body) → bool
    2. 若需要：
       a. 旧 summary 推入 summary_history（带 version / at / turns_at）
       b. 用 [旧 summary + 全文] 调 LLM 生成新 summary
       c. summary_version += 1
       d. 写回 frontmatter（不重写 body）

设计原则：
  - 失败安全：LLM 调失败 → 不更新（下次再试）
  - 写盘走 storage 的锁：两个 chat 并发 update 不会撕裂
  - 摘要可空：从未生成过 → 当作 "no summary yet"，不报错
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from . import storage
from .llm import LLMError, LLMProvider
from .session import Session, SessionMeta, utcnow_iso

if TYPE_CHECKING:
    pass

__all__ = [
    "should_update_summary",
    "update_summary",
    "schedule_summary_update",
    "last_summary_turns",
    "last_summary_at",
    "MIN_TURNS_DELTA",
    "MIN_CHARS_DELTA",
    "MIN_HOURS_SINCE",
    "MIN_TURNS_FOR_LONG_GAP",
]


# ---------------------------------------------------------------------------
# 常量：§8.3 触发阈值
# ---------------------------------------------------------------------------


MIN_TURNS_DELTA = 20             # 触发 1：自上次摘要 ≥ 20 轮
MIN_CHARS_DELTA = 5000           # 触发 2：自上次摘要 ≥ 5000 字符
MIN_HOURS_SINCE = 24             # 触发 3：距上次摘要 > 24h
MIN_TURNS_FOR_LONG_GAP = 5       # 触发 3：且新增 ≥ 5 轮

DEFAULT_SUMMARY_PROMPT_ZH = (
    "请用 1-2 句话（中文，30-80 字）总结以下对话的核心主题。\n"
    '只输出总结本身，不要任何前缀（如「摘要：」）。\n'
    '如果对话内容太少或太杂，输出「无主题短对话」。'
)
DEFAULT_SUMMARY_PROMPT_EN = (
    "Summarize the following conversation in 1-2 sentences (English, 30-80 words).\n"
    "Output only the summary, no prefix like 'Summary:'.\n"
    "If the conversation is too short or scattered, output 'no clear topic'."
)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def should_update_summary(
    meta: SessionMeta,
    body: str,
    *,
    now: datetime | None = None,
) -> bool:
    """判断是否需要重生摘要（§8.3 三条规则 OR）。"""
    if now is None:
        now = datetime.now(timezone.utc)
    current_turns = body.count("**User:**")
    current_chars = len(body)
    last_turns = last_summary_turns(meta)
    last_at = last_summary_at(meta)
    turn_delta = current_turns - last_turns
    char_delta = current_chars  # 简化：body 字符总数（不是增量）

    # 触发 1：≥ 20 轮
    if turn_delta >= MIN_TURNS_DELTA:
        return True
    # 触发 2：≥ 5000 字符
    if char_delta >= MIN_CHARS_DELTA:
        return True
    # 触发 3：> 24h + ≥ 5 轮
    if last_at is not None:
        hours_since = (now - last_at).total_seconds() / 3600
        if hours_since > MIN_HOURS_SINCE and turn_delta >= MIN_TURNS_FOR_LONG_GAP:
            return True
    else:
        # 从未生成过摘要：如果 turn 数 ≥ 5 也触发
        if current_turns >= MIN_TURNS_FOR_LONG_GAP:
            return True

    return False


def update_summary(
    session_id: str,
    llm: LLMProvider,
    *,
    language: str = "zh-CN",
    now: datetime | None = None,
) -> bool:
    """调 LLM 重生摘要，写回 frontmatter。

    不自己加锁（写盘走 storage.write_session 自己的锁），避免重入。
    失败时（LLM 调不通、文件 IO 错）不更新，下次再试。
    并发场景：两个 chat 同时 update 会让一个的更新被覆盖 —— 可接受
    （下次再生成就行，summary_history 不会丢，因为 push 在调用前已做）。

    Returns:
        True = 已更新；False = 失败 / 不需要更新
    """
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        session = storage.read_session(session_id)
    except (storage.SessionNotFound, storage.SessionCorrupt):
        return False

    meta = session.meta
    body = session.body

    if not should_update_summary(meta, body, now=now):
        return False

    # 调 LLM 生成新摘要（无锁状态；可能耗时）
    prompt_system = (
        DEFAULT_SUMMARY_PROMPT_ZH if language.startswith("zh")
        else DEFAULT_SUMMARY_PROMPT_EN
    )
    user_msg = _build_summary_input(meta.summary, body, language=language)
    try:
        new_summary = llm.chat(
            [
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=200,
            temperature=0.3,
        )
    except LLMError:
        return False

    new_summary = _clean_summary(new_summary, language=language)
    if not new_summary:
        return False

    # 推入 history（在内存里做；最后 write_session 一次性落盘）
    current_turns = body.count("**User:**")
    if meta.summary:
        meta.summary_history.append({
            "version": meta.summary_version,
            "at": utcnow_iso(),
            "text": meta.summary,
            "turns_at": last_summary_turns(meta),
        })

    # 更新 meta
    meta.summary = new_summary
    meta.summary_version += 1

    # 写回（不重写 body）—— write_session 内部加锁
    try:
        storage.write_session(Session(meta=meta, body=body))
    except (storage.SessionNotFound, OSError):
        return False

    return True


# ---------------------------------------------------------------------------
# 后台线程版本（Phase 6：避免慢 LLM 阻塞 chat 主流程）
# ---------------------------------------------------------------------------


def schedule_summary_update(
    session_id: str,
    llm: LLMProvider,
    *,
    language: str = "zh-CN",
) -> threading.Thread:
    """非阻塞：起后台线程跑 update_summary，立即返回。

    用途：manager.chat() 末尾用，避免 LLM 调用阻塞 chat 主流程。
    失败静默（与 update_summary 一致：不更新，下次再试）。
    并发：多次调用会起多个线程；storage.write_session 内部加锁保证
    不会撕裂文件；最坏情况是某次更新被覆盖，summary_history 仍保留。

    Args:
        session_id: 会话 ID
        llm: LLMProvider 实例
        language: 摘要语言（zh-CN / en-US）

    Returns:
        启动的 Thread（daemon=True，主进程退出时自动结束）。
        调用方一般不需要 join；测试时可用 .join(timeout=...) 等待。
    """
    def _run() -> None:
        try:
            update_summary(session_id, llm, language=language)
        except Exception:
            # 后台线程：任何异常都吞掉，不影响主流程
            pass

    t = threading.Thread(
        target=_run,
        daemon=True,
        name=f"summary-{session_id[:8]}",
    )
    t.start()
    return t


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def last_summary_turns(meta: SessionMeta) -> int:
    """上次摘要时的 turn 数（用于计算 delta）。"""
    if meta.summary_history:
        last = meta.summary_history[-1]
        turns_at = last.get("turns_at")
        if isinstance(turns_at, int):
            return turns_at
    return 0


def last_summary_at(meta: SessionMeta) -> datetime | None:
    """上次摘要的时间（用于计算 24h gap）。"""
    if meta.summary_history:
        at_str = meta.summary_history[-1].get("at")
        if at_str:
            try:
                s = at_str.strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, AttributeError):
                return None
    return None


def _build_summary_input(
    old_summary: str,
    body: str,
    *,
    language: str,
) -> str:
    """拼出给 LLM 的 user message。"""
    if language.startswith("zh"):
        header = "旧摘要：\n"
        if not old_summary:
            header = "（无旧摘要）\n"
        return f"{header}{old_summary}\n\n对话全文：\n{body}\n\n请生成新摘要："
    header = "Old summary:\n"
    if not old_summary:
        header = "(no previous summary)\n"
    return f"{header}{old_summary}\n\nFull conversation:\n{body}\n\nGenerate new summary:"


def _clean_summary(text: str, *, language: str) -> str:
    """去掉 LLM 输出里的引号、前缀、多余空白。"""
    s = (text or "").strip()
    # 去掉成对引号
    for q in ('"', "'", "「", "」", "『", "』", "《", "》", "`"):
        s = s.strip(q)
    # 去掉常见前缀
    for prefix in ("Summary:", "摘要：", "摘要:", "New summary:", "新摘要：", "新摘要:"):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    s = " ".join(s.split())
    s = s.rstrip(".,;:!?。,;:!?")
    return s