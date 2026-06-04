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
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from . import storage
from .llm import LLMError, LLMProvider
from .session import SessionMeta, utcnow_iso

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

    # 写回（不重写 body）—— 在文件锁内重读 + 合并 + 写，
    # 避免与 manager._recompute_heat 等并发写入产生 lost-update。
    try:
        with storage._exclusive_lock(session_id):
            s2 = storage.read_session(session_id)
            s2.meta.summary = meta.summary
            s2.meta.summary_version = meta.summary_version
            s2.meta.summary_history = meta.summary_history
            s2.meta.updated_at = utcnow_iso()
            # 直接 _atomic_write：write_session 会再 lock 死锁
            storage._atomic_write(
                storage.session_path(session_id),
                storage._dump_frontmatter(s2.meta) + s2.body,
            )
    except (storage.SessionNotFound, storage.SessionCorrupt, OSError):
        return False

    return True


# ---------------------------------------------------------------------------
# 后台线程版本（Phase 6：避免慢 LLM 阻塞 chat 主流程）
# ---------------------------------------------------------------------------


# 全局单线程池:FIFO 顺序执行,避免多后台线程同时改 frontmatter 竞态
# (max_workers=1 是关键:2 个任务同时改同 session,会让一份更新丢失)
_BACKGROUND_POOL: ThreadPoolExecutor | None = None
_POOL_LOCK = threading.Lock()


def _get_pool() -> ThreadPoolExecutor:
    global _BACKGROUND_POOL
    if _BACKGROUND_POOL is None:
        with _POOL_LOCK:
            if _BACKGROUND_POOL is None:
                _BACKGROUND_POOL = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="mmi-bg",
                )
    return _BACKGROUND_POOL


class _ThreadLike:
    """轻量包装,保留 Thread 风格的 .join(timeout=...) / .is_alive() 接口。"""

    def __init__(self, future: Future):
        self._f = future
        self._daemon = True   # ThreadPoolExecutor 内部都是非阻塞,语义近似 daemon

    def join(self, timeout: float | None = None) -> None:
        try:
            self._f.result(timeout=timeout)
        except Exception:
            # 跟 threading.Thread.join 一致:不抛,只静默等
            pass

    def is_alive(self) -> bool:
        return not self._f.done()


def schedule_summary_update(
    session_id: str,
    llm: LLMProvider,
    *,
    language: str = "zh-CN",
) -> _ThreadLike:
    """非阻塞:提交 update_summary 到单线程池,立即返回。

    用途:manager.chat() 末尾用,避免 LLM 调用阻塞 chat 主流程。
    失败静默(与 update_summary 一致:不更新,下次再试)。
    并发:全模块共用 1 个 worker,任务按 FIFO 顺序执行,不会跟
    _schedule_memory_store 抢同一 session 的文件锁。

    Args:
        session_id: 会话 ID
        llm: LLMProvider 实例
        language: 摘要语言(zh-CN / en-US)

    Returns:
        _ThreadLike 包装的 Future(daemon).join(timeout=...) 等待任务结束。
    """
    def _run() -> None:
        try:
            ok = update_summary(session_id, llm, language=language)
            if ok:
                # 摘要写成功后顺带入库(同线程池,FIFO 跟在摘要后)
                # 入库 IO 放摘要线程里跑,避免再起一个独立线程
                _run_memory_store(session_id)
        except Exception:
            # 后台线程:任何异常都吞掉,不影响主流程
            pass

    future = _get_pool().submit(_run)
    return _ThreadLike(future)


def _schedule_memory_store(session_id: str) -> _ThreadLike:
    """提交 store_memory 到线程池(每轮 chat 都调,等摘要触发也调)。

    与 schedule_summary_update 共用同一线程池,任务 FIFO。
    """
    future = _get_pool().submit(_run_memory_store, session_id)
    return _ThreadLike(future)


def _run_memory_store(session_id: str) -> None:
    """线程池 worker:读 body + 调 store_memory。"""
    try:
        body, turns_at = _read_body_for_memory(session_id)
        if not body:
            return
        from . import memory as memory_module
        try:
            memory_module.store_memory(
                session_id, body, turns_at=turns_at,
            )
        except Exception:
            # 记忆入库失败不抛:摘要是关键路径,记忆是锦上添花
            pass
    except Exception:
        pass


def shutdown_background_pool(wait: bool = True) -> None:
    """关闭线程池(测试 teardown / 进程退出用)。"""
    global _BACKGROUND_POOL
    with _POOL_LOCK:
        if _BACKGROUND_POOL is not None:
            _BACKGROUND_POOL.shutdown(wait=wait)
            _BACKGROUND_POOL = None


def _read_body_for_memory(session_id: str) -> tuple[str, int]:
    """读 body + turns_at,供 _run 在 update_summary 之后入库记忆用。

    与 update_summary 内部 read_session 重复了一次磁盘 IO,但避免在
    update_summary 的锁内嵌 store_memory(那个锁我们已经释放)。

    Returns:
        (body, turns_at);读不到时返回 ("", 0)
    """
    try:
        s = storage.read_session(session_id)
    except (storage.SessionNotFound, storage.SessionCorrupt, OSError):
        return "", 0
    n_turns = s.body.count("**User:**")
    return s.body, n_turns


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