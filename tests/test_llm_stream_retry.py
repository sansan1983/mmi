"""R8 4.8 测试:LLMProvider.stream_chat_with_retry 流式重试。

设计约束:
  - pre-yield 错误(还没消费任何 chunk)→ 可重试
  - mid-stream 错误(已 yield 一些 chunk)→ 不可重试,包成 StreamError 透传
  - 4xx → 不重试
  - 5xx / 429 / 网络错误 → 可重试(仅 pre-yield 阶段)
  - max_attempts=3,base_delay=0.5 指数退避(同 chat_with_retry)
"""
from __future__ import annotations

import httpx
import pytest

from mmi.core.exceptions import LLMRetryExhausted, StreamError
from mmi.core.llm import LLMProvider, Classification


# ---------------------------------------------------------------------------
# 假 LLM — 可控的 stream 行为
# ---------------------------------------------------------------------------


class _ScriptedStreamLLM(LLMProvider):
    """stream_chat 按预设剧本返回 chunks / errors。

    剧本是一组"尝试",每组内是 str → yield / Exception → raise。
    每次 stream_chat 调用消耗一组(用完该组用 None 补齐)。
    """
    name = "scripted-stream"

    def __init__(self, attempts: list[list[object]]) -> None:
        # attempts[i] = 第 i 次 stream_chat 调用应表现的剧本
        # 长度不够时补全 None(表示空流)
        self._attempts: list[list[object]] = attempts
        self._attempt_idx = 0  # 下次调 stream_chat 用哪个剧本
        self.call_count = 0

    def chat(self, messages, **kw):
        return "should-not-be-called"

    def classify(self, prompt, *, options):
        return Classification(choice=options[0], confidence=0.99)

    def stream_chat(self, messages, **kw):
        self.call_count += 1
        if self._attempt_idx < len(self._attempts):
            script = self._attempts[self._attempt_idx]
            self._attempt_idx += 1
        else:
            script = []
        for item in script:
            if item is None:
                continue
            if isinstance(item, Exception):
                raise item
            yield item


def _make_429() -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(
        "429", request=httpx.Request("POST", "http://x"),
        response=httpx.Response(429),
    )


def _make_500() -> httpx.HTTPStatusError:
    return httpx.Response(500)
    # 注:HTTPStatusError 需要 request+response,工厂函数封装


def _make_500_err() -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(
        "500", request=httpx.Request("POST", "http://x"),
        response=httpx.Response(500),
    )


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


def test_stream_retry_happy_path_no_retry():
    """无错误 → 1 次 stream_chat 调用,完整 yield。"""
    p = _ScriptedStreamLLM([["a", "b", "c"]])
    out = list(p.stream_chat_with_retry([{"role": "user", "content": "x"}]))
    assert out == ["a", "b", "c"]
    assert p.call_count == 1


def test_stream_retry_pre_yield_timeout_recovers():
    """pre-yield 网络错误 → 重试至成功。"""
    p = _ScriptedStreamLLM([
        [httpx.ConnectError("nope")],  # 第 1 次:连接失败,没 yield 任何东西
        ["hello"],                      # 第 2 次:成功
    ])
    out = list(p.stream_chat_with_retry([{"role": "user", "content": "x"}]))
    assert out == ["hello"]
    assert p.call_count == 2


def test_stream_retry_pre_yield_5xx_recovers():
    """pre-yield 5xx → 重试。"""
    p = _ScriptedStreamLLM([
        [_make_500_err()],
        ["recovered"],
    ])
    out = list(p.stream_chat_with_retry([{"role": "user", "content": "x"}]))
    assert out == ["recovered"]
    assert p.call_count == 2


def test_stream_retry_pre_yield_429_recovers():
    """pre-yield 429 → 重试。"""
    p = _ScriptedStreamLLM([
        [_make_429()],
        ["ok"],
    ])
    out = list(p.stream_chat_with_retry([{"role": "user", "content": "x"}]))
    assert out == ["ok"]
    assert p.call_count == 2


# ---------------------------------------------------------------------------
# 不可重试
# ---------------------------------------------------------------------------


