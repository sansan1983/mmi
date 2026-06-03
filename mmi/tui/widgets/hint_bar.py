"""mmi.tui.widgets.hint_bar —— 快捷键/状态提示条（位于 Input 上方）。

ARCHITECTURE v2：极简暗色，单行 Static，无边框。
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static


__all__ = ["HintBar"]


def _hint_text() -> Text:
    """快捷键提示。"""
    return Text.assemble(
        ("Enter", "#7aa2f7"),
        (" 发送  ·  ", "#565f89"),
        ("Ctrl+C", "#7aa2f7"),
        (" 退出  ·  ", "#565f89"),
        ("↑↓", "#7aa2f7"),
        (" 历史  ·  ", "#565f89"),
        ("/", "#7aa2f7"),
        (" 命令", "#565f89"),
    )


class HintBar(Static):
    """单行快捷键提示条。"""

    DEFAULT_CSS = """
    HintBar {
        height: 1;
        background: #1a1b26;
        color: #565f89;
        padding: 0 1;
    }
    """

    def on_mount(self) -> None:
        self.update(_hint_text())

    def set_model(self, model: str) -> None:
        """更新右侧：当前模型名。"""
        self.update(
            Text.assemble(
                ("Enter", "#7aa2f7"),
                (" 发送  ·  ", "#565f89"),
                ("Ctrl+C", "#7aa2f7"),
                (" 退出  ·  ", "#565f89"),
                ("↑↓", "#7aa2f7"),
                (" 历史  ·  ", "#565f89"),
                ("/", "#7aa2f7"),
                (" 命令  ·  ", "#565f89"),
                (f"模型 {model}", "#bb9af7"),
            )
        )
