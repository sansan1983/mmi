"""mmi.tui —— 终端 UI 子包。

ARCHITECTURE Phase 5：TUI 是 core 之上的纯渲染+导航层。
入口：`mmi.tui.run_tui()`
"""

from .app import CTrimApp, run_tui

__all__ = ["CTrimApp", "run_tui"]
