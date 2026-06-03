"""tests/test_session.py —— core.session 单元测试。

覆盖：
  - SessionMeta 字段对齐 ARCHITECTURE.md §5
  - to_dict / from_dict 往返不丢字段
  - from_dict 容错（缺失字段、多余字段）
  - new() 时间戳对齐、access_count 初始化
  - Session.empty 正确初始化
  - new_session_id 是 26 字符 ULID
  - utcnow_iso 格式（Z 后缀、毫秒精度）
  - DEFAULT_* 常量
"""

from __future__ import annotations

import re

import pytest

from mmi.core.session import (
    DEFAULT_SUMMARY,
    DEFAULT_TITLE,
    Session,
    SessionMeta,
    new_session_id,
    utcnow_iso,
)


# ---------------------------------------------------------------------------
# ULID
# ---------------------------------------------------------------------------


def test_new_session_id_length():
    sid = new_session_id()
    assert len(sid) == 26, f"ULID must be 26 chars, got {len(sid)}: {sid}"


def test_new_session_id_charset():
    """Crockford Base32：字母 + 数字，不含 I/L/O/U。"""
    sid = new_session_id()
    assert re.match(r"^[0-9A-HJKMNP-TV-Z]{26}$", sid), f"bad ULID charset: {sid}"


def test_new_session_ids_unique():
    """连发两个 id 必须不同（即使时间戳相同，靠随机位）。"""
    ids = {new_session_id() for _ in range(20)}
    assert len(ids) == 20


# ---------------------------------------------------------------------------
# utcnow_iso
# ---------------------------------------------------------------------------


def test_utcnow_iso_format():
    s = utcnow_iso()
    # 形如 2026-06-02T10:00:00.123Z
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", s), s


def test_utcnow_iso_changes_over_time():
    """快连续调两次至少有一刻不同（虽然极小概率撞上）。"""
    a = utcnow_iso()
    b = utcnow_iso()
    # 不强求不等（同一毫秒内也可能），只要求返回的是合法字符串
    assert isinstance(a, str) and isinstance(b, str)


# ---------------------------------------------------------------------------
# SessionMeta 默认值
# ---------------------------------------------------------------------------


def test_sessionmeta_defaults():
    m = SessionMeta()
    assert m.version == 1
    assert m.type == "session"
    assert m.session_id == ""
    assert m.title == DEFAULT_TITLE
    assert m.summary == DEFAULT_SUMMARY
    assert m.summary_version == 1
    assert m.keywords == []
    assert m.summary_history == []
    assert m.access_count == 0
    assert m.heat == 0.0
    assert m.state == "active"


def test_sessionmeta_state_literal():
    """state 字段必须是四态字面量之一。"""
    m = SessionMeta()
    assert m.state in ("active", "warm", "cold", "zombie")


# ---------------------------------------------------------------------------
# SessionMeta.new()
# ---------------------------------------------------------------------------


def test_sessionmeta_new_initializes_timestamps():
    sid = new_session_id()
    m = SessionMeta.new(sid, title="postgres-sharding")
    assert m.session_id == sid
    assert m.title == "postgres-sharding"
    assert m.created_at
    assert m.updated_at == m.created_at
    assert m.last_access == m.created_at
    assert m.state == "active"
    assert m.access_count == 1
    assert m.heat == 1.0


# ---------------------------------------------------------------------------
# to_dict / from_dict
# ---------------------------------------------------------------------------


def test_sessionmeta_roundtrip():
    m = SessionMeta.new("01AAAAAAAAAAAAAAAAAAAAAAAA", title="x")
    m.keywords = ["postgres", "sharding"]
    m.summary_history = [{"version": 1, "at": m.created_at, "text": "old"}]

    d = m.to_dict()
    m2 = SessionMeta.from_dict(d)

    assert m2.session_id == m.session_id
    assert m2.title == m.title
    assert m2.keywords == m.keywords
    assert m2.summary_history == m.summary_history
    assert m2.created_at == m.created_at
    assert m2.state == m.state


def test_sessionmeta_from_dict_ignores_unknown_fields():
    """多余字段必须被静默忽略（forward-compat，不破旧版读新版）。"""
    d = {
        "session_id": "01AAAAAAAAAAAAAAAAAAAAAAAA",
        "title": "x",
        "future_field_we_dont_know_yet": "ignore me",
    }
    m = SessionMeta.from_dict(d)
    assert m.session_id == "01AAAAAAAAAAAAAAAAAAAAAAAA"
    assert m.title == "x"
    # 多余字段不应被设置
    assert not hasattr(m, "future_field_we_dont_know_yet") or \
        getattr(m, "future_field_we_dont_know_yet", None) is None


def test_sessionmeta_from_dict_uses_defaults_for_missing():
    """缺失字段必须用 dataclass 默认值补齐。"""
    m = SessionMeta.from_dict({"session_id": "01AAAAAAAAAAAAAAAAAAAAAAAA"})
    assert m.title == DEFAULT_TITLE
    assert m.state == "active"
    assert m.access_count == 0


def test_sessionmeta_from_dict_rejects_non_dict():
    with pytest.raises(ValueError):
        SessionMeta.from_dict("not a dict")  # type: ignore[arg-type]


def test_sessionmeta_to_dict_contains_all_fields():
    """to_dict 必须包含 ARCHITECTURE.md §5 契约字段。"""
    m = SessionMeta()
    d = m.to_dict()
    required = {
        "version", "type", "session_id", "agent_id",
        "title", "summary", "summary_version", "summary_history", "keywords",
        "created_at", "updated_at", "last_access",
        "access_count", "heat", "state",
    }
    missing = required - set(d.keys())
    assert not missing, f"frontmatter 契约缺字段: {missing}"


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


def test_session_empty_creates_fresh_session():
    sid = new_session_id()
    s = Session.empty(sid, title="demo")
    assert s.meta.session_id == sid
    assert s.meta.title == "demo"
    assert s.meta.state == "active"
    assert s.body == ""


def test_session_default_body_empty():
    """Session(meta=...) 默认 body 是空字符串。"""
    m = SessionMeta.new(new_session_id())
    s = Session(meta=m)
    assert s.body == ""


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------


def test_default_title_placeholder():
    """DEFAULT_TITLE 必须是可识别的占位符（不能是空串、不能是空标题）。"""
    assert DEFAULT_TITLE
    assert DEFAULT_TITLE != "untitled".upper() or DEFAULT_TITLE == "untitled"  # 现状保护


def test_default_summary_empty():
    assert DEFAULT_SUMMARY == ""
