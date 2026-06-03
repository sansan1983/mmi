"""mmi.tui.widgets.chat_log —— 聊天滚动区。

ARCHITECTURE Phase 5：包 RichLog，暴露：
  - append_user(text)
  - append_assistant_chunk(text)   # 流式逐片
  - append_assistant_done(text)    # 流式结束（替换最后一行为完整内容）
  - render_paragraph(text)         # 通用：解析 Block 后渲染（折叠块用 Static + can_focus）

设计：
  - 用户/助手标签走 i18n t("tui.chat.user_label") / t("tui.chat.assistant_label")
  - 流式 chunk 用 last-line update（用 markup + update=True）
  - 折叠块用 Static 渲染，绑定 click 切 expand 状态
"""

from __future__ import annotations

from typing import Iterable

from rich.text import Text
from textual.widgets import RichLog, Static

from ...core.i18n import t
from ..parse_blocks import Block, TextBlock, ThinkingBlock, ToolCallBlock, parse_blocks

__all__ = ["ChatLog"]


class CollapsibleStatic(Static):
    """思考 / 工具块（OMP 风格：整行高亮 + 左侧色条）。"""

    DEFAULT_CSS = """
    CollapsibleStatic {
        height: auto;
        color: #bb9af7;
        border-top: solid #2a2e3a;
        border-left: solid #414868;
        padding: 0 1;
    }
    CollapsibleStatic.-thinking {
        background: #1f2335;
        color: #bb9af7;
        border-left: solid #bb9af7;
    }
    CollapsibleStatic.-tool {
        background: #1f2d2a;
        color: #9ece6a;
        border-left: solid #9ece6a;
    }
    """

    def __init__(self, *, kind: str, name: str = "", content: str = ""):
        if kind == "thinking":
            head = t("tui.chat.thinking_expanded")
        else:
            head = t("tui.chat.tool_expanded", name=name)
        rendered = Text.assemble(
            (head + "\n", "bold"),
            (content, "dim"),
        )
        super().__init__(rendered, markup=False)
        self.add_class(f"-{kind}")


class _UserBlock(Static):
    """用户消息块：上细线 + 极轻背景。"""

    DEFAULT_CSS = """
    _UserBlock {
        background: #1f2335;
        border-top: solid #414868;
        height: auto;
        padding: 0 1;
        margin: 0;
    }
    """

    def __init__(self, label: str, text: str) -> None:
        content = Text.assemble(
            (f"[{label}] ", "bold #7dcfff"),
            (text, "#c0caf5"),
        )
        super().__init__(content, markup=False)


class _AssistantBlock(Static):
    """助手消息块：上细线（更暗），无背景。"""

    DEFAULT_CSS = """
    _AssistantBlock {
        background: #1a1b26;
        border-top: solid #2a2e3a;
        height: auto;
        padding: 0 1;
        margin: 0;
    }
    """

    def __init__(self, label: str, text: str) -> None:
        content = Text.assemble(
            (f"[{label}] ", "bold #c0caf5"),
            (text, "#c0caf5"),
        )
        super().__init__(content, markup=False)


class _AssistantStreamBlock(Static):
    """助手流式输出块（会被 chunk 持续 update）。"""

    DEFAULT_CSS = """
    _AssistantStreamBlock {
        background: #1a1b26;
        border-top: solid #2a2e3a;
        height: auto;
        padding: 0 1;
        margin: 0;
    }
    """

    def __init__(self, label: str) -> None:
        self._label = label
        self._buf: list[str] = []
        content = Text(f"[{label}] ", style="bold #c0caf5")
        super().__init__(content, markup=False)

    def append_chunk(self, chunk: str) -> None:
        self._buf.append(chunk)
        # 重新构造：label + buffer 累积内容
        content = Text.assemble(
            (f"[{self._label}] ", "bold #c0caf5"),
            ("".join(self._buf), "#c0caf5"),
        )
        self.update(content)

    def finalize(self) -> None:
        # 留给上层决定如何渲染（可能拆 block）
        pass


class ChatLog(RichLog):
    """聊天滚动区（包 RichLog，承载 _UserBlock / _AssistantBlock / _AssistantStreamBlock）。"""

    DEFAULT_CSS = """
    ChatLog {
        background: #1a1b26;
        padding: 0 0;
    }
    ChatLog > .user-label {
        color: #7dcfff;
        text-style: bold;
    }
    ChatLog > .assistant-label {
        color: #c0caf5;
        text-style: bold;
    }
    ChatLog > .user-content {
        color: #c0caf5;
    }
    ChatLog > .assistant-content {
        color: #c0caf5;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(wrap=True, markup=False, highlight=False, **kwargs)
        self._streaming_active: bool = False
        self._stream_block: _AssistantStreamBlock | None = None

    # ----- 用户 --------------------------------------------------------

    def append_user(self, text: str) -> None:
        """追加一条用户消息。"""
        block = _UserBlock(t("tui.chat.user_label"), text)
        self.mount(block)

    def append_command_input(self, prompt: str, text: str) -> None:
        """追加一条命令输入（! / $ 前缀）。prompt 是 '!' 或 '$'。"""
        block = _UserBlock(prompt, text)
        self.mount(block)

    def append_command_output(self, output: str) -> None:
        """追加一条命令输出（label 固定 '>' 表示 shell 流）。"""
        block = _AssistantBlock(">", output)
        self.mount(block)

    # ----- 助手（流式）-------------------------------------------------

    def append_assistant_start(self) -> None:
        """开始一段助手回复（流式起手）。"""
        self._streaming_active = True
        self._stream_block = _AssistantStreamBlock(t("tui.chat.assistant_label"))
        self.mount(self._stream_block)

    def append_assistant_chunk(self, chunk: str) -> None:
        """流式 chunk：累加并追加到当前行。"""
        if not self._streaming_active or self._stream_block is None:
            self.append_assistant_start()
        assert self._stream_block is not None
        self._stream_block.append_chunk(chunk)

    def append_assistant_done(self, full_text: str | None = None) -> None:
        """流式结束 / 整段到达。"""
        if self._stream_block is not None and full_text is not None:
            self._stream_block.append_chunk("")  # flush
            self._stream_block.append_chunk(full_text)
        self._streaming_active = False
        self._stream_block = None

    # ----- 块渲染（折叠）------------------------------------------------

    def _render_blocks(self, text: str) -> None:
        blocks = parse_blocks(text)
        for b in blocks:
            self._render_block(b)

    def _render_block(self, b: Block) -> None:
        if isinstance(b, TextBlock):
            block = _AssistantBlock(
                t("tui.chat.assistant_label"), b.text
            )
            self.mount(block)
        elif isinstance(b, ThinkingBlock):
            cs = CollapsibleStatic(kind="thinking", content=b.text)
            self.mount(cs)
        elif isinstance(b, ToolCallBlock):
            cs = CollapsibleStatic(kind="tool", name=b.name, content=b.text)
            self.mount(cs)
