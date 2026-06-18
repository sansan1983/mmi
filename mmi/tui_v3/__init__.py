"""mmi.tui_v3 —— MMI Textual-based TUI (consolidated v3, 包入口)。

Port of GA's tui_v3 architecture, adapted for mmi's SessionManager.
Run: mmi tui-python  or  python -m mmi.tui_v3

P2-2: 修复流式内容持久化、清理未使用变量、增加 /delete 和 /export 命令。
Bugfix: 回车进入历史会话、自动滚动、斜杠命令补全。

子模块结构:
  - _bridge:    ManagerBridge (SessionManager → TUI 适配层)
  - _messages:  StreamChunk + StreamDone (TUI 自定义 Message)
  - screens:    5 Screen (SessionList/Chat/NewSession/Search/Command) + count_tokens
  - _app:       MmiTui 主 App + run_tui 入口

向后兼容:
  - 之前所有 `from mmi.tui_v3 import X` 仍工作
  - 模块名仍是 `mmi.tui_v3`(从 .py 变成包)
  - `from mmi.tui_v3 import run_tui` 仍工作(cli/commands/tui.py 用)
"""

from __future__ import annotations

from mmi.tui_v3._app import MmiTui, run_tui
from mmi.tui_v3._bridge import ManagerBridge
from mmi.tui_v3._messages import StreamChunk, StreamDone
from mmi.tui_v3.screens import (
    LIST_TITLE,
    ChatScreen,
    CommandScreen,
    NewSessionScreen,
    SearchScreen,
    SessionListScreen,
    count_tokens,
)

__all__ = [
    "ManagerBridge",
    "StreamChunk",
    "StreamDone",
    "SessionListScreen",
    "ChatScreen",
    "NewSessionScreen",
    "SearchScreen",
    "CommandScreen",
    "MmiTui",
    "run_tui",
    "count_tokens",
    "LIST_TITLE",
]
