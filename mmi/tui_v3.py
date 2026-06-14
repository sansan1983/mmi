"""mmi.tui_v3 — MMI Textual-based TUI (consolidated v3).

Port of GA's tui_v3 architecture, adapted for mmi's SessionManager.
Run: mmi tui-python  or  python -m mmi.tui_v3

P2-2: 修复流式内容持久化、清理未使用变量、增加 /delete 和 /export 命令。
Bugfix: 回车进入历史会话、自动滚动、斜杠命令补全。
"""

from __future__ import annotations

import os
import re
import sys
from typing import TYPE_CHECKING, Iterator

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, Label, ListItem, ListView, RichLog, Static

from mmi.core import config as cfg_module
from mmi.core.i18n import t as _t
from mmi.core.manager import SessionManager
from mmi.core.session import SessionMeta

# ---------------------------------------------------------------------------
# ManagerBridge
# ---------------------------------------------------------------------------


class ManagerBridge:
    """Thin wrapper around SessionManager for TUI use."""

    def __init__(self) -> None:
        self.mgr = SessionManager()

    def list_sessions(self, limit: int = 100) -> list[SessionMeta]:
        return self.mgr.list_sessions(limit=limit)

    def create_session(self, title: str = "untitled") -> str:
        return self.mgr.create(title=title)

    def get_session_body(self, sid: str) -> str:
        try:
            s = self.mgr.get(sid)
            return s.body if s else ""
        except Exception:
            return ""

    def delete_session(self, session_id: str) -> None:
        try:
            self.mgr.delete(session_id)
        except Exception:
            pass

    def stream_chat(self, session_id: str, user_input: str) -> Iterator[str]:
        yield from self.mgr.stream_chat(session_id, user_input)

    def search(self, query: str) -> list[SessionMeta]:
        return self.mgr.search(query)


# ---------------------------------------------------------------------------
# Stream Messages
# ---------------------------------------------------------------------------


class StreamChunk(Message):
    def __init__(self, chunk: str) -> None:
        super().__init__()
        self.chunk = chunk


class StreamDone(Message):
    def __init__(self, reply: str) -> None:
        super().__init__()
        self.reply = reply


# 命令列表常量
_COMMANDS: dict[str, str] = {
    "quit": "退出程序",
    "back": "返回上一页",
    "delete": "删除当前会话",
    "export": "导出为 Markdown",
    "model": "切换模型 (/model <名称>)",
    "refresh": "刷新当前会话",
    "help": "显示帮助",
}

# ---------------------------------------------------------------------------
# Session List Screen
# ---------------------------------------------------------------------------


LIST_TITLE = _t('tui.list.title', default='会话列表')


