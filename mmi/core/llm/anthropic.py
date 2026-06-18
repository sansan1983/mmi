"""mmi.core.llm.anthropic —— Anthropic Claude 直连客户端。

依赖项:_types, base。
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator

from mmi.core.llm._types import Classification, LLMError
from mmi.core.llm.base import LLMProvider


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

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 4096,
        temperature=0.7,
        top_p: float | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        """Anthropic chat()。

        R8.5.1b:按 provider-params 报告补 top_p / stop_sequences(均可选,
        None 不发)。注意:Anthropic 协议下停止词叫 stop_sequences(不是 OpenAI 的 stop)。
        """
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
        if top_p is not None:
            payload["top_p"] = top_p
        if stop_sequences is not None:
            payload["stop_sequences"] = stop_sequences
        data = self._post(payload)
        # 响应格式: {content: [{type: "text", text: "..."}], ...}
        blocks = data.get("content") or []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "text":
                text = b.get("text", "")
                if text:
                    return text
        raise LLMError("Anthropic chat: no text in response")

    def stream_chat(self, messages: list[dict], *, max_tokens: int = 4096, temperature: float = 0.7) -> Iterator[str]:
        """Anthropic 真 SSE 流式(DeepSeek / MiniMax 用 Anthropic 端点时也走这路径)。

        R8.5.2:替换原 fake 实现(只 yield 整段 chat 响应)。

        协议(SSE):
          event: message_start
          event: content_block_start
          event: content_block_delta
            data: {"type":"content_block_delta","index":N,
                   "delta":{"type":"text_delta","text":"Hello"}}
          event: content_block_stop
          event: message_delta
          event: message_stop

        实现要点:
          - 用 httpx.Client.stream("POST", url) 流式读 body
          - 解析 SSE 协议:`event:` 行 + `data:` 行配对(`\n\n` 分隔)
          - 只 yield `content_block_delta.delta.text`(text_delta 类型)
          - 错误处理:HTTPStatusError 转 LLMError(再被 stream_chat_with_retry 抓)
          - 中流网络/解析错误包成 StreamError
          - 不发 stream_options(Anthropic 协议无此概念)

        Yields:
            文本片段(每个 content_block_delta.text 一段)
        """
        import json as _json

        import httpx

        from mmi.core.exceptions import StreamError

        # 构造 payload(同 chat())
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
            "stream": True,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "Content-Type": "application/json",
        }

        try:
            with self._client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = resp.read().decode("utf-8", errors="replace")[:300]
                    raise LLMError(
                        f"Anthropic stream HTTP {resp.status_code}: {body}"
                    )
                # 解析 SSE — 状态机
                current_event = ""
                data_buf: list[str] = []
                for raw_line in resp.iter_lines():
                    line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", errors="replace")
                    if not line:
                        # 空行 = event 边界,处理累积的 event
                        if data_buf:
                            data_text = "\n".join(data_buf)
                            # 只关心 content_block_delta 里的 text_delta
                            if current_event == "content_block_delta":
                                try:
                                    evt = _json.loads(data_text)
                                    delta = evt.get("delta") or {}
                                    if delta.get("type") == "text_delta":
                                        text = delta.get("text") or ""
                                        if text:
                                            yield text
                                except _json.JSONDecodeError:
                                    pass  # 忽略解析失败的 chunk
                            data_buf = []
                            current_event = ""
                        continue
                    if line.startswith(":"):
                        # SSE 注释,忽略
                        continue
                    if line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data_buf.append(line[len("data:"):].lstrip())
                # 流结束,处理最后一批(若有)
                if data_buf and current_event == "content_block_delta":
                    data_text = "\n".join(data_buf)
                    try:
                        evt = _json.loads(data_text)
                        delta = evt.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            text = delta.get("text") or ""
                            if text:
                                yield text
                    except _json.JSONDecodeError:
                        pass
        except LLMError:
            raise
        except (httpx.TimeoutException, httpx.ConnectError, ConnectionError) as e:
            # 网络错误:LLMError,让上层 stream_chat_with_retry 区分 pre/mid-stream
            raise LLMError(f"Anthropic stream network error: {e}") from e
        except Exception as e:
            # 中流其它错误(解析 / 未知):包成 StreamError
            raise StreamError(f"Anthropic stream error: {e}") from e

    def classify(self, prompt: str, *, options: list[str]) -> Classification:
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
