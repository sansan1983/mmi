"""mmi.tui.widgets.header_bar —— 顶部信息条（LOGO + 状态）。

ARCHITECTURE：phase 5 最小版三段式布局的顶段。
- 高度 10%（在 ChatScreen 里通过 height: 10% 设定）
- 左侧 LOGO（大 C + 软件名，思考时切换 spinner）
- 右侧状态信息（模型 / 热度 / 状态）
- 底部 heavy 水平分割线
"""

from __future__ import annotations

from rich.text import Text
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static

from ...core.i18n import t

__all__ = ["HeaderBar"]


# 思考/流式时的旋转图标（10 帧）
_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


def _txt(s: str) -> Text:
    """str -> Rich Text，避开 Static._render 对 renderable 的要求。"""
    return Text(s, overflow="ellipsis")


# ASCII art 大 C（5 行 × 8 字符）
# 渐变：上 #7aa2f7（蓝）→ 中 #9ece6a（绿/过渡）→ 下 #bb9af7（紫）
_LOGO_LINES = [
    "  ██████  ",
    "  ██      ",
    "  ██      ",
    "  ██      ",
    "  ██████  ",
]
_LOGO_GRADIENT = ("#7aa2f7", "#7dafff", "#9ece6a", "#bb9af7", "#bb9af7")


def _logo_text() -> Text:
    """生成渐变大 C 的 Rich Text（每行一种颜色）。"""
    out = Text()
    for line, color in zip(_LOGO_LINES, _LOGO_GRADIENT):
        out.append(line + "\n", style=color)
    return out


class _Logo(Static):
    """LOGO widget：闲置显示渐变 ASCII 块 C + 名称，busy 时切换 spinner。

    设计：reactive 默认值不触发 watch_*，所以 on_mount 主动渲染一次初始内容。
    """

    DEFAULT_CSS = """
    _Logo {
        width: auto;
        padding: 0 1;
        color: #7aa2f7;
    }
    """

    busy: reactive[bool] = reactive(False)
    _frame: reactive[int] = reactive(0)

    def _idle_renderable(self):
        # LOGO + 名称横向排版：LOGO 5 行（高度 25% 的核心），右侧文字
        return Text.assemble(
            _logo_text(),
            "  ",
            (t("tui.app.name"), "bold #c0caf5"),
        )

    def _busy_text(self) -> str:
        return f"{_SPINNER_FRAMES[self._frame % len(_SPINNER_FRAMES)]} {t('tui.app.name')}  {t('tui.header.thinking')}"

    def on_mount(self) -> None:
        self.update(self._idle_renderable())

    def watch_busy(self, new: bool) -> None:
        if new:
            self._frame = 0
            self.update(_txt(self._busy_text()))
            self._tick()
        else:
            self.update(self._idle_renderable())

    def _tick(self) -> None:
        """推进一帧 spinner。"""
        if not self.busy:
            return
        self._frame += 1
        self.update(_txt(self._busy_text()))
        self.set_timer(0.08, self._tick)


class _StatusInfo(Static):
    """右侧状态信息：模型 + 热度 + 状态。"""

    DEFAULT_CSS = """
    _StatusInfo {
        width: 1fr;
        padding: 0 1;
        color: #c0caf5;
        text-align: right;
    }
    """

    model: reactive[str] = reactive("--")
    heat: reactive[str] = reactive("--")
    state: reactive[str] = reactive("active")

    def _text(self) -> str:
        return f"{t('tui.header.model', model=self.model)}  ·  {t('tui.header.heat', heat=self.heat)}  ·  {t('tui.header.state', state=self.state)}"

    def on_mount(self) -> None:
        self.update(_txt(self._text()))

    def watch_model(self, _: str) -> None:
        self.update(_txt(self._text()))

    def watch_heat(self, _: str) -> None:
        self.update(_txt(self._text()))

    def watch_state(self, _: str) -> None:
        self.update(_txt(self._text()))

    def update_session(self, *, model: str, heat: str, state: str) -> None:
        self.model = model
        self.heat = heat
        self.state = state


class HeaderBar(Horizontal):
    """顶部信息条：左 LOGO + 右状态信息；底部带分割线。"""

    DEFAULT_CSS = """
    HeaderBar {
        height: 25%;
        background: #1a1b26;
        border-bottom: solid #414868;
        padding: 0 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._logo = _Logo()
        self._info = _StatusInfo()

    def compose(self):
        yield self._logo
        yield self._info

    def set_busy(self, busy: bool) -> None:
        """切换 LOGO 的 busy 状态。"""
        self._logo.busy = busy

    def update_session(self, *, model: str, heat: str, state: str) -> None:
        self._info.update_session(model=model, heat=heat, state=state)
