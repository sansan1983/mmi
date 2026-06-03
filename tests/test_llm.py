"""tests/test_llm.py —— core.llm 单元测试。

覆盖：
  - LLMError 异常
  - Classification 数据类
  - EchoLLMProvider：chat 行为 / classify 行为
  - OpenAILLMProvider：chat 成功 / chat 失败 / classify JSON 解析
  - get_default_provider() 工厂：无 key → echo，有 key → OpenAI
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core.llm import (  # noqa: E402
    Classification,
    EchoLLMProvider,
    LLMError,
    LLMProvider,
    OpenAILLMProvider,
    get_default_provider,
    reset_default_provider_for_test,
)


# ---------------------------------------------------------------------------
# 抽象类不能直接实例化
# ---------------------------------------------------------------------------


def test_llm_provider_is_abstract():
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_classification_is_high_confidence():
    assert Classification("yes", 0.8).is_high_confidence(0.6) is True
    assert Classification("yes", 0.5).is_high_confidence(0.6) is False
    assert Classification("yes", 0.6).is_high_confidence(0.6) is True


# ---------------------------------------------------------------------------
# EchoLLMProvider
# ---------------------------------------------------------------------------


def test_echo_chat_returns_user_content_with_prefix():
    p = EchoLLMProvider()
    out = p.chat([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "ping"},
    ])
    assert out == "[echo] ping"


def test_echo_chat_with_no_user_returns_empty():
    p = EchoLLMProvider()
    out = p.chat([{"role": "system", "content": "sys"}])
    assert out == "[echo] "


def test_echo_chat_uses_last_user_message():
    p = EchoLLMProvider()
    out = p.chat([
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ack"},
        {"role": "user", "content": "second"},
    ])
    assert "second" in out
    assert "first" not in out


def test_echo_classify_returns_first_option_high_confidence():
    p = EchoLLMProvider()
    r = p.classify("is this real?", options=["yes", "no"])
    assert r.choice == "yes"
    assert r.confidence >= 0.6   # 不误判为 trash
    assert r.raw.startswith("echo:")


def test_echo_classify_empty_options_raises():
    p = EchoLLMProvider()
    with pytest.raises(LLMError):
        p.classify("x", options=[])


# ---------------------------------------------------------------------------
# OpenAILLMProvider：mock openai 包
# ---------------------------------------------------------------------------


class _FakeCompletions:
    def __init__(self, content="hello"):
        self._content = content

    def create(self, **kwargs):
        return _FakeChatResponse(self._content)


class _FakeChatResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeOpenAIClient:
    def __init__(self, content="hello"):
        self.chat = _FakeChatNamespace(content)


class _FakeChatNamespace:
    def __init__(self, content):
        self.completions = _FakeCompletions(content)


def _make_provider(content: str = "hello") -> OpenAILLMProvider:
    """构造一个 OpenAILLMProvider，但 client 用假的（避免真联网）。"""
    p = OpenAILLMProvider.__new__(OpenAILLMProvider)
    p.model = "gpt-4o-mini"
    p.client = _FakeOpenAIClient(content)  # type: ignore[attr-defined]
    return p


def test_openai_chat_returns_content():
    p = _make_provider(content="hi there")
    out = p.chat([{"role": "user", "content": "x"}])
    assert out == "hi there"


def test_openai_chat_empty_content_raises():
    p = _make_provider(content=None)  # type: ignore[arg-type]
    with pytest.raises(LLMError, match="empty content"):
        p.chat([{"role": "user", "content": "x"}])


def test_openai_classify_parses_json():
    import json

    p = OpenAILLMProvider.__new__(OpenAILLMProvider)
    p.model = "gpt-4o-mini"

    fake_json = json.dumps({"choice": "no", "confidence": 0.3})
    p.client = _FakeOpenAIClient(fake_json)  # type: ignore[attr-defined]
    r = p.classify("x", options=["yes", "no"])
    assert r.choice == "no"
    assert r.confidence == 0.3


def test_openai_classify_clamps_confidence_to_0_1():
    import json

    p = OpenAILLMProvider.__new__(OpenAILLMProvider)
    p.model = "gpt-4o-mini"

    fake_json = json.dumps({"choice": "yes", "confidence": 1.5})
    p.client = _FakeOpenAIClient(fake_json)  # type: ignore[attr-defined]
    r = p.classify("x", options=["yes", "no"])
    assert r.confidence == 1.0


def test_openai_classify_unknown_choice_falls_back_to_first():
    import json

    p = OpenAILLMProvider.__new__(OpenAILLMProvider)
    p.model = "gpt-4o-mini"

    fake_json = json.dumps({"choice": "maybe", "confidence": 0.5})
    p.client = _FakeOpenAIClient(fake_json)  # type: ignore[attr-defined]
    r = p.classify("x", options=["yes", "no"])
    assert r.choice == "yes"   # 兜底到第一个


def test_openai_classify_bad_json_raises():
    p = OpenAILLMProvider.__new__(OpenAILLMProvider)
    p.model = "gpt-4o-mini"
    p.client = _FakeOpenAIClient("not json")  # type: ignore[attr-defined]
    with pytest.raises(LLMError, match="bad JSON"):
        p.classify("x", options=["yes", "no"])


def test_openai_construct_without_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        OpenAILLMProvider()


# ---------------------------------------------------------------------------
# get_default_provider 工厂
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_factory():
    reset_default_provider_for_test()
    yield
    reset_default_provider_for_test()


def test_default_factory_returns_echo_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = get_default_provider()
    assert isinstance(p, EchoLLMProvider)


def test_default_factory_caches(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p1 = get_default_provider()
    p2 = get_default_provider()
    assert p1 is p2


def test_default_factory_returns_openai_with_key(monkeypatch):
    # monkeypatch openai.OpenAI 来避免真 import/连接
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-xxx")
    monkeypatch.setattr("openai.OpenAI", lambda **kw: _FakeOpenAIClient())
    p = get_default_provider()
    assert isinstance(p, OpenAILLMProvider)
    assert p.model == "gpt-4o-mini"


def test_default_factory_respects_model_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-xxx")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setattr("openai.OpenAI", lambda **kw: _FakeOpenAIClient())
    p = get_default_provider()
    assert p.model == "gpt-4o"


# ---------------------------------------------------------------------------
# Phase 5: stream_chat
# ---------------------------------------------------------------------------


class _FakeStreamingCompletions:
    """模拟 OpenAI stream=True 返回的同步 generator。"""

    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    def create(self, **kwargs):
        return iter([_FakeStreamChunk(c) for c in self._chunks])


class _FakeStreamChunk:
    def __init__(self, content: str):
        self.choices = [_FakeStreamChoice(content)]


class _FakeStreamChoice:
    def __init__(self, content: str):
        self.delta = _FakeDelta(content)


class _FakeDelta:
    def __init__(self, content: str):
        self.content = content


def _make_streaming_provider(chunks: list[str]) -> OpenAILLMProvider:
    p = OpenAILLMProvider.__new__(OpenAILLMProvider)
    p.model = "gpt-4o-mini"
    fake_client = type(
        "FakeClient",
        (),
        {"chat": type("C", (), {"completions": _FakeStreamingCompletions(chunks)})()},
    )()
    p.client = fake_client  # type: ignore[attr-defined]
    return p


def test_echo_stream_chat_sync_wrapper():
    """Echo 流式（同步入口）：用 asyncio.run 跑 async generator。"""
    import asyncio
    from mmi.core.llm import EchoLLMProvider

    async def _collect():
        gen = EchoLLMProvider().stream_chat([{"role": "user", "content": "hi"}])
        out = []
        async for c in gen:
            out.append(c)
        return out

    assert asyncio.run(_collect()) == ["[echo] hi"]


def test_openai_stream_chat_sync_wrapper():
    """OpenAI 流式（同步入口）：分片正确拼接。"""
    p = _make_streaming_provider(["Hello", ", ", "world!"])
    import asyncio

    async def _collect():
        out = []
        async for c in p.stream_chat([{"role": "user", "content": "x"}]):
            out.append(c)
        return out

    assert asyncio.run(_collect()) == ["Hello", ", ", "world!"]


def test_stream_chat_default_raises_not_implemented():
    """基类 LLMProvider.stream_chat 默认抛 NotImplementedError。"""
    import asyncio
    from mmi.core.llm import LLMProvider, Classification

    class _NoStream(LLMProvider):
        name = "no-stream"

        def chat(self, messages, **kw):
            return "x"

        def classify(self, prompt, *, options):
            return Classification(choice=options[0], confidence=0.5)

    p = _NoStream()

    async def _drain():
        gen = p.stream_chat([{"role": "user", "content": "x"}])
        async for _ in gen:
            pass

    with pytest.raises(NotImplementedError, match="does not support stream_chat"):
        asyncio.run(_drain())
