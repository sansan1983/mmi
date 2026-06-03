"""mmi.tui.screens.search —— 实时 fuzzy 搜索屏。

ARCHITECTURE Phase 5：
  - Input.Changed 触发 fuzzy 过滤（防抖 150ms）
  - rapidfuzz.partial_ratio（阈值 60）
  - 性能预算 < 100ms（mgr.list_sessions(limit=10_000)）
  - Enter 选中 → push ChatScreen
  - Esc / q 关闭
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, ListItem, ListView, Static

from ...core import paths
from ...core.i18n import t
from ...core.session import SessionMeta

if TYPE_CHECKING:
    from ..app import CTrimApp


__all__ = ["SearchScreen"]


# 防抖时间（秒）
_DEBOUNCE_S = 0.15
_FUZZY_THRESHOLD = 60


class _SearchItem(ListItem):
    def __init__(self, meta: SessionMeta, score: int):
        super().__init__()
        self._meta = meta
        self._score = score
        if meta.title:
            label = t(
                "tui.list.entry",
                index=score,
                title=meta.title,
                heat=f"{meta.heat:.1f}",
                state=meta.state,
            )
        else:
            label = t(
                "tui.list.entry.unnamed",
                index=score,
                heat=f"{meta.heat:.1f}",
                state=meta.state,
            )
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(self._label)

    @property
    def meta(self) -> SessionMeta:
        return self._meta


class SearchScreen(Screen):
    """实时 fuzzy 搜索屏。"""

    BINDINGS = [
        Binding("escape", "close", "返回", show=False),
        Binding("q", "close", "返回", show=False),
    ]

    DEFAULT_CSS = """
    SearchScreen {
        background: #1a1b26;
    }
    SearchScreen #search-input-bar {
        height: 3;
        padding: 0 1;
    }
    SearchScreen Input {
        background: #24283b;
        border: tall #7aa2f7;
    }
    SearchScreen Input:focus {
        border: tall #bb9af7;
    }
    SearchScreen #results {
        height: 1fr;
        background: #1a1b26;
    }
    SearchScreen .hint {
        color: #565f89;
        padding: 0 2;
    }
    SearchScreen .empty-msg {
        color: #565f89;
        padding: 0 2;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._all_metas: list[SessionMeta] = []
        self._items: list[_SearchItem] = []
        self._debounce_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="search-input-bar"):
            yield Input(placeholder=t("tui.search.placeholder"), id="search-input")
        with Vertical(id="results"):
            yield Static(t("tui.search.hint"), classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.title = t("tui.search.title")
        except Exception:
            pass
        # 拉所有候选（mgr.list_sessions 已按 heat 排好）
        app: "CTrimApp" = self.app  # type: ignore[assignment]
        self._all_metas = app.mgr.list_sessions(limit=10_000)
        # 焦点
        try:
            self.query_one("#search-input", Input).focus()
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        # 防抖
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = asyncio.create_task(self._refresh_later(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # 选中第一个结果
        try:
            lv = self.query_one("#results-list", ListView)
        except Exception:
            return
        idx = lv.index
        if idx is None or idx >= len(self._items):
            return
        meta = self._items[idx].meta
        from .chat import ChatScreen

        self.app.push_screen(ChatScreen(meta.session_id))

    async def _refresh_later(self, q: str) -> None:
        await asyncio.sleep(_DEBOUNCE_S)
        self._refresh_results(q)

    def _refresh_results(self, q: str) -> None:
        container = self.query_one("#results", Vertical)
        for child in list(container.children):
            child.remove()
        if not q:
            container.mount(Static(t("tui.search.hint"), classes="hint"))
            return
        from ...core.search import fuzzy_match_scores

        scored = fuzzy_match_scores(
            self._all_metas,
            q,
            key=lambda m: m.title or "",
            threshold=_FUZZY_THRESHOLD,
        )
        # heat 兜底（同分时按热度排）
        scored.sort(key=lambda t: (t[0], t[1].heat), reverse=True)
        if not scored:
            container.mount(Static(t("tui.search.empty"), classes="empty-msg"))
            return
        items: list[ListItem] = []
        self._items = []
        for score, m in scored:
            it = _SearchItem(m, score)
            self._items.append(it)
            items.append(it)
        lv = ListView(*items, id="results-list")
        container.mount(lv)
        lv.index = 0

    # ----- actions ------------------------------------------------------

    def action_close(self) -> None:
        self.app.pop_screen()