class SessionListScreen(Screen[None]):
    """Main screen showing session list."""

    BINDINGS = [
        Binding("enter", "open_session", "Open"),
        Binding("n", "new_session", "New"),
        Binding("s", "search", "Search", show=False),
        Binding("q", "quit", "Quit"),
        Binding("slash", "command_palette", "Command"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._items: list[SessionMeta] = []

    def compose(self) -> ComposeResult:
        yield Static(
            f" MMI TUI v3 — {LIST_TITLE} ",
            id="tui-titlebar",
        )
        yield Static("", id="tui-list-info")
        yield ListView(id="tui-session-list")
        yield Static(
            "  ↑↓ 选择 · Enter 进入 · n 新建 · / 命令 · q 退出  ",
            id="tui-footer",
        )

    def on_mount(self) -> None:
        self._load()
        # Bug #1 FIX: DOM 完全挂载后再聚焦，确保 ListView 能捕获 Enter
        lv = self.query_one("#tui-session-list", ListView)
        self.set_timer(0.05, lambda: lv.focus())

    def _load(self) -> None:
        bridge: ManagerBridge = self.app.bridge
        try:
            self._items = bridge.list_sessions(limit=100)
            self._items.sort(key=lambda m: m.heat or 0.0, reverse=True)
        except Exception:
            self._items = []
        lv = self.query_one("#tui-session-list", ListView)
        lv.clear()
        if not self._items:
            lv.mount(ListItem(Static("~ ~ ~ 暂无会话 ~ ~ ~", classes="empty-msg")))
            self.query_one("#tui-list-info", Static).update("会话历史 · 0 个会话")
            return
        for i, meta in enumerate(self._items):
            title = (meta.title or "(untitled)").replace("\n", " ")
            info = f"{i+1:>3}  {title[:36]:36}  heat:{meta.heat:<5.1f}  [{meta.state}]"
            lv.mount(ListItem(Static(info)))
        if self._items:
            lv.index = 0  # Bug #1 FIX: 默认选中第一条
        self.query_one("#tui-list-info", Static).update(
            f"会话历史 · {len(self._items)} 个会话"
        )
        # Bug #1 FIX: 自动聚焦 ListView 使 Enter 生效
        lv.focus()

    # Bug #1 FIX: 必须监听 ListView.Selected 事件，这是 ListView Enter 键的标准路径
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is None:
            return
        idx = event.list_view.index
        if idx is not None and idx < len(self._items):
            meta = self._items[idx]
            self.app.push_screen(ChatScreen(meta.session_id, meta.title))

    def action_open_session(self) -> None:
        lv = self.query_one("#tui-session-list", ListView)
        if lv.index is None or not self._items or lv.index >= len(self._items):
            return
        meta = self._items[lv.index]
        self.app.push_screen(ChatScreen(meta.session_id, meta.title))

    def action_new_session(self) -> None:
        def on_dismiss(sid: str | None) -> None:
            if sid:
                self.app.push_screen(ChatScreen(sid, "untitled"))
                self._load()

        self.app.push_screen(NewSessionScreen(), on_dismiss)

    def action_search(self) -> None:
        def on_dismiss(sid: str | None) -> None:
            if sid:
                self.app.push_screen(ChatScreen(sid, "..."))

        self.app.push_screen(SearchScreen(), on_dismiss)

    def action_quit(self) -> None:
        self.app.exit()

    def action_command_palette(self) -> None:
        def on_dismiss(cmd: str | None) -> None:
            if cmd:
                self._exec_cmd(cmd)

        self.app.push_screen(CommandScreen(), on_dismiss)

    def action_refresh(self) -> None:
        self._load()

    def _exec_cmd(self, cmd: str) -> None:
        cmd = cmd.lstrip("/").strip().lower()
        if cmd in ("quit", "q", "exit"):
            self.app.exit()
        elif cmd in ("back", "b"):
            self.app.pop_screen()
        elif cmd in ("new", "n"):
            self.action_new_session()
        elif cmd in ("refresh", "r"):
            self._load()


# ---------------------------------------------------------------------------
# Chat Screen
# ---------------------------------------------------------------------------


class ChatScreen(Screen[None]):
    """Chat conversation screen with streaming."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+l", "back", "Back"),
        Binding("slash", "command_palette", "Command"),
        Binding("ctrl+r", "refresh", "Refresh"),
    ]

    def __init__(self, session_id: str, title: str = "Chat") -> None:
        super().__init__()
        self._session_id = session_id
        self._title = title
        self._streaming = False
        self._assistant_accumulated: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static(
            f" {self._title} [{self._session_id[:8]}] ", id="tui-chat-titlebar"
        )
        yield RichLog(id="tui-chat-log", highlight=True, markup=True, wrap=True)
        # Bug #3 FIX: 在输入框上方增加一个命令补全提示区域，默认隐藏
        yield Static("", id="tui-completions", classes="completions-hidden")
        yield Input(placeholder="输入消息…  /cmd 执行命令", id="tui-chat-input")
        yield Static("  Esc 返回 · / 命令 · Ctrl+R 刷新  ", id="tui-chat-footer")

    def on_mount(self) -> None:
        self._load_history()
        # Bug #2 FIX: 加载历史后自动滚动到底部
        self.query_one("#tui-chat-log", RichLog).scroll_end(animate=False)
        self.query_one("#tui-chat-input", Input).focus()

    def _load_history(self) -> None:
        bridge: ManagerBridge = self.app.bridge
        body = bridge.get_session_body(self._session_id)
        log = self.query_one("#tui-chat-log", RichLog)
        log.clear()
        if not body:
            log.write(Text("（新会话）", style="dim italic"))
            return
        lines = body.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("**User:**"):
                log.write(
                    Text(
                        f"👤 {stripped.replace('**User:**', '').strip()}",
                        style="bold cyan",
                    )
                )
            elif stripped.startswith("**Assistant:**"):
                log.write(
                    Text(
                        f"🤖 {stripped.replace('**Assistant:**', '').strip()}",
                        style="green",
                    )
                )
            elif stripped.startswith("## "):
                log.write(Text(stripped, style="bold"))
            else:
                log.write(Text(stripped, style="dim"))

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_command_palette(self) -> None:
        def on_dismiss(cmd: str | None) -> None:
            if cmd:
                self._handle_command(cmd)

        self.app.push_screen(CommandScreen(), on_dismiss)

    def action_refresh(self) -> None:
        self._load_history()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self.query_one("#tui-chat-input", Input).clear()
        if text.startswith("/"):
            self._handle_command(text)
            return
        self._send_message(text)

    #  Bug #3 FIX: 斜杠命令输入自动补全

    def on_input_changed(self, event: Input.Changed) -> None:
        text = event.value
        comp = self.query_one("#tui-completions", Static)
        if text.startswith("/"):
            self._show_completions(text, comp)
        else:
            comp.update("")
            comp.classes = "completions-hidden"

    def _show_completions(self, text: str, comp: Static) -> None:
        """Show filtered command completions in the dedicated widget above input."""
        filter_text = text[1:].strip().lower()
        lines: list[str] = []
        for cmd, desc in _COMMANDS.items():
            if filter_text and filter_text not in cmd and filter_text not in desc:
                continue
            lines.append(f"  /{cmd:<12} {desc}")
        if lines:
            comp.update("── 命令候选 ──\n" + "\n".join(lines))
            comp.classes = "completions-visible"
        else:
            comp.update("")
            comp.classes = "completions-hidden"

    def _handle_command(self, cmd: str) -> None:
        parts = cmd[1:].strip().split(maxsplit=1)
        cmd_name = parts[0].lower() if parts else ""
        cmd_arg = parts[1] if len(parts) > 1 else ""
        log = self.query_one("#tui-chat-log", RichLog)

        if cmd_name in ("quit", "q", "exit"):
            self.app.exit()
        elif cmd_name in ("back", "b"):
            self.app.pop_screen()
        elif cmd_name == "delete":
            try:
                bridge: ManagerBridge = self.app.bridge
                bridge.delete_session(self._session_id)
                log.write(
                    Text(f"✓ 会话已删除: {self._session_id[:8]}", style="bold yellow")
                )
                self.app.pop_screen()
            except Exception as e:
                log.write(Text(f"✗ 删除失败: {e}", style="red"))
            self._focus_input()
        elif cmd_name == "export":
            try:
                bridge: ManagerBridge = self.app.bridge
                body = bridge.get_session_body(self._session_id)
                if not body:
                    log.write(Text("⚠ 当前会话为空，无法导出", style="yellow"))
                else:
                    export_path = os.path.join(
                        os.path.expanduser("~"),
                        "mmi_exports",
                        f"{self._session_id[:8]}_{self._title or 'chat'}.md",
                    )
                    os.makedirs(os.path.dirname(export_path), exist_ok=True)
                    with open(export_path, "w", encoding="utf-8") as f:
                        f.write(body)
                    log.write(Text(f"✓ 已导出: {export_path}", style="bold green"))
            except Exception as e:
                log.write(Text(f"✗ 导出失败: {e}", style="red"))
            self._focus_input()
        elif cmd_name == "model":
            if cmd_arg:
                try:
                    cfg_module.set_default_model(cmd_arg)
                    log.write(
                        Text(f"✓ 模型已切换至 {cmd_arg}", style="bold yellow")
                    )
                except Exception as e:
                    log.write(Text(f"✗ 切换失败: {e}", style="red"))
            else:
                cur = cfg_module.get_default_model()
                log.write(Text(f"当前模型: {cur}", style="bold yellow"))
        elif cmd_name in ("refresh", "r"):
            self._load_history()
        elif cmd_name in ("help", "h"):
            log.write(
                Text(
                    "命令: /model [名称]  /delete  /export  /back  /quit  /refresh  /help",
                    style="bold yellow",
                )
            )
        else:
            log.write(Text(f"未知命令: /{cmd_name}", style="red"))
            log.write(Text("输入 /help 查看可用命令", style="dim"))
        self._focus_input()

    def _focus_input(self) -> None:
        self.query_one("#tui-chat-input", Input).focus()

    def _send_message(self, text: str) -> None:
        if self._streaming:
            self.query_one("#tui-chat-log", RichLog).write(
                Text("⚠ 等待当前回复完成…", style="red")
            )
            return
        log = self.query_one("#tui-chat-log", RichLog)
        log.write(Text(f"\n👤 {text}", style="bold cyan"))
        log.write(Text("\n🤖 思考中…", style="dim italic"))
        # Bug #2 FIX: 用户输入后自动滚动到底部
        log.scroll_end(animate=False)
        self._streaming = True
        self._assistant_accumulated = []
        bridge: ManagerBridge = self.app.bridge
        self._stream_assistant_response(bridge, text)

    @work(thread=True)
    def _stream_assistant_response(
        self, bridge: ManagerBridge, user_input: str
    ) -> None:
        """Run streaming in a worker thread."""
        try:
            chunks: list[str] = []
            for chunk in bridge.stream_chat(self._session_id, user_input):
                chunks.append(chunk)
                self.post_message(StreamChunk(chunk))
            reply = "".join(chunks)
            self.post_message(StreamDone(reply))
        except Exception as e:
            err = f"[LLM 错误: {e}]"
            self.post_message(StreamChunk(err))
            self.post_message(StreamDone(err))

    def on_stream_chunk(self, event: StreamChunk) -> None:
        self._assistant_accumulated.append(event.chunk)
        log = self.query_one("#tui-chat-log", RichLog)
        # Bug #2 FIX: 流式输出时自动滚动到底部
        log.write(event.chunk, width=9999)
        log.scroll_end(animate=False)

    def on_stream_done(self, event: StreamDone) -> None:
        self._streaming = False
        # Bug #2 FIX: 流式完成后重新加载历史，自动格式化显示完整对话
        self._load_history()
        self._focus_input()
        self._assistant_accumulated = []


# ---------------------------------------------------------------------------
# New Session Modal
# ---------------------------------------------------------------------------


class NewSessionScreen(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Container(
            Label("新建会话", id="new-session-title"),
            Input(placeholder="会话标题（可选）", id="new-session-input"),
            Container(
                Button("创建", id="btn-create", variant="primary"),
                Button("取消", id="btn-cancel"),
                id="new-session-buttons",
            ),
            id="new-session-dialog",
        )

    def on_mount(self) -> None:
        self.query_one("#new-session-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._create(event.value.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-create":
            inp = self.query_one("#new-session-input", Input)
            self._create(inp.value.strip())
        else:
            self.dismiss(None)

    def _create(self, title: str) -> None:
        if not title:
            title = "untitled"
        try:
            bridge: ManagerBridge = self.app.bridge
            sid = bridge.create_session(title)
            self.dismiss(sid)
        except Exception as e:
            inp = self.query_one("#new-session-input", Input)
            inp.value = f"✗ {e}"
            inp.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Search Modal
# ---------------------------------------------------------------------------


class SearchScreen(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self) -> None:
        super().__init__()
        self._results: list[SessionMeta] = []

    def compose(self) -> ComposeResult:
        yield Container(
            Label("搜索会话", id="search-title"),
            Input(placeholder="输入关键词…", id="search-input"),
            ListView(id="search-results"),
            id="search-dialog",
        )

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        lv = self.query_one("#search-results", ListView)
        lv.clear()
        self._results = []
        if len(query) < 1:
            return
        try:
            bridge: ManagerBridge = self.app.bridge
            self._results = bridge.search(query)
            for r in self._results[:20]:
                lv.mount(ListItem(Static(f"{r.title}  [{r.session_id[:8]}]")))
        except Exception:
            pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is None:
            return
        idx = event.list_view.index
        if idx is not None and idx < len(self._results):
            self.dismiss(self._results[idx].session_id)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Command Modal
# ---------------------------------------------------------------------------


class CommandScreen(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    COMMANDS = {
        "quit": "退出程序",
        "back": "返回上一页",
        "new": "新建会话",
        "refresh": "刷新列表",
        "model": "切换模型 (/model <名称>)",
        "delete": "删除当前会话",
        "export": "导出为 Markdown",
        "help": "帮助信息",
    }

    def compose(self) -> ComposeResult:
        yield Container(
            Label("命令面板", id="cmd-title"),
            Input(placeholder="/<命令>", id="cmd-input"),
            ListView(id="cmd-results"),
            id="cmd-dialog",
        )

    def on_mount(self) -> None:
        self.query_one("#cmd-input", Input).focus()
        self._populate()

    def _populate(self, filter_text: str = "") -> None:
        lv = self.query_one("#cmd-results", ListView)
        lv.clear()
        for cmd, desc in sorted(self.COMMANDS.items()):
            if filter_text and filter_text not in cmd and filter_text not in desc:
                continue
            lv.mount(ListItem(Static(f"/{cmd:<10}  {desc}")))

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate(event.value.strip().lstrip("/"))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is None:
            return
        label = event.item.children[0]
        if isinstance(label, Static):
            text = str(label.render())
            m = re.search(r"/(\w+)", text)
            if m:
                self.dismiss(f"/{m.group(1)}")

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------


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
