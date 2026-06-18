"""LLM.chat_with_retry 行为测试。"""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from mmi.core.exceptions import LLMRetryExhausted
from mmi.core.llm import LLMProvider


class _FakeLLM:
    """Stand-in for LLMProvider; just exposes a chat() method.

    Why not subclass LLMProvider?
      LLMProvider is an ABC with abstract chat/classify. Subclassing in
      tests forces us to also stub classify. Since chat_with_retry only
      uses self.chat(), we bind it as an unbound method to a duck-typed
      object — works as long as chat_with_retry doesn't touch other
      instance state.
    """

    def __init__(self, side_effects: list):
        self._side_effects = list(side_effects)
        self.call_count = 0
        self.sleeps: list[float] = []

    def chat(self, messages):
        self.call_count += 1
        eff = self._side_effects.pop(0) if self._side_effects else "ok"
        if isinstance(eff, Exception):
            raise eff
        return eff


def _retry(llm, messages, **kw):
    return LLMProvider.chat_with_retry(llm, messages, **kw)


def test_retry_on_timeout_then_success():
    timeout = httpx.TimeoutException("timeout")
    llm = _FakeLLM([timeout, "ok"])
    with patch("mmi.core.llm.base.time.sleep") as mock_sleep:
        result = _retry(llm, [{"role": "user", "content": "hi"}])
    assert result.reply == "ok"
    assert result.attempts == 2
    assert llm.call_count == 2
    assert mock_sleep.call_count == 1
    # 退避 0.5s
    assert mock_sleep.call_args.args == (0.5,)


def test_retry_on_5xx_then_success():
    # httpx.HTTPStatusError 5xx 可重试
    req = httpx.Request("POST", "https://api.example.com")
    resp = httpx.Response(503, request=req)
    err5xx = httpx.HTTPStatusError("503", request=req, response=resp)
    llm = _FakeLLM([err5xx, "ok"])
    with patch("mmi.core.llm.base.time.sleep"):
        result = _retry(llm, [])
    assert result.attempts == 2
    assert result.reply == "ok"


def test_retry_on_429_too_many_requests():
    req = httpx.Request("POST", "https://api.example.com")
    resp = httpx.Response(429, request=req)
    err429 = httpx.HTTPStatusError("429", request=req, response=resp)
    llm = _FakeLLM([err429, "ok"])
    with patch("mmi.core.llm.base.time.sleep"):
        result = _retry(llm, [])
    assert result.attempts == 2


def test_no_retry_on_4xx():
    req = httpx.Request("POST", "https://api.example.com")
    resp = httpx.Response(400, request=req)
    err400 = httpx.HTTPStatusError("400", request=req, response=resp)
    llm = _FakeLLM([err400])
    with pytest.raises(httpx.HTTPStatusError):
        _retry(llm, [])
    assert llm.call_count == 1  # 没重试


def test_retry_exhausted_raises():
    timeout = httpx.TimeoutException("timeout")
    llm = _FakeLLM([timeout, timeout, timeout])
    with patch("mmi.core.llm.base.time.sleep"):
        with pytest.raises(LLMRetryExhausted) as ei:
            _retry(llm, [])
    assert ei.value.attempts == 3
    assert llm.call_count == 3


def test_retry_backoff_timing():
    timeout = httpx.TimeoutException("timeout")
    llm = _FakeLLM([timeout, timeout, "ok"])
    sleeps: list[float] = []
    with patch("mmi.core.llm.base.time.sleep", side_effect=lambda s: sleeps.append(s)):
        result = _retry(llm, [])
    assert sleeps == [0.5, 1.0]  # 第 3 次成功前退避 0.5+1.0
    assert result.attempts == 3
