"""mmi.tui.widgets.slash_menu —— 斜杠命令菜单浮层。

ARCHITECTURE Phase 5：监听 Input 变化，/ 开头时弹出。
行为：
  - 候选列表由 commands.COMMANDS 提供
  - 子串过滤（/mod → [/model, /modelhelp...] 实际只有 /model）
  - Tab/Enter 选中 → 把命令 + 空格写回 Input
  - Esc 关闭
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from ...core.i18n import t
from ..commands import COMMANDS

__all__ = ["SlashMenu"]


class SlashMenu(Vertical):
    """斜杠命令菜单（浮层式）。"""

    DEFAULT_CSS = """
    SlashMenu {
        background: #24283b;
        border: round #bb9af7;
        width: 40;
        height: auto;
        padding: 0 1;
        layer: overlay;
    }
    SlashMenu > .menu-title {
        color: #bb9af7;
        text-style: bold;
        height: 1;
    }
    SlashMenu OptionList {
        background: #24283b;
        height: auto;
        max-height: 10;
    }
    SlashMenu OptionList > .option-list-option {
        color: #c0caf5;
    }
    SlashMenu OptionList > .option-list-option.--highlight {
        background: #2ac3de;
        color: #1a1b26;
    }
    """

    query: reactive[str] = reactive("")

    def compose(self):
        yield Static(t("tui.slash.title"), classes="menu-title")
        yield OptionList(id="slash-options")

    def watch_query(self, new: str) -> None:
        self._refresh_options(new)

    def _refresh_options(self, q: str) -> None:
        try:
            opt = self.query_one("#slash-options", OptionList)
        except Exception:
            return
        opt.clear_options()
        # 过滤：以 q 为前缀的 COMMANDS（保留顺序）
        matches = [c for c in COMMANDS if c.startswith(q)]
        if not matches:
            opt.add_option(Option(t("tui.slash.empty"), disabled=True))
            return
        for cmd in matches:
            opt.add_option(Option(cmd))

    def show(self) -> None:
        self.display = True

    def hide(self) -> None:
        self.display = False

    def toggle(self, q: str) -> None:
        """根据 query 决定显隐。"""
        if q.startswith("/") and " " not in q:
            self.query = q
            self.show()
        else:
            self.hide()

    def selected(self) -> str | None:
        """返回当前高亮项的命令字符串。"""
        try:
            opt = self.query_one("#slash-options", OptionList)
        except Exception:
            return None
        idx = opt.highlighted
        if idx is None:
            return None
        try:
            opt_o = opt.get_option_at_index(idx)
        except Exception:
            return None
        # Option.prompt 存的就是命令字符串
        return getattr(opt_o, "prompt", None)
