"""mmi.tui_v3._messages —— TUI 自定义 Message(流式回调)。

依赖项:textual.message。
被依赖:screens。
"""

from __future__ import annotations

from textual.message import Message


class StreamChunk(Message):
    def __init__(self, chunk: str) -> None:
        super().__init__()
        self.chunk = chunk


class StreamDone(Message):
    def __init__(self, reply: str) -> None:
        super().__init__()
        self.reply = reply
