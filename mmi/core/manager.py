"""mmi.core.manager —— 唯一对外门面。

ARCHITECTURE.md §2 原则 1：UI 不允许直接读会话文件。
                    UI 不允许直接 import core.storage / core.session。
ARCHITECTURE.md §7：本类的公开 API 是约定。

Phase 3 范围（ARCHITECTURE.md §9 Phase 3）：
  - 走 context.build_context 构造 LLM messages（摘要 + 最近 N 轮 + 命中段）
  - 4k token 预算硬截断
  - 摘要自动生成（§8.3 触发条件：≥20 轮 / ≥5000 字符 / 24h+≥5 轮）
  - 摘要版本管理（summary_history）
  - 保留 Phase 2 的 3/10/20 checkpoint 逻辑（classifier + titler）

明确不做（见 §9 Phase 3 "明确不做"）：
  - 热度、TUI、embedding 检索（Phase 4 / 5 / 12）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import classifier as cls_module
from . import heat as heat_module
from . import context
from . import storage
from . import summarizer
from . import titler
from .llm import LLMError, LLMProvider, get_default_provider
from mmi.core.session import DEFAULT_TITLE, Session, SessionMeta, new_session_id

log = logging.getLogger(__name__)

__all__ = [
    "SessionManager",
    "ChatResult",
    "SessionNotFound",
    "SessionCorrupt",
    "StorageError",
    "LLMError",
]


# 重新导出 storage 层的异常 + LLMError，让 UI 只 import manager 即可
SessionNotFound = storage.SessionNotFound
SessionCorrupt = storage.SessionCorrupt
StorageError = storage.StorageError


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class ChatResult:
    """manager.chat() 的返回。

    Attributes:
        reply: LLM 给的回复文本
        title_updated: 这一轮是否更新了标题（仅 10/20 轮 checkpoint 可能为 True）
        summary_updated: 这一轮是否更新了摘要（§8.3 触发时为 True）
        context_truncated: LLM 输入是否被 token 截断（loader 4k 上限）
        trashed: 这一轮是否把会话移到 trash（仅 3/10/20 轮 classifier 触发可能为 True）
        trashed_reason: 人类可读原因（trashed=True 时有意义）
    """

    reply: str
    title_updated: bool = False
    summary_updated: bool = False
    context_truncated: bool = False
    trashed: bool = False
    trashed_reason: str = ""


# Classifier / Titler 的 checkpoint
_CLASSIFY_AT_TURNS = (3, 10, 20)
_TITLE_AT_TURNS = (10, 20)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class SessionManager:
    """会话管理的对外门面。

    设计要点：
      - **零状态**：不缓存任何东西，每次调用都直接打 storage。
      - **透明错误**：storage / LLM 异常原样往上抛
      - **不感知 UI**：不知道是 CLI / TUI / GUI 在调它
      - **LLM 注入**：构造时可指定 llm（测试用 Mock），默认走 get_default_provider()
    """

    # R9 9.4:默认并发度。__new__ 直接构造的实例(如测试 mock)也能继承这个默认值。
    _max_batch_workers: int = 4

    def __init__(self, llm: LLMProvider | None = None, max_batch_workers: int = 4):
        """R9 9.4:加 max_batch_workers 参,控制 batch_* 并发度。"""
        self.llm = llm if llm is not None else get_default_provider()
        self._max_batch_workers = max_batch_workers

    # ----- 列表 / 搜索 -----------------------------------------------------

    def touch(self, session_id: str) -> None:
        """记录一次访问（更新 heat / access_count / last_access，不产生对话）。

        与 chat() 不同：不调 LLM，不追加 turn，不触发 title/summary 更新。
        纯粹的热度追踪入口，供外部 hook（如 GA 的 ctx-track）调用。

        Raises:
            SessionNotFound: 会话不存在
        """
        storage.read_meta(session_id)  # 验证存在
        storage.update_access(session_id)

    def get_session_meta(self, session_id: str) -> SessionMeta:
        """读单个会话的 frontmatter(SessionMeta)。

        与 get() 区别:get() 读全文(frontmatter+body),本方法只读 frontmatter,
        适合批量列表/预览场景(轻量)。

        Raises:
            SessionNotFound: 会话不存在
        """
        return storage.read_meta(session_id)

    def batch_touch(self, session_ids: list[str]) -> None:
        """批量 touch,单条失败只 log 不阻塞。

        R9 9.4:多 item 时走 ThreadPoolExecutor 并发(默认 4 worker)。
        """
        if len(session_ids) <= 1:
            # 单元素快路径
            for sid in session_ids:
                try:
                    self.touch(sid)
                except Exception:
                    log.exception("batch_touch failed for %s", sid)
            return
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self._max_batch_workers) as ex:
            futures = [ex.submit(self.touch, sid) for sid in session_ids]
            for fut, sid in zip(futures, session_ids):
                try:
                    fut.result()
                except Exception:
                    log.exception("batch_touch failed for %s", sid)

    def batch_get_meta(self, session_ids: list[str]) -> dict[str, object]:
        """批量拉 meta,不存在的 sid 跳过(不抛 KeyError)。

        R9 9.4:多 item 时走 ThreadPoolExecutor 并发。
        """
        out: dict[str, object] = {}
        if len(session_ids) <= 1:
            for sid in session_ids:
                try:
                    out[sid] = self.get_session_meta(sid)
                except KeyError:
                    continue
                except Exception:
                    log.exception("batch_get_meta failed for %s", sid)
            return out
        from concurrent.futures import ThreadPoolExecutor
        results: dict[str, BaseException | object] = {}
        with ThreadPoolExecutor(max_workers=self._max_batch_workers) as ex:
            futures = {ex.submit(self.get_session_meta, sid): sid for sid in session_ids}
            for fut, sid in futures.items():
                try:
                    results[sid] = fut.result()
                except KeyError:
                    continue  # 不存在 → 跳过
                except Exception:
                    log.exception("batch_get_meta failed for %s", sid)
                    # 错误不进 out(原语义)
        out = {sid: r for sid, r in results.items() if not isinstance(r, BaseException)}
        return out

    def batch_chat(self, items: list[tuple[str, str]]) -> list["ChatResult"]:
        """顺序或并发执行 chat(),单条抛错不阻塞其它(返 ChatResult 带 error)。

        R9 9.4:多 item 时改用 ThreadPoolExecutor 并发,默认 4 worker。
        返回顺序与输入 items 顺序一致。
        """
        from mmi.agent.result import ChatResult as _ChatResult
        from mmi.agent.router import IntentType
        from concurrent.futures import ThreadPoolExecutor

        def _run(sid: str, msg: str) -> _ChatResult:
            try:
                return self.orchestrator.chat(sid, msg)
            except Exception as e:
                log.exception("batch_chat item failed: sid=%s", sid)
                return _ChatResult(
                    reply="",
                    intent=IntentType.UNKNOWN,
                    agent_id="",
                    validation=None,
                    trace_ids=[],
                    error=str(e),
                )

        if len(items) <= 1:
            return [_run(sid, msg) for sid, msg in items]

        results: list[_ChatResult | None] = [None] * len(items)
        with ThreadPoolExecutor(max_workers=self._max_batch_workers) as ex:
            futures = {ex.submit(_run, sid, msg): i for i, (sid, msg) in enumerate(items)}
            for fut, i in futures.items():
                # _run 已经隔离异常,这里 result() 不会抛
                results[i] = fut.result()
        return results  # type: ignore[return-value]

    def list_sessions(self, limit: int = 10) -> list[SessionMeta]:
        """返回前 N 个会话（Phase 4：按 heat 降序，同分时按 last_access 倒序）。

        Phase 1：直接按 last_access 排
        Phase 4：按 heat 排（ARCHITECTURE §8.4）——"最近重要"而非"最近用过"
        优化留给 Phase 3（loader / search）。
        """
        metas: list[SessionMeta] = []
        for sid in storage.list_session_ids():
            try:
                metas.append(storage.read_meta(sid))
            except (storage.SessionCorrupt, storage.SessionNotFound):
                # 损坏的会话不阻塞列表（容错：跳过 + 让用户后续 gc 清理）
                continue
        # 用 heat 排序（heat_module.sort_by_heat 内部用 heat 主键、last_access 兜底）
        metas = heat_module.sort_by_heat(metas, descending=True)
        return metas[:limit]

    def search(self, query: str) -> list[SessionMeta]:
        """按 title 模糊匹配（Phase 1：大小写不敏感的子串匹配）。

        Phase 5 会升级到 rapidfuzz 模糊匹配。
        """
        if not query:
            return []
        q = query.lower()
        hits: list[SessionMeta] = []
        for m in self.list_sessions(limit=10_000):
            if q in m.title.lower():
                hits.append(m)
        return hits

    # ----- 增 / 查 / 改 ----------------------------------------------------

    def create(self, title: str = DEFAULT_TITLE) -> str:
        """创建新会话，返回 session_id。

        写空 frontmatter + 空 body 到磁盘。
        """
        from mmi.core import paths as _paths_mod  # local import so MMI_HOME is read fresh
        _paths_mod.ensure_dirs()
        sid = new_session_id()
        s = Session.empty(sid, title=title)
        storage.write_session(s)
        return sid

    def get(self, session_id: str) -> Session:
        """读全文（frontmatter + body）。"""
        return storage.read_session(session_id)

    def persist_turn(
        self,
        session_id: str,
        user_input: str,
        reply: str,
        *,
        language: str | None = None,
    ) -> ChatResult:
        """3.3 新增:Orchestrator 用的轻量持久化。

        适用:agent 已经生成了 reply,只需要把 turn 写盘 + 后台摘要调度。
        不构造 LLM messages(不需要 context builder / summarizer 触发条件检查)。

        Args:
            session_id: 目标会话
            user_input: 用户消息
            reply: agent 已生成的回复
            language: 输出语言(默认读 i18n.get_lang())

        Returns:
            ChatResult(reply=reply, 其他标志全 False)
        """
        if language is None:
            from . import i18n
            language = i18n.get_lang()
        # 验证会话存在
        storage.read_meta(session_id)
        # 追加 turn(内部已加锁)
        s = storage.append_turn(session_id, user_input, reply)
        # 跨会话记忆入库
        try:
            summarizer._schedule_memory_store(session_id)
        except Exception:
            pass
        # 摘要检查 + 调度
        try:
            will_update = summarizer.should_update_summary(s.meta, s.body)
        except Exception:
            will_update = False
        if will_update:
            summarizer.schedule_summary_update(
                session_id, self.llm, language=language
            )
        # heat 重算
        self._recompute_heat(session_id)
        return ChatResult(
            reply=reply,
            title_updated=False,
            summary_updated=will_update,
            context_truncated=False,
            trashed=False,
            trashed_reason="",
        )

    def chat(self, session_id: str, user_input: str, *, language: str | None = None) -> ChatResult:
        """对话入口（Phase 3：走 loader + summarizer）。

        流程：
          1. 走 context.build_context 构造 LLM messages
             （system[+summary] → hits → recent → current user）
          2. 调 LLM
          3. 追加 turn 到 body
          4. 摘要更新检查（§8.3 触发条件）
          5. 检查 turn count：
             - 3 / 10 / 20 → classifier（命中 trash 规则则移到 trash 目录）
             - 10 / 20 → titler（重命名）
          6. 返回 ChatResult

        Args:
            session_id: 目标会话
            user_input: 用户输入
            language: 输出语言（默认读 i18n.get_lang()）

        Returns:
            ChatResult（reply + trashed + title_updated + summary_updated + context_truncated）

        Raises:
            SessionNotFound: 会话不存在
            LLMError: LLM 不可用且降级也失败
        """
        if language is None:
            from . import i18n
            language = i18n.get_lang()

        # 先验证会话存在（不然 LLM 跑完才发现白跑了）
        storage.read_meta(session_id)

        # 1) 走 loader 构造 messages
        config = context.LoaderConfig()
        ctx = context.build_context_detailed(
            session_id, user_input, config=config, language=language
        )
        messages = ctx.messages
        context_truncated = ctx.truncated

        # 2) 调 LLM（失败时降级：错误信息作为 reply，不抛给 UI）
        try:
            reply = self.llm.chat(messages, max_tokens=4096, temperature=0.7)
        except LLMError as e:
            reply = f"[LLM error: {e}]"

        # 3) 追加 turn
        s = storage.append_turn(session_id, user_input, reply)

        # 4) 跨会话记忆入库(每轮都跑,不等摘要)
        #   短会话(<20 轮/5000 字/24h)不触发摘要,但记忆照样要进库
        #   content_hash 已做去重,重复 body 不会重复入库
        try:
            summarizer._schedule_memory_store(session_id)
        except Exception:
            # store_memory 自身已静默,这里再兜一次
            pass

        # 5) 摘要更新检查(§8.3)—— should_update 同步判,update 后台跑
        #   Phase 6:避免 LLM 慢调用阻塞 chat 主流程;UI 看到 summary_updated
        #   是"将要更新"的乐观信号,实际落盘在后台。
        try:
            will_update = summarizer.should_update_summary(s.meta, s.body)
        except Exception:
            will_update = False
        if will_update:
            summarizer.schedule_summary_update(
                session_id, self.llm, language=language
            )
        summary_updated = will_update

        # 6) 检查点
        trashed = False
        trashed_reason = ""
        title_updated = False

        n_user = storage.count_user_turns(s.body)

        # Classifier checkpoint
        if n_user in _CLASSIFY_AT_TURNS:
            turns = storage.parse_turns(s.body)
            result = cls_module.classify_session(turns, self.llm, language=language)
            if cls_module.is_trash(result):
                storage.move_to_trash(session_id)
                trashed = True
                trashed_reason = result.reason

        # Titler checkpoint（在 trash 检查后：万一被 trash 了就不再 titler）
        if (not trashed) and n_user in _TITLE_AT_TURNS:
            turns = storage.parse_turns(s.body)
            new_title = titler.generate_title(turns, self.llm, language=language)
            cur = s.meta.title
            if new_title and new_title != cur:
                s.meta.title = new_title
                storage.write_session(s)
                title_updated = True

        # 6) heat 重算（Phase 4：ARCHITECTURE §8.4）
        #    被 trash 的会话不重算（不参与主列表排序）
        if not trashed:
            self._recompute_heat(session_id)

        return ChatResult(
            reply=reply,
            title_updated=title_updated,
            summary_updated=summary_updated,
            context_truncated=context_truncated,
            trashed=trashed,
            trashed_reason=trashed_reason,
        )

    # ----- 删 / 归档 / 杂项 ------------------------------------------------

    def archive(self, session_id: str) -> None:
        """归档到 trash（不硬删，可恢复）。"""
        storage.move_to_trash(session_id)

    def trash(self, session_id: str, *, reason: str = "") -> None:
        """把会话移到 trash（Phase 2 新增的公开方法）。

        区别于 archive()：语义上 archive 是"用户主动归档"，trash 是
        "系统判定为杂项"（classifier 自动调用）。Phase 2 两者的实现
        一样（都走 storage.move_to_trash），但分开命名让调用方意图清晰。

        Args:
            session_id: 要移走的会话
            reason: 触发原因（仅日志用，Phase 2 不持久化）
        """
        storage.move_to_trash(session_id)

    def delete(self, session_id: str) -> None:
        """硬删（不可恢复）。"""
        storage.delete_session(session_id)

    # ----- 内部：heat 重算 --------------------------------------------------

    def _recompute_heat(self, session_id: str) -> None:
        """读最新 frontmatter → 算 heat + state → 写回。

        行为：
          - 在文件锁内重读 + 算 + 写，避免与并发 write_session（如后台
            update_summary）产生 lost-update 竞争
          - 只有 heat / state / cold_since 任一变化时才写盘
          - 文件丢失/损坏时静默跳过（不影响 chat 主流程）
          - 由 chat() 末尾调用，也可独立调用（如 list 时惰性补算 —— 暂不做）
        """
        try:
            with storage._exclusive_lock(session_id):
                # 锁内重读：防止和 update_summary 等并发写入冲突
                s = storage.read_session(session_id)
        except (storage.SessionNotFound, storage.SessionCorrupt):
            return
        old_heat = s.meta.heat
        old_state = s.meta.state
        old_cold_since = s.meta.cold_since
        # P2-9:传 total_turns 让 heat 算 content_weight
        n_user_turns = s.body.count("**User:**")
        heat_module.apply_heat_and_state(s.meta, total_turns=n_user_turns)
        if (
            s.meta.heat != old_heat
            or s.meta.state != old_state
            or s.meta.cold_since != old_cold_since
        ):
            try:
                with storage._exclusive_lock(session_id):
                    # 再读一次：若 update_summary 在我们算 heat 期间写了
                    # summary，把 in-memory 的 heat/state 合并到最新视图里
                    s2 = storage.read_session(session_id)
                    s2.meta.heat = s.meta.heat
                    s2.meta.state = s.meta.state
                    s2.meta.cold_since = s.meta.cold_since
                    s2.meta.updated_at = s.meta.updated_at
                    # 直接 _atomic_write：write_session 会再 lock 死锁
                    storage._atomic_write(
                        storage.session_path(session_id),
                        storage._dump_frontmatter(s2.meta) + s2.body,
                    )
            except (storage.SessionNotFound, storage.SessionCorrupt, OSError):
                pass
