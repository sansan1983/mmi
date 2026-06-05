"""mmi.core.llm —— LLM 客户端抽象层。

ARCHITECTURE.md §7 / §3.5.3 / §11：本模块是基线能力，主板自带的 LLM 接口。
Phase 2 范围：
  - 定义 LLMProvider 协议（chat / classify 两个最小方法）
  - EchoLLMProvider：默认实现，无需 API key，用于测试和零配置环境
  - OpenAILLMProvider：OpenAI 兼容端点（任何 /v1/chat/completions 兼容服务）
  - get_default_provider()：从环境变量自动选择

Phase 5 范围（新增）：
  - stream_chat()：同步生成器，逐步 yield 文本片段
  - 默认实现走 chat() 拆成单 chunk（兜底）
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
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mmi.agent.result import ChatResult

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

    # ---- 流式（4.4 新增） --------------------------------------------

    def stream_chat(self, messages: list[dict]):
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
    ) -> "ChatResult":
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


# ---------------------------------------------------------------------------
# 向后兼容别名(R7 plan 文档里把类叫 LLM,实际实现是 LLMProvider)
# ---------------------------------------------------------------------------

LLM = LLMProvider


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

    def stream_chat(self, messages, *, max_tokens=512, temperature=0.7):
        """Echo 流式:走默认实现即可(单 chunk 整段)。"""
        # 走基类默认实现(走 chat + 单 chunk),保持 echo 行为一致
        yield from super().stream_chat(messages)


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

    def stream_chat(self, messages, *, max_tokens=512, temperature=0.7):
        """OpenAI 真流式:同步迭代 stream=True 返回的 chunk。

        OpenAI SDK 的 stream=True 返回同步 `Stream[ChatCompletionChunk]`,
        直接同步迭代 yield 增量文本即可(调用方负责放到后台线程)。

        设计要点(spec 4.4):
          - 同步迭代器:不阻塞 — OpenAI SDK 的 stream 内部异步发请求
          - LLMError 包成 StreamError:与默认实现行为一致
        """
        from mmi.core.exceptions import StreamError
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
                    yield content
        except Exception as e:
            raise StreamError(f"OpenAI stream failed: {e}") from e

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
# Anthropic Provider(独立实现,Anthropic 用自己的消息格式)
# ---------------------------------------------------------------------------


class AnthropicLLMProvider(LLMProvider):
    """Anthropic Claude 客户端(直连 https://api.anthropic.com)。

    用 httpx 调 /v1/messages,带 x-api-key + anthropic-version 头。
    不依赖 anthropic SDK(避免多一个包)。
    """

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "claude-3-5-sonnet-20241022",
        anthropic_version: str = "2023-06-01",
    ):
        import httpx  # 局部导入,避免强制依赖

        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError("anthropic api_key not set")

        self.api_key = api_key
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        self.model = model
        self.anthropic_version = anthropic_version
        self._client = httpx.Client(timeout=60.0)

    def _post(self, payload: dict) -> dict:
        """POST /v1/messages,raise LLMError on error。"""
        import httpx
        try:
            resp = self._client.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.anthropic_version,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as e:
            raise LLMError(f"Anthropic HTTP error: {e}") from e
        if resp.status_code >= 400:
            raise LLMError(
                f"Anthropic HTTP {resp.status_code}: {(resp.text or '')[:200]}"
            )
        try:
            return resp.json()
        except Exception as e:
            raise LLMError(f"Anthropic: bad JSON: {e}") from e

    def chat(self, messages, *, max_tokens=512, temperature=0.7) -> str:
        # Anthropic 要求 system 和 user 分离
        system_parts: list[str] = []
        user_msgs: list[dict] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content") or ""
            if role == "system":
                system_parts.append(content)
            else:
                user_msgs.append({"role": role, "content": content})
        payload: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_msgs,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        data = self._post(payload)
        # 响应格式: {content: [{type: "text", text: "..."}], ...}
        blocks = data.get("content") or []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "text":
                text = b.get("text", "")
                if text:
                    return text
        raise LLMError("Anthropic chat: no text in response")

    def stream_chat(self, messages, *, max_tokens=512, temperature=0.7):
        """Anthropic 简化流式:不做 SSE 解析,直接 yield 整段。"""
        yield self.chat(messages, max_tokens=max_tokens, temperature=temperature)

    def classify(self, prompt, *, options) -> Classification:
        if not options:
            raise LLMError("classify: options must be non-empty")
        opts_str = " | ".join(options)
        system = (
            f"你是一个严格的分类器。从以下选项中选一个：{opts_str}。\n"
            f'只返回 JSON：{{"choice": "<exactly one of: {opts_str}>", "confidence": <float 0.0-1.0>}}'
        )
        try:
            resp_text = self.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=128,
                temperature=0.0,
            )
        except LLMError as e:
            raise LLMError(f"Anthropic classify failed: {e}") from e
        try:
            data = json.loads(resp_text)
        except json.JSONDecodeError:
            # 兜底:从文本里抠 choice
            data = {}
        choice = data.get("choice") if isinstance(data, dict) else None
        confidence = data.get("confidence", 0.5) if isinstance(data, dict) else 0.5
        if not choice or choice not in options:
            choice = options[0]
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        return Classification(choice=choice, confidence=confidence, raw=resp_text)


def _build_provider_from_config() -> LLMProvider:
    """按 ~/.mmi/config.toml [llm] 构造 provider(供 get_default_provider 优先用)。"""
    from . import config as cfg_mod
    from . import providers as prov_mod
    llm = cfg_mod.get_llm_config()
    provider_id = llm.get("provider", "").strip().lower()
    api_key = cfg_mod.resolve_api_key(provider_id)
    base_url = llm.get("base_url", "").strip() or None
    model = llm.get("model", "").strip() or "gpt-4o-mini"
    # api_style 优先级:config 显式 > provider 首选
    api_style = llm.get("api_style", "").strip()
    if not api_style:
        try:
            info = prov_mod.get_provider(provider_id)
            api_style = info.preferred_api_style
        except (ValueError, KeyError):
            api_style = "openai"
    if not provider_id or not api_key:
        return None  # 没配完整,回退到 env
    try:
        if api_style == "anthropic":
            return AnthropicLLMProvider(api_key=api_key, base_url=base_url, model=model)
        # OpenAI 兼容(默认)
        return OpenAILLMProvider(api_key=api_key, base_url=base_url, model=model)
    except LLMError:
        return None


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------


_DEFAULT_LLM: LLMProvider | None = None


def get_default_provider() -> LLMProvider:
    """从 config / env 推断应该用哪个 provider。

    优先级:
      1. ~/.mmi/config.toml [llm] 完整配置(provider + api_key + model)
      2. 环境变量 OPENAI_API_KEY → OpenAILLMProvider
      3. 环境变量 ANTHROPIC_API_KEY → AnthropicLLMProvider
      4. 兜底 → EchoLLMProvider

    返回的实例会缓存(单例),节省重复构造。
    测试时用 reset_default_provider_for_test() 重置。
    """
    global _DEFAULT_LLM
    if _DEFAULT_LLM is not None:
        return _DEFAULT_LLM

    # 1) config.toml
    configured = _build_provider_from_config()
    if configured is not None:
        _DEFAULT_LLM = configured
        return _DEFAULT_LLM

    # 2/3) env vars
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            _DEFAULT_LLM = AnthropicLLMProvider(
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
                model=os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            )
            return _DEFAULT_LLM
        except LLMError:
            pass
    if os.environ.get("OPENAI_API_KEY"):
        try:
            _DEFAULT_LLM = OpenAILLMProvider(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_BASE_URL"),
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            )
            return _DEFAULT_LLM
        except LLMError:
            pass

    # 4) 兜底 echo
    _DEFAULT_LLM = EchoLLMProvider()
    return _DEFAULT_LLM


def reset_default_provider_for_test() -> None:
    """测试用:清空缓存的 provider。"""
    global _DEFAULT_LLM
    _DEFAULT_LLM = None