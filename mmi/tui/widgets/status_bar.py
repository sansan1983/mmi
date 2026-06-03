"""mmi.tui.widgets.status_bar —— 状态栏。

ARCHITECTURE Phase 5：4 字段状态栏
  sid (短) | heat | state | model

设计：
  - 用 textual.reactive 存字段；任何字段变化自动重渲染
  - 不持锁、不做 I/O —— 字段由调用方 set
  - 渲染走 compose()（textual 8.x 标准）
"""

from __future__ import annotations

from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static

from ...core.i18n import t

__all__ = ["StatusBar"]


class StatusBar(Horizontal):
    """横向 4 字段状态栏。"""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: #16161e;
    }
    StatusBar > .field {
        padding: 0 1;
    }
    StatusBar > .field.sid {
        color: #7aa2f7;
    }
    StatusBar > .field.heat {
        color: #e0af68;
    }
    StatusBar > .field.state-active {
        color: #9ece6a;
    }
    StatusBar > .field.state-warm {
        color: #bb9af7;
    }
    StatusBar > .field.state-cold {
        color: #565f89;
    }
    StatusBar > .field.state-zombie {
        color: #f7768e;
    }
    StatusBar > .field.model {
        color: #7dcfff;
    }
    """

    sid_short: reactive[str] = reactive("........")
    heat: reactive[str] = reactive("--")
    state: reactive[str] = reactive("active")
    model: reactive[str] = reactive("--")

    def compose(self):
        yield Static(self._render_sid(), classes="field sid", id="status-sid")
        yield Static(self._render_heat(), classes="field heat", id="status-heat")
        yield Static(self._render_state(), classes=f"field state-{self.state}", id="status-state")
        yield Static(self._render_model(), classes="field model", id="status-model")

    # ----- Reactive 变化时刷对应 widget ---------------------------------

    def watch_sid_short(self, new: str) -> None:
        try:
            self.query_one("#status-sid", Static).update(self._render_sid())
        except Exception:
            pass

    def watch_heat(self, new: str) -> None:
        try:
            self.query_one("#status-heat", Static).update(self._render_heat())
        except Exception:
            pass

    def watch_state(self, new: str) -> None:
        try:
            w = self.query_one("#status-state", Static)
            w.update(self._render_state())
            # 切 class 实现颜色切换
            w.set_class(False, "state-active", "state-warm", "state-cold", "state-zombie")
            w.add_class(f"state-{new}")
        except Exception:
            pass

    def watch_model(self, new: str) -> None:
        try:
            self.query_one("#status-model", Static).update(self._render_model())
        except Exception:
            pass

    # ----- 渲染 ---------------------------------------------------------

    def _render_sid(self) -> str:
        return t("tui.chat.status.sid", sid=self.sid_short)

    def _render_heat(self) -> str:
        return t("tui.chat.status.heat", heat=self.heat)

    def _render_state(self) -> str:
        return t("tui.chat.status.state", state=self.state)

    def _render_model(self) -> str:
        return t("tui.chat.status.model", model=self.model)

    # ----- 公共 API ------------------------------------------------------

    def update_session(self, *, sid: str, heat: float, state: str) -> None:
        """一次性刷 sid / heat / state（model 不动）。"""
        self.sid_short = sid[:8] if len(sid) > 8 else sid
        self.heat = f"{heat:.1f}" if isinstance(heat, (int, float)) else str(heat)
        self.state = state

    def update_model(self, model: str) -> None:
        self.model = model
