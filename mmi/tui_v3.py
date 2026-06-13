"""mmi.tui_v3 — MMI Textual-based TUI (consolidated v3).

Port of GA's tui_v3 architecture, adapted for mmi's SessionManager.
Run: mmi tui-python  or  python -m mmi.tui_v3
"""

from __future__ import annotations

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

    def stream_chat(self, session_id: str, user_input: str) -> Iterator[str]:
        yield from self.mgr.stream_chat(session_id, user_input)

    def search(self, query: str) -> list[SessionMeta]:
        return self.mgr.search(query)


# ---------------------------------------------------------------------------
# Stream Messages (thread-safe messaging)
# ---------------------------------------------------------------------------


class StreamChunk(Message):
    def __init__(self, chunk: str) -> None:
        super().__init__()
        self.chunk = chunk


class StreamDone(Message):
    def __init__(self, reply: str) -> None:
        super().__init__()
        self.reply = reply


# ---------------------------------------------------------------------------
# Session List Screen
# ---------------------------------------------------------------------------


LIST_TITLE = _t('tui.list.title', default='\u4f1a\u8bdd\u5217\u8868')

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
            "  \u2191\u2193 \u9009\u62e9 \u00b7 Enter \u8fdb\u5165 \u00b7 n \u65b0\u5efa \u00b7 / \u547d\u4ee4 \u00b7 q \u9000\u51fa  ",
            id="tui-footer",
        )

    def on_mount(self) -> None:
        self._load()

    def _load(self) -> None:
        bridge: ManagerBridge = self.app.bridge  # type: ignore[attr-defined]
        try:
            self._items = bridge.list_sessions(limit=100)
            self._items.sort(key=lambda m: m.heat or 0.0, reverse=True)
        except Exception:
            self._items = []
        lv = self.query_one("#tui-session-list", ListView)
        lv.clear()
        if not self._items:
            lv.mount(ListItem(Static("~ ~ ~ \u6682\u65e0\u4f1a\u8bdd ~ ~ ~", classes="empty-msg")))
            self.query_one("#tui-list-info", Static).update("\u4f1a\u8bdd\u5386\u53f2 \u00b7 0 \u4e2a\u4f1a\u8bdd")
            return
        for i, meta in enumerate(self._items):
            title = (meta.title or "(untitled)").replace("\n", " ")
            info = f"{i+1:>3}  {title[:36]:36}  heat:{meta.heat:<5.1f}  [{meta.state}]"
            lv.mount(ListItem(Static(info)))
        self.query_one("#tui-list-info", Static).update(
            f"\u4f1a\u8bdd\u5386\u53f2 \u00b7 {len(self._items)} \u4e2a\u4f1a\u8bdd"
        )

    def action_open_session(self) -> None:
        lv = self.query_one("#tui-session-list", ListView)
        if lv.index is None or not self._items or lv.index >= len(self._items):
            return
        meta = self._items[lv.index]
        self.app.push_screen(ChatScreen(meta.session_id, meta.title))  # type: ignore[attr-defined]

    def action_new_session(self) -> None:
        def on_dismiss(sid: str | None) -> None:
            if sid:
                self.app.push_screen(ChatScreen(sid, "untitled"))  # type: ignore[attr-defined]
                self._load()
        self.app.push_screen(NewSessionScreen(), on_dismiss)  # type: ignore[attr-defined]

    def action_search(self) -> None:
        def on_dismiss(sid: str | None) -> None:
            if sid:
                self.app.push_screen(ChatScreen(sid, "..."))  # type: ignore[attr-defined]
        self.app.push_screen(SearchScreen(), on_dismiss)  # type: ignore[attr-defined]

    def action_quit(self) -> None:
        self.app.exit()

    def action_command_palette(self) -> None:
        def on_dismiss(cmd: str | None) -> None:
            if cmd:
                self._exec_cmd(cmd)
        self.app.push_screen(CommandScreen(), on_dismiss)  # type: ignore[attr-defined]

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
        self._stream_buf = ""

    def compose(self) -> ComposeResult:
        yield Static(
            f" {self._title} [{self._session_id[:8]}] ", id="tui-chat-titlebar"
        )
        yield RichLog(id="tui-chat-log", highlight=True, markup=True, wrap=True)
        yield Input(placeholder="\u8f93\u5165\u6d88\u606f\u2026  /cmd \u6267\u884c\u547d\u4ee4", id="tui-chat-input")
        yield Static("  Esc \u8fd4\u56de \u00b7 / \u547d\u4ee4 \u00b7 Ctrl+R \u5237\u65b0  ", id="tui-chat-footer")

    def on_mount(self) -> None:
        self._load_history()
        self.query_one("#tui-chat-input", Input).focus()

    def _load_history(self) -> None:
        bridge: ManagerBridge = self.app.bridge  # type: ignore[attr-defined]
        body = bridge.get_session_body(self._session_id)
        log = self.query_one("#tui-chat-log", RichLog)
        log.clear()
        if not body:
            log.write(Text("\uff08\u65b0\u4f1a\u8bdd\uff09", style="dim italic"))
            return
        lines = body.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("**User:**"):
                log.write(
                    Text(
                        f"\U0001f9d1 {stripped.replace('**User:**', '').strip()}",
                        style="bold cyan",
                    )
                )
            elif stripped.startswith("**Assistant:**"):
                log.write(
                    Text(
                        f"\U0001f916 {stripped.replace('**Assistant:**', '').strip()}",
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
        self.app.push_screen(CommandScreen(), on_dismiss)  # type: ignore[attr-defined]

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

    def _handle_command(self, cmd: str) -> None:
        parts = cmd[1:].strip().split(maxsplit=1)
        cmd_name = parts[0].lower() if parts else ""
        cmd_arg = parts[1] if len(parts) > 1 else ""
        log = self.query_one("#tui-chat-log", RichLog)

        if cmd_name in ("quit", "q", "exit"):
            self.app.exit()
        elif cmd_name in ("back", "b"):
            self.app.pop_screen()
        elif cmd_name == "model":
            if cmd_arg:
                try:
                    cfg_module.set_default_model(cmd_arg)
                    log.write(Text(f"\u2713 \u6a21\u578b\u5df2\u5207\u6362\u81f3 {cmd_arg}", style="bold yellow"))
                except Exception as e:
                    log.write(Text(f"\u2717 \u5207\u6362\u5931\u8d25: {e}", style="red"))
            else:
                cur = cfg_module.get_default_model()
                log.write(Text(f"\u5f53\u524d\u6a21\u578b: {cur}", style="bold yellow"))
        elif cmd_name in ("refresh", "r"):
            self._load_history()
        elif cmd_name in ("help", "h"):
            log.write(
                Text(
                    "\u547d\u4ee4: /model [\u540d\u79f0]  /back  /quit  /refresh  /help",
                    style="bold yellow",
                )
            )
        else:
            log.write(Text(f"\u672a\u77e5\u547d\u4ee4: /{cmd_name}", style="red"))
        self._focus_input()

    def _focus_input(self) -> None:
        self.query_one("#tui-chat-input", Input).focus()

    def _send_message(self, text: str) -> None:
        if self._streaming:
            self.query_one("#tui-chat-log", RichLog).write(
                Text("\u26a0 \u7b49\u5f85\u5f53\u524d\u56de\u590d\u5b8c\u6210\u2026", style="red")
            )
            return
        log = self.query_one("#tui-chat-log", RichLog)
        log.write(Text(f"\n\U0001f9d1 {text}", style="bold cyan"))
        self._streaming = True
        self._assistant_accumulated = []
        bridge: ManagerBridge = self.app.bridge  # type: ignore[attr-defined]
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
            err = f"[LLM \u9519\u8bef: {e}]"
            self.post_message(StreamChunk(err))
            self.post_message(StreamDone(err))

    def on_stream_chunk(self, event: StreamChunk) -> None:
        self._stream_buf += event.chunk
        log = self.query_one("#tui-chat-log", RichLog)
        log.write(event.chunk, width=9999)

    def on_stream_done(self, event: StreamDone) -> None:
        self._streaming = False
        self._focus_input()


# ---------------------------------------------------------------------------
# New Session Modal
# ---------------------------------------------------------------------------


class NewSessionScreen(ModalScreen[str]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Container(
            Label("\u65b0\u5efa\u4f1a\u8bdd", id="new-session-title"),
            Input(placeholder="\u4f1a\u8bdd\u6807\u9898\uff08\u53ef\u9009\uff09", id="new-session-input"),
            Container(
                Button("\u521b\u5efa", id="btn-create", variant="primary"),
                Button("\u53d6\u6d88", id="btn-cancel"),
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
            bridge: ManagerBridge = self.app.bridge  # type: ignore[attr-defined]
            sid = bridge.create_session(title)
            self.dismiss(sid)
        except Exception as e:
            inp = self.query_one("#new-session-input", Input)
            inp.value = f"\u2717 {e}"
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
            Label("\u641c\u7d22\u4f1a\u8bdd", id="search-title"),
            Input(placeholder="\u8f93\u5165\u5173\u952e\u8bcd\u2026", id="search-input"),
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
            bridge: ManagerBridge = self.app.bridge  # type: ignore[attr-defined]
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
        "quit": "\u9000\u51fa\u7a0b\u5e8f",
        "back": "\u8fd4\u56de\u4e0a\u4e00\u9875",
        "new": "\u65b0\u5efa\u4f1a\u8bdd",
        "refresh": "\u5237\u65b0\u5217\u8868",
        "model": "\u5207\u6362\u6a21\u578b (/model <\u540d\u79f0>)",
        "help": "\u5e2e\u52a9\u4fe1\u606f",
    }

    def compose(self) -> ComposeResult:
        yield Container(
            Label("\u547d\u4ee4\u9762\u677f", id="cmd-title"),
            Input(placeholder="/<\u547d\u4ee4>", id="cmd-input"),
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
