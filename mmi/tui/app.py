"""mmi.tui.app —— MMI TUI 入口（键盘切换视图，无 Tab 栏）。"""

from __future__ import annotations

from textual.app import App
from textual.containers import Vertical
from textual.widgets import Static

from ..core import paths as paths_module
from ..core.config import get_theme, set_theme
from ..core.manager import SessionManager
from .history import HistoryStore
from .screens.list import SessionListView
from .screens.chat import ChatView
from .theme_css import DARK_CSS, LIGHT_CSS

__all__ = ["CTrimApp", "run_tui"]


class CTrimApp(App):
    """MMI TUI 应用程序。"""
    
    # 主题设置：'dark' 或 'light'
    _theme = "dark"

    BINDINGS = [
        ("escape", "show_list", "列表"),
        ("f2", "show_list", "列表"),
        ("f3", "show_chat", "聊天"),
        ("t", "toggle_theme", "切换主题"),
    ]

    def __init__(self, mgr: SessionManager | None = None) -> None:
        super().__init__()
        self.mgr = mgr if mgr is not None else SessionManager()
        self._history = HistoryStore()
        self._active_session_id: str | None = None
        # 从配置加载主题设置
        self._theme = get_theme()

    def compose(self):
        yield Static("● ● ●  MMI — memory mesh interface", id="term-titlebar")
        with Vertical(id="main-content"):
            yield SessionListView(id="list-view")
            yield ChatView(id="chat-view")

    def on_mount(self) -> None:
        try:
            paths_module.ensure_dirs()
        except OSError:
            pass
        self._history.load()
        self._apply_theme()
        self._show_list_view()

    def _apply_theme(self) -> None:
        """应用当前主题 CSS。"""
        css = DARK_CSS if self._theme == "dark" else LIGHT_CSS
        self.stylesheet.source = css
        self.stylesheet.reparse()
        self.refresh()

    def action_toggle_theme(self) -> None:
        """切换暗色/亮色主题。"""
        self._theme = "light" if self._theme == "dark" else "dark"
        # 保存主题设置到配置
        set_theme(self._theme)
        self._apply_theme()

    def _show_list_view(self) -> None:
        try:
            self.query_one("#list-view").display = True
            self.query_one("#chat-view").display = False
        except Exception:
            pass

    def _show_chat_view(self) -> None:
        try:
            self.query_one("#list-view").display = False
            self.query_one("#chat-view").display = True
        except Exception:
            pass

    def action_show_list(self) -> None:
        self._show_list_view()
        try:
            self.query_one("#list-view", SessionListView).refresh_sessions()
        except Exception:
            pass

    async def show_chat(self, session_id: str | None = None) -> None:
        if session_id:
            self._active_session_id = session_id
        if not self._active_session_id:
            return
        self._show_chat_view()
        try:
            self.query_one("#chat-view", ChatView).load_session(self._active_session_id)
        except Exception:
            pass

    async def action_show_chat(self) -> None:
        await self.show_chat()

    def action_new_session(self) -> None:
        sid = self.mgr.create()
        self._active_session_id = sid
        self._show_chat_view()
        try:
            self.query_one("#chat-view", ChatView).load_session(sid)
        except Exception:
            pass

    @property
    def active_session_id(self) -> str | None:
        return self._active_session_id


def run_tui() -> int:
    app = CTrimApp()
    try:
        app.run()
    finally:
        try:
            app._history.save()
        except Exception:
            pass
    return 0
