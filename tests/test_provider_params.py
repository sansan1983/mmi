"""R8.5.1b Provider 参数透传测试。

按 docs/dev/预置Provider官方参数差异报告.md 调整后,验证:
  - providers.py: MiniMax api_key_env 大小写(全大写)
  - OpenAILLMProvider.chat() 新增 top_p / stop / response_format(可选,None 不发)
  - OpenAILLMProvider.stream_chat() 加 stream_options
  - AnthropicLLMProvider.chat() 新增 top_p / stop_sequences(可选,None 不发)
  - max_tokens 默认值 512 → 4096(全 llm.py)

测试用 mock 抓 payload,不真发请求。
"""
from __future__ import annotations

from unittest.mock import MagicMock

from mmi.core.llm import AnthropicLLMProvider, OpenAILLMProvider
from mmi.core.providers import get_provider


# ---------------------------------------------------------------------------
# providers.py: MiniMax api_key_env 全大写
# ---------------------------------------------------------------------------


def test_minimax_api_key_env_is_uppercase():
    """R8.5.1b:MiniMax env var 改全大写(报告 7.1)。"""
    info = get_provider("minimax")
    assert info.api_key_env == "MINIMAX_API_KEY"


# ---------------------------------------------------------------------------
# OpenAILLMProvider.chat() 新增参数
# ---------------------------------------------------------------------------


def _make_openai_provider():
    """构造 OpenAILLMProvider,client 替换为 mock。"""
    p = OpenAILLMProvider(api_key="sk-test", base_url="http://x", model="m")
    p.client = MagicMock()
    return p


def test_openai_chat_default_does_not_send_optional_params():
    """默认(top_p/stop/response_format 都不传)→ payload 里**不**应出现这些 key。"""
    p = _make_openai_provider()
    p.chat([{"role": "user", "content": "hi"}])
    kwargs = p.client.chat.completions.create.call_args.kwargs
    assert "top_p" not in kwargs
    assert "stop" not in kwargs
    assert "response_format" not in kwargs
    # max_tokens 仍是 4096 默认
    assert kwargs["max_tokens"] == 4096


def test_openai_chat_sends_top_p_when_provided():
    p = _make_openai_provider()
    p.chat([{"role": "user", "content": "hi"}], top_p=0.9)
    kwargs = p.client.chat.completions.create.call_args.kwargs
    assert kwargs["top_p"] == 0.9


def test_openai_chat_sends_stop_when_provided():
    p = _make_openai_provider()
    p.chat([{"role": "user", "content": "hi"}], stop=["</s>", "###"])
    kwargs = p.client.chat.completions.create.call_args.kwargs
    assert kwargs["stop"] == ["</s>", "###"]


def test_openai_chat_sends_response_format_when_provided():
    p = _make_openai_provider()
    p.chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )
    kwargs = p.client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}


def test_openai_chat_accepts_all_three_together():
    p = _make_openai_provider()
    p.chat(
        [{"role": "user", "content": "hi"}],
        top_p=0.95,
        stop="END",
        response_format={"type": "json_object"},
    )
    kwargs = p.client.chat.completions.create.call_args.kwargs
    assert kwargs["top_p"] == 0.95
    assert kwargs["stop"] == "END"
    assert kwargs["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# OpenAILLMProvider.stream_chat() 加 stream_options
# ---------------------------------------------------------------------------


def _make_stream_chunks(texts: list[str]):
    """构造假 stream:每个 chunk 含 delta.content。"""
    chunks = []
    for t in texts:
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = t
        chunks.append(chunk)
    return chunks


def test_openai_stream_chat_sends_stream_options():
    p = _make_openai_provider()
    p.client.chat.completions.create.return_value = _make_stream_chunks(["a", "b"])
    list(p.stream_chat([{"role": "user", "content": "hi"}]))
    kwargs = p.client.chat.completions.create.call_args.kwargs
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}
    # max_tokens 默认 4096
    assert kwargs["max_tokens"] == 4096


# ---------------------------------------------------------------------------
# AnthropicLLMProvider.chat() 新增参数
# ---------------------------------------------------------------------------


def _make_anthropic_provider(monkeypatch_response):
    """构造 AnthropicLLMProvider,_post 替换为 mock。"""
    p = AnthropicLLMProvider(api_key="sk-test", base_url="http://x", model="m")
    p._post = MagicMock(return_value={
        "content": [{"type": "text", "text": "hi"}],
    })
    return p


def test_anthropic_chat_default_does_not_send_optional_params():
    """默认(top_p/stop_sequences 不传)→ payload 不出现这些 key。"""
    p = _make_anthropic_provider(None)
    p.chat([{"role": "user", "content": "hi"}])
    payload = p._post.call_args.args[0]
    assert "top_p" not in payload
    assert "stop_sequences" not in payload
    assert payload["max_tokens"] == 4096
    assert "system" not in payload  # 没有 system message


def test_anthropic_chat_sends_top_p_when_provided():
    p = _make_anthropic_provider(None)
    p.chat([{"role": "user", "content": "hi"}], top_p=0.95)
    payload = p._post.call_args.args[0]
    assert payload["top_p"] == 0.95


def test_anthropic_chat_sends_stop_sequences_not_stop():
    """Anthropic 协议:停止词 key 是 stop_sequences(不是 OpenAI 的 stop)。"""
    p = _make_anthropic_provider(None)
    p.chat([{"role": "user", "content": "hi"}], stop_sequences=["</s>", "###"])
    payload = p._post.call_args.args[0]
    assert payload["stop_sequences"] == ["</s>", "###"]
    # 确认没"stop"字段(OpenAI 风格名,Anthropic 不用)
    assert "stop" not in payload


def test_anthropic_chat_accepts_all_three_together():
    p = _make_anthropic_provider(None)
    p.chat(
        [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "hi"},
        ],
        top_p=0.95,
        stop_sequences=["</s>"],
    )
    payload = p._post.call_args.args[0]
    assert payload["top_p"] == 0.95
    assert payload["stop_sequences"] == ["</s>"]
    assert payload["system"] == "你是一个助手"


# ---------------------------------------------------------------------------
# max_tokens 默认值(全 llm.py)
# ---------------------------------------------------------------------------


def test_openai_chat_default_max_tokens_is_4096():
    """R8.5.1b:max_tokens 默认 512 → 4096(各家官方推荐)。"""
    p = _make_openai_provider()
    p.chat([{"role": "user", "content": "hi"}])
    assert p.client.chat.completions.create.call_args.kwargs["max_tokens"] == 4096


def test_anthropic_chat_default_max_tokens_is_4096():
    p = _make_anthropic_provider(None)
    p.chat([{"role": "user", "content": "hi"}])
    assert p._post.call_args.args[0]["max_tokens"] == 4096


def test_explicit_max_tokens_still_wins():
    """显式传 max_tokens 仍能覆盖默认值。"""
    p = _make_openai_provider()
    p.chat([{"role": "user", "content": "hi"}], max_tokens=123)
    assert p.client.chat.completions.create.call_args.kwargs["max_tokens"] == 123
