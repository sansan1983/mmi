"""tests/conftest_tui.py —— TUI 测试专用 fixture。

ARCHITECTURE Phase 5：
  - isolated_home：隔离 MMI_HOME
  - scripted_llm：可预设回复的 LLM provider
  - run_pilot：跑 textual app 测试
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from ulid import ULID

from mmi.core import paths
from mmi.core.llm import Classification, LLMProvider


# ---------------------------------------------------------------------------
# isolated_home
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    yield tmp_path


# ---------------------------------------------------------------------------
# ScriptedLLM
# ---------------------------------------------------------------------------


class ScriptedLLM(LLMProvider):
    """可预设回复的 LLM，同时实现 chat() 和 stream_chat()。"""

    name = "scripted"

    def __init__(
        self,
        replies: list[str] | None = None,
        stream_chunks: list[list[str]] | None = None,
        support_stream: bool = True,
    ):
        self._replies = replies or ["stub reply"]
        self._call_count = 0
        self._stream_chunks = stream_chunks  # 每次 stream 调用的 chunk 列表
        self._support_stream = support_stream
        self.last_messages: list[dict] = []

    def chat(self, messages, *, max_tokens=512, temperature=0.7) -> str:
        self.last_messages = list(messages)
        idx = min(self._call_count, len(self._replies) - 1)
        reply = self._replies[idx]
        self._call_count += 1
        return reply

    def classify(self, prompt, *, options) -> Classification:
        return Classification(choice=options[0], confidence=0.99)

    def stream_chat(self, messages, *, max_tokens=512, temperature=0.7):
        if not self._support_stream:
            raise NotImplementedError("scripted LLM without stream support")
        self.last_messages = list(messages)
        if self._stream_chunks is not None:
            idx = min(self._call_count, len(self._stream_chunks) - 1)
            chunks = self._stream_chunks[idx]
        else:
            idx = min(self._call_count, len(self._replies) - 1)
            chunks = [self._replies[idx]]
        self._call_count += 1
        for c in chunks:
            yield c


# ---------------------------------------------------------------------------
# CTrimApp 工厂
# ---------------------------------------------------------------------------


@pytest.fixture
def make_app(isolated_home):
    """返回一个工厂函数：传 (manager_kwargs) 拿到 CTrimApp。"""

    def _factory(llm: LLMProvider | None = None):
        from mmi.core import manager as mgr_module
        from mmi.tui.app import CTrimApp

        mgr = mgr_module.SessionManager(llm=llm) if llm else mgr_module.SessionManager()
        return CTrimApp(mgr=mgr)

    return _factory


# ---------------------------------------------------------------------------
# Pilot helper
# ---------------------------------------------------------------------------


def new_sid() -> str:
    return str(ULID())


def _run(coro):
    """同步跑 async coroutine。"""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# ScriptedLLM 作为 fixture（让测试可以直接用参数注入）
# ---------------------------------------------------------------------------


@pytest.fixture
def scripted_llm_factory():
    """返回一个工厂：(replies=, stream_chunks=, support_stream=) -> ScriptedLLM。"""

    def _factory(**kwargs):
        return ScriptedLLM(**kwargs)

    return _factory
