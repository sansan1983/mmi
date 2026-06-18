"""mmi.tui_v3._app —— MmiTui 主 App + run_tui 入口。

依赖项:_bridge, screens。
被依赖:__init__.py re-export + cli/commands/tui.py。
"""

from __future__ import annotations

import sys

from textual.app import App

from mmi.tui_v3._bridge import ManagerBridge
from mmi.tui_v3.screens import SessionListScreen


class MmiTui(App[None]):
    """MMI TUI v3 — Main Application."""

    TITLE = "MMI TUI v3"
    SUB_TITLE = "v0.1.0"

    CSS = """
    Screen {
        background: #1a1b26;
        color: #c0caf5;
    }

    #tui-titlebar, #tui-chat-titlebar {
        height: 2;
        background: #0f0f17;
        color: #7aa2f7;
        text-align: center;
        text-style: bold;
        border-bottom: solid #2a2b3e;
    }

    #tui-list-info {
        height: 1;
        background: #1a1b26;
        color: #565f89;
        text-align: center;
    }

    #tui-session-list {
        height: 1fr;
        border: none;
    }

    ListView {
        background: #1a1b26;
    }

    ListItem {
        padding: 0 1;
    }

    ListItem > Static {
        color: #c0caf5;
    }

    ListItem:hover, ListItem:focus {
        background: #2a2b3e;
    }

    #tui-footer, #tui-chat-footer {
        height: 1;
        background: #0f0f17;
        color: #565f89;
        text-align: center;
    }

    #tui-chat-log {
        height: 1fr;
        background: #1a1b26;
        color: #c0caf5;
        border: none;
        padding: 0 1;
        overflow-y: scroll;
    }

    /* Bug #3 FIX: 命令补全提示区域 */
    #tui-completions {
        height: auto;
        max-height: 8;
        background: #16161e;
        color: #a9b1d6;
        border: solid #2a2b3e;
        padding: 0 1;
        overflow-y: auto;
    }
    #tui-completions.completions-hidden {
        display: none;
    }
    #tui-completions.completions-visible {
        display: block;
    }

    #tui-chat-input {
        height: 3;
        background: #0f0f17;
        color: #c0caf5;
        border: solid #2a2b3e;
    }

    #tui-chat-input:focus {
        border: solid #7aa2f7;
    }

    #new-session-dialog, #search-dialog, #cmd-dialog {
        width: 50;
        height: auto;
        border: solid #7aa2f7;
        background: #1a1b26;
        padding: 1 2;
        margin: 4 8;
    }

    #new-session-title, #search-title, #cmd-title {
        text-style: bold;
        color: #7aa2f7;
        padding-bottom: 1;
    }

    #new-session-input, #search-input, #cmd-input {
        background: #0f0f17;
        color: #c0caf5;
        border: solid #2a2b3e;
    }

    #new-session-input:focus, #search-input:focus, #cmd-input:focus {
        border: solid #7aa2f7;
    }

    #new-session-buttons {
        height: auto;
        align: center middle;
        padding-top: 1;
    }

    Button {
        background: #2a2b3e;
        color: #c0caf5;
        margin: 0 1;
    }

    Button:hover {
        background: #7aa2f7;
        color: #1a1b26;
    }

    #search-results, #cmd-results {
        height: 12;
        border: none;
    }

    .empty-msg {
        color: #565f89;
        text-align: center;
        padding: 2;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.bridge = ManagerBridge()

    def on_mount(self) -> None:
        self.push_screen(SessionListScreen())


def run_tui() -> int:
    """Entry point: run the TUI."""
    app = MmiTui()
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[tui_v3] Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_tui())
