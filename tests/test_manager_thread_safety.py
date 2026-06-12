"""tests/test_manager_thread_safety.py —— P1A-3 SessionManager 线程安全测试。

覆盖：
  - 并发 create() 不产生重复 session_id
  - 并发 chat() 不出现数据竞争（写会话正常）
  - _recompute_heat 线程安全（两阶段读-算-写）
  - batch_* 并发场景（ThreadPoolExecutor 路径）
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core import paths, storage  # noqa: E402
from mmi.core.storage import list_session_ids  # noqa: E402
from mmi.core.manager import SessionManager, ChatResult  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    yield tmp_path


@pytest.fixture
def manager(isolated_home):
    return SessionManager()


# ---------------------------------------------------------------------------
# 并发 create
# ---------------------------------------------------------------------------

def test_concurrent_create_no_duplicate_ids(manager):
    """多个线程同时 create()，返回的 session_id 必须互不重复。"""
    n = 20
    ids: list[str] = []
    errors: list[Exception] = []

    def worker():
        try:
            sid = manager.create()
            ids.append(sid)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"create raised: {errors}"
    assert len(ids) == n
    assert len(set(ids)) == n, "duplicate session_id detected"


def test_concurrent_create_all_persisted(manager):
    """并发 create 的会话全部可读（写盘成功）。"""
    n = 10
    ids: list[str] = []

    def worker():
        sid = manager.create()
        ids.append(sid)

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(worker) for _ in range(n)]
        for f in futures:
            f.result()

    for sid in ids:
        s = storage.read_session(sid)
        assert s.meta.session_id == sid


# ---------------------------------------------------------------------------
# 并发 _recompute_heat（通过 chat）
# ---------------------------------------------------------------------------

def test_concurrent_chat_no_corruption(manager):
    """多线程同时 chat 同一会话，不出现数据损坏（每个 chat 成功返回）。

    注意：Windows 下并发写同一文件受文件锁限制，此处测多会话并发
    （各线程操作不同会话，无文件锁冲突），验证 Manager._lock 的
    逻辑线程安全。
    """
    n = 5

    def worker(i: int):
        sid = manager.create(title=f"concurrent-{i}")
        result = manager.chat(sid, f"ping thread-{i}")
        assert result.reply, "chat returned empty reply"

    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = [ex.submit(worker, i) for i in range(n)]
        for f in futures:
            f.result()

    # 验证所有会话都写成功了
    assert len(list_session_ids()) >= n


# ---------------------------------------------------------------------------
# batch_* 并发
# ---------------------------------------------------------------------------

def test_batch_chat_concurrent(manager):
    """batch_chat 多会话并发 chat（需要 mock orchestrator）。"""
    from unittest.mock import MagicMock
    sid = manager.create(title="batch-concurrent-test")
    # batch_chat 走 self.orchestrator.chat，需要 mock
    manager.orchestrator = MagicMock()
    manager.orchestrator.chat.return_value = ChatResult(
        reply="[echo] reply",
    )
    items = [(sid, f"batch msg {i}") for i in range(8)]
    results = manager.batch_chat(items)
    assert len(results) == 8
    for r in results:
        assert r.reply.startswith("[echo]"), f"expected EchoLLM reply, got {r.reply!r}"


def test_batch_touch_concurrent(manager):
    """batch_touch 并发不抛（单条失败只 log）。"""
    sid = manager.create(title="batch-touch-test")
    manager.batch_touch([sid, sid, sid, "fake-id", sid])
    # fake-id 跳过，但其他不应抛
    meta = manager.get_session_meta(sid)
    assert meta.access_count >= 3
