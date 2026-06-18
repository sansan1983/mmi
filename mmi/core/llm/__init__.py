"""mmi.core.llm —— LLM 客户端抽象层(包入口,re-export 所有子模块符号)。

ARCHITECTURE.md §7 / §3.5.3 / §11：本模块是基线能力，主板自带的 LLM 接口。

子模块结构:
  - _types:    LLMError, Classification
  - base:      LLMProvider ABC + 默认 stream_chat + chat_with_retry + stream_chat_with_retry
  - echo:      EchoLLMProvider(默认 / 测试用)
  - openai:    OpenAILLMProvider(/v1/chat/completions 兼容)
  - anthropic: AnthropicLLMProvider(httpx 直连,真 SSE)
  - factory:   get_default_provider / _build_provider_from_config
  - ipc_stub:  顶层 stream_chat async stub(给 ipc_server 用)

向后兼容:
  - 之前所有 `from mmi.core.llm import X` / `from .llm import X` 仍工作
  - 模块名仍是 `mmi.core.llm`(从 .py 变成包)
  - `from mmi.core import llm as llm_module` 仍工作

设计原则:
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

from mmi.core.llm._types import Classification, LLMError
from mmi.core.llm.anthropic import AnthropicLLMProvider
from mmi.core.llm.base import LLMProvider
from mmi.core.llm.echo import EchoLLMProvider
from mmi.core.llm.factory import (
    get_default_provider,
    reset_default_provider_for_test,
)
from mmi.core.llm.ipc_stub import stream_chat
from mmi.core.llm.openai import OpenAILLMProvider

__all__ = [
    "LLMProvider",
    "LLMError",
    "Classification",
    "EchoLLMProvider",
    "OpenAILLMProvider",
    "AnthropicLLMProvider",
    "get_default_provider",
    "reset_default_provider_for_test",
    "stream_chat",
]
