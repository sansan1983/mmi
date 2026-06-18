"""mmi.tui_v3._bridge —— SessionManager → TUI 适配层。

依赖项:mmi.core.manager, mmi.core.session。
被依赖:screens, _app。
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from mmi.core.manager import SessionManager
from mmi.core.session import SessionMeta


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

    def delete_session(self, session_id: str) -> None:
        with contextlib.suppress(Exception):
            self.mgr.delete(session_id)

    def stream_chat(self, session_id: str, user_input: str) -> Iterator[str]:
        yield from self.mgr.stream_chat(session_id, user_input)

    def search(self, query: str) -> list[SessionMeta]:
        return self.mgr.search(query)
