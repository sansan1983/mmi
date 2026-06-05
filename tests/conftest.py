"""tests/conftest.py —— TUI 测试专用 fixture。

ARCHITECTURE Phase 5：
  - isolated_home：隔离 MMI_HOME
  - scripted_llm：可预设回复的 LLM provider
  - run_pilot：跑 textual app 测试

R8 跨期遗留 #8 收尾:ScriptedLLM 抽到 tests/_fakes.py,本文件保留 fixture
(scripted_llm_factory / make_app),不再定义 LLM 类。
"""
from __future__ import annotations

import asyncio

import pytest
from ulid import ULID

from mmi.core import paths
from mmi.core.llm import LLMProvider
from tests._fakes import ScriptedLLM


# R9 9.1: test_cli.py 已归档,加保险防止后续被恢复时跑出 ctrim 路径错误
collect_ignore_glob = ["test_cli.py"]


# ---------------------------------------------------------------------------
# isolated_home
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    yield tmp_path


# ---------------------------------------------------------------------------
# CTrimApp 工厂
# ---------------------------------------------------------------------------


@pytest.fixture
def make_app(isolated_home):
    """返回一个工厂：传 (manager_kwargs) 拿到 CTrimApp。"""

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
