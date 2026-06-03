"""mmi.tui.screens.list —— 启动屏（会话列表）。

ARCHITECTURE Phase 5：
  - on_mount 拉 mgr.list_sessions(limit=10)
  - ListView 显示每条 [heat 12.0] [active] postgres-sharding
  - 快捷键：Enter 进入 / n 新建 / s 搜索 / q 退出
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, ListItem, ListView, Static

from ...core import paths, storage
from ...core.i18n import t
from ...core.session import SessionMeta

if TYPE_CHECKING:
    from ..app import CTrimApp


__all__ = ["SessionListScreen"]


class _SessionItem(ListItem):
    """ListView 的一行（带 SessionMeta）。"""

    def __init__(self, meta: SessionMeta, index: int):
        super().__init__()
        self._meta = meta
        self._index = index
        if meta.title:
            label = t(
                "tui.list.entry",
                index=index,
                title=meta.title,
                heat=f"{meta.heat:.1f}",
                state=meta.state,
            )
        else:
            label = t(
                "tui.list.entry.unnamed",
                index=index,
                heat=f"{meta.heat:.1f}",
                state=meta.state,
            )
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(self._label)

    @property
    def meta(self) -> SessionMeta:
        return self._meta


class SessionListScreen(Screen):
    """TUI 启动屏：前 N 条会话。"""

    BINDINGS = [
        Binding("n", "new_session", "新建"),
        Binding("s", "search", "搜索"),
        Binding("q", "quit_app", "退出"),
        Binding("enter", "enter_session", "进入", show=False),
    ]

    DEFAULT_CSS = """
    SessionListScreen {
        background: #1a1b26;
    }
    SessionListScreen ListView {
        height: 1fr;
        background: #1a1b26;
    }
    SessionListScreen ListView > ListItem {
        padding: 0 1;
    }
    SessionListScreen ListView > ListItem.--highlight {
        background: #2ac3de;
        color: #1a1b26;
    }
    SessionListScreen .empty-pane {
        align: center middle;
        height: 1fr;
        color: #565f89;
    }
    SessionListScreen .empty-pane .hint {
        color: #7aa2f7;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._items: list[_SessionItem] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Vertical(id="list-container")
        yield Footer()

    def on_mount(self) -> None:
        # Header 标题
        try:
            self.title = t("tui.list.title")
        except Exception:
            pass
        self._load_sessions()

    def _load_sessions(self) -> None:
        container = self.query_one("#list-container", Vertical)
        # 移除旧子节点
        for child in list(container.children):
            child.remove()
        app: "CTrimApp" = self.app  # type: ignore[assignment]
        sessions = app.mgr.list_sessions(limit=10)
        if not sessions:
            from textual.containers import Vertical as V

            empty = V(classes="empty-pane")
            container.mount(empty)
            empty.mount(Static(t("tui.list.empty")))
            empty.mount(Static(t("tui.list.empty.hint"), classes="hint"))
            return
        items: list[ListItem] = []
        for i, meta in enumerate(sessions, 1):
            it = _SessionItem(meta, i)
            self._items.append(it)
            items.append(it)
        lv = ListView(*items, id="sessions-list")
        container.mount(lv)
        lv.index = 0

    # ----- Actions ------------------------------------------------------

    def action_new_session(self) -> None:
        app: "CTrimApp" = self.app  # type: ignore[assignment]
        sid = app.mgr.create()
        from .chat import ChatScreen

        self.app.push_screen(ChatScreen(sid))

    def action_search(self) -> None:
        from .search import SearchScreen

        self.app.push_screen(SearchScreen())

    def action_quit_app(self) -> None:
        self.app.exit()

    def action_enter_session(self) -> None:
        # 拿到 ListView 高亮项
        try:
            lv = self.query_one("#sessions-list", ListView)
        except Exception:
            return
        idx = lv.index
        if idx is None or idx >= len(self._items):
            return
        meta = self._items[idx].meta
        from .chat import ChatScreen

        self.app.push_screen(ChatScreen(meta.session_id))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """ListView 内 Enter 触发：直接走 enter_session 动作。

        ListView 把 Enter 路由成 Selected 事件而不是冒泡到 Screen binding，
        所以必须在这里挂 handler。Screen-level Binding 仍保留供键盘直达用。
        """
        self.action_enter_session()
