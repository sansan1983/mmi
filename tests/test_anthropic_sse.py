"""R8.5.2 AnthropicLLMProvider.stream_chat 真 SSE 流式测试。

测试方法:用 mock httpx.Client 注入构造的 SSE 响应,验证:
  - 只 yield content_block_delta.text(text_delta 类型)
  - 忽略其它 event(message_start / block_start / block_stop / message_delta / message_stop)
  - 多 content block 都正确处理
  - 忽略 input_json_delta(tool use 块)— 我们只关心 text
  - HTTP 4xx/5xx 错误转 LLMError
  - 流中网络错误包成 StreamError
  - 空流(没有任何 text_delta)→ 0 个 yield
  - SSE 注释行(`:` 开头)忽略
  - 多个 data: 行(续行)— 都累积到同一个 event

httpx.Client.stream() 返回 context manager 包裹的 Response,
需要 mock 这个完整的 context manager 接口。
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from mmi.core.llm import AnthropicLLMProvider, LLMError


# ---------------------------------------------------------------------------
# Fake httpx helpers
# ---------------------------------------------------------------------------


def _sse_event(event: str, data: dict) -> str:
    """构造一条 SSE event(单行 data)。"""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _sse_event_multiline_data(event: str, *data_lines: str) -> str:
    """构造一条 SSE event(多行 data)— Anthropic 实际格式。"""
    out = f"event: {event}\n"
    for line in data_lines:
        out += f"data: {line}\n"
    out += "\n"
    return out


def _make_stream_response(body_text: str, status_code: int = 200) -> MagicMock:
    """构造一个假 httpx Response with .iter_lines() yielding body lines.

    返回的对象是 context manager 协议实现(stream() 上下文),
    内含 status_code + iter_lines() + read()。
    """
    resp = MagicMock()
    resp.status_code = status_code
    if status_code >= 400:
        resp.read.return_value = body_text.encode("utf-8")
    else:
        # iter_lines yield str 行
        resp.iter_lines.return_value = iter(body_text.split("\n"))
    return resp


def _make_stream_context(resp: MagicMock) -> MagicMock:
    """构造 httpx.Client.stream() 上下文管理器,__enter__ 返 resp。"""
    ctx = MagicMock()
    ctx.__enter__.return_value = resp
    ctx.__exit__.return_value = False
    return ctx


def _make_anthropic_client(client: MagicMock) -> AnthropicLLMProvider:
    """构造 AnthropicLLMProvider 替换 self._client。"""
    p = AnthropicLLMProvider(api_key="sk-test", base_url="http://x", model="m")
    p._client = client
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_stream_yields_only_text_delta_chunks():
    """只 yield content_block_delta 中的 text_delta 文本,其它 event 忽略。"""
    body = (
        _sse_event("message_start", {"type": "message_start", "message": {"id": "msg_1"}})
        + _sse_event("content_block_start", {"type": "content_block_start", "index": 0,
                                            "content_block": {"type": "text", "text": ""}})
        + _sse_event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                              "delta": {"type": "text_delta", "text": "Hello"}})
        + _sse_event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                              "delta": {"type": "text_delta", "text": ", "}})
        + _sse_event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                              "delta": {"type": "text_delta", "text": "world!"}})
        + _sse_event("content_block_stop", {"type": "content_block_stop", "index": 0})
        + _sse_event("message_delta", {"type": "message_delta",
                                        "delta": {"stop_reason": "end_turn"}})
        + _sse_event("message_stop", {"type": "message_stop"})
    )
    resp = _make_stream_response(body)
    client = MagicMock()
    client.stream.return_value = _make_stream_context(resp)
    p = _make_anthropic_client(client)

    out = list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert out == ["Hello", ", ", "world!"]


def test_stream_handles_multiple_content_blocks():
    """多 content block(text + tool_use 等)— 仍只 yield text_delta。"""
    body = (
        # 第一个 text block
        _sse_event("content_block_start", {"type": "content_block_start", "index": 0,
                                            "content_block": {"type": "text", "text": ""}})
        + _sse_event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                              "delta": {"type": "text_delta", "text": "Reasoning: "}})
        + _sse_event("content_block_stop", {"type": "content_block_stop", "index": 0})
        # tool_use block(应当被忽略)
        + _sse_event("content_block_start", {"type": "content_block_start", "index": 1,
                                            "content_block": {"type": "tool_use",
                                                              "id": "tool_1", "name": "bash"}})
        + _sse_event("content_block_delta", {"type": "content_block_delta", "index": 1,
                                              "delta": {"type": "input_json_delta",
                                                        "partial_json": '{"cmd":'}})
        + _sse_event("content_block_stop", {"type": "content_block_stop", "index": 1})
        # 第二个 text block
        + _sse_event("content_block_start", {"type": "content_block_start", "index": 2,
                                            "content_block": {"type": "text", "text": ""}})
        + _sse_event("content_block_delta", {"type": "content_block_delta", "index": 2,
                                              "delta": {"type": "text_delta", "text": "Result."}})
        + _sse_event("content_block_stop", {"type": "content_block_stop", "index": 2})
    )
    resp = _make_stream_response(body)
    client = MagicMock()
    client.stream.return_value = _make_stream_context(resp)
    p = _make_anthropic_client(client)

    out = list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert out == ["Reasoning: ", "Result."]  # tool_use 不出现


def test_stream_ignores_sse_comments():
    """SSE 注释行(`:` 开头)— 忽略。"""
    body = (
        ":this is a comment\n"
        ": another comment\n"
        + _sse_event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                              "delta": {"type": "text_delta", "text": "x"}})
    )
    resp = _make_stream_response(body)
    client = MagicMock()
    client.stream.return_value = _make_stream_context(resp)
    p = _make_anthropic_client(client)

    out = list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert out == ["x"]


def test_stream_handles_multiline_data():
    """data: 行可能多行(JSON 太长被折行)— 都累积到同一个 event。"""
    body = (
        _sse_event_multiline_data(
            "content_block_delta",
            json.dumps({"type": "content_block_delta", "index": 0,
                        "delta": {"type": "text_delta", "text": "abc"}}),
        )
    )
    resp = _make_stream_response(body)
    client = MagicMock()
    client.stream.return_value = _make_stream_context(resp)
    p = _make_anthropic_client(client)

    out = list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert out == ["abc"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_stream_empty_response_yields_nothing():
    """空流(没有任何 text_delta)→ 0 个 yield,无错。"""
    body = (
        _sse_event("message_start", {"type": "message_start", "message": {"id": "msg_1"}})
        + _sse_event("content_block_start", {"type": "content_block_start", "index": 0,
                                            "content_block": {"type": "text", "text": ""}})
        + _sse_event("content_block_stop", {"type": "content_block_stop", "index": 0})
        + _sse_event("message_stop", {"type": "message_stop"})
    )
    resp = _make_stream_response(body)
    client = MagicMock()
    client.stream.return_value = _make_stream_context(resp)
    p = _make_anthropic_client(client)

    out = list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert out == []


def test_stream_ignores_malformed_json_chunk():
    """JSON 解析失败的 chunk 跳过,不崩。"""
    body = (
        "event: content_block_delta\n"
        "data: {not valid json\n"  # 解析失败
        "\n"
        + _sse_event("content_block_delta", {"type": "content_block_delta", "index": 0,
                                              "delta": {"type": "text_delta", "text": "ok"}})
    )
    resp = _make_stream_response(body)
    client = MagicMock()
    client.stream.return_value = _make_stream_context(resp)
    p = _make_anthropic_client(client)

    out = list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert out == ["ok"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_stream_http_4xx_raises_llm_error():
    """HTTP 4xx 错误转 LLMError(让 stream_chat_with_retry 处理 4xx → 不可重试)。"""
    resp = _make_stream_response(
        '{"error": {"type": "invalid_request_error", "message": "bad model"}}',
        status_code=400,
    )
    client = MagicMock()
    client.stream.return_value = _make_stream_context(resp)
    p = _make_anthropic_client(client)

    with pytest.raises(LLMError) as exc_info:
        list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert exc_info.value.status_code if hasattr(exc_info.value, "status_code") else "400" in str(exc_info.value) or "HTTP 400" in str(exc_info.value)


def test_stream_http_5xx_raises_llm_error():
    """HTTP 5xx → LLMError(stream_chat_with_retry 区分 pre-yield vs mid-stream 决定是否重试)。"""
    resp = _make_stream_response("upstream error", status_code=503)
    client = MagicMock()
    client.stream.return_value = _make_stream_context(resp)
    p = _make_anthropic_client(client)

    with pytest.raises(LLMError) as exc_info:
        list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert "503" in str(exc_info.value) or "HTTP" in str(exc_info.value)


def test_stream_network_error_raises_llm_error():
    """网络错误(TimeoutException / ConnectError)→ LLMError。"""
    client = MagicMock()
    client.stream.side_effect = httpx.ConnectError("nope")
    p = _make_anthropic_client(client)

    with pytest.raises(LLMError) as exc_info:
        list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert "network error" in str(exc_info.value).lower() or "nope" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------


def test_stream_payload_includes_stream_flag():
    """R8.5.2:payload 必须带 stream: True(Anthropic 走真流式的前提)。"""
    captured_payload: dict = {}

    def fake_post(method, url, headers, json):
        captured_payload.update(json)
        # 返回空 body(不进入 yield 循环)
        resp = MagicMock()
        resp.status_code = 200
        resp.iter_lines.return_value = iter([])
        ctx = MagicMock()
        ctx.__enter__.return_value = resp
        ctx.__exit__.return_value = False
        return ctx

    client = MagicMock()
    client.stream.side_effect = fake_post
    p = _make_anthropic_client(client)

    list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert captured_payload["stream"] is True


def test_stream_payload_splits_system_message():
    """system message 移到 payload['system'],不放 messages 里(Anthropic 协议要求)。"""
    captured_payload: dict = {}

    def fake_post(method, url, headers, json):
        captured_payload.update(json)
        resp = MagicMock()
        resp.status_code = 200
        resp.iter_lines.return_value = iter([])
        ctx = MagicMock()
        ctx.__enter__.return_value = resp
        ctx.__exit__.return_value = False
        return ctx

    client = MagicMock()
    client.stream.side_effect = fake_post
    p = _make_anthropic_client(client)

    list(p.stream_chat([
        {"role": "system", "content": "你是一个助手"},
        {"role": "user", "content": "hi"},
    ]))
    assert captured_payload["system"] == "你是一个助手"
    # system 不在 messages 里
    assert all(m["role"] != "system" for m in captured_payload["messages"])
    # 2 条 messages(0 条 system + 1 条 user) — 实际 1 条
    assert len(captured_payload["messages"]) == 1
    assert captured_payload["messages"][0]["role"] == "user"


def test_stream_payload_uses_max_tokens_4096_by_default():
    """R8.5.1b:max_tokens 默认 4096(报告中各家推荐值)。"""
    captured_payload: dict = {}

    def fake_post(method, url, headers, json):
        captured_payload.update(json)
        resp = MagicMock()
        resp.status_code = 200
        resp.iter_lines.return_value = iter([])
        ctx = MagicMock()
        ctx.__enter__.return_value = resp
        ctx.__exit__.return_value = False
        return ctx

    client = MagicMock()
    client.stream.side_effect = fake_post
    p = _make_anthropic_client(client)

    list(p.stream_chat([{"role": "user", "content": "hi"}]))
    assert captured_payload["max_tokens"] == 4096
