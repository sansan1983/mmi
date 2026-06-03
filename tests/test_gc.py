"""tests/test_gc.py —— core.gc 单元测试。

覆盖：
  - TTL 删除（trashed_at 早于 cutoff）
  - TTL 保留（trashed_at 晚于 cutoff）
  - dry-run：不真删
  - 兜底：trashed_at 缺失时用文件 mtime
  - 损坏文件：跳过但记 error
  - 空 trash：返回空 report
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from ulid import ULID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core import gc, paths, storage  # noqa: E402
from mmi.core.session import Session, SessionMeta  # noqa: E402


def _new_sid() -> str:
    return str(ULID())


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    yield tmp_path


def _write_trash_session(sid: str, *, trashed_at: str, body: str = ""):
    """写一个会话到 trash（trashed_at 可控）。

    move_to_trash 会把 trashed_at 设为当前时间，所以我们先 move 再覆写。
    """
    meta = SessionMeta.new(sid, title="trashed")
    s = Session(meta=meta, body=body)
    storage.write_session(s)
    storage.move_to_trash(sid)
    # 覆写 trashed_at
    s2 = storage.read_trash_session(sid)
    s2.meta.trashed_at = trashed_at
    # 直接 dump + 写回
    from mmi.core.storage import _dump_frontmatter
    p = storage.trash_path(sid)
    p.write_text(_dump_frontmatter(s2.meta) + s2.body, encoding="utf-8")


def _write_trash_file_raw(sid: str, body_text: str, *, mtime: datetime | None = None):
    """直接写 trash 目录文件（用于 mtime 兜底测试）。"""
    p = paths.get_trash_dir() / f"{sid}.session.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body_text, encoding="utf-8")
    if mtime is not None:
        os.utime(p, (mtime.timestamp(), mtime.timestamp()))


# ---------------------------------------------------------------------------
# 空 trash
# ---------------------------------------------------------------------------


def test_gc_empty_trash_returns_empty_report(isolated_home):
    report = gc.gc_trash(ttl_days=7)
    assert report.entries == []
    assert report.deleted_count == 0
    assert report.bytes_freed == 0


# ---------------------------------------------------------------------------
# TTL：早于 cutoff 删
# ---------------------------------------------------------------------------


def test_gc_deletes_old_session(isolated_home):
    sid = _new_sid()
    old = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    _write_trash_session(sid, trashed_at=old)
    report = gc.gc_trash(ttl_days=7)
    assert report.deleted_count == 1
    assert not (paths.get_trash_dir() / f"{sid}.session.md").exists()


def test_gc_keeps_recent_session(isolated_home):
    sid = _new_sid()
    recent = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    _write_trash_session(sid, trashed_at=recent)
    report = gc.gc_trash(ttl_days=7)
    assert report.deleted_count == 0
    assert (paths.get_trash_dir() / f"{sid}.session.md").exists()


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------


def test_gc_dry_run_does_not_delete(isolated_home):
    sid = _new_sid()
    old = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    _write_trash_session(sid, trashed_at=old, body="x" * 1000)
    report = gc.gc_trash(ttl_days=7, dry_run=True)
    assert len(report.entries) == 1
    assert report.entries[0].deleted is False
    assert report.deleted_count == 0
    assert report.bytes_freed == 0
    assert (paths.get_trash_dir() / f"{sid}.session.md").exists()


# ---------------------------------------------------------------------------
# 兜底：trashed_at 缺失用 mtime
# ---------------------------------------------------------------------------


def test_gc_falls_back_to_mtime_when_trashed_at_empty(isolated_home):
    sid = _new_sid()
    # trashed_at 空（直接写文件，绕过 move_to_trash）
    _write_trash_file_raw(
        sid,
        f"---\nversion: 1\nsession_id: {sid}\ntitle: legacy\n---\n\nbody\n",
        mtime=datetime.now() - timedelta(days=30),
    )
    report = gc.gc_trash(ttl_days=7)
    # 兜底用 mtime → 30 天 > 7 → 删
    matches = [e for e in report.entries if e.session_id == sid]
    assert len(matches) == 1
    assert matches[0].deleted is True


# ---------------------------------------------------------------------------
# 损坏文件
# ---------------------------------------------------------------------------


def test_gc_skips_corrupt_file(isolated_home):
    sid = _new_sid()
    _write_trash_file_raw(sid, "this is not valid frontmatter")
    report = gc.gc_trash(ttl_days=7)
    assert len(report.entries) == 1
    assert report.entries[0].error
    assert report.failed_count == 1
    # 文件没被删
    assert (paths.get_trash_dir() / f"{sid}.session.md").exists()


# ---------------------------------------------------------------------------
# 报告聚合
# ---------------------------------------------------------------------------


def test_gc_report_aggregates_counts(isolated_home):
    sid_old1 = _new_sid()
    sid_old2 = _new_sid()
    sid_new = _new_sid()
    old = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    new = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    _write_trash_session(sid_old1, trashed_at=old, body="x" * 100)
    _write_trash_session(sid_old2, trashed_at=old, body="x" * 200)
    _write_trash_session(sid_new, trashed_at=new)

    report = gc.gc_trash(ttl_days=7)
    assert report.deleted_count == 2
    assert report.kept_count == 1
    assert report.bytes_freed >= 300


# ---------------------------------------------------------------------------
# 自定义 ttl_days
# ---------------------------------------------------------------------------


def test_gc_custom_ttl(isolated_home):
    sid1 = _new_sid()
    sid2 = _new_sid()
    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # ttl=2: 3 天前 > 2 → 删
    _write_trash_session(sid1, trashed_at=three_days_ago)
    report = gc.gc_trash(ttl_days=2)
    assert report.deleted_count == 1

    # ttl=5: 3 天前 < 5 → 保留
    _write_trash_session(sid2, trashed_at=three_days_ago)
    report2 = gc.gc_trash(ttl_days=5)
    assert report2.deleted_count == 0
    assert (paths.get_trash_dir() / f"{sid2}.session.md").exists()


# ---------------------------------------------------------------------------
# Phase 4: zombie 清理
# ---------------------------------------------------------------------------


def _write_active_zombie(sid: str, *, cold_since: str, access_count: int = 1):
    """写一个 active 目录的 zombie 会话（state=zombie + cold_since 远超 90 天）。

    注意：必须把所有时间字段都设为 cold_since 之前 / 之后一致，
    否则 recency_bonus 会让 heat 涨到 active。
    """
    meta = SessionMeta.new(sid, title="zombie")
    meta.state = "zombie"
    meta.cold_since = cold_since
    meta.access_count = access_count
    # 设个老 created_at / last_access，让 recency_bonus = 0
    meta.created_at = cold_since
    meta.last_access = cold_since
    s = Session(meta=meta, body="")
    storage.write_session(s)


def test_gc_zombies_deletes_zombie_session(isolated_home):
    sid = _new_sid()
    long_ago = (datetime.now(timezone.utc) - timedelta(days=100)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    _write_active_zombie(sid, cold_since=long_ago)
    assert (paths.get_sessions_dir() / f"{sid}.session.md").exists()

    report = gc.gc_zombies()
    assert report.deleted_count == 1
    matches = [e for e in report.entries if e.session_id == sid]
    assert len(matches) == 1
    assert matches[0].kind == "zombie"
    assert matches[0].deleted is True
    assert not (paths.get_sessions_dir() / f"{sid}.session.md").exists()


def test_gc_zombies_dry_run_does_not_delete(isolated_home):
    sid = _new_sid()
    long_ago = (datetime.now(timezone.utc) - timedelta(days=100)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    _write_active_zombie(sid, cold_since=long_ago, access_count=5)
    report = gc.gc_zombies(dry_run=True)
    assert report.deleted_count == 0
    assert report.entries[0].deleted is False
    assert report.entries[0].kind == "zombie"
    assert (paths.get_sessions_dir() / f"{sid}.session.md").exists()


def test_gc_zombies_skips_non_zombie(isolated_home):
    """active 会话不是 zombie → 不出现在报告里。"""
    sid = _new_sid()
    meta = SessionMeta.new(sid, title="alive")
    # 默认 state=active, access=1, heat≈11
    s = Session(meta=meta, body="")
    storage.write_session(s)
    report = gc.gc_zombies()
    assert report.entries == []
    assert (paths.get_sessions_dir() / f"{sid}.session.md").exists()


def test_gc_zombies_promotes_cold_to_zombie(isolated_home):
    """cold 持续 > 90 天的会话 → gc 时重算 + 标记 zombie + 删除。"""
    sid = _new_sid()
    long_ago = (datetime.now(timezone.utc) - timedelta(days=100)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    # 写一个 state=cold 的会话（cold_since 100 天前）
    meta = SessionMeta.new(sid, title="aged")
    meta.state = "cold"
    meta.cold_since = long_ago
    meta.created_at = long_ago
    meta.last_access = long_ago
    meta.access_count = 1
    s = Session(meta=meta, body="")
    storage.write_session(s)

    report = gc.gc_zombies()
    matches = [e for e in report.entries if e.session_id == sid]
    assert len(matches) == 1
    assert matches[0].kind == "zombie"
    assert matches[0].deleted is True


# ---------------------------------------------------------------------------
# Phase 4: gc_all（合并 trash + zombie）
# ---------------------------------------------------------------------------


def test_gc_all_combines_trash_and_zombie(isolated_home):
    """trash 过期 + zombie 都被删，且 entries 包含两种 kind。"""
    trash_sid = _new_sid()
    zombie_sid = _new_sid()
    old = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    long_ago = (datetime.now(timezone.utc) - timedelta(days=100)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    _write_trash_session(trash_sid, trashed_at=old)
    _write_active_zombie(zombie_sid, cold_since=long_ago)

    report = gc.gc_all(ttl_days=7)
    assert report.deleted_count == 2
    assert {e.kind for e in report.entries} == {"trash", "zombie"}
    assert report.trash_entries[0].session_id == trash_sid
    assert report.zombie_entries[0].session_id == zombie_sid


def test_gc_all_empty(isolated_home):
    report = gc.gc_all()
    assert report.entries == []
    assert report.deleted_count == 0