def test_stream_retry_pre_yield_4xx_raises_immediately():
    """pre-yield 4xx → 不重试,直接抛。"""
    p = _ScriptedStreamLLM([
        [httpx.HTTPStatusError(
            "400", request=httpx.Request("POST", "http://x"),
            response=httpx.Response(400),
        )],
        ["should-not-reach"],
    ])
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        list(p.stream_chat_with_retry([{"role": "user", "content": "x"}]))
    assert exc_info.value.response.status_code == 400
    assert p.call_count == 1  # 没重试


def test_stream_retry_mid_stream_error_raises_stream_error():
    """mid-stream 错误(已 yield 了部分 chunk)→ 包成 StreamError 透传,不重试。"""
    p = _ScriptedStreamLLM([
        ["Hello", ", ", httpx.ConnectError("mid-stream")],  # mid-stream 断
    ])
    with pytest.raises(StreamError) as exc_info:
        list(p.stream_chat_with_retry([{"role": "user", "content": "x"}]))
    assert "mid-stream" in str(exc_info.value).lower()
    assert "2 chunks" in str(exc_info.value)
    assert p.call_count == 1  # 没重试


def test_stream_retry_mid_stream_5xx_raises_stream_error():
    """mid-stream 5xx → 包成 StreamError 透传,不重试。"""
    p = _ScriptedStreamLLM([
        ["a", _make_500_err()],  # mid-stream 5xx
    ])
    with pytest.raises(StreamError) as exc_info:
        list(p.stream_chat_with_retry([{"role": "user", "content": "x"}]))
    assert "1 chunks" in str(exc_info.value)
    assert p.call_count == 1


# ---------------------------------------------------------------------------
# 重试耗尽
# ---------------------------------------------------------------------------


def test_stream_retry_exhausts_after_max_attempts():
    """pre-yield 持续失败 → N 次后抛 LLMRetryExhausted。"""
    p = _ScriptedStreamLLM([[httpx.ConnectError("nope")]] * 5)  # 5 次调用,每次 pre-yield 失败
    with pytest.raises(LLMRetryExhausted) as exc_info:
        list(p.stream_chat_with_retry([{"role": "user", "content": "x"}], max_attempts=3))
    assert exc_info.value.attempts == 3
    assert p.call_count == 3  # 3 次后放弃


def test_stream_retry_exhausts_default_max_attempts_3():
    """默认 max_attempts=3。"""
    p = _ScriptedStreamLLM([[httpx.ConnectError("nope")]] * 5)
    with pytest.raises(LLMRetryExhausted) as exc_info:
        list(p.stream_chat_with_retry([{"role": "user", "content": "x"}]))
    assert exc_info.value.attempts == 3
    assert p.call_count == 3


# ---------------------------------------------------------------------------
# 退避时序
# ---------------------------------------------------------------------------


def test_stream_retry_uses_exponential_backoff(monkeypatch):
    """退避时序同 chat_with_retry:attempt N 退 base_delay * 2^(N-1)。"""
    sleep_calls: list[float] = []
    monkeypatch.setattr("mmi.core.llm.base.time.sleep", lambda s: sleep_calls.append(s))

    p = _ScriptedStreamLLM([
        [httpx.ConnectError("x")],  # 第 1 次
        [httpx.ConnectError("x")],  # 第 2 次
        ["ok"],                       # 第 3 次成功
    ])
    list(p.stream_chat_with_retry(
        [{"role": "user", "content": "x"}],
        max_attempts=3,
        base_delay=0.5,
    ))

    # max_attempts=3,前 2 次失败各 sleep 一次(0.5, 1.0)
    assert sleep_calls == [0.5, 1.0]
    assert p.call_count == 3  # 3 次调用(前 2 失败 + 第 3 成功)


# ---------------------------------------------------------------------------
# EchoLLMProvider 默认实现兼容
# ---------------------------------------------------------------------------


def test_echo_provider_stream_retry_works():
    """EchoLLMProvider.stream_chat 默认走 chat() 拆单 chunk — 重试包装后能正常 yield。"""
    from mmi.core.llm import EchoLLMProvider
    p = EchoLLMProvider()
    out = list(p.stream_chat_with_retry([{"role": "user", "content": "hi"}]))
    assert out == ["[echo] hi"]
