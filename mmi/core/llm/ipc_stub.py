"""mmi.core.llm.ipc_stub —— TUI / IPC streaming entry stub (M4.1)。

`mmi.core.ipc_server` 的 send_message handler 走 anyio.from_thread.run 调
这个 async 函数,把每个 delta 包成 JSON-RPC notification 写回 TUI。
现阶段为 stub:固定 yield 'hello ' 三次,只为打通 IPC 流式协议管道。
真正的 LLM 接入留给 M4 wiring(用 get_default_provider().stream_chat()
包成 async 即可)。

与上面同名的 LLMProvider.stream_chat **不同**:
  - 类方法 LLMProvider.stream_chat → 同步生成器,直接传 OpenAI messages
  - 模块函数 stream_chat → AsyncIterator,IPC server 用
命名空间不冲突(一个是 self.stream_chat,一个是 mmi.core.llm.stream_chat)。

依赖项:无。
被依赖:__init__.py re-export; ipc_server.py 的 `from .llm import stream_chat`。
"""

from __future__ import annotations

from collections.abc import AsyncIterator


async def stream_chat(session_id: str, content: str) -> AsyncIterator[str]:
    """Yield token deltas. Stub: yields 'hello ' three times for any input."""
    for _ in range(3):
        yield "hello "
