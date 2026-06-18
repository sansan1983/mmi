"""mmi.core.llm.echo —— EchoLLMProvider（默认 / 测试用）。

依赖项:_types, base。
"""

from __future__ import annotations

from collections.abc import Iterator

from mmi.core.llm._types import Classification, LLMError
from mmi.core.llm.base import LLMProvider


class EchoLLMProvider(LLMProvider):
    """回声 LLM —— 不联网，不调任何外部服务。

    用途：
      1. 默认 fallback（无 OPENAI_API_KEY）
      2. 单元测试的可控 provider
      3. 让用户在没有 API key 时也能跑通"echo LLM 假聊"

    行为：
      - chat()：返回最后一条 user 消息的内容 + 前缀标记
      - classify()：总是返回 options[0]（"yes"）和 0.99 置信度
        这样不会因为 echo 误判而 trash 有意义的会话（保守策略）
    """

    name = "echo"

    _CHAT_PREFIX = "[echo] "
    _CLASSIFY_DEFAULT_CONFIDENCE = 0.99

    def chat(self, messages: list[dict], *, max_tokens: int = 4096, temperature: float = 0.7) -> str:
        # 找最后一条 user 消息
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        return f"{self._CHAT_PREFIX}{last_user}"

    def classify(self, prompt: str, *, options: list[str]) -> Classification:
        if not options:
            raise LLMError("EchoLLMProvider.classify: options must be non-empty")
        return Classification(
            choice=options[0],
            confidence=self._CLASSIFY_DEFAULT_CONFIDENCE,
            raw=f"echo:{options[0]}",
        )

    def stream_chat(self, messages: list[dict], *, max_tokens: int = 4096, temperature: float = 0.7) -> Iterator[str]:
        """Echo 流式:走默认实现即可(单 chunk 整段)。"""
        # 走基类默认实现(走 chat + 单 chunk),保持 echo 行为一致
        yield from super().stream_chat(messages)
