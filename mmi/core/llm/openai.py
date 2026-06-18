"""mmi.core.llm.openai —— OpenAI 兼容 LLM 客户端。

依赖项:_types, base。
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator

from mmi.core.llm._types import Classification, LLMError
from mmi.core.llm.base import LLMProvider


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

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 4096,
        temperature=0.7,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
        response_format: dict | None = None,
    ) -> str:
        """OpenAI 兼容 chat()。

        R8.5.1b:按 provider-params 报告补 top_p / stop / response_format(均可选,
        None 不发)。各家(智谱/千问)都支持,具体语义各家可能略不同。
        (Kimi 已在 R8.5.3 从预置移除,要用走自定义)
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if top_p is not None:
            kwargs["top_p"] = top_p
        if stop is not None:
            kwargs["stop"] = stop
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            raise LLMError(f"OpenAI chat failed: {e}") from e

        if not resp.choices:
            raise LLMError("OpenAI chat: empty choices")
        content = resp.choices[0].message.content
        if content is None:
            raise LLMError("OpenAI chat: empty content")
        return content

    def stream_chat(self, messages: list[dict], *, max_tokens: int = 4096, temperature: float = 0.7) -> Iterator[str]:
        """OpenAI 真流式:同步迭代 stream=True 返回的 chunk。

        OpenAI SDK 的 stream=True 返回同步 `Stream[ChatCompletionChunk]`,
        直接同步迭代 yield 增量文本即可(调用方负责放到后台线程)。

        设计要点(spec 4.4):
          - 同步迭代器:不阻塞 — OpenAI SDK 的 stream 内部异步发请求
          - LLMError 包成 StreamError:与默认实现行为一致

        R8.5.1b:加 stream_options={"include_usage": true},
        让最后一块附带 usage 信息(各家都支持)。
        """
        from mmi.core.exceptions import StreamError
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
                stream_options={"include_usage": True},
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

    def classify(self, prompt: str, *, options: list[str]) -> Classification:
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
