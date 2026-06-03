"""mmi.core.llm —— LLM 客户端抽象层。

ARCHITECTURE.md §7 / §3.5.3 / §11：本模块是基线能力，主板自带的 LLM 接口。
Phase 2 范围：
  - 定义 LLMProvider 协议（chat / classify 两个最小方法）
  - EchoLLMProvider：默认实现，无需 API key，用于测试和零配置环境
  - OpenAILLMProvider：OpenAI 兼容端点（任何 /v1/chat/completions 兼容服务）
  - get_default_provider()：从环境变量自动选择

Phase 5 范围（新增）：
  - stream_chat()：async generator，逐步 yield 文本片段
  - 默认实现抛 NotImplementedError，调用方降级到 chat() 整段
  - EchoLLMProvider / OpenAILLMProvider 各自实现

设计原则：
  - 轻量优先：不依赖重型 SDK，openai 是仅有的第三方依赖
  - 安全降级：LLM 调用失败 → 抛 LLMError，由调用方决定如何处理
  - 调用方不感知 LLM 形态（titler / classifier / manager / tui 都只看接口）
  - 流式是"能力"而非"必须"：不支持的 provider 不破坏调用方

环境变量：
  OPENAI_API_KEY      必填（用真 LLM 时）；不设置则回退到 Echo
  OPENAI_BASE_URL     可选（兼容端点，比如本地 ollama、deepseek、自建网关）
  OPENAI_MODEL        可选（默认 gpt-4o-mini）

示例：
    from mmi.core.llm import get_default_provider
    llm = get_default_provider()
    reply = llm.chat([{"role": "user", "content": "hello"}])
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

__all__ = [
    "LLMProvider",
    "LLMError",
    "Classification",
    "EchoLLMProvider",
    "OpenAILLMProvider",
    "get_default_provider",
    "reset_default_provider_for_test",
]


# ---------------------------------------------------------------------------
# 异常 / 数据类
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """LLM 调用失败（网络 / 鉴权 / 解析错误等）。调用方应安全降级。"""


@dataclass
class Classification:
    """classify() 的结构化结果。"""

    choice: str          # 选中的选项（必须在 options 内）
    confidence: float     # 0.0 - 1.0，调用方按阈值过滤
    raw: str = ""         # 原始返回（调试用）

    def is_high_confidence(self, threshold: float = 0.6) -> bool:
        return self.confidence >= threshold


# ---------------------------------------------------------------------------
# 协议
# ---------------------------------------------------------------------------


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
        max_tokens: int = 512,
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

    # ---- 流式（Phase 5 新增） --------------------------------------------

    async def stream_chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """流式对话：逐步 yield 文本片段。

        设计要点（ARCHITECTURE.md §3.5.3）：
          - 不是 abstractmethod：默认实现抛 NotImplementedError，老 provider
            子类（测试用 Mock）不会被强制实现
          - 调用方（manager / tui）应 try/except NotImplementedError 降级到 chat() 整段
          - 走 async generator 而非 callback：跟 textual worker / asyncio.to_thread 配合更好

        Args:
            messages: OpenAI 格式
            max_tokens: 同 chat
            temperature: 同 chat

        Yields:
            文本片段（不保证按 token 边界，调用方应原样拼接）

        Raises:
            NotImplementedError: provider 不支持流式（调用方应降级到 chat()）
            LLMError: 底层错误
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support stream_chat; "
            "fallback to chat() is recommended"
        )
        # 让类型检查器满意（async generator 必须有 yield）
        yield ""  # pragma: no cover


# ---------------------------------------------------------------------------
# Echo：默认 / 测试用
# ---------------------------------------------------------------------------


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

    def chat(self, messages, *, max_tokens=512, temperature=0.7) -> str:
        # 找最后一条 user 消息
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        return f"{self._CHAT_PREFIX}{last_user}"

    def classify(self, prompt, *, options):
        if not options:
            raise LLMError("EchoLLMProvider.classify: options must be non-empty")
        return Classification(
            choice=options[0],
            confidence=self._CLASSIFY_DEFAULT_CONFIDENCE,
            raw=f"echo:{options[0]}",
        )

    async def stream_chat(self, messages, *, max_tokens=512, temperature=0.7):
        """Echo 流式：一次 yield 完整 echo 回复。

        Phase 5：测试和默认 fallback 都需要"能流"的 provider。
        一次 yield 整段，便于 TUI 端用同一条 stream_chat 路径走完。
        """
        full = self.chat(messages, max_tokens=max_tokens, temperature=temperature)
        yield full


# ---------------------------------------------------------------------------
# OpenAI 兼容
# ---------------------------------------------------------------------------


