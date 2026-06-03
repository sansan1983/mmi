"""mmi.tui.screens.chat —— 聊天视图。"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, TextArea

from ...core import config as cfg_module
from ...core.llm import get_default_provider
from ...core.storage import parse_turns

if TYPE_CHECKING:
    from ..app import CTrimApp

__all__ = ["ChatView"]

_CMDS: dict[str, str] = {
    "help": "显示帮助", "clear": "清屏", "list": "返回列表",
    "new": "新建会话", "search": "搜索", "quit": "退出",
    "model": "切换模型 例: /model gpt-4o",
}
_HELP = "\n".join(f"  /{k:<10} {v}" for k, v in _CMDS.items())


# ---------------------------------------------------------------------------
# TextArea
# ---------------------------------------------------------------------------

class SendTextArea(TextArea):
    """Enter 发送，Ctrl+Enter 换行。自动维护 > 前缀。"""

    def on_mount(self) -> None:
        self.text = "> "
        self.cursor_location = (0, 2)

    def on_key(self, event) -> None:
        if event.key == "enter":
            event.stop()
            chat: ChatView = self.parent
            if not isinstance(chat, ChatView):
                return
            text = self.text.strip()
            if not text or text == ">":
                return
            self.text = "> "
            self.cursor_location = (0, 2)
            cmd = text[1:].strip() if text.startswith(">") else text
            if cmd.startswith("/"):
                chat.handle_command(cmd)
            elif cmd:
                chat.send_message(cmd)


# ---------------------------------------------------------------------------
# Turn
# ---------------------------------------------------------------------------

class Turn(Vertical):
    def __init__(self, role: str, content: str = "", meta: str = "",
                 collapsed: bool = False) -> None:
        super().__init__()
        self._role = role
        self._content = content
        self._meta = meta
        self._collapsed = collapsed

    def compose(self) -> ComposeResult:
        icon = "▶" if self._collapsed else "▼"
        rn = "You" if self._role == "user" else "MMI"
        rc = "role-user" if self._role == "user" else "role-asst"
        yield Static(f" {icon}  {rn} {self._meta}", classes=f"turn-header {rc}")
        self._body = Vertical(classes=f"turn-body {'-hidden' if self._collapsed else ''}")
        self._cw = Static(self._content, classes="msg-content")
        with self._body:
            yield self._cw

    def append_content(self, chunk: str) -> None:
        self._content += chunk
        self._cw.update(self._content)

    def on_click(self) -> None:
        try:
            h = not self._body.has_class("-hidden")
            self._body.set_class(h, "-hidden")
            sh = self.query_one(".turn-header", Static)
            rn = "You" if self._role == "user" else "MMI"
            self._collapsed = h
            sh.update(f" {'▶' if h else '▼'}  {rn} {self._meta}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ChatView
# ---------------------------------------------------------------------------

class ChatView(Vertical):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._session_id: str | None = None
        self._session_title: str = ""

    def compose(self) -> ComposeResult:
        yield Static(" M   gpt-4o  heat --  active      ~-- ctx", id="chat-topbar")
        yield VerticalScroll(id="msg-area")
        yield SendTextArea("", id="input-editor")
        yield Static("  Enter 发送  ·  / 命令  ·  Esc 返回         ● 就绪",
                     id="chat-footer")

    def load_session(self, session_id: str) -> None:
        self._session_id = session_id
        try:
            app: "CTrimApp" = self.app
            meta = next((m for m in app.mgr.list_sessions(limit=1000)
                         if m.session_id == session_id), None)
        except Exception:
            meta = None
        if meta:
            self._session_title = meta.title or session_id[:8]
            self._update_topbar(meta)
        else:
            self._session_title = session_id[:8]
        self._update_footer()
        self._load_messages()
        self.call_after_refresh(lambda: self.query_one("#input-editor").focus())

    def _update_topbar(self, meta) -> None:
        try:
            tb = self.query_one("#chat-topbar", Static)
            tb.update(f" M   {cfg_module.get_default_model()}  heat {meta.heat:.1f}  {meta.state}      ~-- ctx")
        except Exception:
            pass

    def _update_footer(self) -> None:
        try:
            f = self.query_one("#chat-footer", Static)
            f.update(f"  Enter 发送  ·  / 命令  ·  Esc 返回        {self._session_title}  ● 就绪")
        except Exception:
            pass

    def _load_messages(self) -> None:
        ma = self.query_one("#msg-area", VerticalScroll)
        ma.remove_children()
        if not self._session_id:
            return
        try:
            app: "CTrimApp" = self.app
            session = app.mgr.get(self._session_id)
        except Exception:
            return
        turns = parse_turns(getattr(session, "body", ""))
        for i, t in enumerate(turns):
            role = t["role"]
            content = t["content"]
            ts = time.strftime("%H:%M:%S")
            collapsed = role == "assistant" and i == len(turns) - 1 and len(content) > 200
            ma.mount(Turn(role, content, meta=f"~?? tok  {ts}", collapsed=collapsed))
        ma.scroll_end()

    def send_message(self, text: str) -> None:
        self._add_turn("user", text)
        self.set_busy(True)
        self.call_later(self._stream_reply, text)

    async def _stream_reply(self, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        turn = Turn("assistant", meta=f"~? tok  {ts}")
        try:
            self.query_one("#msg-area", VerticalScroll).mount(turn)
        except Exception:
            self.set_busy(False)
            return
        try:
            async for chunk in get_default_provider().stream_chat([{"role": "user", "content": text}]):
                turn.append_content(chunk)
                self.query_one("#msg-area", VerticalScroll).scroll_end(animate=False)
                await asyncio.sleep(0)
        except Exception as e:
            turn.append_content(f"\n[error: {e}]")
        turn._meta = f"~{len(turn._content) // 4} tok  {ts}"
        try:
            self.query_one(".turn-header", Static).update(f" ▼  MMI {turn._meta}")
        except Exception:
            pass
        self.set_busy(False)
        self._save()

    def handle_command(self, text: str) -> None:
        parts = text[1:].strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        if cmd == "help":
            self._add_turn("assistant", f"可用命令:\n{_HELP}", collapsed=False)
        elif cmd == "clear":
            self.clear_messages()
        elif cmd in ("list", "new"):
            try:
                app: "CTrimApp" = self.app
                if cmd == "new":
                    app.action_new_session()
                else:
                    app.call_from_thread(app.show_list)
            except Exception:
                pass
        elif cmd == "search":
            from .search import SearchScreen
            self.app.push_screen(SearchScreen())
        elif cmd == "quit":
            self.app.exit()
        elif cmd == "model" and arg:
            try:
                cfg_module.write_key("model", arg)
                self._add_turn("system", f"模型已切换至 {arg}")
            except Exception:
                self._add_turn("system", "切换模型失败")
        else:
            self._add_turn("assistant", f"未知命令: /{cmd}\n输入 /help 查看可用命令")

    def _add_turn(self, role: str, content: str, collapsed: bool | None = None) -> None:
        ts = time.strftime("%H:%M:%S")
        meta = f"{'~' + str(len(content) // 4) if role == 'assistant' else '~?'} tok  {ts}"
        if collapsed is None:
            collapsed = role == "assistant" and len(content) > 200
        try:
            ma = self.query_one("#msg-area", VerticalScroll)
            ma.mount(Turn(role, content, meta=meta, collapsed=collapsed))
            ma.scroll_end()
        except Exception:
            pass

    def _save(self) -> None:
        """将 UI turns 写回 session.body（Markdown 格式）。"""
        if not self._session_id:
            return
        turns: list[dict] = []
        try:
            ma = self.query_one("#msg-area", VerticalScroll)
            for c in ma.children:
                if isinstance(c, Turn):
                    turns.append({"role": c._role, "content": c._content})
        except Exception:
            return
        if not turns:
            return
        date = datetime.now().strftime("%Y-%m-%d")
        parts = [f"## {date}"]
        for t in turns:
            label = "User" if t["role"] == "user" else "Assistant"
            parts.append(f"**{label}:** {t['content']}")
        body = "\n\n".join(parts) + "\n"
        try:
            app: "CTrimApp" = self.app
            s = app.mgr.get(self._session_id)
            if s:
                s.body = body
                app.mgr.storage.write_session(s)
        except Exception:
            pass

    def set_busy(self, busy: bool) -> None:
        try:
            f = self.query_one("#chat-footer", Static)
            t = f.renderable or ""
            f.update(t.replace("● 就绪", "● 工作中") if busy else t.replace("● 工作中", "● 就绪"))
        except Exception:
            pass

    def clear_messages(self) -> None:
        try:
            self.query_one("#msg-area", VerticalScroll).remove_children()
        except Exception:
            pass
