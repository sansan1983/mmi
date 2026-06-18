"""mmi.core.llm.ipc_stub —— TUI / IPC streaming entry.

`mmi.core.ipc_server` 的 send_message handler 走 anyio.from_thread.run 调
这个 async 函数,把每个 delta 包成 JSON-RPC notification 写回 TUI。

P9.2 实现:调 get_default_provider().stream_chat(),把同步生成器桥接成
async 生成器。用 anyio.to_thread.run_sync 把流预生成,再异步 yield —
不阻塞 event loop,且与 OpenAI / Anthropic 真流式兼容(它们的
stream_chat 是 sync generator,底层走 httpx)。

与 LLMProvider.stream_chat 的区别:
  - 类方法 LLMProvider.stream_chat → 同步生成器,直接传 OpenAI messages
  - 模块函数 stream_chat          → AsyncIterator,IPC server 用

依赖项:mmi.core.llm.get_default_provider, anyio。
被依赖:__init__.py re-export; ipc_server.py 的 `from .llm import stream_chat`。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import anyio


async def stream_chat(session_id: str, content: str) -> AsyncIterator[str]:  # noqa: ARG001
    """Yield token deltas from the configured LLM provider.

    Parameters
    ----------
    session_id : str
        Session identifier (currently unused — passed through for protocol
        compatibility; future routing may consult it).
    content : str
        The user's message to send to the LLM.

    Yields
    ------
    str
        Text fragments from the provider's ``stream_chat``.

    Notes
    -----
    The synchronous ``stream_chat`` generator is materialised in a worker
    thread (``anyio.to_thread.run_sync``) before the async iteration begins.
    This keeps the event loop responsive but loses true token-by-token
    streaming for callers that consume ``ipc_server.send_message``. Future
    optimisation: stream chunks incrementally using ``anyio`` channels.
    """
    from mmi.core.llm import get_default_provider
    from mmi.core.llm._types import LLMError

    messages = [{"role": "user", "content": content}]
    try:
        provider = get_default_provider()
        chunks: list[str] = await anyio.to_thread.run_sync(
            lambda: list(provider.stream_chat(messages))
        )
    except LLMError as e:
        yield f"[LLM error: {e}]"
        return

    for chunk in chunks:
        if chunk:
            yield chunk
