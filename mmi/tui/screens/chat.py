"""mmi.tui.screens.chat —— 主聊天屏。

ARCHITECTURE Phase 5（最大块）：
  布局：StatusBar + ChatContainer + TextArea + SlashMenu（overlay）
  交互：
    - Enter / Ctrl+Enter 发送
    - Ctrl+C 双击退出（OMP 风格）
    - ↑↓ 命令历史
    - / 触发斜杠菜单
  LLM 调用：worker 调度 + 流式降级到 chat() 整段
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import shlex
import subprocess
import time
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import TextArea

from .. import commands as commands_module
from ...core import config as cfg_module
from ...core.i18n import t
from ..widgets.chat_log import ChatLog
from ..widgets.header_bar import HeaderBar
from ..widgets.hint_bar import HintBar
from ..widgets.slash_menu import SlashMenu


class _ChatTextArea(TextArea, inherit_bindings=False):
    """TextArea for the chat input.

    去掉 ctrl+d (delete_right) / ctrl+z (undo) 默认绑定 —— 这两个键在
    ChatScreen.on_key 中被劫持做"清空输入"和"通知挂起不支持"。
    """

    BINDINGS = [
        b
        for b in TextArea.BINDINGS
        if b.key and "ctrl+d" not in b.key and "ctrl+z" not in b.key
    ]

if TYPE_CHECKING:
    from ..app import CTrimApp


__all__ = ["ChatScreen"]


class History:
    """命令历史（不依赖外部包）。"""

    def __init__(self, max_size: int = 1000):
        self._items: list[str] = []
        self._max = max_size
        self._cursor: int = -1  # -1 = 不在历史中

    def push(self, text: str) -> None:
        if not text:
            return
        if self._items and self._items[-1] == text:
            return
        self._items.append(text)
        if len(self._items) > self._max:
            self._items = self._items[-self._max :]
        self._cursor = -1

    def prev(self) -> str | None:
        if not self._items:
            return None
        if self._cursor + 1 >= len(self._items):
            return None
        self._cursor += 1
        return self._items[-(self._cursor + 1)]

    def next(self) -> str | None:
        if self._cursor <= 0:
            self._cursor = -1
            return ""
        self._cursor -= 1
        return self._items[-(self._cursor + 1)]

    def reset(self) -> None:
        self._cursor = -1


class ChatScreen(Screen):
    """主聊天屏。"""

    BINDINGS = [
        Binding("ctrl+c", "exit_or_clear", "退出", show=False),
        Binding("ctrl+enter", "handle_submit", "发送", show=False),
    ]

    DEFAULT_CSS = """
    ChatScreen {
        background: #1a1b26;
    }
    ChatScreen #input-bar {
        height: auto;
        padding: 0 1;
    }
    ChatScreen #chat-frame {
        height: 1fr;
    }
    """

    # Ctrl+C 双击时间窗（秒）
    CTRL_C_WINDOW = 1.5

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id
        self._history = History()
        self._last_exit_at: float = 0.0
        self._is_streaming: bool = False

    # ----- compose ------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")
        with Vertical(id="chat-frame"):
            yield ChatLog(id="chat-log")
            yield SlashMenu(id="slash-menu")
        yield HintBar(id="hint-bar")
        with Vertical(id="input-bar"):
            yield _ChatTextArea(id="input", name="input-editor")

    def on_mount(self) -> None:
        try:
            self.title = t("tui.chat.title")
        except Exception:
            pass
        # 状态栏初值
        self._refresh_status_bar()
        # 输入框拿焦点
        try:
            self.query_one("#input", TextArea).focus()
        except Exception:
            pass
        # 斜杠菜单默认隐藏
        try:
            self.query_one("#slash-menu", SlashMenu).hide()
        except Exception:
            pass

    # ----- 状态栏 -------------------------------------------------------

    def _refresh_status_bar(self) -> None:
        app: "CTrimApp" = self.app  # type: ignore[assignment]
        try:
            hb = self.query_one("#header-bar", HeaderBar)
        except Exception:
            return
        # 拿最新 meta
        try:
            metas = app.mgr.list_sessions(limit=10_000)
            meta = next((m for m in metas if m.session_id == self.session_id), None)
        except Exception:
            meta = None
        if meta is not None:
            hb.update_session(
                model=cfg_module.get_default_model(),
                heat=f"{meta.heat:.1f}",
                state=meta.state,
            )
        else:
            hb.update_session(
                model=cfg_module.get_default_model(),
                heat="--",
                state="active",
            )

    # ----- TextArea 事件 ------------------------------------------------

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """监听 / 触发斜杠菜单 + 切换 bash / python 边框色。"""
        try:
            val = event.text_area.text
        except Exception:
            val = ""
        # bash / python 前缀 → 切边框色
        try:
            ed = self.query_one("#input", TextArea)
            ed.set_class(val.startswith("!"), "-bash")
            ed.set_class(val.startswith("$"), "-python")
        except Exception:
            pass
        # 斜杠菜单
        if val.startswith("/") and " " not in val:
            try:
                sm = self.query_one("#slash-menu", SlashMenu)
                sm.toggle(val)
            except Exception:
                pass
        else:
            try:
                self.query_one("#slash-menu", SlashMenu).hide()
            except Exception:
                pass

    def action_handle_submit(self) -> None:
        """Ctrl+Enter 触发：根据前缀派发到 bash / python / slash / chat。"""
        if self._is_streaming:
            return
        try:
            ed = self.query_one("#input", TextArea)
            text = ed.text.strip()
        except Exception:
            return
        if not text:
            return
        # bash 前缀
        if text.startswith("!"):
            cmd = text[1:].strip()
            if cmd:
                self._dispatch_command("bash", text, cmd)
            return
        # python 前缀
        if text.startswith("$"):
            code = text[1:].strip()
            if code:
                self._dispatch_command("python", text, code)
            return
        # 斜杠命令？
        if text.startswith("/"):
            result = commands_module.dispatch(self, text)
            self._apply_command_result(result)
            # 清空输入
            try:
                ed.text = ""
            except Exception:
                pass
            try:
                self.query_one("#slash-menu", SlashMenu).hide()
            except Exception:
                pass
            return
        # 普通消息
        self._do_chat_submit(text)

    def _do_chat_submit(self, text: str) -> None:
        """派发普通聊天消息（清空输入 + 写日志 + 起 worker）。"""
        self._history.push(text)
        try:
            ed = self.query_one("#input", TextArea)
            ed.text = ""
        except Exception:
            pass
        try:
            self.query_one("#chat-log", ChatLog).append_user(text)
        except Exception:
            pass
        # 调度 worker
        self.run_worker(
            self._do_chat(text),
            exclusive=True,
            thread=False,
            name="chat-stream",
        )

    async def _do_chat(self, text: str) -> None:
        """worker 主体：调 LLM 流式（不可用则降级）。"""
        self._is_streaming = True
        chat_log = self.query_one("#chat-log", ChatLog)
        header_bar = self.query_one("#header-bar", HeaderBar)
        header_bar.set_busy(True)
        try:
            app: "CTrimApp" = self.app  # type: ignore[assignment]
            messages = self._build_messages(text)
            # 先调一次 sync chat 拿 reply（流式仅影响 UI 渲染；core 仍走 chat 持久化）
            # Phase 5 简化：TUI 走 stream 路径，回复用 chat 持久化（保持 body 不变）
            try:
                # 走真流式
                chat_log.append_assistant_start()
                ait = app.mgr.llm.stream_chat(messages, max_tokens=512, temperature=0.7)
                buf: list[str] = []
                async for chunk in ait:
                    buf.append(chunk)
                    chat_log.append_assistant_chunk(chunk)
                chat_log.append_assistant_done("".join(buf))
                # 持久化（用 chat() 走完整流程：turn + heat + 摘要）
                await asyncio.to_thread(app.mgr.chat, self.session_id, text)
            except NotImplementedError:
                # 降级：sync chat
                reply = await asyncio.to_thread(app.mgr.chat, self.session_id, text)
                chat_log.append_assistant_done(reply)
            except Exception as e:
                self.notify(t("tui.chat.error.llm", error=str(e)), severity="error")
                return
            # 刷状态栏
            self._refresh_status_bar()
        finally:
            header_bar.set_busy(False)
            self._is_streaming = False

    def _build_messages(self, text: str) -> list[dict]:
        """构造 OpenAI 格式 messages。

        Phase 5 简化：只发 system 引导 + 当前 user。
        完整 loader 走 manager.chat 的内部流程；这里只给 stream 喂一个最小上下文。
        """
        from ...core.i18n import get_lang

        sys_text = (
            "你是 C-Trim 的助手。可以使用以下折叠协议（可选）：\n"
            "> [thinking] ...思考过程...\n"
            "> [tool_call name=xxx] ...参数/结果...\n"
            "TUI 会把上述两行起头的内容渲染为可折叠块。"
        )
        if get_lang() == "zh-CN":
            sys_text = (
                "你是 C-Trim 的助手。可以使用以下折叠协议（可选）：\n"
                "> [thinking] ...思考过程...\n"
                "> [tool_call name=xxx] ...参数/结果...\n"
                "TUI 会把上述两行起头的内容渲染为可折叠块。"
            )
        return [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": text},
        ]

    # ----- 斜杠命令结果处理 --------------------------------------------

    def _apply_command_result(self, result: commands_module.SlashCommandResult) -> None:
        if result.action == "stay":
            if result.msg:
                self.notify(result.msg, severity="warning")
        elif result.action == "pop":
            self.app.pop_screen()
        elif result.action == "pop_after_archive":
            self.notify("archived", timeout=2)
            self.app.pop_screen()
        elif result.action == "push_search":
            from .search import SearchScreen

            self.app.push_screen(SearchScreen())
        elif result.action == "refresh_model":
            self._refresh_status_bar()
            self.notify(f"model → {cfg_module.get_default_model()}", timeout=2)
        elif result.action == "exit":
            self.app.exit()

    # ----- Ctrl+C / Ctrl+D 双击退出 / Ctrl+Z 占位 -----------------------

    def action_exit_or_clear(self) -> None:
        """Ctrl+C 或 Ctrl+D：第一次清空输入，1.5s 内第二次退出。"""
        try:
            ed = self.query_one("#input", TextArea)
        except Exception:
            return
        if ed.text.strip():
            # 有内容：清空
            ed.text = ""
            return
        now = time.monotonic()
        if now - self._last_exit_at < self.CTRL_C_WINDOW:
            self.app.exit()
            return
        self._last_exit_at = now
        self.notify(t("tui.chat.ctrl_c_hint"), timeout=2)

    def action_ctrl_z_unsupported(self) -> None:
        """Ctrl+Z 在 TUI 中不支持 OS 级挂起；只是通知用户。"""
        self.notify(t("tui.chat.ctrl_z_unsupported"), timeout=3)

    # ----- ↑↓ 历史（TextArea widget 上绑）-------------------------------

    def on_key(self, event) -> None:  # type: ignore[no-untyped-def]
        """捕获 TextArea 拿焦点时的 ↑↓；拦截 Ctrl+D / Ctrl+Z。"""
        # 全局快捷键（无视焦点，但要 prevent_default 阻止 TextArea 内置绑定）
        if event.key == "ctrl+d":
            self.action_exit_or_clear()
            event.prevent_default()
            return
        if event.key == "ctrl+z":
            self.action_ctrl_z_unsupported()
            event.prevent_default()
            return
        # ↑↓ 历史（只在 TextArea 拿焦点时拦截）
        try:
            focused = self.focused
            ed = self.query_one("#input", TextArea)
        except Exception:
            return
        if focused is not ed:
            return
        if event.key == "up":
            prev = self._history.prev()
            if prev is not None:
                ed.text = prev
                # TextArea 游标移到末尾
                line_count = prev.count("\n") + 1
                ed.cursor_location = (line_count - 1, len(prev.rsplit("\n", 1)[-1]))
            event.prevent_default()
        elif event.key == "down":
            nxt = self._history.next()
            if nxt is not None:
                ed.text = nxt
                line_count = nxt.count("\n") + 1
                ed.cursor_location = (line_count - 1, len(nxt.rsplit("\n", 1)[-1]))
            event.prevent_default()

    # ----- bash / python 前缀命令（绕过 LLM）----------------------------

    def _dispatch_command(self, kind: str, raw_text: str, payload: str) -> None:
        """派发 bash / python：清空输入 + 写聊天日志 + 起 worker。"""
        if self._is_streaming:
            return
        self._history.push(raw_text)
        try:
            ed = self.query_one("#input", TextArea)
            ed.text = ""
            ed.remove_class("-bash")
            ed.remove_class("-python")
        except Exception:
            pass
        try:
            chat_log = self.query_one("#chat-log", ChatLog)
            prompt = "!" if kind == "bash" else "$"
            chat_log.append_command_input(prompt, payload)
        except Exception:
            pass
        self.run_worker(
            self._do_command(kind, payload),
            exclusive=True,
            thread=False,
            name=f"command-{kind}",
        )

    async def _do_command(self, kind: str, payload: str) -> None:
        """worker 主体：调 _run_bash / _run_python，append 到聊天日志。"""
        self._is_streaming = True
        try:
            if kind == "bash":
                output = await asyncio.to_thread(_run_bash, payload)
            else:
                output = await asyncio.to_thread(_run_python, payload)
            chat_log = self.query_one("#chat-log", ChatLog)
            chat_log.append_command_output(output)
        except Exception as e:
            try:
                self.notify(f"command failed: {e}", severity="error")
            except Exception:
                pass
        finally:
            self._is_streaming = False


# ---------------------------------------------------------------------------
# bash / python 执行（模块级，便于单测）
# ---------------------------------------------------------------------------


def _run_bash(cmd: str) -> str:
    """通过 subprocess 跑 bash 命令，返回 stdout+stderr 文本。

    安全约束：shell=False + shlex.split + 10s timeout。
    """
    if not cmd:
        return ""
    try:
        args = shlex.split(cmd)
        if not args:
            return ""
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=10.0,
        )
        out = result.stdout or ""
        if result.stderr:
            out += result.stderr
        if result.returncode != 0:
            out = f"[exit {result.returncode}]\n{out}"
        return out.rstrip("\n") or "(no output)"
    except FileNotFoundError as e:
        return f"[bash] command not found: {e}"
    except subprocess.TimeoutExpired:
        return "[bash] timeout (>10s)"
    except Exception as e:
        return f"[bash] error: {e}"


def _run_python(code: str) -> str:
    """通过 exec 跑 python 代码，返回捕获的 stdout。

    无沙箱（本地可信使用）。错误信息追加到输出末尾。
    """
    if not code:
        return ""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(code, {"__builtins__": __builtins__})  # noqa: S102
    except Exception as e:
        buf.write(f"\n[error] {type(e).__name__}: {e}")
    return buf.getvalue().rstrip("\n") or "(no output)"
