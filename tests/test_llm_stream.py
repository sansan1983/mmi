"""LLM.stream_chat 行为测试。"""
from __future__ import annotations

import pytest

from mmi.core.exceptions import StreamError
from mmi.core.llm import LLMProvider


class _FakeStreamLLM(LLMProvider):
    """模拟 Provider,直接给 chunk 列表。"""

    def __init__(self, chunks: list):
        self._chunks = list(chunks)
        self.call_count = 0

    def chat(self, messages):
        # stream 测试不调 chat;抛错只是保险
        raise RuntimeError("should not be called")

    def classify(self, text: str) -> str:
        return "qa"

    def stream_chat(self, messages):
        self.call_count += 1
        for c in self._chunks:
            if isinstance(c, Exception):
                raise StreamError(str(c))
            yield c


def test_stream_iterates_chunks():
    llm = _FakeStreamLLM(["He", "llo", " world"])
    out = list(llm.stream_chat([]))
    assert "".join(out) == "Hello world"


def test_stream_raises_on_mid_chunk_error():
    llm = _FakeStreamLLM(["a", "b", RuntimeError("net"), "c"])
    with pytest.raises(StreamError):
        list(llm.stream_chat([]))


def test_stream_empty():
    llm = _FakeStreamLLM([])
    assert list(llm.stream_chat([])) == []


def test_default_stream_chat_uses_chat():
    """基类默认 stream_chat:走 chat,拆成单 chunk 返。"""

    class _OneShot(LLMProvider):
        def __init__(self, text):
            self._text = text

        def chat(self, messages):
            return self._text

        def classify(self, text: str) -> str:
            return "qa"

    llm = _OneShot("hello")
    out = list(llm.stream_chat([]))
    assert out == ["hello"]
