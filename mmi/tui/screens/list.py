"""mmi.tui.screens.list —— 会话列表视图。

网格风格（mockup 设计），单 Static + 预格式化文本。

快捷键：↑↓ 选择 · Enter 进入 · n 新建 · s 搜索 · q 退出
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from ...core.i18n import t
from ...core import config as cfg_module
from ...core.session import SessionMeta

if TYPE_CHECKING:
    from ..app import CTrimApp

__all__ = ["SessionListView"]

# 列宽（字符格数，中文=2）
_COL_IDX = 4
_COL_HEAT = 8
_COL_STATE = 8
_COL_MODEL = 12
_COL_TITLE = 36


def _width(s: str) -> int:
    """计算终端显示宽度（CJK 字符算2格）。"""
    w = 0
    for ch in s:
        w += 2 if ord(ch) >= 0x2e80 else 1
    return w

def _lpad(s: str, w: int) -> str:
    """左对齐（右侧补空格）。"""
    return s + ' ' * max(0, w - _width(s))


def _rpad(s: str, w: int) -> str:
    """右对齐（左侧补空格）。"""
    return ' ' * max(0, w - _width(s)) + s


def _fmt_item(index: int, title: str, heat: float, state: str, model: str) -> str:
    idx = f"{index:>{_COL_IDX-1}}"
    ttl = title if _width(title) <= _COL_TITLE else title[:_COL_TITLE-3] + "..."
    ht = f"{heat:<{_COL_HEAT}.1f}"
    st = f"{state:<{_COL_STATE}}"
    md = f"{model:<{_COL_MODEL}}"
    return f"{idx}  {_lpad(ttl, _COL_TITLE)}  {ht}  {st}  {md}"


def _fmt_header() -> str:
    idx = f"{'#':>{_COL_IDX-1}}"
    return f" {idx}  {_lpad('标题', _COL_TITLE)}  {_lpad('热度', _COL_HEAT)}  {_lpad('状态', _COL_STATE)}  {_lpad('模型', _COL_MODEL)}"

# ---------------------------------------------------------------------------
# 列表视图
# ---------------------------------------------------------------------------

class SessionListView(Vertical):
    """会话列表视图。单 Static 行 + 预格式化文本。"""

    BINDINGS = [
        ("down", "cursor_down", "Down"),
        ("up", "cursor_up", "Up"),
        ("enter", "enter", "Enter"),
        ("n", "new", "New"),
        ("s", "search", "Search"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.can_focus = True
        self._items: list[SessionMeta] = []
        self._selected: int = 0
        self._row_widgets: list[Static] = []
    def compose(self) -> ComposeResult:
        # 顶栏（单 Static，避免 Horizontal 多 Static 不渲染的问题）
        yield Static("", id="list-top")
        # 表头
        yield Static(_fmt_header(), id="list-header")
        # 列表区
        yield VerticalScroll(id="list-items")
        # 空态
        with Vertical(id="empty-state"):
            yield Static("~ ~ ~", classes="empty-big")
            yield Static(t("tui.list.empty"), classes="empty-text")
            yield Static(t("tui.list.empty.hint"), classes="empty-hint")
        # 底栏
        yield Static("  ↑↓ 选择  ·  Enter 进入  ·  n 新建  ·  s 搜索  ·  q 退出  ", id="list-footer")

    def on_mount(self) -> None:
        self.focus()
        self.refresh_sessions()

    def refresh_sessions(self) -> None:
        try:
            app: "CTrimApp" = self.app  # type: ignore[assignment]
            self._items = app.mgr.list_sessions(limit=100)
        except Exception:
            self._items = []
        self._rebuild()

    def _rebuild(self) -> None:
        container = self.query_one("#list-items", VerticalScroll)
        container.remove_children()
        self._row_widgets.clear()
        empty_state = self.query_one("#empty-state", Vertical)
        if not self._items:
            container.display = False
            empty_state.display = True
            return
        container.display = True
        empty_state.display = False
        for i, meta in enumerate(self._items):
            title = meta.title or "(untitled)"
            text = _fmt_item(i + 1, title, meta.heat, meta.state,
                             cfg_module.get_default_model())
            w = Static(text, classes="list-row")
            self._row_widgets.append(w)
            container.mount(w)
        self._select(0)
        # 更新顶栏计数
        try:
            top = self.query_one("#list-top", Static)
            top.update(f"会话历史 · {len(self._items)} 个会话")
        except Exception:
            pass
            pass

    def _select(self, idx: int) -> None:
        if not self._row_widgets:
            return
        idx = max(0, min(idx, len(self._row_widgets) - 1))
        for w in self._row_widgets:
            w.remove_class("-sel")
        self._row_widgets[idx].add_class("-sel")
        self._selected = idx
        try:
            container = self.query_one("#list-items", VerticalScroll)
            container.scroll_to_widget(self._row_widgets[idx])
        except Exception:
            pass

    def action_cursor_down(self) -> None:
        if self._row_widgets:
            self._select(self._selected + 1)

    def action_cursor_up(self) -> None:
        if self._row_widgets:
            self._select(self._selected - 1)

    async def action_enter(self) -> None:
        if not self._row_widgets:
            return
        meta = self._items[self._selected]
        try:
            app: "CTrimApp" = self.app  # type: ignore[assignment]
            await app.show_chat(meta.session_id)
        except Exception:
            pass

    async def action_new(self) -> None:
        try:
            app: "CTrimApp" = self.app  # type: ignore[assignment]
            app.action_new_session()
        except Exception:
            pass

    def action_search(self) -> None:
        from .search import SearchScreen
        self.app.push_screen(SearchScreen())

    def action_quit(self) -> None:
        self.app.exit()