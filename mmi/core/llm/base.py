"""mmi.core.llm.base —— LLMProvider 协议 + 默认实现 + 重试。

依赖项:_types。
被依赖:3 个 provider 模块, factory.py。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import TYPE_CHECKING

from mmi.core.llm._types import Classification

if TYPE_CHECKING:
    from mmi.agent.result import ChatResult


class LLMProvider(ABC):
    """LLM 客户端的最小接口。

    设计原则（见 ARCHITECTURE.md §3.5.3）：
      - 主板只暴露接口契约，不暴露具体实现
      - 模块可替换：titler / classifier 只依赖本类，不依赖具体子类
    """

    name: str = "abstract"

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """发一轮对话，返回 LLM 文本回复。

        Args:
            messages: OpenAI 格式 [{"role": ..., "content": ...}, ...]
            max_tokens: 上限
            temperature: 0.0 = 确定性，1.0 = 发散

        Returns:
            LLM 文本回复（不含 system/role 标签）

        Raises:
            LLMError: 任何底层错误（网络、鉴权、解析、空回复）
        """

    @abstractmethod
    def classify(self, prompt: str, *, options: list[str]) -> Classification:
        """二选一 / 多选一分类（用 LLM 判定）。

        Args:
            prompt: 给 LLM 的完整 prompt
            options: 候选选项列表，LLM 必须从中选一个

        Returns:
            Classification(choice, confidence)

        Raises:
            LLMError: 底层错误
        """

    # ---- 流式（4.4 新增） --------------------------------------------

    def stream_chat(self, messages: list[dict]) -> Iterator[str]:
        """默认实现:走 chat,拆成单 chunk。子类可 override 走真流式。

        设计要点(spec 4.4):
          - 同步迭代器起步(不抽 async def):本仓 SDK 同步(httpx + OpenAI 兼容),
            强行 async 收益小、改动面大
          - 不是 abstractmethod:子类可不实现,默认实现直接走 chat() 整段
          - 真流式 Provider(OpenAI)可 override 走 stream=True

        Args:
            messages: OpenAI 格式 [{"role": ..., "content": ...}, ...]

        Yields:
            文本片段(单 chunk,默认实现就是整段)

        Raises:
            StreamError: chat() 失败时包成 StreamError
        """
        from mmi.core.exceptions import StreamError
        try:
            text = self.chat(messages)
        except Exception as e:
            raise StreamError(str(e)) from e
        yield text

    # ---- 4.3 重试 ---------------------------------------------------------

    def chat_with_retry(
        self,
        messages: list[dict],
        *,
        max_attempts: int = 3,
        base_delay: float = 0.5,
    ) -> ChatResult:
        """指数退避重试 chat()。

        可重试异常:
          - httpx.TimeoutException / httpx.ConnectError / ConnectionError (网络)
          - httpx.HTTPStatusError 5xx / 429 (服务端临时错误)

        不可重试(直接 raise):
          - httpx.HTTPStatusError 4xx(除 429 外的客户端错误)
          - 其它 LLMError

        Args:
            messages: 同 chat()
            max_attempts: 最大尝试次数,默认 3
            base_delay: 退避基数,attempt=N 的退避是 base_delay * 2^(N-1)

        Returns:
            ChatResult(reply=..., attempts=N),N 是成功的那次

        Raises:
            LLMRetryExhausted: 重试 N 次后仍失败
            httpx.HTTPStatusError: 4xx 直接抛
        """
        import httpx

        from mmi.agent.result import ChatResult
        from mmi.core.exceptions import LLMRetryExhausted

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                text = self.chat(messages)
                return ChatResult(
                    reply=text,
                    intent=None,  # 顶层 chat 不分类 intent
                    agent_id="",
                    validation=None,
                    trace_ids=[],
                    attempts=attempt,
                )
            except (httpx.TimeoutException, httpx.ConnectError, ConnectionError) as e:
                last_error = e
                if attempt < max_attempts:
                    time.sleep(base_delay * (2 ** (attempt - 1)))
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status >= 500 or status == 429:
                    last_error = e
                    if attempt < max_attempts:
                        time.sleep(base_delay * (2 ** (attempt - 1)))
                else:
                    raise
        raise LLMRetryExhausted(attempts=max_attempts, last_error=last_error)

    # ---- 4.8 流式重试 ----------------------------------------------------

    def stream_chat_with_retry(
        self,
        messages: list[dict],
        *,
        max_attempts: int = 3,
        base_delay: float = 0.5,
    ) -> Iterator[str]:
        """流式重试,语义跟 chat_with_retry 对齐。

        关键设计(stream 的本质约束):
          - stream_chat 是生成器,每调一次产生新的 stream 实例
          - 预生成阶段(yield 之前的错误)→ 可重试,且对调用者不可见
            (caller 还没拿到第一个 chunk,新 stream 整段重发)
          - 中流错误(已 yield 了部分 chunk 之后)→ 不可重试
            (caller 已消费了 N 个 chunk,重试会重复,让 UI 看到两段一样的文本)

        实现:用内层生成器 + 状态机。
          - 第一次失败:如果是 pre-yield(没消费过任何 chunk),重试
          - 如果已经 yield 过,直接抛(让 StreamError 透传)

        可重试异常(仅 pre-yield 阶段):同 chat_with_retry
          - httpx.TimeoutException / httpx.ConnectError / ConnectionError
          - httpx.HTTPStatusError 5xx / 429
        不可重试:4xx / 其它 LLMError / 中流 StreamError

        Args:
            messages: 同 stream_chat()
            max_attempts: 最大尝试次数,默认 3
            base_delay: 退避基数,attempt=N 的退避是 base_delay * 2^(N-1)

        Yields:
            文本片段(从成功的某次 stream_chat 转发)

        Raises:
            LLMRetryExhausted: pre-yield 阶段重试 N 次后仍失败
            StreamError: 中流错误(已 yield 过部分内容,重试不安全的)
            httpx.HTTPStatusError: 4xx 直接抛
        """
        import httpx

        from mmi.core.exceptions import LLMRetryExhausted

        # 状态:caller 是否已消费过 chunk
        consumed_count = 0
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                gen = self.stream_chat(messages)
                for chunk in gen:
                    consumed_count += 1
                    yield chunk
                return  # 整段流式成功
            except (httpx.TimeoutException, httpx.ConnectError, ConnectionError) as e:
                last_error = e
                if consumed_count > 0:
                    # 中流错误:不可安全重试(已 yield 的 chunk 不可收回)
                    from mmi.core.exceptions import StreamError
                    raise StreamError(f"mid-stream error after {consumed_count} chunks: {e}") from e
                if attempt < max_attempts:
                    time.sleep(base_delay * (2 ** (attempt - 1)))
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status >= 500 or status == 429:
                    last_error = e
                    if consumed_count > 0:
                        from mmi.core.exceptions import StreamError
                        raise StreamError(f"mid-stream error after {consumed_count} chunks: {e}") from e
                    if attempt < max_attempts:
                        time.sleep(base_delay * (2 ** (attempt - 1)))
                else:
                    # 4xx:不可重试
                    if consumed_count > 0:
                        from mmi.core.exceptions import StreamError
                        raise StreamError(f"mid-stream 4xx after {consumed_count} chunks: {e}") from e
                    raise
            except Exception as e:
                # 其它异常(LLMError 等)— 不可重试
                if consumed_count > 0:
                    from mmi.core.exceptions import StreamError
                    raise StreamError(f"mid-stream error after {consumed_count} chunks: {e}") from e
                raise
        # pre-yield 阶段耗尽
        raise LLMRetryExhausted(attempts=max_attempts, last_error=last_error)
