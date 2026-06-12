"""mmi.tui.history —— TUI 命令历史栈（持久化）。

ARCHITECTURE Phase 5：
  - ~/.mmi/.tui_history 存最近 1000 条
  - 启动加载、退出保存
  - Phase 5 简化版：纯函数式，持久化在 App 生命周期
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core import paths as paths_module

__all__ = ["HistoryStore", "HISTORY_FILENAME", "HISTORY_MAX"]


HISTORY_FILENAME = ".tui_history"
HISTORY_MAX = 1000


class HistoryStore:
    """命令历史持久化。

    设计：
      - items: list[str]（去重相邻重复；最新在末尾）
      - cursor: int（-1 = 不在历史中；>=0 表示在 history 的位置）
    """

    def __init__(self, max_size: int = HISTORY_MAX):
        self._items: list[str] = []
        self._cursor: int = -1
        self._max = max_size

    @property
    def items(self) -> list[str]:
        return list(self._items)

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

    def load(self, path: Path | None = None) -> None:
        p = path or (paths_module.get_root() / HISTORY_FILENAME)
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, list):
            return
        self._items = [str(x) for x in data if isinstance(x, str) and x.strip()][-self._max :]
        self._cursor = -1

    def save(self, path: Path | None = None) -> bool:
        p = path or (paths_module.get_root() / HISTORY_FILENAME)
        try:
            p.write_text(
                json.dumps(self._items, ensure_ascii=False, indent=None),
                encoding="utf-8",
            )
            return True
        except OSError:
            return False
