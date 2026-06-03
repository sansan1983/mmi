"""tests/test_paths.py —— core.paths 单元测试。

覆盖：
  - 默认根路径推断（~/.ctrim/）
  - MMI_HOME 环境变量覆盖
  - ensure_dirs idempotent（重复调用不报错）
  - 子目录路径构造正确
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mmi.core import paths


# ---------------------------------------------------------------------------
# fixture：每个测试隔离一个临时 MMI_HOME
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """让 paths.get_root() 返回 tmp_path，不污染真实 ~/.ctrim/。"""
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    yield tmp_path


# ---------------------------------------------------------------------------
# get_root
# ---------------------------------------------------------------------------


def test_get_root_default_uses_home(monkeypatch):
    """默认情况下根目录在 $HOME/.ctrim/。"""
    monkeypatch.delenv("MMI_HOME", raising=False)
    root = paths.get_root()
    assert root == (Path.home() / ".mmi").resolve()


def test_get_root_env_override(isolated_home):
    """MMI_HOME 必须覆盖默认 HOME 推断。"""
    assert paths.get_root() == isolated_home.resolve()


def test_get_root_returns_absolute(monkeypatch, tmp_path):
    """根路径必须是绝对路径（即使 MMI_HOME 是相对路径）。"""
    # 切到 tmp_path 再用相对路径，避免污染调用方 CWD
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MMI_HOME", "./relative-dir")
    root = paths.get_root()
    assert root.is_absolute()


# ---------------------------------------------------------------------------
# 子目录
# ---------------------------------------------------------------------------


def test_get_sessions_dir_layout(isolated_home):
    assert paths.get_sessions_dir() == isolated_home.resolve() / "sessions" / "active"


def test_get_trash_dir_layout(isolated_home):
    assert paths.get_trash_dir() == isolated_home.resolve() / "sessions" / "trash"


def test_get_index_path_layout(isolated_home):
    assert paths.get_index_path() == isolated_home.resolve() / "index.json"


def test_get_config_path_layout(isolated_home):
    assert paths.get_config_path() == isolated_home.resolve() / "config.toml"


def test_sessions_and_trash_are_siblings(isolated_home):
    """active 与 trash 必须是同级目录（统一受 sessions/ 管辖）。"""
    assert paths.get_sessions_dir().parent == paths.get_trash_dir().parent


# ---------------------------------------------------------------------------
# ensure_dirs
# ---------------------------------------------------------------------------


def test_ensure_dirs_creates_all(isolated_home):
    """首次调用应当创建根 + active + trash。"""
    assert not paths.get_sessions_dir().exists()
    assert not paths.get_trash_dir().exists()
    paths.ensure_dirs()
    assert paths.get_root().is_dir()
    assert paths.get_sessions_dir().is_dir()
    assert paths.get_trash_dir().is_dir()


def test_ensure_dirs_is_idempotent(isolated_home):
    """重复调用必须无副作用（不抛异常、不破坏现有文件）。"""
    paths.ensure_dirs()
    # 在已存在的目录里塞一个文件，再次 ensure_dirs 不应删除它
    sentinel = paths.get_sessions_dir() / "marker.session.md"
    sentinel.write_text("hello", encoding="utf-8")
    paths.ensure_dirs()
    paths.ensure_dirs()
    assert sentinel.read_text(encoding="utf-8") == "hello"


def test_ensure_dirs_returns_root(isolated_home):
    """方便链式调用：ensure_dirs() 必须返回根路径。"""
    assert paths.ensure_dirs() == isolated_home.resolve()


def test_ensure_dirs_handles_existing_root(isolated_home):
    """如果根目录已存在但子目录不存在，仍能补齐。"""
    isolated_home.mkdir(parents=True, exist_ok=True)
    paths.ensure_dirs()
    assert paths.get_sessions_dir().exists()
    assert paths.get_trash_dir().exists()


# ---------------------------------------------------------------------------
# 环境变量隔离回归
# ---------------------------------------------------------------------------


def test_env_override_does_not_leak_between_tests(monkeypatch, tmp_path):
    """两次设置不同的 MMI_HOME 必须各自独立解析。"""
    monkeypatch.setenv("MMI_HOME", str(tmp_path / "a"))
    root_a = paths.get_root()
    monkeypatch.setenv("MMI_HOME", str(tmp_path / "b"))
    root_b = paths.get_root()
    assert root_a != root_b
    assert root_a.name == "a"
    assert root_b.name == "b"
