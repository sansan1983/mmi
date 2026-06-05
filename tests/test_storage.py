"""tests/test_storage.py —— core.storage 单元测试 + 并发锁验证。

覆盖：
  - 路径工具（session_path / lock_path / _validate_session_id）
  - 序列化（_dump_frontmatter / _parse_frontmatter 往返）
  - format_turn 输出格式
  - list_session_ids / read_meta / read_session
  - write_session / append_turn（含 access_count 自增、updated_at 更新）
  - move_to_trash / delete_session
  - 异常：SessionNotFound / SessionCorrupt / 非法 session_id
  - 并发：两个线程同时 append_turn 不撕裂、access_count 累加正确
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest
import yaml

from mmi.core import paths
from mmi.core.session import Session, SessionMeta, new_session_id
from mmi.core.storage import (
    SessionCorrupt,
    SessionNotFound,
    StorageError,
    append_turn,
    delete_session,
    format_turn,
    list_session_ids,
    lock_path,
    move_to_trash,
    read_meta,
    read_session,
    session_path,
    write_session,
)


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """隔离每个测试的 ~/.ctrim/，避免互相污染。"""
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    yield tmp_path


# ---------------------------------------------------------------------------
# 路径工具
# ---------------------------------------------------------------------------


def test_session_path_uses_active_dir(isolated_home):
    sid = "01AAAAAAAAAAAAAAAAAAAAAAAA"
    p = session_path(sid)
    assert p == isolated_home / "sessions" / "active" / f"{sid}.session.md"


def test_lock_path_sibling(isolated_home):
    """锁文件必须与会话文件同目录（方便锁作用域对齐）。"""
    sid = "01AAAAAAAAAAAAAAAAAAAAAAAA"
    assert lock_path(sid).parent == session_path(sid).parent


@pytest.mark.parametrize("bad_id", [
    "",
    "not-a-ulid",
    "01AAAAAAAAAAAAAAAAAAAAAAA",   # 25 字符
    "../etc/passwd",
    "01AAAAAAAAAAAAAAAAAAAAAAAAX", # 27 字符
    "abc",
])
def test_session_path_rejects_bad_ids(bad_id):
    with pytest.raises(ValueError):
        session_path(bad_id)


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def test_dump_and_parse_roundtrip(isolated_home):
    sid = new_session_id()
    m = SessionMeta.new(sid, title="roundtrip")
    m.keywords = ["a", "b"]
    s = Session(meta=m, body="## 2026-06-02\n\n**User:** hi\n\n**Assistant:** yo\n")
    write_session(s)
    s2 = read_session(sid)
    assert s2.meta.title == "roundtrip"
    assert s2.meta.keywords == ["a", "b"]
    assert "**User:** hi" in s2.body
    assert "**Assistant:** yo" in s2.body


def test_dump_uses_ordered_keys(isolated_home):
    """frontmatter 字段顺序应当与 ARCHITECTURE.md §5 对齐，方便 diff 友好。"""
    sid = new_session_id()
    m = SessionMeta.new(sid, title="x")
    s = Session(meta=m, body="")
    write_session(s)
    raw = session_path(sid).read_text(encoding="utf-8")
    # 找到 yaml 块
    yaml_match = re.search(r"^---\n(.*?)\n---", raw, re.DOTALL)
    assert yaml_match, raw
    yaml_text = yaml_match.group(1)
    parsed = yaml.safe_load(yaml_text)
    # 字段顺序：按 dataclass 字段定义
    keys = list(parsed.keys())
    assert keys[0] == "version"
    assert keys[1] == "type"
    assert keys[2] == "session_id"


def test_parse_rejects_missing_opening_dash(isolated_home):
    """没有开头的 --- 视为损坏。"""
    p = session_path(new_session_id())
    p.write_text("not yaml at all", encoding="utf-8")
    with pytest.raises(SessionCorrupt):
        read_meta(p.stem.removesuffix(".session"))


def test_parse_rejects_missing_closing_dash(isolated_home):
    """有开头没结尾 → 损坏。"""
    p = session_path(new_session_id())
    p.write_text("---\ntitle: x\n", encoding="utf-8")
    with pytest.raises(SessionCorrupt):
        read_meta(p.stem.removesuffix(".session"))


# ---------------------------------------------------------------------------
# format_turn
# ---------------------------------------------------------------------------


def test_format_turn_default_date():
    out = format_turn("hi", "hello")
    assert out.startswith("## ")
    assert "**User:** hi" in out
    assert "**Assistant:** hello" in out


def test_format_turn_explicit_date():
    out = format_turn("hi", "hello", date="2026-05-28")
    assert out.startswith("## 2026-05-28\n")


def test_format_turn_strips_surrounding_whitespace():
    out = format_turn("  hi  ", "  hello  ")
    assert "**User:** hi" in out
    assert "**Assistant:** hello" in out


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


def test_read_session_raises_not_found(isolated_home):
    with pytest.raises(SessionNotFound):
        read_session("01AAAAAAAAAAAAAAAAAAAAAAAA")


def test_read_meta_raises_not_found(isolated_home):
    with pytest.raises(SessionNotFound):
        read_meta("01AAAAAAAAAAAAAAAAAAAAAAAA")


def test_write_session_rejects_empty_id(isolated_home):
    s = Session(meta=SessionMeta(session_id=""), body="")
    with pytest.raises(StorageError):
        write_session(s)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_list_session_ids_empty(isolated_home):
    assert list_session_ids() == []


def test_list_session_ids_returns_all(isolated_home):
    ids = []
    for _ in range(3):
        sid = new_session_id()
        write_session(Session.empty(sid, title=sid))
        ids.append(sid)
    found = set(list_session_ids())
    assert found == set(ids)


def test_append_turn_increments_count(isolated_home):
    sid = new_session_id()
    write_session(Session.empty(sid, title="t"))

    s1 = append_turn(sid, "u1", "a1")
    assert s1.meta.access_count == 2  # new() 初始化为 1，append 后 +1
    assert s1.meta.access_count == read_meta(sid).access_count

    s2 = append_turn(sid, "u2", "a2")
    assert s2.meta.access_count == 3


def test_append_turn_updates_body(isolated_home):
    sid = new_session_id()
    write_session(Session.empty(sid, title="t"))
    append_turn(sid, "first", "first-reply")
    append_turn(sid, "second", "second-reply")
    s = read_session(sid)
    assert s.body.count("**User:**") == 2
    assert "first" in s.body
    assert "second" in s.body


def test_append_turn_updates_timestamps(isolated_home):
    sid = new_session_id()
    write_session(Session.empty(sid, title="t"))
    s1 = read_session(sid)
    initial_updated = s1.meta.updated_at
    initial_access = s1.meta.last_access

    s2 = append_turn(sid, "u", "a")
    # updated_at / last_access 必须晚于初始
    assert s2.meta.updated_at >= initial_updated
    assert s2.meta.last_access >= initial_access


# ---------------------------------------------------------------------------
# 移动 / 删除
# ---------------------------------------------------------------------------


def test_move_to_trash(isolated_home):
    sid = new_session_id()
    write_session(Session.empty(sid, title="t"))
    assert session_path(sid).exists()

    dst = move_to_trash(sid)
    assert dst == paths.get_trash_dir() / f"{sid}.session.md"
    assert dst.exists()
    assert not session_path(sid).exists()


def test_move_to_trash_not_found(isolated_home):
    with pytest.raises(SessionNotFound):
        move_to_trash("01AAAAAAAAAAAAAAAAAAAAAAAA")


def test_delete_session(isolated_home):
    sid = new_session_id()
    write_session(Session.empty(sid, title="t"))
    delete_session(sid)
    assert not session_path(sid).exists()
    assert not lock_path(sid).exists()


def test_delete_session_not_found(isolated_home):
    with pytest.raises(SessionNotFound):
        delete_session("01AAAAAAAAAAAAAAAAAAAAAAAA")


# ---------------------------------------------------------------------------
# 原子写
# ---------------------------------------------------------------------------


def test_atomic_write_does_not_leave_tmp(isolated_home, monkeypatch):
    """写失败时不应留下 .tmp 残留。"""

    # 强制 atomic write 失败
    def boom(self, *a, **kw):
        raise OSError("simulated rename failure")
    monkeypatch.setattr(Path, "rename", boom)

    sid = new_session_id()
    s = Session.empty(sid, title="t")
    with pytest.raises(OSError):
        write_session(s)
    # tmp 不应残留
    tmps = list(paths.get_sessions_dir().glob("*.tmp"))
    assert tmps == []


# ---------------------------------------------------------------------------
# 并发
# ---------------------------------------------------------------------------


def test_concurrent_append_no_corruption(isolated_home):
    """两个线程同时 append_turn 同一会话：都能成功，正文完整。"""
    sid = new_session_id()
    write_session(Session.empty(sid, title="concurrent"))

    barrier = threading.Barrier(2)

    def worker(prefix: str):
        barrier.wait()  # 两个线程对齐后同时冲
        for i in range(5):
            append_turn(sid, f"{prefix}-u{i}", f"{prefix}-a{i}")

    t1 = threading.Thread(target=worker, args=("A",))
    t2 = threading.Thread(target=worker, args=("B",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    s = read_session(sid)
    # 共 10 轮对话，user / assistant 各 10 行
    assert s.body.count("**User:**") == 10
    assert s.body.count("**Assistant:**") == 10
    # access_count 应当累加 10 次（new() 初始 1 + 10 = 11）
    assert s.meta.access_count == 11
    # A 和 B 双方都被写入
    assert "A-u0" in s.body and "B-u4" in s.body


# ---------------------------------------------------------------------------
# Phase 2：trashed_at 字段 + parse_turns / count_user_turns
# ---------------------------------------------------------------------------


def test_move_to_trash_sets_trashed_at(isolated_home):
    from mmi.core.storage import read_trash_session
    sid = new_session_id()
    write_session(Session.empty(sid, title="t"))
    move_to_trash(sid)
    s = read_trash_session(sid)
    assert s.meta.trashed_at != ""
    assert s.meta.trashed_at.endswith("Z")


def test_sessionmeta_trashed_at_default_empty():
    m = SessionMeta.new(new_session_id())
    assert m.trashed_at == ""


def test_parse_turns_empty():
    from mmi.core.storage import parse_turns
    assert parse_turns("") == []


def test_parse_turns_single_turn():
    from mmi.core.storage import parse_turns
    body = "## 2026-06-02\n\n**User:** hi\n\n**Assistant:** hello\n"
    turns = parse_turns(body)
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "hi"
    assert turns[1]["role"] == "assistant"
    assert turns[1]["content"] == "hello"


def test_parse_turns_multiple_turns():
    from mmi.core.storage import parse_turns
    body = (
        "## 2026-06-02\n\n"
        "**User:** u1\n\n**Assistant:** a1\n\n"
        "**User:** u2\n\n**Assistant:** a2\n"
    )
    turns = parse_turns(body)
    assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant"]
    assert [t["content"] for t in turns] == ["u1", "a1", "u2", "a2"]


def test_count_user_turns_empty():
    from mmi.core.storage import count_user_turns
    assert count_user_turns("") == 0


def test_count_user_turns_counts_only_user_blocks():
    from mmi.core.storage import count_user_turns
    body = "**User:** a\n\n**Assistant:** b\n\n**User:** c\n"
    assert count_user_turns(body) == 2


def test_list_trash_ids_empty(isolated_home):
    from mmi.core.storage import list_trash_ids
    assert list_trash_ids() == []


def test_list_trash_ids_finds_trashed_sessions(isolated_home):
    from mmi.core.storage import list_trash_ids
    sid1 = new_session_id()
    sid2 = new_session_id()
    write_session(Session.empty(sid1, title="a"))
    write_session(Session.empty(sid2, title="b"))
    move_to_trash(sid1)
    move_to_trash(sid2)
    found = list_trash_ids()
    assert sid1 in found
    assert sid2 in found


def test_trash_path_and_session_path_differ(isolated_home):
    from mmi.core.storage import trash_path
    sid = new_session_id()
    assert session_path(sid) != trash_path(sid)
    assert "active" in str(session_path(sid))
    assert "trash" in str(trash_path(sid))
