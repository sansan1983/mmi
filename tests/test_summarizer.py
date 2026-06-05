"""tests/test_summarizer.py —— core.summarizer 单元测试。

覆盖：
  - should_update_summary：§8.3 三条触发规则
  - last_summary_turns / last_summary_at 辅助
  - update_summary：调 LLM / 推 history / 写盘 / 失败降级
  - summary 字段 + summary_version 递增
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from ulid import ULID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core import paths, storage, summarizer  # noqa: E402
from mmi.core.llm import LLMError, LLMProvider  # noqa: E402
from mmi.core.session import Session, SessionMeta  # noqa: E402


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    yield tmp_path


def _new_sid() -> str:
    return str(ULID())


class _StubLLM(LLMProvider):
    def __init__(self, summary: str = "新摘要"):
        self.name = "stub"
        self._summary = summary
        self.calls = 0
        self.fail_with: Exception | None = None

    def chat(self, messages, **kw):
        self.calls += 1
        if self.fail_with:
            raise self.fail_with
        return self._summary

    def classify(self, prompt, *, options):
        raise LLMError("not used")


def _seed(sid: str, *, n_turns: int, body_chars_each: int = 50, summary: str = ""):
    """写一个会话，n_turns 个 user turn。"""
    meta = SessionMeta.new(sid, title="t")
    meta.summary = summary
    body = ""
    for i in range(n_turns):
        body += f"**User:** turn {i} " + "x" * body_chars_each + "\n\n"
        body += f"**Assistant:** reply {i} " + "y" * body_chars_each + "\n\n"
    storage.write_session(Session(meta=meta, body=body))


# ---------------------------------------------------------------------------
# should_update_summary
# ---------------------------------------------------------------------------


def test_should_update_fresh_session_with_5_turns():
    """无 summary + 5 turns → 触发（首次生成）。"""
    meta = SessionMeta.new("01HXXXXXXXXXXXXXXXXXXXXXXX")
    body = ("**User:** a\n\n**Assistant:** b\n\n") * 5
    assert summarizer.should_update_summary(meta, body) is True


def test_should_update_fresh_session_with_2_turns():
    """无 summary + 2 turns → 不触发（turns < 5）。"""
    meta = SessionMeta.new("01HXXXXXXXXXXXXXXXXXXXXXXX")
    body = ("**User:** a\n\n**Assistant:** b\n\n") * 2
    assert summarizer.should_update_summary(meta, body) is False


def test_should_update_when_turn_delta_ge_20():
    """现有 summary + 后续 ≥ 20 turns → 触发。"""
    meta = SessionMeta.new("01HXXXXXXXXXXXXXXXXXXXXXXX")
    meta.summary = "old"
    meta.summary_history = [
        {"version": 1, "at": "2026-06-01T00:00:00.000Z", "text": "old", "turns_at": 0}
    ]
    body = ("**User:** a\n\n**Assistant:** b\n\n") * 20
    assert summarizer.should_update_summary(meta, body) is True


def test_should_update_when_chars_ge_5000():
    """body chars ≥ 5000 → 触发。"""
    meta = SessionMeta.new("01HXXXXXXXXXXXXXXXXXXXXXXX")
    meta.summary = "old"
    meta.summary_history = [
        {"version": 1, "at": "2026-06-01T00:00:00.000Z", "text": "old", "turns_at": 0}
    ]
    body = "x" * 5000
    assert summarizer.should_update_summary(meta, body) is True


def test_should_update_when_24h_plus_5_turns():
    """距离上次摘要 > 24h + ≥ 5 turns → 触发。"""
    meta = SessionMeta.new("01HXXXXXXXXXXXXXXXXXXXXXXX")
    meta.summary = "old"
    old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    meta.summary_history = [
        {"version": 1, "at": old_time, "text": "old", "turns_at": 0}
    ]
    body = ("**User:** a\n\n**Assistant:** b\n\n") * 5
    assert summarizer.should_update_summary(meta, body) is True


def test_should_not_update_recent_summary():
    """距离上次摘要 < 24h + 少 turns → 不触发。"""
    meta = SessionMeta.new("01HXXXXXXXXXXXXXXXXXXXXXXX")
    meta.summary = "old"
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    meta.summary_history = [
        {"version": 1, "at": recent, "text": "old", "turns_at": 10}
    ]
    body = ("**User:** a\n\n**Assistant:** b\n\n") * 3  # 3 turns，< 20
    assert summarizer.should_update_summary(meta, body) is False


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def test_last_summary_turns_empty():
    meta = SessionMeta.new("01HXXXXXXXXXXXXXXXXXXXXXXX")
    assert summarizer.last_summary_turns(meta) == 0


def test_last_summary_turns_with_history():
    meta = SessionMeta.new("01HXXXXXXXXXXXXXXXXXXXXXXX")
    meta.summary_history = [
        {"version": 1, "at": "2026-06-01T00:00:00.000Z", "text": "a", "turns_at": 5},
        {"version": 2, "at": "2026-06-02T00:00:00.000Z", "text": "b", "turns_at": 15},
    ]
    assert summarizer.last_summary_turns(meta) == 15


def test_last_summary_at_parses_z():
    meta = SessionMeta.new("01HXXXXXXXXXXXXXXXXXXXXXXX")
    meta.summary_history = [
        {"version": 1, "at": "2026-06-01T10:30:00.000Z", "text": "a", "turns_at": 5}
    ]
    dt = summarizer.last_summary_at(meta)
    assert dt is not None
    assert dt.year == 2026 and dt.month == 6 and dt.day == 1


# ---------------------------------------------------------------------------
# update_summary
# ---------------------------------------------------------------------------


def test_update_summary_first_time(isolated_home):
    """首次生成摘要：no summary → 调 LLM → summary 字段写入，version=2。"""
    sid = _new_sid()
    _seed(sid, n_turns=5)
    llm = _StubLLM(summary="这是新摘要")
    assert summarizer.update_summary(sid, llm, language="zh-CN") is True
    meta = storage.read_meta(sid)
    assert meta.summary == "这是新摘要"
    assert meta.summary_version == 2
    # 第一次 history 应该有一条（旧空 summary 不入 history）
    assert len(meta.summary_history) == 0


def test_update_summary_pushes_old_to_history(isolated_home):
    """二次更新：旧摘要推入 history，summary_version 递增。"""
    sid = _new_sid()
    _seed(sid, n_turns=20, summary="old summary")
    # 预设 history 一条（之前生成过）
    meta = storage.read_meta(sid)
    meta.summary_history.append({
        "version": 1, "at": "2026-06-01T00:00:00.000Z", "text": "old summary", "turns_at": 0
    })
    storage.write_session(Session(meta=meta, body=storage.read_session(sid).body))

    llm = _StubLLM(summary="newer summary")
    assert summarizer.update_summary(sid, llm) is True

    meta2 = storage.read_meta(sid)
    assert meta2.summary == "newer summary"
    assert meta2.summary_version == 2  # 1 -> 2
    # history 现在应该有 1 条：旧摘要 + 它的 turns_at
    assert len(meta2.summary_history) == 2
    assert meta2.summary_history[-1]["text"] == "old summary"


def test_update_summary_no_op_when_not_needed(isolated_home):
    """不满足触发条件 → update_summary 不调 LLM，不更新。"""
    sid = _new_sid()
    _seed(sid, n_turns=2, summary="fresh")
    meta = storage.read_meta(sid)
    meta.summary_history.append({
        "version": 1, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "text": "fresh", "turns_at": 0
    })
    storage.write_session(Session(meta=meta, body=storage.read_session(sid).body))

    llm = _StubLLM(summary="UNEXPECTED")
    assert summarizer.update_summary(sid, llm) is False
    # LLM 没被调
    assert llm.calls == 0


def test_update_summary_llm_failure_returns_false(isolated_home):
    sid = _new_sid()
    _seed(sid, n_turns=20, summary="old")
    llm = _StubLLM()
    llm.fail_with = LLMError("network down")
    assert summarizer.update_summary(sid, llm) is False
    # 摘要没被改
    meta = storage.read_meta(sid)
    assert meta.summary == "old"


def test_update_summary_unknown_session(isolated_home):
    llm = _StubLLM()
    assert summarizer.update_summary(_new_sid(), llm) is False
    assert llm.calls == 0


# ---------------------------------------------------------------------------
# schedule_summary_update（Phase 6：后台线程化）
# ---------------------------------------------------------------------------


def test_schedule_summary_update_returns_thread(isolated_home):
    """schedule_summary_update 应当返回一个 Thread-like 包装(daemon=True 语义)。"""
    from mmi.core import manager as mgr_module
    from tests.conftest import ScriptedLLM

    mgr = mgr_module.SessionManager(llm=ScriptedLLM())
    sid = mgr.create()
    t = summarizer.schedule_summary_update(sid, ScriptedLLM())
    # 兼容 Thread API:.join(timeout=) / .is_alive()
    assert hasattr(t, "join") and callable(t.join)
    assert hasattr(t, "is_alive") and callable(t.is_alive)
    t.join(timeout=2.0)  # 清理
    assert not t.is_alive()


def test_schedule_summary_update_does_not_block(isolated_home):
    """schedule 应当立即返回（不阻塞主流程）。"""
    import time
    from mmi.core import manager as mgr_module
    from tests.conftest import ScriptedLLM

    mgr = mgr_module.SessionManager(llm=ScriptedLLM())
    sid = mgr.create()
    t0 = time.monotonic()
    summarizer.schedule_summary_update(sid, ScriptedLLM())
    elapsed = time.monotonic() - t0
    # 立即返回，应当 < 100ms
    assert elapsed < 0.1, f"schedule took {elapsed*1000:.1f}ms, expected < 100ms"


def test_schedule_summary_update_swallows_exceptions(isolated_home):
    """后台线程任何异常都应被吞掉，不影响主流程。"""
    from mmi.core import manager as mgr_module
    from tests.conftest import ScriptedLLM

    mgr = mgr_module.SessionManager(llm=ScriptedLLM())
    mgr.create()
    # 不存在的 session_id → update_summary 会 catch SessionNotFound 返 False
    # 但 schedule 不应抛任何异常
    t = summarizer.schedule_summary_update("not-a-real-ulid-xxxxxxxxxx", ScriptedLLM())
    t.join(timeout=2.0)
    assert not t.is_alive()  # 线程已结束
