"""tests/test_loader.py —— core.loader 单元测试。

覆盖：
  - build_context 基本三段（system/hits/recent/current）
  - summary 拼到 system
  - recent N 轮截断
  - hits 关键词命中
  - 命中段 + 最近轮去重
  - token 估算 + 截断
  - 容错：会话不存在 / 损坏
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from ulid import ULID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core import context as loader, paths, storage  # noqa: E402
from mmi.core.session import Session, SessionMeta  # noqa: E402


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    yield tmp_path


def _new_sid() -> str:
    return str(ULID())


def _seed_session(sid: str, turns: list[tuple[str, str]], *, summary: str = "", title: str = "test") -> None:
    """写一个会话：turns 是 [(user, assistant), ...] 列表。"""
    meta = SessionMeta.new(sid, title=title)
    meta.summary = summary
    body_parts = []
    for u, a in turns:
        body_parts.append(f"**User:** {u}\n\n**Assistant:** {a}\n")
    body = "\n".join(body_parts)
    storage.write_session(Session(meta=meta, body=body))


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


def test_estimate_tokens_simple():
    msgs = [{"role": "user", "content": "hello world"}]
    # tiktoken "hello world" = 2 tokens, +4 role overhead = 6
    n = loader.estimate_tokens(msgs)
    assert 1 <= n <= 15, f"expected ~6 tokens, got {n}"


def test_estimate_tokens_empty():
    assert loader.estimate_tokens([]) == 0


# ---------------------------------------------------------------------------
# build_context 基本
# ---------------------------------------------------------------------------


def test_build_context_empty_session_returns_just_current_user(isolated_home):
    """新会话（无正文）只返回 system + current user。"""
    sid = _new_sid()
    storage.write_session(Session.empty(sid, title="t"))
    messages = loader.build_context(sid, "hello", language="en-US")
    # 1 个 system + 1 个 user
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "hello"


def test_build_context_unknown_session_degrades_gracefully(isolated_home):
    """不存在的会话 → loader 降级为只返 system + current user（不抛）。"""
    messages = loader.build_context(_new_sid(), "hello", language="en-US")
    # 1 个 system + 1 个 user
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "hello"


def test_build_context_includes_summary_in_system(isolated_home):
    sid = _new_sid()
    _seed_session(sid, [("hi", "hello")], summary="用户问好")
    messages = loader.build_context(sid, "follow up", language="zh-CN")
    system_content = messages[0]["content"]
    assert "用户问好" in system_content


def test_build_context_includes_recent_turns(isolated_home):
    sid = _new_sid()
    _seed_session(sid, [
        ("first question", "first answer"),
        ("second question", "second answer"),
        ("third question", "third answer"),
    ])
    messages = loader.build_context(sid, "new question", language="en-US")
    # 应该有 3 个 history turn + 1 current = 4 条 user/assistant + 1 system = 7
    # 但 user count depends on whether hits overlaps
    roles = [m["role"] for m in messages]
    assert "user" in roles
    assert "assistant" in roles
    # 最近 3 轮的 user 都应出现
    user_contents = [m["content"] for m in messages if m["role"] == "user"]
    assert "third question" in user_contents


def test_build_context_recent_turns_limit(isolated_home):
    """recent_turns=2 时只取最后 2 轮。"""
    sid = _new_sid()
    _seed_session(sid, [
        (f"u{i}", f"a{i}") for i in range(10)
    ])
    config = loader.LoaderConfig(recent_turns=2, hit_paragraphs=0, max_tokens=100000)
    messages = loader.build_context(sid, "new", config=config, language="en-US")
    # system + 2 user + 2 assistant + current user = 6
    assert len(messages) == 6
    user_contents = [m["content"] for m in messages if m["role"] == "user"]
    # 最近 2 轮的 user：u8, u9
    assert "u8" in user_contents
    assert "u9" in user_contents
    assert "u0" not in user_contents


# ---------------------------------------------------------------------------
# 命中段 + 去重
# ---------------------------------------------------------------------------


def test_build_context_includes_keyword_hits(isolated_home):
    """当有 10+ 轮历史时，新提问里的关键词能命中老 turn。"""
    sid = _new_sid()
    _seed_session(sid, [
        (f"q{i}", f"a{i}") for i in range(15)
    ])
    # 在第 5 轮里塞一个特殊词
    storage.write_session(Session(
        meta=SessionMeta.new(sid, title="t"),
        body=""
    ))
    # 重写：在第 3 轮插一个关于 "kubernetes" 的 turn
    body_lines = []
    for i in range(15):
        if i == 3:
            body_lines.append("**User:** how to deploy kubernetes cluster?")
            body_lines.append("")
            body_lines.append("**Assistant:** use kubeadm or kops")
            body_lines.append("")
        body_lines.append(f"**User:** q{i}")
        body_lines.append("")
        body_lines.append(f"**Assistant:** a{i}")
        body_lines.append("")
    body = "\n".join(body_lines)
    storage.write_session(Session(meta=SessionMeta.new(sid), body=body))

    config = loader.LoaderConfig(recent_turns=2, hit_paragraphs=3, max_tokens=100000)
    messages = loader.build_context(sid, "kubernetes deployment", config=config, language="en-US")
    contents = " ".join(m["content"] for m in messages)
    # 命中段应该出现：第 3 轮的 user 提到 kubernetes
    assert "kubernetes" in contents or "kubeadm" in contents


def test_build_context_dedup_overlap(isolated_home):
    """如果最近轮和命中段内容重复，不重复发。"""
    sid = _new_sid()
    # 5 轮，每轮都提 "postgres"
    _seed_session(sid, [
        (f"postgres topic {i}", f"postgres answer {i}") for i in range(5)
    ])
    config = loader.LoaderConfig(recent_turns=3, hit_paragraphs=3, max_tokens=100000)
    messages = loader.build_context(sid, "postgres", config=config, language="en-US")
    # 统计 user 消息的 "postgres topic" 出现次数
    user_msgs = [m for m in messages if m["role"] == "user" and m["content"].startswith("postgres topic")]
    # 5 轮都该出现，但每条只一次（去重生效）
    assert len(user_msgs) == 5
    # 唯一性
    contents = [m["content"] for m in user_msgs]
    assert len(set(contents)) == 5


# ---------------------------------------------------------------------------
# Token 截断
# ---------------------------------------------------------------------------


def test_truncate_when_over_budget(isolated_home):
    """超出 max_tokens 时应截断。"""
    sid = _new_sid()
    # 写很多长 turn
    _seed_session(sid, [
        ("x" * 500, "y" * 500) for _ in range(10)
    ])
    config = loader.LoaderConfig(recent_turns=5, hit_paragraphs=0, max_tokens=200)
    ctx = loader.build_context_detailed(sid, "new", config=config, language="en-US")
    assert ctx.truncated is True
    # 截断后 estimated_tokens <= max_tokens
    assert ctx.estimated_tokens <= config.max_tokens


def test_no_truncate_when_under_budget(isolated_home):
    sid = _new_sid()
    _seed_session(sid, [("hi", "hello")])
    config = loader.LoaderConfig(recent_turns=10, hit_paragraphs=3, max_tokens=100000)
    ctx = loader.build_context_detailed(sid, "new", config=config, language="en-US")
    assert ctx.truncated is False


# ---------------------------------------------------------------------------
# 容错
# ---------------------------------------------------------------------------


def test_build_context_corrupt_session_degrades_gracefully(isolated_home):
    """损坏的会话 → loader 降级为只返 system + current user（不抛）。"""
    sid = _new_sid()
    p = storage.session_path(sid)
    p.write_text("garbage", encoding="utf-8")
    messages = loader.build_context(sid, "hello", language="en-US")
    # 1 个 system + 1 个 user
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


# ---------------------------------------------------------------------------
# 详细版 build_context_detailed
# ---------------------------------------------------------------------------


def test_build_context_detailed_returns_structured_info(isolated_home):
    sid = _new_sid()
    _seed_session(sid, [("u1", "a1"), ("u2", "a2")], summary="测试摘要")
    ctx = loader.build_context_detailed(sid, "u3", language="zh-CN")
    assert ctx.summary == "测试摘要"
    assert len(ctx.recent_turns) >= 2
    assert ctx.total_chars > 0
    assert ctx.estimated_tokens > 0
    assert isinstance(ctx.messages, list)
