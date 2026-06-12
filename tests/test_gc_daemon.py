"""tests/test_gc_daemon.py —— 后台 GC daemon 测试。

覆盖：
  - DaemonGC 单例（get_instance 幂等）
  - on_chat_done 计数 + chat_interval 触发
  - enabled=False 时不触发
  - ensure_started 幂等（不重复启动线程）
  - gc_daemon 属性可访问
  - update_config 持久化 + 内存生效
  - 异常静默（gc_func 抛错不传播）
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core import paths  # noqa: E402
from mmi.core.gc_daemon import (  # noqa: E402
    DaemonGC,
    GcDaemonConfig,
    _get_gc_daemon,
    start_gc_daemon,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_daemon(monkeypatch, tmp_path):
    """每个测试用独立的 DaemonGC 实例（重置单例状态）。"""
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    # 重置单例
    DaemonGC._instance = None
    yield
    DaemonGC._instance = None


# ---------------------------------------------------------------------------
# GcDaemonConfig
# ---------------------------------------------------------------------------

def test_config_defaults():
    cfg = GcDaemonConfig()
    assert cfg.enabled is True
    assert cfg.chat_interval == 10
    assert cfg.sleep_seconds == 3600


def test_config_from_dict():
    cfg = GcDaemonConfig.from_dict({"enabled": False, "chat_interval": 5, "sleep_seconds": 7200})
    assert cfg.enabled is False
    assert cfg.chat_interval == 5
    assert cfg.sleep_seconds == 7200


def test_config_to_dict():
    cfg = GcDaemonConfig(enabled=False, chat_interval=7, sleep_seconds=1800)
    d = cfg.to_dict()
    assert d["enabled"] is False
    assert d["chat_interval"] == 7
    assert d["sleep_seconds"] == 1800


# ---------------------------------------------------------------------------
# DaemonGC 单例
# ---------------------------------------------------------------------------

def test_get_instance_returns_same_object():
    a = DaemonGC.get_instance()
    b = DaemonGC.get_instance()
    assert a is b


def test_get_instance_creates_with_default_config():
    dg = DaemonGC.get_instance()
    assert isinstance(dg.config, GcDaemonConfig)


# ---------------------------------------------------------------------------
# on_chat_done + chat_interval 触发
# ---------------------------------------------------------------------------

def test_on_chat_done_counts_up():
    dg = DaemonGC.get_instance()
    dg.config = GcDaemonConfig(enabled=True, chat_interval=3, sleep_seconds=9999)
    gc_calls = []
    dg._gc_func = lambda: gc_calls.append(1)
    dg.on_chat_done()
    dg.on_chat_done()
    assert len(gc_calls) == 0  # 还没到 interval


def test_on_chat_done_triggers_at_interval():
    dg = DaemonGC.get_instance()
    dg.config = GcDaemonConfig(enabled=True, chat_interval=3, sleep_seconds=9999)
    gc_calls = []
    dg._gc_func = lambda: gc_calls.append(1)
    dg.on_chat_done()
    dg.on_chat_done()
    dg.on_chat_done()  # 到达 interval → 触发
    assert len(gc_calls) == 1
    # 触发后计数器归零
    dg.on_chat_done()
    dg.on_chat_done()
    assert len(gc_calls) == 1  # 还差一次


def test_on_chat_done_disabled_skips(monkeypatch):
    # 重置单例
    DaemonGC._instance = None
    dg = DaemonGC(config=GcDaemonConfig(enabled=False))
    gc_calls = []
    dg._gc_func = lambda: gc_calls.append(1)
    for _ in range(10):
        dg.on_chat_done()
    assert len(gc_calls) == 0


def test_on_chat_done_gc_func_exception_swallowed():
    dg = DaemonGC.get_instance()
    dg.config = GcDaemonConfig(enabled=True, chat_interval=1, sleep_seconds=9999)
    dg._gc_func = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    # 不抛 → ok
    dg.on_chat_done()


# ---------------------------------------------------------------------------
# ensure_started 幂等
# ---------------------------------------------------------------------------

def test_ensure_started_starts_thread():
    dg = DaemonGC.get_instance()
    dg.config = GcDaemonConfig(enabled=True, sleep_seconds=9999)
    assert dg._thread is None
    dg.ensure_started()
    assert dg._thread is not None
    assert dg._thread.daemon is True
    assert dg._thread.is_alive()


def test_ensure_started_idempotent():
    dg = DaemonGC.get_instance()
    dg.config = GcDaemonConfig(enabled=True, sleep_seconds=9999)
    dg.ensure_started()
    t1 = dg._thread
    dg.ensure_started()  # 不再启动
    assert dg._thread is t1


def test_ensure_started_disabled_skips(monkeypatch):
    DaemonGC._instance = None
    dg = DaemonGC(config=GcDaemonConfig(enabled=False))
    dg.ensure_started()
    assert dg._thread is None


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

def test_stop_joins_thread():
    dg = DaemonGC.get_instance()
    dg.config = GcDaemonConfig(enabled=True, sleep_seconds=9999)
    dg.ensure_started()
    dg.stop()
    assert dg._thread is None


# ---------------------------------------------------------------------------
# update_config
# ---------------------------------------------------------------------------

def test_update_config_changes_memory(monkeypatch, tmp_path):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    DaemonGC._instance = None
    dg = DaemonGC.get_instance()
    new_cfg = GcDaemonConfig(enabled=True, chat_interval=7, sleep_seconds=1800)
    DaemonGC.update_config(new_cfg)
    assert dg.config.chat_interval == 7
    assert dg.config.sleep_seconds == 1800


# ---------------------------------------------------------------------------
# 模块级便利函数
# ---------------------------------------------------------------------------

def test_gc_daemon_singleton_accessible():
    # gc_daemon 模块属性 gc_daemon（延迟解析）每次返回同一实例
    from mmi.core.gc_daemon import _get_gc_daemon
    a = _get_gc_daemon()
    b = _get_gc_daemon()
    assert a is b


def test_start_gc_daemon_idempotent():
    start_gc_daemon()
    start_gc_daemon()  # 不抛
