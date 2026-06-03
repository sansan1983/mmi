"""tests/test_titler.py —— core.titler 单元测试。

覆盖：
  - heuristic_title：英文/中文分词 + 停用词 + 长度截断
  - generate_title：LLM 成功 / LLM 失败回退 / 不接受"复制首句"
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core.llm import LLMError, LLMProvider  # noqa: E402
from mmi.core.titler import (  # noqa: E402
    generate_title,
    heuristic_title,
)


# ---------------------------------------------------------------------------
# Test double：可控的 LLM
# ---------------------------------------------------------------------------


class _StubLLM(LLMProvider):
    """可预设 chat 返回值；调用次数也记下来。"""

    def __init__(self, reply: str = "weather in tokyo"):
        self.name = "stub"
        self._reply = reply
        self.calls: int = 0
        self.fail_with: Exception | None = None

    def chat(self, messages, **kw):
        self.calls += 1
        if self.fail_with:
            raise self.fail_with
        return self._reply

    def classify(self, prompt, *, options):
        raise LLMError("not used in titler tests")


# ---------------------------------------------------------------------------
# heuristic_title
# ---------------------------------------------------------------------------


def test_heuristic_empty_turns_returns_untitled():
    assert heuristic_title([]) == "untitled"


def test_heuristic_zh_picks_content_chars():
    turns = [
        {"role": "user", "content": "我在写一个 Python 爬虫"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "用 requests 库"},
    ]
    title = heuristic_title(turns, language="zh-CN")
    # 应该非空非 untitled
    assert title != "untitled"
    assert len(title) > 0
    # heuristic 不会因为 2-gram 含停用字字符就过滤（"我在" 是合法 token），
    # 只要 title 不"全是孤立停用字"就行。简单判断：长度 < 4 的中文标题不行。
    assert len(title) >= 2


def test_heuristic_en_picks_content_words():
    turns = [
        {"role": "user", "content": "How do I design a postgres sharding strategy?"},
        {"role": "assistant", "content": "Use hash sharding."},
        {"role": "user", "content": "What about connection pooling?"},
    ]
    title = heuristic_title(turns, language="en-US")
    # 英文应该是若干有意义的词拼起来
    assert title != "untitled"
    # 不应全是停用词
    for word in title.split():
        assert word not in {"the", "a", "is", "to"}


def test_heuristic_only_stopwords_falls_back_to_raw():
    # 全是停用词：极端情况
    turns = [
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "hi there"},
    ]
    title = heuristic_title(turns, language="en-US")
    # fallback 到原文前 N 词
    assert title != "untitled"
    assert "hello" in title or "hi" in title


def test_heuristic_respects_max_words():
    # 很多 user 消息，但标题不能超过 TITLE_MAX_WORDS
    turns = [{"role": "user", "content": f"topic{i} word{i}"} for i in range(20)]
    title = heuristic_title(turns, language="en-US")
    assert len(title.split()) <= 12


# ---------------------------------------------------------------------------
# generate_title
# ---------------------------------------------------------------------------


def test_generate_title_uses_llm_reply():
    llm = _StubLLM(reply="postgres sharding design")
    turns = [
        {"role": "user", "content": "I want to shard my postgres database"},
        {"role": "assistant", "content": "Use hash sharding"},
    ]
    title = generate_title(turns, llm, language="en-US")
    assert title == "postgres sharding design"
    assert llm.calls == 1


def test_generate_title_rejects_copy_of_first_user_message():
    # LLM 不应该直接复制第一句 user（§8.2）
    llm = _StubLLM(reply="hello there how are you")
    turns = [{"role": "user", "content": "hello there how are you"}]
    # generate_title 会因为不通过 _is_acceptable 而重试
    # 但 stub 永远返回同一个值，所以会触发 fallback heuristic
    # heuristic 也会产出 "hello there how are you"（全是停用词时回退到原文），
    # 最后兜底返回 "untitled"（确保绝不 = 首句）
    title = generate_title(turns, llm, language="en-US")
    assert title.lower() != "hello there how are you"
    assert title == "untitled"


def test_generate_title_strips_quotes_and_prefix():
    llm = _StubLLM(reply='"Title: postgres sharding"')
    turns = [
        {"role": "user", "content": "shard my db"},
        {"role": "assistant", "content": "ok"},
    ]
    title = generate_title(turns, llm, language="en-US")
    assert '"' not in title
    assert not title.lower().startswith("title:")


def test_generate_title_falls_back_to_heuristic_on_llm_error():
    llm = _StubLLM()
    llm.fail_with = LLMError("network down")
    turns = [
        {"role": "user", "content": "designing a redis cache layer"},
        {"role": "user", "content": "for high throughput"},
    ]
    title = generate_title(turns, llm, language="en-US")
    # 重试 3 次后 fallback 到 heuristic
    assert title != "untitled"
    assert llm.calls == 3


def test_generate_title_no_user_turns_returns_heuristic_untitled():
    llm = _StubLLM(reply="anything")
    turns = [{"role": "assistant", "content": "only assistant"}]
    title = generate_title(turns, llm, language="en-US")
    # 没有 user 直接走 heuristic，最终是 untitled
    assert title == "untitled"
    assert llm.calls == 0
