"""mmi.tui.app —— textual App 入口。

ARCHITECTURE Phase 5：
  - 持有 SessionManager（每个进程一个）
  - 启动屏 = SessionListScreen
  - 不感知具体 Screen 之外的逻辑
  - 退出时持久化命令历史
"""

from __future__ import annotations

from textual.app import App

from mmi.core.manager import SessionManager
from ..core import paths as paths_module
from .history import HistoryStore
from .screens.list import SessionListScreen
from .theme_css import THEME_CSS

__all__ = ["CTrimApp", "run_tui"]


class CTrimApp(App):
    """C-Trim TUI 入口。"""

    CSS = THEME_CSS

    def __init__(self, mgr: SessionManager | None = None) -> None:
        super().__init__()
        self.mgr = mgr if mgr is not None else SessionManager()
        self._history = HistoryStore()

    def on_mount(self) -> None:
        # 确保数据目录
        try:
            paths_module.ensure_dirs()
        except OSError:
            pass
        # 加载历史
        self._history.load()
        # 推启动屏
        self.push_screen(SessionListScreen())


def run_tui() -> int:
    """CLI 入口：构造 App 跑起来。"""
    app = CTrimApp()
    try:
        app.run()
    finally:
        # 退出时保存历史
        try:
            app._history.save()
        except Exception:
            pass
    return 0