class OpenAILLMProvider(LLMProvider):
    """OpenAI 兼容 LLM 客户端。

    支持任何 /v1/chat/completions 兼容端点：
      - OpenAI 官方
      - Azure OpenAI（通过 base_url 改）
      - 本地 ollama（http://localhost:11434/v1）
      - DeepSeek、Anthropic 兼容网关等
    """

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gpt-4o-mini",
    ):
        # 延迟 import —— echo 模式下不强制要求 openai
        try:
            from openai import OpenAI
        except ImportError as e:
            raise LLMError(
                "openai package not installed; pip install 'openai>=1.0'"
            ) from e

        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMError("OPENAI_API_KEY not set")

        kwargs: dict = {"api_key": api_key}
        if base_url or os.environ.get("OPENAI_BASE_URL"):
            kwargs["base_url"] = base_url or os.environ.get("OPENAI_BASE_URL")
        self.model = model
        self.client = OpenAI(**kwargs)

    def chat(self, messages, *, max_tokens=512, temperature=0.7) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as e:
            raise LLMError(f"OpenAI chat failed: {e}") from e

        if not resp.choices:
            raise LLMError("OpenAI chat: empty choices")
        content = resp.choices[0].message.content
        if content is None:
            raise LLMError("OpenAI chat: empty content")
        return content

    async def stream_chat(self, messages, *, max_tokens=512, temperature=0.7):
        """OpenAI 同步流式生成器包成 async generator。

        OpenAI SDK 的 stream=True 返回同步 `Stream[ChatCompletionChunk]`
        （blocks 当前线程）。我们在另一线程同步迭代，异步 yield 增量文本。

        实现技巧（避免 run_in_executor 死锁）：
          - OpenAI stream 在专属后台线程里同步迭代
          - 用 queue.Queue 在两线程间传 chunk
          - async generator 从 queue 异步取
        """
        import asyncio
        import queue
        import threading

        q: queue.Queue = queue.Queue()
        done = threading.Event()
        error: list = []

        def _produce():
            try:
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None) if delta else None
                    if content:
                        q.put(content)
            except Exception as e:
                error.append(LLMError(f"OpenAI stream failed: {e}"))
            finally:
                done.set()

        t = threading.Thread(target=_produce, daemon=True)
        t.start()

        while True:
            # 给 producer 一点时间，避免 busy loop
            await asyncio.sleep(0)
            try:
                yield q.get_nowait()
            except queue.Empty:
                if done.is_set():
                    # 排空剩余（如果最后那一刻 put 后才 set）
                    try:
                        yield q.get_nowait()
                    except queue.Empty:
                        pass
                    if error:
                        raise error[0]
                    return
                # 未完成，让出事件循环
                await asyncio.sleep(0.01)

    def classify(self, prompt, *, options) -> Classification:
        if not options:
            raise LLMError("classify: options must be non-empty")

        opts_str = " | ".join(options)
        system = (
            f"你是一个严格的分类器。从以下选项中选一个：{opts_str}。\n"
            f'只返回 JSON：{{"choice": "<exactly one of: {opts_str}>", "confidence": <float 0.0-1.0>}}'
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=64,
                temperature=0.0,
            )
        except Exception as e:
            raise LLMError(f"OpenAI classify failed: {e}") from e

        if not resp.choices:
            raise LLMError("OpenAI classify: empty choices")
        text = resp.choices[0].message.content or "{}"

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"OpenAI classify: bad JSON {text!r}: {e}") from e

        choice = data.get("choice")
        confidence = data.get("confidence", 0.5)
        if choice not in options:
            # 兜底：LLM 返回了 options 外的值，取第一个
            choice = options[0]
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.5
        # 强制范围
        confidence = max(0.0, min(1.0, confidence))

        return Classification(choice=choice, confidence=confidence, raw=text)


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------


_DEFAULT_LLM: LLMProvider | None = None


def get_default_provider() -> LLMProvider:
    """从环境变量推断应该用哪个 provider。

    规则：
      1. OPENAI_API_KEY 已设置 → OpenAILLMProvider
      2. 否则 → EchoLLMProvider

    返回的实例会缓存（单例），节省重复构造。
    测试时用 reset_default_provider_for_test() 重置。
    """
    global _DEFAULT_LLM
    if _DEFAULT_LLM is not None:
        return _DEFAULT_LLM

    if os.environ.get("OPENAI_API_KEY"):
        try:
            _DEFAULT_LLM = OpenAILLMProvider(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_BASE_URL"),
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            )
        except LLMError:
            # OpenAI 配置有问题（比如 base_url 格式错），兜底 echo
            _DEFAULT_LLM = EchoLLMProvider()
    else:
        _DEFAULT_LLM = EchoLLMProvider()

    return _DEFAULT_LLM


def reset_default_provider_for_test() -> None:
    """测试用：清空缓存的 provider。"""
    global _DEFAULT_LLM
    _DEFAULT_LLM = None