"""R8 测试基建:共享的 LLMProvider 假实现。

目的:消除各测试文件里重复的 _StubLLM / _FakeLLM / ScriptedLLM 定义。
约定:测试代码 import 应 `from tests._fakes import X`(本目录内),或通过
conftest 暴露的 fixture 注入。

提供的假实现:
  - ScriptedLLM — 可预设 chat replies / stream chunks / 关闭 stream 支持
  - KeywordStubLLM — 按 user message 关键词返不同内容(给 phase 3 agent 测试用)
  - MinimalStubLLM — 永远返固定字符串,记录 call 历史(给纯协议测试用)
"""
from __future__ import annotations

from typing import Any

from mmi.core.llm import Classification, LLMProvider


class ScriptedLLM(LLMProvider):
    """可预设回复的 LLM,同时实现 chat() 和 stream_chat()。

    适用场景:需要精确控制 LLM 返值(让 Validator / Pipeline 走特定路径)。
    从 conftest 提到此处(R8 跨期遗留 #8):让非 conftest 测试文件也能直接 import。
    """

    name = "scripted"

    def __init__(
        self,
        replies: list[str] | None = None,
        stream_chunks: list[list[str]] | None = None,
        support_stream: bool = True,
    ) -> None:
        self._replies = replies or ["stub reply"]
        self._call_count = 0
        self._stream_chunks = stream_chunks
        self._support_stream = support_stream
        self.last_messages: list[dict] = []

    def chat(self, messages, *, max_tokens: int = 512, temperature: float = 0.7) -> str:
        self.last_messages = list(messages)
        idx = min(self._call_count, len(self._replies) - 1)
        reply = self._replies[idx]
        self._call_count += 1
        return reply

    def classify(self, prompt: str, *, options: list[str]) -> Classification:
        return Classification(choice=options[0], confidence=0.99)

    def stream_chat(self, messages, *, max_tokens: int = 512, temperature: float = 0.7):
        if not self._support_stream:
            raise NotImplementedError("scripted LLM without stream support")
        self.last_messages = list(messages)
        if self._stream_chunks is not None:
            idx = min(self._call_count, len(self._stream_chunks) - 1)
            chunks = self._stream_chunks[idx]
        else:
            idx = min(self._call_count, len(self._replies) - 1)
            chunks = [self._replies[idx]]
        self._call_count += 1
        for c in chunks:
            yield c


class KeywordStubLLM(LLMProvider):
    """按 user message 关键词返不同内容。

    适用场景:agent / orchestrator 端到端测试,需要触发特定 Validator rule。
    内置 3 个关键词:
      - "密码" / "password"  → 触发 no_dangerous_tokens rule
      - "审计" / "audit"     → 返 audit 风格的 markdown
      - 其它                 → 返一段正常输出
    """

    name = "keyword-stub"

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kw: Any) -> str:
        self.calls.append(list(messages))
        user = messages[-1]["content"] if messages else ""
        if "密码" in user or "password" in user:
            return 'password = "secret123"'
        if "审计" in user or "audit" in user:
            return "## Audit\n发现:输入校验不足"
        return "这是一段正常输出,用于测试"

    def classify(self, prompt: str, *, options: list[str]) -> Classification:
        return Classification(choice=options[0], confidence=0.99)


class MinimalStubLLM(LLMProvider):
    """永远返固定字符串,记录所有 chat 调用。

    适用场景:只需要 LLM 不抛错 + 返值可控的协议测试(orchestrator / pipeline / steps)。
    """

    name = "minimal-stub"

    def __init__(self, reply: str = "stub-reply") -> None:
        self._reply = reply
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kw: Any) -> str:
        self.calls.append(list(messages))
        return self._reply

    def classify(self, prompt: str, *, options: list[str]) -> Classification:
        return Classification(choice=options[0], confidence=0.99)
